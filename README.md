# WorkBuddy Conversation Manager

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

一个给 AI Agent 用的技能：管理本机 **WorkBuddy** 的会话——体检、筛选、按完整对话历史两步式重命名、迁移任务/空间、备份与回滚。

> A portable agent skill for managing local **WorkBuddy** sessions: doctor, list/filter, two-step rename from full transcripts, move between tasks/spaces, backup & rollback.

---

## 为什么需要它

WorkBuddy 侧栏标题通常只反映首条消息，长对话真正的落点在中后段；空间迁移还涉及 JSONL、侧栏快照和（可选的）记忆/产出。这个技能把「读完整历史 → 起准确标题 → 安全写回」和「改归属」变成可重复的流程，并默认先干跑、自动备份。

## 能做什么

| 命令 | 用途 | 写库 |
|---|---|---|
| `doctor` | 8 项体检：数据库、WAL、表结构、进程、会话文件、快照、标题一致性、备份 | 否 |
| `list` | 关键词/cwd/时间/区域/账号筛选 | 否 |
| `rename --export` | 导出完整历史，按字数 LPT 自动分片 | 否 |
| `rename --import` | 导入 `titles.json`；默认干跑，`--apply` 落盘 | 是 |
| `move` | 迁移任务/空间；默认只改元数据并同步会话文件 | 是 |
| `backup` | 整库快照，默认保留最近 10 份 | 否 |
| `rollback` | 按迁移 manifest 单条/整批回滚 | 是 |

**不做**：不删除会话、不改对话正文、不重建索引、不操作云端或其他设备的会话。

## 快速开始

```bash
# 1. 体检
python scripts/workbuddy_sessions.py doctor

# 2. 看会话
python scripts/workbuddy_sessions.py list --all-users --limit 20

# 3. 导出完整历史并分片
python scripts/workbuddy_sessions.py rename --export --all-users --shards 8 --out ./wb-exp

# 4. agent 读 ./wb-exp/*.txt 与 shards/groupN.json，产出 titles.json

# 5. 干跑
python scripts/workbuddy_sessions.py rename --import ./wb-exp/titles.json

# 6. 确认后落盘
python scripts/workbuddy_sessions.py rename --import ./wb-exp/titles.json --apply \
  --backup-dir ./workbuddy-rename-backup
```

`titles.json` 格式：

```json
[
  {"sid": "6ed7f61f", "new_title": "整理 WorkBuddy 会话标题与分类", "category": "系统"},
  {"session_id": "57cb405c-0997-47b8-bf97-d3fac97d42dc", "new_title": "把会话管理技能开源并部署笔记本"}
]
```

`sid` 支持完整 UUID 或前 8 位；`new_title` 可不带前缀，`category` 会自动补成 `[分类] 标题`。

标题长度默认 **20–30 字**，可用 `--min-title-len` / `--max-title-len` 调整到 **10–30**。前缀和空格计入长度。

## 迁移

```bash
# 默认：只改 DB 归属/任务标志，并同步必要的会话 JSONL/子目录
python scripts/workbuddy_sessions.py move --session 6ed7f61f --to "X:/赞大拇指"

# 需要连记忆和产出一起搬时
python scripts/workbuddy_sessions.py move --session 6ed7f61f --to "X:/赞大拇指" --with-assets
```

WorkBuddy 按 `cwd` 推导正文路径，所以只改数据库会导致对话读不到；默认模式会同步 JSONL 与同名子目录，但不搬记忆和产出。

## 安全设计

- **默认干跑**：`rename --import` 不加 `--apply` 只打印 `[PLAN]`。
- **按对象备份**：迁移每条一份 manifest；重命名按批次备份数据库、JSONL 和两个账号的侧栏快照。
- **每条独立事务**：某条失败只影响它自己，其余继续。
- **热写可选**：允许 WorkBuddy 运行中写入；要硬性拦截加 `--require-closed`（退出码 3）。
- **副本演练**：`--workbuddy-home` 可指向数据库副本，与真库互不影响。
- **只改元数据**：默认不碰记忆与产出；需要时显式 `--with-assets`。
- **不覆盖**：目标已有同名文件先备份；备份目录自动去重。

## 安装

把整个目录放进宿主的用户级技能目录：

```bash
cp -r workbuddy-conversation-manager "$HOME/.qoder/skills/"
cp -r workbuddy-conversation-manager "$HOME/.workbuddy/skills/"
# Codex 存在时
[ -d "$HOME/.codex" ] && cp -r workbuddy-conversation-manager "$HOME/.codex/skills/"
```

验证：

```bash
python "$HOME/.qoder/skills/workbuddy-conversation-manager/scripts/workbuddy_sessions.py" doctor
```

详见 [`references/install.md`](references/install.md)。

## 文档

| 文件 | 内容 |
|---|---|
| [`SKILL.md`](SKILL.md) | 技能主文档：命令、工作流、安全规则 |
| [`references/workbuddy-storage.md`](references/workbuddy-storage.md) | 表结构、路径编码、标题存储、验证 SQL、已知坑 |
| [`references/rename-classify.md`](references/rename-classify.md) | 两步式重命名、LPT 分片、子智能体模板 |
| [`references/cases.md`](references/cases.md) | 70 条对话重命名实测与踩坑 |
| [`references/install.md`](references/install.md) | 三端安装与验证 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本记录 |
| [`PUBLISHING.md`](PUBLISHING.md) | 各平台发布状态与提交材料 |

## 已知限制

- 仅支持 **Windows**。
- 只操作本机 `~/.workbuddy` 的本地会话。
- 不删除会话、不改对话正文、不重建搜索索引。
- 默认迁移不搬记忆与产出；需要时加 `--with-assets`。

## 环境要求

- Python 3.9+
- WorkBuddy（Windows），已登录并产生过会话
- 对 `~/.workbuddy` 的读写权限

## License

[MIT](LICENSE)
