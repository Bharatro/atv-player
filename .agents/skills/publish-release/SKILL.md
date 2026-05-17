---
name: publish-release
description: 自动创建 GitHub Release、生成中文 Release Notes、创建并推送 Git Tag
---

# publish-release

用于自动发布 GitHub Release。

## 触发示例

- 发布版本 0.45.0
- 创建 release
- 发版
- 发布新版本

---

## 输入

版本号：

```text
0.45.0
```

自动派生：

```text
tag: v0.45.0
title: v0.45.0
```

---

## 执行流程

### 1. 获取最近提交

优先：

```bash
git log --pretty=format:"%s" $(git describe --tags --abbrev=0)..HEAD
```

如果没有 tag：

```bash
git log --pretty=format:"%s" -20
```

---

### 2. 生成中文 Release Notes

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

输出到：

```text
RELEASE_NOTES.md
```

---

### 3. 创建并推送 Tag

如果 tag 不存在：

```bash
git tag v0.45.0
git push origin v0.45.0
```

如果已存在则跳过。

---

### 4. 创建 GitHub Release

优先使用 GitHub CLI：

```bash
gh release create v0.45.0 \
  --title "v0.45.0" \
  --notes-file RELEASE_NOTES.md
```

如果 release 已存在：

```bash
gh release edit v0.45.0 \
  --title "v0.45.0" \
  --notes-file RELEASE_NOTES.md
```

---

## 最终输出

```text
✅ Release 创建完成

- Tag: v0.45.0
- Title: v0.45.0
- 已推送 Git Tag
- 已创建 GitHub Release
```
