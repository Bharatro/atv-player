# 弹幕 hydrate-only 早于媒体播放修复设计

## 背景

播放条目已经有可用地址时，`PlayerWindow` 会并行启动两项工作：异步 playback loader 使用 hydrate-only 模式补充条目详情，媒体地址则进入播放前预处理。弹幕下载可能在媒体预处理完成前结束。

当前 hydrate-only 成功回调会无条件调用 `_configure_danmaku_for_current_item()`。如果媒体仍在预处理，新媒体尚未提交给 mpv，此时生成 ASS 并执行 `sub-add` 没有可挂载的媒体上下文。mpv 命令可能不报错，但 `track-list` 中不会出现新字幕轨道，最终记录“弹幕加载失败: 播放器未返回弹幕轨道”。

现有 `file-loaded` 重挂载只能恢复已经开始加载的媒体，无法阻止这次播放开始前的无效挂载和错误日志。

## 目标

- 当前条目仍在媒体预处理时，hydrate-only 成功回调不提前配置弹幕。
- 正式播放开始后继续通过现有即时配置和 `file-loaded` 重挂载加载弹幕。
- 已经播放且没有待处理媒体预处理时，hydrate-only 仍可立即刷新弹幕。
- 字幕、音轨、清晰度和详情 UI 的 hydrate-only 刷新行为保持不变。

## 方案

在 `_handle_playback_loader_succeeded()` 的 hydrate-only 分支中保留现有媒体控件刷新，只在当前条目没有待处理的 playback prepare 时调用 `_configure_danmaku_for_current_item()`。

待处理状态必须同时匹配当前播放索引。这样过期或其他条目的 prepare 状态不会阻止当前条目配置弹幕。

当匹配的 playback prepare 仍在进行时：

1. hydrate-only 回调更新详情、字幕、音轨和清晰度状态。
2. 跳过本次弹幕配置，不启动弹幕轮询，也不执行 `sub-add`。
3. playback prepare 完成后，`_start_current_item_playback()` 向 mpv 加载新媒体并沿现有 post-load 配置路径处理弹幕。
4. 对真实 `MpvWidget`，对应的 `file-loaded` 回调继续重新配置一次弹幕，避免媒体切换清除提前加入的轨道。

当没有匹配的 playback prepare 时，hydrate-only 分支保持现有立即配置行为，以支持已播放媒体的异步详情刷新。

## 错误处理

不新增重试、超时或用户可见日志。现有正式播放阶段的弹幕渲染、`sub-add` 重试和“弹幕加载失败”处理保持不变。

## 测试

新增回归测试，构造 hydrate-only 成功且当前索引存在匹配的 `_PendingPlaybackPrepare`：

- 断言缓存弹幕恢复、字幕、音轨和清晰度刷新仍执行。
- 断言 `_configure_danmaku_for_current_item()` 不执行。

保留现有 hydrate-only 测试，验证没有待处理 playback prepare 时仍立即配置弹幕。继续运行 `file-loaded` 重挂载测试，确认正式播放后的恢复路径不受影响。

## 非目标

- 不调整 mpv 的字幕轨道探测等待时间。
- 不改变普通字幕或音轨的加载时序。
- 不重构整体 playback loader、媒体预处理或 post-load 生命周期。
- 不处理日志中相隔约 19 秒的第二次同地址播放调用；该事件与首次弹幕轨道缺失没有因果关系。
