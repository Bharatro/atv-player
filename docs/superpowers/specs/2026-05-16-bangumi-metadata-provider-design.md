# Bangumi Metadata Provider Design

## Summary

在现有 metadata provider 架构上新增独立 `BangumiMetadataProvider`，同时接入：

- 自动元数据增强 `MetadataHydrator`
- 播放器手动 `刮削` 对话框 `MetadataScrapeService`
- 剧集标题增强 `episode_title_resolver`

Bangumi 只对 `动漫 / 番剧 / ACG` 类目启用，不参与普通电影、电视剧、综艺等条目的 metadata 搜索与增强。

Bangumi 接入采用：

- 默认匿名可用
- `Access Token` 可选配置

即没有 token 也允许读取公开动画条目；如果用户配置了 token，则请求额外带上 `Authorization: Bearer <token>`。

字段策略上：

- 内置动漫文本元数据优先 `Bangumi`
- 视觉图像仍优先 `TMDB`
- 站点源继续承担补充与兜底

## Goals

- 新增真实 `BangumiMetadataProvider`，同时支持自动增强和手动 `刮削`。
- 仅在 `动漫 / 番剧 / ACG` 类目启用 Bangumi。
- 没有 token 时也能匿名读取公开条目。
- 有 token 时自动按 bearer token 模式请求。
- 利用 Bangumi 的季度番与单集标题数据，增强动漫剧集标题。
- 不让 Bangumi provider 的失败中断整个 metadata 链路。

## Non-Goals

- 本轮不接入 Bangumi 用户收藏、在看、评分同步等用户态能力。
- 本轮不新增用户可配置的 provider 排序 UI。
- 本轮不让 Bangumi 参与非动漫条目的 metadata 搜索。
- 本轮不重写现有 metadata cache、hydrator 或 scrape UI 架构。
- 本轮不做多语言切换配置，默认优先取中文可读字段并回退原题。

## Current Problem

当前代码里已经有：

- `MetadataHydrator` 自动增强链路
- `MetadataScrapeService` 手动 `刮削` 链路
- `TMDB`、豆瓣、B站、爱奇艺、腾讯等 provider
- 剧集标题增强链路

但动漫场景仍有明显缺口：

- 缺少一个专门的 ACG 元数据库源
- 中日文标题、别名、季度番识别能力不足
- 声优、制作信息这类动漫核心字段不完整
- 单集标题增强目前依赖站点源或 TMDB，不够稳定

Bangumi 正好补足这些能力，但必须以“动漫限定”的方式接入，避免把通用影视作品误引流到 Bangumi 造成错配。

## Approach Options

### Option A: Add Bangumi as an explicit standalone provider

做法：

- 新增 `BangumiClient`
- 新增 `BangumiMetadataProvider`
- `AppCoordinator` 显式组装 provider 顺序
- `merge`、`scrape`、`episode_title_resolver` 针对 Bangumi 做最小增量支持

优点：

- 完全符合现有 metadata provider 架构
- 自动增强和手动 `刮削` 自然复用
- 以后继续调优匹配、字段优先级、剧集标题增强都更清晰

缺点：

- 需要补 client、provider、配置、存储和测试

### Option B: Only add Bangumi to manual scrape

做法：

- Bangumi 只出现在播放器的手动 `刮削` 里

优点：

- 实现最小

缺点：

- 不满足“自动增强也要支持”的目标
- 动漫条目每次都要用户手动选择

### Option C: Fold Bangumi into an existing anime-oriented provider

做法：

- 把 Bangumi 请求逻辑塞进现有 `BilibiliMetadataProvider` 或别的 provider

优点：

- 表面文件数更少

缺点：

- 数据库源和站点源职责混杂
- 后续维护 provider 优先级和字段覆盖会变复杂

## Decision

采用 **Option A**。

原因：

- 用户明确要求 Bangumi 同时支持自动增强和手动 `刮削`
- 当前仓库已有稳定 provider 架构，Bangumi 适合作为标准 provider 接入
- Bangumi 和站点源、TMDB 的字段优势不同，拆开后更容易做字段级优先级控制

## Design

### 1. Provider activation and configuration

新增配置项：

- `metadata_bangumi_access_token: str = ""`

配置落点：

- `AppConfig`
- SQLite `app_config`
- `AdvancedSettingsDialog`

UI 文案：

- 字段名：`Bangumi Access Token`
- placeholder：`可选；留空时使用匿名访问`

行为：

- token 为空时，仍构建 `BangumiMetadataProvider`
- token 非空时，请求额外带上 `Authorization: Bearer <token>`
- 不新增独立总开关；只要元数据增强开启，Bangumi 就按动漫类目自动参与

### 2. Provider ordering

推荐 provider 顺序：

- `CustomPluginProvider`
- `BangumiMetadataProvider`
- `BilibiliMetadataProvider`
- `IqiyiMetadataProvider`
- `TencentMetadataProvider`
- `OfficialDoubanProvider`
- `TMDBProvider`
- `LocalDoubanProvider`

含义：

- 插件返回的 metadata 仍保持最高优先级
- 动漫场景优先使用 Bangumi 作为主元数据库源
- B站、爱奇艺、腾讯作为站点补充
- TMDB 提供更强的图片能力
- 豆瓣系作为兜底补充

### 3. Anime-only activation rules

Bangumi 只对动漫类目启用。

建议新增统一 helper：

- `is_bangumi_anime_query(query: MetadataQuery) -> bool`
- `is_bangumi_anime_context(context: MetadataContext) -> bool`

判定来源：

- `category_name`
- `type_name`

命中词：

- `动漫`
- `动画`
- `番剧`
- `ACG`
- `anime`

自动增强：

- `BangumiMetadataProvider.can_enrich(...)` 对非动漫 context 返回 `False`

手动 `刮削`：

- `MetadataScrapeService.provider_options_for_query(query)` 或等价过滤逻辑
- 非动漫条目不展示 `Bangumi` 选项，而不是展示后返回空结果

剧集标题增强：

- 只有动漫条目才让 Bangumi 参与剧集标题候选

### 4. Bangumi client

新增 `BangumiClient`，职责仅限 Bangumi API HTTP 封装。

基础约束：

- 所有请求带规范 `User-Agent`
- token 非空时带 `Authorization: Bearer <token>`
- 默认超时 `10s`
- 使用 `https://api.bgm.tv/v0` 端点

接口建议：

- `search_subjects(keyword: str) -> list[dict[str, object]]`
- `get_subject(subject_id: int | str) -> dict[str, object]`
- `get_subject_persons(subject_id: int | str) -> list[dict[str, object]]`
- `get_subject_characters(subject_id: int | str) -> list[dict[str, object]]`
- `get_episodes(subject_id: int | str) -> list[dict[str, object]]`

认证模式：

- 匿名读取：允许公开条目搜索与详情读取
- token 模式：相同请求自动附带 bearer token

错误处理：

- 非 2xx、超时、响应结构异常都抛出 provider 可捕获异常

### 5. Search strategy

`BangumiMetadataProvider.search(...)` 只在动漫 query 下工作。

搜索流程：

1. 读取原始标题
2. 如果标题带明显季数后缀，再生成“去季数后缀”的补充搜索词
3. 按搜索词依次调用 `search_subjects`
4. 汇总结果并按 `subject_id` 去重
5. 只保留动画类 subject
6. 映射成 `MetadataMatch`

只保留的 subject 类型：

- 动画 / 番剧 对应类型

搜索命中信息写入 `MetadataMatch.raw`：

- `name`
- `name_cn`
- `date`
- `images`
- `tags`
- `infobox`
- `rank`
- `score`
- `aliases`
- `season_number`
- `episodes_count`
- `categories`

`provider_id` 编码：

- `subject:{id}`

不额外做 season 编码：

- Bangumi 的季度番通常本身就是独立 subject
- 这样更符合 Bangumi 的数据模型

### 6. Matching rules

Bangumi 使用保守匹配，不做激进弱匹配。

强匹配判断顺序：

1. 规范化后与 `name_cn` 完全一致
2. 规范化后与 `name` 完全一致
3. 规范化后命中别名集合
4. 如果查询提供年份且结果可解析年份，则优先要求年份一致
5. 如果查询标题包含季数，优先要求季数一致

补充规则：

- 中文别名和日文原题都参与匹配
- 如果标题近似但年份、季数明显冲突，直接拒绝
- 没有高置信结果时返回空，让后续 provider 兜底

`MetadataMatch.score`：

- 使用现有 `score_match(...)` 体系
- 为 Bangumi 增加“动漫类精确标题命中”的 provider 加权

### 7. Detail mapping

`BangumiMetadataProvider.get_detail(...)` 拉取：

- subject
- subject persons
- subject characters
- episodes

再统一映射为 `MetadataRecord`。

字段映射建议：

- `provider`: `bangumi`
- `provider_id`: `subject:{id}`
- `title`: `name_cn`，为空时回退 `name`
- `original_title`: `name`
- `year`: 从放送日期提取年份
- `poster`: 优先大图，再回退通用图
- `overview`: `summary`
- `rating`: 评分均值
- `genres`: 从标签与 infobox 解析的动画类型
- `country`: 从 infobox 或标签提取
- `language`: 从 infobox 或标签提取
- `aliases`: 中日文标题、别名、罗马字标题去重合并
- `actors`: 角色配音表里的声优名
- `directors`: staff 中的监督、导演、系列构成等核心制作人员

`detail_fields` 建议补充：

- `Bangumi ID`
- `原题`
- `别名`
- `话数`
- `放送开始`
- `放送结束`
- `声优`
- `制作公司`

### 8. Episode title enhancement

Bangumi 的剧集列表需要接入现有 `episode_title_resolver`。

做法：

- 在 detail 阶段把剧集列表写入 `record` 对应候选的 `raw["episodes"]`
- 每集至少保留：
  - `sort`
  - `name`
  - `name_cn`
  - `type`
  - `airdate`

`episode_title_resolver` 新增 `bangumi` 分支：

- 优先取 `name_cn`
- 没有中文标题时回退 `name`
- 只使用正片剧集，不把 SP、OP、ED、PV 等特殊条目默认映射到主播放列表

剧集标题优先级调整为：

- `plugin`
- `bangumi`
- `bilibili`
- `tmdb`
- `tencent`
- `iqiyi`

原因：

- 动漫场景下，Bangumi 的单集标题比通用影视库更稳定
- 站点源标题可能带平台化修饰，Bangumi 更接近数据库标准标题

`MetadataScrapeService.build_episode_title_playlist(...)` 也需要把 `bangumi` 纳入自动候选顺序。

### 9. Merge policy

Bangumi 是动漫文本元数据强源，但不是图片优先源。

建议调整字段优先级：

- `overview`
  - `plugin > bangumi > official_douban > tmdb > bilibili/tencent/iqiyi > local_douban`
- `rating`
  - `plugin > bangumi > official_douban > tmdb > bilibili/tencent/iqiyi > local_douban`
- `poster`
  - `tmdb > bangumi > official_douban > local_douban > plugin > iqiyi`
- `year`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`
- `actors`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`
- `directors`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`
- `genres`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`
- `country`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`
- `language`
  - `bangumi > tmdb > official_douban > local_douban > plugin > iqiyi`

直观策略：

- 内置动漫文本优先 `Bangumi`
- 视觉图优先 `TMDB`
- 站点源和豆瓣继续做补充与兜底

`detail_fields` 允许：

- `Bangumi ID`
- `别名`
- `原题`
- `声优`
- `制作公司`

覆盖同 label 的旧值。

### 10. Failure handling

自动增强：

- Bangumi 搜索失败或详情失败时记录 warning，并继续其他 provider

手动 `刮削`：

- 选择 `全部` 时如果 Bangumi 失败，仍保留 Bangumi 分组
- 在该分组里显示错误文案

token 相关失败：

- token 无效时按 provider 失败处理
- 不因为 Bangumi 鉴权失败影响其他 provider

缓存：

- 沿用现有 `MetadataCache`
- search/detail cache key 按 provider 维度独立保存

### 11. App coordinator integration

`AppCoordinator` 需要：

- 构建 `BangumiClient(token=config.metadata_bangumi_access_token)`
- 始终构建 `BangumiMetadataProvider(client)`
- 把它放入自动增强 provider 列表
- 把它放入手动 `刮削` provider 列表

非动漫条目的实际过滤由 provider 本身和 scrape 过滤逻辑完成，不靠 coordinator 在构建期删除 provider。

这样可以避免：

- 同一个运行期里因为条目类型不同而频繁重建不同 provider 组合

## Testing

### 1. `BangumiClient`

- 匿名请求包含规范 `User-Agent`
- token 请求附加 `Authorization: Bearer ...`
- 能正确解析：
  - subject 搜索
  - subject 详情
  - persons
  - characters
  - episodes

### 2. `BangumiMetadataProvider`

- 非动漫类 `can_enrich=False`
- 动漫类 `can_enrich=True`
- 搜索能命中：
  - `name_cn`
  - `name`
  - 别名
- 年份冲突或季数冲突时拒绝误匹配
- 详情能正确映射：
  - 评分
  - 简介
  - 原题
  - 别名
  - 声优
  - 制作信息
  - 剧集列表

### 3. `MetadataScrapeService`

- 动漫条目 provider 选项包含 `Bangumi`
- 非动漫条目 provider 选项不包含 `Bangumi`
- 手动应用 Bangumi 结果后可正确写回 metadata
- Bangumi 可参与剧集标题增强

### 4. `merge`

- 动漫场景下 Bangumi 文本字段优先于 `tmdb/tencent/iqiyi/bilibili`
- `poster` 仍保持 `tmdb` 优先

### 5. `storage/ui/app`

- `metadata_bangumi_access_token` 能持久化
- 高级设置能读写该字段
- `AppCoordinator` 在无 token 时仍构建 Bangumi provider
- `AppCoordinator` 在有 token 时把 token 注入 client

## References

- Bangumi Auth: <https://raw.githubusercontent.com/bangumi/api/master/docs-raw/How-to-Auth.md>
- Bangumi User-Agent: <https://raw.githubusercontent.com/bangumi/api/master/docs-raw/user%20agent.md>
- Bangumi OpenAPI: <https://github.com/bangumi/api/blob/master/open-api/v0.yaml>
