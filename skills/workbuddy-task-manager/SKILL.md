---
slug: workbuddy-task-manager
displayName: WorkBuddy任务管理
summary: 管理 WorkBuddy 本地任务与分组：按完整历史两步式重命名、任务/分组迁移（含记忆与产出）、备份回滚、10 项体检。默认干跑并按对象备份。
iconUrl: https://cdn.jsdelivr.net/gh/HuaHua-Technophile/workbuddy-task-manager@main/skills/workbuddy-task-manager/assets/icon-512.png
category: dev-programming
homepage: https://github.com/HuaHua-Technophile/workbuddy-task-manager
name: workbuddy-task-manager
description: 管理本机 WorkBuddy 的任务：体检、列表筛选、两步式重命名（导出完整历史/导入标题）、迁移任务/分组、整库备份与回滚。用于「重命名 WorkBuddy 任务、给任务改标题、整理任务名称、移动任务、换分组、把任务放到某个分组、列出 WorkBuddy 任务、WorkBuddy 体检、备份 WorkBuddy 数据」等请求；只操作本机 ~/.workbuddy 数据。
description_zh: 管理 WorkBuddy 本地任务：体检、筛选、两步式重命名、任务/分组迁移、备份回滚；默认干跑，按对象备份。
description_en: Manage local WorkBuddy tasks — doctor, list/filter, two-step rename from full transcripts, move between tasks/groups, backup & rollback; dry-run by default with per-object backups.
display_name: WorkBuddy Task Manager
display_name_zh: WorkBuddy任务管理
display_name_en: WorkBuddy Task Manager
examples_zh:
  - "把标题太短的 WorkBuddy 任务批量重命名"
  - "把 NAS 相关任务归到 NAS 分组，记忆和产出一起带过去"
  - "新建 D:/VMs 分组并迁入虚拟机任务"
examples_en:
  - "Batch rename WorkBuddy tasks whose titles are too short"
  - "Move NAS-related tasks into the NAS group with memory and outputs"
  - "Create a D:/VMs group and move VM tasks into it"
author: HuaHua
version: 1.5.0
tags: [WorkBuddy, 任务管理, 分组, 重命名, 迁移, SQLite]
license: MIT
---

# WorkBuddy 任务管理

Manage local WorkBuddy tasks: doctor, list/filter, two-step rename from full transcripts, move between tasks/groups, backup/rollback.

## 这个技能做什么

| 命令 | 用途 | 写库 |
|---|---|---|
| `doctor` | 10 项体检：库、WAL、表结构、进程、任务文件、目录一致性、空目录、快照、标题一致性、备份 | 否 |
| `list` | 列出任务，支持关键词/cwd/时间/区域/账号筛选 | 否 |
| `rename --export` | 导出完整任务历史，按字数 LPT 自动分片 | 否 |
| `rename --import` | 导入 `titles.json`；默认干跑，`--apply` 落盘 | 是 |
| `move` | 迁移任务到任务/分组；默认连记忆、产出和任务文件一起搬 | 是 |
| `backup` | 整库快照，默认保留最近 10 份 | 否 |
| `rollback` | 按迁移 manifest 单条/整批回滚 | 是 |
| `extract` / `apply-titles` | 旧命令，保留兼容；建议改用 `rename` | 部分 |

**不做什么**：不删除任务、不改任务正文、不重建搜索索引、不操作云端或其他设备的任务。

## 核心事实

- 数据库：`~/.workbuddy/workbuddy.db`（WAL 模式）；可用 `--workbuddy-home` 指向副本做演练。
- 数据表：`sessions` 存任务、`spaces` 存分组；`sessions.space_id` 指向 `spaces.id`，`is_playground` 仍区分 `1=任务` / `0=分组`。
- 任务正文：`~/.workbuddy/projects/<encoded-cwd>/<session-id>.jsonl`；子代理、工具结果在同名目录。
- 标题三层：JSONL 最后一条 `custom-title` 事件是有效标题；数据库 `title` / `custom_title` 和侧栏快照 `title` 是展示与缓存层，三层要一起写。
- 产出识别三路：`artifact-index`、`changes-index` 详情、JSONL `function_call` 里 `Write` / `Edit` 的 `file_path`；正文解析必须在搬走 JSONL 之前完成。
- 侧栏快照：`~/.workbuddy/<user-id>/sidebar-list-snapshot.json`；应用启动会按数据库重建。
- 本机可能有多个 `user_id`；`list` / `rename --export` / `rename --import` 用 `--all-users` 覆盖全部账号。
- 迁移默认同时搬任务 JSONL/子目录、记忆与产出。WorkBuddy 按 `cwd` 推导正文路径，只改数据库会导致任务读不到；只要元数据时加 `--metadata-only`。
- 搬完后源项目目录若已无任何 `*.jsonl`，默认自动删除；`--keep-orphans` 保留。删除清单写入 `batch.json` 的 `removed_dirs`。
- 分组优先读 `spaces` 表；旧数据没有 `space_id` 时回退到 `is_playground=0` 的 `cwd`。新建分组会写入 `spaces` 表，首个迁入任务作为种子。
- 备份目录自动去重，同名或同一秒追加时间戳；文本文件用临时文件 + `os.replace` 原子写入。

## 安装与验证

仓库按 `skills/workbuddy-task-manager/` 组织，根目录有 `install.py`；宿主需要扁平技能目录：

```bash
python install.py --targets all
# 或只装一个宿主
python install.py --to ~/.qoder/skills
```

安装后的扁平目录：

```
~/.qoder/skills/workbuddy-task-manager/
~/.workbuddy/skills/workbuddy-task-manager/
~/.agents/skills/workbuddy-task-manager/
```

验证：

```bash
python <skill-dir>/scripts/workbuddy_tasks.py doctor
python <skill-dir>/scripts/workbuddy_tasks.py doctor --deep
```

10 项全 `OK` 说明可用；`--deep` 额外核对 JSONL 最后一条 custom-title。`WorkBuddy 进程` 只是提示项，运行中也允许热写。

## 命令总览

所有命令支持 `--json`；`--workbuddy-home` 可指向数据库副本做演练。写操作默认允许 WorkBuddy 运行中热写；要硬性拦截加 `--require-closed`（退出码 3）。

### doctor

```bash
python <skill-dir>/scripts/workbuddy_tasks.py doctor
python <skill-dir>/scripts/workbuddy_tasks.py doctor --deep --json
```

退出码：`0` 全绿；`1` 有告警。

### list

```bash
python <skill-dir>/scripts/workbuddy_tasks.py list --all-users
python <skill-dir>/scripts/workbuddy_tasks.py list --keyword Qoder --area task --since 2026-11-01
python <skill-dir>/scripts/workbuddy_tasks.py list --cwd NAS --include-deleted --limit 20
```

筛选维度：`--all-users`、`--keyword`、`--cwd`、`--since`、`--area task|group|all`（`space` 为兼容别名）、`--include-deleted`、`--limit`。

### rename（两步式）

第一步，导出完整历史并自动分片：

```bash
python <skill-dir>/scripts/workbuddy_tasks.py rename --export --all-users --shards 8 --out ./wb-exp
# 可限定范围
python <skill-dir>/scripts/workbuddy_tasks.py rename --export --area group --keyword NAS --shards 4 --out ./wb-exp
```

产出：

- `wb-exp/<sid>.txt`：完整 user/assistant 正文。
- `wb-exp/<sid>.digest.txt`：全部用户消息 + 助手首尾结论。
- `wb-exp/manifest.json`：字数、消息数、JSONL 路径。
- `wb-exp/shards/groupN.json`：按字数 LPT 均衡分好的子智能体清单。

第二步，agent 读 `.txt` / `.digest.txt`，产出 `titles.json`：

```json
[
  {"sid": "6ed7f61f", "new_title": "整理 WorkBuddy 任务标题与分类", "category": "系统"},
  {"session_id": "57cb405c-0997-47b8-bf97-d3fac97d42dc", "new_title": "把任务管理技能开源并部署笔记本"}
]
```

`sid` 支持完整 UUID 或前 8 位；`new_title` 可不带前缀，`category` 会自动补成 `[分类] 标题`。

写回：

```bash
# 默认干跑：只打印 [PLAN]，不写库
python <skill-dir>/scripts/workbuddy_tasks.py rename --import titles.json

# 确认后落盘
python <skill-dir>/scripts/workbuddy_tasks.py rename --import titles.json --apply \
  --backup-dir ./workbuddy-rename-backup
```

标题规则：

- 格式 `[短分类] 标题`，单分类；短类 2–4 个汉字。
- 默认长度 **20–30 字**；可用 `--min-title-len` / `--max-title-len` 调整，允许范围 **10–30**。
- 前缀和空格计入长度；较长标题侧栏会截断，完整标题可悬浮或进详情查看。
- 中文为主，NAS/DDNS/SSH/nvm/AI 等技术词保留英文；不加引号、书名号、句号、问号、emoji、路径分隔符。
- 允许不同任务重名；默认覆盖已有自定义标题。
- 不写密码/令牌原文。

标题写入三层：JSONL 追加 `custom-title`、数据库 `title/custom_title`、对应用户快照 `title`。写后逐条校验，不一致记 `verify_failed`。

### move

```bash
# 默认：改归属 + 搬任务 JSONL/子目录 + 搬该任务的记忆段落与产出
python <skill-dir>/scripts/workbuddy_tasks.py move --task 6ed7f61f --to "X:/赞大拇指"

# 只要元数据，不搬记忆与产出
python <skill-dir>/scripts/workbuddy_tasks.py move --task 6ed7f61f --to "X:/赞大拇指" --metadata-only
```

分组模式会同步：

1. `sessions.cwd` 与 `is_playground`；
2. `projects/<encoded-cwd>/<sid>.jsonl` 与同名子目录（正文路径由 cwd 推导，必须同步）；
3. 该任务写入的源分组记忆段落、产出文件及其旧路径链接；
4. 侧栏快照 `space.name`。

产出识别三路合并：`artifact-index`、`changes-index` 详情、JSONL `function_call` 的 `Write` / `Edit` 路径；正文解析在搬走 JSONL 之前完成，避免搬完再解析导致空结果。

默认迁移记忆与产出；只要元数据时加 `--metadata-only`。任务模式只改 `is_playground=1`，不动 cwd 与文件。

搬空的源项目目录默认自动删除，`--keep-orphans` 保留，删除清单写入 `batch.json` 的 `removed_dirs`。

目标分组不存在时加 `--create-group`；目标目录必须已存在，确认要新建目录时再加 `--allow-missing`。

每条迁移独立事务，失败只回滚该条；manifest 记录源/目标、任务文件、记忆、产出和快照。

### backup / rollback

```bash
python <skill-dir>/scripts/workbuddy_tasks.py backup --list
python <skill-dir>/scripts/workbuddy_tasks.py backup --keep 10
python <skill-dir>/scripts/workbuddy_tasks.py backup --backup-dir D:/wb-backups
```

默认写到当前目录 `workbuddy-backups/db/<timestamp>/`，含 `workbuddy.db`、WAL/SHM（存在时）和 `meta.json`；默认保留最近 10 份。快照用于手工恢复或破坏性操作前锚点，不自动回滚。

迁移回滚：

```bash
python <skill-dir>/scripts/workbuddy_tasks.py rollback \
  --manifest "<backup>/<sid>/manifest.json"
python <skill-dir>/scripts/workbuddy_tasks.py rollback --batch "<backup>/batch.json"
```

### 旧命令

`extract` 等价于 `rename --export`；`apply-titles` 等价于 `rename --import`，两者都保留兼容，但新流程统一用 `rename`。

## 典型工作流

**批量重命名全部任务**

```bash
doctor
backup
rename --export --all-users --shards 8 --out ./wb-exp
# 子智能体读 ./wb-exp/shards/groupN.json，产出 titles.json
rename --import titles.json              # 干跑
rename --import titles.json --apply      # 落盘
```

**用户改长度**

保留上一轮 `category` / `summary` / `notes`，只做扩写或压缩，然后再次 `rename --import`；备份目录另起一组，不覆盖上一轮。

**按主题迁移**

```bash
list --all-users
move --task <sid> --to "D:/B/NAS"
# 默认连记忆/产出一起搬；只要元数据加 --metadata-only

# 目标分组不存在时，用首个迁入任务创建分组
python <skill-dir>/scripts/workbuddy_tasks.py move --task 6cd29df7 --to "D:/VMs" --create-group
# 目录不存在且确认创建时
python <skill-dir>/scripts/workbuddy_tasks.py move --task 6cd29df7 --to "D:/VMs" --create-group --allow-missing
```

## 安全规则

- 先 `doctor`，破坏性操作前 `backup`。
- 写操作默认允许热写；要强制应用退出加 `--require-closed`，退出码 `3`。
- 每条迁移/重命名独立事务；失败只影响该条，其余继续。
- 重命名按批次备份数据库、目标 JSONL 和两个账号的侧栏快照；旧标题只进 `rename-manifest.json`。
- 迁移每条约一份 manifest；记录数据库行、任务文件、记忆、产出和快照。
- 目标已有同名任务文件/产出文件时先备份，不覆盖。
- 已删除任务默认跳过；`--include-deleted` 只用于查看。
- 子智能体只提案，不直接写库；写入由主智能体统一执行。

## 非目标与限制

- 不删除任务、不改任务正文、不重建搜索索引。
- 只处理本机 `~/.workbuddy` 的本地任务；云端或其他设备任务不在范围内。
- 只支持 Windows（依赖 `tasklist`、本地路径与侧栏快照目录约定）。
- 默认迁移会搬记忆与产出；只要元数据时显式 `--metadata-only`。
- 标题长度、分类清单、是否覆盖自定义标题由调用方决定，技能不内置固定类目。

## 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| 重命名后标题没变 | 只改了数据库或快照 | 重跑 `rename --import --apply`；确认 JSONL 末尾有 `custom-title` |
| 重启后标题回退 | 只改了快照 | 数据库和 JSONL 必须一起写 |
| `rename --import` 只打印 `[PLAN]` | 默认干跑 | 加 `--apply` 落盘 |
| 标题被拒绝 | 长度不在 10–30、缺少前缀、含禁用字符 | 调整标题或分类后重跑 |
| `--require-closed` 返回 3 | WorkBuddy 正在运行 | 退出应用后重跑，或去掉该参数 |
| 迁移后任务打不开 | 只改了数据库 cwd，JSONL 没跟着移动 | 用本技能 `move`，它会同改 DB 与 JSONL；不要手工只改库 |
| 迁移后记忆/产出没跟过去 | 使用了 `--metadata-only` | 去掉该参数重跑，或手工迁移 |
| 产出只搬到了旧索引里的少数文件 | 只依赖 `artifact-index`/`changes-index` | 1.4.0 起会补 JSONL `Write`/`Edit` 路径；确认 JSONL 仍在源目录后再搬 |
| 仓库根没有 SKILL.md | 仓库是 `skills/<name>/` 结构，宿主要扁平目录 | 运行 `python install.py --targets all` |
| doctor 提示标题不一致 | 应用缓存未重建 | 重启应用；仍不一致则重跑导入 |
| 找不到目标分组 | 目标不在 `spaces` 表，且没有 legacy cwd | 加 `--create-group`，或先在 WorkBuddy 里打开该分组 |
| 想新建空分组 | WorkBuddy 分组由任务 cwd 派生 | 先迁入一条种子任务；不存在空分组 |
| `--create-group` 报目录不存在 | 默认要求目标目录已存在 | 确认路径后加 `--allow-missing` |
| 迁移后旧项目目录还在 | 加了 `--keep-orphans`，或目录里还有其他任务 | 去掉该参数重跑；有任务的目录不会删 |
| 备份目录带时间戳后缀 | 同名或同一秒已存在 | 正常保护行为，用最新目录 |
| 子智能体漏条 | 清单没对齐 | 用 `manifest.json` 的 sid 做差集核对 |
| `python -c` 反引号被执行 | Bash 命令替换 | 长脚本写成 `.py` 文件再运行 |

## 资源

- `references/workbuddy-storage.md`：表结构、路径编码、标题存储、验证 SQL、已知坑。
- `references/rename-classify.md`：导出/分片/子智能体/导入/报告的完整流程。
- `references/cases.md`：70 条任务重命名实测数据与踩坑记录。
- `references/install.md`：Qoder、WorkBuddy、Codex 的安装位置与复制命令。
- `README.md` / `CHANGELOG.md` / `PUBLISHING.md`：使用说明、版本记录、各平台发布状态。
