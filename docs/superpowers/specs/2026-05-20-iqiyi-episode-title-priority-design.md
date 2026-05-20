# IQIYI Episode Title Priority Design

## Summary

当剧集标题改写能够被强判定为“爱奇艺剧集”时，让 `iqiyi` 的剧集标题结果优先级高于 `tmdb`；否则保持现有顺序不变。

这次改动同时覆盖两条链路：

- 自动剧集标题增强
- 手动刮削后的候选构建与剧集标题播放列表生成

本次只调整“剧集标题改写”的来源优先级，不调整海报、简介、评分等元数据字段的 merge 策略。

## Goals

- 在强判定为爱奇艺剧集时，让 `iqiyi` 剧集标题结果可压过 `tmdb`
- 让自动增强链路和手动刮削链路共用同一套判定规则
- 避免把 `iqiyi` 全局永久提升到 `tmdb` 之前
- 保持 `bangumi` 与 `bilibili` 现有更高优先级不变

## Non-Goals

- 不调整 metadata field merge 的 provider 优先级
- 不改变 `bangumi`、`bilibili`、`tencent` 的匹配与提权规则
- 不把弱命中的爱奇艺候选当作高置信度候选
- 不扩大到非剧集场景或电影场景

## Scope

主要改动：

- `src/atv_player/metadata/episode_title_resolver.py`
- `src/atv_player/metadata/scrape.py`
- `src/atv_player/app.py`

主要验证：

- `tests/test_metadata_episode_title_resolver.py`
- `tests/test_metadata_scrape_service.py`
- `tests/test_app.py`

## Current Problem

当前剧集标题改写有两条独立但相关的链路：

1. `AppCoordinator` 的自动剧集标题增强
2. `MetadataScrapeService.build_episode_title_playlist()` 的候选遍历

这两条链路最终都依赖 `build_provider_episode_playlist(...)` 产出可用的分集标题映射，但 `iqiyi` 在固定顺序中始终落在 `tmdb` 之后。

结果是：

- 即使当前剧集本身更像爱奇艺剧集
- 即使爱奇艺候选能产出更合适的结构化分集标题

只要 `tmdb` 先成功产出结果，`iqiyi` 就很难在现有机制下覆盖它。直接把 `iqiyi` 全局提到 `tmdb` 前面又会放大误命中风险，因此需要“条件性提权”。

## Approach Options

### Option A: 全局把 `iqiyi` 提到 `tmdb` 之前

做法：

- 直接修改固定来源优先级顺序

优点：

- 实现最简单

缺点：

- 会放大爱奇艺弱命中覆盖 `tmdb` 的风险
- 无法表达“只在高置信度爱奇艺剧集场景提权”

### Option B: 只有绑定来源为 `iqiyi` 才提权

做法：

- 仅对已有爱奇艺绑定的剧集让 `iqiyi` 高于 `tmdb`

优点：

- 风险最低

缺点：

- 覆盖范围不够
- 未绑定但标题、年份、季信息高度一致的爱奇艺剧集仍然会被 `tmdb` 抢先

### Option C: 强判定成立时对 `iqiyi` 条件性提权

做法：

- 新增统一判定函数
- 只有强判定为爱奇艺剧集时，才在剧集标题改写场景里临时让 `iqiyi` 高于 `tmdb`

优点：

- 风险可控
- 覆盖绑定和未绑定但高度一致的爱奇艺剧集
- 能同时服务自动增强和手动刮削两条链路

缺点：

- 需要明确并维护一套高置信度判定规则

## Decision

采用 **Option C**。

原因：

- 这次需求不是让 `iqiyi` 永久高于 `tmdb`，而是只在“可判定为爱奇艺剧集”的前提下提权。
- 当前代码里已经有统一的“能否产出剧集标题映射”能力，适合把“高置信度判定”也收敛到同一层。
- 条件性提权既能覆盖绑定场景，也能覆盖未绑定但命中质量足够高的场景。

## Design

### 1. Unified IQIYI confidence gate

新增统一判定函数，供自动增强链路和手动刮削链路共用。

强判定为爱奇艺剧集，必须满足以下条件之一：

- 当前绑定来源就是 `iqiyi`
- `iqiyi` 候选能够成功产出有效的剧集标题映射，并且候选标题与当前剧名高度一致

这里的“有效剧集标题映射”指：

- `build_provider_episode_playlist(...)` 对该 `iqiyi` 候选返回非空结果
- 返回结果中至少存在实际改写过的分集标题，而不是仅回显原始文件名

### 2. High-confidence title compatibility rules

未绑定场景下，“标题与当前剧名高度一致”先采用保守规则：

- 标题主名归一化后应一致
- 如果双方都带年份，则年份不能冲突
- 如果双方都能解析出季信息，则季信息不能冲突

归一化比较沿用现有 metadata title normalization 思路，不引入新的模糊相似度算法。

本轮不做：

- 模糊分数匹配
- 别名召回
- 更宽松的跨站标题近似判断

原因是这会显著抬高误提权风险。

### 3. Priority model

保留现有默认来源顺序作为基础顺序：

- `plugin`
- `bangumi`
- `bilibili`
- `tmdb`
- `tencent`
- `iqiyi`

当且仅当爱奇艺强判定成立时，本次剧集标题改写使用临时顺序：

- `plugin`
- `bangumi`
- `bilibili`
- `iqiyi`
- `tmdb`
- `tencent`

这是一种“本次候选集内的临时排序”或“本次改写使用的临时 source priority”，不是全局常量永久变更。

### 4. Automatic enhancement integration

`AppCoordinator` 自动剧集标题增强链路保持现有 TMDB 预加载能力，但调整比较策略：

- 先继续尝试已有绑定候选
- 保留 TMDB 的直接搜索与 season detail hydration
- 在 provider 候选比较前，识别是否存在强判定成立的爱奇艺候选
- 如果存在，则后续候选比较与覆盖逻辑使用提权后的临时顺序
- 如果不存在，则保持当前行为

这样可以避免：

- 直接删掉现有 TMDB 快路径
- 让爱奇艺弱命中无条件抢占 TMDB

同时保证在映射数量相同、结果不同的情况下，高置信度 `iqiyi` 能覆盖 `tmdb`。

### 5. Manual scrape integration

`MetadataScrapeService.build_episode_title_playlist()` 当前按固定 provider 顺序搜第一个可用结果。

本次改成两段式：

1. 先收集并 hydrate 候选
2. 再根据是否存在强判定成立的爱奇艺候选，决定本次候选遍历顺序

具体行为：

- 如果 `preferred_candidate` 本身是强判定成立的 `iqiyi` 候选，则它优先于 `tmdb`
- 如果自动搜到的 `iqiyi` 候选满足强判定，也让它在本次排序里先于 `tmdb`
- 如果没有高置信度爱奇艺候选，保持原顺序

这样手动刮削和自动增强会共用同一套爱奇艺提权语义，不会出现链路分叉。

### 6. Code placement

统一判定逻辑放在 `episode_title_resolver` 附近，原因是：

- 它已经持有“候选能否产出可用分集标题”的核心能力
- `app.py` 与 `metadata/scrape.py` 都已经依赖这里的剧集标题构建逻辑
- 可以减少跨模块重复实现和行为漂移

建议提供的辅助能力包括：

- 判断某个候选是否能被强判定为爱奇艺剧集
- 根据当前候选集返回本次应使用的 episode title source priority

## Testing

先用 TDD 补齐以下行为测试。

### Resolver-level tests

- 绑定来源为 `iqiyi` 时，判定函数返回强判定成立
- 未绑定但标题、年份、季信息一致，且 `iqiyi` 候选能生成有效映射时，判定成立
- 标题不一致时，判定失败
- 年份冲突时，判定失败
- 季信息冲突时，判定失败
- 强判定成立时返回提权后的 source priority
- 不成立时返回默认 source priority

### App coordinator tests

- 自动增强中，已绑定 `iqiyi` 时，`iqiyi` 覆盖同映射数的 `tmdb`
- 未绑定但高置信度 `iqiyi` 候选存在时，`iqiyi` 覆盖 `tmdb`
- 未绑定且标题或季信息不一致时，仍保持 `tmdb` 优先

### Scrape service tests

- 手动候选构建里，高置信度 `iqiyi` 候选优先于 `tmdb`
- 不满足高置信度条件时，遍历顺序仍保持 `tmdb` 在前
- `preferred_candidate` 为高置信度 `iqiyi` 时，行为与自动搜到的高置信度 `iqiyi` 一致

## Risks And Mitigations

- 风险：爱奇艺搜索结果标题规范化不稳定，导致“高度一致”判定偏松或偏紧。
  缓解：首版只采用主标题一致、年份不冲突、季信息不冲突的保守规则，不上模糊相似度。

- 风险：自动增强与手动刮削若各自写判断，后续会漂移。
  缓解：统一把判定和优先级计算收敛到共享函数。

- 风险：为了让爱奇艺提权，意外破坏 `bangumi` / `bilibili` 现有更高优先级。
  缓解：临时顺序只调整 `iqiyi` 与 `tmdb`、`tencent` 的相对位置，不动更高层级。

- 风险：把“能产出映射”本身当作高置信度依据可能产生循环调用或重复计算。
  缓解：复用已有 playlist build 结果，避免为判定额外引入第二套映射逻辑。
