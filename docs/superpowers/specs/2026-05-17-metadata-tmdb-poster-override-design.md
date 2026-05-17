# Metadata TMDB Poster Override Design

## Summary

自动 metadata hydration 当前只有首个命中的 provider 会走完整 merge，后续 provider 只会补空字段。这导致 `TMDB` 即使拥有更高质量的封面，只要不是第一命中，就无法覆盖已经写入的低质量 `poster`。目标是让自动增强链路允许 `TMDB` 这样的高优先级视觉来源覆盖现有封面，同时保持 `overview`、`rating` 等文本字段的现有优先级不变。手动 metadata 刮削“应用结果”链路已经使用整条替换语义，本轮不改变其行为，只补回归约束。

## Goals

- 自动 hydration 时允许高优先级 provider 覆盖已有封面。
- 保持现有“豆瓣文案优先、TMDB 视觉优先”的字段策略。
- 不扩大成一次全面 metadata merge 行为重写。
- 确认手动 metadata 刮削 apply 继续保持当前替换行为。

## Non-Goals

- 不改变手动 metadata 刮削 apply 的字段替换语义。
- 不调整 `overview`、`rating`、`year`、`actors`、`genres` 的现有优先级。
- 不增加“高清封面”分辨率探测、下载尺寸比较或图片质量评分。
- 不新增用户配置项来控制 provider 字段优先级。

## Scope

主要改动：

- `src/atv_player/metadata/merge.py`
- `src/atv_player/metadata/hydrator.py`
- `tests/test_metadata_hydrator.py`
- 如有必要，补充 `tests/test_metadata_merge.py`
- 如有必要，补充 `tests/test_metadata_scrape_service.py`

不预期修改 UI 交互、缓存结构或 provider API。

## Current Problem

当前自动 hydration 流程是：

1. 首个可信命中的 provider 调用 `merge_metadata_record()`
2. 后续 provider 只调用 `fill_missing_metadata_record()`

这意味着后续 provider 只能填写空字段，不能覆盖已有字段。

虽然 `merge_metadata_record()` 内部已经把 `poster` 优先级设为：

- `tmdb`
- `bangumi`
- `official_douban`
- `local_douban`
- `douban`
- `plugin`
- `iqiyi`

但这个优先级只在“完整 merge”时生效。实际结果是：

- `official_douban` 或 `local_douban` 若先写入封面，后续 `TMDB` 不会再覆盖。
- 用户最终看到的可能是低质量、小图或非标准纵向海报。
- `overview` 和 `rating` 当前又确实不应该被后续 `TMDB` 覆盖，因此不能简单把所有后续 provider 都改成完整 merge。

手动 metadata 刮削 apply 则不同：

- `MetadataScrapeService.apply()` 使用 `replace_metadata_record()`
- 用户手动选择结果后，本来就会整体替换当前 metadata

因此手动链路不存在“TMDB 不能覆盖封面”的缺口，本轮只需要保证它不被自动链路改动误伤。

## Approach Options

### Option A: Add a targeted visual-field override pass after fill-missing

做法：

- 自动 hydration 首个 provider 继续完整 merge
- 后续 provider 继续 `fill_missing_metadata_record()`
- 然后再执行一个很小的“视觉字段覆盖”步骤
- 该步骤至少允许 `poster` 按现有字段优先级覆盖

优点：

- 变更面最小
- 和现有字段优先级表保持一致
- 不会意外改变文本字段行为

缺点：

- merge 逻辑会分成“完整 merge + 补空 + 视觉覆盖”三段

### Option B: Change later providers to use full merge as well

做法：

- 自动 hydration 的后续 provider 不再 `fill_missing_metadata_record()`
- 改为再次调用 `merge_metadata_record()`

优点：

- 规则更统一

缺点：

- 后续 provider 可能覆盖年份、演员、类型、国家等更多字段
- 行为变化明显超出这次需求范围

### Option C: Special-case TMDB inside hydrator only

做法：

- 保持现有通用 merge 逻辑不变
- 仅在 hydrator 里写死：后续 `TMDB` 可以覆盖 `vod_pic`

优点：

- 实现最快

缺点：

- 规则分散在调用层，不利于维护
- 以后若 `bangumi` 或别的来源也要视觉覆盖，又会继续堆特判

## Decision

采用 **Option A**。

原因：

- 需求本质是“允许高优先级视觉字段后置覆盖”，不是“让所有字段都重新 merge”。
- 现有 `poster` provider priority 已经定义清楚，缺的是自动 hydration 后续阶段缺少覆盖入口。
- 该方案能最小化改动，同时避免伤到 `overview` / `rating` 的既有策略。

## Design

### 1. Introduce a shared visual-field override helper

在 `metadata/merge.py` 新增一个很小的辅助函数，职责是：

- 只处理视觉字段
- 目前至少处理 `poster`
- 是否允许覆盖仍然复用现有 `_can_override()` / `_FIELD_PROVIDER_PRIORITY`

建议语义：

- 当 `record.poster` 非空
- 且当前 `vod.vod_pic` 为空，或 `record.provider` 对 `poster` 的优先级高于当前来源
- 则写入 `vod.vod_pic`
- 同时刷新 `metadata_field_sources["poster"]`

本轮不必顺手扩大到非用户可见需求。如果仓库内已经存在稳定的 `backdrop` 写回位置，可以一并纳入；否则只处理 `poster`。

### 2. Keep full merge behavior unchanged

`merge_metadata_record()` 继续保持现有语义：

- 首次主命中 provider 决定完整 metadata merge
- 现有 `poster`、`overview`、`rating` 等字段优先级不在这里重写

这样可以避免把本次改动扩散成一次 merge 重构。

### 3. Extend automatic hydration with a post-fill visual override

`MetadataHydrator.hydrate()` 中的后续 provider 处理改为：

1. 继续先执行 `fill_missing_metadata_record(vod, record)`
2. 紧接着执行新的视觉字段覆盖 helper

结果：

- 后续 provider 仍只补文本空字段
- 但 `TMDB` 等高优先级视觉来源能覆盖已有封面
- `official_douban` 等文本来源仍保留简介和评分控制权

### 4. Manual scrape apply remains replacement-based

`MetadataScrapeService.apply()` / `replace_metadata_record()` 保持不变：

- 用户手动应用某个 provider 时，仍完整替换当前 metadata
- 不引入“只覆盖视觉字段”的额外限制

如实现上需要共用小 helper，可以复用，但不得改变手动 apply 的外部效果。

### 5. Test coverage

至少补以下测试：

- 自动 hydration：
  - 先由 `official_douban` 写入 `poster` / `overview` / `rating`
  - 后续 `TMDB` 提供新 `poster`
  - 结果应为：
    - `poster` 被 `TMDB` 覆盖
    - `overview` 仍保留豆瓣
    - `rating` 仍保留豆瓣

- 自动 hydration 回归：
  - 后续非高优先级 provider 不能反向覆盖 `TMDB poster`

- 手动 scrape apply 回归：
  - 继续完整替换 metadata 字段
  - 本轮自动 hydration 改动不影响 `apply()` 行为

## Risks

- 如果视觉字段 helper 写得太宽，可能无意中把非视觉字段也带进后续覆盖流程。
- 如果 helper 和 `merge_metadata_record()` 各自维护不同的优先级判断，后续容易漂移。

规避方式：

- helper 只复用现有优先级判断，不复制第二套排序规则
- 测试明确覆盖“封面可覆盖，但简介和评分不可覆盖”

## Verification

实现后至少运行：

- `uv run pytest tests/test_metadata_hydrator.py -q`
- `uv run pytest tests/test_metadata_scrape_service.py -q`
- 如 merge 测试有新增，再跑 `uv run pytest tests/test_metadata_merge.py -q`
