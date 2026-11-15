# Changelog

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
