# Player Log Bottom When Details Hidden Design

## Summary

当前播放器右侧侧栏中，`播放日志` 始终挂在 `details` 区域内部。当用户关闭 `详情` 但保留 `播放日志` 时，日志虽然还能显示，但它仍依附于详情容器，无法实现“播放列表占据剩余全部高度，日志固定显示在底部”的布局。

本次改动在 `详情` 隐藏且 `播放日志` 显示时，临时把日志区域移动到右侧侧栏底部；播放列表占据上方全部剩余高度。其余状态保持现有结构不变。

## Goals

- 当 `详情` 隐藏且 `播放日志` 开启时，让日志显示在右侧侧栏底部。
- 让播放列表在该状态下占据日志上方的全部剩余高度。
- 保持现有 `播放日志` 内容、开关语义和滚动行为不变。
- 在恢复 `详情` 后，恢复原有详情栏结构和日志位置。

## Non-Goals

- 重做右侧侧栏整体架构。
- 引入新的 splitter 层级或新的持久化配置项。
- 修改 fullscreen、wide mode 或播放列表开关的既有语义。
- 修改日志区最大高度规则。

## Scope

主要改动：

- `src/atv_player/ui/player_window.py`

主要验证：

- `tests/test_player_window_ui.py`

## Design

### Normal Layout

以下状态保持不变：

- `详情` 显示时，`log_section` 继续留在 `details` 容器内部
- `播放日志` 关闭时，`log_section` 继续按现有逻辑隐藏
- fullscreen 和 wide mode 继续按现有逻辑隐藏整个右侧侧栏

也就是说，只有一种状态会触发新布局：

- `详情` 隐藏
- `播放日志` 显示
- 非 fullscreen
- 非 wide mode

### Bottom Docked Log State

在该状态下：

- `details` 整体隐藏
- `playlist` 继续留在 `sidebar_splitter` 中，并占据右侧主区域全部剩余高度
- `log_section` 从 `details` 布局中临时移出，挂到 `sidebar_container` 的底部布局中

这样视觉结果应为：

- 上方：播放列表
- 下方：播放日志

不应该在两者之间保留额外的空白详情区域。

### Reattachment Rules

当以下任一条件成立时，`log_section` 必须回到 `details` 容器内：

- `详情` 重新显示
- `播放日志` 关闭
- 进入 fullscreen
- 进入 wide mode

恢复后，`details` 布局中的顺序应保持不变：

- `metadata_section`
- `log_section`

### Height Behavior

日志区域移到底部后，继续沿用现有最大高度限制逻辑，而不是重新定义另一套底部日志高度规则。

也就是说：

- 日志仍然是可滚动文本区
- 底部日志区域仍然受当前的最大高度约束控制

### Implementation Boundary

实现应集中在 `PlayerWindow` 内部，使用小范围私有方法处理：

- 判断当前是否需要底部日志布局
- 在两个父布局之间移动 `log_section`
- 在现有 `_apply_visibility_state()` 流程中统一应用

不要为这次需求引入新的通用布局类。

## Testing

补充或更新 UI 测试覆盖：

- 当关闭 `详情` 且保留 `播放日志` 时，`log_section` 不再位于 `details` 布局内，而位于右侧侧栏底部容器
- 该状态下 `playlist` 仍可见，`details` 隐藏
- 当重新打开 `详情` 时，`log_section` 回到 `details` 布局中
- 当关闭 `播放日志` 时，不留下额外的底部日志区域

## Risks

- 如果 `log_section` 在布局切换时没有正确从旧布局移除，Qt 可能出现父子关系错误或重复布局行为。
- 如果恢复顺序处理不严谨，重新显示 `详情` 后日志可能回不到 `metadata_section` 之后。
- 如果底部日志状态判断遗漏 fullscreen 或 wide mode，侧栏隐藏时可能残留日志区域。
