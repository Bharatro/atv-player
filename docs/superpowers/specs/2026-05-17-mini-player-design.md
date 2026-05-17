# Mini Player Design

## Summary

桌面播放器新增 `Mini Player` 模式，用于“长期挂着看”的轻量播放场景。该模式在现有 `PlayerWindow` 内切换，不新建独立播放窗口。进入后窗口切为 `always on top + 无边框`，隐藏侧栏和现有大控制区，只保留鼠标移入时出现的悬浮小控制栏；双击视频区域或点击恢复按钮可返回普通播放器模式。

第一版目标是把它做成稳定、轻量、适合 Linux 桌面常驻的小窗能力，不尝试把完整播放器能力压缩进小窗。

## Goals

- 提供播放器内可切换的 `Mini Player` 模式。
- 进入 Mini Player 时保持当前播放不中断。
- 让 Mini Player 具备 `置顶`、`无边框`、`小控制栏`、`双击恢复`。
- 小控制栏默认隐藏，鼠标移入视频区域时显示，移出后隐藏。
- 记住 Mini Player 上次的位置和尺寸。
- 保持该能力主要封装在 `PlayerWindow` 内，尽量不扩散到主窗口恢复链路。

## Non-Goals

- 新建独立的第二个播放器窗口。
- 在 Mini Player 中保留完整的音量、宽屏、全屏、弹幕、刮削、日志、详情等控制。
- 启动应用时自动恢复到 Mini Player。
- 第一版同时提供多个入口形态。
- 改变当前普通模式下视频双击进入全屏的行为。

## Scope

主要改动：

- `src/atv_player/ui/player_window.py`
- `src/atv_player/models.py`
- `src/atv_player/storage.py`

主要验证：

- `tests/test_player_window_ui.py`

## Design

### Mode Model

`Mini Player` 作为 `PlayerWindow` 的独立显示模式存在，不与当前 `wide mode` 或 `fullscreen` 并存。

建议新增显式状态与入口方法：

- `enter_mini_player()`
- `exit_mini_player()`
- `toggle_mini_player()`
- `_is_mini_player`

所有按钮、双击、`Esc`、关闭恢复逻辑都统一走这组入口，避免分散修改窗口 flags 和显隐状态。

模式关系约束：

- 进入 Mini Player 前，如果当前处于 `fullscreen`，先退出 fullscreen 视觉状态。
- 进入 Mini Player 前，如果当前处于 `wide mode`，保留配置值不重要，直接退出该视觉状态。
- Mini Player 内不允许继续切换 `fullscreen` 或 `wide mode`。
- 从 Mini Player 恢复时，只恢复到普通播放器模式，不自动返回 fullscreen。

这样可以把 Mini Player 视为更高优先级的窗口显示模式，避免状态嵌套。

### Entry and Exit

第一版入口只做成播放器底部控制区中的独立按钮，不同时扩展到右键菜单。

原因：

- 当前 `PlayerWindow` 已有稳定的底部按钮区和按钮测试模式。
- 第一版先把核心窗口模式做稳，比扩入口更重要。
- 菜单项可以在后续迭代补充，不影响内部状态设计。

退出入口包括：

- 再次点击 Mini Player 按钮
- Mini Player 内悬浮小控制栏中的“恢复普通模式”按钮
- Mini Player 内双击视频区域
- Mini Player 内按 `Esc`

其中：

- 普通模式下视频双击仍保持当前行为：切 fullscreen
- Mini Player 下视频双击改为：恢复普通模式
- `Esc` 在 Mini Player 下优先退出 Mini Player，不直接返回主窗口

### Window Behavior

进入 Mini Player 时：

- 保持当前播放状态和进度，不重建 session
- 保存普通播放器当前几何信息，供恢复使用
- 应用 `Qt.WindowStaysOnTopHint`
- 应用 `Qt.FramelessWindowHint`
- 隐藏窗口的普通侧栏、底部控制区、详情区、日志区
- 应用 Mini Player 几何信息

退出 Mini Player 时：

- 移除置顶和无边框 flags
- 恢复普通播放器窗口几何
- 恢复普通模式下的控件显示规则

实现上应避免直接破坏现有 `player_window_geometry` 语义。普通模式和 Mini Player 需要分开保存几何信息。

### UI Composition

Mini Player 只保留两层界面：

1. `纯视频层`
2. `悬浮小控制栏`

默认状态下只显示视频层。悬浮小控制栏在鼠标移入视频区域时出现，移出后隐藏。

第一版小控制栏仅保留：

- 播放/暂停
- 上一集
- 下一集
- 进度条
- 恢复普通模式
- 关闭播放器

以下控件在 Mini Player 第一版不保留：

- 音量
- 宽屏
- 全屏
- 播放列表切换
- 详情 / 日志
- 弹幕源与弹幕设置
- 刮削
- 字幕 / 音轨 / 清晰度 / 解析器 / 片头片尾设置

这样可以避免小窗变成“把大控制栏硬缩小”的结果，保持长期悬挂场景的清爽度。

### Hover Behavior

Mini Player 沿用现有视频区域鼠标活动检测能力，但目标从“仅控制鼠标隐藏”扩展为“同时控制悬浮小控制栏显隐”。

行为规则：

- 鼠标进入视频区域：显示悬浮小控制栏
- 鼠标持续停留：控制栏保持可见
- 鼠标移出视频区域：隐藏悬浮小控制栏
- 播放时的 cursor auto-hide 逻辑继续工作，但不应与控制栏显隐相互打架

实现上建议把悬浮控制栏放在视频栈上层，作为独立 overlay，而不是复用当前 `bottom_area`。这是因为 `bottom_area` 依附整体窗口布局，不适合 frameless 小窗的 hover 体验。

### Persistence

新增 Mini Player 专用持久化字段：

- `mini_player_geometry`

不新增“启动后自动回到 Mini Player”的配置。即使用户关闭应用时身处 Mini Player，下次启动也不应直接恢复到小窗，以免影响可发现性和启动体验。

几何持久化策略：

- 普通播放器继续使用现有 `player_window_geometry`
- Mini Player 使用独立的 `mini_player_geometry`
- 两者互不覆盖

### Visibility Rules

Mini Player 激活时，`_apply_visibility_state()` 或其后续拆分逻辑需要显式感知 `_is_mini_player`。

Mini Player 下应满足：

- 侧栏隐藏
- 现有底部大控制栏隐藏
- playlist / details / log 全部隐藏
- 普通模式下依赖 `toggle_playlist_button`、`toggle_details_button`、`toggle_log_button` 的可见性规则暂不生效

普通模式恢复后再回到现有显示规则。

### Testing

补充 `PlayerWindow` UI 测试覆盖：

- 进入 Mini Player 后窗口 flags 包含置顶和无边框
- 进入 Mini Player 后侧栏和现有底部大控制区被隐藏
- Mini Player 下双击视频区域会恢复普通模式，而不是切 fullscreen
- Mini Player 下 `Esc` 只退出 Mini Player，不触发返回主窗口
- 退出 Mini Player 后普通模式可见性恢复正常
- Mini Player 几何信息可保存并在下次进入时恢复
- 悬浮小控制栏会随鼠标进入 / 移出视频区域显示和隐藏

不把第一版重点放在 `MainWindow` 相关恢复链路测试，因为这个能力应尽量局部封装在 `PlayerWindow` 内。

## Risks

- Qt 窗口 flags 在运行时切换后可能需要重新 `show()` 才能稳定生效，恢复顺序如果处理不好，容易出现窗口尺寸或焦点异常。
- 如果 Mini Player 和 fullscreen / wide mode 没有清晰的互斥规则，后续会产生难以维护的状态组合。
- 如果复用现有 `bottom_area` 而不是独立 overlay，小控制栏 hover 体验会被当前整体布局约束拖累。
- 如果 Mini Player 几何和普通播放器几何混用，用户在两种模式之间来回切换后窗口尺寸会互相污染。
