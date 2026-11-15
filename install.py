#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库里的技能安装/同步到宿主技能目录（扁平布局）。

仓库按 skills/<name>/SKILL.md 组织（便于 skills.sh 等目录索引），
宿主则要求 <技能目录>/SKILL.md，所以安装时把内容摊平复制过去。

用法：
    python install.py                  # 装到 ~/.workbuddy/skills
    python install.py --to ~/.qoder/skills
    python install.py --targets all    # WorkBuddy / Qoder / agents 都装
"""
import argparse
import os
import shutil
import sys

NAME = "workbuddy-conversation-manager"
REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "skills", NAME)
FILES = ["SKILL.md", "CHANGELOG.md", "PUBLISHING.md"]
DIRS = ["scripts", "references", "examples"]
SKIP = {"__pycache__", ".git", "dist"}

HOMES = {
    "workbuddy": "~/.workbuddy/skills",
    "qoder": "~/.qoder/skills",
    "agents": "~/.agents/skills",
}


def sync(dest_root):
    if not os.path.isdir(SRC):
        raise SystemExit(f"找不到技能目录: {SRC}")
    dest = os.path.join(os.path.expanduser(dest_root), NAME)
    os.makedirs(dest, exist_ok=True)
    n = 0
    for f in FILES:
        p = os.path.join(SRC, f)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dest, f))
            n += 1
    for d in DIRS:
        base = os.path.join(SRC, d)
        for cur, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP]
            rel = os.path.relpath(cur, SRC)
            os.makedirs(os.path.join(dest, rel), exist_ok=True)
            for fn in files:
                if fn.endswith(".pyc") or fn == "build_pkg.py":
                    continue
                shutil.copy2(os.path.join(cur, fn), os.path.join(dest, rel, fn))
                n += 1
    return dest, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", help="目标技能根目录，例如 ~/.qoder/skills")
    ap.add_argument("--targets", choices=["one", "all"], default="one",
                    help="all = 同时装到 WorkBuddy / Qoder / agents")
    args = ap.parse_args()

    targets = list(HOMES.values()) if args.targets == "all" else [args.to or HOMES["workbuddy"]]
    for target in targets:
        dest, n = sync(target)
        print(f"[OK] {n} 个文件 -> {dest}")


if __name__ == "__main__":
    sys.exit(main())
