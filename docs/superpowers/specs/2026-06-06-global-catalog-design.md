# 环球片单内置源 Design

## Goal

Add a built-in `环球片单` source immediately after `豆瓣电影` in the main navigation. The source exposes the full seven-module media hub from the supplied Widget script through the app's existing poster-grid browsing model.

## Scope

`环球片单` includes these top-level categories:

- 动漫全境聚合
- 全球影剧类别
- 全能电影榜单
- 全球综艺频道
- 影剧流行风向
- 平台分流片库
- 流媒体 TOP10

Each category exposes the script's relevant secondary choices as existing `CategoryFilter` groups, such as data source, region, platform, media type, year, genre, ranking mode, and sorting.

This feature does not add playback extraction. Items are discovery entries represented as `VodItem` cards and follow the existing open/detail behavior used by built-in media tabs.

## Architecture

Add a dedicated `GlobalCatalogController` and supporting service/client code instead of embedding Widget JavaScript in `MainWindow` or `PosterGridPage`.

The controller provides the same surface as other poster-grid controllers:

- `load_categories() -> list[DoubanCategory]`
- `load_items(category_id, page, filters=None) -> tuple[list[VodItem], int]`

The main window creates a `PosterGridPage` for this controller, registers it as a built-in tab with key `global_catalog`, title `环球片单`, and inserts it after the existing `douban` tab in both default tab definitions and built-in tab management definitions.

The controller delegates network work and mapping to a service layer. This keeps UI code limited to tab registration and signal wiring.

## Data Flow

The source normalizes all results to `VodItem`.

For TMDB-native categories, the service calls TMDB discovery/search/trending endpoints and maps the response directly to cards. The TMDB API key comes from the existing `AppConfig.metadata_tmdb_api_key`.

For external ranking sources, the service first obtains title or ID candidates, then resolves them through TMDB where practical:

- Bangumi calendar and airtime pages
- Bilibili PGC ranking
- AniList GraphQL ranking
- Jikan/MAL top anime
- Trakt ranking
- Douban public listing
- Rotten Tomatoes browse pages
- FlixPatrol top 10 pages

TMDB image paths are converted to poster/backdrop URLs. The card description contains date/ranking context plus the available overview. `vod_remarks` carries compact ranking or score text when available.

## Filters

The seven top-level categories map to stable category IDs. Each category owns a focused set of filters:

- Anime: source plus source-specific selectors such as date, Bilibili partition, Bangumi year/season/sort, TMDB sort, AniList sort, MAL sort.
- Global genres: media type, genre, region, ordering.
- Movies: mode plus general/year/genre selectors.
- Variety: region and list type.
- Trends: source plus IMDb, Rotten Tomatoes, Trakt, and Douban selectors.
- Platform matrix: content category, platform, sort.
- Streaming top 10: region, platform, media type.

Unsupported or irrelevant filter combinations fall back to the script's defaults rather than raising UI errors.

## Error Handling

Network and parsing failures are contained within the current category request. A failed request returns an empty page or a single text-style `VodItem` explaining the failure, matching existing controller behavior where possible.

Web-scraped sources are treated as best-effort. Parsing logic deduplicates titles, tolerates missing scores, and returns partial results when some title-to-TMDB matches fail.

Short in-memory caches are allowed for scrape-heavy Bangumi, Rotten Tomatoes, and FlixPatrol calls to reduce repeated requests during pagination and filter changes.

## Testing

Add tests before implementation:

- `MainWindow` shows built-in tabs in order with `环球片单` immediately after `豆瓣电影`.
- Built-in tab management includes `环球片单`, and the existing hide/rename/order mechanism can address it by key.
- `GlobalCatalogController.load_categories()` returns all seven categories with representative filters.
- A TMDB-backed category maps TMDB payloads into `VodItem` fields.
- An external ranking path resolves a title through TMDB and maps the result.
- A network or parse failure returns the expected empty/error result without raising.

## Non-Goals

- Do not add new top-level tabs for each module.
- Do not create a new UI component for this feature.
- Do not add or expose embedded Trakt credentials.
- Do not implement playback source resolution for discovery-only TMDB cards.
