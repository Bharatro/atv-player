# Bilibili Grouped Playlist Tree Design

## Summary

B站详情页当前已经能返回多个播放分组，例如 `BiliBili`、`相关视频`、`UP主视频`，播放器也会把这些分组作为独立 `playlists` 处理。但播放器侧目前只能展示“当前线路的平铺列表”，`上一集 / 下一集 / 自动连播` 也只会在当前 `session.playlist` 内顺序推进，无法满足“按分组树展开浏览，并跨分组顺序播放”的需求。

这个方案把 B 站详情的播放列表展示扩展成两种可切换模式：

- `普通列表`：保持现有分组切换和单组播放列表
- `分组树`：把 B 站所有分组展示成可展开折叠的树，并按树中从上到下、组内从前到后的顺序播放

实现重点不是改 B 站 controller 的数据结构，而是在播放器中基于现有 `request.playlists` 增加一套 B 站专属树状展示和顺序映射逻辑。

## Goals

- 为 B 站播放会话增加“普通列表 / 分组树”两种播放列表展示模式。
- 分组树支持任意数量的 B 站分组，不只限于 `BiliBili / 相关视频 / UP主视频`。
- 每个分组都支持展开折叠。
- 在分组树模式下，点击叶子节点可以直接播放对应视频。
- 在分组树模式下，`上一集 / 下一集 / 自动连播` 按整棵树的顺序跨分组推进。
- 新模式只对 B 站生效，不影响其他来源。
- 通过高级设置保存该模式开关。

## Non-Goals

- 不把树状播放列表扩展成全局通用播放器能力。
- 不要求其他 controller 产出树形结构。
- 不修改 B 站详情 API 的返回格式。
- 不重做播放器整体布局。
- 不在本次改动里增加会话内临时切换按钮。

## Scope

主要改动范围：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/player_window.py`

主要验证范围：

- `tests/test_player_window_ui.py`
- `tests/test_app.py`

## User Experience

这个功能是 B 站专属的全局播放设置，入口放在“高级设置 > 播放设置”。

建议增加一个布尔配置项：

- `B站播放列表显示为分组树`

行为规则：

- 关闭时，B 站播放会话继续使用当前模式：
  - 顶部显示 `playlist_group_combo`
  - 下方列表只显示当前分组的内容
  - `上一集 / 下一集 / 自动连播` 只在当前分组内推进
- 开启时，且当前会话 `source_kind == "bilibili"`：
  - 隐藏 `playlist_group_combo`
  - 隐藏 `playlist_source_combo`
  - 右侧播放列表改为树状控件
  - 顶层节点显示分组名
  - 子节点显示该分组下的视频条目
  - `上一集 / 下一集 / 自动连播` 按整棵树的顺序推进

非 B 站会话即使开关打开，也继续使用现有列表模式，不显示树状控件。

## UI Design

播放器当前播放列表区域使用 `QListWidget`。这次改动需要在播放器窗口内同时支持：

- 现有 `QListWidget` 普通列表
- 新的 `QTreeWidget` 分组树

建议保留现有 `self.playlist`，新增一个专用于 B 站树模式的 `self.bilibili_playlist_tree`，二者在同一位置互斥显示。

显示规则：

- 不是 B 站会话：只显示 `self.playlist`
- 是 B 站会话且开关关闭：只显示 `self.playlist`
- 是 B 站会话且开关开启：只显示 `self.bilibili_playlist_tree`

树控件规则：

- 顶层节点是分组，例如 `BiliBili`、`相关视频`、`UP主视频`
- 每个顶层节点可展开折叠
- 叶子节点对应具体 `PlayItem`
- 顶层节点不可触发播放
- 默认展开所有分组，避免额外点击才能顺序浏览
- 当前播放项所在叶子节点需要有明显高亮
- 当前播放项之前的叶子节点使用较弱样式，保持和现有列表“已播 / 当前 / 未播”的语义一致

标题显示仍沿用现有 `playlist_title_mode` 和 `playlist_item_display_title(...)` 逻辑，避免树模式和普通模式出现不同标题来源。

## Data Model

不修改 B 站 controller 当前的核心输出语义。

`BilibiliController.build_request()` 继续返回：

- `playlists`: 每个分组一个 `list[PlayItem]`
- `playlist_index`: 当前分组索引
- `playlist`: 当前默认分组

树模式所需的跨组顺序能力不放到 controller 层，而放到 `PlayerWindow` 的 B 站专属视图状态中。

建议新增一个配置字段到 `AppConfig`：

- `bilibili_grouped_playlist_tree_enabled: bool = False`

不建议在 `OpenPlayerRequest` 或 `PlayerSession` 上新增通用树模型字段，因为这个能力只服务 B 站 UI 展示，放到会话通用模型里只会扩大影响面。

## Tree Ordering Model

树模式的关键是把原始分组 `session.playlists` 映射成一条“顺序播放序列”。

定义：

- `grouped_playlists`: 原始的 `session.playlists`
- `tree_flat_playlist`: 按分组顺序展开后的扁平列表
- `tree_flat_index_by_item`: `id(item)` 到扁平索引的映射
- `tree_item_by_flat_index`: 扁平索引到树叶子节点的映射

展开顺序固定为：

1. 按 `session.playlists` 的原始组顺序遍历
2. 每组内按原始 `PlayItem` 顺序遍历

例如：

- `BiliBili`: A
- `相关视频`: B, C
- `UP主视频`: D, E

树模式下的顺序播放列表为：

- A, B, C, D, E

这样既满足“3个分组顺序播放”，也天然兼容电视剧、动画等拥有更多分组的场景。

## Playback Behavior

当前播放器所有核心播放行为都围绕 `session.playlist` 和 `current_index` 运转。树模式若只改显示，不改活动播放列表，则无法跨分组自动连播。

因此树模式下需要临时切换“活动播放列表语义”：

- 原始分组数据仍保存在 `session.playlists`
- 当前活动播放序列改为 `tree_flat_playlist`
- `current_index` 改为该扁平顺序列表中的索引

具体规则：

- 进入 B 站树模式时：
  - 基于 `session.playlists` 生成 `tree_flat_playlist`
  - 从当前播放项定位到对应的扁平索引
  - 之后 `play_next()`、`play_previous()`、`_handle_playback_finished()` 都沿用现有逻辑，因为它们天然只依赖当前活动 `session.playlist`
- 退出树模式或非树模式时：
  - 当前活动播放列表恢复为当前分组 `session.playlists[session.playlist_index]`
  - `current_index` 恢复为当前项在当前分组中的组内索引

这意味着树模式本质上是 B 站会话的一种播放上下文切换，而不是单纯换一个控件。

## Source Group Interaction

树模式和现有分组切换控件是两套互斥交互：

- 普通列表模式：`playlist_group_combo` 正常工作
- 树模式：隐藏来源切换控件，不再允许用户只切到某一个分组视角

原因：

- 树模式的目标是把所有分组视为一条完整顺序链路
- 若保留来源切换控件，会同时存在“当前分组播放”和“全树顺序播放”两套相互冲突的导航语义

因此树模式下，右侧树就是唯一的播放列表入口。

## Tree Click Behavior

点击行为分两类：

- 点击顶层分组节点：只展开或折叠，不触发播放
- 点击叶子节点：播放对应 `PlayItem`

播放叶子节点时：

- 从树节点取出对应 `PlayItem`
- 用 `id(item)` 查找它在 `tree_flat_playlist` 中的扁平索引
- 复用现有 `_play_item_at_index(...)` 路径

这样可以避免复制 `PlayItem`，继续使用同一个对象承接：

- playback loader
- danmaku
- subtitles
- detail fields
- metadata hydration

## Dynamic Updates And Replacement Playlists

播放器内存在替换当前播放列表的逻辑，例如网盘展开或播放 loader 返回 replacement playlist。

B 站树模式需要明确兼容规则：

- 如果当前会话不是 B 站树模式，保持现有逻辑
- 如果当前会话是 B 站树模式，并且替换只影响当前活动项所属的原始分组：
  - 先更新 `session.playlists` 中对应分组的列表
  - 重新生成 `tree_flat_playlist`
  - 尽量根据当前 `PlayItem` 重新定位扁平索引

定位失败时按以下回退：

1. 同分组内相同组内索引
2. 同分组最后一个有效项
3. 整棵树第一项

这样可以避免刷新后直接丢失当前播放上下文。

## History And Progress

这次改动不扩展历史记录结构，继续沿用现有：

- `playlistIndex`
- `episode`

原因：

- 该功能是 B 站专属展示模式，不是新的通用数据模型
- 历史恢复首先要保证与现有普通模式兼容

树模式下的恢复策略：

- 会话打开时仍按原始 `playlistIndex + episode` 恢复到具体 `PlayItem`
- 若当前配置启用树模式，再把该 `PlayItem` 映射到扁平树索引

进度上报也继续基于当前真实 `PlayItem` 和 `session.source_vod_id`，不需要区分普通模式或树模式。

## Error Handling

- `session.playlists` 为空时，不显示树控件。
- 某个分组为空时，不创建空顶层节点。
- 树模式生成的扁平列表为空时，回退到普通列表渲染。
- 当前项无法映射回扁平索引时，不抛异常，回退到第一项。
- 点击树顶层节点时不触发播放，也不污染当前索引。
- 关闭树模式时若当前项不在当前 `playlist_index` 对应分组中，则用它所属分组作为新的活动分组。

## Testing

`tests/test_player_window_ui.py` 应覆盖：

- B 站会话且开关关闭时，仍显示普通列表和分组切换
- B 站会话且开关开启时，显示树控件并隐藏分组切换
- 树中顶层节点数量与原始分组数量一致
- 点击分组节点只折叠展开，不触发播放
- 点击叶子节点会播放对应视频
- `play_next()` 能从组 1 的最后一项跳到组 2 的第一项
- 播放结束自动连播能跨组推进
- 非 B 站会话即使开关开启，也不显示树控件

`tests/test_app.py` 或相关设置测试应覆盖：

- 新配置项能从 `SettingsRepository` 正确加载默认值
- 高级设置保存后配置项能持久化
- 重新打开设置时复选框状态正确回显

## Implementation Notes

建议实现顺序：

1. 先加配置字段、存储默认值和高级设置复选框
2. 再在 `PlayerWindow` 增加树控件和模式判断
3. 再补“原始分组 <-> 树扁平列表”的映射辅助方法
4. 最后接入点击播放、`play_next()`、自动连播和替换列表后的重新映射

核心原则：

- controller 不改接口语义
- 树模式不复制业务对象，只做引用映射
- 非 B 站路径保持零行为变化
