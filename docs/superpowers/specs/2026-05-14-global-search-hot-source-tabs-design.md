# Global Search Hot Source Tabs Design

## Goal

Extend the global-search popup hot-search area from a single-source category tab strip to a two-level selector:

- source tabs: `360 / 腾讯 / 爱奇艺`
- category tabs: dynamic per selected source

This preserves the current history behavior and explicit popup-button trigger while making hot-search results switchable by content source.

## Confirmed Product Decisions

- keep the current left history / right hot-search popup layout
- keep the current explicit popup-button trigger
- add a source-level selector above the hot-search category tabs
- keep `360` as a source instead of replacing it
- default source should remember the last selected source
- category tabs should be dynamic per source capability
- category selection should be global, not per source
  - when switching source, reuse the current category if supported
  - otherwise fall back to the first supported category for that source

## Scope

This change covers:

- hot-search source registry and metadata
- source tab UI above category tabs
- source-specific hot-search loader dispatch
- dynamic category tabs per source
- persisted last-selected source
- tests for source switching, dynamic categories, and fallback behavior

This change does not cover:

- changing history persistence rules
- changing popup open/close behavior
- changing search result behavior after clicking a hot item
- changing the existing visual refresh direction outside what the new source tabs require

## Source Model

Represent hot-search sources explicitly in the main-window hot-search logic.

Each source should define:

- source key
- display title
- supported categories
- loader function

### 360

Supported categories:

- `movie`
- `tv`
- `variety`
- `comic`
- `dsp`

This matches the current implementation.

### 腾讯

Supported categories:

- single feed only unless a second category-capable endpoint is later verified

For the current change, use only categories that are actually supported by the provided public endpoint. Do not invent content categories without a verified API path.

### 爱奇艺

Supported categories:

- single feed only unless a second category-capable endpoint is later verified

Same rule as Tencent: only expose categories that can really be fetched from the provided public endpoint.

## Category Behavior

The category layer remains below the source layer.

Behavior:

1. Read the remembered current source.
2. Read the current global category selection.
3. Build category tabs for the chosen source only.
4. If the current global category exists in that source, keep it selected.
5. If not, select that source's first supported category.

This keeps source switching predictable while avoiding dead tabs.

## Persistence

Persist the last selected hot-search source in app config alongside the existing search history state.

Recommended field:

- `global_search_hot_source`

Rules:

- save when the user changes source
- restore on next popup open / app launch
- if stored source is unknown, fall back to `360`

The category selection does not need source-specific persistence for this change.

## UI Design

The right column gains this vertical structure:

1. section title: `热搜`
2. source tabs: `360 / 腾讯 / 爱奇艺`
3. category tabs for the selected source
4. ranked hot-search list

### Source Tabs

- should read as the stronger selector layer
- use the same warm visual language as the existing popup refresh
- should clearly differ from category tabs through spacing and weight

### Category Tabs

- remain lighter than the source tabs
- are rebuilt dynamically when source changes

## Loading and Caching

Cache hot-search results by `(source, category)` instead of only by category.

Recommended cache key shape:

- string tuple or composite key such as `(source_key, category_key)`

Rules:

- source switch should render cached results immediately if present
- otherwise show the existing empty/loading transition until async load completes
- category switch should behave the same way within the active source

## API Integration

### 360

Keep using the current loader:

- `http://api.xcvts.cn/api/hotlist/360so_juhe?type=<category>`

### 腾讯

Integrate the provided endpoint:

- `https://pbaccess.video.qq.com/trpc.videosearch.hot_rank.HotRankServantHttp/HotRankHttp`

Use the provided JSON POST body and browser-like headers required by that endpoint.

Normalize the response into the existing internal hot-item shape:

- `{"title": ..., "query": ...}`

### 爱奇艺

Integrate the provided endpoint:

- `https://mesh.if.iqiyi.com/portal/lw/search/keywords/hotList?...`

Normalize it into the same internal hot-item shape.

## Error Handling

On load failure for a given `(source, category)`:

- cache an empty list for that request key
- keep the popup responsive
- show the existing compact empty-state presentation

Failures in one source must not affect cached results for another source.

## Testing

Add UI and loader-focused coverage for:

- source tabs render in the popup
- remembered source is restored
- category tabs rebuild dynamically per source
- unsupported global category falls back to the first category of the new source
- cache is keyed by source and category
- clicking a hot item from any source still triggers search

Keep existing history-action and popup-close coverage intact.

## Implementation Notes

Recommended implementation sequence:

1. add config field for remembered hot-search source
2. replace flat hot-tab metadata with source + category metadata
3. add source tab UI to `GlobalSearchPopup`
4. refactor cache and async loading to use `(source, category)`
5. add Tencent and iQiyi loaders
6. update tests for dynamic source/category behavior
