#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 会话管理（仅标准库）：体检、列表、两步式重命名、迁移、备份与回滚。

重命名：rename --export 导出完整历史与 LPT 分片 → agent 产出 titles.json →
rename --import 默认干跑，加 --apply 落盘。默认标题长度 20–30 字，可放宽到 10–30。

迁移：默认同时迁移记忆与产出，并同步必要的会话 JSONL/子目录；
只要元数据时加 --metadata-only。

核心事实：
- 侧栏的「任务 / 空间」由 sessions.is_playground 决定：1=任务，0=空间。
- 空间归属由 sessions.cwd 决定，cwd 必须与已有空间完全一致（宽松匹配、严格写入）。
- 对话正文在 <home>/projects/<encoded-cwd>/<session-id>.jsonl，附件/子代理在同名目录。
- 侧栏缓存是 <home>/<user-id>/sidebar-list-snapshot.json；数据库才是权威。
- 有效标题以 JSONL 最后一条 custom-title 事件为准；数据库 title/custom_title 与快照 title 同步写。
- 记忆在 <workspace>/.workbuddy/memory/YYYY-MM-DD.md，变更范围从 changes-index 的 hunk 反推。
- 产物三路：artifact-index、changes-index、JSONL function_call 的 Write/Edit；迁移后旧路径保留硬链接（跨盘回退复制）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

VERSION = "1.4.0"
DEFAULT_HOME = Path(os.environ.get("WORKBUDDY_HOME", str(Path.home() / ".workbuddy")))
SNAP_GLOB = "*/sidebar-list-snapshot.json"


class UserError(Exception):
    pass


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def norm_cwd(value: str) -> str:
    s = str(value).strip().strip('"')
    s = s.replace("\\", "/")
    s = re.sub(r"/+", "/", s)
    if len(s) >= 2 and s[1] == ":":
        s = s[0].lower() + s[1:]
    if len(s) > 3 and s.endswith("/"):
        s = s[:-1]
    return s


def path_key(value) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def is_under(child, parent) -> bool:
    try:
        return os.path.commonpath([path_key(child), path_key(parent)]) == path_key(parent)
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def unique_dir(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}-{stamp}")
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}-{stamp}-{n}")
        n += 1
    return candidate


def unique_with_timestamp(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = path.stem
    suffix = path.suffix
    candidate = path.with_name(f"{base}_{stamp}{suffix}")
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{base}_{stamp}-{n}{suffix}")
        n += 1
    return candidate


def format_ms(ms) -> str:
    if not ms:
        return "-"
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def app_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WorkBuddy.exe"],
            capture_output=True, text=True, timeout=5, errors="replace",
        ).stdout
        return "WorkBuddy.exe" in out
    except Exception:
        return False


class WorkBuddy:
    def __init__(self, home: Path, user_id: str | None = None):
        self.home = Path(home).expanduser().resolve()
        self.db_path = self.home / "workbuddy.db"
        if not self.db_path.exists():
            raise UserError(f"找不到 WorkBuddy 数据库：{self.db_path}")
        self.con = sqlite3.connect(str(self.db_path), timeout=3)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA busy_timeout=3000")
        self.user_id = user_id or self.default_user_id()

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass

    def default_user_id(self):
        row = self.con.execute(
            "select user_id, count(*) c from sessions where deleted_at is null "
            "group by user_id order by c desc limit 1"
        ).fetchone()
        return row[0] if row and row[0] else None

    def session(self, sid: str):
        row = self.con.execute("select * from sessions where id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def all_sessions(self, include_deleted: bool = False):
        where = "" if include_deleted else "deleted_at is null and "
        if self.user_id and self.user_id != "*":
            rows = self.con.execute(
                f"select * from sessions where {where}user_id=? "
                "order by last_activity_at desc", (self.user_id,)
            ).fetchall()
        else:
            rows = self.con.execute(
                f"select * from sessions where {where}1=1 "
                "order by last_activity_at desc"
            ).fetchall()
        return [dict(r) for r in rows]

    def find_sessions(self, query: str):
        q = str(query).strip()
        rows = self.all_sessions()
        hits = [r for r in rows if r["id"] == q]
        if not hits and len(q) >= 6:
            hits = [r for r in rows if r["id"].startswith(q)]
        if not hits:
            ql = q.lower()
            hits = [
                r for r in rows
                if (r.get("title") or "").lower() == ql
                or (r.get("custom_title") or "").lower() == ql
            ]
        if not hits:
            ql = q.lower()
            hits = [
                r for r in rows
                if ql in (r.get("title") or "").lower()
                or ql in (r.get("custom_title") or "").lower()
            ]
        return hits

    def spaces(self):
        if self.user_id and self.user_id != "*":
            rows = self.con.execute(
                "select cwd, count(*) n, max(last_activity_at) last from sessions "
                "where deleted_at is null and is_playground=0 and user_id=? "
                "group by cwd order by last desc", (self.user_id,)
            ).fetchall()
        else:
            rows = self.con.execute(
                "select cwd, count(*) n, max(last_activity_at) last from sessions "
                "where deleted_at is null and is_playground=0 "
                "group by cwd order by last desc"
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_space(self, query: str) -> str:
        spaced = self.spaces()
        if not spaced:
            raise UserError("数据库里没有任何空间（is_playground=0 且未删除的会话）。")
        raw_q = str(query).strip()
        nq = norm_cwd(raw_q).lower()
        exact = [s for s in spaced if norm_cwd(s["cwd"]).lower() == nq]
        if len(exact) == 1:
            return exact[0]["cwd"]
        loose = []
        for s in spaced:
            n = norm_cwd(s["cwd"])
            if n.lower().endswith("/" + nq) or Path(n).name.lower() == raw_q.lower():
                loose.append(s)
        if len(loose) == 1:
            return loose[0]["cwd"]
        if len(exact) > 1 or len(loose) > 1:
            candidates = exact or loose
            lines = "\n".join(
                f"  - {s['cwd']} ({s['n']} 条, 最近 {format_ms(s['last'])})"
                for s in candidates
            )
            raise UserError(f"目标空间不唯一，请用完整路径指定：\n{lines}")
        lines = "\n".join(
            f"  - {s['cwd']} ({s['n']} 条, 最近 {format_ms(s['last'])})"
            for s in spaced[:20]
        )
        raise UserError(
            f"找不到已有空间：{raw_q}\n只允许迁移到已有空间。可用空间：\n{lines}"
        )

    @staticmethod
    def encode_cwd(cwd: str) -> str:
        n = norm_cwd(cwd)
        if len(n) >= 2 and n[1] == ":":
            n = n[0].lower() + n[1:]
        return n.replace(":/", "-").replace(":", "-").replace("/", "-")

    def project_dir_for_space(self, cwd: str) -> Path:
        row = self.con.execute(
            "select id from sessions where cwd=? and deleted_at is null "
            "order by is_playground asc, last_activity_at desc limit 1", (cwd,)
        ).fetchone()
        if row:
            found = list((self.home / "projects").glob(f"*/{row[0]}.jsonl"))
            if found:
                return found[0].parent
        return self.home / "projects" / self.encode_cwd(cwd)

    def source_project_dir(self, sid: str) -> Path:
        found = list((self.home / "projects").glob(f"*/{sid}.jsonl"))
        if not found:
            raise UserError(
                f"找不到会话文件 projects/*/{sid}.jsonl；可能已被移动或删除。"
            )
        if len(found) > 1:
            lines = "\n".join(f"  - {p}" for p in found)
            raise UserError(f"发现多个同名会话文件，请人工确认：\n{lines}")
        return found[0].parent

    def snapshots(self):
        out = []
        for p in sorted(self.home.glob(SNAP_GLOB)):
            try:
                data = json.loads(read_text(p))
            except Exception:
                continue
            if any(item.get("id") for item in data.get("items", [])):
                out.append((p, data))
        return out

    def update_session(self, sid: str, cwd: str | None = None, is_playground: int | None = None):
        sets, params = [], []
        if cwd is not None:
            sets.append("cwd=?")
            params.append(cwd)
        if is_playground is not None:
            sets.append("is_playground=?")
            params.append(int(is_playground))
        if not sets:
            return
        params.append(sid)
        last = None
        for attempt in range(3):
            try:
                with self.con:
                    cur = self.con.execute(
                        f"update sessions set {', '.join(sets)} where id=?", params
                    )
                    if cur.rowcount != 1:
                        raise UserError(f"更新 sessions 影响行数异常：{cur.rowcount}")
                last = None
                break
            except sqlite3.OperationalError as exc:
                last = exc
                if ("locked" in str(exc).lower() or "busy" in str(exc).lower()) and attempt < 2:
                    time.sleep(1)
                    continue
                raise
        if last:
            raise UserError(f"数据库写入失败（已重试 3 次）：{last}")
        try:
            self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass

    def backup_db(self, dest_dir: Path):
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "workbuddy.db"
        try:
            dst = sqlite3.connect(str(dest))
            self.con.backup(dst)
            dst.close()
        except Exception:
            shutil.copy2(self.db_path, dest)
        for name in ("workbuddy.db-wal", "workbuddy.db-shm"):
            src = self.home / name
            if src.exists():
                shutil.copy2(src, dest_dir / name)


class Backup:
    def __init__(self, wb: WorkBuddy, base: Path | None = None):
        self.wb = wb
        self.base = unique_dir((Path(base) if base else wb.home / "backup" / f"workbuddy-move-{now_stamp()}").expanduser().resolve())
        self.base.mkdir(parents=True, exist_ok=True)
        self.items = []
        self.removed_dirs = []

    def item_dir(self, sid: str) -> Path:
        d = self.base / sid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def copy_file(self, src: Path, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def copy_tree(self, src: Path, dest: Path) -> Path:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return dest

    def batch_manifest(self):
        data = {
            "version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "workbuddy_home": str(self.wb.home),
            "items": self.items,
            "removed_dirs": self.removed_dirs,
        }
        path = self.base / "batch.json"
        write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
        return path


def load_json(path: Path):
    try:
        return json.loads(read_text(path))
    except Exception:
        return None


def change_details(wb: WorkBuddy, sid: str):
    index_path = wb.home / "changes-index" / f"{sid}.json"
    index = load_json(index_path)
    if not index:
        return []
    out = []
    for change in index.get("changes", []):
        ref = change.get("detailRef")
        if not ref:
            continue
        detail_path = wb.home / "changes-detail" / sid / ref
        detail = load_json(detail_path)
        if detail:
            out.append((change, detail))
    return out


def memory_heading(line: str):
    m = re.match(r"^(#{1,6})\s+", line)
    return len(m.group(1)) if m else 0


def demote_headings(block: str) -> str:
    lines = []
    for line in block.splitlines():
        m = re.match(r"^(#{1,6})(\s+)", line)
        if m:
            hashes = m.group(1)
            line = ("#" * min(6, len(hashes) + 1)) + line[len(hashes):]
        lines.append(line)
    return "\n".join(lines)


def strip_leading_h1(block: str) -> str:
    lines = block.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^#\s+\d{4}-\d{2}-\d{2}", lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def collect_memory_blocks(wb: WorkBuddy, sid: str, old_cwd: str):
    """返回 [{file, blocks:[...]}]，只移动能从源记忆文件精确定位的段落。"""
    memory_root = Path(old_cwd) / ".workbuddy" / "memory"
    per_file: dict[str, list[str]] = {}
    for change, detail in change_details(wb, sid):
        for f in detail.get("change", {}).get("files", []):
            fp = f.get("filePath")
            if not fp:
                continue
            p = Path(fp)
            if not is_under(p, memory_root) or p.suffix.lower() != ".md":
                continue
            candidates = []
            for hunk in f.get("hunks", []):
                lines = []
                for line in hunk.get("lines", []):
                    if line.startswith("+") and not line.startswith("+++"):
                        lines.append(line[1:])
                block = "\n".join(lines).strip("\n")
                if block.strip():
                    candidates.append(block)
            if candidates:
                per_file.setdefault(str(p), []).extend(candidates)
    result = []
    for fp, candidates in per_file.items():
        p = Path(fp)
        if not p.exists():
            continue
        text = read_text(p).replace("\r\n", "\n")
        selected: list[str] = []
        for cand in sorted(set(candidates), key=len, reverse=True):
            block = cand.replace("\r\n", "\n").strip("\n")
            if not block:
                continue
            if any(block in s for s in selected):
                continue
            if block not in text:
                continue
            selected = [s for s in selected if s not in block]
            selected.append(block)
        if selected:
            result.append({"file": p, "blocks": selected})
    return result


def remove_blocks(text: str, blocks: list[str]) -> tuple[str, bool]:
    original = text
    t = text.replace("\r\n", "\n")
    ranges = []
    for block in blocks:
        b = block.replace("\r\n", "\n").strip("\n")
        idx = t.find(b)
        if idx >= 0:
            start = idx
            end = idx + len(b)
            while start > 0 and t[start - 1] == "\n":
                start -= 1
            while end < len(t) and t[end] == "\n":
                end += 1
            ranges.append((start, end))
    for start, end in sorted(ranges, reverse=True):
        prefix = t[:start].rstrip("\n")
        suffix = t[end:].lstrip("\n")
        t = (prefix + "\n\n" + suffix).rstrip() + "\n" if suffix else prefix.rstrip() + "\n"
    return t, t != original


def append_memory_block(target: Path, date: str, block: str, marker: str, old_cwd: str, sid: str):
    block2 = demote_headings(strip_leading_h1(block)).strip()
    if target.exists():
        cur = read_text(target)
        if marker in cur:
            return cur, ""
        appended = "\n\n---\n\n" + marker + "\n\n" + block2 + "\n"
        new = cur.rstrip() + appended
    else:
        prefix = f"# {date}\n\n" + marker + "\n\n"
        new = prefix + block2 + "\n"
        appended = new
    write_text(target, new)
    return new, appended


class Mover:
    def __init__(self, wb: WorkBuddy, backup: Backup, opts):
        self.wb = wb
        self.backup = backup
        self.opts = opts
        self.manifests = []

    def _backup_output(self, sid: str, src: Path, old_cwd: Path) -> Path | None:
        if not src.exists() or not src.is_file():
            return None
        rel = os.path.relpath(str(src), str(old_cwd))
        dest = self.backup.item_dir(sid) / "outputs" / rel
        return self.backup.copy_file(src, dest)

    def _move_output(self, sid: str, src: Path, old_cwd: Path, target_cwd: Path):
        rel = os.path.relpath(str(src), str(old_cwd))
        dst = Path(target_cwd) / rel
        record = {
            "src": str(src), "dst": str(dst), "rel": rel,
            "status": "pending", "link_created": False,
            "renamed": False, "src_backup": None, "dst_backup": None,
        }
        backup_path = self._backup_output(sid, src, old_cwd)
        record["src_backup"] = str(backup_path) if backup_path else None
        if not src.exists():
            if dst.exists():
                record["status"] = "already-moved"
            else:
                record["status"] = "missing"
            return record
        if src.is_dir():
            record["status"] = "directory-skipped"
            return record
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            try:
                same = src.stat().st_size == dst.stat().st_size and sha256_file(src) == sha256_file(dst)
            except Exception:
                same = False
            if same:
                record["status"] = "same-exists"
                return record
            dst = unique_with_timestamp(dst)
            record["dst"] = str(dst)
            record["renamed"] = True
        else:
            record["dst_backup"] = None
        shutil.move(str(src), str(dst))
        try:
            os.link(dst, src)
            record["link_created"] = True
        except Exception:
            shutil.copy2(dst, src)
            record["link_created"] = False
        record["status"] = "moved"
        return record

    def _collect_outputs(self, sid: str, old_cwd: Path, jsonl: Path | None = None):
        paths: list[Path] = []
        art = load_json(self.wb.home / "artifact-index" / f"{sid}.json")
        if art:
            for item in art.get("artifacts", []):
                uri = item.get("uri") or ""
                if uri.startswith("file://"):
                    raw = unquote(urlparse(uri).path)
                    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
                        raw = raw[1:]
                    paths.append(Path(raw))
        for _change, detail in change_details(self.wb, sid):
            for f in detail.get("change", {}).get("files", []):
                fp = f.get("filePath")
                if fp and f.get("action") in ("create", "modify", "rename"):
                    paths.append(Path(fp))
        if jsonl:
            paths.extend(sorted(tool_output_paths(jsonl, old_cwd), key=str))
        seen = set()
        out = []
        for p in paths:
            if not is_under(p, old_cwd):
                continue
            if is_under(p, old_cwd / ".workbuddy"):
                continue
            k = path_key(p)
            if k in seen:
                continue
            seen.add(k)
            out.append(p)
        return out

    def _patch_snapshots(self, sid: str, target_cwd: str, item_dir: Path):
        patched = []
        for path, data in self.wb.snapshots():
            hit = False
            for item in data.get("items", []):
                if item.get("id") == sid:
                    item.setdefault("space", {})["name"] = target_cwd
                    hit = True
            if not hit:
                continue
            backup = self.backup.copy_file(path, item_dir / "snapshot" / path.name)
            write_text(path, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            patched.append({"path": str(path), "backup": str(backup)})
        return patched

    def move(self, session: dict, target_cwd: str | None, mode: str):
        sid = session["id"]
        old_cwd_raw = session["cwd"]
        old_cwd = Path(old_cwd_raw)
        title = session.get("custom_title") or session.get("title") or sid
        old_flag = int(session.get("is_playground") or 0)
        if mode == "space":
            assert target_cwd
            if norm_cwd(old_cwd_raw) == norm_cwd(target_cwd):
                return {
                    "session_id": sid, "title": title, "status": "skipped",
                    "reason": "已经在目标空间", "old_cwd": old_cwd_raw,
                    "target_cwd": target_cwd,
                }
            new_cwd = target_cwd
            new_flag = 0
        else:
            new_cwd = old_cwd_raw
            new_flag = 1
            target_cwd = old_cwd_raw

        item_dir = self.backup.item_dir(sid)
        src_project = None
        dst_project = None
        pre_outputs = []
        with_assets = bool(getattr(self.opts, "with_assets", False))
        manifest = {
            "version": 1, "session_id": sid, "title": title, "mode": mode,
            "from_cwd": old_cwd_raw, "to_cwd": new_cwd,
            "metadata_only": not with_assets,
            "old_is_playground": old_flag, "new_is_playground": new_flag,
            "backup_dir": str(item_dir), "memory": [], "outputs": [],
            "snapshots": [], "session": {}, "db_changed": False,
        }
        self.backup.copy_file(self.wb.db_path, item_dir / "db" / "workbuddy.db")
        write_text(item_dir / "db-row.json", json.dumps(session, ensure_ascii=False, indent=2))
        manifest_path = item_dir / "manifest.json"
        write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

        if mode == "space":
            src_project = self.wb.source_project_dir(sid)
            src_jsonl = src_project / f"{sid}.jsonl"
            src_dir = src_project / sid
            manifest["session"] = {
                "src_jsonl": str(src_jsonl), "src_dir": str(src_dir) if src_dir.exists() else None,
                "dst_jsonl": None, "dst_dir": None,
                "target_jsonl_backup": None, "target_dir_backup": None,
            }
            dst_project = self.wb.project_dir_for_space(new_cwd)
            dst_project.mkdir(parents=True, exist_ok=True)
            dst_jsonl = dst_project / f"{sid}.jsonl"
            dst_dir = dst_project / sid
            manifest["session"]["dst_jsonl"] = str(dst_jsonl)
            manifest["session"]["dst_dir"] = str(dst_dir)
            self.backup.copy_file(src_jsonl, item_dir / "session" / f"{sid}.jsonl")
            if src_dir.exists():
                self.backup.copy_tree(src_dir, item_dir / "session" / sid)
            if dst_jsonl.exists():
                manifest["session"]["target_jsonl_backup"] = str(
                    self.backup.copy_file(dst_jsonl, item_dir / "session" / f"target-existing-{sid}.jsonl")
                )
            if dst_dir.exists():
                manifest["session"]["target_dir_backup"] = str(
                    self.backup.copy_tree(dst_dir, item_dir / "session" / f"target-existing-{sid}")
                )
            if with_assets and not self.opts.no_artifacts:
                # 必须在搬走 JSONL 之前解析正文里的写文件调用。
                pre_outputs = self._collect_outputs(sid, old_cwd, src_jsonl)
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

        try:
            self.wb.update_session(
                sid,
                cwd=new_cwd if mode == "space" else None,
                is_playground=new_flag,
            )
            manifest["db_changed"] = True
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

            if mode == "space":
                if dst_jsonl.exists():
                    os.replace(src_jsonl, dst_jsonl)
                else:
                    shutil.move(str(src_jsonl), str(dst_jsonl))
                if src_dir.exists():
                    if dst_dir.exists():
                        shutil.rmtree(dst_dir)
                    shutil.move(str(src_dir), str(dst_dir))

                memory_items = collect_memory_blocks(self.wb, sid, old_cwd_raw) if with_assets else []
                for mem in memory_items:
                    src_file = mem["file"]
                    date = src_file.stem
                    target_file = Path(new_cwd) / ".workbuddy" / "memory" / src_file.name
                    marker = f"## 迁移自 {old_cwd_raw}（会话 {sid}）"
                    src_backup = self.backup.copy_file(
                        src_file, item_dir / "memory" / date / "source.md"
                    )
                    target_backup = None
                    target_existed = target_file.exists()
                    if target_existed:
                        target_backup = self.backup.copy_file(
                            target_file, item_dir / "memory" / date / "target.md"
                        )
                    new_source, changed = remove_blocks(read_text(src_file), mem["blocks"])
                    if not changed:
                        continue
                    write_text(src_file, new_source)
                    try:
                        _, appended = append_memory_block(
                            target_file, date, "\n\n".join(mem["blocks"]), marker,
                            old_cwd_raw, sid,
                        )
                    except Exception as exc:
                        self.backup.copy_file(src_backup, src_file)
                        raise UserError(f"写入目标记忆失败：{target_file}：{exc}")
                    manifest["memory"].append({
                        "source_file": str(src_file), "target_file": str(target_file),
                        "target_existed": target_existed, "marker": marker,
                        "appended": appended, "blocks": mem["blocks"],
                        "source_backup": str(src_backup),
                        "target_backup": str(target_backup) if target_backup else None,
                    })
                    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

                if with_assets and not self.opts.no_artifacts:
                    for out in pre_outputs:
                        rec = self._move_output(sid, out, old_cwd, Path(new_cwd))
                        manifest["outputs"].append(rec)
                    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

                manifest["snapshots"] = self._patch_snapshots(sid, new_cwd, item_dir)
                write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

            checks = self.verify(manifest)
            if not all(checks.values()):
                time.sleep(1)
                checks = self.verify(manifest)
            if not all(checks.values()):
                failed = [k for k, v in checks.items() if not v]
                self.rollback_manifest(manifest)
                raise UserError("验证失败，已回滚：" + "、".join(failed))
            manifest["status"] = "ok"
            manifest["checks"] = checks
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
            self.manifests.append(str(manifest_path))
            if str(manifest_path) not in self.backup.items:
                self.backup.items.append(str(manifest_path.resolve()))
            return {
                "session_id": sid, "title": title, "status": "ok",
                "old_cwd": old_cwd_raw, "target_cwd": new_cwd,
                "manifest": str(manifest_path), "backup": str(item_dir),
                "metadata_only": manifest.get("metadata_only", True),
                "src_project": str(src_project) if src_project else None,
                "dst_project": str(dst_project) if dst_project else None,
                "memory": len(manifest["memory"]), "outputs": len(manifest["outputs"]),
                "checks": checks,
            }
        except UserError as exc:
            if manifest.get("db_changed"):
                try:
                    self.rollback_manifest(manifest)
                except Exception as rb_exc:
                    raise UserError(f"迁移异常且回滚失败：{exc}；回滚错误：{rb_exc}")
                raise UserError(f"迁移异常，已回滚：{exc}")
            raise
        except Exception as exc:
            if not manifest.get("db_changed"):
                raise UserError(f"迁移异常（尚未写入数据库）：{exc}")
            try:
                self.rollback_manifest(manifest)
            except Exception as rb_exc:
                raise UserError(f"迁移异常且回滚失败：{exc}；回滚错误：{rb_exc}")
            raise UserError(f"迁移异常，已回滚：{exc}")

    def verify(self, manifest: dict):
        sid = manifest["session_id"]
        row = self.wb.session(sid)
        checks = {
            "db_cwd": bool(row) and norm_cwd(row["cwd"]) == norm_cwd(manifest["to_cwd"]),
            "db_is_playground": bool(row) and int(row["is_playground"] or 0) == manifest["new_is_playground"],
        }
        if manifest["mode"] == "space":
            dst_jsonl = Path(manifest["session"]["dst_jsonl"])
            src_jsonl = Path(manifest["session"]["src_jsonl"])
            checks["session_jsonl"] = dst_jsonl.exists() and not src_jsonl.exists()
            checks["session_dir"] = True
            if manifest["session"].get("src_dir"):
                checks["session_dir"] = Path(manifest["session"]["dst_dir"]).exists() and not Path(manifest["session"]["src_dir"]).exists()
            for mem in manifest["memory"]:
                src = Path(mem["source_file"])
                tgt = Path(mem["target_file"])
                src_text = read_text(src) if src.exists() else ""
                checks[f"memory_src:{src.name}"] = not any(
                    block in src_text for block in mem.get("blocks", [])
                )
                checks[f"memory_dst:{tgt.name}"] = tgt.exists() and mem["marker"] in read_text(tgt)
            for out in manifest["outputs"]:
                if out["status"] in ("moved", "already-moved", "same-exists"):
                    checks[f"output:{Path(out['dst']).name}"] = Path(out["dst"]).exists()
            for snap in manifest["snapshots"]:
                data = load_json(Path(snap["path"]))
                checks[f"snapshot:{Path(snap['path']).parent.name}"] = bool(data) and any(
                    item.get("id") == sid and (item.get("space") or {}).get("name") == manifest["to_cwd"]
                    for item in data.get("items", [])
                )
        return checks

    def rollback_manifest(self, manifest: dict):
        sid = manifest["session_id"]
        self.wb.update_session(
            sid,
            cwd=manifest["from_cwd"],
            is_playground=manifest["old_is_playground"],
        )
        if manifest["mode"] == "space":
            sess = manifest["session"]
            src_jsonl = Path(sess["src_jsonl"])
            dst_jsonl = Path(sess["dst_jsonl"])
            if dst_jsonl.exists():
                src_jsonl.parent.mkdir(parents=True, exist_ok=True)
                if src_jsonl.exists():
                    src_jsonl.unlink()
                shutil.move(str(dst_jsonl), str(src_jsonl))
            if sess.get("target_jsonl_backup") and Path(sess["target_jsonl_backup"]).exists():
                shutil.copy2(sess["target_jsonl_backup"], dst_jsonl)
            src_dir = Path(sess["src_dir"]) if sess.get("src_dir") else None
            dst_dir = Path(sess["dst_dir"]) if sess.get("dst_dir") else None
            if src_dir and dst_dir and dst_dir.exists():
                if src_dir.exists():
                    shutil.rmtree(src_dir)
                shutil.move(str(dst_dir), str(src_dir))
            if sess.get("target_dir_backup") and Path(sess["target_dir_backup"]).exists():
                if dst_dir and dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(sess["target_dir_backup"], dst_dir)
            for mem in manifest.get("memory", []):
                src = Path(mem["source_file"])
                tgt = Path(mem["target_file"])
                if Path(mem["source_backup"]).exists():
                    shutil.copy2(mem["source_backup"], src)
                if tgt.exists() and mem.get("appended"):
                    cur = read_text(tgt)
                    if mem["appended"] in cur:
                        if mem.get("target_existed"):
                            write_text(tgt, cur.replace(mem["appended"], "", 1).rstrip() + "\n")
                        else:
                            tgt.unlink()
                    elif not mem.get("target_existed"):
                        tgt.unlink()
            for out in manifest.get("outputs", []):
                src = Path(out["src"])
                dst = Path(out["dst"])
                if out.get("link_created") and src.exists():
                    try:
                        src.unlink()
                    except Exception:
                        pass
                if dst.exists():
                    if src.exists():
                        src.unlink()
                    shutil.move(str(dst), str(src))
                if out.get("dst_backup") and Path(out["dst_backup"]).exists():
                    shutil.copy2(out["dst_backup"], dst)
            for snap in manifest.get("snapshots", []):
                if Path(snap["backup"]).exists():
                    shutil.copy2(snap["backup"], snap["path"])


def print_spaces(wb: WorkBuddy, as_json=False):
    spaces = wb.spaces()
    if as_json:
        print(json.dumps({"user_id": wb.user_id, "spaces": spaces}, ensure_ascii=False, indent=2))
        return
    print(f"用户: {wb.user_id or '-'}")
    print(f"{'空间路径':<60} {'会话数':>6}  最近活跃")
    print("-" * 88)
    for s in spaces:
        print(f"{s['cwd']:<60} {s['n']:>6}  {format_ms(s['last'])}")


def print_sessions(rows, as_json=False):
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    print(f"{'ID':<38} {'任务?':<5} {'空间':<28} {'最近活跃':<18} 标题")
    print("-" * 130)
    for r in rows:
        print(
            f"{r['id']:<38} {'是' if r.get('is_playground') else '否':<5} "
            f"{r['cwd'][:28]:<28} {format_ms(r.get('last_activity_at')):<18} "
            f"{r.get('custom_title') or r.get('title') or ''}"
        )


def select_sessions(wb: WorkBuddy, queries: list[str]):
    selected = []
    for q in queries:
        hits = wb.find_sessions(q)
        if not hits:
            raise UserError(f"找不到会话：{q}")
        if len(hits) > 1:
            print_sessions(hits)
            raise UserError(
                f"“{q}”命中 {len(hits)} 条，请改用完整的 session ID 或更精确的标题。"
            )
        selected.append(hits[0])
    seen = set()
    out = []
    for s in selected:
        if s["id"] not in seen:
            seen.add(s["id"])
            out.append(s)
    return out


def filter_session_rows(rows, args):
    if getattr(args, "keyword", None):
        kw = args.keyword.lower()
        rows = [
            r for r in rows
            if kw in (r.get("title") or "").lower()
            or kw in (r.get("custom_title") or "").lower()
        ]
    if getattr(args, "cwd", None):
        needle = norm_cwd(args.cwd).lower()
        rows = [r for r in rows if needle in norm_cwd(r.get("cwd") or "").lower()]
    area = getattr(args, "area", "all")
    if area == "task":
        rows = [r for r in rows if int(r.get("is_playground") or 0) == 1]
    elif area == "space":
        rows = [r for r in rows if int(r.get("is_playground") or 0) == 0]
    if getattr(args, "since", None):
        try:
            start = int(datetime.strptime(args.since, "%Y-%m-%d").timestamp() * 1000)
        except ValueError:
            raise UserError("--since 需要 YYYY-MM-DD 格式")
        rows = [r for r in rows if int(r.get("last_activity_at") or 0) >= start]
    return rows


def select_by_ids(wb: WorkBuddy, ids_text: str):
    wanted = [x.strip() for x in re.split(r"[,\s]+", ids_text or "") if x.strip()]
    sessions = wb.all_sessions()
    out, errors = [], []
    for prefix in wanted:
        hits = [s for s in sessions if s["id"].startswith(prefix)]
        if not hits:
            errors.append(f"{prefix}(未找到)")
        elif len(hits) > 1:
            errors.append(f"{prefix}(命中 {len(hits)} 条)")
        else:
            out.append(hits[0])
    if errors:
        raise UserError("无法唯一确定会话：" + "、".join(errors))
    seen, unique = set(), []
    for s in out:
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        unique.append(s)
    return unique


def normalize_space_path(value: str) -> str:
    s = str(value).strip().strip('"').replace("\\", "/")
    s = re.sub(r"/+", "/", s)
    if len(s) >= 2 and s[1] == ":":
        s = s[0].upper() + s[1:]
    if len(s) > 3:
        s = s.rstrip("/")
    if not re.match(r"^[A-Za-z]:/", s):
        raise UserError("--create-space 需要 Windows 绝对路径，例如 D:/VMs")
    return s


def resolve_target_space(wb: WorkBuddy, value: str, create: bool, allow_missing: bool = False):
    try:
        return wb.resolve_space(value)
    except UserError as exc:
        if not create or "找不到已有空间" not in str(exc):
            raise
        path = normalize_space_path(value)
        target = Path(path)
        if target.exists():
            if not target.is_dir():
                raise UserError(f"目标路径不是目录：{path}")
            print(f"[INFO] 使用已有目录创建空间：{path}（首个迁入会话作为种子）")
            return path
        if not allow_missing:
            raise UserError(f"目录不存在：{path}。确认在该路径创建空间请加 --allow-missing。")
        target.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 新建目录并创建空间：{path}（首个迁入会话作为种子）")
        return path


def cmd_move(args):
    wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
    try:
        if getattr(args, "require_closed", False) and app_running():
            print("错误：WorkBuddy 正在运行，--require-closed 要求先退出应用。", file=sys.stderr)
            return 3
        if args.running_check and app_running():
            print("提示：检测到 WorkBuddy 正在运行。按配置允许热写；若侧栏未刷新，请切换空间或重启应用。")
        sessions = select_sessions(wb, args.session)
        create = bool(getattr(args, "create_space", False))
        allow_missing = bool(getattr(args, "allow_missing", False))
        if args.mode == "space":
            if not args.to:
                raise UserError("迁移到空间时必须提供 --to。")
            if len(args.to) == 1:
                targets = [resolve_target_space(wb, args.to[0], create, allow_missing)] * len(sessions)
            elif len(args.to) == len(sessions):
                targets = [resolve_target_space(wb, t, create, allow_missing) for t in args.to]
            else:
                raise UserError("--to 的数量必须是 1，或与会话数量一致。")
        else:
            targets = [None] * len(sessions)
        backup = Backup(wb, Path(args.backup_dir) if args.backup_dir else None)
        wb.backup_db(backup.base / "db")
        mover = Mover(wb, backup, args)
        results = []
        for session, target in zip(sessions, targets):
            try:
                result = mover.move(session, target, args.mode)
                results.append(result)
                if result["status"] == "ok":
                    mode_label = "仅元数据" if result.get("metadata_only") else "元数据+记忆/产出"
                    print(
                        f"[OK] {result['title']}  {result['old_cwd']} -> {result['target_cwd']}  "
                        f"[{mode_label}] 记忆 {result['memory']} 文件 / 产出 {result['outputs']} 个"
                    )
                    print(f"     备份: {result['backup']}")
                else:
                    print(f"[SKIP] {result['title']}：{result.get('reason')}")
            except UserError as exc:
                print(f"[FAIL] {session.get('title') or session['id']}：{exc}", file=sys.stderr)
                results.append({"session_id": session["id"], "status": "failed", "error": str(exc)})
            except Exception as exc:
                print(f"[FAIL] {session.get('title') or session['id']}：{exc}", file=sys.stderr)
                results.append({"session_id": session["id"], "status": "failed", "error": str(exc)})
        removed_dirs = []
        if not getattr(args, "keep_orphans", False):
            src_dirs = [r.get("src_project") for r in results if r.get("src_project")]
            dst_dirs = [r.get("dst_project") for r in results if r.get("dst_project")]
            removed_dirs = clean_orphan_project_dirs(wb.home, src_dirs, keep=dst_dirs)
            backup.removed_dirs = removed_dirs
        batch = backup.batch_manifest()
        ok = sum(1 for r in results if r.get("status") == "ok")
        skip = sum(1 for r in results if r.get("status") == "skipped")
        fail = sum(1 for r in results if r.get("status") == "failed")
        print(f"\n完成：成功 {ok}，跳过 {skip}，失败 {fail}")
        if removed_dirs:
            print(f"已清理 {len(removed_dirs)} 个空源项目目录：")
            for d in removed_dirs:
                print(f"  - {d}")
        print(f"批次清单：{batch}")
        if args.json:
            print(json.dumps({"results": results, "batch_manifest": str(batch)}, ensure_ascii=False, indent=2))
        return 0 if fail == 0 else 1
    finally:
        wb.close()


def cmd_rollback(args):
    wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
    try:
        if getattr(args, "require_closed", False) and app_running():
            print("错误：WorkBuddy 正在运行，--require-closed 要求先退出应用。", file=sys.stderr)
            return 3
        manifests = []
        if args.manifest:
            manifests = [Path(p).expanduser().resolve() for p in args.manifest]
        elif args.batch:
            batch_path = Path(args.batch)
            data = load_json(batch_path)
            if not data:
                raise UserError(f"无法读取批次清单：{args.batch}")
            base = batch_path.resolve().parent
            manifests = [
                Path(item) if Path(item).is_absolute() else base / Path(item)
                for item in data.get("items", [])
            ]
            if not manifests:
                raise UserError(f"批次清单里没有可回滚的条目：{args.batch}")
        else:
            raise UserError("请提供 --manifest 或 --batch。")
        mover = Mover(wb, None, args)
        for path in reversed(manifests):
            data = load_json(path)
            if not data:
                print(f"[FAIL] 无法读取清单：{path}", file=sys.stderr)
                continue
            try:
                mover.rollback_manifest(data)
                print(f"[OK] 已回滚 {data.get('title')} ({data.get('session_id')})")
            except Exception as exc:
                print(f"[FAIL] 回滚 {data.get('session_id')} 失败：{exc}", file=sys.stderr)
        return 0
    finally:
        wb.close()


def cmd_find(args):
    wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
    try:
        if args.query:
            rows = wb.find_sessions(args.query)
        else:
            rows = wb.all_sessions()[: args.limit]
        if not rows:
            raise UserError(f"找不到会话：{args.query}")
        print_sessions(rows, args.json)
        return 0
    finally:
        wb.close()


def cmd_show(args):
    wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
    try:
        row = wb.session(args.session_id)
        if not row:
            raise UserError(f"找不到会话：{args.session_id}")
        if args.json:
            print(json.dumps(row, ensure_ascii=False, indent=2))
        else:
            for k, v in row.items():
                print(f"{k} = {v!r}")
        return 0
    finally:
        wb.close()


def _finish_doctor(checks, as_json: bool):
    if as_json:
        print(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            print(f"[{c['status'].upper()}] {c['check']}: {c['detail']}")
        ok = sum(1 for c in checks if c["status"] == "ok")
        warn = sum(1 for c in checks if c["status"] == "warn")
        fail = sum(1 for c in checks if c["status"] == "fail")
        print(f"\n体检完成：{ok} OK, {warn} WARN, {fail} FAIL")
    return 0 if all(c["status"] == "ok" for c in checks) else 1


def cmd_doctor(args):
    home = Path(args.workbuddy_home).expanduser().resolve()
    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    db_path = home / "workbuddy.db"
    if not db_path.exists():
        add("数据库", "fail", f"未找到 {db_path}")
        return _finish_doctor(checks, args.json)
    try:
        wb = WorkBuddy(home, "*")
    except Exception as exc:
        add("数据库", "fail", str(exc))
        return _finish_doctor(checks, args.json)
    try:
        try:
            integrity = wb.con.execute("PRAGMA integrity_check").fetchone()[0]
        except Exception as exc:
            integrity = f"error: {exc}"
        add(
            "数据库",
            "ok" if integrity == "ok" else "fail",
            f"{db_path} ({db_path.stat().st_size / 1024:.1f}KB), integrity={integrity}",
        )
        wal = home / "workbuddy.db-wal"
        shm = home / "workbuddy.db-shm"
        wal_size = wal.stat().st_size if wal.exists() else 0
        add(
            "WAL",
            "warn" if wal_size > 50 * 1024 * 1024 else "ok",
            f"wal={wal_size / 1024:.1f}KB, shm={'有' if shm.exists() else '无'}",
        )
        cols = {r[1] for r in wb.con.execute("PRAGMA table_info(sessions)")}
        required = {"id", "cwd", "is_playground", "title", "custom_title", "user_id", "deleted_at", "last_activity_at"}
        missing = required - cols
        add(
            "表结构",
            "fail" if missing else "ok",
            ("缺少：" + ", ".join(sorted(missing))) if missing else f"sessions {len(cols)} 列",
        )
        add("WorkBuddy 进程", "ok", "运行中（允许热写）" if app_running() else "未运行")
        sessions = wb.all_sessions()
        missing_jsonl = [s for s in sessions if not find_jsonl(home, s["id"])]
        add(
            "会话文件",
            "warn" if missing_jsonl else "ok",
            f"{len(sessions)} 条会话，{len(missing_jsonl)} 条缺 JSONL",
        )
        dir_mismatch = []
        for s in sessions:
            p = find_jsonl(home, s["id"])
            if not p:
                continue
            expected = home / "projects" / WorkBuddy.encode_cwd(s["cwd"])
            if path_key(p.parent) != path_key(expected):
                dir_mismatch.append(s["id"])
        add(
            "项目目录一致性",
            "warn" if dir_mismatch else "ok",
            f"{len(dir_mismatch)} 条 JSONL 目录与 cwd 不一致"
            + (f"；示例 {dir_mismatch[0][:8]}" if dir_mismatch else ""),
        )
        orphan_dirs = []
        projects_root = home / "projects"
        if projects_root.exists():
            for d in projects_root.iterdir():
                if d.is_dir() and not d.is_symlink() and not any(d.glob("*.jsonl")):
                    orphan_dirs.append(d)
        add(
            "空项目目录",
            "warn" if orphan_dirs else "ok",
            f"{len(orphan_dirs)} 个无会话目录"
            + (f"：{', '.join(d.name for d in orphan_dirs[:3])}" if orphan_dirs else ""),
        )
        snaps = wb.snapshots()
        snap_items = {}
        dup = 0
        for path, data in snaps:
            for item in data.get("items", []):
                sid = item.get("id")
                if sid in snap_items:
                    dup += 1
                snap_items[sid] = (path, item)
        expected_users = {s["user_id"] for s in sessions}
        snap_users = {p.parent.name for p, _ in snaps}
        missing_users = expected_users - snap_users
        missing_snap = [s["id"] for s in sessions if s["id"] not in snap_items]
        add(
            "侧栏快照",
            "warn" if (missing_snap or dup or missing_users) else "ok",
            f"{len(snaps)} 个文件 / {len(snap_items)} 条目；缺快照 {len(missing_snap)} 条；"
            f"重复 {dup}；缺账号 {len(missing_users)}",
        )
        title_mismatch = []
        for s in sessions:
            hit = snap_items.get(s["id"])
            if hit and (hit[1].get("title") or "") != (s.get("title") or ""):
                title_mismatch.append(s["id"])
        add(
            "标题一致性",
            "warn" if title_mismatch else "ok",
            f"{len(title_mismatch)} 条数据库与快照标题不一致",
        )
        if args.deep:
            deep_bad = []
            for s in sessions:
                p = find_jsonl(home, s["id"])
                if not p:
                    continue
                actual = last_custom_title(p)
                if actual and actual != (s.get("title") or ""):
                    deep_bad.append(s["id"])
            add(
                "JSONL 标题",
                "warn" if deep_bad else "ok",
                f"{len(deep_bad)} 条最后 custom-title 与数据库不一致",
            )
        backup_dirs = []
        for root in (home / "backup", Path.cwd() / "workbuddy-backups", Path.cwd()):
            if not root.exists():
                continue
            for p in root.iterdir():
                if p.is_dir() and ("backup" in p.name or "备份" in p.name):
                    backup_dirs.append(p.resolve())
        backup_dirs = sorted(set(backup_dirs), key=lambda p: p.stat().st_mtime, reverse=True)
        add(
            "备份",
            "ok" if backup_dirs else "warn",
            f"{len(backup_dirs)} 个备份目录"
            + (f"，最新 {backup_dirs[0].name}" if backup_dirs else "，建议先运行 backup"),
        )
    finally:
        wb.close()
    return _finish_doctor(checks, args.json)


def cmd_backup(args):
    home = Path(args.workbuddy_home).expanduser().resolve()
    db_path = home / "workbuddy.db"
    if not db_path.exists():
        raise UserError(f"找不到 WorkBuddy 数据库：{db_path}")
    root = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else (Path.cwd() / "workbuddy-backups" / "db")
    if args.list:
        dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name) if root.exists() else []
        rows = []
        for p in dirs:
            meta = load_json(p / "meta.json") or {}
            rows.append({
                "path": str(p), "name": p.name,
                "size": (p / "workbuddy.db").stat().st_size if (p / "workbuddy.db").exists() else 0,
                "created_at": meta.get("created_at"),
                "sessions": meta.get("sessions"),
            })
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(f"{'备份':<24} {'大小':>9}  会话")
            print("-" * 60)
            for r in rows:
                print(f"{r['name']:<24} {r['size'] / 1024:>7.1f}KB  {r['sessions'] if r['sessions'] is not None else '-'}")
            print(f"\n共 {len(rows)} 份，目录：{root}")
        return 0
    root.mkdir(parents=True, exist_ok=True)
    dest = unique_dir(root / now_stamp())
    dest.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest / "workbuddy.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for name in ("workbuddy.db-wal", "workbuddy.db-shm"):
        src_file = home / name
        if src_file.exists():
            shutil.copy2(src_file, dest / name)
    con = sqlite3.connect(str(db_path))
    try:
        sessions = con.execute("select count(*) from sessions where deleted_at is null").fetchone()[0]
        users = con.execute("select count(distinct user_id) from sessions where deleted_at is null").fetchone()[0]
    finally:
        con.close()
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "workbuddy_home": str(home),
        "db": str(db_path),
        "sessions": sessions,
        "users": users,
    }
    write_text(dest / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    removed = []
    keep = max(0, int(args.keep))
    dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)
    if keep and len(dirs) > keep:
        for old in dirs[:-keep]:
            shutil.rmtree(old)
            removed.append(old.name)
    print(f"[OK] 整库备份：{dest}（{sessions} 条会话，{users} 个账号）")
    if removed:
        print(f"     已清理旧备份 {len(removed)} 份：{', '.join(removed)}")
    if args.json:
        print(json.dumps({"backup": str(dest), "meta": meta, "removed": removed},
                         ensure_ascii=False, indent=2))
    return 0


SYSTEM_REMINDER_RE = re.compile(r"<system-reminder\b[\s\S]*?</system-reminder>", re.I)
TURN_ABORTED_RE = re.compile(r"<turn_aborted\b[\s\S]*?</turn_aborted>", re.I)


def find_jsonl(home: Path, sid: str):
    found = list((Path(home) / "projects").glob(f"*/{sid}.jsonl"))
    return found[0] if found else None


WRITE_TOOL_NAMES = {
    "Write", "Edit", "MultiEdit", "NotebookEdit",
    "write_file", "edit_file", "apply_patch", "create_file", "replace_in_file",
}


def tool_output_paths(jsonl: Path, root: Path):
    """从 WorkBuddy JSONL 的 function_call 里抽写文件类工具的路径。"""
    out = set()
    if not jsonl or not jsonl.exists():
        return out
    root = Path(root)
    for line in read_text(jsonl).splitlines():
        if not line.strip() or '"function_call"' not in line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("type") != "function_call":
            continue
        name = item.get("name") or item.get("tool") or ""
        if name not in WRITE_TOOL_NAMES:
            continue
        raw = item.get("arguments")
        if isinstance(raw, dict):
            args = raw
        elif isinstance(raw, str):
            try:
                args = json.loads(raw)
            except Exception:
                args = {}
        else:
            args = {}
        if not isinstance(args, dict):
            args = {}
        for key in ("file_path", "notebook_path", "path"):
            value = args.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            p = Path(value.strip().strip('"'))
            if not p.is_absolute():
                p = root / p
            if is_under(p, root):
                out.add(p)
    return out


def clean_orphan_project_dirs(home: Path, candidates, keep=()):
    """删除已无任何 *.jsonl 的源项目目录；keep 中的目标目录永不删。"""
    projects_root = (Path(home) / "projects").resolve()
    keep_keys = {path_key(p) for p in keep if p}
    removed = []
    seen = set()
    for cand in candidates:
        if not cand:
            continue
        try:
            d = Path(cand).resolve()
        except Exception:
            continue
        key = path_key(d)
        if key in seen or key in keep_keys:
            continue
        seen.add(key)
        if not d.is_dir() or d.is_symlink():
            continue
        if path_key(d.parent) != path_key(projects_root):
            continue
        if any(d.glob("*.jsonl")):
            continue
        try:
            shutil.rmtree(d)
            removed.append(str(d))
        except Exception:
            pass
    return removed


def extract_content_text(item: dict) -> str:
    content = item.get("content")
    parts = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype in ("input_text", "output_text", "text"):
                text = part.get("text") or ""
                if text:
                    parts.append(text)
            elif ptype in ("input_image", "image_blob_ref", "image_url"):
                parts.append("[图片]")
    return "\n".join(parts).strip()


def strip_injected(text: str) -> str:
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = TURN_ABORTED_RE.sub("", text)
    text = re.sub(r"</?user_query>", "", text, flags=re.I)
    text = re.sub(r"<image_local_path>[\s\S]*?</image_local_path>", "[图片]", text, flags=re.I)
    return text.strip()


def build_digest(dialog):
    users = [t for role, t in dialog if role == "user"]
    assistants = [t for role, t in dialog if role == "assistant"]
    lines = ["# 摘要片段（用户消息全文 + 助手首尾结论）"]
    lines.append(f"# 用户 {len(users)} 条，助手 {len(assistants)} 条")
    for i, text in enumerate(users):
        lines.append(f"[user #{i + 1}] {text[:4000]}")
    if assistants:
        lines.append(f"[assistant 首条] {assistants[0][:800]}")
        for text in assistants[-3:]:
            lines.append(f"[assistant 尾段] ...{text[-1500:]}")
    return "\n\n".join(lines) + "\n"


def parse_dialog(jsonl: Path):
    lines = []
    users = assistants = 0
    for raw in read_text(jsonl).splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except Exception:
            continue
        if item.get("type") != "message":
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        if item.get("providerData", {}).get("skipRun") is True:
            continue
        text = extract_content_text(item)
        if role == "user":
            text = strip_injected(text)
            if not text or text.startswith("<task-notification"):
                continue
        if not text:
            continue
        if role == "user":
            users += 1
        else:
            assistants += 1
        lines.append((role, text))
    return lines, users, assistants


def last_custom_title(jsonl: Path):
    title = None
    for raw in read_text(jsonl).splitlines():
        try:
            item = json.loads(raw)
        except Exception:
            continue
        if item.get("type") == "custom-title" and str(item.get("customTitle") or "").strip():
            title = item["customTitle"].strip()
    return title


def append_custom_title(jsonl: Path, sid: str, title: str, cwd: str | None):
    event = {
        "type": "custom-title",
        "id": str(uuid.uuid4()),
        "customTitle": title,
        "sessionId": sid,
        "timestamp": int(time.time() * 1000),
    }
    if cwd:
        event["project"] = cwd
    needs_newline = False
    if jsonl.exists() and jsonl.stat().st_size > 0:
        with open(jsonl, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) != b"\n"
    with open(jsonl, "a", encoding="utf-8", newline="\n") as f:
        if needs_newline:
            f.write("\n")
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return event


def normalize_title(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


FORBIDDEN_TITLE_CHARS = set('"\'“”‘’《》？?。\n\r\t/*\\<>|')


def title_problems(title: str, require_prefix: bool, min_len: int = 20, max_len: int = 30):
    problems = []
    if not title:
        return ["标题为空"]
    if len(title) < min_len:
        problems.append(f"长度 {len(title)} 少于 {min_len} 字")
    if len(title) > max_len:
        problems.append(f"长度 {len(title)} 超过 {max_len} 字")
    if any(ord(ch) < 32 for ch in title):
        problems.append("包含控制字符")
    bad = sorted({ch for ch in title if ch in FORBIDDEN_TITLE_CHARS})
    if bad:
        problems.append("包含禁用字符：" + " ".join(bad))
    if require_prefix and not re.match(r"^\[[^\[\]\r\n]{1,8}\]\s+\S", title):
        problems.append("缺少 [短分类] 前缀")
    return problems


def patch_snapshots_title(wb: WorkBuddy, sid: str, title: str):
    patched = []
    for path, data in wb.snapshots():
        hit = False
        for item in data.get("items", []):
            if item.get("id") == sid:
                item["title"] = title
                item["isUserDefinedTitle"] = 1
                hit = True
        if hit:
            data["savedAt"] = int(time.time() * 1000)
            write_text(path, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            patched.append(str(path))
    return patched


def set_session_title(wb: WorkBuddy, sid: str, title: str):
    last = None
    for attempt in range(3):
        try:
            with wb.con:
                cur = wb.con.execute(
                    "update sessions set title=?, custom_title=? where id=?",
                    (title, title, sid),
                )
                if cur.rowcount != 1:
                    raise UserError(f"更新 sessions 影响行数异常：{cur.rowcount}")
            last = None
            break
        except sqlite3.OperationalError as exc:
            last = exc
            if ("locked" in str(exc).lower() or "busy" in str(exc).lower()) and attempt < 2:
                time.sleep(1)
                continue
            raise
    if last:
        raise UserError(f"数据库写入失败（已重试 3 次）：{last}")
    try:
        wb.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass


def cmd_list(args):
    wb = WorkBuddy(Path(args.workbuddy_home), "*" if args.all_users else args.user_id)
    try:
        rows = filter_session_rows(wb.all_sessions(include_deleted=args.include_deleted), args)
        if args.limit:
            rows = rows[: args.limit]
        items = []
        for r in rows:
            p = find_jsonl(wb.home, r["id"])
            items.append({
                "session_id": r["id"],
                "user_id": r["user_id"],
                "is_playground": int(r["is_playground"] or 0),
                "deleted": bool(r.get("deleted_at")),
                "cwd": r["cwd"],
                "title": r.get("custom_title") or r.get("title") or "",
                "last_activity_at": r.get("last_activity_at"),
                "jsonl": str(p) if p else None,
                "bytes": p.stat().st_size if p else None,
            })
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return 0
        print(f"{'ID':<38} {'账号':<9} {'区':<3} {'大小':>9}  标题")
        print("-" * 110)
        for it in items:
            size = f"{it['bytes']/1024:.0f}KB" if it["bytes"] is not None else "缺失"
            area = "任务" if it["is_playground"] else "空间"
            print(
                f"{it['session_id']:<38} {it['user_id'][:8]:<9} {area:<3} {size:>9}  "
                f"{it['title'][:48]}"
            )
        print(f"\n共 {len(items)} 条")
        return 0
    finally:
        wb.close()


def cmd_extract(args):
    wb = WorkBuddy(Path(args.workbuddy_home), "*" if args.all_users else args.user_id)
    try:
        sessions = getattr(args, "_sessions", None)
        if sessions is None:
            if getattr(args, "all", False):
                sessions = wb.all_sessions()
            elif getattr(args, "session", None):
                sessions = select_sessions(wb, args.session)
            else:
                raise UserError("请用 --session 指定会话，或使用 --all。")
        out = Path(args.out).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        manifest = []
        for s in sessions:
            sid = s["id"]
            jsonl = find_jsonl(wb.home, sid)
            entry = {
                "session_id": sid,
                "user_id": s["user_id"],
                "is_playground": int(s["is_playground"] or 0),
                "cwd": s["cwd"],
                "title": s.get("custom_title") or s.get("title") or "",
                "last_activity_at": s.get("last_activity_at"),
                "jsonl": str(jsonl) if jsonl else None,
                "bytes": jsonl.stat().st_size if jsonl else None,
                "text_file": None, "digest_file": None, "chars": 0,
                "digest_chars": 0, "lines": 0,
                "messages_user": 0, "messages_assistant": 0,
                "error": None,
            }
            if not jsonl:
                entry["error"] = "找不到 JSONL"
                manifest.append(entry)
                print(f"[FAIL] {sid} 找不到 JSONL", file=sys.stderr)
                continue
            try:
                dialog, users, assistants = parse_dialog(jsonl)
                chunks = [
                    f"# Session {sid}",
                    f"# Title: {entry['title']}",
                    f"# CWD: {s['cwd']}",
                    f"# User: {s['user_id']}",
                    f"# Area: {'任务' if entry['is_playground'] else '空间'}",
                    f"# Size: {entry['bytes']} bytes",
                    "# Note: 仅 user/assistant 正文，已去除 system-reminder 与工具调用",
                    "",
                ]
                for role, text in dialog:
                    tag = "user" if role == "user" else "assistant"
                    chunks.append(f"[{tag}] {text}")
                    chunks.append("")
                body = "\n".join(chunks)
                text_file = out / f"{sid}.txt"
                digest_file = out / f"{sid}.digest.txt"
                digest = build_digest(dialog)
                write_text(text_file, body)
                write_text(digest_file, digest)
                entry.update({
                    "text_file": str(text_file), "digest_file": str(digest_file),
                    "chars": len(body), "digest_chars": len(digest),
                    "lines": body.count("\n") + 1,
                    "messages_user": users, "messages_assistant": assistants,
                })
                print(f"[OK] {sid[:8]} {users}/{assistants} 条消息 → {text_file.name} ({len(body)} 字)")
            except Exception as exc:
                entry["error"] = str(exc)
                print(f"[FAIL] {sid} 提取失败：{exc}", file=sys.stderr)
            manifest.append(entry)
        manifest_path = out / "manifest.json"
        write_text(manifest_path, json.dumps({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "workbuddy_home": str(wb.home),
            "items": manifest,
        }, ensure_ascii=False, indent=2))
        if args.shards > 0:
            usable = [e for e in manifest if not e.get("error") and e.get("text_file")]
            usable.sort(key=lambda x: -(x.get("chars") or 0))
            bins = [[] for _ in range(args.shards)]
            totals = [0] * args.shards
            for entry in usable:
                idx = min(range(args.shards), key=lambda k: totals[k])
                bins[idx].append(entry)
                totals[idx] += entry.get("chars") or 0
            shard_dir = out / "shards"
            shard_dir.mkdir(parents=True, exist_ok=True)
            for idx, bucket in enumerate(bins, 1):
                payload = {
                    "group": idx,
                    "count": len(bucket),
                    "total_chars": totals[idx - 1],
                    "items": [{
                        "session_id": e["session_id"], "user_id": e["user_id"],
                        "is_playground": e["is_playground"], "cwd": e["cwd"],
                        "title": e["title"], "chars": e["chars"],
                        "digest_chars": e["digest_chars"],
                        "text_file": e["text_file"], "digest_file": e["digest_file"],
                    } for e in bucket],
                }
                write_text(shard_dir / f"group{idx}.json",
                           json.dumps(payload, ensure_ascii=False, indent=2))
                print(f"[SHARD] group{idx}: {len(bucket)} 条 / {totals[idx - 1]} 字")
            print(f"分片清单：{shard_dir}")
        print(f"\n清单：{manifest_path}")
        if args.json:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        bad = sum(1 for e in manifest if e.get("error"))
        return 1 if bad else 0
    finally:
        wb.close()


def cmd_apply_titles(args):
    wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
    try:
        if getattr(args, "require_closed", False) and app_running():
            print("错误：WorkBuddy 正在运行，--require-closed 要求先退出应用。", file=sys.stderr)
            return 3
        proposals_path = Path(args.proposals)
        data = load_json(proposals_path)
        if data is None:
            raise UserError(f"无法解析提案文件：{proposals_path}")
        raw_items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(raw_items, list) or not raw_items:
            raise UserError("提案文件必须是非空数组，或含 items 数组的对象。")
        if (
            args.min_title_len < 10
            or args.max_title_len > 30
            or args.min_title_len > args.max_title_len
        ):
            raise UserError("标题长度范围限定 10–30，默认 20–30；请检查 --min-title-len / --max-title-len。")
        by_id = {}
        categories = {}
        for raw in raw_items:
            sid = str((raw or {}).get("session_id") or (raw or {}).get("sid") or "").strip()
            if not sid:
                continue
            raw_title = normalize_title((raw or {}).get("new_title"))
            category = normalize_title((raw or {}).get("category")).strip("[]")
            if category and raw_title and not raw_title.startswith("["):
                raw_title = f"[{category}] {raw_title}"
            by_id[sid] = raw_title
            if category:
                categories[sid] = category
        base = Path(args.backup_dir) if args.backup_dir else Path.cwd() / f"workbuddy-rename-backup-{now_stamp()}"
        base = unique_dir(base)
        results = []
        for sid, title in by_id.items():
            row = wb.session(sid)
            if not row or row.get("deleted_at"):
                results.append({"session_id": sid, "status": "failed", "error": "会话不存在或已删除"})
                continue
            jsonl = find_jsonl(wb.home, sid)
            if not jsonl:
                results.append({"session_id": sid, "status": "failed", "error": "找不到 JSONL"})
                continue
            problems = title_problems(
                title, args.require_prefix, args.min_title_len, args.max_title_len
            )
            if problems:
                results.append({
                    "session_id": sid, "status": "failed", "title": title,
                    "old_title": row.get("title"), "error": "；".join(problems),
                })
                continue
            results.append({
                "session_id": sid, "status": "planned", "title": title,
                "category": categories.get(sid),
                "old_title": row.get("title"), "user_id": row["user_id"],
                "cwd": row["cwd"], "is_playground": int(row["is_playground"] or 0),
                "jsonl": str(jsonl),
            })
        if getattr(args, "dry_run", False) or not getattr(args, "apply", False):
            planned = [r for r in results if r["status"] == "planned"]
            failed = [r for r in results if r["status"] == "failed"]
            if args.json:
                print(json.dumps({"dry_run": True, "results": results}, ensure_ascii=False, indent=2))
            else:
                for r in results:
                    if r["status"] == "planned":
                        print(f"[PLAN] {r['session_id'][:8]} {r['title']}")
                    else:
                        print(f"[FAIL] {r['session_id'][:8]} {r.get('error')}")
                print(f"\n干跑：计划 {len(planned)} 条，失败 {len(failed)} 条；确认后加 --apply 落盘。")
            return 0 if not failed else 1
        base.mkdir(parents=True, exist_ok=True)
        wb.backup_db(base / "db")
        for path, _data in wb.snapshots():
            dest = base / "snapshots" / path.parent.name / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        applied = []
        for rec in results:
            if rec["status"] != "planned":
                applied.append(rec)
                continue
            sid = rec["session_id"]
            jsonl = Path(rec["jsonl"])
            session_backup = base / "sessions" / sid / f"{sid}.jsonl"
            session_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jsonl, session_backup)
            try:
                event = append_custom_title(jsonl, sid, rec["title"], rec.get("cwd"))
                set_session_title(wb, sid, rec["title"])
                snaps = patch_snapshots_title(wb, sid, rec["title"])
                ok_jsonl = last_custom_title(jsonl) == rec["title"]
                row = wb.session(sid)
                ok_db = bool(row) and (row.get("title") or "") == rec["title"]
                ok_snap = all(
                    any(item.get("id") == sid and item.get("title") == rec["title"]
                        for item in (load_json(Path(p)) or {}).get("items", []))
                    for p in snaps
                ) if snaps else True
                rec.update({
                    "status": "ok" if (ok_jsonl and ok_db and ok_snap) else "verify_failed",
                    "event_id": event["id"], "snapshots": snaps,
                    "backup": str(session_backup),
                    "checks": {"jsonl": ok_jsonl, "db": ok_db, "snapshot": ok_snap},
                })
                print(f"[{'OK' if rec['status'] == 'ok' else 'WARN'}] {sid[:8]} {rec['title']}")
            except Exception as exc:
                rec.update({"status": "failed", "error": str(exc)})
                print(f"[FAIL] {sid[:8]} {exc}", file=sys.stderr)
            applied.append(rec)
        manifest_path = base / "rename-manifest.json"
        write_text(manifest_path, json.dumps({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "proposals": str(proposals_path.resolve()),
            "items": applied,
        }, ensure_ascii=False, indent=2))
        ok = sum(1 for r in applied if r["status"] == "ok")
        failed = sum(1 for r in applied if r["status"] in ("failed", "verify_failed"))
        print(f"\n完成：成功 {ok}，失败 {failed}，共 {len(applied)} 条")
        print(f"备份与清单：{base}")
        if args.json:
            print(json.dumps({"results": applied, "backup": str(base)}, ensure_ascii=False, indent=2))
        return 0 if failed == 0 else 1
    finally:
        wb.close()


def cmd_rename(args):
    if bool(args.export) == bool(args.import_file):
        raise UserError("请指定且只指定 --export 或 --import。")
    if args.export:
        if not args.out:
            raise UserError("--export 需要 --out 指定导出目录。")
        wb = WorkBuddy(Path(args.workbuddy_home), "*" if args.all_users else args.user_id)
        try:
            if args.ids:
                sessions = select_by_ids(wb, args.ids)
            else:
                sessions = filter_session_rows(
                    wb.all_sessions(include_deleted=args.include_deleted), args
                )
            if args.limit:
                sessions = sessions[: args.limit]
            if not sessions:
                raise UserError("没有匹配的会话。")
        finally:
            wb.close()
        args._sessions = sessions
        args.all = True
        args.session = []
        return cmd_extract(args)
    args.proposals = args.import_file
    args.dry_run = not args.apply
    return cmd_apply_titles(args)


def build_parser():
    p = argparse.ArgumentParser(
        prog="workbuddy_sessions.py",
        description="WorkBuddy 会话管理：体检、列表、两步式重命名、迁移、备份与回滚",
    )
    p.add_argument("--version", action="version", version=f"workbuddy-conversation-manager {VERSION}")
    p.add_argument("--workbuddy-home", default=str(DEFAULT_HOME), help="WorkBuddy 数据目录")
    p.add_argument("--user-id", default=None, help="只处理指定用户；默认取会话最多的用户")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("spaces", help="列出已有空间")
    sp.add_argument("--json", action="store_true")

    sf = sub.add_parser("find", help="按 ID/标题/关键词查会话")
    sf.add_argument("query", nargs="?")
    sf.add_argument("--limit", type=int, default=30)
    sf.add_argument("--json", action="store_true")
    sf.set_defaults(func=cmd_find)

    ss = sub.add_parser("show", help="显示单条会话详情")
    ss.add_argument("session_id")
    ss.add_argument("--json", action="store_true")
    ss.set_defaults(func=cmd_show)

    sd = sub.add_parser("doctor", help="体检：库/表/进程/文件/快照/标题/备份")
    sd.add_argument("--deep", action="store_true", help="逐条扫描 JSONL 最后一条 custom-title")
    sd.add_argument("--json", action="store_true")
    sd.set_defaults(func=cmd_doctor)

    sb = sub.add_parser("backup", help="整库快照备份")
    sb.add_argument("--list", action="store_true", help="列出已有备份")
    sb.add_argument("--keep", type=int, default=10, help="保留最近 N 份，默认 10")
    sb.add_argument("--backup-dir", default=None)
    sb.add_argument("--json", action="store_true")
    sb.set_defaults(func=cmd_backup)

    sl = sub.add_parser("list", help="列出会话（支持多账号）")
    sl.add_argument("--all-users", action="store_true")
    sl.add_argument("--keyword", default=None, help="标题关键词")
    sl.add_argument("--cwd", default=None, help="cwd 包含匹配")
    sl.add_argument("--since", default=None, help="YYYY-MM-DD 之后活跃")
    sl.add_argument("--area", choices=["all", "task", "space"], default="all")
    sl.add_argument("--include-deleted", action="store_true")
    sl.add_argument("--limit", type=int, default=0)
    sl.add_argument("--json", action="store_true")
    sl.set_defaults(func=cmd_list)

    se = sub.add_parser("extract", help="提取 user/assistant 正文（旧命令，等价 rename --export）")
    se.add_argument("--session", action="append", default=[])
    se.add_argument("--all", action="store_true")
    se.add_argument("--all-users", action="store_true")
    se.add_argument("--out", required=True)
    se.add_argument("--shards", type=int, default=0, help="按字数 LPT 均衡切成 N 组子智能体清单")
    se.add_argument("--json", action="store_true")
    se.set_defaults(func=cmd_extract)

    sr = sub.add_parser("rename", help="两步式重命名：--export 导出/分片，--import 写回（默认干跑）")
    sr.add_argument("--export", action="store_true", help="导出完整对话历史与 LPT 分片")
    sr.add_argument("--import", dest="import_file", metavar="FILE", help="导入 titles.json")
    sr.add_argument("--apply-flag", "--apply", dest="apply", action="store_true", help="真正写库")
    sr.add_argument("--out", help="--export 的输出目录")
    sr.add_argument("--shards", type=int, default=0, help="--export 时按字数切成 N 组")
    sr.add_argument("--ids", help="逗号分隔的会话 ID 前缀")
    sr.add_argument("--all-users", action="store_true")
    sr.add_argument("--keyword", default=None)
    sr.add_argument("--cwd", default=None)
    sr.add_argument("--since", default=None, help="YYYY-MM-DD 之后活跃")
    sr.add_argument("--area", choices=["all", "task", "space"], default="all")
    sr.add_argument("--include-deleted", action="store_true")
    sr.add_argument("--limit", type=int, default=0)
    sr.add_argument("--backup-dir", default=None)
    sr.add_argument("--min-title-len", type=int, default=20)
    sr.add_argument("--max-title-len", type=int, default=30)
    sr.add_argument("--no-require-prefix", dest="require_prefix", action="store_false")
    sr.add_argument("--require-closed", action="store_true")
    sr.add_argument("--json", action="store_true")
    sr.set_defaults(func=cmd_rename, require_prefix=True, apply=False, dry_run=False)

    st = sub.add_parser("apply-titles", help="写回标题（旧命令，默认干跑）")
    st.add_argument("--proposals", required=True)
    st.add_argument("--backup-dir", default=None)
    st.add_argument("--apply-flag", "--apply", dest="apply", action="store_true")
    st.add_argument("--dry-run", action="store_true")
    st.add_argument("--min-title-len", type=int, default=20)
    st.add_argument("--max-title-len", type=int, default=30)
    st.add_argument("--no-require-prefix", dest="require_prefix", action="store_false")
    st.add_argument("--require-closed", action="store_true", help="WorkBuddy 运行时拒绝写入并返回退出码 3")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_apply_titles, require_prefix=True, apply=False, dry_run=False)

    mv = sub.add_parser("move", help="迁移会话")
    mv.add_argument("--session", action="append", required=True, help="会话 ID、标题或关键词；可重复")
    mv.add_argument("--to", action="append", default=[], help="目标空间路径/名称；可重复")
    mv.add_argument("--mode", choices=["space", "task"], default="space")
    mv.add_argument("--backup-dir", default=None)
    mv.add_argument("--create-space", action="store_true",
                    help="目标空间不存在时按绝对路径创建，首个迁入会话作为种子")
    mv.add_argument("--allow-missing", action="store_true",
                    help="配合 --create-space，目录不存在时允许创建")
    mv.add_argument("--keep-orphans", action="store_true",
                    help="保留搬空的源项目目录（默认自动删除）")
    asset_group = mv.add_mutually_exclusive_group()
    asset_group.add_argument("--with-assets", dest="with_assets", action="store_true",
                             help="迁移记忆与产出（默认）")
    asset_group.add_argument("--metadata-only", dest="with_assets", action="store_false",
                             help="只改元数据并同步会话文件，不搬记忆与产出")
    mv.add_argument("--no-artifacts", action="store_true", help="迁移记忆但跳过产出")
    mv.add_argument("--no-running-check", dest="running_check", action="store_false", help="不检测 WorkBuddy 是否运行")
    mv.add_argument("--require-closed", action="store_true", help="WorkBuddy 运行时拒绝写入并返回退出码 3")
    mv.add_argument("--json", action="store_true")
    mv.set_defaults(func=cmd_move, running_check=True, with_assets=True)

    rb = sub.add_parser("rollback", help="按清单回滚")
    rb.add_argument("--manifest", action="append", default=[])
    rb.add_argument("--batch", default=None)
    rb.add_argument("--backup-dir", default=None)
    rb.add_argument("--require-closed", action="store_true")
    rb.add_argument("--json", action="store_true")
    rb.set_defaults(func=cmd_rollback, running_check=False, no_artifacts=False)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "spaces":
        wb = WorkBuddy(Path(args.workbuddy_home), args.user_id)
        try:
            print_spaces(wb, args.json)
            return 0
        finally:
            wb.close()
    try:
        return args.func(args)
    except UserError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
