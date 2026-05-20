# Metadata Original Detail Match Scoring Design

## Summary

增强 metadata 自动匹配打分时，除了现有的标题、年份、季度、分类信号外，再让原始详情里已有的基础字段参与候选排序：

- `vod_area`
- `vod_lang`
- `vod_director`
- `vod_actor`

这些字段只作为附加软信号参与 `score_match(...)`，不改变现有“标题和年份优先”的主逻辑，也不为了拿更多字段而提前请求候选 detail。

## Goals

- 让自动 metadata enhancement 在“同标题 / 同年份 / 同季”候选之间，更倾向原始详情更接近的结果。
- 只使用原始详情页已经有值的基础字段参与打分。
- 保持 provider 搜索阶段的统一排序入口，不把规则分散到各 provider。
- 不增加自动增强时的网络请求数量。

## Non-Goals

- 不让 `detail_fields` 参与匹配打分。
- 不让 `vod_content`、`dbid`、海报等其他字段参与本轮打分。
- 不把基础字段变成硬过滤条件。
- 不在 search 阶段之外提前请求候选 detail 做二次重排。
- 不调整现有 metadata merge 优先级或 hydration 主流程。

## Current Problem

当前 `score_match(...)` 主要依赖：

- 标题相似度
- 季度识别
- 年份接近程度
- 类别/类型匹配
- 少数 provider 的精确标题 bonus

这套规则对“粗筛”已经够用，但当多个候选：

- 标题都很像
- 年份也一致
- 分类也不冲突

时，排序缺少来自原始详情的额外判别信号。

而当前原始详情里往往已经有一些基础字段，例如：

- 地区
- 语言
- 导演
- 演员

这些值如果不参与 search scoring，就会丢失一部分很有价值的区分能力。

## Approach Options

### Option A: Extend `MetadataQuery` and add common field-based bonuses in `score_match(...)`

做法：

- 给 `MetadataQuery` 增加 `vod_area / vod_lang / vod_director / vod_actor`
- `MetadataContext.to_query()` 从原始 `VodItem` 读取这些字段
- `score_match(...)` 从 `match.raw` 提取候选的同类字段并做软加分

优点：

- 规则集中
- 所有 provider 共用统一打分入口
- 不增加额外请求
- 更容易测试和维护

缺点：

- 只有 search `raw` 本来就带这些字段的 provider 才能获得加分
- 不同 provider 的字段完整度不一致，收益会有差别

### Option B: Let each provider apply its own original-detail bonuses

做法：

- 在腾讯、爱奇艺、Bilibili、Bangumi 等 provider 的 `search(...)` 中分别读取 query 基础字段并本地加分

优点：

- 可以按 provider 原始字段结构做更细定制

缺点：

- 规则分散
- 权重容易漂移
- 后续维护成本高

### Option C: Fetch top candidate details and rerank with full records

做法：

- 先搜索
- 对前几个候选拉 detail
- 用 detail 中更完整的国家、语言、导演、演员做二次重排

优点：

- 理论上最准

缺点：

- 增加自动增强请求成本
- 拉长 hydration 延迟
- 复杂度和收益不匹配

## Decision

采用 **Option A**。

原因：

- 需求本质是“让原始详情已有基础字段参与搜索阶段候选排序”，不是重写 metadata hydration。
- 通用 `score_match(...)` 已经是全局匹配规则入口，把新信号放进去最自然。
- 这条路径不增加网络请求，也不会改变现有 provider 责任边界。

## Design

### 1. Extend `MetadataQuery`

在 `MetadataQuery` 中新增：

- `vod_area: str = ""`
- `vod_lang: str = ""`
- `vod_director: str = ""`
- `vod_actor: str = ""`

语义：

- 这些值代表当前原始详情里已经存在的基础字段
- 仅用于匹配阶段打分
- 不是增强后结果，也不是 provider detail 的派生值

### 2. Populate query from original detail

`MetadataContext.to_query()` 在构建 query 时，把当前 `VodItem` 上这 4 个原始基础字段写入 `MetadataQuery`。

来源规则：

- 直接使用当前参与 enhancement 的 `vod`
- 值为空时保持空字符串
- 不做额外清洗以外的结构重写

这样可以保证：

- search scoring 使用的是“增强前已知详情”
- 后续 metadata merge 不会反向污染 query 信号

### 3. Candidate-side field extraction

`score_match(...)` 继续只吃 `MetadataQuery` + `MetadataMatch`。

候选端信息来源：

- 从 `match.raw` 中提取地区、语言、导演、演员相关字段
- 不调用 `provider.get_detail(...)`

字段提取要求：

- 允许同时适配字符串、列表、嵌套对象
- 对导演/演员按“名称集合”比较
- 对地区/语言按标准化 token 比较

本轮不要求每个 provider 都有完整字段。

若某个 provider 的 `raw` 中没有对应信息：

- 不加分
- 不扣分

### 4. Scoring rules

新增信号全部采用“软加分”模型，不引入硬过滤。

建议原则：

- 标题完全匹配、年份一致、季度一致仍然是主导信号
- 原始基础字段只用于拉开高相似候选之间的排序
- 任一字段不命中时，默认不因缺失而重罚

建议加分方向：

- `vod_area` 与候选地区有交集：小幅加分
- `vod_lang` 与候选语言有交集：小幅加分
- `vod_director` 与候选导演集合有交集：中小幅加分
- `vod_actor` 与候选演员集合有交集：中小幅加分

推荐权重约束：

- 单个基础字段 bonus 明显小于标题完全匹配 bonus
- 四个基础字段全部命中时，总增益也不应压过明显的标题/年份冲突

也就是说：

- 它们只负责“在合理候选里选更像的”
- 不负责“把明显不对的候选强行拉上来”

### 5. Matching behavior expectations

期望行为：

1. 当两个候选标题、年份都相同或非常接近时：
   - 更匹配原始地区/语言/导演/演员的候选应排前
2. 当候选缺失这些字段时：
   - 保持现有标题/年份/分类排序
3. 当标题或年份明显冲突时：
   - 新增基础字段 bonus 不能掩盖这类强冲突

### 6. Testing

需要补两类测试。

#### 6.1 Query mapping tests

覆盖：

- `MetadataContext.to_query()` 会把 `vod_area / vod_lang / vod_director / vod_actor` 带入 `MetadataQuery`
- 原始值为空时，对应 query 字段保持空

#### 6.2 Match scoring tests

覆盖：

- 相同标题 / 年份下，地区更匹配的候选分数更高
- 相同标题 / 年份下，语言更匹配的候选分数更高
- 相同标题 / 年份下，导演更匹配的候选分数更高
- 相同标题 / 年份下，演员更匹配的候选分数更高
- query 侧这些字段为空时，不产生额外加分
- 明显年份冲突仍然保持不可信匹配

## Risks and Constraints

- 不同 provider search `raw` 的字段命名并不统一，字段抽取逻辑需要做兼容适配。
- 原始 `vod_actor` / `vod_director` 目前是逗号拼接字符串，不同来源的分隔符可能不一致，需要在 matching 层做统一 token 化。
- 如果某些 provider 的 search raw 只带少量文本字段，本轮收益可能主要集中在爱奇艺、腾讯这类搜索结果更丰富的来源上。这是预期内限制，不是设计缺陷。

## Implementation Outline

1. 扩展 `MetadataQuery` 基础字段。
2. 更新 `MetadataContext.to_query()` 映射原始 `VodItem` 基础字段。
3. 在 `metadata.matching` 中新增候选基础字段提取与归一化逻辑。
4. 在 `score_match(...)` 中加入 area/lang/director/actor 软加分。
5. 补充 query 映射和 scoring 的 focused tests。
