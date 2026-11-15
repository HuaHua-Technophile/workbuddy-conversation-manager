# 跨 Harness 安装

技能是纯目录 + Python 标准库脚本，可以原样复制到 Qoder、WorkBuddy、Codex 或其他支持 `SKILL.md` 的 Harness。

## 目录要求

```
workbuddy-conversation-manager/
├── SKILL.md
├── scripts/workbuddy_sessions.py
└── references/
    ├── workbuddy-storage.md
    └── install.md
```

- 不需要 `pip install`。
- 需要 Python 3.9+；先确认 `python --version`。
- 需要对 `~/.workbuddy` 的读写权限、目标工作空间的写权限。
- 默认迁移只改元数据并同步会话文件；只有加 `--with-assets` 才需要产出文件的源/目标同盘或跨盘复制。

## Qoder

用户级（所有项目可用）：

```
%USERPROFILE%\.qoder\skills\workbuddy-conversation-manager\
```

项目级（只对当前项目）：

```
<项目>\.qoder\skills\workbuddy-conversation-manager\
```

复制（PowerShell，把 `<源>` 替换成技能目录）：

```powershell
$src = "<源>\workbuddy-conversation-manager"
$dst = "$env:USERPROFILE\.qoder\skills\workbuddy-conversation-manager"
Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue
Copy-Item -Recurse $src $dst
```

或 Git Bash：

```bash
cp -r "<源>/workbuddy-conversation-manager" "$HOME/.qoder/skills/"
```

加载：

- 在 Qoder 里执行 `/skills reload`，再用 `/skills list` 确认出现 `workbuddy-conversation-manager`。
- 也可以直接 `/workbuddy-conversation-manager` 调用。

## WorkBuddy

技能目录：

```
%USERPROFILE%\.workbuddy\skills\workbuddy-conversation-manager\
```

复制：

```powershell
$src = "<源>\workbuddy-conversation-manager"
$dst = "$env:USERPROFILE\.workbuddy\skills\workbuddy-conversation-manager"
Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue
Copy-Item -Recurse $src $dst
```

WorkBuddy 的技能列表读取 `~/.workbuddy/skills/*/SKILL.md`；复制后重启应用或重新打开技能页面即可看到。SKILL.md 里的 `display_name_zh` 会作为中文显示名。

## Codex

本机未检测到 `~/.codex`，所以未自动安装。Codex 常见技能目录（以实际版本为准）：

```
~/.codex/skills/<skill-name>/
```

检测与安装：

```bash
if [ -d "$HOME/.codex" ]; then
  mkdir -p "$HOME/.codex/skills"
  cp -r "<源>/workbuddy-conversation-manager" "$HOME/.codex/skills/"
fi
```

如果 Codex 使用共享的 `~/.agents/skills/`（部分版本/插件会这样映射），也可以复制到：

```
~/.agents/skills/workbuddy-conversation-manager/
```

复制后重启 Codex 会话，确认技能列表出现该项。

## 多端同步

建议只保留一份“源目录”（例如本机 Qoder 用户级目录），更新后重新复制到 WorkBuddy / Codex：

```bash
SRC="$HOME/.qoder/skills/workbuddy-conversation-manager"
cp -r "$SRC" "$HOME/.workbuddy/skills/"
# Codex 存在时
[ -d "$HOME/.codex" ] && cp -r "$SRC" "$HOME/.codex/skills/"
```

不要在多端分别手改，否则版本会漂移。

## 验证安装

任选一个 Harness 的终端运行：

```bash
python "<技能目录>/scripts/workbuddy_sessions.py" --help
python "<技能目录>/scripts/workbuddy_sessions.py" doctor
```

`doctor` 能读出数据库、会话文件和快照状态，说明数据目录与权限正常。

## 常见安装问题

| 现象 | 处理 |
|---|---|
| Qoder 技能列表没有出现 | 检查目录名与 `name` 字段一致；执行 `/skills reload` |
| WorkBuddy 看不到技能 | 确认 `~/.workbuddy/skills/<name>/SKILL.md` 存在；重启应用 |
| 运行报 `No such file: workbuddy.db` | 用 `--workbuddy-home` 指向真实数据目录，或确认 WorkBuddy 已安装并登录过 |
| 运行时提示数据库被锁 | 脚本会自动重试 3 次；仍失败则关闭 WorkBuddy 后重试 |
| 产出旧路径没有链接 | 跨盘硬链接失败，脚本回退复制；查看 manifest 的 `outputs` |
