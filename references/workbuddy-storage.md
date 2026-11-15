# WorkBuddy 本地存储与操作口径

## 目录结构

```
%USERPROFILE%\.workbuddy\
├── workbuddy.db                     SQLite 主库（WAL 模式）
├── workbuddy.db-wal / -shm
├── projects\
│   └── <encoded-cwd>\
│       ├── <session-id>.jsonl       对话正文
│       └── <session-id>\            子代理、工具结果等
│           ├── subagents\
│           └── tool-results\
├── <user-id>\
│   └── sidebar-list-snapshot.json   侧栏缓存（可被应用重建）
├── changes-index\<session-id>.json  会话改动的文件清单
├── changes-detail\<session-id>\     每条改动的 hunk 详情
├── artifact-index\<session-id>.json 对话中展示过的产出
├── assistant-display\<session-id>.json
├── file-history\<session-id>\
├── file-tree-manifests\<session-id>.json
└── backup\                          迁移备份
```

会话正文、子代理与工具结果按“空间”分目录；其余按 `session-id` 存放的索引不随空间移动。

## 数据库关键字段

`sessions` 表（迁移只改 `cwd` 与 `is_playground`）：

| 字段 | 含义 |
|---|---|
| `id` | 会话 UUID |
| `cwd` | 空间归属路径，权威来源 |
| `is_playground` | `1`=顶部“任务”；`0`=“空间” |
| `title` / `custom_title` | 标题；重命名时两者一起写 |
| `user_id` | 账号；只处理当前用户或 `--all-users` |
| `last_activity_at` / `updated_at` | 排序与显示 |
| `deleted_at` | 非空表示已删除，默认忽略 |

`workspaces` 表只是“最近打开过的工作目录”，不决定侧栏分组，不要拿它当权威。

### 空间判定

应用构建空间列表时使用的等价查询：

```sql
SELECT DISTINCT cwd
FROM sessions
WHERE is_playground = 0 AND deleted_at IS NULL;
```

因此：

- 目标空间必须至少有一条 `is_playground=0` 的会话。
- 只有 `is_playground=1` 会话的临时目录不算“空间”。
- 任务移到空间：`cwd` 改成目标，`is_playground` 改 0。
- 空间移到任务：`is_playground` 改 1，`cwd` 不变。

## 路径编码

- 数据库里的 `cwd` 既有 `D:/B/NAS`（正斜杠），也可能出现反斜杠；比较时统一：
  - 反斜杠转 `/`
  - 合并重复 `/`
  - 盘符转小写
  - 去掉末尾 `/`（保留 `D:/`）
- 写入时使用目标空间在数据库里的**原始字符串**，不要自己重写格式。
- 项目目录编码：盘符小写，`:/` 合并替换为一个 `-`，其余 `/` 替换为 `-`：
  - `%USERPROFILE%/WorkBuddy/2026-11-06-17-39-02`
    → `c-Users-<user>-WorkBuddy-2026-11-06-17-39-02`
  - `D:/B/赞大拇指` → `d-B-赞大拇指`
  - `X:/赞大拇指` → `x-赞大拇指`（不是 `x--赞大拇指`）
- 源会话目录不要靠编码猜：在 `projects/*/<session-id>.jsonl` 里按文件名找。
- 目标目录优先用目标空间里任一会话的现有项目目录；没有时退回 `encode_cwd`。

## 多账号

`sessions.user_id` 区分账号；本机可能有多个。`list` / `rename --export` 默认取会话最多的账号，`--all-users` 覆盖全部。

每个账号在 `<home>/<user-id>/sidebar-list-snapshot.json` 有独立快照；写标题时按 session 的 `user_id` 更新对应快照。脚本会扫描全部快照并按 `item.id` 命中，跨账号安全。

`session_settings.conversationTags` 已被 `automationId` / `quickAsk` 占用，不是通用分类字段，不要用来存主题分类。

## 标题与重命名

应用读取历史时，有效标题的优先级：

1. 最后一条 `custom-title` 事件的 `customTitle`
2. 最后一条 `ai-title` 事件的 `aiTitle`
3. `topic`
4. 首条真实用户消息

因此重命名必须向 JSONL 追加：

```json
{"type":"custom-title","id":"<uuid>","customTitle":"[网络] 部署 NAS DDNS","sessionId":"<sid>","timestamp":1794719908478,"project":"<cwd>"}
```

数据库层：写 `sessions.title` 和 `sessions.custom_title`。侧栏快照层：写 item 的 `title`，置 `isUserDefinedTitle=1`，`savedAt` 更新为当前毫秒。三层缺一不可：

- 只写快照：重启后按数据库重建，标题回退。
- 只写数据库：对话内历史仍显示旧 `ai-title`。
- 只写 JSONL：侧栏即时显示可能不变，直到重建。

快照格式：`version=3`，紧凑 JSON；`items` 必须满足 `isValidSnapshotItem`：`id` / `title` / `state` / `transport` / `kind` / `lastActivityAt` / `isPinned` 类型正确，`space` 为 `{type,name}`。

标题限制：默认 20–30 字，允许 10–30；前缀和空格都计入长度；前缀正则 `^\[[^\[\]]{1,8}\]\s+\S`；允许重复；不加引号、书名号、句号、问号、emoji、路径分隔符。20 字以上在侧栏通常会截断，完整标题需悬浮或进详情查看。提案可只给 `category` + 不带前缀的 `new_title`，脚本会自动补 `[category] `。

## 对话正文提取

`message` 事件的 `content` 是数组，元素类型：

- `input_text` / `output_text` / `text` → 取 `text`
- `input_image` / `image_blob_ref` / `image_url` → 标记 `[图片]`
- `content` 本身是字符串 → 直接使用

跳过事件类型：`session-meta`、`file-history-snapshot`、`reasoning`、`function_call`、`function_call_result`、`credit-usage`、`ai-title`、`custom-title`。

用户消息需要去掉 `system-reminder`、`turn_aborted`、`<user_query>` 包装；`task-notification` 是后台任务通知，不是用户诉求，跳过。

## 空间创建

WorkBuddy 没有独立的 workspace 表；空间由 `is_playground=0` 的会话 `cwd` 派生。要新建一个空间：

```bash
python <skill-dir>/scripts/workbuddy_sessions.py move --session <sid> --to "D:/VMs" --create-space
```

目录不存在时脚本会创建；首个迁入的会话成为空间种子。不存在“空空间”这种形态。

## 迁移：默认搬全套

`move` 默认做：

1. `sessions.cwd` 改为目标空间，`is_playground` 置 `0`（或任务模式置 `1`）；
2. 移动 `projects/<encoded-cwd>/<sid>.jsonl` 与同名子目录；
3. 搬该会话写入的源工作空间记忆段落，按日期追加到目标工作空间记忆；
4. 搬产出文件，并在旧路径保留硬链接/副本；
5. 侧栏快照该 item 的 `space.name` 改为目标路径。

为什么必须移动 JSONL：应用按 `cwd` 推导正文路径（`projects/<encoded-cwd>/<sid>.jsonl`）；只改数据库会导致对话读不到。

只要元数据时加 `--metadata-only`：仍会改 DB、移动 JSONL/子目录、更新快照，但不碰记忆与产出。`--no-artifacts` 可在搬记忆时跳过产出。

`MEMORY.md` 长期约定不改；需要时人工提炼。

## 备份与回滚

### 迁移按条备份

每条迁移在 `<backup>/<session-id>/manifest.json`：

```json
{
  "version": 1,
  "session_id": "…",
  "mode": "space",
  "metadata_only": false,
  "from_cwd": "…",
  "to_cwd": "…",
  "old_is_playground": 0,
  "new_is_playground": 0,
  "db_changed": true,
  "session": {
    "src_jsonl": "…", "dst_jsonl": "…",
    "src_dir": "…", "dst_dir": "…",
    "target_jsonl_backup": null, "target_dir_backup": null
  },
  "memory": [],
  "outputs": [],
  "snapshots": [{"path": "…", "backup": "…"}]
}
```

`batch.json` 的 `items` 是本批全部 manifest 路径。回滚按 manifest 逆序恢复：数据库行 → 会话文件/子目录 → 记忆 → 产出 → 侧栏快照。

### 重命名批次备份

`rename --import --apply` 在批次开始时备份：

```
<backup>/db/workbuddy.db (+wal/shm)
<backup>/snapshots/<user-id>/sidebar-list-snapshot.json
<backup>/sessions/<sid>/<sid>.jsonl
<backup>/rename-manifest.json
```

`rename-manifest.json` 含 `old_title` / `new_title` / `jsonl` / `backup` / `checks` / `event_id`；旧标题只在这里保留。重命名不提供自动回滚；恢复时把 JSONL 和快照备份复制回原位，并恢复 `sessions.title` / `custom_title`。

### 整库快照

`backup` 写到当前目录 `workbuddy-backups/db/<timestamp>/`，含数据库、WAL/SHM 和 `meta.json`；默认保留最近 10 份，`--keep N` 调整，`--list` 列出。快照用于手工恢复或破坏性操作前锚点。

备份目录用 `unique_dir` 去重：同名或同一秒已存在时追加时间戳，不覆盖上一轮备份。文本文件统一走临时文件 + `os.replace` 原子写入。

## 体检

`doctor` 只读，检查 8 项：

1. 数据库存在、可打开、`PRAGMA integrity_check=ok`；
2. WAL/SHM 状态，WAL 超过 50MB 告警；
3. `sessions` 表必需列齐全；
4. WorkBuddy 进程是否运行（运行中允许热写）；
5. 有效会话数与缺失 JSONL 数；
6. 侧栏快照文件数、条目数、缺快照/重复/缺账号；
7. 数据库 `title` 与快照 `title` 是否一致；
8. 备份目录数量与最新一份。

`doctor --deep` 额外逐条扫描 JSONL 最后一条 `custom-title` 与数据库 `title` 是否一致。退出码 `0` 全绿，`1` 有告警。

## 数据库写入与锁

- 连接：`sqlite3.connect(db, timeout=3)` + `PRAGMA busy_timeout=3000`。
- 更新：`BEGIN IMMEDIATE`（Python `with con`）→ `UPDATE` → commit。
- 锁冲突（`database is locked` / `busy`）：重试 3 次，每次 1 秒；仍失败中止该条。
- 成功后尝试 `PRAGMA wal_checkpoint(TRUNCATE)`；应用运行时可能失败，忽略即可，WAL 中已提交的数据仍可见。
- 备份数据库用 SQLite `Connection.backup()`，比直接复制正在写入的 `.db` 更一致；WAL/SHM 额外复制一份。
- `--require-closed`：`move` / `rename --import` / `rollback` 加此参数时，如果检测到 WorkBuddy 正在运行，直接返回退出码 `3`，不写任何数据。

## 验证清单

每条空间迁移至少验证：

```sql
SELECT cwd, is_playground FROM sessions WHERE id = '<session-id>';
-- cwd 必须等于目标空间原值；is_playground 必须为 0
```

文件：

- `<目标项目目录>/<session-id>.jsonl` 存在；
- 旧项目目录下该 `.jsonl` 不存在；
- 源有会话子目录时，目标子目录存在且源子目录不存在；
- 默认模式下，产出目标文件存在，旧路径硬链接/副本存在；
- 默认模式下，源记忆不再包含搬走的段落，目标记忆含 `迁移自 ...（会话 ...）` 标记；
- 侧栏快照该 item 的 `space.name` 等于目标路径。

重命名至少验证：

- 数据库 `title` 等于新标题；
- JSONL 最后一条 `custom-title` 等于新标题；
- 侧栏快照 `title` 等于新标题。

## 已知坑

1. **只改快照不改数据库**：重启后被数据库覆盖，侧栏回到旧空间。
2. **只改 `cwd` 不改 `is_playground`**：对话仍留在顶部“任务”区。
3. **只改数据库不移动 JSONL**：应用按新 cwd 找正文，对话读不到。
4. **把任务临时目录当空间**：它没有 `is_playground=0` 会话，不是空间。
5. **直接覆盖目标同名会话文件**：会丢目标原有对话；必须先备份再写。
6. **跨盘硬链接失败**：`os.link` 会报错；回退复制，报告里注明。
7. **记忆整文件移动**：会带走其他会话的内容；必须按 hunk 精确段落搬。默认迁移即会搬记忆；只要元数据时加 `--metadata-only`。
8. **应用运行中改快照**：应用可能重写；数据库正确即可，提示用户切换空间/重启。
9. **标题模糊匹配**：必须列候选让用户选，不能默认取最新。
10. **`workspaces.path` 误当权威**：它只记录最近打开目录，不决定分组。
11. **重命名只写快照**：应用启动会按数据库重建，标题回退；三层一起写。
12. **标题长度含前缀**：`[系统] ` 本身占 5 个字符；默认 20–30，允许 10–30。
13. **多账号只处理一个**：默认只取会话最多的账号；要覆盖全部必须加 `--all-users`。
14. **把 `task-notification` 当用户消息**：提取器已跳过；自定义解析也要过滤。
15. **`sessionSettings.conversationTags` 当分类字段**：它被 automationId / quickAsk 占用，写错可能影响后台自动化。
16. **Bash 反引号**：`python -c "..."` 里的反引号会被 shell 当命令替换执行；长脚本写成 `.py` 文件再运行。
17. **子智能体并发写库**：多个子智能体直接改 SQLite/JSONL 会冲突；只让它们产出提案，主智能体统一写入。
18. **路径编码双横线**：`X:/赞大拇指` 应编码为 `x-赞大拇指`，不是 `x--赞大拇指`；`:/` 要合并替换。
