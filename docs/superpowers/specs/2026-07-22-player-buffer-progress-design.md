# 播放器缓存进度显示设计

## 目标

在播放器进度条上显示「缓存进度」：以一段浅色区域表示当前播放位置之后已缓冲的播放时长（即 mpv 的 demuxer 缓存）。进度条形成三段——已播放（强调色）、已缓存（浅色）、未缓存（轨道色），不新增任何文字标签。

## 已确认需求

- 数据来源为 mpv 的 `demuxer-cache-duration` 属性（当前播放位置之后已缓冲的秒数），不接入 m3u8 代理预下载进度。
- 缓存段只在进度条上绘制，不显示数字或文字。
- 缓存段位于手柄右侧，表示「当前播放进度 + 缓存的播放时间」这个终点以内的区域。
- 不改变现有播放、seek、进度轮询的时序与频率。

## 方案选择

复用现有 `progress_timer` → `_sync_progress_slider` 轮询通道：在每次轮询中按需读取 `demuxer-cache-duration`，并交给 `ClickableSlider` 绘制缓存段。

未采用以下方案：

- 新增 `observe_property("demuxer-cache-duration")` 并发射独立信号：现有 `duration` 同样是按需读取、未 observe，轮询方式与之一致，且缓存时长本就随播放平滑变化，无需事件驱动。
- 在 m3u8 代理侧统计预下载进度：用户已确认只用 mpv demuxer 缓存。
- 单独加文字标签：用户已确认仅进度条缓存段。

## 组件与职责

### mpv_widget — 缓存时长读取

在 `MpvWidget` 新增 `demuxer_cache_duration_seconds() -> int`，完全复刻现有 `duration_seconds()` 的结构：

1. `_on_widget_thread()` 守卫，非控件线程时通过 `_run_on_widget_thread` 转发。
2. `_player is None` 时返回 0。
3. 经 `_player_property("demuxer-cache-duration", None)` 读取，再用 `_seconds_property_value()` 归一化（`None`、布尔、异常、负值一律返回 0）。

不修改属性观察注册，不新增信号。

### ClickableSlider — 缓存段绘制

在 `ClickableSlider` 增加缓存终点状态与绘制：

1. `__init__` 新增实例字段 `_buffer_value = 0`。
2. 新增 `set_buffer_value(value: int)`，钳制到 `[minimum(), maximum()]` 后写入 `_buffer_value` 并 `update()` 触发重绘。
3. `paintEvent` 在「绘制已播放 accent 段」**之前**插入缓存段：当控件启用且 `_buffer_value > self.value()` 时，计算缓存终点 x（复用现有 `progress = (v - min) / range` 与 `handle_diameter/2 + progress * available_width` 公式，把 `value` 换成 `_buffer_value`），用 `player_buffer` token 颜色绘制从 0 到缓存终点 x 的圆角矩形。
4. 随后按现有顺序绘制 accent 已播放段与手柄，保证 accent 在缓存段之上、手柄在最上。

z 序结果与设计稿一致：左→右为 已播放 / 已缓存 / 未缓存，手柄位于已播放与已缓存交界。

### player_window — 数据桥接

在 `_sync_progress_slider` 中，于读取 `position`、`duration` 之后：

1. 通过 `hasattr(self.video, "demuxer_cache_duration_seconds")` 防御性读取缓存时长，异常或缺失视为 0。
2. 计算 `buffer_end = min(position + cache_duration, effective_duration)`。
3. 调用 `self.progress.set_buffer_value(buffer_end)`。

项切换或进度重置处（现有 `self.progress.setValue(0)` 附近）同步 `self.progress.set_buffer_value(0)`，避免上一集的缓存段残留。

### theme — 缓存段颜色 token

在 `ThemeTokens` 与全部主题块新增 `player_buffer: str` 字段：

- 深色主题取介于 `player_button_border` 与 accent 之间的偏暗中性色（如 `#3a4252` 一类半透明观感）。
- 浅色主题取浅灰，明显浅于轨道色但不与 `border_subtle`（禁用态轨道）撞色。

理由：代码库强偏好显式可主题化 token；复用 `border_subtle` 会与禁用态轨道混用造成歧义。

## 状态流

```text
mpv demuxer-cache-duration
        │
        ▼
MpvWidget.demuxer_cache_duration_seconds()   （progress_timer 每次轮询按需读取）
        │
        ▼
_sync_progress_slider()  算 buffer_end = position + cache，钳到 duration
        │
        ▼
ClickableSlider.set_buffer_value(buffer_end)
        │
        ▼
paintEvent：轨道 → 缓存段(player_buffer) → accent 已播放段 → 手柄
```

不经过配置对象、设置仓库或数据库。

## 边界与降级

下列情况无需特判，按现有机制自然降级：

- 本地文件：`demuxer-cache-duration` 接近剩余时长，`buffer_end` 钳到 `effective_duration`，剩余整段显示为缓存（符合「确实已全缓存」）。
- 直播（duration 未知或为 0）：进度条本就禁用或隐藏，缓存段不绘制。
- seek 越过缓冲区：mpv 重新缓冲，缓存段随 `demuxer-cache-duration` 自然缩短后再增长。
- 缓存为空或 underrun：`cache_duration` 为 0，`buffer_end == position`，缓存段消失，只剩 accent 与轨道色。
- 切换剧集初期 `demuxer-cache-duration` 为 `None`：归一化为 0，缓存段随后随缓冲增长出现。

## 测试设计

沿用 `tests/test_player_window_ui.py` 现有测试模式，按测试驱动流程覆盖：

1. `MpvWidget.demuxer_cache_duration_seconds` 在无播放器、属性为 `None`、属性为负、读取抛异常时均返回 0。
2. `ClickableSlider.set_buffer_value` 将值钳制到 `[minimum, maximum]`。
3. `set_buffer_value(0)` 或值不大于当前 `value()` 时，`paintEvent` 不绘制缓存段（行为可通过绘制前后状态或几何计算验证，沿用现有 slider 测试方式）。
4. `_sync_progress_slider` 在 mock 控件返回固定 `position`、`duration`、缓存时长时，调用 `set_buffer_value` 传入 `min(position + cache, duration)`。
5. 控件缺少 `demuxer_cache_duration_seconds` 时 `_sync_progress_slider` 不抛异常，缓存段按 0 处理。
6. 项切换/重置进度时缓存段被清零。
7. 运行播放器窗口相关测试及必要的完整测试集，确认未破坏进度、seek、时间标签与主题渲染。

## 非目标

- 缓存时长文字标签或弹幕式提示。
- 缓冲中 spinner / `cache-buffering-state` 百分比指示。
- 接入 m3u8 代理预下载进度。
- 调整 `progress_timer` / `report_timer` 轮询频率。
- 修改任何配置或持久化逻辑。

## 验收标准

- 播放网络视频时，进度条手柄右侧出现一段浅色缓存区域，随缓冲增长、随 seek 缩短。
- 本地文件播放时缓存段自然延伸到进度条末端，不报错。
- 直播或无 duration 场景下不绘制缓存段，不影响现有进度条行为。
- 缓存段颜色随主题切换正确变化。
- 切换剧集后缓存段从空开始，不残留上一集状态。
- 不改变现有播放、seek、时间标签与轮询时序。
