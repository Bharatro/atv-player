# Following TMDB Related Recommendations Design

## Goal

在“我的追更”详情页中展示当前媒体的 TMDB 关联推荐，并让推荐项能快速进入资源搜索或加入追更。

## Scope

- 在追更详情页“分集详情”下方、“演职员列表”上方新增“TMDB 关联推荐”区。
- 推荐区异步加载，不阻塞详情页首屏、分集加载或演职员渲染。
- 推荐来源只使用当前媒体明确的 TMDB 身份。
- 推荐项左键触发全局搜索。
- 推荐项右键菜单提供：
  - `搜索资源`
  - `加入追更`
- `加入追更` 复用现有 `FollowingController.add_candidate(DiscoveryItem)` 路径。

## Out Of Scope

- 不做个性化推荐算法。
- 不改变“添加追更”弹窗已有推荐/热门/筛选入口。
- 不把推荐直接作为播放源打开。
- 不自动为没有 TMDB 身份的追更做模糊匹配。

## Architecture

数据层复用现有 `TMDBDiscoveryService`、`DiscoveryItem` 和 TMDB client 的 recommendations 端点，新增单媒体推荐方法。`FollowingController` 从当前追更记录和详情快照中解析 TMDB provider identity，并提供详情页专用的 `load_related_recommendations(following_id)` 方法。

UI 层由 `FollowingDetailPage` 管理推荐区。`load_record()` 先渲染详情，再启动后台线程加载推荐；请求完成后通过 Qt signal 回到 UI 线程渲染推荐卡片。推荐卡片通过左键 signal 交给 `MainWindow` 启动全局搜索，通过右键菜单调用详情页已有 controller 加入追更。

## Data Flow

1. 用户打开追更详情页。
2. `FollowingDetailPage.load_record()` 加载并渲染详情。
3. 页面设置推荐区状态为“正在加载关联推荐...”。
4. 后台线程调用 `FollowingController.load_related_recommendations(following_id)`。
5. controller 解析当前记录的 TMDB identity：
   - 优先 `record.provider == "tmdb"` 且 `record.provider_id` 为 `tv:<id>` 或 `movie:<id>`。
   - 其次使用 `record.external_ids["tmdb"]`，媒体类型由 `record.provider_id` 或 `record.media_kind` 推断。
   - 再从 metadata bundle 的 TMDB source snapshot provider_id 中解析。
6. controller 调用 discovery service 的单媒体推荐方法。
7. UI 渲染横向推荐卡片，并隐藏当前已追更项。
8. 左键推荐项发出 `related_global_search_requested(title)`。
9. 主窗口收到 signal 后填入全局搜索框并启动全局搜索。
10. 右键 `加入追更` 调用 `controller.add_candidate(item)`，成功后显示提示并重新加载推荐状态。

## Error Handling

- 没有 discovery service：推荐区隐藏。
- 没有明确 TMDB identity：推荐区隐藏。
- 推荐请求失败：推荐区显示“关联推荐加载失败”。
- 推荐为空：推荐区显示“暂无关联推荐”。
- 加入追更失败：详情页状态栏显示失败信息。

## Testing

- `TMDBDiscoveryService` 可按单个 TMDB 媒体加载 recommendations 并复用缓存。
- `FollowingController` 能从记录、external ids、TMDB source snapshot 解析详情页推荐 identity。
- `FollowingDetailPage` 打开详情页时异步请求推荐，不阻塞首屏渲染。
- 推荐卡左键发出全局搜索 signal。
- 推荐卡右键菜单包含 `搜索资源` 和 `加入追更`。
- `MainWindow` 收到详情页推荐搜索 signal 后启动全局搜索。
