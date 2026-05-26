# TMDB Following Discovery Design

## Goal

在现有“添加追更”弹窗里做一套轻量但完整的 TMDB 发现能力，覆盖：

- 热门榜单
- 推荐
- 筛选
- 现有搜索

并保持以下边界：

- 不改主窗口现有资源搜索页
- 不改追更页主界面结构
- 发现能力只放在“添加追更”弹窗内
- 推荐基于“最近活跃内容”，不是全量历史库扫描
- 推荐种子只使用“明确 TMDB ID”的追更和收藏

## Scope

本轮包含：

- 扩展“添加追更”弹窗为四标签发现入口
- 新增 TMDB discovery 数据层，统一承接推荐 / 热门 / 筛选 / 搜索
- 新增基于最近活跃追更和收藏的推荐聚合逻辑
- 新增收藏到 TMDB 的明确绑定层，使收藏可参与推荐
- 新增热门榜单与 TMDB Discover 筛选查询
- 新增 discovery 结果缓存和推荐缓存

本轮不包含：

- 追更页主界面新增推荐区
- 主导航新增独立 TMDB 标签页
- 替换现有资源搜索
- 收藏标题自动模糊匹配 TMDB 并静默绑定
- 长期用户画像、学习型推荐或跨设备同步

## Current Problems

当前 TMDB 在项目里已经深接到：

- 元数据搜索与详情
- 追更详情
- 添加追更的 TMDB-only 搜索卡片

但还缺少“发现型”能力：

- 没有热门榜单入口
- 没有基于追更 / 收藏的推荐入口
- 没有可浏览的 TMDB 筛选入口
- 收藏没有稳定的 TMDB 身份，无法作为推荐种子

这导致“添加追更”仍偏向精确搜索，而不是一个能逛、能发现、能快速加追更的入口。

## User Experience

### Entry Point

用户点击“添加追更”后，打开的仍是现有对话框，但顶部改成四个一级标签：

- `推荐`
- `热门`
- `筛选`
- `搜索`

默认进入 `推荐`。

### Shared Result Cards

四个标签共用同一套结果卡片和交互。每个卡片显示：

- 海报
- 标题
- 年份
- 媒体类型
- 评分
- 简介摘要
- 已追更状态
- 已收藏状态
- 加入追更动作

结果列表保持现有卡片心智，不为每个标签分别设计不同结果容器。

### Search Tab

`搜索` 标签保留现有能力：

- TMDB 关键字搜索
- 粘贴 TMDB URL 直达
- 粘贴 Bangumi URL 直达
- 粘贴豆瓣 URL 直达

它不再是默认入口，而是精确查找入口。

### Recommendation Tab

`推荐` 是默认入口，面向“最近在看什么，就继续给我看什么”。

- 使用最近活跃的追更和收藏作为种子
- 追更权重大于收藏
- 最近播放 / 最近更新 / 最近添加的追更优先
- 已追更、已收藏项默认过滤
- 如果推荐结果不足，自动补位热门结果

### Trending Tab

`热门` 提供稳定、可逛的榜单入口，作为推荐冷启动和失败时的兜底层。

第一版推荐提供少量固定榜单，不引入复杂配置。

### Discover Tab

`筛选` 提供 TMDB Discover 条件浏览，不是全文搜索。

第一版只保留高价值条件，避免面板膨胀。

## Approved Direction

### Option A: Keep Search-Only Add-Following Flow

- 继续维持“手动搜索 + URL 粘贴”
- 不引入榜单、推荐、筛选

优点：

- 范围最小
- 不需要新增 discovery 数据层

缺点：

- 无法满足“TMDB 深度集成”的目标
- 仍然缺少发现能力

### Option B: Put Discovery Into Search Page

- 保持添加追更弹窗简单
- 把 TMDB 热门 / 推荐 / 筛选放进主窗口搜索页

优点：

- 可以做更完整的浏览器式页面

缺点：

- 用户明确要求保留现有资源搜索，不希望改到搜索页主路径
- 和“我要添加追更”这个使用场景距离更远

### Option C: Put Discovery Into Add-Following Dialog

- 在现有“添加追更”弹窗中增加 `推荐 / 热门 / 筛选 / 搜索` 四标签
- 保持追更主界面和资源搜索页不变

优点：

- 最贴合当前用户任务
- 复用现有追更添加心智
- 深度集成 TMDB，但不扩大到主导航重构

缺点：

- 对话框内部的数据和状态管理会变复杂

### Recommendation

采用 **Option C**。

这是用户已经确认的方向。

## Architecture

### Overview

本轮新增一层以 TMDB discovery 为中心的服务，而不是把推荐 / 热门 / 筛选逻辑直接散落到 dialog 和 controller 中。

整体分层：

- `TMDBClient`
  - 只负责 HTTP 请求与原始 payload
- `TMDBDiscoveryService`
  - 负责热门、筛选、搜索、推荐结果统一组装
- `RecommendationSeedBuilder`
  - 从追更和收藏里抽取最近活跃、具备明确 TMDB ID 的推荐种子
- `FavoriteTMDBBindingRepository`
  - 维护收藏到 TMDB 的明确绑定
- `FollowingController` / 或其下游 dialog controller glue
  - 负责把 discovery 结果接入“添加追更”弹窗
- `FollowingSearchDialog`
  - 负责标签、筛选控件、列表切换和加追更交互

### Core Models

建议新增三类核心模型。

#### `DiscoveryQuery`

描述一次发现请求：

- 入口类型：`recommendation | trending | discover | search`
- 页码 / 分页大小
- 媒体类型
- 榜单类型
- 筛选条件
- 搜索关键字

#### `DiscoveryItem`

统一承接四个入口的结果卡片字段：

- `provider="tmdb"`
- `provider_id`
- `tmdb_id`
- `media_type`
- `title`
- `year`
- `poster`
- `backdrop`
- `rating`
- `overview`
- `badges` / `source_label`
- `is_following`
- `is_favorited`

#### `RecommendationSeed`

仅在推荐链路内部使用：

- `tmdb_provider_id`
- `tmdb_id`
- `media_type`
- `seed_source`: `following | favorite`
- `activity_weight`
- `activity_timestamp`
- `reason_flags`

这些模型的目的，是把 discovery UI 从当前 `MetadataScrapeCandidate` 的搜索语义中解耦出来。

## Data Flow

### Dialog Startup

打开“添加追更”弹窗时：

1. 默认选中 `推荐`
2. 发起推荐查询
3. 如果推荐结果不足或推荐不可用，则自动回退并展示热门结果
4. 状态文案明确说明当前是“推荐”还是“推荐不足，已补充热门”

### Search

用户切到 `搜索`：

1. 输入关键字或粘贴 URL
2. URL 优先走已有直达识别
3. 非 URL 输入走 TMDB 搜索
4. 搜索结果映射为统一 `DiscoveryItem`
5. 与其他标签共用卡片渲染

### Trending

用户切到 `热门`：

1. 选择固定榜单
2. discovery service 调 TMDB 对应端点
3. payload 走缓存
4. 映射为 `DiscoveryItem`

### Discover

用户切到 `筛选`：

1. 配置筛选条件
2. 点击“应用筛选”
3. 调 TMDB discover 端点
4. payload 走缓存
5. 映射为 `DiscoveryItem`

### Recommendation

`推荐` 查询流程：

1. 从追更记录抽取具备明确 TMDB ID 的候选
2. 从收藏 TMDB 绑定层抽取具备明确 TMDB ID 的候选
3. 本地去重
4. 按最近活跃度和来源权重排序
5. 截断为固定上限的种子列表
6. 对每个种子拉少量 TMDB 推荐结果
7. 本地聚合并打分
8. 过滤掉已追更、已收藏和信息残缺项
9. 输出统一 `DiscoveryItem`

## Recommendation Design

### Seed Selection

推荐种子只使用“明确 TMDB ID”的内容。

#### Following Seeds

追更直接使用现有稳定字段：

- `provider`
- `provider_id`
- `external_ids`

符合以下之一即可视为可用 TMDB 种子：

- `provider == "tmdb"`
- `external_ids["tmdb"]` 存在

#### Favorite Seeds

收藏不直接从 `favorites` 表取 TMDB 身份，而是通过新增的收藏 TMDB 绑定层提供。

只有存在明确绑定的收藏才参与推荐种子构建。

### Activity Bias

推荐要明确偏向最近活跃内容，而不是覆盖整个历史库。

优先级信号：

- 追更高于收藏
- 有更新的追更高于无更新追更
- 最近播放的追更高于长期未动追更
- 最近添加的追更高于旧追更
- 最近更新过的收藏高于长期未动收藏

### Seed Truncation

为避免大库用户打开弹窗时请求失控：

- 先本地去重
- 再截断到固定种子上限，例如 `20-40`
- 每个种子只取少量推荐结果，例如 `10-20`

推荐请求数必须与“库总量”解耦，而与“最近活跃截断后种子数”绑定。

### Scoring

第一版只做可解释的加权聚合分，不做黑盒推荐。

分数组成：

- 来自多少不同种子推荐到同一候选
- 种子的来源权重
- 种子的活跃度权重
- 候选自身的 TMDB 质量信号作为轻微辅助：
  - `vote_average`
  - `vote_count`
  - `popularity`

不做：

- 文本相似度二次建模
- 年份接近度建模
- 跨类型惩罚或奖励

## Favorite TMDB Binding Design

### Why Separate Binding Storage

不要直接把 TMDB 字段塞进 `favorites` 主表。

原因：

- 收藏主表应继续代表源站收藏记录
- TMDB 绑定可能失效或被重绑，不应污染主记录
- 推荐种子、状态展示、未来的详情增强都可以复用独立绑定层

### Binding Rules

绑定策略保持保守：

- 只接受明确 TMDB identity
- 如果现有详情或元数据链路已拿到明确 `tmdb provider_id`，则保存绑定
- 如果没有明确 TMDB identity，则不强行猜测，不纳入推荐

本轮明确不做：

- 按收藏标题自动搜索 TMDB 并静默绑定

### Expected Usage

收藏 TMDB 绑定用于：

- 构建推荐种子
- 给 discovery 卡片标出“已收藏”
- 为后续收藏详情增强预留统一身份层

## Hot and Discover Design

### Trending Buckets

第一版热门只做有限的固定入口，避免对话框上方再叠复杂配置。

建议固定榜单包括：

- 热门剧集
- 热门电影
- 正在播出
- 本周趋势

热门结果主要用于：

- 独立浏览
- 推荐冷启动兜底
- 推荐失败兜底

### Discover Filters

第一版筛选条件控制在高价值、低复杂度集合：

- 媒体类型：电影 / 剧集 / 全部
- 排序：热门 / 评分 / 上映日期
- 年份
- 地区
- 类型
- 播出状态

筛选交互采用“修改条件后点击应用”，而不是每次改动都自动请求。

这样更适合桌面端，也更容易测试和缓存。

## Caching

### Trending and Discover Cache

热门和筛选结果按 query key 缓存：

- 榜单类型
- 媒体类型
- 筛选条件
- 页码

### Recommendation Cache

推荐不能直接按“全量追更 + 收藏列表”缓存。

应该按“截断后种子摘要 key”缓存：

- 种子 identity
- 种子来源
- 活跃版本信息

这样缓存 key 稳定且不会随着用户大库无限膨胀。

## Error Handling and Fallback

### No TMDB API Key

如果没有 TMDB API Key：

- `推荐 / 热门 / 筛选` 置灰
- 显示需要先配置 TMDB API Key
- `搜索` 中保留非 TMDB URL 直达能力

### Recommendation Fallback

如果出现以下情况：

- 没有足够推荐种子
- 推荐结果过少
- 推荐请求失败

则默认页自动回退到热门结果，不显示空白主视图。

### Discover and Search Failures

- 热门失败：显示错误并允许切换到搜索
- 筛选失败：保留筛选条件与上次结果
- 搜索失败：保留输入与上次结果

## Testing

需要覆盖以下层级。

### Recommendation Unit Tests

- 追更种子优先于收藏种子
- 最近活跃追更优先于旧记录
- 已追更、已收藏结果被过滤
- 同候选被多个种子推荐时分数累积
- 大库场景下只截取固定数量种子

### Favorite Binding Tests

- 只有明确 TMDB identity 才保存收藏绑定
- 没有明确 identity 时不生成绑定
- 收藏绑定可被推荐种子构建器正确读取

### Discovery Service Tests

- 热门请求正确映射到榜单 query
- Discover 请求正确映射筛选条件
- 搜索 / 热门 / 筛选 / 推荐都能统一输出 `DiscoveryItem`
- 推荐不足时正确回退热门
- cache key 稳定且区分不同 query

### Dialog UI Tests

- 默认进入 `推荐`
- 四标签切换工作正常
- 推荐不足时显示热门补位文案
- 结果卡片正确显示已追更 / 已收藏状态
- 搜索标签仍保留 URL 直达
- 加入追更行为在四标签下都可工作

## Implementation Notes

推荐的实现顺序：

1. 先补收藏到 TMDB 的明确绑定层
2. 抽出 recommendation seed builder
3. 扩展 TMDB client 需要的热门 / discover / recommendation 端点
4. 建立统一 discovery service 与 `DiscoveryItem`
5. 在 dialog 中加四标签和状态切换
6. 最后接缓存和回退文案

这个顺序能保证：

- 先把“身份层”补齐
- 再做推荐算法
- 最后接 UI，避免 UI 先行堆临时逻辑

## Open Questions Resolved

以下问题已经在本次讨论中确认：

- 发现能力不放资源搜索页
- 发现能力不放追更主界面
- 发现能力放在“添加追更”弹窗
- 保留现有资源搜索
- 默认入口是 `推荐`
- 内容范围是全量 TMDB 内容
- 推荐基于最近活跃内容
- 收藏只有明确 TMDB 绑定才参与推荐

