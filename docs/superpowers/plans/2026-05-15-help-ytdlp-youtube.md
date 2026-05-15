# Help Doc yt-dlp / YouTube Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `docs/help.md` so end users can install `yt-dlp`, understand when the app uses it, and know what conditions must be met to play YouTube videos.

**Architecture:** Keep all content changes inside `docs/help.md`. Add a small prerequisite note in the startup section, clarify the `yt-dlp` route in global search, and add one dedicated `yt-dlp` / `YouTube` help subsection with compact troubleshooting.

**Tech Stack:** Markdown documentation

---

## File Structure

- Modify: `docs/help.md`
  Responsibility: hold all user-facing `yt-dlp` / `YouTube` installation, usage, and troubleshooting guidance.

### Task 1: Add `yt-dlp` Prerequisites and Direct-Open Routing Notes

**Files:**
- Modify: `docs/help.md`

- [ ] **Step 1: Insert the prerequisite bullet and install commands**

In the `## 2. 运行前准备` section of `docs/help.md`, change the prerequisite bullet list and startup note to this form:

```md
启动前需要满足以下条件：

- 安装 Python `3.12+`
- 安装 `uv`
- 系统中存在可用的 `libmpv`
- 如果要播放 `YouTube` 等页面链接，系统中还需要可用的 `yt-dlp`
- 有一个可访问的 `alist-tvbox` 后端
```

Then add this block right after the existing `start.sh` snippet and before the `libmpv` troubleshooting sentence:

```md
如果你希望在应用里直接打开 `YouTube` 等页面链接，建议先确认系统里已经安装 `yt-dlp`。

常见安装方式：

- macOS：`brew install yt-dlp`
- Windows：`winget install yt-dlp.yt-dlp`
- Linux / 通用 Python 环境：`pipx install yt-dlp`
- 如果你已经有 Python 环境，也可以使用：`python -m pip install -U yt-dlp`

安装后建议先在终端确认：

```bash
yt-dlp --version
```

如果这条命令不能执行，应用通常也无法直接播放 `YouTube` 页面链接。
```

- [ ] **Step 2: Add the global-search direct-open routing note**

In the `### 4.2 全局搜索` section of `docs/help.md`, replace the current three `直接打开` bullets:

```md
- 输入 `magnet:?` 或 `ed2k://`：进入离线下载打开流程
- 输入常见网盘分享链接：进入网盘详情/解析流程
- 输入普通 `HTTP/HTTPS` 媒体或页面地址：走内置全局解析并直接拉起播放器
```

with:

```md
- 输入 `magnet:?` 或 `ed2k://`：进入离线下载打开流程
- 输入常见网盘分享链接：进入网盘详情/解析流程
- 输入 `YouTube` 页面链接：如果系统里有可用的 `yt-dlp`，应用会尝试直接拉起播放器
- 输入普通 `HTTP/HTTPS` 媒体或页面地址：走内置全局解析并直接拉起播放器
```

Then append this paragraph after the existing `内置解析` warning:

```md
也就是说，`YouTube` 这类页面地址不需要你先手动转换成直链媒体文件；只要系统里能找到可用的 `yt-dlp`，应用会优先尝试走 `yt-dlp` 打开。
```

- [ ] **Step 3: Verify the changed sections read correctly**

Run:

```bash
sed -n '1,120p' docs/help.md
```

Expected: the prerequisites list mentions `yt-dlp`, install commands are present, and the global-search section explicitly mentions `YouTube` page links

- [ ] **Step 4: Commit the first documentation block**

Run:

```bash
git add docs/help.md
git commit -m "docs: add yt-dlp prerequisites to help"
```

### Task 2: Add a Dedicated `yt-dlp` / `YouTube` Help Section

**Files:**
- Modify: `docs/help.md`

- [ ] **Step 1: Insert the dedicated section after global search**

In `docs/help.md`, insert this new section between `### 4.2 全局搜索` and `### 4.3 快捷键帮助`:

```md
### 4.3 `yt-dlp` 与 `YouTube` 播放

当你输入 `YouTube`、`X/Twitter`、`Instagram`、`TikTok` 这类页面链接时，应用可能会调用 `yt-dlp` 提取可播放地址、标题、封面、字幕和清晰度信息。

如果你主要关心 `YouTube` 播放，至少先确认下面几件事：

1. 终端里执行 `yt-dlp --version` 能成功返回版本号。
2. 当前网络环境能访问 `YouTube`。
3. 你输入的是有效的 `YouTube` 页面链接，例如 `https://www.youtube.com/watch?v=...`。
4. 某些视频如果受地区、年龄或登录状态限制，可能还需要浏览器 Cookie 或更合适的网络环境。

请注意：安装了 `yt-dlp` 不代表所有 `YouTube` 视频都一定能播放。站点限制、账号限制、地区限制和网络环境都会影响结果。

常见排查顺序：

- 如果应用提示 `yt-dlp 未安装`：先在终端执行 `yt-dlp --version`，确认命令本身是否存在。
- 如果终端里能运行 `yt-dlp`，但应用里仍提示未安装：确认启动应用和安装 `yt-dlp` 使用的是同一个系统环境或 PATH。
- 如果提示地区限制：通常不是应用本身问题，优先检查网络环境，必要时补充浏览器 Cookie。
- 如果能看到详情但无法起播：先确认视频链接本身有效，再检查网络环境和站点限制。
- 如果清晰度或字幕数量和网页看到的不一致：这通常取决于 `yt-dlp` 当次提取到的结果，并不一定表示应用异常。
```

- [ ] **Step 2: Adjust following subsection numbering**

Because the new block takes `### 4.3`, rename the next heading in `docs/help.md` from:

```md
### 4.3 快捷键帮助
```

to:

```md
### 4.4 快捷键帮助
```

Do not renumber unrelated top-level sections.

- [ ] **Step 3: Verify the inserted help section**

Run:

```bash
sed -n '40,130p' docs/help.md
```

Expected: the new `yt-dlp` / `YouTube` section appears between global search and shortcut help, and the shortcut help heading is now `### 4.4`

- [ ] **Step 4: Commit the dedicated help section**

Run:

```bash
git add docs/help.md
git commit -m "docs: add yt-dlp youtube help section"
```

### Task 3: Review the Full Help Doc for Clarity and Scope

**Files:**
- Modify: `docs/help.md`

- [ ] **Step 1: Perform a terminology cleanup pass**

Open `docs/help.md` and make sure the new content only uses user-facing terms. Specifically, keep these concepts:

```text
页面链接
安装
PATH
网络环境
Cookie
地区限制
```

Do not introduce internal terms such as:

```text
YtdlpPlaybackService
playback_loader
session.vod
缓存键
插件控制器
```

If any internal wording slipped in, replace it with end-user language directly in `docs/help.md`.

- [ ] **Step 2: Run a focused placeholder and terminology scan**

Run:

```bash
rg -n "TODO|TBD|YtdlpPlaybackService|playback_loader|session\\.vod|缓存键|插件控制器" docs/help.md
```

Expected: no matches

- [ ] **Step 3: Read the final full document slice**

Run:

```bash
sed -n '1,160p' docs/help.md
```

Expected: the startup prerequisites, global-search behavior, and dedicated `yt-dlp` / `YouTube` section read as one coherent user guide

- [ ] **Step 4: Commit the final wording pass**

Run:

```bash
git add docs/help.md
git commit -m "docs: polish yt-dlp youtube help wording"
```

## Self-Review

- Spec coverage:
  - Startup prerequisites and install commands: Task 1
  - Global-search routing explanation: Task 1
  - Dedicated `yt-dlp` / `YouTube` section: Task 2
  - User-facing troubleshooting and no internal implementation detail: Task 3
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every editing step includes exact text to insert or replace
  - Every verification step includes an exact command and expected result
- Type consistency:
  - Only `docs/help.md` is modified throughout the plan
  - Section numbering is updated consistently from `4.3` to `4.4`
