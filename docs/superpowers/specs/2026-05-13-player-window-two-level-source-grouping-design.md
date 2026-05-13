# Player Window Two-Level Source Grouping Design

## Summary

播放器窗口当前只支持单个“来源”下拉框，对应一层 `playlists` 列表。这个方案把来源选择扩展成明确的两级结构，用两个联动下拉框承载“大组”和“子源”，解决来源过多时单个下拉难以扫描的问题，同时保持现有选集列表、播放逻辑和大部分 controller 接口尽量稳定。

目标示例：

- 一级分组：`解析`、`百度`、`夸克`、`磁力`
- 二级子源：`解析1`、`百度1`、`百度2`、`夸克1`、`夸克2`、`夸克3`、`磁力1`

## Goals

- 在播放器窗口支持两级播放源分组。
- 用两个联动下拉框替换当前单个来源下拉框。
- 一级下拉只显示大组，二级下拉只显示当前大组下的子源。
- 保持当前选集列表继续展示“当前子源”的内容。
- 切换来源时尽量保持当前选集序号，减少观看打断。
- 兼容现有单层来源和旧的 `playlists` / `playlist_index` 数据路径。

## Non-Goals

- 不支持任意层级树。
- 不改成树控件或级联菜单。
- 不重做选集列表主体。
- 不重构播放 loader、解析、弹幕等核心播放链路。
- 不要求所有 controller 同时原生产出新结构。

## Scope

主要实现范围：

- `src/atv_player/models.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/plugins/controller.py`
- 相关调用方中 `OpenPlayerRequest` 到 `PlayerSession` 的传递

主要验证范围：

- `tests/test_player_controller.py`
- `tests/test_player_window_ui.py`
- `tests/test_spider_plugin_controller.py`

## UI Design

播放器左侧来源选择区域由一个来源下拉框改成两个联动下拉框：

- 一级下拉：大组选择，例如 `解析`、`百度`、`夸克`、`磁力`
- 二级下拉：当前大组下的子源，例如 `夸克1`、`夸克2`、`夸克3`

下方原有选集列表不变，始终展示当前子源的 `playlist`。

显示规则：

- 存在多个大组时，显示一级下拉。
- 当前大组存在多个子源时，显示二级下拉。
- 只有一个大组时，隐藏一级下拉。
- 当前大组只有一个子源时，隐藏二级下拉。
- 整体只有一个叶子来源时，两个下拉都隐藏。

这保证单层来源场景继续保持简洁，不会因为引入二级模型而强行显示多余控件。

## Data Model

这次改动只引入明确的两级来源结构，不做通用递归树。

建议新增两个模型概念：

- `PlaybackSourceGroup`
  - `label`: 大组名称，例如 `夸克`
  - `sources`: 当前大组下的子源列表
- `PlaybackSource`
  - `label`: 子源名称，例如 `夸克2`
  - `playlist`: 当前子源对应的 `list[PlayItem]`

`OpenPlayerRequest` 和 `PlayerSession` 增加：

- `source_groups: list[PlaybackSourceGroup]`
- `source_group_index: int`
- `source_index: int`

现有的 `session.playlist` 继续表示“当前正在播放的叶子子源 playlist”。这条语义不变，可以最大程度减少现有播放链路改动。

为兼容旧代码路径，现有字段先保留：

- `playlists`
- `playlist_index`

它们可以继续作为扁平叶子来源的兼容层存在，优先服务旧 controller、旧历史和未迁移逻辑。新 UI 和新选择状态以 `source_groups` 为准。

## Compatibility Normalization

`PlayerController` 负责把旧结构统一规范化成新的两级结构。

旧单层 `playlists` 输入应被规范化为：

- 每个叶子来源对应一个 `PlaybackSourceGroup`
- group `label` 使用该叶子来源的线路名，例如 `备用线`
- group 下只有一个 `PlaybackSource`
- source `label` 与 group `label` 相同

示例：

- 旧结构 `备用线`, `极速线`
- 规范化后：
  - group `备用线` -> source `备用线`
  - group `极速线` -> source `极速线`

这样一级下拉仍然可以承担当前单层切线功能，而二级下拉在单子源时自动隐藏。

对于天然两级来源的数据，controller 可以直接构造 `source_groups`，不必先扁平化再逆向重建。

## Selection Behavior

切换行为需要尽量减少观看中断。

一级分组切换规则：

- 用户切换到新大组时，二级下拉自动切换到该组第一个子源。
- 播放优先保持当前选集序号。
- 如果目标子源没有该序号，则退到最后一集。

二级子源切换规则：

- 优先保持当前选集序号。
- 如果目标子源没有该序号，则退到最后一集。

空列表保护：

- 目标子源为空时，不主动播放空源。
- 仍然刷新选集列表和来源状态，但不触发无效播放。

如果当前还没有开始播放，则来源切换后只在存在可播放项时进入播放。

## Playback Session Behavior

`session.playlist` 继续绑定当前叶子子源。

当用户切换一级或二级来源时：

- 先上报当前进度并停止当前播放
- 更新 `source_group_index` / `source_index`
- 更新 `session.playlist`
- 重新渲染选集列表
- 用新的目标选集索引重新加载当前项

现有依赖 `session.playlist` 的逻辑，例如：

- 播放启动
- 异步播放 loader
- 弹幕搜索与加载
- 字幕和音轨刷新
- 播放进度上报

都不需要知道两级结构的细节，只需要继续基于当前叶子子源工作。

## Dynamic Replacement Playlists

对网盘、磁力、占位播放项替换成真实文件列表这类动态场景：

- 只更新当前叶子子源的 `playlist`
- 不改动其他 group 或 source
- 当前 UI 继续停留在原来的大组和子源上

这意味着 replacement playlist 不能再简单理解为“更新当前线路”，而应理解为“更新当前叶子子源的内容”。

## History Persistence And Restore

历史记录需要从单个 `playlist_index` 扩展成两级来源状态：

- `source_group_index`
- `source_index`
- `episode`

恢复规则：

- 历史中的大组和子源都存在时，直接恢复到该叶子来源和选集。
- 大组存在但子源不存在时，退回该组第一个子源。
- 大组也不存在时，退回整体的第一个可用叶子来源。

旧历史兼容：

- 旧记录里只有 `playlist_index` 时，先按旧的扁平叶子顺序映射。
- 映射失败时，按新的降级规则回退到第一个可用叶子来源。

这样可以兼容已有播放历史，不要求一次性迁移所有历史数据。

## Spider Plugin Integration

`SpiderPluginController` 是当前最可能产出多来源结构的入口之一，应支持直接构造两级来源。

例如插件返回的多组线路如果天然可表达成：

- `解析` -> `解析1`
- `百度` -> `百度1`, `百度2`
- `夸克` -> `夸克1`, `夸克2`, `夸克3`
- `磁力` -> `磁力1`

则 controller 应直接构造 `source_groups`，并同步给当前叶子来源生成兼容层 `playlists`。

如果某个 controller 仍然只提供旧 `playlists`，则由 `PlayerController` 统一规范化，不要求 controller 在本次改动里全部重写。

## Error Handling

- 一级分组没有可用子源时，一级下拉可以展示该组，但切换后不触发播放。
- 二级子源为空时，不触发播放，选集列表显示空状态。
- 历史记录越界时，不抛异常，按降级规则回退。
- replacement playlist 为空时，不覆盖当前有效播放列表。

所有来源切换都应避免出现索引越界、空列表直接访问或 UI 状态与 `session.playlist` 不一致的问题。

## Testing

`PlayerController` 测试应覆盖：

- 旧单层 `playlists` 正确规范化为两级来源结构
- 多级来源正确选中当前 group/source
- 历史优先恢复到 group/source
- 历史失效时按降级规则回退

`PlayerWindow` 测试应覆盖：

- 一级/二级下拉的显示与隐藏规则
- 一级切换时二级自动切到第一个子源
- 来源切换时尽量保持当前选集序号
- 越界时回退到最后一集
- replacement playlist 只更新当前叶子子源

`SpiderPluginController` 测试应覆盖：

- 可直接产出两级来源结构
- 单层来源继续可播
- 新旧结构在 `OpenPlayerRequest` 到 `PlayerSession` 之间保持一致

## Risks And Mitigations

- 风险：现有大量逻辑默认只有一层 `playlists`。
  - 缓解：保持 `session.playlist` 语义不变，把两级结构收敛在归一化层和来源切换 UI。

- 风险：历史恢复与动态 replacement playlist 同时作用时状态错乱。
  - 缓解：明确“历史恢复只决定首次选中叶子来源”，“replacement 只更新当前叶子子源内容”。

- 风险：单层来源被两级模型污染，UI 变得冗余。
  - 缓解：通过显示规则隐藏无意义的一级或二级下拉。

## Result

完成后，播放器窗口可以在不引入树控件和任意层级复杂度的前提下，支持清晰的两级播放源分组。来源很多时用户先按大组缩小范围，再在二级下拉里选具体子源；单层来源场景继续保持当前简洁体验；播放、历史和动态解析路径则继续围绕当前叶子子源工作。
