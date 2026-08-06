# 弹幕在 file-loaded 后重新挂载设计

## 背景

播放条目已经取得 `danmaku_xml` 时，`PlayerWindow` 会在向 mpv 发出媒体加载命令后立即异步生成 ASS，并通过 `sub-add` 挂载弹幕。mpv 的加载命令返回不代表新媒体已经触发 `file-loaded`；新媒体随后完成切换时会清除提前添加的外挂字幕轨道。

这会导致弹幕 XML、ASS 和轨道 ID 均成功产生，却没有弹幕显示，也没有“弹幕加载失败”日志。自动切集的 hydrate-only 路径会进一步放大该时序：它可能在新视频开始加载之前，将下一集弹幕挂载到旧媒体。

## 目标

- 真实 `MpvWidget` 播放每个新媒体时，在对应的 `file-loaded` 到达后重新配置当前条目的弹幕。
- 快速切集或过期回调不得把旧条目的弹幕挂到新条目。
- 保留现有即时应用暂停、倍速、音量和静音的行为。
- 不恢复曾导致 Windows 播放崩溃的“全部播放器配置等待 file-loaded”行为。
- 不改变使用测试替身或其他非 `MpvWidget` 视频对象时的同步弹幕配置行为。

## 方案

### 播放请求关联

`PlayerWindow` 增加一个仅用于弹幕的待加载条目引用。使用真实 `video_widget` 开始播放时，在调用 `_video_load()` 之前记录本次 `PlayItem`；加载命令抛出异常时清除此引用。

### file-loaded 处理

`_handle_video_file_loaded()` 保留现有 YouTube 元数据刷新与通用 post-load 逻辑。除此之外，它取得并清除待加载弹幕条目，并且仅在以下条件都满足时重新调用 `_configure_danmaku_for_current_item()`：

- session 仍存在；
- 当前索引有效；
- 当前 playlist 中的对象与记录的 `PlayItem` 是同一个对象；
- 该次回调没有已经通过 `_apply_post_load_player_configuration()` 配置过同一条目。

对象身份检查沿用现有异步回调的防陈旧模式。清除待处理引用后再配置，确保同一个 `file-loaded` 不会重复消费。

### 保留即时配置

`_should_defer_post_load_player_configuration()` 继续返回 `False`。`_start_current_item_playback()` 仍会立即应用暂停、倍速、音量、静音以及当前已有的弹幕配置。即时弹幕配置可以保留现有交互速度；真实 `file-loaded` 后的第二次配置负责恢复被 mpv 媒体替换清除的轨道。

异步 ASS 渲染已有 request ID 和当前条目身份校验。后一次配置会使较早的渲染结果失效，因此无需新增线程同步机制。

## 错误处理

- 媒体加载命令失败时清除待加载弹幕条目，防止之后无关的 `file-loaded` 消费它。
- session 或当前条目已变化时静默丢弃过期回调。
- file-loaded 后弹幕渲染或 `sub-add` 失败，继续使用现有重试和“弹幕加载失败”日志路径。

## 测试

新增 PlayerWindow 回归测试，验证：

1. 使用真实 `video_widget` 开始播放时，弹幕会先按现有行为配置一次；模拟 `file-loaded` 后，会针对同一条目再次配置。
2. 在 `file-loaded` 前切换 session 当前条目时，不会为过期条目重新配置弹幕。
3. `_video_load()` 抛出异常后，不保留待加载弹幕引用。
4. 既有默认启用、保存关闭偏好、hydrate-only 刷新和 Windows 即时配置测试继续通过。

## 非目标

- 不重构字幕、音轨或视频清晰度的整体 post-load 生命周期。
- 不改变弹幕获取、缓存、ASS 渲染格式或弹幕偏好语义。
- 不为成功挂载新增用户可见日志；诊断日志可在后续可观测性工作中单独设计。
