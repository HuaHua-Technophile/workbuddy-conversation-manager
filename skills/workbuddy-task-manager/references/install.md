# 跨 Harness 安装

仓库按 `skills/workbuddy-task-manager/SKILL.md` 组织，便于 skills.sh 等目录站索引；宿主只认“技能目录根部有 SKILL.md”的扁平形态，所以用仓库根目录的 `install.py` 摊平安装。

## 一键安装

```bash
# 同时装到 WorkBuddy / Qoder / agents
python install.py --targets all

# 只装一个宿主
python install.py --to ~/.qoder/skills
```

安装脚本会复制 `SKILL.md`、`CHANGELOG.md`、`PUBLISHING.md`，以及 `scripts/`、`references/`、`examples/`；不会复制 `build_pkg.py`、`__pycache__` 和仓库构建产物。

## 宿主目录

| 宿主 | 用户级技能目录 |
|---|---|
| Qoder | `~/.qoder/skills/workbuddy-task-manager/` |
| WorkBuddy | `~/.workbuddy/skills/workbuddy-task-manager/` |
| 共享 agents 目录 | `~/.agents/skills/workbuddy-task-manager/` |
| Codex（可选） | `~/.codex/skills/workbuddy-task-manager/` |

Codex 目录不存在时无需创建；需要时用 `--to ~/.codex/skills` 安装。

## 手动复制（备选）

```bash
mkdir -p "$HOME/.qoder/skills"
cp -r skills/workbuddy-task-manager "$HOME/.qoder/skills/"
```

手动复制后目录内应直接看到 `SKILL.md`，而不是 `skills/` 子目录。

## 验证

```bash
python "$HOME/.qoder/skills/workbuddy-task-manager/scripts/workbuddy_tasks.py" doctor
```

`doctor` 10 项全 `OK` 说明数据库、任务文件、目录一致性、快照和备份都正常。`备份` 项超过 14 天会提示重新备份。

开发仓库内还可以跑端到端测试（26 项，每个用例独立临时库，不碰真实数据）：

```bash
python -m unittest discover -s skills/workbuddy-task-manager/tests -v
```

## 常见问题

| 现象 | 处理 |
|---|---|
| 仓库根没有 SKILL.md，技能加载不到 | 仓库是 `skills/<name>/` 布局，运行 `python install.py --targets all` 安装扁平副本 |
| Qoder/WorkBuddy 技能列表没有出现 | 确认宿主技能目录内直接有 `SKILL.md`；重启应用或重新打开技能页 |
| 运行报找不到 `workbuddy.db` | 用 `--workbuddy-home` 指向真实数据目录，或确认 WorkBuddy 已安装并登录过 |
| 数据库被锁 | 脚本会自动重试 3 次；仍失败则退出 WorkBuddy 后重试，或加 `--require-closed` |
| skills.sh 目录页 404 | `install.py` 只负责本地安装；skills.sh 收录取决于仓库索引状态，`skills list -g` 显示 tracked 不等于已收录 |
