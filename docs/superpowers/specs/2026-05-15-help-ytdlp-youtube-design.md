# Help Doc yt-dlp / YouTube Design

## Summary

更新 `docs/help.md`，补充终端用户视角下的 `yt-dlp` 安装说明，以及“想在 `atv-player` 里播放 YouTube 视频，需要满足哪些条件”的操作指引和排障说明。

本次只修改帮助文档，不改 `README.md`、UI 文案或程序行为。

## Goals

- 让用户知道 `yt-dlp` 是播放 YouTube 等站点页面链接的前置条件之一。
- 让用户能按系统平台快速完成 `yt-dlp` 安装，并用简单命令确认安装成功。
- 让用户理解在应用里什么场景会走 `yt-dlp`，而不是误以为只能播放直链媒体文件。
- 提供简洁可执行的排障顺序，回答“为什么装了还不能播”。

## Non-Goals

- 不把 `docs/help.md` 写成完整的 `yt-dlp` 官方安装手册。
- 不加入内部实现细节，如类名、函数名、缓存或会话同步逻辑。
- 不新增对话框、帮助按钮、快捷键或 UI 内嵌帮助入口。
- 不修改 `README.md`、`help_dialog.py` 或其他文档文件。

## Scope

主要改动：

- `docs/help.md`

本次不涉及代码测试，验证重点是文档内容和结构是否清晰、准确、可执行。

## Current Problem

当前 `docs/help.md` 已经说明了 Python、`uv`、`libmpv` 和后端准备，但没有明确告诉用户：

- 播放 YouTube 等页面链接时还需要系统可用的 `yt-dlp`
- 应用在什么场景下会调用 `yt-dlp`
- 如何确认 `yt-dlp` 真正安装到了当前系统 PATH
- 安装了 `yt-dlp` 之后，为什么某些 YouTube 视频仍然可能不能播放

结果是用户即使装好了应用，也容易卡在“输入了 YouTube 链接却打不开”的状态，并且不知道应该从安装、网络、链接类型还是站点限制开始排查。

## Approach Options

### Option A: Only add one sentence in prerequisites

只在“运行前准备”里补一条“需要安装 `yt-dlp`”。

优点：

- 改动最小。

缺点：

- 不能回答“怎么安装”“装好后怎么确认”“为什么还是不能播”。
- 用户遇到问题时仍然要自己猜测原因。

### Option B: Scatter notes into multiple existing sections

分别在“运行前准备”“全局搜索”“排障”里各补几句 `yt-dlp` 相关说明。

优点：

- 能贴近现有文档结构。

缺点：

- 信息分散，用户要来回翻。
- 很难形成一段完整的 YouTube 播放说明。

### Option C: Add a dedicated `yt-dlp` / YouTube help section and small cross-references

在“运行前准备”补前置条件，在“直接打开”相关位置补一句路由说明，并新增一个独立小节集中说明 `yt-dlp` 安装、用途、成功条件和常见失败原因。

优点：

- 最容易被终端用户理解和检索。
- 既保留前置条件提醒，也提供专题化排障说明。
- 不需要改 UI，只靠现有帮助文档就能回答大部分问题。

缺点：

- 文档会增加一个专题小节。

## Decision

采用 **Option C**。

原因：

- 它兼顾“首次安装前看到要求”和“遇到问题时快速查到答案”两种使用场景。
- 对现有文档结构侵入小，但信息组织最清晰。
- 最符合这次目标：回答“怎么安装 `yt-dlp`，怎么才能播放 YouTube 视频”。

## Design

### 1. Update prerequisites section

在 `docs/help.md` 的“运行前准备”里新增一条前置条件：

- 如果要播放 YouTube 或其他依赖页面解析的站点链接，系统里还需要可用的 `yt-dlp`

这部分只写最短安装和确认方式，不展开高级配置。

建议覆盖：

- macOS：`brew install yt-dlp`
- Windows：`winget install yt-dlp.yt-dlp`
- Linux / 通用 Python 环境：`pipx install yt-dlp` 或 `python -m pip install -U yt-dlp`
- 安装确认：`yt-dlp --version`

### 2. Clarify when the app uses `yt-dlp`

在“全局搜索”中“直接打开”相关段落补一句明确说明：

- 输入 `YouTube` 页面链接时，应用会尝试走 `yt-dlp` 打开

重点是让用户知道：

- 不需要先手动把 YouTube 转成 `mp4` 直链
- 应用识别的是页面链接，不只是媒体文件 URL

### 3. Add a dedicated `yt-dlp` / YouTube section

新增一个独立小节，标题可以是：

- `yt-dlp` 与 `YouTube` 播放

这个小节集中回答四类问题：

1. 应用什么时候会调用 `yt-dlp`
2. 如何确认系统安装正确
3. 想正常播放 YouTube 至少需要满足什么条件
4. 常见失败现象应该怎么排查

### 4. Keep the playback requirements user-facing

“怎么才能播放 YouTube 视频”这部分应写成可执行的检查项，而不是程序内部术语。

至少包括：

- 系统 PATH 里能找到 `yt-dlp`
- 当前网络环境能访问 YouTube
- 输入的是有效的 YouTube 页面链接
- 某些受地区、年龄、登录状态限制的视频，可能还需要浏览器 Cookie 或合适网络环境

这里应明确写“安装好 `yt-dlp` 不代表所有 YouTube 视频都一定能播放”，避免用户把所有失败都归因到应用本身。

### 5. Keep troubleshooting compact and practical

排障部分使用“现象 -> 原因 -> 建议动作”的结构，避免写成大篇幅说明书。

建议覆盖这些常见现象：

- 提示 `yt-dlp 未安装`
- 提示地区限制
- 有详情但无法起播
- 清晰度或字幕数量与网页看到的不一致

每项只给 1 到 3 条用户可执行动作，例如：

- 先运行 `yt-dlp --version`
- 确认终端里 `yt-dlp` 和启动应用使用的是同一个环境
- 更换网络环境或补充浏览器 Cookie

### 6. Avoid deep implementation details

文档里不应出现：

- `YtdlpPlaybackService`
- `playback_loader`
- `session.vod`
- 解析缓存
- 插件控制器

用户文档只保留对实际使用有帮助的概念：

- 页面链接
- 安装
- PATH
- 网络环境
- Cookie
- 地区限制

## Result

完成后，`docs/help.md` 会明确告诉用户：

- 为什么播放 YouTube 需要 `yt-dlp`
- 怎么在常见平台安装 `yt-dlp`
- 怎么确认安装成功
- 在应用里什么输入会走 `yt-dlp`
- 如果还不能播，应该先检查什么
