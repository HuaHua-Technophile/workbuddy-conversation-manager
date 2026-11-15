# Changelog

## 1.4.0 — 2026-11-15

- 产出识别新增 JSONL `function_call` 里 `Write` / `Edit` 的 `file_path`，与 `artifact-index`、`changes-index` 三路合并；本机实测在 28 条会话中发现 104 个 cwd 内非记忆路径。
- 正文解析固定在搬走 JSONL 之前，避免搬完再解析导致空结果。
- frontmatter 增加 `examples_zh` / `examples_en` / `author`；头像改为官方 WorkBuddy 图标 + 会话徽标组合，提供 256/512/1024 多尺寸。
- 仓库重构为 `skills/<name>/` + 根 `install.py`，便于 skills.sh 等目录索引；宿主仍安装为扁平技能目录。
- `PUBLISHING.md` 更正 skills.sh 状态为未收录/待复核，补充 WorkBuddy/Qoder 市场提交材料。

## 1.3.0 — 2026-11-15

- `move` 搬完后自动删除已无 `*.jsonl` 的源项目目录；`--keep-orphans` 可保留，删除清单写入 `batch.json` 的 `removed_dirs`。
- `doctor` 新增「项目目录一致性」与「空项目目录」检查，默认体检从 8 项扩到 10 项。
- `--create-space` 改为目录必须已存在，确认新建目录时需加 `--allow-missing`。
- 本机实测：清理 3 个空源目录，`projects/` 从 93 个目录收敛到 90 个；70 条会话目录一致性 0 异常。
- 近期迁移实测：9 条会话调整归属，3 个记忆文件与 85 条产出登记（33 条实际移动、26 条已存在、26 条源文件缺失）。

## 1.2.0 — 2026-11-15

- `move --create-space`：目标空间不存在时按绝对路径创建目录，首个迁入会话作为空间种子。
- 文档补充 WorkBuddy 空间由 `cwd` 派生的说明。

## 1.1.0 — 2026-11-15

- `move` 默认恢复为同时迁移记忆与产出，并同步会话文件；新增 `--metadata-only` 只改元数据。
- 迁移 manifest 的 `metadata_only` 默认改为 `false`；`--no-artifacts` 仍可在搬记忆时跳过产出。
- 文档与发布物同步更新到 1.1.0。

## 1.0.0 — 2026-11-15

首次公开发布，由内部技能 `workbuddy-move-conversation` 重命名并重构。

### 新增

- `doctor`：8 项体检（数据库、WAL、表结构、进程、会话文件、快照、标题一致性、备份）。
- `list`：关键词、cwd、时间、区域、账号筛选。
- `rename --export` / `rename --import`：两步式重命名，默认干跑，`--apply` 落盘。
- `rename --export --shards N`：按字数 LPT 自动分片，单条超大对话独占一组。
- `backup`：整库快照，默认保留最近 10 份，目录自动去重。
- `move --with-assets`：可选迁移记忆与产出；默认只改元数据并同步会话文件。

### 变更

- 技能名从 `workbuddy-move-conversation` 改为 `workbuddy-conversation-manager`。
- 脚本名从 `workbuddy_move.py` 改为 `workbuddy_sessions.py`。
- 标题默认长度改为 **20–30 字**，允许范围 **10–30**；前缀和空格计入。
- 重命名默认干跑，必须 `--apply` 才写库。
- 迁移默认只改元数据并同步必要的 JSONL/子目录，不再默认搬记忆与产出。
- 标题校验增加引号、书名号、句号、问号、路径分隔符等禁用字符。
- `category` 字段可自动补 `[分类] ` 前缀。
- 备份与文本写入改为原子写入 + 目录去重。
- 修正 Windows 路径编码：`X:/赞大拇指` → `x-赞大拇指`（避免双横线）。
- `--ids` 和 `find` 支持会话 ID 前缀。

### 兼容

- `extract` / `apply-titles` 保留为旧命令别名，建议改用 `rename`。
- 迁移 manifest 继续兼容旧格式；新增 `metadata_only` 字段。

## 0.9.0 — 内部迭代

- 批量读取、子智能体分片、三层标题写入、70 条对话重命名实测。
- 支持多账号、侧栏快照、`custom-title` 事件。
