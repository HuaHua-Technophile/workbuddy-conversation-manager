#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包成两个市场上架用的 zip。

- -root：zip 根目录直接是 SKILL.md（部分市场要求此形态）
- -dir：单层目录 workbuddy-conversation-manager/，内含 SKILL.md（另一些市场要求此形态）

用法：python skills/workbuddy-conversation-manager/scripts/build_pkg.py [--out dist]
"""
import argparse
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # skills/<name>/
REPO = os.path.dirname(os.path.dirname(ROOT))                        # 仓库根
NAME = "workbuddy-conversation-manager"
VERSION = "1.4.0"

FILES = ["SKILL.md", "README.md", "CHANGELOG.md", "LICENSE", "PUBLISHING.md"]
DIRS = ["scripts", "references", "examples"]
SKIP_DIRS = {"__pycache__", ".git", "dist"}


def collect():
    items = []
    for f in FILES:
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            p = os.path.join(REPO, f)
        if os.path.isfile(p):
            items.append((p, f))
    for d in DIRS:
        base = os.path.join(ROOT, d)
        for cur, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for fn in files:
                if fn.endswith(".pyc") or fn == "build_pkg.py":
                    continue
                p = os.path.join(cur, fn)
                items.append((p, os.path.relpath(p, ROOT).replace("\\", "/")))
    return items


def build(out_dir, prefix):
    items = collect()
    path = os.path.join(out_dir, f'{NAME}-{"root" if not prefix else "dir"}-{VERSION}.zip')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in items:
            z.write(p, f"{prefix}{rel}" if prefix else rel)
    print(f"{os.path.basename(path)}  {os.path.getsize(path) / 1024:.1f} KB  {len(items)} files")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    build(args.out, "")
    build(args.out, NAME + "/")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
