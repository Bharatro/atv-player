# Dialog No Maximize Button Design

## Summary

移除所有应用内 `ThemedDialogBase` 对话框标题栏上的最大化按钮，统一恢复为“仅保留关闭按钮”的对话框控制语义。

本次改动只影响应用内自建对话框的标题栏按钮显示，不调整主窗口、登录窗口、播放器窗口的最大化能力，也不改变对话框内容布局和业务行为。

## Goals

- 让所有应用内对话框不再显示最大化按钮。
- 保持 `ThemedDialogBase` 作为“对话框默认不最大化”的统一语义来源。
- 清理当前若干对话框显式传入 `allow_maximize=True` 的分散特例。
- 用 UI 测试锁住“所有应用内对话框不显示最大化按钮”的行为。

## Non-Goals

- 本轮不改动 `MainWindow`、`LoginWindow`、`PlayerWindow` 的最大化按钮行为。
- 本轮不改动对话框 padding、resize、拖拽等其他窗口 chrome 行为。
- 本轮不影响 `QMessageBox`、`QFileDialog`、`QColorDialog` 等原生/标准弹窗。

## Scope

主要改动：

- `src/atv_player/ui/plugin_manager_dialog.py`
- `src/atv_player/ui/help_dialog.py`
- `src/atv_player/ui/live_source_manager_dialog.py`
- `src/atv_player/ui/manual_live_source_dialog.py`
- `src/atv_player/ui/player_window.py`

主要验证：

- `tests/test_window_chrome.py`
- `tests/test_player_window_ui.py`
- 需要时补充对应对话框 UI 测试

## Current Problem

`ThemedDialogBase` 本身默认隐藏最大化按钮，但当前项目里仍有若干应用内对话框显式传入 `allow_maximize=True`，导致对话框控制语义不一致：

- `PluginManagerDialog`
- `ShortcutHelpDialog`
- `LiveSourceManagerDialog`
- `ManualLiveSourceDialog`
- 播放器里的 `_PlayerToolDialog`，即“弹幕设置”“刮削”“弹幕源”

这与用户当前要求“对话框不要最大化按钮”直接冲突，也会让对话框与主窗口/播放器窗口的标题栏行为边界变模糊。

## Approach Options

### Option A: Remove `allow_maximize=True` at each dialog call site

做法：

- 保留 `ThemedDialogBase` 接口不变
- 把所有应用内对话框上的 `allow_maximize=True` 移除

优点：

- 改动最小
- 风险最低
- 完全符合当前需求

缺点：

- 依赖测试保证未来不再重新加回去

### Option B: Remove maximize support from `ThemedDialogBase` entirely

做法：

- 删除 `ThemedDialogBase` 上的 `allow_maximize` 能力

优点：

- 约束最强

缺点：

- 改动更大
- 会把“未来某个对话框确实需要最大化”的扩展点一起移除

### Option C: Keep the parameter but hide the button with styles

做法：

- 保留 `allow_maximize=True`
- 通过样式或运行时显隐覆盖按钮

优点：

- 表面上不改调用点

缺点：

- 增加隐式行为
- 比直接删参数更绕
- 不符合当前代码已经有显式布尔控制的结构

## Decision

采用 **Option A**。

原因：

- `ThemedDialogBase` 已经提供了正确的默认语义，当前问题只是少量调用点显式打开了最大化按钮。
- 直接移除这些调用点上的 `allow_maximize=True` 能以最小代价恢复一致性。
- 这比修改基类接口更稳，也更容易通过现有 UI 测试覆盖。

## Design

### 1. Base dialog behavior stays the default

`ThemedDialogBase` 继续保持当前默认行为：

- 隐藏最大化按钮
- 隐藏最小化按钮
- 保留关闭按钮

本轮不改它的默认语义。

### 2. Remove explicit maximize opt-ins

把所有应用内自建对话框上的 `allow_maximize=True` 调用移除，让它们回落到基类默认行为。

涉及对象：

- `PluginManagerDialog`
- `ShortcutHelpDialog`
- `LiveSourceManagerDialog`
- `ManualLiveSourceDialog`
- `_PlayerToolDialog`

### 3. Runtime player dialogs

播放器里的“弹幕设置”“刮削”“弹幕源”都通过 `_PlayerToolDialog` 创建。

因此只要 `_PlayerToolDialog` 不再向 `ThemedDialogBase` 传 `allow_maximize=True`，这三个运行时对话框会一起恢复为无最大化按钮，不需要分别修改。

## Testing

新增或调整测试覆盖以下行为：

- `ThemedDialogBase` 默认隐藏最大化按钮的基类断言继续成立。
- 播放器运行时对话框“弹幕设置”“刮削”“弹幕源”的最大化按钮均隐藏。
- 如果已有静态对话框测试覆盖到标题栏，可补断言确保这些对话框同样不显示最大化按钮。

## Risks And Mitigations

- 风险：某个对话框过去依赖最大化按钮做大尺寸展示。
  缓解：这次只移除按钮，不改默认尺寸；若后续确实需要更大初始空间，应单独通过默认 `resize()` 解决，而不是复用最大化按钮。

- 风险：只改调用点容易在后续回归中重新引入 `allow_maximize=True`。
  缓解：补 UI 测试，直接断言运行时和基类对话框按钮隐藏状态。
