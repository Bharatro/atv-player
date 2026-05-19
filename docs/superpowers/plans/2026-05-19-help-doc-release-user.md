# Help Doc Release User Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework `docs/help.md` into a release-user-first manual that guides packaged-app users through first use, clarifies `yt-dlp` and backend dependencies, and adds structured reference chapters without changing app behavior.

**Architecture:** Keep the existing mature operation chapters as the core, but reorder the document into a two-layer flow: first-use guidance up front, then reference information in the back half. Implement the change in slices inside `docs/help.md` so each patch is easy to review: startup path first, then settings wording, then new capability/reference chapters, then data/terminology/renumbering, followed by a final consistency pass.

**Tech Stack:** Markdown, existing repository docs conventions, `rg`, `sed`, `git`

---

## File Map

- Modify `docs/help.md`
  Reorder the document, add release-user quick start, split prerequisites, refine `yt-dlp` wording, add reference chapters, expand local data guidance, unify terminology, and renumber headings.

### Task 1: Reframe The Opening For Release Users

**Files:**
- Modify: `docs/help.md`
- Review: `docs/help.md`

- [ ] **Step 1: Rewrite the opening section and add the packaged-release quick start**

Replace the introduction and the first chapters so the document clearly defaults to packaged release users and inserts a new `快速开始（3 分钟）` section before prerequisites.

```markdown
# atv-player 详细帮助文档

本文档面向终端用户，按“快速开始 -> 主窗口 -> 播放器 -> 直播源 -> 插件 -> 排障”的顺序说明实际使用方法。

## 1. 应用定位

`atv-player` 是一个围绕 `alist-tvbox` 后端工作的桌面播放器：

- 主窗口负责登录、浏览内容、全局搜索、查看历史、管理插件和直播源。
- 播放器窗口负责实际播放、切换线路、恢复进度、管理字幕、弹幕、清晰度和媒体刮削。
- 应用会在本地保存大部分使用状态，以便下次启动时继续上次的工作位置。

如果你使用的是 GitHub Release 提供的打包版本，可直接按下面的“快速开始（3 分钟）”完成首次使用；如果你是从源码运行或自行打包，再看后面的源码运行说明。

## 2. 快速开始（3 分钟）

如果你使用的是发布页面提供的打包单体包，推荐按下面顺序完成首次使用：

1. 下载与你平台对应的发行包并解压。
2. 直接运行 `atv-player`。
3. 启动 `alist-tvbox` 后端。
4. 在登录页输入后端地址、用户名和密码。
5. 登录成功后，在顶部搜索框输入影片名。
6. 双击结果进入播放。

如果你要直接打开 `YouTube` 等页面链接，还需要单独安装 `yt-dlp`。如果你在启动、登录或播放时遇到问题，再继续阅读后文对应章节。
```

- [ ] **Step 2: Split prerequisites into packaged users and source users**

Rewrite the current prerequisites so packaged users only see real runtime prerequisites, while the source-run path is explicitly demoted to a separate subsection.

````markdown
## 3. 运行前准备

### 3.1 发布版用户

如果你使用的是发布页面提供的打包版本，启动前只需要确认：

- 有一个可访问的 `alist-tvbox` 后端
- 当前网络环境能访问你要使用的内容来源
- 如果要直接播放 `YouTube` 等页面链接，系统里已经单独安装可用的 `yt-dlp`

`yt-dlp` 不随 `atv-player` 一起打包。常见安装方式：

- macOS：`brew install yt-dlp`
- Windows：`winget install yt-dlp.yt-dlp`
- Linux / 通用 Python 环境：`pipx install yt-dlp`
- 如果你已经有 Python 环境，也可以使用：`python -m pip install -U yt-dlp`

安装后建议先在终端确认：

```bash
yt-dlp --version
```

如果这条命令不能执行，应用通常也无法直接播放 `YouTube` 页面链接。

### 3.2 从源码运行

如果你是开发者，或希望从源码运行 / 自行打包，再按下面准备：

- 安装 Python `3.12+`
- 安装 `uv`
- 系统中存在可用的 `libmpv`

Linux 上推荐先验证以下两步：

```bash
uv sync --group dev
./start.sh
```

`start.sh` 实际执行：

```bash
uv run src/atv_player/main.py
```

如果启动时报错找不到 `libmpv`，优先先解决系统运行库问题，再继续排查应用本身。
````

- [ ] **Step 3: Adjust the next chapter numbers and keep the login flow intact**

Renumber the existing `登录与启动` chapter from `## 3` to `## 4` and keep the body focused on the app’s login behavior instead of install/setup prerequisites.

```markdown
## 4. 登录与启动

启动应用后会先进入登录页：

- 后端地址默认值是 `http://127.0.0.1:4567`
- 应用会自动回填上次使用的后端地址和用户名
- 登录成功后会自动获取并缓存 `vod token`
- 应用不会保存密码
```

- [ ] **Step 4: Verify the new front section headings**

Run: `rg -n "^## " docs/help.md | head -n 8`

Expected:

- `## 1. 应用定位`
- `## 2. 快速开始（3 分钟）`
- `## 3. 运行前准备`
- `## 4. 登录与启动`

- [ ] **Step 5: Commit the release-user opening slice**

```bash
git add docs/help.md
git commit -m "docs: reframe help doc for release users"
```

### Task 2: Refine Main-Flow Wording And Settings Guidance

**Files:**
- Modify: `docs/help.md`
- Review: `docs/help.md`

- [ ] **Step 1: Renumber main operation chapters after the new opening**

Update the top-level headings that follow the new front matter so the operational flow becomes:

```markdown
## 5. 主窗口总览
## 6. 各页面如何使用
## 7. 播放器窗口
## 8. 网络直播
## 9. 插件管理
## 10. 高级设置
```

Keep the existing subsection bodies unless wording needs to change for the release-user framing.

- [ ] **Step 2: Tighten the `yt-dlp` wording inside the main-window section**

Keep the existing direct-open and troubleshooting coverage, but add the packaged-app framing so users do not confuse `yt-dlp` with an app-bundled component.

```markdown
### 5.3 `yt-dlp` 与 `YouTube` 播放

当你输入 `YouTube`、`X/Twitter`、`Instagram`、`TikTok` 这类页面链接时，应用可能会调用系统中单独安装的 `yt-dlp` 提取可播放地址、标题、封面、字幕和清晰度信息。

请注意：`yt-dlp` 是外部工具，不随 `atv-player` 的发行包一起提供。安装了 `yt-dlp` 也不代表所有页面都一定能播放，结果仍受站点限制、账号状态、地区限制和网络环境影响。
```

Use the actual subsection number that results after renumbering the chapter.

- [ ] **Step 3: Add a normal-user recommendation block under playback settings**

Extend the `播放设置` subsection with guidance that matches the current defaults instead of introducing alternate numbers.

```markdown
普通用户建议：

- **播放缓存大小**：默认 `512 MB`，通常保持默认即可
- **解码模式**：优先使用硬件解码
- **网络超时**：一般保持默认或按网络情况小幅调整
- **普通流预读时长**：默认 `20` 秒，通常保持默认即可
- 只有在播放卡顿、超时或兼容性异常时，再逐项调整
```

- [ ] **Step 4: Verify the settings section contains the default-aligned recommendation block**

Run: `rg -n "普通用户建议|512 MB|20 秒" docs/help.md`

Expected:

- A `普通用户建议` block exists in the `播放设置` subsection.
- The only explicit recommendation numbers are `512 MB` and `20 秒`.

- [ ] **Step 5: Commit the wording and settings slice**

```bash
git add docs/help.md
git commit -m "docs: refine playback help wording"
```

### Task 3: Add The Capability Reference Chapters

**Files:**
- Modify: `docs/help.md`
- Review: `docs/help.md`

- [ ] **Step 1: Insert the support matrix chapter after advanced settings**

Add a new top-level chapter immediately after `高级设置` that consolidates supported sources and protocols into grouped lists.

```markdown
## 11. 支持的内容来源与协议

应用支持的内容来源和协议大致可以分为以下几类：

### 11.1 视频网站

- `YouTube`
- B站
- 腾讯视频
- 爱奇艺
- 优酷
- 芒果 TV

### 11.2 媒体服务器

- `Emby`
- `Jellyfin`

### 11.3 网盘与分享链接

- 百度网盘
- 阿里云盘
- 夸克网盘
- `PikPak`
- 常见网盘分享链接

### 11.4 本地与远程媒体

- 普通 `HTTP/HTTPS` 媒体地址
- `M3U8`
- 远程蓝光 `ISO`

### 11.5 协议与格式

- `HLS`
- `DASH`
- `magnet:?`
- `ed2k://`
- 外挂字幕
- `QRC / KRC / YRC`

实际可用性取决于当前后端能力、插件、网络环境和第三方站点状态。
```

- [ ] **Step 2: Insert the capability dependency chapter**

Add a new chapter after the support matrix that explains which features are local, backend-driven, or external.

```markdown
## 12. 功能依赖关系

### 12.1 仅本地播放器能力

- `mpv` 播放
- 主字幕 / 次字幕
- 弹幕搜索、切换、渲染和缓存
- 元数据刮削与展示
- 本地 HLS 代理
- 远程蓝光 `ISO` 流式读取
- 播放设置、日志、海报与本地缓存管理

### 12.2 依赖 `alist-tvbox` 后端

- 登录
- 文件浏览
- 播放记录
- 网盘解析
- 离线下载
- 由后端能力驱动的标签页和媒体浏览

### 12.3 依赖外部工具或外部环境

- `yt-dlp`
- 代理网络
- 浏览器 Cookie
- TMDB / Bangumi / 豆瓣等第三方服务配置
- 远程插件及其自身可用性
```

- [ ] **Step 3: Insert the player technical features chapter**

Add a user-facing summary of advanced playback capabilities after the dependency chapter.

```markdown
## 13. 播放器技术特性

- **`mpv` 硬件解码**：优先使用系统可用的硬件解码能力，降低 CPU 压力。
- **`DASH` 多清晰度切换**：对支持的内容显示可选清晰度和相关编码信息。
- **多线路与自动切线**：同一内容支持多条线路，必要时可手动切换或自动切换。
- **本地 HLS 代理与分片缓存**：重写 `M3U8`、过滤广告片段并缓存分片，减少重复请求。
- **远程蓝光 `ISO` 流式读取**：通过 HTTP range 请求直接读取远程蓝光镜像内容。
- **`ASS` 弹幕渲染**：把弹幕转换为可控样式的 `ASS` 覆盖层。
- **主字幕 / 次字幕双轨**：支持同时管理主字幕和次字幕。
- **`yt-dlp` 页面提取**：可直接从受支持站点页面链接提取播放地址和元数据。
- **卡拉 OK 歌词渲染**：支持 `QRC`、`KRC`、`YRC` 逐字歌词显示。
- **播放恢复**：尽量恢复上次观看位置和相关播放状态。
```

- [ ] **Step 4: Verify the new reference chapters exist in order**

Run: `rg -n "^## (11|12|13)\\." docs/help.md`

Expected:

- `## 11. 支持的内容来源与协议`
- `## 12. 功能依赖关系`
- `## 13. 播放器技术特性`

- [ ] **Step 5: Commit the capability reference slice**

```bash
git add docs/help.md
git commit -m "docs: add help capability reference chapters"
```

### Task 4: Expand Local Data Guidance And Unify Terminology

**Files:**
- Modify: `docs/help.md`
- Review: `docs/help.md`

- [ ] **Step 1: Rewrite the local data chapter into data, cache, reset, and migration guidance**

Replace the current `本地保存的数据` chapter with a broader chapter that keeps the directory list but adds reset and migration instructions.

````markdown
## 14. 本地数据、缓存与迁移

### 14.1 数据目录

应用会把状态写到 `Qt` 标准数据目录和缓存目录。Linux 上通常是：

```text
~/.local/share/atv-player
~/.cache/atv-player
```

不同平台的实际路径可能不同，但应用使用的是 Qt 标准目录。

### 14.2 会保存什么

- 登录状态和 `vod token`
- 插件配置与缓存
- 直播源和 EPG 配置
- 播放历史与恢复信息
- 元数据绑定记录
- 弹幕偏好
- 主题、代理和播放设置

### 14.3 缓存机制

应用会缓存以下内容，以减少重复请求并提升加载速度：

- 海报
- 插件缓存
- 弹幕搜索结果
- 弹幕 XML / ASS
- 元数据结果
- HLS / TS 分片

### 14.4 重置应用

如果你希望恢复初始状态，可删除以下目录：

```text
~/.local/share/atv-player
~/.cache/atv-player
```

### 14.5 迁移到新电脑

如果你希望尽量保留登录状态、插件、直播源、播放历史、元数据绑定和偏好设置，可复制以下目录到新环境：

```text
~/.local/share/atv-player
~/.cache/atv-player
```
````

- [ ] **Step 2: Add a terminology chapter before shortcuts**

Insert a short, stable terminology table before the shortcut chapter so the rest of the document can use the same words consistently.

```markdown
## 15. 术语约定

| 术语 | 含义 |
|------|------|
| `来源` | 一个内容提供方或插件 / 网站入口 |
| `来源分组` | 同一内容下按版本、语言或内容类型划分的大组 |
| `线路` | 同一内容的不同播放源 |
| `剧集` | 具体播放项，例如 `EP01`、`第 3 集` |
| `解析器` | 把待解析地址转换成最终可播地址的内置解析方式 |
| `播放项` | 列表中可直接点播的具体条目 |
```

- [ ] **Step 3: Renumber the shortcut and FAQ chapters and normalize mixed terminology**

Update the final top-level chapter numbers and replace obvious mixed wording where it conflicts with the new terminology chapter.

```markdown
## 16. 快捷键总表
## 17. 常见问题与排障
```

Examples of wording updates to apply where needed:

```markdown
- 在详情页选择剧集、线路或播放项进入播放器。
- 有多组来源时可先切换来源分组，再切换线路。
- 有些播放项不是最终媒体地址，而是待解析地址。此时播放器会启用“解析”下拉框。
```

- [ ] **Step 4: Verify the back-half chapter order and terminology chapter**

Run: `rg -n "^## (14|15|16|17)\\." docs/help.md`

Expected:

- `## 14. 本地数据、缓存与迁移`
- `## 15. 术语约定`
- `## 16. 快捷键总表`
- `## 17. 常见问题与排障`

- [ ] **Step 5: Commit the data and terminology slice**

```bash
git add docs/help.md
git commit -m "docs: expand help data and terminology guidance"
```

### Task 5: Run A Full Document Consistency Pass

**Files:**
- Modify: `docs/help.md`
- Review: `docs/help.md`

- [ ] **Step 1: Scan for stale numbering and source-first wording**

Run:

```bash
rg -n "^## |^### " docs/help.md
```

Expected:

- Top-level chapters run cleanly from `## 1.` through `## 17.`
- Subsections under the renumbered chapters use matching prefixes.

- [ ] **Step 2: Read the full document and fix wording collisions inline**

Perform a full read-through and patch any leftover wording that contradicts the new release-user framing, especially:

```markdown
- 任何把发行版用户默认指向 Python / `uv` 安装的句子
- 任何把 `yt-dlp` 写成随应用打包的句子
- 任何把支持范围写成绝对承诺的句子
- 任何仍把“来源 / 线路 / 播放项 / 解析器”混用到难以理解的句子
```

- [ ] **Step 3: Verify the final diff for structure and whitespace issues**

Run:

```bash
git diff -- docs/help.md
git diff --check -- docs/help.md
```

Expected:

- The diff only touches `docs/help.md`
- No trailing whitespace or malformed patch warnings are reported

- [ ] **Step 4: Commit the final polish pass**

```bash
git add docs/help.md
git commit -m "docs: polish release-user help manual"
```
