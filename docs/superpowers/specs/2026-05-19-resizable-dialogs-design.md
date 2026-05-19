# Resizable Dialogs Design

## Summary

让所有继承 `ThemedDialogBase` 的应用内自建对话框默认支持无边框窗口的边缘和角落缩放，同时继续保持“无最小化、无最大化、仅关闭按钮”的对话框标题栏语义。

本次改动只调整对话框窗口 chrome 的默认能力，不修复当前顶层窗口缩放失效问题，也不改业务对话框内容布局和交互流程。

## Goals

- 所有 `ThemedDialogBase` 对话框默认支持拖拽调整大小。
- 保持对话框标题栏按钮语义不变，只显示关闭按钮。
- 把行为收敛在窗口 chrome 基类，避免逐个对话框显式开启。
- 保留少量特殊对话框未来显式关闭缩放能力的入口。

## Non-Goals

- 本轮不修复 `MainWindow`、`LoginWindow`、`PlayerWindow` 当前缩放失效问题。
- 本轮不调整原生 `QMessageBox`、`QFileDialog` 等系统弹窗。
- 本轮不改对话框默认尺寸、最小尺寸或内容布局结构。
- 本轮不重新设计标题栏按钮，仍然不显示最大化按钮。

## Scope

主要改动：

- `src/atv_player/ui/window_chrome.py`

主要验证：

- `tests/test_window_chrome.py`

## Current Problem

当前 `_ThemedChromeMixin` 已经具备统一的无边框窗口缩放逻辑，但 `ThemedDialogBase` 在构造时固定传入 `resizable=False`，导致所有应用内自建对话框都无法复用这套能力。

这让大内容对话框的桌面交互体验不完整，例如帮助、插件管理、直播源管理、高级设置和播放器工具对话框都只能使用固定初始尺寸，无法按内容密度自行放大或缩小。

## Approach Options

### Option A: 逐个对话框显式开启 `resizable=True`

做法：

- 在每个具体对话框类里单独传 `resizable=True`

优点：

- 影响面可控

缺点：

- 行为分散
- 容易漏掉现有或未来新增对话框
- 与“所有对话框支持调整大小”的目标不一致

### Option B: `ThemedDialogBase` 默认开启缩放，不保留关闭入口

做法：

- 直接把 `ThemedDialogBase` 写死为 `resizable=True`

优点：

- 改动最小
- 默认行为统一

缺点：

- 如果后续有极小或语义上应固定尺寸的对话框，没有显式关闭通道

### Option C: `ThemedDialogBase` 增加 `resizable` 参数，默认值为 `True`

做法：

- 在 `ThemedDialogBase` 构造函数新增 `resizable: bool = True`
- 把该值传给 `_init_window_chrome(...)`

优点：

- 默认行为统一覆盖所有应用内对话框
- 仍保留个别特殊对话框显式关闭的扩展点
- 改动集中在基类，业务对话框无需逐个改造

缺点：

- 相比写死默认值，多一个公开参数需要维护

## Decision

采用 **Option C**。

原因：

- 需求目标是“所有应用内对话框支持调整大小”，最稳定的实现位置就是 `ThemedDialogBase`。
- 当前缩放逻辑已在 `_ThemedChromeMixin` 中存在，不需要新增第二套实现。
- 默认开启并保留显式关闭入口，比逐个类手动接线更稳，也比彻底写死更灵活。

## Design

### 1. Base dialog contract

`ThemedDialogBase` 构造函数调整为：

- 保留 `title`
- 保留 `parent`
- 保留 `allow_maximize`
- 新增 `resizable: bool = True`

内部调用 `_init_window_chrome(...)` 时，不再固定传 `resizable=False`，而是透传该参数。

这样一来，所有未显式覆盖的 `ThemedDialogBase` 子类都会默认启用窗口边缘缩放能力。

### 2. Title bar semantics stay unchanged

本次只打开缩放能力，不改变对话框标题栏按钮语义：

- 最小化按钮继续隐藏
- 最大化按钮继续隐藏
- 关闭按钮继续保留

也就是说，对话框仍然不是“可最大化窗口”，只是“可从边缘拖拽调整大小的对话框”。

### 3. Business dialogs inherit automatically

现有应用内自建对话框不需要逐个修改：

- `AdvancedSettingsDialog`
- `PluginManagerDialog`
- `PluginReorderDialog`
- `LiveSourceManagerDialog`
- `ManualLiveSourceDialog`
- `ShortcutHelpDialog`
- 播放器运行时工具对话框

它们只要继续继承 `ThemedDialogBase`，就会自动获得缩放能力，并沿用各自现有的 `resize(...)` 和 `minimumSize(...)` 约束。

### 4. Explicit opt-out remains available

如果未来出现确实不适合缩放的特殊对话框，可以显式传：

```python
super().__init__(title="...", parent=parent, resizable=False)
```

这样无需再回改基类默认行为。

## Testing

优先用基类测试锁住行为契约，而不是在每个业务对话框里重复断言：

- `ThemedDialogBase` 默认 `is_window_resizable()` 为 `True`
- 显式传入 `resizable=False` 时，`is_window_resizable()` 为 `False`
- 对话框默认仍隐藏最大化按钮

测试位置：

- `tests/test_window_chrome.py`

## Risks And Mitigations

- 风险：某些小型对话框启用缩放后，交互语义可能显得比以前更“重”。
  缓解：保留 `resizable=False` 显式退出通道，后续按需局部关闭。

- 风险：需求容易与“顶层窗口缩放失效”混淆。
  缓解：本 spec 明确排除顶层窗口修复，只覆盖 `ThemedDialogBase`。

- 风险：只改基类可能让行为变化范围比预期更广。
  缓解：通过基类契约测试和 focused diff 控制范围，确保只影响自建对话框。
