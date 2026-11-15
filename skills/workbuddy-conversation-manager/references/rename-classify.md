# WorkBuddy 两步式批量重命名

## 适用场景

用户要求「读取本机所有 WorkBuddy 任务」「给每个任务重命名」「按主题分类」「加分类前缀」时使用。流程与 Qoder Conversation Manager 对齐：先导出完整历史，再由 agent 产出 `titles.json`，最后导入写回。

不适用于：迁移分组（用 `move`）、单条标题微调（可直接 `rename --import` 传一条）。

## 输入与约定

- 数据目录：默认 `~/.workbuddy`，可用 `--workbuddy-home` 覆盖。
- 账号：默认取任务最多的账号；`--all-users` 覆盖全部。
- 已删除任务：`deleted_at` 非空默认跳过。
- 读取粒度：只读 `message` 事件里的 user/assistant 正文，跳过 reasoning、工具调用、图片二进制。
- 大任务：正文超过 3MB 或提取后超过 3 万字的，先读 `.digest.txt`，再对正文首/中/尾抽样。
- 分类体系：由调用方外部传入，不写死在脚本里；建议先给子智能体一套短类，允许新类，最后收敛到 8–12 个。

## 步骤

### 1. 体检并导出

```bash
python <skill-dir>/scripts/workbuddy_sessions.py doctor
python <skill-dir>/scripts/workbuddy_sessions.py backup
python <skill-dir>/scripts/workbuddy_sessions.py rename --export --all-users --shards 8 --out ./wb-exp
```

可限定范围：

```bash
python <skill-dir>/scripts/workbuddy_sessions.py rename --export \
  --area space --keyword NAS --since 2026-11-01 --shards 4 --out ./wb-exp
```

生成：

- `wb-exp/<sid>.txt`：完整 user/assistant 正文；已去除 `system-reminder`、`turn_aborted`、`<user_query>` 包装，跳过 `task-notification`。
- `wb-exp/<sid>.digest.txt`：全部用户消息（单条最多 4000 字）+ 助手首条前 800 字 + 最后 3 条各 1500 字。
- `wb-exp/manifest.json`：每条的字数、原始字节、消息数、JSONL 路径、是否任务区。
- `wb-exp/shards/groupN.json`：按字数 LPT 均衡分组；单条超大任务独占一组。

检查 `manifest.json` 的 `errors` 必须为 0；批量操作前重新 `list` 一次，避免应用新产生的任务漏掉。

### 2. 派子智能体

子智能体只读、只提案，禁止修改 WorkBuddy 数据库/JSONL/快照。每个子智能体负责一组：

```text
你是 WorkBuddy 任务整理项目的读取子智能体，负责第 N 组（X 条任务）。只做读取与研究，并写一个 JSON 结果文件；绝对不要修改 WorkBuddy 数据库、JSONL、侧栏快照或任何源数据。

输入清单：<绝对路径>/wb-exp/shards/groupN.json

读取要求：
1. 先读清单 JSON。
2. chars <= 30000：用 Read 完整读取 text_file。
3. chars > 30000：先完整读 digest_file，再对 text_file 读开头 120 行、中部 120 行、结尾 120 行，必要时用 Grep 搜索 `[user]`。
4. 必须覆盖清单里的每一条。

标题规则：
- new_title 不写 `[分类]` 前缀，只写正文；category 单独给。
- 总长度按调用方指定；默认 20–30 个字符（最终前缀也计入）。
- 动作 + 具体对象，避免“处理”“排查”“配置”这类泛词。
- 中文为主，NAS/DDNS/SSH/nvm/AI 等技术词保留英文。
- 不加引号、书名号、句号、问号、emoji、路径分隔符；不写密码/令牌原文。
- 允许不同任务重名。

摘要：一句话 ≤30 字，说明解决了什么或产出了什么。

输出：
Write 到 <绝对路径>/wb-exp/results/groupN.json
[{"sid":"...","new_title":"...","category":"网络","summary":"...","confidence":"high"}]
```

Agent 类型：默认 `general-purpose` 可能被禁用，可改用 `【示例】研究助手`。各组可在一条消息里并发调用。

### 3. 合并与校验

主智能体读取 `results/group*.json`，校验：

- 提案数等于导出任务数，`sid` 不重不漏。
- `new_title` 非空；加上 `[category] ` 后长度落在 10–30，默认要求 20–30。
- 分类收敛在 8–12 个；异常条目降级为 `[其他] 原标题` 并记入报告。
- 允许重名，不去重。
- 合并成 `wb-exp/titles.json`。

### 4. 导入（默认干跑）

```bash
# 只打印 [PLAN]，不写库
python <skill-dir>/scripts/workbuddy_sessions.py rename --import ./wb-exp/titles.json

# 确认后落盘
python <skill-dir>/scripts/workbuddy_sessions.py rename --import ./wb-exp/titles.json --apply \
  --backup-dir ./workbuddy-rename-backup
```

标题长度：

- 默认 20–30 字，前缀和空格计入。
- 可用 `--min-title-len` / `--max-title-len` 调整，允许范围 10–30。
- 超长/过短/缺前缀/禁用字符的条目会逐条 `[FAIL]`，其他条继续。

脚本行为：

1. 校验每条提案；不合格的记 `failed`，其他条继续。
2. `--apply` 时批次备份：数据库（SQLite backup API）、目标 JSONL、两个账号的侧栏快照。
3. 每条任务：
   - 在 JSONL 末尾追加 `custom-title` 事件；
   - 更新 `sessions.title` 和 `sessions.custom_title`；
   - 更新对应用户快照的 `title`，置 `isUserDefinedTitle=1`；
   - 立即校验 JSONL 最后一条、数据库、快照，不一致记 `verify_failed`。
4. 写 `<backup>/rename-manifest.json`，含旧标题、新标题、JSONL 路径、备份路径、校验结果。

`custom-title` 事件形态：

```json
{"type":"custom-title","id":"<uuid>","customTitle":"[网络] 部署 NAS DDNS","sessionId":"<sid>","timestamp":1794719908478,"project":"%USERPROFILE%/WorkBuddy/2026-10-14-23-21-47"}
```

### 5. 校验与启动应用

- 独立校验数据库、JSONL、快照三层 70/70。
- 启动 WorkBuddy，等 10–15 秒，检查两个账号快照的 mtime 是否被应用重写、标题是否仍是新标题。
- 应用在托盘运行时可能没有主窗口句柄，无法优雅关闭；让用户手动重启或切换分组。

### 6. 报告与清理

生成一次性 Markdown 报告：处理范围、分类分布、逐条 ID/账号/区域/新标题/一句话摘要、写入与校验结果、备份路径、低置信度条目。

报告不含旧标题；旧标题只在 `rename-manifest.json` 里。清理 `wb-exp`（含 txt、digest、shards、results、临时脚本），保留报告和备份。

## 用户改长度

保留上一轮 `category` / `summary` / `notes`，只让子智能体在 `new_title` 上扩写或压缩，不重新分类：

```json
{"sid":"...","pass1_title":"...","category":"网络","summary":"...","notes":"..."}
```

合并后再次 `rename --import`，备份目录另起一组，不覆盖上一轮。

## 安全与边界

- 先 `doctor`，破坏性操作前 `backup`。
- 子智能体只提案，主智能体统一写入，避免并发写冲突。
- 默认覆盖已有自定义标题；要保留人工标题，在合并阶段过滤掉已有 `custom-title` 的任务。
- 需要应用退出才写库时加 `--require-closed`；不加则允许热写，写完重启验证。
- 已删除任务不处理；旧标题只进 manifest，不展示。

## 已知坑

1. **只写快照**：重启后被数据库覆盖，标题回退。三层一起写。
2. **只写数据库**：任务内历史仍显示旧标题；必须追加 `custom-title` 事件。
3. **标题长度算错**：`[系统] ` 前缀本身占 5 个字符；中文、英文、空格都按 1 个字符计。默认 20–30，允许 10–30。
4. **长标题侧栏截断**：20–30 字通常只能显示前段，完整标题在悬浮提示或详情中。
5. **默认干跑**：`rename --import` 不加 `--apply` 只打印 `[PLAN]`；这是保护行为。
6. **前缀重复**：`new_title` 不带前缀，交给 `category` 自动补；已带前缀时脚本不重复补。
7. **大任务直接整读**：单条 20 万字会撑爆子智能体上下文；先 digest 再抽样。
8. **把 `task-notification` 当用户消息**：提取器已跳过；自定义提取逻辑也要过滤。
9. **多账号只处理一个**：默认只取任务最多的账号；要覆盖全部必须加 `--all-users`。
10. **Bash 反引号**：`python -c "..."` 中的反引号会被 shell 当命令替换执行；长脚本写成 `.py` 文件再运行。
11. **应用启动后快照被重写**：正常行为；数据库和 JSONL 正确，重建后标题仍是新的。
12. **备份同名**：同一秒或同一路径重复执行会覆盖；脚本已用 `unique_dir` 追加时间戳。
