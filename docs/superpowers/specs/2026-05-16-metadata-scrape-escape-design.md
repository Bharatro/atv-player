# Metadata Scrape Dialog Escape Design

## Summary

调整播放器中的 `Esc` 行为：

- 当 `刮削` 对话框可见时，`Esc` 只关闭该对话框
- 不触发 `返回主界面`
- 不中断当前播放

范围仅限播放器内现有 `Esc` 分发逻辑和对应测试。

## Goal

- 修复 `刮削` 对话框打开时按下 `Esc` 会退出播放的问题
- 让 `刮削` 对话框的 `Esc` 行为与播放器内其他辅助对话框保持一致

## Non-Goals

- 不修改 `S` 快捷键打开刮削对话框的行为
- 不重构播放器整体快捷键体系
- 不改变全屏态下 `Esc` 退出全屏的现有行为
- 不修改对话框布局、搜索、应用结果或元数据写回逻辑

## Current Behavior

`PlayerWindow._handle_escape()` 当前按顺序处理：

1. 关闭帮助对话框、弹幕设置对话框、弹幕源对话框
2. 若当前全屏，则退出全屏
3. 否则执行 `PlayerWindow._return_to_main()`

`刮削` 对话框没有被纳入第一步的“可被 `Esc` 直接关闭的辅助对话框”列表，因此对话框可见时，`Esc` 最终仍会落到 `返回主界面`，导致播放被退出。

## Options

### Option A: Extend the existing escape-dismiss helper

把 `刮削` 对话框加入 `_dismiss_escape_dialog()` 的判断顺序。

优点：

- 改动最小
- 与当前帮助/弹幕对话框处理方式一致
- 风险局部，易于测试

缺点：

- 继续沿用集中式分发，而不是让每个对话框自己持有快捷键策略

### Option B: Install a dedicated `Esc` shortcut on the scrape dialog

在 `刮削` 对话框内部单独绑定 `Esc -> close()`。

优点：

- 行为边界看起来更靠近对话框自身

缺点：

- 容易和父窗口现有 `Esc` 处理竞争
- 需要额外确认 Qt 快捷键优先级
- 会让类似对话框行为来源分散

## Decision

采用 **Option A**。

原因：

- 当前播放器已经有统一的 `Esc` 分发点，继续在这里补齐 `刮削` 对话框最直接
- 该修复是现有漏判，不需要引入新的快捷键机制
- 与现有帮助/弹幕对话框的体验保持一致

## Design

### Escape handling

在 [`player_window.py`](/home/harold/workspace/atv-player/src/atv_player/ui/player_window.py) 中补充一个 `_close_metadata_scrape_dialog()` 辅助方法，语义与现有：

- `_close_danmaku_source_dialog()`
- `_close_danmaku_settings_dialog()`

保持一致：

- 若对话框不存在或当前不可见，则不做任何事
- 若对话框可见，则关闭对话框

然后在 `_dismiss_escape_dialog()` 中加入 `刮削` 对话框分支。

预期顺序：

1. 弹幕设置
2. 弹幕源
3. 刮削
4. 快捷键帮助

只要任一对话框被关闭，就返回 `True`，阻止后续 `Esc` 继续触发全屏退出或 `返回主界面`。

### Return-to-main behavior

`_return_to_main()` 也应同步关闭 `刮削` 对话框，确保用户通过其他路径离开播放器时不会残留该子对话框。

这不会改变已有用户语义，只是补齐资源与窗口状态清理的一致性。

## Testing

在 [`tests/test_player_window_ui.py`](/home/harold/workspace/atv-player/tests/test_player_window_ui.py) 增加聚焦覆盖：

- 当 `刮削` 对话框已打开时，向播放器发送 `Esc`
- 断言 `刮削` 对话框被关闭
- 断言播放器窗口仍可见
- 断言未执行 `closed_to_main`

保留现有播放器快捷键测试，确保：

- 非对话框场景下，普通 `Esc` 仍按原逻辑工作
- 全屏场景下，`Esc` 仍优先退出全屏

## Risks

- 如果未来新增更多播放器子对话框但忘记接入 `_dismiss_escape_dialog()`，同类问题可能再次出现

当前先保持最小修复，不在本轮扩展为通用对话框注册机制。
