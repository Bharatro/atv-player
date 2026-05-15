# yt-dlp Detail Writeback Design

## Summary

所有走 `yt-dlp` 的播放入口，在解析出 YouTube 等站点的详情后，都要把结果统一写回当前视频详情，而不只是更新播放 URL。回写策略以 `yt-dlp` 结果为准，直接覆盖当前会话中的标题、封面、简介，以及当前播放项的运行时播放元数据。

## Goals

- 统一所有 `yt-dlp` 入口的详情回写行为。
- 让播放器标题、详情面板、封面、历史记录来源名称与 `yt-dlp` 解析结果保持一致。
- 消除 `MainWindow`、插件控制器、解析回退路径之间各自维护字段赋值逻辑的分叉。

## Non-Goals

- 不新增 YouTube 专用控制器或专用详情模型。
- 不扩展回写到 `vod_year`、`vod_actor`、`vod_director` 等当前未稳定消费的字段。
- 不修改 `yt-dlp` 失败时的现有报错和回退策略。
- 不引入新的播放状态机或新的详情刷新通道。

## Scope

主要改动：

- `src/atv_player/yt_dlp_service.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/plugins/controller.py`

主要验证：

- `tests/test_main_window_ui.py`
- `tests/test_spider_plugin_controller.py`
- `tests/test_yt_dlp_service.py`

## Current Problem

当前仓库里只有部分 `yt-dlp` 播放路径会回写视频详情：

- `MainWindow` 的 `ytdlp` 直连入口会更新 `session.vod.vod_name`、`vod_pic`、`vod_content`
- 插件播放链路里的 `_maybe_hydrate_ytdlp_item()` 只更新 `PlayItem`
- 解析失败后回退到 `yt-dlp` 的路径也有单独维护的字段赋值

这导致同样是 YouTube 链接，不同入口进入播放器后，看到的标题、封面、简介并不一致。有些入口只拿到了可播地址，但详情面板仍停留在旧的插件详情或占位信息。

## Approach Options

### Option A: Patch each entry independently

分别在 `MainWindow`、插件控制器、解析回退路径里手工补齐相同字段赋值。

优点：

- 改动直接。

缺点：

- 同一套字段覆盖规则会继续分散在多个入口。
- 后续新增字段或调整覆盖策略时容易漏改。

### Option B: Add a shared yt-dlp result applicator

抽出统一的 `yt-dlp` 结果应用助手，把 `YtdlpResolveResult` 覆盖写入 `VodItem` 和 `PlayItem`，所有入口都调这一处。

优点：

- 覆盖规则集中，和“所有入口统一行为”的目标一致。
- 可以复用到同步入口、异步 loader 和插件播放链路。
- 后续新增稳定字段时只需改一处。

缺点：

- 需要整理现有入口的手工赋值代码。

### Option C: Force all callers to rebuild request from `resolve_to_play_item()`

让所有调用方都放弃本地会话对象，拿 `yt-dlp` 返回的新 `VodItem` / `PlayItem` 重新构建请求。

优点：

- 数据来源最统一。

缺点：

- 对现有会话和异步加载链路侵入过大。
- 容易影响历史记录、当前播放项切换和会话内刷新逻辑。

## Decision

采用 **Option B**。

原因：

- 它能在不重构播放会话模型的前提下统一所有 `yt-dlp` 入口。
- 详情对象和播放项对象继续原地更新，兼容现有 `session`、占位详情和异步加载模型。
- 风险和改动范围都明显小于整条链路重建请求对象。

## Design

### 1. Shared writeback helper

在 `src/atv_player/yt_dlp_service.py` 增加统一助手，用于把 `YtdlpResolveResult` 覆盖写回已有 `VodItem` 和 `PlayItem`。

该助手负责两类字段：

- `VodItem` 详情字段
- `PlayItem` 运行时播放字段

这样所有入口都复用同一套覆盖规则，而不是各自手写字段同步。

### 2. `VodItem` overwrite rules

`VodItem` 只覆盖当前已经稳定展示和消费的三个字段：

- `vod_name`
- `vod_pic`
- `vod_content`

覆盖规则不是“仅空值填充”，而是按本次需求直接以 `yt-dlp` 结果为准。也就是说：

- `yt-dlp` 有标题时，覆盖当前 `vod_name`
- `yt-dlp` 有封面时，覆盖当前 `vod_pic`
- `yt-dlp` 返回空简介时，也允许把 `vod_content` 覆盖为空字符串

`vod_id` 保持当前会话已有值，不因为 `yt-dlp` 详情刷新而改写。

### 3. `PlayItem` overwrite rules

`PlayItem` 作为运行时播放对象，始终按 `yt-dlp` 解析结果覆盖：

- `url`
- `original_url`
- `headers`
- `audio_url`
- `ytdl_format`
- `playback_qualities`
- `selected_playback_quality_id`
- `external_subtitles`
- `duration_seconds`
- `title`
- `media_title`

这些字段本来就是解析结果的一部分，不需要保留旧值优先级。

### 4. Main window entry alignment

`MainWindow` 中所有已经调用 `yt-dlp` 的入口都改为使用统一助手，而不是在本地分别赋值：

- `ytdlp` 直连播放入口
- 内置解析失败后回退到 `yt-dlp` 的入口

这样无论用户是直接输入 YouTube 链接，还是先走内置解析后回退到 `yt-dlp`，最终详情回写行为都一致。

### 5. Plugin playback alignment

插件播放链路中的 `_maybe_hydrate_ytdlp_item()` 需要从“只更新 `PlayItem`”扩展为“同时支持更新当前会话详情对象”。

行为要求：

- 当插件详情或播放项最终命中 `yt-dlp` 解析时，当前会话中的 `VodItem` 也要同步覆盖
- 更新必须落在当前正在使用的会话详情对象上，而不是只改局部临时变量

这样插件页进入的 YouTube 播放，也能和直链入口看到相同的标题、封面、简介。

### 6. Failure behavior

`yt-dlp` 失败时不新增新的吞错或降级规则：

- 原本该抛错的入口继续抛错
- 原本先走解析器、失败后再回退到 `yt-dlp` 的链路继续保留现有回退顺序

只有在拿到有效 `YtdlpResolveResult` 之后，才执行统一详情回写。

### 7. Testing

测试应覆盖以下场景：

- `MainWindow` 直连 `yt-dlp` 入口会覆盖 `session.vod.vod_name`、`vod_pic`、`vod_content`
- `MainWindow` 的解析回退到 `yt-dlp` 路径也会覆盖同样字段
- 插件详情返回 YouTube URL 时，播放加载后会同步覆盖当前会话详情对象
- 服务层已有 `resolve_to_play_item()` 行为继续保持，确保返回值和统一覆盖规则一致

## Result

完成后，所有最终走 `yt-dlp` 的播放入口都会按同一套规则，把解析得到的标题、封面、简介和播放元数据写回当前会话。用户不再因为入口不同而看到不同的 YouTube 详情内容。
