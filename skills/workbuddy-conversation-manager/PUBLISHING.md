# 发布与上架

本文件记录分发渠道状态与提交步骤。平台规则可能变化，**以页面提示为准**；下列流程核对于 2026-11-15。

## 状态总览

| 平台 | 状态 | 说明 |
|---|---|---|
| GitHub | ✅ 已发布 | [仓库](https://github.com/HuaHua-Technophile/workbuddy-conversation-manager) · [v1.4.0 Release](https://github.com/HuaHua-Technophile/workbuddy-conversation-manager/releases/tag/v1.4.0)，MIT，含 `-root` / `-dir` 两个安装包 |
| skills.sh（Vercel Labs 目录） | ⚠️ 未收录/待复核 | 2026-11-15 复核页面为 404。该站没有手动提交入口，按 `npx skills add` 安装量索引；仓库已改为 `skills/<name>/` 布局，需重新检查索引状态。`skills list -g` 显示 tracked 不等于 skills.sh 已收录。 |
| WorkBuddy 开放平台 | 🕒 审核中 | 2026-11-15 已提交 `-dir` 包，技能 ID `os_d12a959583509f94`，预计 7 个工作日。 |
| SkillHub（腾讯） | ⏳ 待提交（GitHub 导入） | 绑定 GitHub 后可直接识别 `skills/<name>/`，无需本地上传 zip。slug `workbuddy-conversation-manager`，版本 1.4.0。 |
| Qoder 技能市场 | ⏳ 待提交 | 客户端「扩展 → 技能 → 添加技能」可先自用；公开市场走拓展发布，机审。使用 `-dir` 包。 |
| skillstore.io / Skill Vault | ⏳ 可选 | 第三方目录，填仓库地址或上传 SKILL.md。 |

## 仓库结构

```
workbuddy-conversation-manager/
├── install.py
├── README.md
├── LICENSE
├── .gitignore
├── dist/                              # 构建产物（git 忽略）
└── skills/
    └── workbuddy-conversation-manager/
        ├── SKILL.md
        ├── CHANGELOG.md
        ├── PUBLISHING.md
        ├── assets/
        │   ├── icon-1024.png
        │   ├── icon-512.png
        │   └── icon-512.jpg
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
python skills/workbuddy-conversation-manager/scripts/build_pkg.py
```

生成：

- `dist/workbuddy-conversation-manager-root-1.4.0.zip`：根目录直接含 `SKILL.md`
- `dist/workbuddy-conversation-manager-dir-1.4.0.zip`：单层目录 `workbuddy-conversation-manager/`

## 提交材料

- **标识名**：`workbuddy-conversation-manager`（小写字母、数字、连字符）
- **中文名**：`WorkBuddy会话管理`
- **英文名**：`WorkBuddy Conversation Manager`
- **版本**：1.4.0
- **分类**：开发工具 / 效率工具 / 数据管理
- **许可证**：MIT
- **头像**：`skills/workbuddy-conversation-manager/assets/icon-512.png`（512×512，105 KB，≤500 KB；官方 WorkBuddy 图标 + 会话徽标）

**中文简介**

> 管理 WorkBuddy 本地会话：体检、筛选、按完整历史两步式重命名、任务/空间迁移（含记忆与产出）、备份回滚；默认干跑并按对象备份。

**英文简介**

> Manage local WorkBuddy sessions — doctor, list/filter, two-step rename from full transcripts, move between tasks/spaces with memory and outputs, backup & rollback, with dry-run default and per-object backups.

**适用场景**

- 侧栏标题只反映第一句话，批量重命名
- 把同一主题的对话归入对应空间（含记忆与产出）
- 新建空间并迁入种子会话
- 改库前体检与回滚

**限制**

- 仅 Windows；Python 3.9+
- 只操作本机 `~/.workbuddy` 数据
- 不删除会话、不改对话正文、不重建搜索索引
- 默认迁移会搬记忆与产出；只要元数据时用 `--metadata-only`

## frontmatter 字段

WorkBuddy/Qoder 市场解析 `SKILL.md` 时会检查以下字段：

| 字段 | 本仓库取值 |
|---|---|
| `name` | `workbuddy-conversation-manager` |
| `version` | `1.4.0` |
| `display_name` | `WorkBuddy Conversation Manager` |
| `display_name_zh` | `WorkBuddy会话管理` |
| `description` | 中文触发描述 |
| `description_zh` / `description_en` | 双语描述 |
| `examples_zh` / `examples_en` | 每语言 3 条示例 |
| `author` | `HuaHua` |
| `tags` | WorkBuddy / 会话管理 / 重命名 / 迁移 / SQLite |
| `license` | MIT |

## 渠道一：WorkBuddy 开放平台

1. 打开 <https://open.workbuddy.cn>，完成开发者认证。
2. 左侧「发布管理 → 技能 → 创建」。
3. 上传 `workbuddy-conversation-manager-dir-1.4.0.zip`。要求：解压后第一层就是技能目录，即 `workbuddy-conversation-manager/SKILL.md`，且只允许两级目录。
4. 平台自动解析 frontmatter；缺字段会拒绝。
5. 上传头像 `assets/icon-512.png`，补充分类与使用说明。
6. 提交审核；当日 5 次 / 当月 20 次提审配额。

## 渠道二：SkillHub

1. 绑定 GitHub 账号后打开 <https://skillhub.cn/dashboard/publish>，选择「发布 Skill → 从 GitHub 导入」。
2. 平台会扫描已绑定仓库的 `skills/<name>/` 目录，直接勾选 `workbuddy-conversation-manager`。
3. 首次发布填 slug、显示名称、版本、变更说明；导入源在 GitHub，后续更新直接刷新仓库即可。
4. 若 GitHub 导入不可用，再退回「本地上传」，使用 `-dir` 包。
5. 已发布条目在「我的 Skills」显示安全审核状态，审核通过后同步到技能广场。

## 渠道三：Qoder 技能市场

1. 客户端「扩展 → 技能 → 添加技能」可先本地自用。
2. 公开市场走「拓展发布」，上传 `workbuddy-conversation-manager-dir-1.4.0.zip`。
3. 参考文档：<https://docs.qoder.com/zh/qoderwork/skill-marketplace-guidelines>
4. 机审为主，通常几分钟出结果。

## 渠道四：skills.sh

- 没有手动提交入口；按仓库安装量索引。
- 已验证 `https://skills.sh/HuaHua-Technophile/workbuddy-conversation-manager` 当前为 404。
- 仓库已改为 `skills/<name>/` 布局，安装/更新后需重新检查页面，不要仅凭 `skills list -g` 判断已收录。
- 一键安装：

```bash
npx skills add HuaHua-Technophile/workbuddy-conversation-manager
# 本机 npm 缓存异常时
pnpm dlx skills add HuaHua-Technophile/workbuddy-conversation-manager -g -y
```

## 渠道五：第三方目录（可选）

- **skillstore.io**：打开 <https://skillstore.io/submit>，填仓库地址。
- **Skill Vault**：打开 <https://skillvault.md>，登录后上传 `SKILL.md`。

## 版本发布流程

```bash
python skills/workbuddy-conversation-manager/scripts/build_pkg.py
git add -A
git commit -m "feat(v1.4.0): ..."
git tag v1.4.0
git push && git push --tags
gh release create v1.4.0 dist/*.zip --title "v1.4.0" --notes "..."
```

发布前检查：

- [ ] `SKILL.md` 的 `version` = 本次发布版本
- [ ] `scripts/workbuddy_sessions.py` 的 `VERSION` 一致
- [ ] `scripts/build_pkg.py` 的 `VERSION` 一致
- [ ] `python install.py --targets all` 后宿主技能可加载
- [ ] `doctor` 通过
- [ ] 解压 `-dir` 包确认第一层目录名与 `name` 一致
- [ ] frontmatter 字段齐全
- [ ] 头像 512×512 且 ≤500 KB
