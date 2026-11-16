#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workbuddy_tasks.py 的端到端测试（标准库 unittest，真跑 CLI，不 mock）。

每个用例用 `tempfile.TemporaryDirectory` 建独立夹具：一份最小但结构真实的
WorkBuddy 库（sessions / spaces）加一份 `~/.workbuddy` 副本（projects、侧栏快照、
changes-index、artifact-index），再用 `--workbuddy-home / --backup-dir` 指过去。
全程不碰本机真实库。

跑法：
    python -m unittest discover -s skills/workbuddy-task-manager/tests -v
"""
import contextlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
SCRIPTS = SKILL_DIR / "scripts"
SCRIPT = SCRIPTS / "workbuddy_tasks.py"
SKILL_MD = SKILL_DIR / "SKILL.md"
EXAMPLES = SKILL_DIR / "examples" / "titles.example.json"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import workbuddy_tasks as wt          # noqa: E402
import build_pkg                     # noqa: E402

# ---------------------------------------------------------------- 夹具常量

UID = "user-0001"
SID_1 = "11111111-1111-4111-8111-111111111111"
SID_2 = "22222222-2222-4222-8222-222222222222"
SID_DEL = "33333333-3333-4333-8333-333333333333"
SID_AMB_A = "deadbeef-0000-4000-8000-00000000000a"
SID_AMB_B = "deadbeef-0000-4000-8000-00000000000b"
SPACE_A = "aaaaaaaa-0000-4000-8000-00000000000a"
SPACE_B = "bbbbbbbb-0000-4000-8000-00000000000b"

SCHEMA = """
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  cwd TEXT NOT NULL,
  user_id TEXT NOT NULL,
  title TEXT,
  custom_title TEXT,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  last_activity_at INTEGER,
  deleted_at INTEGER,
  is_playground INTEGER NOT NULL,
  transport TEXT NOT NULL,
  conversation_origin TEXT,
  space_id TEXT
);
CREATE TABLE spaces (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  name TEXT NOT NULL,
  primary_folder_path TEXT,
  create_folder_path TEXT,
  pinned INTEGER NOT NULL,
  sort_order INTEGER,
  status TEXT NOT NULL,
  transport TEXT NOT NULL,
  conversation_origin TEXT,
  deleted_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  source_kind TEXT
);
"""

DEFAULT_SESSIONS = [
    {"sid": SID_1, "cwd": "A", "space": SPACE_A, "title": "[测试] 源分组里的第一条任务"},
    {"sid": SID_2, "cwd": "B", "space": SPACE_B, "title": "[测试] 目标分组里的任务", "deleted": -1},
    {"sid": SID_DEL, "cwd": "A", "space": SPACE_A, "title": "[测试] 已删除任务", "deleted": 1794000000000},
]


def encode_cwd(cwd):
    return wt.WorkBuddy.encode_cwd(str(cwd))


class Sandbox:
    """一个隔离的 WorkBuddy 数据副本。"""

    def __init__(self, root, sessions=None):
        self.root = Path(root)
        self.home = self.root / "home"
        self.bk = self.root / "bk"
        self.work = self.root / "work"
        self.cwd_a = self.work / "A"
        self.cwd_b = self.work / "B"
        self.newdir = self.work / "NewSpace"
        self.db = self.home / "workbuddy.db"
        for d in (self.home, self.bk, self.cwd_a, self.cwd_b):
            d.mkdir(parents=True, exist_ok=True)
        self.sessions = sessions if sessions is not None else DEFAULT_SESSIONS
        self._build()

    def _build(self):
        con = sqlite3.connect(self.db)
        try:
            con.executescript(SCHEMA)
            now = 1794000000000
            for space_id, cwd, name in (
                (SPACE_A, self.cwd_a, "A"),
                (SPACE_B, self.cwd_b, "B"),
            ):
                con.execute(
                    "insert into spaces values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (space_id, UID, "dev-1", name, None, str(cwd), 0, None,
                     "active", "local", None, -1, now, now, "seed"),
                )
            for item in self.sessions:
                cwd = self.cwd_a if item["cwd"] == "A" else self.cwd_b
                con.execute(
                    "insert into sessions values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item["sid"], str(cwd), UID, item["title"], None, "completed",
                     now, now, now, item.get("deleted"), 0, "local", None, item["space"]),
                )
            con.commit()
        finally:
            con.close()

        for item in self.sessions:
            if item.get("deleted", 0) and item.get("deleted") != -1:
                continue
            cwd = self.cwd_a if item["cwd"] == "A" else self.cwd_b
            proj = self.home / "projects" / encode_cwd(cwd)
            proj.mkdir(parents=True, exist_ok=True)
            (proj / f"{item['sid']}.jsonl").write_text(
                "\n".join([
                    json.dumps({"type": "message", "role": "user", "content": "帮我整理这个任务"}),
                    json.dumps({"type": "message", "role": "assistant", "content": "好的"}),
                    json.dumps({"type": "custom-title", "customTitle": item["title"],
                                "sessionId": item["sid"]}),
                ]) + "\n",
                encoding="utf-8",
            )

        snap = self.home / UID / "sidebar-list-snapshot.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({
            "version": 1,
            "items": [
                {"id": item["sid"], "title": item["title"],
                 "space": {"name": str(self.cwd_a if item["cwd"] == "A" else self.cwd_b)}}
                for item in self.sessions
                if not (item.get("deleted", 0) and item.get("deleted") != -1)
            ],
        }), encoding="utf-8")

        self.add_memory_and_output(SID_1, self.cwd_a)
        self.add_memory_and_output(SID_2, self.cwd_b, memory=False)

    def add_memory_and_output(self, sid, cwd, memory=True):
        if memory:
            mem = cwd / ".workbuddy" / "memory" / "2026-11-15.md"
            mem.parent.mkdir(parents=True, exist_ok=True)
            mem.write_text("# 2026-11-15\n\n## 记忆块\n- 事实一\n", encoding="utf-8")
            detail_dir = self.home / "changes-detail" / sid
            detail_dir.mkdir(parents=True, exist_ok=True)
            (self.home / "changes-index").mkdir(parents=True, exist_ok=True)
            (self.home / "changes-index" / f"{sid}.json").write_text(
                json.dumps({"changes": [{"detailRef": "d1.json"}]}), encoding="utf-8")
            (detail_dir / "d1.json").write_text(json.dumps({
                "change": {"files": [{
                    "filePath": str(mem), "action": "modify",
                    "hunks": [{"lines": ["+## 记忆块", "+- 事实一"]}],
                }]}
            }), encoding="utf-8")
        out_dir = cwd / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "report.txt"
        output.write_text("report", encoding="utf-8")
        (self.home / "artifact-index").mkdir(parents=True, exist_ok=True)
        (self.home / "artifact-index" / f"{sid}.json").write_text(
            json.dumps({"artifacts": [{"uri": output.as_uri()}]}), encoding="utf-8")

    def add_session(self, sid, cwd, space, title, deleted=None):
        con = sqlite3.connect(self.db)
        try:
            now = 1794000000000
            con.execute(
                "insert into sessions values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, str(cwd), UID, title, None, "completed", now, now, now, deleted, 0,
                 "local", None, space),
            )
            con.commit()
        finally:
            con.close()
        proj = self.home / "projects" / encode_cwd(cwd)
        proj.mkdir(parents=True, exist_ok=True)
        (proj / f"{sid}.jsonl").write_text(
            json.dumps({"type": "message", "role": "user", "content": "帮我整理"}) + "\n",
            encoding="utf-8",
        )

    def session(self, sid):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("select * from sessions where id=?", (sid,)).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def space_ids(self):
        con = sqlite3.connect(self.db)
        try:
            return {r[0] for r in con.execute("select id from spaces")}
        finally:
            con.close()

    def batches(self):
        return sorted(self.root.glob("bk*/batch.json"))


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="wbtaudit-")
        self.box = Sandbox(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def new_box(self, sessions=None):
        sub = Path(self._tmp.name) / ("b%d" % len(list(Path(self._tmp.name).iterdir())))
        sub.mkdir()
        return Sandbox(sub, sessions)

    def run_cli(self, *args, expect=None, box=None, cwd=None, env=None):
        box = box or self.box
        cmd = [sys.executable, str(SCRIPT), "--workbuddy-home", str(box.home)]
        cmd += [str(a) for a in args]
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(cwd or box.root), env=full_env,
        )
        if expect is not None:
            self.assertEqual(
                r.returncode, expect,
                msg="cmd=%s\nstdout=%s\nstderr=%s" % (cmd, r.stdout, r.stderr),
            )
        return r

    def run_json(self, *args, **kw):
        r = self.run_cli(*(tuple(args) + ("--json",)), **kw)
        return json.loads(r.stdout)

    def write_proposals(self, items):
        path = self.box.root / "titles.json"
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return path

    def export_dir(self):
        return self.box.root / "export"


# ---------------------------------------------------------------- 纯函数

class TestHelpers(unittest.TestCase):

    def test_is_deleted_understands_minus_one(self):
        self.assertFalse(wt.is_deleted({"deleted_at": None}))
        self.assertFalse(wt.is_deleted({"deleted_at": -1}))
        self.assertTrue(wt.is_deleted({"deleted_at": 1794000000000}))

    def test_backup_rel_keeps_hierarchy_and_rejects_escape(self):
        base = Path("C:/base")
        self.assertEqual(
            wt.backup_rel(Path("C:/base/out/x/log.txt"), base), "out/x/log.txt")
        self.assertIsNone(wt.backup_rel(Path("C:/other/log.txt"), base))
        self.assertIsNone(wt.backup_rel(Path("D:log.txt"), base))

    def test_title_problems_reports_characters(self):
        problems = wt.title_problems("太短", require_prefix=False, min_len=20, max_len=30)
        self.assertTrue(any("字符" in p for p in problems), problems)

    def test_example_titles_pass_default_rules(self):
        items = json.loads(EXAMPLES.read_text(encoding="utf-8"))
        for item in items:
            title = item["new_title"]
            if item.get("category") and not title.startswith("["):
                title = f"[{item['category']}] {title}"
            self.assertEqual(
                wt.title_problems(title, True, 20, 30), [],
                msg=f"示例标题不合法：{title!r}",
            )


# ---------------------------------------------------------------- JSON 契约

class TestJsonContract(CliTestCase):

    def test_backup_json_is_single_document_and_has_no_wal(self):
        data = self.run_json("backup", "--backup-dir", self.box.root / "manual", "--keep", "3")
        backup = Path(data["backup"])
        self.assertTrue((backup / "workbuddy.db").exists())
        self.assertFalse((backup / "workbuddy.db-wal").exists())
        self.assertFalse((backup / "workbuddy.db-shm").exists())
        self.assertEqual(data["meta"]["sessions"], 2, "deleted_at=-1 也是未删除，必须计入")

    def test_list_json_deleted_flag_for_minus_one(self):
        rows = self.run_json("list", "--all-users", "--include-deleted")
        by_id = {r["session_id"]: r for r in rows}
        self.assertFalse(by_id[SID_2]["deleted"], "deleted_at=-1 不应被当成已删除")
        self.assertTrue(by_id[SID_DEL]["deleted"])

    def test_export_json_shape_and_shards(self):
        data = self.run_json(
            "rename", "--export", "--all-users", "--shards", "2", "--out", self.export_dir())
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["shards"]), 2)
        self.assertTrue(data["out_dir"])

    def test_export_empty_result_is_valid_json(self):
        data = self.run_json(
            "rename", "--export", "--keyword", "绝对不存在的关键词", "--out", self.export_dir())
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["items"], [])
        self.assertIsNone(data["out_dir"])

    def test_move_and_rollback_json_single_document(self):
        data = self.run_json("move", "--task", SID_1, "--to", self.box.cwd_b,
                             "--backup-dir", self.box.root / "movebk")
        self.assertEqual(data["results"][0]["status"], "ok")
        batch = Path(data["batch_manifest"])
        rolled = self.run_json("rollback", "--batch", batch)
        self.assertEqual(rolled["failed"], 0)
        self.assertEqual(rolled["restored"], 1)

    def test_rename_apply_json_single_document(self):
        proposals = self.write_proposals([{
            "sid": SID_1[:8],
            "new_title": "把短 ID 的标题真正写回任务",
            "category": "测试",
        }])
        data = self.run_json("rename", "--import", proposals, "--apply",
                             "--backup-dir", self.box.root / "renamebk")
        self.assertTrue(data["applied"])
        self.assertEqual(data["results"][0]["status"], "ok")


# ---------------------------------------------------------------- 重命名

class TestRename(CliTestCase):

    def test_short_sid_is_resolved_not_rejected(self):
        proposals = self.write_proposals([{
            "sid": SID_1[:8],
            "new_title": "把短 ID 的标题真正写回任务",
            "category": "测试",
        }])
        dry = self.run_json("rename", "--import", proposals)
        self.assertEqual(len(dry["plan"]), 1, dry)
        self.assertEqual(dry["plan"][0]["session_id"], SID_1)

        self.run_json("rename", "--import", proposals, "--apply",
                      "--backup-dir", self.box.root / "renamebk")
        self.assertEqual(self.box.session(SID_1)["title"], "[测试] 把短 ID 的标题真正写回任务")
        jsonl = self.box.home / "projects" / encode_cwd(self.box.cwd_a) / f"{SID_1}.jsonl"
        self.assertEqual(wt.last_custom_title(jsonl), "[测试] 把短 ID 的标题真正写回任务")
        snap = json.loads((self.box.home / UID / "sidebar-list-snapshot.json").read_text(encoding="utf-8"))
        titles = {i["id"]: i["title"] for i in snap["items"]}
        self.assertEqual(titles[SID_1], "[测试] 把短 ID 的标题真正写回任务")

    def test_ambiguous_id_prefix_is_reported(self):
        self.box.add_session(SID_AMB_A, self.box.cwd_a, SPACE_A, "[测试] 前缀冲突任务甲")
        self.box.add_session(SID_AMB_B, self.box.cwd_a, SPACE_A, "[测试] 前缀冲突任务乙")
        proposals = self.write_proposals([{
            "sid": "deadbeef",
            "new_title": "把前缀冲突的任务标题写回",
            "category": "测试",
        }])
        data = self.run_json("rename", "--import", proposals, expect=1)
        self.assertEqual(data["results"][0]["status"], "failed")
        self.assertIn("不唯一", data["results"][0]["error"])

    def test_deleted_task_is_skipped(self):
        proposals = self.write_proposals([{
            "sid": SID_DEL[:8],
            "new_title": "把已删除任务的标题写回",
            "category": "测试",
        }])
        data = self.run_json("rename", "--import", proposals)
        self.assertEqual(data["results"][0]["status"], "skipped")

    def test_utf8_emoji_does_not_crash_gbk_console(self):
        self.box.add_session(
            "44444444-4444-4444-8444-444444444444", self.box.cwd_a, SPACE_A,
            "[测试] 带 emoji 的任务标题 😀",
        )
        r = self.run_cli("list", "--all-users",
                         env={"PYTHONIOENCODING": "gbk"}, expect=0)
        self.assertNotIn("UnicodeEncodeError", r.stderr)
        self.assertIn("😀", r.stdout)


# ---------------------------------------------------------------- 迁移

class TestMove(CliTestCase):

    def test_move_brings_files_memory_outputs_and_cleans_source(self):
        data = self.run_json("move", "--task", SID_1, "--to", self.box.cwd_b,
                             "--backup-dir", self.box.root / "movebk")
        rec = data["results"][0]
        self.assertEqual(rec["status"], "ok")
        self.assertIn("memory_src:2026-11-15.md", rec["checks"])

        row = self.box.session(SID_1)
        self.assertEqual(wt.norm_cwd(row["cwd"]), wt.norm_cwd(self.box.cwd_b))
        self.assertEqual(row["space_id"], SPACE_B)

        src_proj = self.box.home / "projects" / encode_cwd(self.box.cwd_a)
        dst_proj = self.box.home / "projects" / encode_cwd(self.box.cwd_b)
        self.assertFalse((src_proj / f"{SID_1}.jsonl").exists())
        self.assertTrue((dst_proj / f"{SID_1}.jsonl").exists())
        self.assertFalse((src_proj / f"{SID_1}.jsonl").parent.exists(), "空源目录应被清理")

        dst_mem = self.box.cwd_b / ".workbuddy" / "memory" / "2026-11-15.md"
        self.assertTrue(dst_mem.exists())
        self.assertIn(f"任务 {SID_1}", dst_mem.read_text(encoding="utf-8"))
        self.assertTrue((self.box.cwd_b / "out" / "report.txt").exists())

        snap = json.loads((self.box.home / UID / "sidebar-list-snapshot.json").read_text(encoding="utf-8"))
        item = next(i for i in snap["items"] if i["id"] == SID_1)
        self.assertEqual(wt.norm_cwd(item["space"]["name"]), wt.norm_cwd(self.box.cwd_b))

    def test_metadata_only_does_not_move_memory_or_outputs(self):
        data = self.run_json("move", "--task", SID_2, "--to", self.box.cwd_a,
                             "--metadata-only", "--backup-dir", self.box.root / "movebk")
        rec = data["results"][0]
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["memory"], 0)
        self.assertEqual(rec["outputs"], 0)
        self.assertTrue((self.box.cwd_b / "out" / "report.txt").exists(), "元数据模式不应搬产出")
        mem_a = self.box.cwd_a / ".workbuddy" / "memory" / "2026-11-15.md"
        self.assertFalse(
            mem_a.exists() and f"任务 {SID_2}" in mem_a.read_text(encoding="utf-8"),
            "元数据模式不应写入目标记忆",
        )

    def test_create_group_is_rolled_back_with_batch(self):
        data = self.run_json(
            "move", "--task", SID_2, "--to", self.box.newdir,
            "--create-group", "--allow-missing", "--backup-dir", self.box.root / "newbk")
        created = data["created_spaces"]
        self.assertEqual(len(created), 1)
        space_id = created[0]["id"]
        self.assertIn(space_id, self.box.space_ids())

        batch = Path(data["batch_manifest"])
        items = json.loads(batch.read_text(encoding="utf-8"))["items"]
        self.assertTrue(any("space-" + space_id in item for item in items))

        rolled = self.run_json("rollback", "--batch", batch)
        self.assertEqual(rolled["failed"], 0)
        self.assertNotIn(space_id, self.box.space_ids())
        self.assertEqual(wt.norm_cwd(self.box.session(SID_2)["cwd"]), wt.norm_cwd(self.box.cwd_b))

    def test_tampered_manifest_is_rejected_before_touching_files(self):
        data = self.run_json("move", "--task", SID_1, "--to", self.box.cwd_b,
                             "--backup-dir", self.box.root / "movebk")
        manifest = Path(data["results"][0]["manifest"])
        victim = self.box.home / "projects" / "victimdir" / "victim.txt"
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_text("keep me", encoding="utf-8")

        tampered = json.loads(manifest.read_text(encoding="utf-8"))
        tampered["session"]["src_jsonl"] = str(victim)
        bad = manifest.parent / "tampered.json"
        bad.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

        r = self.run_cli("rollback", "--manifest", bad, "--json", expect=2)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["exit"], 2)
        self.assertIn("src_jsonl", payload["error"])
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(wt.norm_cwd(self.box.session(SID_1)["cwd"]), wt.norm_cwd(self.box.cwd_b))


# ---------------------------------------------------------------- 回滚热写闸门

class TestRollbackHotGuard(unittest.TestCase):

    def test_running_app_blocks_rollback_without_force_hot(self):
        with tempfile.TemporaryDirectory(prefix="wbguard-") as tmp:
            box = Sandbox(tmp)
            out = io.StringIO()
            err = io.StringIO()
            with mock.patch.object(wt, "DEFAULT_HOME", box.home), \
                    mock.patch.object(wt, "app_running", return_value=True), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    wt.main(["--workbuddy-home", str(box.home), "rollback",
                             "--manifest", str(box.root / "missing.json"), "--json"])
            self.assertEqual(cm.exception.code, 3)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["exit"], 3)
            self.assertIn("--force-hot", payload["error"])


# ---------------------------------------------------------------- doctor

class TestDoctor(CliTestCase):

    def test_backup_missing_is_suggested_not_failed(self):
        data = self.run_json("doctor")
        checks = {c["check"]: c for c in data["checks"]}
        self.assertEqual(checks["备份"]["status"], "warn")
        self.assertIn("backup", checks["备份"]["detail"])

    def test_stale_backup_is_warned(self):
        bk = self.box.root / "workbuddy-backups"
        bk.mkdir(parents=True, exist_ok=True)
        old = 1700000000
        os.utime(bk, (old, old))
        data = self.run_json("doctor")
        checks = {c["check"]: c for c in data["checks"]}
        self.assertEqual(checks["备份"]["status"], "warn")
        self.assertIn("14 天", checks["备份"]["detail"])


# ---------------------------------------------------------------- 版本与 frontmatter

FM_FENCE = "---"
FM_KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")

try:
    import yaml
except ImportError:
    yaml = None


def frontmatter_lines():
    lines = SKILL_MD.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != FM_FENCE:
        raise AssertionError("SKILL.md 必须以 --- 开头")
    for i in range(1, len(lines)):
        if lines[i].strip() == FM_FENCE:
            return lines[1:i]
    raise AssertionError("SKILL.md frontmatter 缺少结束的 ---")


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return value


def frontmatter_map():
    fm = {}
    current = None
    for line in frontmatter_lines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            item = _unquote(re.sub(r"^-\s+", "", line.strip()))
            if current is None:
                raise AssertionError(f"没有归属键的序列项：{line!r}")
            if not isinstance(fm[current], list):
                fm[current] = []
            fm[current].append(item)
            continue
        m = FM_KEY.match(line)
        if not m:
            raise AssertionError(f"frontmatter 顶层行不是 key: value：{line!r}")
        current = m.group(1)
        fm[current] = _unquote(m.group(2).strip())
    return fm


def as_items(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_unquote(x.strip()) for x in inner.split(",")] if inner else []
    raise AssertionError(f"不是序列：{value!r}")


class TestVersionAndFrontmatter(unittest.TestCase):

    def test_version_single_source_of_truth(self):
        script_version = re.search(
            r'^VERSION = "([^"]+)"', SCRIPT.read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(script_version, frontmatter_map()["version"])
        self.assertEqual(script_version, build_pkg.VERSION)
        self.assertRegex(script_version, r"^\d+\.\d+\.\d+$")

    def test_frontmatter_plain_scalars_are_yaml_safe(self):
        seen = set()
        for line in frontmatter_lines():
            if not line.strip():
                continue
            if line.startswith((" ", "\t")):
                value = re.sub(r"^-\s+", "", line.strip())
            else:
                m = FM_KEY.match(line)
                self.assertIsNotNone(m, f"无法解析：{line!r}")
                self.assertNotIn(m.group(1), seen, f"键重复：{m.group(1)}")
                seen.add(m.group(1))
                value = m.group(2).strip()
            if not value or value[0] in ('"', "'"):
                if value:
                    self.assertEqual(value[0], value[-1], f"引号未闭合：{line!r}")
                continue
            self.assertNotIn(": ", value, f"未加引号的值含「冒号+空格」：{line!r}")
            self.assertNotIn("\t", value, f"值含制表符：{line!r}")
            self.assertNotIn(" #", value, f"值含「空格+#」：{line!r}")
            self.assertFalse(value.endswith(":"), f"值以冒号结尾：{line!r}")
            if value.startswith("["):
                self.assertTrue(value.endswith("]"), f"flow sequence 未闭合：{line!r}")
        self.assertIn("name", seen)
        self.assertIn("version", seen)

    def test_frontmatter_fence_is_single_pair(self):
        text = SKILL_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
        lines = text.split("\n")
        self.assertEqual(lines[0].strip(), FM_FENCE)
        fences = [i + 1 for i, line in enumerate(lines) if line.strip() == FM_FENCE]
        self.assertEqual(len(fences), 2, f"frontmatter 围栏应恰好一对：{fences}")

    @unittest.skipUnless(yaml, "未安装 PyYAML，跳过严格解析断言")
    def test_frontmatter_parses_with_real_yaml(self):
        data = yaml.safe_load("\n".join(frontmatter_lines()))
        self.assertIsInstance(data, dict)
        self.assertEqual(data["version"], wt.VERSION)

    def test_required_market_fields_and_example_limit(self):
        fm = frontmatter_map()
        required = [
            "name", "version", "display_name", "display_name_zh", "display_name_en",
            "description", "description_zh", "description_en", "slug", "displayName",
            "summary", "iconUrl", "category", "homepage", "author", "license",
            "examples_zh", "examples_en", "tags",
        ]
        self.assertEqual(sorted(fm), sorted(required))
        for key in required:
            if key in ("examples_zh", "examples_en", "tags"):
                continue
            self.assertIsInstance(fm[key], str)
            self.assertTrue(fm[key].strip(), f"{key} 为空")
        for key in ("examples_zh", "examples_en"):
            items = as_items(fm[key])
            self.assertGreaterEqual(len(items), 1)
            self.assertLessEqual(len(items), 3, f"{key} 最多 3 条（WorkBuddy 平台限制）")
        self.assertGreaterEqual(len(as_items(fm["tags"])), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
