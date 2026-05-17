# 一键发布设计

## 背景

当前仓库同时存在两条发布链路：

- 本地手工链路：修改 `RELEASE_NOTES.md`、创建 tag、手工创建 GitHub Release
- CI 链路：push `v*` tag 后由 GitHub Actions 构建产物并发布 release

两条链路的职责重叠，导致以下问题：

- release notes 不是单一来源
- 本地 release 创建与 CI release 创建可能冲突
- tag 可能指向远端不存在的提交
- 本地凭据、远端协议和 CI 权限问题会直接干扰发版

目标是把发布收敛为一个稳定流程：AI 只生成 release notes，用户运行一个脚本完成发版，其余发布动作统一交给 CI。

## 目标

- AI 只负责生成或改写 `RELEASE_NOTES.md`
- `RELEASE_NOTES.md` 必须提交到仓库
- 本地一键脚本只负责发布收尾，不负责生成 release 或构建产物
- GitHub Actions 成为唯一正式发布者
- GitHub Release 正文和 Telegram 通知正文共用同一份 release notes

## 非目标

- 脚本不负责挑选要发布的功能提交
- 脚本不负责合并分支或解决冲突
- 脚本不负责本地构建产物
- 不支持从未提交的工作区状态直接生成正式 release

## 约束

- 用户在运行发布脚本前，当前分支已经包含所有要发布的功能提交
- 发布前允许未提交变更只能是 `RELEASE_NOTES.md`
- 发布脚本可以自动创建一个只包含 `RELEASE_NOTES.md` 的发布提交
- GitHub Release 的唯一正文来源是仓库中的 `RELEASE_NOTES.md`

## 总体方案

发布职责按以下方式收口：

- AI：生成 `RELEASE_NOTES.md`
- 本地脚本 `scripts/release.sh <version>`：检查仓库状态、提交 notes、推送当前分支、创建 tag、推送 tag、等待 CI 结果
- GitHub Actions：基于 tag 构建产物，读取仓库中的 `RELEASE_NOTES.md` 创建或更新 GitHub Release，并发送 Telegram 通知

发布链路固定为：

1. AI 生成 `RELEASE_NOTES.md`
2. 用户运行 `scripts/release.sh X.Y.Z`
3. 脚本创建只包含 notes 的提交
4. 脚本先推送当前分支，再推送 `vX.Y.Z` tag
5. CI 接收 tag，构建产物并发布 release

## 本地脚本设计

脚本入口：

```bash
scripts/release.sh 0.49.0
```

脚本行为：

1. 校验版本号格式必须为 `X.Y.Z`
2. 计算目标 tag 为 `vX.Y.Z`
3. 打印当前分支、当前 `HEAD`、目标版本、目标 tag
4. 校验当前分支必须是正式发布分支，第一版限定为 `master`
5. 校验工作区未提交变更仅允许 `RELEASE_NOTES.md`
6. 校验 `RELEASE_NOTES.md` 非空
7. 校验本地与远端不存在同名 tag
8. 校验当前分支不落后远端；如果 `behind` 则直接失败
9. 只 `git add RELEASE_NOTES.md`
10. 自动创建发布提交，例如 `docs: add release notes for v0.49.0`
11. 推送当前分支到远端
12. 创建本地 tag `v0.49.0`
13. 推送 tag 到远端
14. 轮询对应 GitHub Actions run，成功时输出 release URL，失败时输出 run URL 并返回非 0

关键顺序约束：

- 必须先推分支，再推 tag
- 脚本不得本地执行 `gh release create`
- 脚本只提交 `RELEASE_NOTES.md`，避免夹带其他改动

## CI Workflow 设计

保留现有“tag push 触发构建”的总体结构，但调整 release 正文来源。

### 需要保留的行为

- `push tags: v*` 触发 workflow
- 三平台构建与产物收集逻辑保留
- release job 继续上传构建产物
- Telegram 通知继续在 release job 中发送

### 需要修改的行为

- `Create GitHub Release` 不再使用 `generate_release_notes: true`
- 改为显式使用仓库中的 `RELEASE_NOTES.md` 作为 release body
- release 已存在时应走“更新 release 正文和资产”的幂等路径，而不是失败退出
- Telegram 通知继续读取最终 release body，保证与发布页完全一致

### release job 语义

1. 下载构建产物
2. 收集 release assets
3. 使用 `RELEASE_NOTES.md` 创建或更新 tag 对应 release
4. 读取最终 release body
5. 发送 Telegram 通知

## 环境与凭据要求

- 远端协议需要统一，推荐将 `origin` 统一为 SSH
- 本地发布机器必须具备稳定的 push 权限
- 脚本不依赖修改用户级 `~/.gitconfig`
- CI 使用 `GITHUB_TOKEN` 负责 release 创建、更新和资产上传

## 失败处理

脚本应在以下场景直接失败并给出明确原因：

- 版本号非法
- 当前分支不是正式发布分支
- `RELEASE_NOTES.md` 之外存在未提交改动
- 当前分支落后远端
- 本地或远端已存在同名 tag
- 推送当前分支失败
- 推送 tag 失败
- CI release workflow 失败

失败时输出原则：

- 本地校验失败：打印明确的检查项和当前状态
- 推送失败：打印 git 命令与远端错误
- CI 失败：输出 GitHub Actions run URL

## 防呆规则

- 脚本启动即打印 `branch`、`HEAD`、`version`、`tag`
- 第一版只允许在 `master` 上执行
- 脚本不自动拉取、不自动 rebase、不自动 merge
- 发布脚本的唯一自动提交是 `RELEASE_NOTES.md`
- 推送分支成功之前不得创建 release tag

## 测试与验证

需要新增或更新以下验证：

- 脚本级别
  - 版本号校验
  - 工作区脏状态校验
  - 只允许 `RELEASE_NOTES.md` 被提交
  - `behind` 远端时失败
  - tag 已存在时失败
  - 先推分支再推 tag 的顺序验证
- workflow 级别
  - release job 使用 `RELEASE_NOTES.md` 而不是 `generate_release_notes`
  - Telegram 通知继续复用最终 release body
  - release job 在已有 release 时能执行更新路径

## 风险与缓解

- 风险：用户在 `RELEASE_NOTES.md` 之外还保留本地修改，脚本可能把工作区状态搞混。
  - 缓解：脚本在发现额外脏文件时直接退出。
- 风险：tag 在分支推送前创建，会再次出现“远端不存在对应提交”的问题。
  - 缓解：脚本流程强制先推分支，再推 tag。
- 风险：本地凭据和远端协议混用，导致推送偶发失败。
  - 缓解：统一远端协议，并避免脚本承担 release API 写操作。
- 风险：CI 仍然使用自动生成 notes，覆盖 AI 产出的文案。
  - 缓解：移除 `generate_release_notes: true`，改为显式传入 `RELEASE_NOTES.md`。

## 结果

完成改造后，正式发布流程应简化为：

1. AI 生成 `RELEASE_NOTES.md`
2. 用户执行 `scripts/release.sh X.Y.Z`
3. CI 自动完成构建、GitHub Release 更新和 Telegram 通知

这样可以把发布过程从“本地手工补洞”收敛成“单脚本点火，CI 单点发布”的稳定链路。
