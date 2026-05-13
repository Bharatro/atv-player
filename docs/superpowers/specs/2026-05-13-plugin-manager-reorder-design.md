# Plugin Manager Reorder Design

## Summary

当前插件管理只支持单选后点击 `上移` / `下移` 做相邻交换。这个模型适合少量微调，但当用户需要把靠后的插件一次性挪到前面时，必须重复点击很多次，交互成本过高。

本次改动目标是把“长距离调整顺序”和“少量微调”拆开处理：主插件管理页继续保留轻量的单步调整入口，同时新增一个专用的“调整顺序”对话框，让用户可以集中完成拖拽排序、置顶/置底和少量微调，再一次性保存结果。

## Goals

- 为插件顺序调整提供专用入口，覆盖长距离移动和少量微调两类场景。
- 保持主插件管理页简洁，不在现有顶栏继续堆叠更多排序按钮。
- 让一次排序会话里的多次调整先停留在本地草稿，保存时再统一提交。
- 复用现有 `sort_order` 持久化模型，不改变插件排序的外部语义。

## Non-Goals

- 不改变插件启用、刷新、删除、重命名、配置编辑等现有管理动作。
- 不在排序对话框中加入插件刷新、删除或启用/禁用等非排序操作。
- 不引入自动保存或拖拽即落库的行为。
- 不把主插件管理页扩展为复杂的内联拖拽工作台。

## Current Flow

当前插件管理 UI 位于 [plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:49)。

- 主对话框顶栏提供 `上移` 和 `下移` 按钮。
- `_move_selected(direction)` 只支持单选，并直接调用 `plugin_manager.move_plugin(plugin_id, direction)`。
- repository 层的 [move_plugin](/home/harold/workspace/atv-player/src/atv_player/plugins/repository.py:200) 会读取当前插件顺序、与相邻项交换位置、然后重写所有插件的 `sort_order`。

这意味着当前排序模型本质上是“单项相邻交换”，而不是“提交最终顺序”。因此只在 UI 上增加更多按钮，无法从根本上改善长距离调整体验。

## Proposed Behavior

### Main Dialog

主插件管理页新增一个明显的 `调整顺序` 按钮，打开专用排序对话框。

- 现有 `上移` / `下移` 按钮继续保留，服务于小幅度微调。
- 不新增 `移动到...`、`置顶`、`置底` 等更多主界面按钮，避免顶栏继续膨胀。
- 排序完成并保存后，主插件管理页执行一次 `reload_plugins()`，刷新表格顺序并沿用现有脏状态判断。

### Reorder Dialog

新增一个只负责排序的专用对话框。该对话框只展示排序相关信息：

- 当前顺序
- 插件名称
- 启用状态

对话框内支持：

- 拖拽排序，用于长距离移动
- `置顶`
- `置底`
- `上移`
- `下移`

按钮和拖拽都只修改本地排序草稿，不立即写入数据库。

对话框底部使用 `保存` / `取消`：

- `保存`：一次性提交最终顺序
- `取消`：丢弃本次排序会话的所有调整

### Save Semantics

排序对话框打开时，从 manager 读取当前插件列表并按当前顺序生成本地草稿列表。

- 用户在对话框中的所有操作都只改草稿列表。
- 点击 `保存` 时，将草稿里的最终 `plugin_id` 顺序一次性提交给 manager。
- 点击 `取消` 时，不做任何持久化写入。

这种“先编辑，再提交”的模型更适合连续做多次排序操作，也避免拖一次就触发一次数据库更新。

## Architecture

### Dialog Responsibilities

[plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py) 负责：

- 在主插件管理页增加 `调整顺序` 入口
- 打开专用排序对话框
- 在排序保存成功后调用 `reload_plugins()`

新的排序对话框负责：

- 维护本地排序草稿
- 提供拖拽、置顶/置底、上移/下移
- 统一处理保存与取消

排序对话框不直接操作 repository，而是通过 plugin manager 提交最终顺序，保持 UI 与存储实现解耦。

### Manager Contract

[plugins/__init__.py](/home/harold/workspace/atv-player/src/atv_player/plugins/__init__.py) 需要新增一个批量重排接口，例如：

```python
def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
    # validate and persist final order
```

语义要求：

- 参数表示用户确认后的完整最终顺序
- manager 负责校验该顺序与当前插件集合一致
- 校验通过后，把顺序提交给 repository

现有 `move_plugin(plugin_id, direction)` 保留，继续给主插件管理页的单步微调入口使用。专用排序对话框不应循环调用 `move_plugin(...)`，否则一次长距离拖拽会退化为多次相邻交换。

### Repository Contract

[repository.py](/home/harold/workspace/atv-player/src/atv_player/plugins/repository.py:200) 目前只有 `move_plugin(plugin_id, direction)`。

需要新增一个按最终顺序重写 `sort_order` 的接口，例如：

```python
def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
    # rewrite sort_order from the final ordered ids
```

该接口负责：

- 读取当前插件集合
- 校验传入的 `plugin_id` 集合与当前数据库中的插件集合完全一致
- 按传入顺序从 `0` 开始重写所有插件的 `sort_order`

如果集合不一致，则抛出明确错误而不是静默覆盖，避免排序窗口打开后插件列表被外部改动时写回旧草稿。

## Conflict Handling

排序是一个草稿型操作，因此需要处理“窗口打开后，插件列表已发生变化”的情况。

推荐做法：

- 保存前由 manager 或 repository 对当前插件集合做一次一致性校验。
- 如果发现有插件新增、删除，或 `plugin_id` 集合不匹配，则拒绝保存。
- UI 弹出提示，例如“插件列表已变化，请重新打开排序窗口”，并保留当前草稿，供用户决定是否手动记录后重来。

这比静默覆盖当前顺序更安全，也更符合“排序窗口基于一个快照编辑”的语义。

## Error Handling

- 排序保存失败时，对话框不自动关闭。
- 失败后保留当前草稿和当前选中项，用户可以重试或取消。
- 取消关闭时不提示保存草稿；本次会话的修改直接丢弃。

排序对话框内部不负责处理插件刷新错误、加载错误或启用状态切换错误，因为这些都不属于排序职责范围。

## Testing

至少覆盖以下场景：

- 打开排序窗口时，初始顺序与主插件管理页一致。
- 拖拽后点击 `保存`，会一次性写入新的 `sort_order`。
- 点击 `取消`，不会修改数据库中的顺序。
- `置顶`、`置底`、`上移`、`下移` 都只影响本地草稿，不提前写库。
- 保存成功后，主插件管理页重新加载并显示新的顺序。
- 保存前若插件集合变化，提交会被拒绝，并向用户显示明确提示。
- 主插件管理页原有 `move_plugin(plugin_id, direction)` 微调路径继续可用。

## Risks

- 如果专用排序对话框仍然复用多次 `move_plugin(...)`，长距离排序的交互收益会被实现细节抵消。
- 如果保存时不校验插件集合一致性，外部新增或删除插件时可能发生静默覆盖。
- 如果主插件管理页继续堆叠更多排序按钮，新的专用排序入口价值会被界面复杂度抵消。

## Recommendation

采用“主界面轻量微调 + 专用排序对话框批量提交”的方案。

这是对当前插件管理结构最稳妥的扩展：

- 不破坏已有的主界面操作习惯
- 能显著改善长距离调整顺序的体验
- 保持排序逻辑边界清晰，只在保存时一次性落库
- 为后续增加键盘快捷键或更细的列表交互留出空间
