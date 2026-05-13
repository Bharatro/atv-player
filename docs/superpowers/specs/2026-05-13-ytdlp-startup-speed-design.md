# yt-dlp Startup Speed Design

## Summary

优化所有 `yt-dlp` 播放入口的启动路径，让播放器窗口先打开，再在窗口内异步执行 `yt-dlp` 解析与元数据补齐。目标是缩短“输入或点击 YouTube 链接 -> 播放器窗口出现并开始起播”的体感等待时间。

本次改动统一适用于所有最终走 `yt-dlp` 的入口，不只覆盖全局搜索框中的 YouTube 直链。

## Goals

- 点击或输入可由 `yt-dlp` 解析的链接后，播放器窗口应立即打开。
- `yt-dlp` 解析应在 `PlayerWindow` 内通过现有异步加载链路执行，而不是在 `MainWindow` 中阻塞开窗。
- 视频应在获取到最小可播信息后尽快起播。
- 标题、封面、时长、描述、字幕、清晰度等元数据允许在起播前后补齐。
- 同一链接短时间内重复打开时，应复用短时缓存结果，缩短 `解析中` 阶段。

## Non-Goals

- 不引入新的全局播放状态机。
- 不为 YouTube 或其他 `yt-dlp` 站点新增独立控制器或专用播放器窗口。
- 不做自动双解析竞速，不并发运行 `yt-dlp` 与内置解析器。
- 不在本次实现中加入预热、相邻视频预取或后台批量元数据抓取。
- 不做真实网络集成测试或首帧耗时基准测试。

## Scope

主要改动：

- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/yt_dlp_service.py`

主要验证：

- `tests/test_yt_dlp_service.py`
- `tests/test_player_window_ui.py`
- `tests/test_main_window_ui.py`

如果当前仓库中的主窗口入口测试文件不是 `tests/test_main_window_ui.py`，实现时应把对应用例放到已有的主窗口测试文件中，而不是新建重复测试模块。

## Current Problem

当前 `yt-dlp` 启动路径会在 `MainWindow` 内同步调用 `resolve_to_play_item()`，先等待 `yt-dlp` 完整返回播放地址和元数据，再构造 `OpenPlayerRequest` 并打开播放器。

这导致两个用户可感知问题：

- 播放器窗口出现过晚，用户在点击后缺少即时反馈。
- `yt-dlp` 的网络耗时、提取耗时和元数据组装耗时全部落在开窗前，直接拉长首播等待时间。

与之相比，现有异步 `playback_loader` 路径已经能够在播放器内展示 `准备中`、`解析中`、`连接中` 和失败恢复动作，但 `yt-dlp` 入口还没有接入这条链路。

## Approach Options

### Option A: Keep synchronous open and only tune `yt-dlp`

继续保留 `MainWindow` 同步解析，只调整 `yt-dlp` 参数、超时或提取字段。

优点：

- 改动最小。

缺点：

- 不能解决“窗口出现过晚”的核心问题。
- 与本次目标“先开窗再解析”不一致。

### Option B: Convert `yt-dlp` entry into placeholder request plus async loader

`MainWindow` 只构造最小占位 `OpenPlayerRequest`，把实际 `yt-dlp` 解析放到 `PlayerWindow` 的异步 `playback_loader` 中执行。

优点：

- 直接命中“先开窗、起播优先”的体验目标。
- 可以复用现有启动状态、失败动作和异步加载线程模型。
- 改动边界清晰，不需要重构整体播放器架构。

缺点：

- 需要补充 `yt-dlp` 结果回填逻辑。
- 需要确保异步结果不会污染用户已切换的播放项。

### Option C: Add a dedicated `yt-dlp` startup service

单独引入新的协调服务，统一处理 `yt-dlp` 的预热、解析和元数据同步。

优点：

- 长期扩展性更强。

缺点：

- 对当前目标来说过重。
- 会扩大本轮回归面。

## Decision

采用 **Option B**。

原因：

- 它是唯一直接满足“播放器窗口先出现”的方案。
- 它可以在现有 `playback_loader` 机制上增量实现。
- 它为后续继续优化 `yt-dlp` 重试、预热和缓存保留了演进空间，但不会在本轮过度设计。

## Design

### 1. Main Window request construction

`MainWindow` 中所有 `yt-dlp` 播放入口都改为构造占位请求，而不是同步解析完整播放结果。

占位请求要求：

- `vod` 使用最小占位数据，至少保留原始 URL 作为 `vod_id` 和可见标题兜底。
- `playlist` 仅包含一个 `PlayItem`。
- 初始 `PlayItem.url` 为空。
- `PlayItem.original_url` 保留原始链接。
- `source_mode` 继续使用 `ytdlp`。
- `playback_loader` 指向 `yt-dlp` 异步加载逻辑。
- `async_playback_loader` 设为 `True`。

这样 `MainWindow` 只负责判断“该链接应走 `yt-dlp` 路径”，不再承担真正的提取耗时。

### 2. Unified entry routing

所有最终走 `yt-dlp` 的入口都应统一走同一 builder 路径。

路由规则：

- 若 `yt-dlp` 可用且 `can_resolve(url)` 为真，则优先走 `yt-dlp` 占位请求。
- 若链接不属于 `yt-dlp` 识别站点，则保持现有内置解析或其他详情打开逻辑。
- 进入 `yt-dlp` 路径后，重试应继续走同一路径，不自动切换为内置解析。

这保证同类链接在不同入口下的行为一致，避免主窗口、搜索入口和重试入口分别走不同的解析时序。

### 3. Async `yt-dlp` playback loader

`playback_loader` 在线程中执行 `yt-dlp` 解析，并把结果原地回填到当前会话对象。

加载阶段行为：

1. `PlayerWindow` 打开后进入 `preparing`
2. 发现当前项 `url` 为空且存在异步 `playback_loader`
3. 进入 `resolving`
4. 后台线程执行 `yt-dlp` 解析
5. 成功后回填播放地址和元数据
6. 播放器继续进入 `connecting`
7. 连接成功后进入 `buffering`
8. 出首帧后进入 `playing`

`playback_loader` 至少需要回填：

- `PlayItem.url`
- `PlayItem.headers`
- `PlayItem.original_url`
- `PlayItem.playback_qualities`
- `PlayItem.external_subtitles`
- `PlayItem.duration_seconds`
- `PlayItem.media_title`
- `PlayItem.title`
- 默认 `selected_playback_quality_id`

同时需要更新 `session.vod` 中对应的：

- `vod_name`
- `vod_pic`
- `vod_content`
- `vod_id` 保持原始 URL

`yt-dlp` 返回结果到达后，`PlayerWindow` 应刷新：

- 窗口标题
- 详情封面
- 视频封面覆盖层
- 元数据面板
- 字幕状态
- 清晰度状态

### 4. Session-safe result application

异步结果只能回填到发起请求时仍然有效的当前项。

实现约束：

- 沿用现有 `request_id` 和 `_pending_playback_loader` 校验。
- 如果用户在结果返回前切换了播放项、切换了线路或当前会话已失效，则丢弃旧结果。
- 不能通过重新 `open_player()` 达到更新 UI 的目的，必须原地更新当前 session。

这样可以避免旧的 `yt-dlp` 结果覆盖用户已经切换到的新内容。

### 5. `yt-dlp` result cache

本次为 `yt-dlp` 增加短时解析结果缓存，缓存的是“起播所需最小结果 + 可延后展示元数据”。

缓存内容：

- 直连播放 URL
- 请求头
- 标题
- 封面
- 时长
- 描述
- 字幕列表
- 清晰度列表
- extractor

缓存键：

- `flag = "ytdlp"`
- 原始 URL
- `parser_key = "ytdlp"`

缓存 TTL：

- `300` 秒

缓存行为：

- 命中缓存时，异步 loader 应直接使用缓存结果，缩短 `解析中` 阶段。
- 过期后重新调用 `yt-dlp`。

实现上不应把现有仅服务于内置解析器的 `ResolveCacheValue` 直接扩展为混合用途结构。`yt-dlp` 结果应使用独立且语义清晰的缓存值类型，避免让内置解析器缓存承担额外复杂性。

### 6. Metadata timing

本次明确允许以下信息在起播前后补齐：

- 标题
- 封面
- 时长
- 描述
- 字幕列表
- 清晰度列表

窗口打开前不再要求这些字段全部就绪。原始 URL 占位信息足以支持先开窗和展示启动状态。

这次用户已明确接受“描述也可以延后”，因此不需要在开窗前强制等待完整详情。

### 7. Failure behavior

`yt-dlp` 失败后应继续走 `PlayerWindow` 内现有失败态展示，而不是在主窗口提前拦截为同步错误弹窗。

失败恢复行为：

- 默认动作保留 `重试`
- 如果当前项属于可换解析器场景，则继续允许 `换解析器`
- 如果存在多线路，则继续允许 `换线路`

本次不做自动静默降级：

- 不在一次点击中并发启动 `yt-dlp` 与内置解析
- 不在 `yt-dlp` 失败后自动回退到内置解析

用户应始终能明确当前正在使用哪条解析路径。

## Data Flow

### Successful path

1. 用户输入或点击可由 `yt-dlp` 解析的链接
2. `MainWindow` 构造占位 `OpenPlayerRequest`
3. `PlayerWindow` 立即打开
4. 当前项因 `url` 为空而触发异步 `playback_loader`
5. 状态区显示 `正在解析播放地址`
6. `yt-dlp` 解析返回
7. 播放地址和元数据回填到当前 session
8. 播放器开始连接并起播
9. UI 刷新标题、封面、描述、字幕和清晰度

### Failed path

1. 用户输入或点击可由 `yt-dlp` 解析的链接
2. `PlayerWindow` 打开并显示 `解析中`
3. `yt-dlp` 解析失败
4. 播放器进入 `failed`
5. 状态区展示失败文案与恢复动作
6. 日志记录失败原因

## Testing

### `tests/test_yt_dlp_service.py`

新增或调整测试覆盖：

- `yt-dlp` 结果缓存命中时不重复执行提取
- 缓存过期后重新提取
- 缓存结果包含播放地址、头信息和元数据

### `tests/test_player_window_ui.py`

新增或调整测试覆盖：

- `yt-dlp` 占位请求打开后，播放器先进入 `resolving`
- 异步 loader 成功后会启动实际播放
- 成功后会刷新标题、封面、元数据
- 成功后会刷新字幕和清晰度状态
- 异步 loader 失败后显示播放器内失败态
- 旧请求返回时不会污染已切换的当前播放项

### Main window entry tests

在现有主窗口测试文件中补充覆盖：

- `yt-dlp` 入口生成的是异步占位 `OpenPlayerRequest`
- 主窗口不再同步调用 `resolve_to_play_item()`
- 所有 `yt-dlp` 入口统一复用同一构造路径

### Explicitly out of scope for tests

- 不做真实 `yt-dlp` 网络访问
- 不做 YouTube 实站集成测试
- 不验证真实首帧时间数值

## Risks

- 如果回填逻辑只更新 `PlayItem` 而不更新 `session.vod`，UI 标题、封面和描述会不同步。
- 如果异步结果缺少 request/session 校验，旧结果可能覆盖用户已切换的播放项。
- 如果主窗口仍保留同步解析分支，不同入口会出现行为不一致。
- 如果缓存结构与内置解析缓存强耦合，后续维护会变得混乱。

## Acceptance

本次改动完成后，应满足以下结果：

- 可由 `yt-dlp` 解析的链接点击后，播放器窗口会立即打开。
- 用户能在播放器内看到 `解析中 -> 连接中 -> 缓冲中 -> 播放中` 的状态流转。
- `yt-dlp` 解析不再阻塞播放器窗口出现。
- 元数据可以在起播前后补齐，并正确刷新 UI。
- 同一链接在短时间内重复打开时，`解析中` 阶段明显缩短。
