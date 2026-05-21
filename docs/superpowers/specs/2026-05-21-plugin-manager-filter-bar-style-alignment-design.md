# Plugin Manager Filter Bar Style Alignment Design

## Summary

插件管理对话框最近新增了搜索、筛选、排序条件栏，但当前这一行仍然使用原生 `QComboBox` 和局部手调宽度，和应用里已经存在的 `HistoryPage` filter bar 风格不一致。用户已经明确希望它统一成和“高级设置 / 日志”里下拉框相同的样式，而不是只做一点局部留白修补。

本次改动目标是让插件管理条件栏完整对齐现有 `HistoryPage` filter bar 模式：组件类型一致、宽度计算方式一致、横向布局节奏一致，同时保持现有搜索/筛选/排序行为不变。

## Goals

- 让插件管理条件栏的两个下拉框与现有 `FlatComboBox` 视觉风格一致。
- 让插件管理条件栏的宽度策略与 `HistoryPage` 的 filter combo 保持一致。
- 让搜索框、下拉框、末尾动作按钮在同一条 filter bar 上形成一致的布局节奏。
- 保留当前插件管理搜索、筛选、排序的行为和状态逻辑。

## Non-Goals

- 不修改插件管理表格、按钮区第二行或日志弹窗。
- 不改动 `plugin_manager`、repository、数据模型。
- 不做新的全局主题系统抽象。
- 不改变搜索、筛选、排序的业务规则。

## Current Flow

当前插件管理对话框位于 [plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:49)。

- `enabled_filter_combo` 和 `sort_combo` 使用原生 `QComboBox`
- 通过固定 `minimumWidth` 手动留宽
- 条件栏只做了局部 `QHBoxLayout` 拼装

而应用内现有的 `HistoryPage` filter bar 位于 [history_page.py](/home/harold/workspace/atv-player/src/atv_player/ui/history_page.py:91)，其下拉框方案是：

- 使用 `FlatComboBox`
- 通过 `_configure_filter_combo(...)` 设置
  - `AdjustToMinimumContentsLengthWithIcon`
  - `minimumContentsLength`
  - `maxVisibleItems`
  - 基于最长标签文本和内部 padding 的最小宽度
  - `Preferred / Fixed` 的尺寸策略

这两套实现目前并不统一，因此插件管理条件栏看起来像“新拼的一行”，而不是现有 UI 语言的一部分。

## Proposed Behavior

### Control Alignment

插件管理条件栏统一到 `HistoryPage` filter bar 模式：

- `enabled_filter_combo` 改为 `FlatComboBox`
- `sort_combo` 改为 `FlatComboBox`
- `search_input` 保留 `QLineEdit`，但样式和留白策略对齐 `HistoryPage.search_edit`
- `clear_filters_button` 保留为按钮，但作为同一条 filter bar 的末尾动作控件参与统一布局

表格和按钮区不变，搜索/筛选/排序行为不变。

### Width And Sizing Strategy

两个下拉框不再依赖固定 magic number 宽度，而采用与 `HistoryPage._configure_filter_combo(...)` 一致的策略：

- `QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon`
- 设置 `minimumContentsLength`
- 设置 `maxVisibleItems`
- 根据最长选项文本宽度 + `flat_combo_left_padding` + `flat_combo_indicator_padding` 计算 `minimumWidth`
- 设置 `QSizePolicy.Policy.Preferred` / `QSizePolicy.Policy.Fixed`

建议两者都使用 `minimumContentsLength = 6`，足以覆盖当前文案并保持和现有 filter combo 的紧凑感。

### Filter Bar Layout

条件栏整体按 `HistoryPage` 同类 filter bar 的节奏处理：

- 搜索框为主弹性控件，占剩余主要宽度
- 两个下拉框为按内容留宽的辅控件
- `清空` 按钮放在最右
- 横向间距统一，不再采用插件管理自己的局部调参思路

最终视觉效果应满足：

- 搜索框明显宽于两个下拉框
- 两个下拉框像同一组 filter combo，而不是两个宽度不同的普通下拉框
- 这整行看起来和 `HistoryPage` 属于同一套界面语言

## Architecture

### Reuse Existing UI Pattern

实现重点放在 [plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:49) 内部，直接复用现有 UI 模式而不是重新发明：

- 从 [theme.py](/home/harold/workspace/atv-player/src/atv_player/ui/theme.py:16) 引入 `FlatComboBox`
- 参考 [history_page.py](/home/harold/workspace/atv-player/src/atv_player/ui/history_page.py:171) 的 `_configure_filter_combo(...)` 规则

允许插件管理对话框内部新增一个小型私有 helper，例如 `_configure_filter_combo(...)`，但要求：

- 参数和行为与 `HistoryPage` 对齐
- 不引入新的一套独立宽度逻辑

### Keep Behavior Separate From Styling

这次改动只触碰条件栏的组件和布局层，不改：

- `_visible_plugins(...)`
- `_matches_search(...)`
- `_sort_plugins(...)`
- `_clear_view_filters(...)`
- `_apply_view_filters(...)`

也就是说，视图行为逻辑和样式/布局逻辑继续分离，避免为了统一外观而牵动业务路径。

## Error Handling

- 这次改动不引入新的后台请求或错误路径。
- 如果下拉框样式或最小宽度计算有问题，应该通过 UI 测试提前暴露，而不是运行时降级到静默不一致。

## Testing

继续在 [test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:1) 增补测试。

至少覆盖：

- 两个条件栏下拉框现在是 `FlatComboBox`
- 两个下拉框的 `sizeAdjustPolicy()` 为 `AdjustToMinimumContentsLengthWithIcon`
- `minimumContentsLength()` 为预期值
- `maxVisibleItems()` 为预期值
- `minimumWidth()` 至少覆盖最长选项文本宽度 + padding
- 搜索框宽度大于两个下拉框
- 原有搜索 / 筛选 / 排序 / 清空 / 空状态测试继续通过

## Risks

- 如果只替换样式表而不复用 `FlatComboBox`，会复制现有主题逻辑并造成维护分叉。
- 如果仍然保留固定宽度，选项文案一旦变化，插件管理条件栏会继续与其他 filter bar 脱节。
- 如果为了对齐而顺手改搜索/筛选业务逻辑，会扩大改动面并增加回归风险。

## Recommendation

采用“完整复用 `HistoryPage` filter bar 模式”的方案，而不是只补局部视觉修饰。

这是最稳妥的路径：

- 用户能直接得到和“高级设置 / 日志”一致的下拉框风格
- 实现上复用现有 `FlatComboBox` 和宽度计算规则
- 改动面集中在插件管理 UI 文件和现有 UI 测试内
- 不会引入新的主题分叉
