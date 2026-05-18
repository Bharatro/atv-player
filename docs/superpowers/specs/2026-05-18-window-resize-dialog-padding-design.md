# Window Resize And Dialog Padding Design

## Summary

在现有自定义标题栏基础上补齐两个体验缺口：

- 所有继承 `ThemedDialogBase` 的应用内对话框默认增加一层轻量内容内边距，避免内容区直接贴边。
- `MainWindow`、`PlayerWindow`、`LoginWindow` 这三个顶层窗口支持无边框窗口的拖拽移动和边缘/角落缩放。

本次改动只覆盖窗口 chrome 与承载布局，不调整业务流程、页面结构或播放器内部功能逻辑。

## Goals

- 统一所有自建对话框的显示留白，让内容区不再紧贴外框。
- 让主窗口、播放窗口、登录窗口在自定义标题栏模式下仍具备桌面应用常见的窗口缩放能力。
- 保持现有标题栏按钮语义不变：对话框默认不显示最大化按钮，主窗口和顶层播放/登录窗口保留最大化能力。
- 把行为收敛在窗口 chrome 基类，避免每个窗口重复实现 resize hit-test 或内容边距。

## Non-Goals

- 本轮不把“可调整大小”扩散到所有 `ThemedDialogBase` 对话框。
- 本轮不改变 `QMessageBox`、`QColorDialog`、`QFileDialog` 等原生/标准弹窗的窗口 chrome。
- 本轮不重做主窗口、播放器窗口、登录窗口内部布局结构。
- 本轮不引入平台原生阴影、吸附、系统级 snap layout 等更复杂窗口管理能力。

## Scope

主要改动：

- `src/atv_player/ui/window_chrome.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/ui/login_window.py`

主要验证：

- `tests/test_window_chrome.py`
- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_login_window_ui.py`

## Current Problem

当前自定义标题栏已经统一了窗口外观和标题栏拖拽，但仍有两个直接问题：

- `ThemedDialogBase` 的内容容器默认是零边距，多个对话框内容直接贴到边框，视觉上过紧。
- 顶层窗口启用了 `FramelessWindowHint` 后，虽然标题栏可以拖动窗口，但没有补齐窗口边缘 resize hit-test，用户无法像普通桌面窗口那样从边和角拖拽调整大小。

这导致三个顶层窗口在无边框模式下的基础桌面交互不完整，而对话框则缺少统一的显示留白。

## Approach Options

### Option A: Per-dialog and per-window patching

做法：

- 每个对话框自己设置内容边距
- 每个顶层窗口自己处理鼠标命中、光标形态和 resize

优点：

- 局部改动看起来直接

缺点：

- 重复逻辑多
- 后续新增窗口容易漏
- 同类行为难以保证一致

### Option B: Centralize in window chrome base

做法：

- 在 `ThemedDialogBase` 内统一设置对话框内容区默认 padding
- 在窗口 chrome mixin 中增加“允许缩放”的统一能力，并由顶层窗口选择开启

优点：

- 改动集中
- 行为一致
- 对现有业务窗口侵入最小
- 新窗口默认继承一致行为

缺点：

- 需要在基类里增加一小层通用 hit-test 与鼠标事件逻辑

### Option C: Global padding for all windows and dialogs

做法：

- 在所有 `Themed*Base` 内容区统一加 padding
- 顺手给所有顶层窗口和对话框开启 resize

优点：

- 表面上最“统一”

缺点：

- 会破坏主窗口、播放器窗口现有贴边布局
- 会把大量不需要缩放的对话框一起改成 resizable
- 范围明显超过本次用户确认边界

## Decision

采用 **Option B**。

原因：

- 用户明确要求“对话框”统一加 padding，但只点名主窗口、播放窗口、登录窗口需要支持拖拽移动与调整大小。
- 对话框的视觉留白和顶层窗口的 resize 能力都属于 window chrome 基类职责，集中在基类实现最稳定。
- 保持窗口能力按类型分层，可以避免误伤播放器内部弹窗和其他工具对话框的既有尺寸语义。

## Design

### 1. Dialog content padding

`ThemedDialogBase` 默认给 `content_layout()` 设置统一内容边距，目标是“轻量留白”而不是卡片式大边框。

设计约束：

- padding 只作用于对话框内容区，不作用于标题栏。
- 默认值保持小而稳定，避免压缩中小型对话框可用空间。
- 各具体对话框如果确实需要特殊布局，仍可在自身类中显式覆盖。

这样可以一次性覆盖：

- `AdvancedSettingsDialog`
- `PluginManagerDialog`
- `PluginReorderDialog`
- `LiveSourceManagerDialog`
- `ManualLiveSourceDialog`
- `ShortcutHelpDialog`
- 播放器运行时创建的 `ThemedDialogBase` 对话框

### 2. Resizable frameless top-level windows

在 `_ThemedChromeMixin` 中补充可选的无边框缩放能力，但默认关闭。

基类新增语义：

- `resizable: bool`
- 仅当 `resizable=True` 时，启用窗口边缘 hit-test、光标切换和拖拽缩放

缩放目标窗口：

- `MainWindow`
- `PlayerWindow`
- `LoginWindow`

不启用缩放的对象：

- 所有 `ThemedDialogBase` 对话框

### 3. Resize hit-test model

对启用缩放的窗口，在窗口四边和四角定义一个窄的命中区域。

行为：

- 鼠标悬停到边/角时切换到对应 resize 光标
- 左键按下并命中边/角时进入 resize 模式
- 拖拽时按命中的边更新窗口 geometry
- 左键释放时退出 resize 模式

实现原则：

- 只在非最大化、非全屏状态下允许 resize
- 尊重窗口已有 `minimumSize()`
- 优先保证边角命中，其次是单边命中
- 未命中 resize 区域时，不影响现有内容控件交互

### 4. Move behavior

标题栏拖拽移动行为继续保留。

约束：

- 最大化状态下不允许普通拖动位移
- 进入 resize 模式后，不应再触发标题栏拖动逻辑
- 登录窗口、主窗口、播放器窗口都沿用同一套标题栏拖动语义

本轮不扩展为“从最大化标题栏拖出后还原并继续拖动”的复杂系统窗口行为。

### 5. Window-specific integration

三个顶层窗口只做最小接入：

- `MainWindow`：继续维持当前 `ThemedMainWindowBase` 用法，仅开启 `resizable`
- `PlayerWindow`：继续维持当前 `ThemedWidgetWindowBase` 用法，仅开启 `resizable`
- `LoginWindow`：继续维持当前 `ThemedWidgetWindowBase` 用法，仅开启 `resizable`

除登录窗口现有内容居中布局外，本轮不额外修改这三个窗口的页面结构。

## Testing

新增或调整测试覆盖以下行为：

- `ThemedDialogBase` 默认隐藏最大化按钮的行为仍然成立
- `ThemedDialogBase` 的内容布局默认带有非零 padding
- `MainWindow`、`PlayerWindow`、`LoginWindow` 仍使用自定义标题栏，且标记为允许缩放
- resize 相关基类状态只对允许缩放的顶层窗口生效，不扩散到对话框

测试策略以 UI 结构与状态断言为主，不依赖高脆弱度的完整鼠标拖拽像素模拟。

## Risks And Mitigations

- 风险：统一对话框 padding 可能让个别紧凑对话框高度略增。
  缓解：padding 保持轻量，并允许具体对话框按需覆盖。

- 风险：无边框 resize 逻辑可能与子控件鼠标事件冲突。
  缓解：只在边缘窄命中区拦截，非命中区域保持原事件流。

- 风险：最大化/全屏状态下 resize 光标或命中行为异常。
  缓解：在最大化和全屏时完全禁用 resize hit-test。
