---
name: publish-release
description: Use when publishing a new atv-player version after feature commits are ready and the user wants AI to generate RELEASE_NOTES.md and then run the repo release script.
---

# publish-release

为 `atv-player` 执行发布收尾。

这个 skill 只做两件事：

1. 生成或改写 `RELEASE_NOTES.md`
2. 调用 `scripts/release.sh <version>` 完成发布

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

### 0. 先检查当前分支

先执行：

```bash
git branch --show-current
```

要求：

- 当前分支必须是 `master`
- 如果不是 `master`，停止发布流程并明确提示用户先切回 `master`
- 不要在错误分支上继续生成 `RELEASE_NOTES.md` 或调用发布脚本

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

脚本会负责：

- 校验当前分支和工作区状态
- 自动提交 `RELEASE_NOTES.md`
- 推送当前分支
- 创建并推送 `v0.50.0` tag
- 等待 GitHub Actions 完成
- 输出 release URL

如果脚本失败，直接报告脚本输出的阻塞原因，不要回退到本地手工创建 release。

脚本本身也会再次校验当前分支是否为 `master`，但 skill 应该在调用脚本前就先做这层检查。

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
