# Changelog

## 1.6.0 — 2026-11-16

对照 `qoder-task-manager` 1.7.0–1.7.2 的审计修复清单，对 WorkBuddy 版本做同等审计：数据安全、输出契约、功能正确性、健壮性与工程化共 20 余项，并补 26 项端到端测试。所有验证都在临时库夹具上完成，真实库零写入。

### 数据安全（会真丢/写坏数据的几处）

- **`deleted_at=-1` 被误判成已删除**：本机真实库里 109 条未删除任务中有 26 条用 `-1` 表示未删。旧代码在 `list --json` 把 `deleted` 报成 `true`，`rename --import` 直接把这类任务当已删除拒绝。新增 `is_deleted()`（正数时间戳才算删除），列表、重命名、备份计数统一使用。
- **`rename --import` 的短 ID 从未生效**：文档和示例都写「`sid` 支持前 8 位」，实现却只做 `sessions.id` 精确匹配，短 ID 一律报「任务不存在」。改为「完整 ID 直查 → 唯一前缀解析 → 撞车明确报错」，并在测试里覆盖短 ID 成功写回与 `deadbeef` 双命中拒绝。
- **回滚默认在应用运行时裸奔**：`rollback` 会直接改数据库行并搬回文件，旧版本只在显式 `--require-closed` 时检查进程。现在默认检测到 WorkBuddy 运行中就退出码 `3`，`--force-hot` 才放行并打风险提示；`--workbuddy-home` 指向副本时不做拦截。
- **回滚清单可被手改成任意文件操作**：manifest 是外部 JSON，旧代码完全信任其中的 `src_jsonl/dst_jsonl`、记忆、产出和快照路径。新增路径白名单校验：任务文件必须是 `projects/` 下的 `<sid>.jsonl`，记忆/产出必须落在源或目标 cwd 内，备份文件必须落在该条备份目录内；越界整批中止（退出码 2），不先回滚一半。
- **`--create-group` 新建的分组行没有回滚记录**：旧版本回滚整批后 `spaces` 表残留孤儿行。现在每次新建分组写一条 `space-create` 清单进同一批次，`rollback --batch` 在任务搬回后确认无会话引用再删除该行；单条 `rollback --manifest` 也支持。
- **侧栏快照备份同名覆盖**：所有账号的快照都叫 `sidebar-list-snapshot.json`，旧代码按 basename 落到同一个 `snapshot/`，多账号时会互相覆盖。改为 `snapshot/<user-id>/sidebar-list-snapshot.json`。
- **整库快照不再复制 `-wal/-shm`**：SQLite backup API 已经把 WAL 合入目标库，旧代码额外复制一份「旧主库 + 新 WAL」，手工恢复时可能拼出不一致的库。现在只产出一致性单文件 `workbuddy.db` + `meta.json`；`backup` 的任务数统计也改为把 `-1` 计为未删除。
- **迁移备份改放当前目录**：默认从 `~/.workbuddy/backup/` 改为 `./workbuddy-backups/move-<时间戳>/`，与 `backup` 命令一致，不再往应用数据目录写临时产物。
- **重命名单条失败会留下半截状态**：JSONL 已追加标题、数据库写入失败时旧版本只报错不还原。现在尽力恢复 JSONL、数据库 `title/custom_title` 和该账号快照，并在结果里回报 `rolled_back`。
- **产出备份路径兜底**：`backup_rel()` 拒绝绝对路径、盘相对路径（`D:x.txt`）和含 `..` 的相对路径；拿不到合法相对路径时改用 `basename-<sha1 前 8 位>`，不会把备份写出备份根。

### 输出契约（`--json` 现在能直接喂给 `json.load`）

- **新增 JSON_MODE**：`--json` 时人类可读输出全部静音，整条命令只在最后打一份文档；`[OK]/[PLAN]/[FAIL]` 等进度不再混入 stdout。
- **告警分流**：`warn()` 在 JSON 模式收集到 `warnings` 字段；`list/find/spaces/backup --list` 保持数组形状，告警改走 stderr。
- **错误也是合法 JSON**：致命错误在 stdout 输出 `{"error": ..., "exit": N}`，stderr 同时给错误原文。
- **空结果合法**：`rename --export` 无匹配时输出 `count=0`、`out_dir=null`，不再当错误；`move`/`rollback`/`extract`/`backup`/`rename --import` 各自只打一份固定形状。
- **`rollback --json` 之前完全没有 JSON 输出**，现在补齐 `{restored, failed, items, applied, warnings}`。
- **`list` 截断提示**：`--limit` 把结果截断时，人读模式明确提示「另有 N 条被截断」，不再让人误以为总数只有这么多。

### 功能正确性

- **`find` 空库不带查询**：原来抛「找不到任务：None」，现在 `--json` 返回 `[]`、人读提示「没有任务」，退出码 0。
- **项目目录多副本**：`find_jsonl()` 改为排序后取第一个，多副本时打 `[NOTE]`；`source_project_dir()` / `project_dir_for_space()` 同样排序，不再依赖 glob 的偶然顺序。
- **`doctor` 备份项做真检查**：最近备份超过 14 天标 `warn` 并提示重新备份；从未备份仍是提示而非失败。
- **标题长度报错单位改为「字符」**：与「20–30 字符（前缀和空格计入）」口径一致，避免把「字」理解成汉字数。

### 工程化

- **新增 26 项端到端测试** `tests/test_workbuddy_tasks.py`：标准库 `unittest`，绝大多数用 subprocess 真跑 CLI；每个用例独立临时库，覆盖 JSON 单文档、短 ID/歧义 ID、`-1` 删除语义、迁移文件/记忆/产出/空目录清理、建组回滚、清单篡改拦截、热回滚闸门、备份无 WAL、GBK 控制台 emoji、frontmatter YAML 安全与版本一致性。
- **版本号单一来源**：`build_pkg.py` 改为从 `workbuddy_tasks.py` 读取 `VERSION`，测试同时校验脚本、SKILL.md frontmatter 与打包脚本三处一致。
- **frontmatter lint**：新增最小充分判据（未加引号的值不得含半角冒号+空格、制表符、` #`，flow sequence 必须闭合等），防止 WorkBuddy 开放平台因 YAML 解析失败拒包；同时钉住 19 个市场字段与「示例最多 3 条」的平台上限。
- **LF 统一**：新增 `.gitattributes`，文本文件统一 LF，消除跨平台整文件 diff 噪音。
- 版本号同步到 1.6.0：脚本 `VERSION`、`SKILL.md` 的 `version:`、`build_pkg.py` 的 `VERSION_FALLBACK`。

## 1.5.0 — 2026-11-15

仓库、技能目录、脚本名、安装目录、包名、Release 资产、SkillHub slug 与文档链接统一为 `workbuddy-task-manager`。

- 脚本改名为 `workbuddy_tasks.py`；CLI 新增 `--task` / `--create-group` / `groups` / `--area group` 别名，旧参数继续兼容。
- 用户可见英文统一为 task / group；README、PUBLISHING、references 与 CI 路径同步更新。
- 对齐 WorkBuddy 新版数据模型：分组优先读取 `spaces` 表，`move` 同步写 `sessions.space_id`；旧版没有 `space_id` 时回退到 `is_playground=0` + `cwd`。
- WorkBuddy 内部数据库/接口的 `sessions`、`spaces`、`session_id`、`space_id`、`is_playground`、`conversation_origin` 等原始命名保留，不做破坏性修改。
- README banner 改用 Pillow 脚本 `assets/draw_banner.py` 生成（1280×380，深绿渐变 + 网格 + 光晕/圆环 + 白色图标容器），更新到 v1.5.0；GitHub Release、SkillHub 与 WorkBuddy `-dir` 包使用 1.5.0。
- SkillHub 新 slug 已上架（`skillId=322122`）；旧 slug 已下架并删除。

## 1.4.2 — 2026-11-15

全项目术语统一为「任务」和「分组」：覆盖 README、SKILL.md、CHANGELOG、PUBLISHING、references、examples 与 CLI 帮助/输出。

- 命令、参数与数据库字段保持不变：`sessions`、`session_id`、`--task`、`groups`、`--create-group`、`space.name`。
- 展示名统一为 `WorkBuddy任务管理` / `WorkBuddy Task Manager`；`slug` 与 `name` 保持不变。
- 版本对齐到 1.4.2：GitHub Release、SkillHub 与 WorkBuddy `-dir` 包使用同一版本号。
- SkillHub 1.4.2 已提交（`skillId=322039`，审核中）；过审后展示名与概述切换为“任务 / 分组”。

## 1.4.1 — 2026-11-15

- 图标重做为 Qoder 同构布局：左下角 WorkBuddy 图标，右上紫色文档位与右下铅笔徽标保持原位；提供 256/512/1024 与 JPG 版本。
- `SKILL.md` frontmatter 补齐 SkillHub 驼峰字段：`slug` / `displayName` / `summary` / `iconUrl` / `category`（`dev-programming`）与 `homepage`，与 WorkBuddy 下划线字段并存。
- `iconUrl` 改指向仓库自身（jsdelivr），图标随后续提交更新，不再依赖平台托管地址。
- 新增 `.github/workflows/release.yml`：推送 `v*` tag 时校验三处版本号、构建两个 zip、发布 GitHub Release；同一 workflow 的 `skillhub` job 在配置 `SKILLHUB_KEY` 后自动发布，并在发布前剔除 `assets/`。
- `PUBLISHING.md` 补充 SkillHub CLI 发布、图标异步生效、`category` 字段、WorkBuddy 手动更新和 CI 两个坑。
- 已通过本机 SkillHub CLI 发布 1.4.1（`skillId=322039`，审核中）；`iconUrl` 与 `category=dev-programming` 已生效。

## 1.4.0 — 2026-11-15

- 产出识别新增 JSONL `function_call` 里 `Write` / `Edit` 的 `file_path`，与 `artifact-index`、`changes-index` 三路合并；本机实测在 28 条任务中发现 104 个 cwd 内非记忆路径。
- 正文解析固定在搬走 JSONL 之前，避免搬完再解析导致空结果。
- frontmatter 增加 `examples_zh` / `examples_en` / `author`；头像改为官方 WorkBuddy 图标 + 任务徽标组合，提供 256/512/1024 多尺寸。
- 仓库重构为 `skills/<name>/` + 根 `install.py`，便于 skills.sh 等目录索引；宿主仍安装为扁平技能目录。
- `PUBLISHING.md` 更正 skills.sh 状态为未收录/待复核，补充 WorkBuddy/Qoder 市场提交材料。
- 2026-11-15 已通过 GitHub 导入发布到 SkillHub（v1.4.0，安全审核中）；WorkBuddy 开放平台首次提交被收回，当日提审配额已满，次日重新提交。

## 1.3.0 — 2026-11-15

- `move` 搬完后自动删除已无 `*.jsonl` 的源项目目录；`--keep-orphans` 可保留，删除清单写入 `batch.json` 的 `removed_dirs`。
- `doctor` 新增「项目目录一致性」与「空项目目录」检查，默认体检从 8 项扩到 10 项。
- `--create-group` 改为目录必须已存在，确认新建目录时需加 `--allow-missing`。
- 本机实测：清理 3 个空源目录，`projects/` 从 93 个目录收敛到 90 个；70 条任务目录一致性 0 异常。
- 近期迁移实测：9 条任务调整归属，3 个记忆文件与 85 条产出登记（33 条实际移动、26 条已存在、26 条源文件缺失）。

## 1.2.0 — 2026-11-15

- `move --create-group`：目标分组不存在时按绝对路径创建目录，首个迁入任务作为分组种子。
- 文档补充 WorkBuddy 分组由 `cwd` 派生的说明。

## 1.1.0 — 2026-11-15

- `move` 默认恢复为同时迁移记忆与产出，并同步任务文件；新增 `--metadata-only` 只改元数据。
- 迁移 manifest 的 `metadata_only` 默认改为 `false`；`--no-artifacts` 仍可在搬记忆时跳过产出。
- 文档与发布物同步更新到 1.1.0。

## 1.0.0 — 2026-11-15

首次公开发布，由内部技能 `workbuddy-move-conversation` 重命名并重构。

### 新增

- `doctor`：8 项体检（数据库、WAL、表结构、进程、任务文件、快照、标题一致性、备份）。
- `list`：关键词、cwd、时间、区域、账号筛选。
- `rename --export` / `rename --import`：两步式重命名，默认干跑，`--apply` 落盘。
- `rename --export --shards N`：按字数 LPT 自动分片，单条超大任务独占一组。
- `backup`：整库快照，默认保留最近 10 份，目录自动去重。
- `move --with-assets`：可选迁移记忆与产出；默认只改元数据并同步任务文件。

### 变更

- 技能名从 `workbuddy-move-conversation` 改为 `workbuddy-task-manager`。
- 脚本名从 `workbuddy_move.py` 改为 `workbuddy_tasks.py`。
- 标题默认长度改为 **20–30 字**，允许范围 **10–30**；前缀和空格计入。
- 重命名默认干跑，必须 `--apply` 才写库。
- 迁移默认只改元数据并同步必要的 JSONL/子目录，不再默认搬记忆与产出。
- 标题校验增加引号、书名号、句号、问号、路径分隔符等禁用字符。
- `category` 字段可自动补 `[分类] ` 前缀。
- 备份与文本写入改为原子写入 + 目录去重。
- 修正 Windows 路径编码：`X:/赞大拇指` → `x-赞大拇指`（避免双横线）。
- `--ids` 和 `find` 支持任务 ID 前缀。

### 兼容

- `extract` / `apply-titles` 保留为旧命令别名，建议改用 `rename`。
- 迁移 manifest 继续兼容旧格式；新增 `metadata_only` 字段。

## 0.9.0 — 内部迭代

- 批量读取、子智能体分片、三层标题写入、70 条任务重命名实测。
- 支持多账号、侧栏快照、`custom-title` 事件。
