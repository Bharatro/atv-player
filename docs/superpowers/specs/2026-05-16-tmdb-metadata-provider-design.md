# TMDB Metadata Provider Design

## Summary

在现有媒体增强链路上新增真实 `TMDBProvider`，并把当前“本地豆瓣优先，`alist-tvbox` fallback”的隐式逻辑改成显式 provider 链：

- `LocalDoubanProvider`
- `TMDBProvider`
- `RemoteDoubanProvider`

最终增强优先级为：

- `本地豆瓣 > TMDB > alist-tvbox豆瓣`

这里的“优先级”不是简单按 provider 整体覆盖，而是按字段区分：

- 豆瓣优先：`简介`、`评分`、`豆瓣 ID`
- TMDB 优先：`海报`、`背景图`、`年份`、`演员`、`导演`、`类型`、`别名`、`IMDb ID`、`TMDB ID`

另外，TMDB 搜索时必须使用 `category_name` 推断媒体类型，避免把电影和剧集混搜导致错配。

## Goals

- 接入真实 TMDB v3 API，使用现有 `TMDB API Key` 配置项。
- 在播放器详情页的媒体增强中，按 `本地豆瓣 > TMDB > alist-tvbox豆瓣` 的顺序工作。
- 保持 `search(title)`、`get_detail(id)` 的统一 provider 接口不变。
- 使用 `category_name` 推断 TMDB 搜索目标是 `movie` 还是 `tv`。
- 不让单个 provider 的失败中断整个 metadata hydration。

## Non-Goals

- 本轮不接入 TMDB season/episode 级精确映射。
- 本轮不做 TMDB 多语言切换，默认使用 `zh-CN`。
- 本轮不新增用户可配置的 provider 排序。
- 本轮不接入爱奇艺、腾讯视频、B站 metadata provider。

## Current Problem

当前代码里：

- `metadata_tmdb_api_key` 已能保存，但没有真实消费方。
- `DoubanProvider` 同时承担本地豆瓣与 `alist-tvbox` fallback 编排。
- 外部增强只有豆瓣来源，海报/背景图/别名/IMDb ID/TMDB ID 这类字段补全能力不足。
- TMDB 搜索如果不区分电影和剧集，容易把名称相同的作品错配到错误类型。

## Approach Options

### Option A: Keep a single `DoubanProvider` and add TMDB inside it

做法：

- 保留当前 `DoubanProvider`
- 在其内部串行尝试本地豆瓣、TMDB、远程豆瓣

优点：

- 表面改动少

缺点：

- provider 职责失控
- 后续再加其他来源时会继续膨胀

### Option B: Split metadata sources into explicit providers

做法：

- 新增 `LocalDoubanProvider`
- 新增 `TMDBProvider`
- 新增 `RemoteDoubanProvider`
- `AppCoordinator` 显式按顺序组装 provider 列表

优点：

- 边界清晰
- 缓存键和错误边界独立
- 以后继续加 provider 不需要重写既有类

缺点：

- 需要拆分当前 `DoubanProvider`
- 测试面会扩大

### Option C: Add a generic provider router layer

做法：

- 在 `MetadataHydrator` 前再加一层统一调度器

优点：

- 框架完整

缺点：

- 对当前需求过重
- 增加额外抽象，没有立刻收益

## Decision

采用 **Option B**。

原因：

- 用户已经明确了 provider 顺序：`本地豆瓣 > TMDB > alist-tvbox豆瓣`
- 这个顺序天然适合映射为显式 provider 链，而不是塞进一个 provider 的内部 fallback
- TMDB 和豆瓣的字段优势不同，拆开后更容易实现字段级优先级

## Design

### 1. Provider architecture

外部 metadata provider 链改成：

- `LocalDoubanProvider`
- `TMDBProvider`
- `RemoteDoubanProvider`

插件来源则变成：

- `CustomPluginProvider`（如果插件返回 metadata）
- `LocalDoubanProvider`
- `TMDBProvider`
- `RemoteDoubanProvider`

普通内置来源变成：

- `LocalDoubanProvider`
- `TMDBProvider`
- `RemoteDoubanProvider`

行为约束：

- `LocalDoubanProvider`
  - 只负责本地豆瓣搜索和详情
  - 风控、解析失败、无结果时直接返回空
- `TMDBProvider`
  - 只负责 TMDB 搜索和详情
  - 仅当 `metadata_tmdb_api_key` 非空时启用
- `RemoteDoubanProvider`
  - 只负责 `alist-tvbox /api/movies` 搜索和详情
  - 作为最后豆瓣兜底

### 2. TMDB client

新增 `TMDBClient`，职责仅限 TMDB v3 HTTP 封装。

接口：

- `search_movie(title: str, year: str = "") -> list[dict[str, object]]`
- `search_tv(title: str, year: str = "") -> list[dict[str, object]]`
- `get_movie_detail(tmdb_id: str | int) -> dict[str, object]`
- `get_tv_detail(tmdb_id: str | int) -> dict[str, object]`

认证：

- 使用官方支持的 application auth `api_key` 查询参数

请求参数：

- 默认 `language=zh-CN`
- movie 搜索使用 `year`
- tv 搜索使用 `first_air_date_year`

详情扩展：

- movie:
  - `append_to_response=external_ids,images,alternative_titles,credits`
- tv:
  - `append_to_response=external_ids,images,alternative_titles,aggregate_credits`

图片：

- `TMDBClient` 懒加载 `/configuration`
- 根据 `secure_base_url` 和 `poster_sizes` / `backdrop_sizes` 拼接最终图片 URL

### 3. `category_name`-driven TMDB media type inference

TMDB 搜索前，先根据 `MetadataQuery.category_name` 推断媒体类型：

- 明确电影：
  - `category_name` 包含 `电影`、`影片`、`movie`
- 明确剧集：
  - `category_name` 包含 `电视剧`、`剧集`、`动漫`、`番剧`、`综艺`、`纪录片`、`tv`
- 不明确：
  - 先尝试 `movie`
  - 再尝试 `tv`

建议新增独立 helper：

- `infer_tmdb_media_type(query: MetadataQuery) -> str`

返回值：

- `"movie"`
- `"tv"`
- `""`

约束：

- 判为 `movie` 时，只调用 movie 端点
- 判为 `tv` 时，只调用 tv 端点
- 判不明时，按 `movie -> tv` 顺序尝试

### 4. TMDB matching rules

`TMDBProvider` 仍采用统一的 `search()` / `get_detail()` 接口。

搜索命中规则：

1. 按 `category_name` 先决定是搜 `movie` 还是 `tv`
2. 搜索结果里只接受“强匹配”
3. 若无强匹配，则返回空，不做弱匹配兜底

强匹配建议规则：

- 规范化标题后与查询标题相同
- 或 `alternative_titles` / `aliases` 中包含原始标题
- 如果查询提供 `year`，且结果里也有年份，则优先要求年份一致

`provider_id` 编码：

- movie: `movie:{id}`
- tv: `tv:{id}`

这样避免 TMDB movie/tv 数字 id 冲突。

### 5. Metadata field mapping and merge policy

`TMDBProvider` 输出统一 `MetadataRecord`，重点字段：

- `poster`
- `backdrop`
- `year`
- `overview`
- `rating`
- `actors`
- `directors`
- `genres`
- `aliases`
- `imdb_id`
- `tmdb_id`

字段级优先级如下：

- `overview`
  - `local_douban > remote_douban > tmdb > plugin > original`
- `rating`
  - `local_douban > remote_douban > tmdb > plugin > original`
- `poster`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `backdrop`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `year`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `actors`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `directors`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `genres`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `aliases`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `imdb_id`
  - `tmdb > local_douban > remote_douban > plugin > original`
- `tmdb_id`
  - `tmdb > plugin > original`
- `douban_id`
  - `local_douban > remote_douban > plugin > original`
- `title`
  - 保持现有策略，不主动覆盖原始 `vod_name`

实现建议：

- 给 `merge_metadata_record()` 增加字段级 provider priority 配置
- 不把“哪个 provider 能覆盖哪个字段”的逻辑散落在多个 if/else 中

### 6. App wiring

`AppCoordinator._build_metadata_hydrator_factory()` 调整为：

- 保持 `metadata_enhancement_enabled == False` 时直接返回 `None`
- 每次创建 provider 前重新读取最新配置
- 使用：
  - `metadata_douban_cookie`
  - `metadata_tmdb_api_key`

provider 构造建议：

- `LocalDoubanProvider(LocalDoubanClient(...))`
- `TMDBProvider(TMDBClient(api_key=...))`，仅在 key 非空时加入
- `RemoteDoubanProvider(api_client)`

缓存：

- 继续复用 `MetadataCache`
- provider 名分别为：
  - `local_douban`
  - `tmdb`
  - `remote_douban`

### 7. Error handling

- `TMDB API Key` 为空：
  - 不报错
  - 不注入 `TMDBProvider`
- `TMDB` 401 / 429 / 5xx / timeout：
  - provider 当次失败
  - 交给 `MetadataHydrator` 现有降级逻辑继续后续 provider
- 本地豆瓣风控：
  - `LocalDoubanProvider` 返回空
- `alist-tvbox` 豆瓣异常：
  - `RemoteDoubanProvider` 失败
  - 不阻塞整个播放器详情页

## Testing

### Unit tests

- `tests/test_metadata_tmdb_provider.py`
  - movie 搜索命中
  - tv 搜索命中
  - `category_name` 推断 movie
  - `category_name` 推断 tv
  - 不明确时 `movie -> tv` 顺序尝试
  - 强匹配过滤掉错误结果
  - movie 详情映射
  - tv 详情映射

- `tests/test_metadata_hydrator.py`
  - 本地豆瓣保留简介/评分
  - TMDB 补海报/背景图/别名/TMDB ID
  - provider 失败不会中断 hydration

- `tests/test_app.py`
  - 有 `metadata_tmdb_api_key` 时注入 `TMDBProvider`
  - 无 key 时不注入
  - 关闭媒体增强时仍整体短路

### Regression tests

- `tests/test_metadata_merge.py`
  - 覆盖字段级 provider 优先级
- `tests/test_main_window_ui.py`
  - 高级设置继续正确保存 `TMDB API Key`

## Risks

- `category_name` 的分类词可能不完整，导致 TMDB 走错 movie/tv 端点。
- 中文标题和 TMDB 中文别名并不总是完全一致，强匹配规则过严时会降低命中率。
- 若字段级 merge 设计做得太 ad-hoc，后续再接更多 provider 会迅速失控。

## Rollout

分三步落地：

1. TMDB client + TMDB provider
2. 拆分本地/远程豆瓣 provider，并更新 app wiring
3. 升级 merge 规则为字段级 provider 优先级，并补全测试
