# 真实案例与实测数据

以下数据来自本机 WorkBuddy（Windows，两个本地账号）的实际操作。

## 案例一：70 条对话批量重命名

### 背景

- 主账号 46 条（6 个空间），旧账号 24 条（全部在任务区）。
- 有效会话 70 条，另有 77 条 `deleted_at` 非空的已删除会话，按要求跳过。
- 原始标题全部是 AI 自动生成，`custom_title` 为空；存在「开始新的对话」「打包任务的请求」这类模糊标题。
- JSONL 合计约 114 MB；提取 user/assistant 正文后约 155 万字。

### 流程

1. 13 轮追问确定范围：两个账号、跳过已删除、只读正文、8 组子智能体、分类前缀、长度、备份与验收方式。
2. `list --all-users` 确认 70 条；`rename --export --all-users --shards 8` 生成 `.txt`、`.digest.txt`、`manifest.json` 和 `shards/groupN.json`。
3. 按 `chars` 降序做 LPT 分组：8 组各约 18 万字；最长一条 267,657 字独占一组。
4. 8 个「研究助手」子智能体并行读取；`chars <= 30000` 读全文，超过则读 digest + 正文首/中/尾各 120 行。
5. 子智能体只产出 `{session_id, new_title, category, summary, confidence, notes}`，主智能体合并校验。
6. `rename --import --apply` 三层写入：JSONL `custom-title`、数据库 `title/custom_title`、侧栏快照 `title`。
7. 启动 WorkBuddy，应用重建快照后 70 条标题仍保留；数据库/JSONL/快照三层校验 70/70。

### 标题长度改了两轮

- 第一轮要求 15–20 字，检查发现 24 条低于 15 字。
- 第二轮用户改为 20–30 字；保留 `category` / `summary` / `notes`，只做扩写，不重新分类。
- 最终 70 条长度 21–29 字，平均 26.2 字，无重名。
- 结论：用户改长度时只重跑第二轮提案和 `rename --import`，备份目录另起一组。
- 新版本默认标题长度为 20–30 字，允许 10–30；本次最终 21–29 字。

### 分类结果

`系统` 15、`开发` 13、`网络` 12、`AI` 6、`办公` 6、`学习` 6、`生活` 4、`娱乐` 4、`采购` 3、`其他` 1。

### 踩过的坑

1. **标题长度会变**：第一轮 15–20 与第二轮 20–30 之间，只改长度不改分类，避免重新读全文。
2. **应用在托盘运行**：`MainWindowHandle` 为 0，`CloseMainWindow()` 关不掉；写完标题后需用户手动重启或切换空间，侧栏才重建。
3. **快照会被应用重写**：这是正常行为；数据库和 JSONL 正确即可，重启后仍是新标题。
4. **Bash 反引号**：`python -c "..."` 里的反引号会被 shell 当命令替换执行；生成报告等长脚本要写成 `.py` 文件。
5. **多账号快照**：两个账号各有一份 `sidebar-list-snapshot.json`；脚本按 item.id 扫描全部快照，不能只改主账号。
6. **`task-notification` 不是用户消息**：提取时要跳过，否则会把后台任务结果当成用户诉求。
7. **新会话会插进来**：应用启动后可能创建一条新会话（如「用户问候」），批量操作前重新 `list` 确认数量，不要固定写死 70。
8. **备份同名**：同一秒或同一路径重复执行会覆盖；脚本用 `unique_dir` 追加时间戳保护。

### 复现命令

```bash
python <skill>/scripts/workbuddy_sessions.py doctor
python <skill>/scripts/workbuddy_sessions.py backup
python <skill>/scripts/workbuddy_sessions.py list --all-users
python <skill>/scripts/workbuddy_sessions.py rename --export --all-users --shards 8 --out ./wb-exp
# 子智能体读 ./wb-exp/shards/groupN.json，产出 titles.json
python <skill>/scripts/workbuddy_sessions.py rename --import ./wb-exp/titles.json --apply \
  --backup-dir ./workbuddy-rename-backup \
  --min-title-len 20 --max-title-len 30
```

## 案例二：单条/批量空间迁移

迁移的验证点与重命名不同，重点在四层一致性：

1. `sessions.cwd` 与 `is_playground`；
2. `projects/<encoded-cwd>/<sid>.jsonl` 与同名子目录；
3. 源/目标工作空间记忆文件的精确段落；
4. 产出文件目标位置与旧路径硬链接/副本。

实际排障顺序：先 `doctor` 看会话文件是否齐全，再 `spaces` 确认目标空间存在，最后 `move` 逐条写入并按 manifest 校验。应用运行中允许热写，写完重启验证侧栏分组。

## 实测参考

- 70 条、114 MB JSONL、155 万字正文，8 个子智能体并行，提取约 1 分钟。
- 单条最大 267,657 字，独占一组，读 digest + 首中尾抽样即可稳定命名。
- 三层写入 70 条耗时约数秒；应用重启后快照重建，标题不回退。
