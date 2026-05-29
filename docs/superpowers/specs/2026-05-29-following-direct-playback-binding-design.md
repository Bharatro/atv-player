# 追更直接播放绑定 Design

## Summary

追更详情页需要在条目有更新后，让用户直接进入上次使用的播放来源，并由现有播放历史恢复分集、线路和播放位置。同时保留现有“搜索播放”入口。播放器保存播放记录时，同步更新追更记录里的最近播放来源，并用当前播放源可见集数前进更新追更的最新集数。

## Goals

- 在追更记录中保存最近一次实际播放使用的来源类型、来源 key 和 vod_id。
- 追更详情页提供直接播放入口，优先打开最近播放来源。
- 继续保留“搜索播放”作为重新查找片源的入口。
- 打开直接播放来源后，继续依赖现有本地播放历史恢复播放位置、分集和线路。
- 播放窗口更新播放记录时，同步更新追更记录。
- 切换到其他来源默认播放较早集数时，不覆盖最近播放来源绑定；只有当前播放集数达到追更当前进度或更靠后时才更新绑定。
- 播放源列表显示出更多集数时，可以前进更新追更记录里的 `latest_episode`，不做回退。

## Non-Goals

- 不在追更记录中重复保存播放位置、分集索引、线路索引或速度。
- 不替换现有播放历史恢复机制。
- 不移除“搜索播放”。
- 不让播放源集数回退覆盖元数据或已记录的最新集数。
- 不改变收藏、历史页或全局搜索的既有行为。

## Architecture

复用现有追更和播放历史边界：

- `FollowingSourceBinding` 继续作为追更与内部播放源的绑定模型，只需要 `source_kind`、`source_key`、`vod_id` 参与本次直接播放。
- `FollowingController` 增加面向播放器的绑定更新入口。它根据追更 id 更新或置顶匹配的 `source_bindings`，但只有当前播放进度不早于追更当前进度时才更新最近播放绑定；播放源最新集数大于现有值时更新 `latest_episode`。
- `MainWindow._report_player_item_following_progress()` 在播放器满足进度上报阈值后，继续更新观看进度，并同步上次播放来源绑定。
- `FollowingDetailPage` 增加直接播放信号和按钮状态。存在可用绑定时按钮可点；不存在绑定时保留“搜索播放”作为主要可用路径。
- `MainWindow` 处理追更直接播放信号，根据绑定调用现有来源控制器的 `build_request` 或 `build_request_from_detail`，再交给现有 `_start_open_request()`。
- 播放历史仍由各来源现有 `playback_history_loader` / `playback_history_saver` 负责，播放器创建 session 时自动恢复。

## Data Flow

播放中：

1. 播放窗口保存播放记录。
2. 播放窗口调用追更进度 reporter。
3. `MainWindow` 找到匹配追更记录。
4. `FollowingController` 更新当前观看进度。
5. `FollowingController` 判断当前播放集数是否达到追更当前进度；例如已在来源 1 看到第 20 集，切到来源 2 默认播放第 1 集时，不更新最近播放来源绑定。
6. 判断通过后，`FollowingController` 保存最近播放来源绑定：`source_kind`、`source_key`、`vod_id`。
7. 如果当前播放列表推断出的最高集数大于追更现有 `latest_episode`，更新 `latest_episode` 并计算更新状态。

追更详情直接播放：

1. 用户打开追更详情。
2. 页面展示“继续播放”和“搜索播放”。
3. “继续播放”读取追更记录首个最近播放绑定。
4. `MainWindow` 按绑定来源构建播放请求。
5. 播放器打开后通过现有播放历史自动恢复播放位置。

## Source Routing

直接播放只支持已有可路由来源：

- `browse` 使用 `browse_controller.build_request_from_detail(vod_id)`。
- `spider_plugin` 和 `plugin` 使用 `_plugin_controller_by_id(source_key).build_request(vod_id)`。
- `telegram`、`bilibili`、`youtube`、`emby`、`jellyfin`、`feiniu` 使用对应控制器的 `build_request(vod_id)`。
- `direct_parse` 不作为追更直接播放绑定的首选来源；该类播放仍可通过搜索或历史入口进入。

无法路由或控制器缺失时，页面显示错误，不删除绑定。

## Testing

Focused tests should cover:

- repository/controller updates source binding with only `source_kind`、`source_key`、`vod_id`。
- controller does not update source binding when a newly switched source is playing an earlier episode than the current following progress.
- controller updates source binding when the newly switched source reaches the current following progress or a later episode.
- controller updates playback-source latest episode only when it advances.
- main window progress reporter updates both progress and source binding.
- following detail page emits direct-play request while preserving search-play.
- main window routes a following direct-play binding to the correct source request.
- direct-play request relies on existing playback history hooks instead of adding duplicated resume fields.
