# Bilibili Anime Metadata Design

## Summary

在现有 metadata provider 架构中增强 `BilibiliMetadataProvider`，只对 `番剧 / 国创 / 动画 / 动漫` 场景接入更完整的 B 站番剧详情能力，同时把这套能力接到：

- 自动元数据增强 `MetadataHydrator`
- 播放器手动 `刮削` 对话框 `MetadataScrapeService`
- 剧集标题改写 `episode_title_resolver`

核心规则：

- 只在动画类目启用
- 能判定当前条目属于 B 站番剧时，剧集标题优先使用 B 站
- 不能稳定判定或 B 站详情不完整时，回退到 `TMDB`

这次改动重点不是“新增一个普通站点搜索源”，而是把 B 站番剧季详情作为动画场景下的高质量剧集标题来源。

## Goals

- 只在 `番剧 / 国创 / 动画 / 动漫` 场景增强 B 站 metadata。
- 为 `BilibiliMetadataProvider` 增加真实的番剧季详情抓取，而不是只依赖搜索结果摘要。
- 在动画场景下，能把 B 站单集标题稳定用于剧集标题改写。
- 修复 `TMDB` 存在空标题或缺集标题时，B 站已有标题却没有被利用的问题。
- 保持现有 provider 架构、cache 和 scrape UI 不变。

## Non-Goals

- 不接入 B 站电影、电视剧、综艺等非动画季信息。
- 不新增用户可配置的 provider 排序 UI。
- 不重写 `MetadataHydrator` 和 `MetadataScrapeService` 的整体控制流。
- 不把 B 站提升为动画场景下的通用文本元数据主源；文本主源仍由现有优先级决定。
- 不接入用户态能力，如追番、评分、历史同步。

## Current Problem

当前代码里虽然已经有：

- `BilibiliMetadataProvider`
- `MetadataHydrator`
- `MetadataScrapeService`
- `episode_title_resolver`

但 `bilibili` provider 仍有两个明显缺口：

1. `search()` 主要依赖 `media_bangumi` 搜索结果，`get_detail()` 也基本只消费搜索时带回来的摘要字段。
2. 剧集标题改写依赖搜索结果中的 `eps`，没有稳定拉取完整季详情，因此当搜索结果缺少完整集信息时，无法覆盖 `TMDB` 的空标题缺口。

实际后果：

- 某些番剧在 `TMDB` 某一集缺标题，但 B 站播放页已经有正确标题，播放器仍回退到 `TMDB` 空值或旧值。
- 动画条目已经命中 B 站候选，但无法把 B 站作为一个“可确认的番剧季来源”参与优先级决策。

## Approach Options

### Option A: Keep current Bilibili search-only mapping

做法：

- 不新增 B 站详情接口
- 继续依赖 `media_bangumi` 搜索结果里的 `eps`

优点：

- 改动最小

缺点：

- 无法稳定拿到完整季的单集标题
- 不能解决 `TMDB` 缺标题但 B 站有标题的核心问题

### Option B: Always prefer Bilibili episode titles for anime

做法：

- 只要是动画类目，就无条件让 B 站标题压过 `TMDB`

优点：

- 逻辑简单

缺点：

- 误匹配风险高
- 不符合“只有确认属于 B 站时才用 B 站，否则回退 TMDB”的要求

### Option C: Bilibili ownership check plus fallback to TMDB

做法：

- 动画类目中，先搜索 B 站番剧候选
- 只有当候选可被确认是有效的 B 站番剧季条目时，才把 B 站标题放在 `TMDB` 前面
- 否则直接回退 `TMDB`

优点：

- 符合用户要求
- 能利用 B 站真实番剧标题补齐 `TMDB` 缺口
- 不会把非 B 站动画条目错误覆盖

缺点：

- 需要新增 B 站番剧详情抓取与归属判定逻辑

## Decision

采用 **Option C**。

原因：

- 用户明确要求“如果能判定属于 B 站就用 B 站来源，否则回退 TMDB”
- 当前仓库已经把 `bilibili` 放在动画剧集标题候选链路里，问题在于 provider 数据不够完整，不在于架构缺失
- 先做 B 站归属判定，再决定是否覆盖 `TMDB`，是风险最低且最符合预期的方案

## Design

### 1. Activation scope

这次增强只对以下类目启用：

- `番剧`
- `国创`
- `动画`
- `动漫`
- `anime`

启用点：

- `BilibiliMetadataProvider.can_enrich(...)`
- `MetadataScrapeService.build_episode_title_playlist(...)` 中的自动候选流程
- `episode_title_resolver` 中的 `bilibili` 候选判断

对于非动画类目：

- `bilibili` provider 仍可保留现有普通 metadata 搜索能力
- 但本轮新增的番剧详情抓取与剧集标题优先逻辑不参与

### 2. Bilibili ownership model

这里的“属于 B 站”不做站外版权意义上的归属判断，而做“当前 metadata 候选是否能确认映射到 B 站番剧季条目”的工程判定。

新增一个轻量判定概念：

- `bilibili anime candidate`

判定条件：

1. 查询本身属于动画类目。
2. `media_bangumi` 搜索返回高置信匹配。
3. 候选能够解析出有效的 `season_id` 或 `ssid`。
4. 使用该 `season_id/ssid` 拉到有效季详情。
5. 季详情中存在可用于映射主播放列表的正片剧集列表。

只要满足以上条件，就视为“可判定属于 B 站”，允许其在剧集标题改写时优先于 `TMDB`。

不额外引入持久化“归属标记”字段；判定完全由当前候选及详情数据即时得出。

### 3. Bilibili client/detail fetching

`BilibiliMetadataProvider` 继续保留现有搜索逻辑，但新增真实详情抓取。

建议新增内部详情接口封装：

- `get_season_detail_by_id(season_id: str | int) -> dict[str, object]`
- `get_season_sections_by_id(season_id: str | int) -> dict[str, object] | list[dict[str, object]]`

目标是从 B 站番剧详情接口拿到：

- 季标题
- 原标题/副标题
- 简介
- 封面
- 区域
- 类型/风格
- 声优
- 制作信息
- 正片剧集列表
- 可选的分区/附加列表信息

实现要求：

- 延续现有 WBI / 浏览器头处理方式
- 优先从 `provider_id` 或搜索结果中提取 `season_id`
- 详情抓取失败时不影响整个 metadata 链路，只回退搜索摘要或其他 provider

### 4. Search result normalization

`BilibiliMetadataProvider.search()` 需要把更多可复用字段写进 `match.raw`：

- `season_id`
- `media_id`
- `season_type`
- `season_type_name`
- `cover`
- `areas`
- `styles`
- `index_show`
- `eps`

如果搜索结果已有足够多的 `eps`，可以直接复用；否则在需要剧集标题或 detail 时再走季详情接口补齐。

这样可以减少不必要的详情请求，同时保留按需 hydration 的能力。

### 5. Detail mapping

`BilibiliMetadataProvider.get_detail()` 改为两阶段：

1. 先用 `match.raw` 作为基础字段
2. 如果存在 `season_id`，再尝试拉 B 站季详情并覆盖/补全字段

字段策略：

- `title`: 优先详情标题，回退搜索标题
- `overview`: 优先详情简介
- `poster`: 优先详情封面
- `genres`: 详情 `styles` 优先
- `country`: 详情区域优先
- `detail_fields`: 继续输出 `分区 / 更新状态 / 声优 / 制作信息`
- `raw["episodes"]`: 统一写入规范化后的单集列表，供剧集标题改写复用

本轮不强行从 B 站产出评分字段；如果详情里有评分，可以先保存在 `raw`，不作为 merge 主字段依赖。

### 6. Episode normalization

新增 B 站剧集规范化步骤，把搜索结果 `eps` 或详情页剧集结构映射成统一列表。

每一集至少保留：

- `episode_number`
- `title`
- `long_title`
- `badge`
- `episode_type`
- `sort`

正片判定规则：

- 优先使用详情中的主正片列表
- 跳过 SP、PV、OP、ED、预告、花絮等特殊条目
- 只把能稳定映射到主播放列表的剧集纳入标题改写

最终 `episode_title_resolver` 只依赖规范化后的正片列表，而不是直接耦合搜索接口原始字段。

### 7. Episode title rewrite policy

动画类目下的自动候选顺序调整为：

- `bangumi`
- `bilibili`（仅当可判定为 B 站番剧季）
- `tmdb`
- `tencent`
- `iqiyi`

具体规则：

1. 若 `bangumi` 候选可用，保持其优先级不变。
2. 若 `bilibili` 候选可用，且通过 B 站归属判定，则整体优先于 `TMDB`。
3. 若 `bilibili` 候选不可确认，或详情没有有效正片列表，则直接跳过，回退 `TMDB`。
4. 若 `TMDB` 某一集标题为空，而 B 站候选有效，则整套标题直接采用 B 站，不做逐集混合来源。

这里明确不做“TMDB 和 B 站单集级拼接混合”。

原因：

- 当前播放列表标题来源模型更适合“整套候选覆盖”
- 混合来源会让调试和来源标记更复杂
- 用户的规则是“能确认属于 B 站就用 B 站，否则回退 TMDB”，不是“逐集择优混拼”

### 8. Metadata scrape integration

`MetadataScrapeService.build_episode_title_playlist(...)` 保持现有控制流，但增强 `bilibili` 候选处理：

- 如果是用户手动选中的 `bilibili` 候选，先尝试补全 B 站季详情
- 如果补全后通过归属判定，则允许其优先用于剧集标题改写
- 如果补全后仍无有效正片列表，则回退自动候选链路中的 `TMDB`

自动搜索时：

- 只在动画类目主动尝试 `bilibili`
- `bilibili` 候选必须先通过归属判定，才允许排在 `tmdb` 前面

### 9. Error handling

需要保证以下失败模式都只影响当前 provider，不影响整体链路：

- B 站搜索风险控制
- B 站详情接口失败
- `season_id` 无法解析
- 剧集列表为空或只包含特殊条目
- 详情字段结构变化

行为：

- `MetadataHydrator` 中记录 warning，继续下一个 provider
- `MetadataScrapeService` 中保留 provider group，但不阻断其他结果
- 剧集标题改写时安全回退 `TMDB`

### 10. Testing

先补测试，再改实现。

需要覆盖：

- `BilibiliMetadataProvider.get_detail()` 在存在 `season_id` 时会拉详情并把 `episodes` 写回 `raw`
- 动画类目下，B 站候选通过归属判定时，`build_episode_title_playlist()` 优先使用 B 站而不是 `TMDB`
- B 站候选缺少有效季详情或有效正片列表时，会回退 `TMDB`
- B 站剧集规范化会跳过特殊条目，只映射正片
- `TMDB` 缺标题但 B 站有标题的番剧 case 能被 B 站整体覆盖

## Acceptance Criteria

- 动画类目条目在命中有效 B 站番剧季候选时，可用 B 站单集标题改写播放列表。
- 无法确认 B 站番剧季候选时，剧集标题自动回退 `TMDB`。
- `MetadataHydrator` 中的 `bilibili` detail 不再只依赖搜索摘要，能补出更完整的番剧 metadata。
- 手动 `刮削` 选中 B 站结果后，剧集标题改写可复用同一套详情数据。
- 非动画类目不启用本轮新增的 B 站番剧增强逻辑。

## Open Questions Resolved

- 是否扩展到电影、电视剧、综艺：不扩展，只做 `番剧 / 国创 / 动画`。
- B 站和 `TMDB` 是否逐集混合：不混合，按候选整套覆盖。
- B 站何时压过 `TMDB`：只有在动画类目且 B 站番剧季候选可被确认时。
