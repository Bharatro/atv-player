---
name: publish-release
description: Use when publishing a new atv-player version after feature commits are ready and the user wants AI to generate RELEASE_NOTES.md and then run the repo release script.
---

# publish-release

为 `atv-player` 执行发布收尾。

这个 skill 只做两件事：

1. 生成或改写 `RELEASE_NOTES.md`
2. 调用 `scripts/release.sh <version>` 完成发布

其它发布相关事情全部交给发布脚本完成。

不要再使用本地 `gh release create`、`gh release edit` 或手工 `git tag` 作为主流程。正式 release 由仓库脚本和 GitHub Actions 负责。

## 触发示例

- 发布版本 `0.50.0`
- 发版
- 生成 release notes 并发布
- 只描述代理改动然后发版

## 输入

版本号：

```text
0.50.0
```

自动派生：

```text
tag: v0.50.0
script: scripts/release.sh 0.50.0
```

## 执行流程

### 1. 获取最近 tag 以来的提交

优先：

```bash
git log --pretty=format:"%s" $(git describe --tags --abbrev=0)..HEAD
```

如果没有 tag：

```bash
git log --pretty=format:"%s" -20
```

必要时补充查看提交范围和改动文件，用来判断哪些内容应该进入 release notes。

### 2. 生成中文 `RELEASE_NOTES.md`

要求：

- 使用中文
- 面向最终用户
- 按“新增 / 优化 / 修复”分类
- 合并重复或相似 commit
- 忽略：
  - typo
  - wip
  - test
  - debug
- 忽略文档类更新
- 如果用户要求“只描述某类改动”，严格按该范围写，不扩展到其他变更

分类映射：

```text
feat/add/support -> 新增
fix/bug -> 修复
optimize/improve/perf/refactor -> 优化
```

如果检测到以下关键词，优先保留：

- TVBox
- MPV
- 弹幕
- 网盘
- yt-dlp
- 刮削
- TMDB
- 代理

输出到：

```text
RELEASE_NOTES.md
```

### 3. 运行仓库发布脚本

使用唯一发布入口：

```bash
scripts/release.sh 0.50.0
```

AI 到这里为止只允许做这一步调用，不允许额外接管发布过程。除了 `RELEASE_NOTES.md` 之外，其它事情全部交给发布脚本。

脚本会负责：

- 校验当前分支和工作区状态
- 允许保留未跟踪的 `docs/` 文档，不阻塞发布
- 自动提交 `RELEASE_NOTES.md`
- 推送当前分支
- 创建并推送 `v0.50.0` tag
- 输出 release URL；如果 GitHub Release 尚未生成，则输出对应的 release 页面地址供后续查看

如果脚本失败，直接报告脚本输出的阻塞原因并停止，不要扩展处理。

## 禁止事项

除了生成 `RELEASE_NOTES.md` 和调用 `scripts/release.sh <version>` 之外，AI 不要做任何额外发布修复动作，包括但不限于：

- 不要手工 `git tag`
- 不要手工 `git push`
- 不要手工 `gh release create` / `gh release edit`
- 不要等待或轮询 GitHub Actions
- 不要 `stash`、移动、删除工作区文件来“帮助发布”
- 不要删除或改写本地 / 远端 tag
- 不要修改 git remote、认证方式或凭据配置

如果仓库状态、tag、权限、认证或网络环境有问题，让脚本报错，然后把阻塞点原样告诉用户。

## 最终输出

```text
✅ Release 发布完成

- Version: 0.50.0
- Tag: v0.50.0
- Release notes: RELEASE_NOTES.md
- Release URL: <script output>
```

如果脚本失败，输出：

```text
❌ Release 发布失败

- Version: 0.50.0
- 阻塞点: <script stderr / 关键错误>
```
