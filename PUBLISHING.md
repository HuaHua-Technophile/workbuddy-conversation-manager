# 发布与上架

本文件记录该技能在各分发渠道的状态，以及还需要人工完成的步骤。

## 状态总览

| 平台 | 状态 | 说明 |
|---|---|---|
| GitHub | ✅ 已发布 | [仓库](https://github.com/HuaHua-Technophile/workbuddy-conversation-manager)，MIT，含 v1.0.0 Release 与两个安装包 |
| skills.sh（Vercel Labs Agent Skills Directory） | ✅ 已收录 | 已通过 `pnpm dlx skills add ... -g` 安装到 `~/.agents/skills/`，榜单检索有延迟 |
| WorkBuddy 开放平台 | ⏳ 待提交 | 安装包已就绪，需开发者认证后后台上传 |
| Qoder 技能市场 | ⏳ 待提交 | 安装包已就绪，需在 Qoder 内提交（机审） |
| skillstore.io | ⏳ 待提交 | 填仓库地址即可，需 GitHub 登录授权 |
| Skill Vault（skillvault.md） | ⏳ 待提交 | 需注册登录后上传 SKILL.md |
| Claude 插件目录 | ❌ 暂不适用 | 需要付费开发者计划 |

## 一键安装

```bash
npx skills add HuaHua-Technophile/workbuddy-conversation-manager
# 本机 npm 缓存异常时可用 pnpm
pnpm dlx skills add HuaHua-Technophile/workbuddy-conversation-manager -g -y
```

或直接克隆：

```bash
git clone https://github.com/HuaHua-Technophile/workbuddy-conversation-manager.git
```

## 提交材料

**技能名（英文）**：WorkBuddy Conversation Manager
**技能名（中文）**：WorkBuddy会话管理
**版本**：1.0.0
**分类**：开发工具 / 效率工具 / 数据管理
**许可证**：MIT

**一句话简介（中文）**
> 管理 WorkBuddy 本地会话：体检、筛选、按完整历史两步式重命名、任务/空间迁移、备份回滚；默认干跑并自动备份。

**一句话简介（英文）**
> Manage local WorkBuddy sessions — doctor, list/filter, two-step rename from full transcripts, move between tasks/spaces, backup & rollback, with dry-run default and automatic backups.

**适用场景**

- 侧栏标题只反映第一句话、难以辨认时批量重命名
- 把同一主题的对话归入对应空间
- 改库前的体检与回滚
- 清理/迁移 WorkBuddy 会话归属

**限制说明**

- 仅 Windows；需 Python 3.9+
- 只操作本机 `~/.workbuddy` 数据
- 不删除会话、不改对话正文
- 迁移默认只改元数据并同步会话文件；记忆/产出需 `--with-assets`

## 打包

```bash
python scripts/build_pkg.py
```

生成两个包：

- `dist/workbuddy-conversation-manager-root-1.0.0.zip`：根目录直接含 `SKILL.md`
- `dist/workbuddy-conversation-manager-dir-1.0.0.zip`：单层目录 `workbuddy-conversation-manager/`

## 版本发布流程

```bash
git add -A
git commit -m "feat: ..."
git tag v1.0.0
git push && git push --tags
gh release create v1.0.0 dist/*.zip --title "v1.0.0" --notes "..."
```

## 待人工完成的步骤

### 1. WorkBuddy 开放平台

1. 打开 <https://open.workbuddy.cn>，完成开发者认证。
2. 进入「发布管理 → 技能 → 创建」，上传 `workbuddy-conversation-manager-root-1.0.0.zip`。
3. 补充头像（512×512，≤500KB）、分类、使用说明。
4. 提交审核。

### 2. Qoder 技能市场

1. 在 Qoder 内打开技能市场 → 上传自有 Skill。
2. 使用 `workbuddy-conversation-manager-dir-1.0.0.zip`（单层同名目录 + SKILL.md）。
3. 参考文档：<https://docs.qoder.com/zh/qoderwork/skill-marketplace-guidelines>

### 3. skillstore.io

1. 打开 <https://skillstore.io/submit>。
2. 填入仓库地址 `https://github.com/HuaHua-Technophile/workbuddy-conversation-manager`。
3. 等待自动安全扫描与人工审核。

### 4. Skill Vault

1. 打开 <https://skillvault.md>，用 GitHub / Google / 邮箱登录。
2. 上传 `SKILL.md`，填写兼容的宿主标签。
