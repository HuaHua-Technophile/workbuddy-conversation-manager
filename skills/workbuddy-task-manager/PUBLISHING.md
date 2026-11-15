# 发布与上架

本文件记录分发渠道状态与提交步骤。平台规则可能变化，**以页面提示为准**；下列流程核对于 2026-11-15。

## 状态总览

| 平台 | 状态 | 说明 |
|---|---|---|
| GitHub | ✅ v1.5.0 已发布 | [仓库](https://github.com/HuaHua-Technophile/workbuddy-task-manager/releases)，MIT。已接 `.github/workflows/release.yml`：push tag `v*` 自动校验版本、打包并发布 Release。本次 1.5.0 的 Release 手动创建，SkillHub 新 slug 由本机 CLI 发布；旧 slug 已退役。下一版配置 `SKILLHUB_KEY` 后走 tag 自动化。 |
| SkillHub（腾讯） | 🕒 v1.5.0 审核中 | 新 slug `workbuddy-task-manager` 已发布，旧 slug 已退役；skillId 与新 listing 以实际发布结果为准。`iconUrl` 使用仓库 jsdelivr，`category=dev-programming`。 |
| WorkBuddy 开放平台 | ⚠️ 已收回，配额已满 | 2026-11-15 首次提交后显示已收回；当日提审 5/5 已满。2026-11-16 上传 v1.5.0 `-dir` 包重新提交。技能 ID `os_d12a959583509f94`。 |
| skills.sh（Vercel Labs 目录） | ⚠️ 未收录 | 无手动提交入口，按 `npx skills add` 安装量索引；已改为 `skills/<name>/` 布局，等平台扫描。 |
| Qoder 技能市场 | ⏳ 待提交 | 客户端「扩展 → 技能 → 添加技能」可先自用；公开市场走拓展发布。 |
| skillstore.io / Skill Vault | ⏳ 可选 | 第三方目录，填仓库地址或上传 SKILL.md。 |

## 仓库结构

```
workbuddy-task-manager/
├── .github/
│   └── workflows/
│       └── release.yml                # tag 自动构建 + GitHub Release + SkillHub
├── install.py
├── README.md
├── LICENSE
├── .gitignore
├── dist/                              # 构建产物（git 忽略）
└── skills/
    └── workbuddy-task-manager/
        ├── SKILL.md
        ├── CHANGELOG.md
        ├── PUBLISHING.md
        ├── assets/
        │   ├── icon-1024.png
        │   ├── icon-512.png
        │   ├── icon-512.jpg
        │   ├── icon-256.png
        │   └── icon-256.jpg
        ├── scripts/
        ├── references/
        └── examples/
```

仓库采用 `skills/<name>/` 布局便于目录站索引；宿主要求扁平技能目录，用根目录 `install.py` 摊平安装：

```bash
python install.py --targets all
# 或只装一个宿主
python install.py --to ~/.qoder/skills
```

## 打包

```bash
python skills/workbuddy-task-manager/scripts/build_pkg.py
```

生成：

- `dist/workbuddy-task-manager-root-<版本>.zip`：根目录直接含 `SKILL.md`
- `dist/workbuddy-task-manager-dir-<版本>.zip`：单层目录 `workbuddy-task-manager/`

两个包内容一致，只差一层目录。WorkBuddy 与 Qoder 使用 `-dir` 包。

## 提交材料

- **标识名**：`workbuddy-task-manager`（小写字母、数字、连字符）
- **中文名**：`WorkBuddy任务管理`
- **英文名**：`WorkBuddy Task Manager`
- **版本**：1.5.0
- **SkillHub 分类**：`dev-programming`（开发编程）
- **许可证**：MIT
- **头像**：`assets/icon-512.png`（512×512，约 243 KB，≤500 KB；Qoder 同构布局：左下 WorkBuddy 图标、右上紫色文档、右下紫色铅笔）

**中文简介**

> 管理 WorkBuddy 本地任务：体检、筛选、按完整历史两步式重命名、任务/分组迁移（含记忆与产出）、备份回滚；默认干跑并按对象备份。

**英文简介**

> Manage local WorkBuddy tasks — doctor, list/filter, two-step rename from full transcripts, move between tasks/groups with memory and outputs, backup & rollback, with dry-run default and per-object backups.

**适用场景**

- 侧栏标题只反映第一句话，批量重命名
- 把同一主题的任务归入对应分组（含记忆与产出）
- 新建分组并迁入种子任务
- 改库前体检与回滚

**限制**

- 仅 Windows；Python 3.9+
- 只操作本机 `~/.workbuddy` 数据
- 不删除任务、不改任务正文、不重建搜索索引
- 默认迁移会搬记忆与产出；只要元数据时用 `--metadata-only`

## frontmatter 字段

WorkBuddy/Qoder 市场解析 `SKILL.md` 时会检查以下字段：

| 字段 | 本仓库取值 |
|---|---|
| `name` | `workbuddy-task-manager` |
| `version` | `1.5.0` |
| `display_name` | `WorkBuddy Task Manager` |
| `display_name_zh` | `WorkBuddy任务管理` |
| `description` | 中文触发描述 |
| `description_zh` / `description_en` | 双语描述 |
| `examples_zh` / `examples_en` | 每语言 3 条示例 |
| `author` | `HuaHua` |
| `tags` | WorkBuddy / 任务管理 / 分组 / 重命名 / 迁移 / SQLite |
| `license` | MIT |

SkillHub CLI 只认另一套驼峰字段，两套并存，互不影响：

| 字段 | 本仓库取值 |
|---|---|
| `slug` | `workbuddy-task-manager` |
| `displayName` | `WorkBuddy任务管理` |
| `summary` | 中文简介，列表页展示 |
| `iconUrl` | `https://cdn.jsdelivr.net/gh/HuaHua-Technophile/workbuddy-task-manager@main/skills/workbuddy-task-manager/assets/icon-512.png` |
| `category` | `dev-programming`（一级分类 key） |
| `homepage` | GitHub 仓库地址 |

## 渠道一：GitHub + SkillHub 自动发布

### GitHub Actions

`.github/workflows/release.yml` 在 push tag `v*` 时：

1. 校验 tag 与 `SKILL.md`、`workbuddy_tasks.py`、`build_pkg.py` 三处版本号一致。
2. 运行 `python skills/workbuddy-task-manager/scripts/workbuddy_tasks.py --version` 做脚本可导入检查。
3. 构建 `-root` / `-dir` 两个 zip。
4. 创建 GitHub Release 并上传 zip。
5. 同一 workflow 的 `skillhub` job 登录 SkillHub CLI 并发布（需要仓库 secret `SKILLHUB_KEY`）。

标准流程：

```bash
# 1) 同步三处版本号：SKILL.md / scripts/workbuddy_tasks.py / scripts/build_pkg.py
# 2) 写 CHANGELOG
git add -A && git commit -m "feat(vX.Y.Z): ..."
git push
git tag -a vX.Y.Z -m "vX.Y.Z — 摘要"
git push origin vX.Y.Z     # GitHub Release 与 SkillHub 自动开始
```

补发历史版本：

```bash
gh workflow run Release --repo HuaHua-Technophile/workbuddy-task-manager -f tag=v1.5.0
```

### SkillHub CLI（本机手动/CI 共用）

本机 CLI 是纯 Python 单文件，Windows 的 Git Bash 可直接跑，不需要 WSL：

```bash
python "C:/Users/HuaHua/.skillhub/skills_store_cli.py" auth whoami
```

首次登录：

```bash
python "C:/Users/HuaHua/.skillhub/skills_store_cli.py" login --key skh_xxx --host https://api.skillhub.cn
python "C:/Users/HuaHua/.skillhub/skills_store_cli.py" auth whoami
```

- Token 在 <https://skillhub.cn/dashboard/keys> 创建，只显示一次。
- 本机 `~/.skillhub/config.json` / 凭证文件是**明文**，不要提交到仓库。
- GitHub Actions 用仓库 secret `SKILLHUB_KEY`；secret 由 GitHub 加密保存，创建后不可回读，fork PR 拿不到。

发布前先 dry-run：

```bash
rm -rf /tmp/pub && mkdir -p /tmp/pub
cp -r skills/workbuddy-task-manager /tmp/pub/
rm -rf /tmp/pub/workbuddy-task-manager/assets
python "C:/Users/HuaHua/.skillhub/skills_store_cli.py" publish /tmp/pub/workbuddy-task-manager \
  --host https://api.skillhub.cn \
  --changelog "v1.5.0：仓库与技能标识统一为 workbuddy-task-manager，CLI 增加 task/group 别名" \
  --dry-run
```

正式发布去掉 `--dry-run`。关键规则：

- **必须剔除 `assets/`**：CLI 会把技能目录下所有文件打包上传，平台拒绝 `png` 等二进制文件（`400 不允许的文件类型`）。本地安装目录不含 assets，所以本地发布不会暴露这个问题，CI 会。
- **同 slug 发布 = 新版本**，但版本号必须递增；同版本会报 `版本 x.y.z 已存在`。
- **图标异步生效**：publish 成功后 `skill.iconUrl` 可能还是旧值，约 30–60 秒后更新；`iconUrl` 可用仓库 jsdelivr，不依赖平台托管。
- **分类用 `category`**（一级 key，如 `dev-programming`），不是 `categoryIds`；`categoryIds` 是团队版字段，普通 Skill 会被静默忽略。
- 连续发布会触发 `429 请求过于频繁`，等约 50 秒再试。

发布后在 <https://skillhub.cn/dashboard> 查看「安全审核中」；审核通过后详情页才完整可见。

本机实测（2026-11-15）：v1.5.0 使用新 slug 重新发布；发布后 `iconUrl` 指向仓库 jsdelivr，`category=dev-programming`。审核通过后展示名与概述使用“任务 / 分组”。

### CI 的两个坑

1. **不能另建由 Release 触发的 workflow**：`GITHUB_TOKEN` 创建的 Release 不会再触发其他 workflow（GitHub 防递归）。SkillHub 发布必须放在同一个 workflow 的第二个 job（`needs: release`）。
2. **必须先剔除 `assets/`**：见上，CI 第一次跑最容易挂在这里。

> 当前 WorkBuddy 仓库尚未配置 `SKILLHUB_KEY`；配置后 tag 流程才能全绿。配置前可先手动跑上面的 CLI 发布。

## 渠道二：WorkBuddy 开放平台

1. 打开 <https://open.workbuddy.cn>，完成开发者认证。
2. 左侧「发布管理 → 技能 → 创建」。
3. 上传 `workbuddy-task-manager-dir-<版本>.zip`。要求：解压后第一层就是技能目录，即 `workbuddy-task-manager/SKILL.md`，且只允许两级目录。
4. 平台自动解析 frontmatter；缺字段会拒绝。
5. 上传头像 `assets/icon-512.png`，补充分类与使用说明。
6. 提交审核；当日 5 次 / 当月 20 次提审配额。
7. 已上架后更新版本：列表卡片右侧「更新版本」，传新的 `-dir` 包，技能 ID 与 slug 不变，同样消耗提审额度。
8. 2026-11-15 实测：首次提交后状态变为「已收回」，同日配额已用满 5/5，页面提示次日再提交；重新提交前先查「收回原因」。

> WorkBuddy 没有 API / CLI / CI，只能控制台手动上传；GitHub 自动化覆盖不到这一渠道。

## 渠道三：Qoder 技能市场

1. 客户端「扩展 → 技能 → 添加技能」可先本地自用。
2. 公开市场走「拓展发布」，上传 `workbuddy-task-manager-dir-<版本>.zip`。
3. 参考文档：<https://docs.qoder.com/zh/qoderwork/skill-marketplace-guidelines>
4. 机审为主，通常几分钟出结果。

## 渠道四：skills.sh

- 没有手动提交入口；按仓库安装量索引。
- 已验证 `https://skills.sh/HuaHua-Technophile/workbuddy-task-manager` 当前为 404。
- 仓库已改为 `skills/<name>/` 布局，安装/更新后需重新检查页面，不要仅凭 `skills list -g` 判断已收录。
- 一键安装：

```bash
npx skills add HuaHua-Technophile/workbuddy-task-manager
# 本机 npm 缓存异常时
pnpm dlx skills add HuaHua-Technophile/workbuddy-task-manager -g -y
```

## 渠道五：第三方目录（可选）

- **skillstore.io**：打开 <https://skillstore.io/submit>，填仓库地址。
- **Skill Vault**：打开 <https://skillvault.md>，登录后上传 `SKILL.md`。

## 版本发布流程

1. 改三处版本号：`SKILL.md` / `scripts/workbuddy_tasks.py` / `scripts/build_pkg.py`。
2. 更新 `CHANGELOG.md`，同步 `PUBLISHING.md` 的渠道状态。
3. 本地 `python skills/workbuddy-task-manager/scripts/build_pkg.py`，确认两个 zip 可生成。
4. `git add -A && git commit -m "feat(vX.Y.Z): ..." && git push`。
5. 配置 `SKILLHUB_KEY` 后，`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`；Actions 会完成 Release 与 SkillHub。
6. 到 WorkBuddy 开放平台手动上传 `-dir` 包（额度允许时）。
7. 需要时手动补 SkillHub 图标/分类或检查审核状态。

发布前检查：

- [ ] 三处版本号一致：`SKILL.md` / `scripts/workbuddy_tasks.py` / `scripts/build_pkg.py`
- [ ] `python scripts/workbuddy_tasks.py doctor` 通过
- [ ] `python scripts/build_pkg.py` 能生成两个 zip
- [ ] 解压 `-dir` 包确认第一层目录名与 `name` 一致
- [ ] frontmatter 必填字段齐全（WorkBuddy 下划线族 + SkillHub 驼峰族）
- [ ] `iconUrl` 地址可达（`curl -I`）
- [ ] 发布前临时目录已剔除 `assets/`
- [ ] 头像 512×512 且 ≤500 KB
- [ ] 打 tag 后看 Actions 是否全绿，再处理 WorkBuddy 手动上传
