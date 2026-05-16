# TMDB Season Overview Priority Design

## Summary

自动 metadata hydration 当前已经能从 `TMDB` 拿到季级简介，但 `overview` 合并优先级仍然是：

- `local_douban`
- `remote_douban`
- `douban`
- `tmdb`
- `plugin`

这会导致剧集季级命中时，`TMDB` 的季简介被“本地豆瓣”覆盖。目标是把简介优先级调整为：

- `OfficialDoubanProvider` 也就是 `local_douban` 仍然可以覆盖简介
- `TMDB` 的季级简介高于 `LocalDoubanProvider` 也就是 `remote_douban`
- `remote_douban` 只能作为简介兜底，不能覆盖已有简介

其它字段如海报、年份、演员、导演、评分、豆瓣 ID 的合并规则保持不变。

## Goals

- 自动 hydration 时优先使用 `TMDB` 季级简介。
- 保留 `OfficialDoubanProvider` 对简介的覆盖权。
- 将 `LocalDoubanProvider` 降为简介的最后兜底来源。
- 把改动限制在现有 metadata merge 逻辑和测试中。

## Non-Goals

- 不改手动刮削“应用结果”的替换语义。
- 不改 `rating`、`poster`、`year` 等非 `overview` 字段优先级。
- 不给 provider 排序增加用户配置。
- 不重构 `MetadataRecord` 模型。

## Scope

主要改动：

- `src/atv_player/metadata/merge.py`
- `tests/test_metadata_hydrator.py`

如实现需要，可少量补充 provider/merge 相关测试，但不扩大到 UI 或 cache 行为。

## Current Problem

当前 `TMDBProvider` 已经在季级命中时使用：

- `provider_id` 形如 `tv:<id>:season:<n>`
- `get_tv_season_detail()` 的 `overview` 优先于整剧 `overview`

但 `merge_metadata_record()` 对 `overview` 的覆盖仍采用固定 provider 名称顺序，不区分：

- `tmdb` 普通剧集简介
- `tmdb` 季级简介

也不区分 `remote_douban` 应该是高优先级覆盖还是低优先级兜底。

结果是：

- 自动搜索时，季级 `TMDB` 简介会被 `remote_douban` 覆盖。
- 用户即使已经修复了季识别，自动补全仍然显示不想要的简介来源。

## Approach Options

### Option A: Only reorder provider names for `overview`

做法：

- 直接把 `overview` 优先级改成 `local_douban > tmdb > douban > remote_douban > plugin`

优点：

- 代码最简单

缺点：

- 无法区分“TMDB 季级简介”和“TMDB 普通简介”
- 会让所有 TMDB 电视剧简介都整体抬高，不够精确

### Option B: Add special handling for TMDB season overview

做法：

- `overview` 字段保持单独规则
- 当 `record.provider == "tmdb"` 且 `provider_id` 含 `:season:` 时，给予更高覆盖权
- `local_douban` 仍可覆盖
- `remote_douban` 降为只能兜底

优点：

- 精确命中“TMDB 季简介优先”的需求
- 改动面小，不影响其它字段

缺点：

- `merge.py` 里会多一层 `overview` 特判

### Option C: Extend `MetadataRecord` with structured priority flags

做法：

- 给 `MetadataRecord` 增加类似 `overview_priority` 或 `is_season_overview` 字段
- 合并逻辑不再解析 `provider_id`

优点：

- 模型语义更清晰

缺点：

- 改动面比当前需求大
- 需要同步调整 provider、缓存和测试

## Decision

采用 **Option B**。

原因：

- 用户需要的是“TMDB 季简介优先”，不是“所有 TMDB 简介优先”。
- 现有 `provider_id` 已经携带 `:season:` 语义，不需要扩展模型即可识别。
- 能把 `remote_douban` 明确降为简介兜底，同时保留 `local_douban` 的覆盖权。

## Design

### 1. `overview` override policy becomes field-specific logic

保留现有 `_FIELD_PROVIDER_PRIORITY` 处理大多数字段，但 `overview` 不再完全依赖固定 provider 名称表。

`overview` 新规则：

1. `local_douban` 可以覆盖任何已有简介。
2. `tmdb` 且 `provider_id` 含 `:season:` 时：
   - 可以覆盖 `tmdb` 普通简介
   - 可以覆盖 `douban`
   - 可以覆盖 `remote_douban`
   - 不可以覆盖 `local_douban`
3. `douban` 保持中间优先级：
   - 可以覆盖 `remote_douban`
   - 不可以覆盖 `local_douban`
   - 不可以覆盖 `tmdb` 季简介
4. `remote_douban` 只在当前没有简介时写入，不能覆盖已有简介。
5. 其它 provider 保持最低优先级兜底。

### 2. Season detection stays local to merge logic

新增一个很小的 helper，用于识别 `TMDB` 记录是否为季级简介：

- `record.provider == "tmdb"`
- `record.provider_id` 字符串包含 `:season:`

不新增数据模型字段，不改 cache key，不改 provider 输出结构。

### 3. No change to manual scrape apply

手动刮削“应用结果”继续使用 `replace_metadata_record()`：

- 用户手动应用哪个来源，就完整替换成哪个来源
- 本轮不把新的 `overview` 优先级规则带入手动替换逻辑

### 4. Tests

补充并更新 hydration 测试，至少覆盖：

- `TMDB` 季简介可以覆盖 `remote_douban` 简介。
- `local_douban` 仍然可以覆盖 `TMDB` 季简介。
- `remote_douban` 不能覆盖已经存在的 `TMDB` 季简介。
- 非季级 `TMDB` 简介不因为本次改动获得新的全局最高优先级。

## Risks

- 如果合并逻辑写得过于隐式，后续再调简介来源时会变难理解。
- `provider_id` 的季级语义目前依赖字符串约定，未来若格式变化，需要同步调整 helper。

## Verification

实现后至少运行：

- `uv run pytest tests/test_metadata_hydrator.py -q`
- 如有必要，再补跑与 metadata merge 相关的其它测试子集

