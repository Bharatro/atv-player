# Following Discovery Search Year And Cache Design

## Goal

Refine the `添加追更` dialog in two targeted ways:

- Add a year input on the `搜索` tab and pass valid years through to TMDB-backed search
- Make `推荐` and `热门` reuse stable disk cache so repeated tab switches and app restarts stay fast

## Scope

This round includes:

- A search-tab-only year input field with validation
- Passing the validated year into the existing metadata search pipeline
- Keeping URL direct-open search behavior unchanged
- Reworking recommendation cache boundaries so disk cache remains reusable across restarts
- Preserving trending disk cache behavior with explicit “cache hit means return immediately” semantics

This round does not include:

- Local-only filtering of already fetched search results
- Changing `筛选` tab controls
- Background refresh when cache is hit
- Changes to the main following page outside the add-following dialog

## Current Problems

### Search

The current `搜索` tab only sends a title string through `FollowingController.search_media()`.

TMDB search already supports year parameters:

- movie search uses `year`
- TV search uses `first_air_date_year`

But the add-following dialog does not expose or pass a year value, so users cannot narrow search results by year.

### Recommendation And Trending Performance

`热门` and `推荐` already have cache plumbing, but the current user-visible behavior still feels slow when switching tabs or reopening the app.

The main issue is recommendation cache stability:

- recommendation results are cached with a key that includes the full seed list and current follow/favorite exclusion sets
- this makes the cache easy to invalidate even when the underlying recommendation pool has not meaningfully changed
- after restart, the feature often behaves like a cold load because the key no longer matches

## Approved Direction

### Search Year Filter

- Put the year control on the `搜索` tab only
- Use a free text year input, default empty
- Empty value means “no year filter”
- Non-empty but invalid values block search and show `请输入 4 位年份`
- Valid 4-digit years are sent to the backend search pipeline
- URL direct-open searches ignore the year input

### Cache Behavior

- Cache hit means use the cache immediately
- No background refresh on cache hit
- Network requests happen only when cache is absent or expired

## Recommended Approach

Use a thin UI change for search-year input and a service-layer cache boundary change for recommendation reuse.

This keeps the dialog simple while fixing the actual performance problem in the data layer instead of masking it in the UI.

## UX Design

### Search Tab

The `搜索` tab keeps the current title / URL input and adds a second input for year.

Behavior:

- title empty: block search with the existing prompt
- year empty: search normally without year constraint
- year has value but is not exactly 4 digits: block search and show `请输入 4 位年份`
- year is valid: include it in the search request
- URL query: continue direct URL resolution and ignore year

The year input is only visible on the `搜索` tab.

### Recommendation And Trending Tabs

No new controls are added.

Behavior:

- if dialog in-memory tab state exists, render it immediately
- otherwise, load from disk cache if present and still valid
- if no valid cache exists, request fresh data and then persist it

## Architecture

### UI Layer

`FollowingSearchDialog` will:

- add a year input field next to the search input on the `搜索` tab
- validate the input before dispatching a search request
- include `year` in search-tab state keys so cached tab results remain distinct per query/year combination
- keep other tabs unchanged

### Controller Layer

`FollowingController.search_media()` will accept an optional `year` argument.

Rules:

- plain text search creates `MetadataQuery(title=..., year=...)`
- URL candidates continue the current direct-resolution path and do not use `year`

### Discovery Service Layer

`TMDBDiscoveryService` will keep separate behavior for trending and recommendation.

#### Trending

- cache key remains query-driven: list key, media type, page
- cache hit returns immediately
- no refresh behind the scenes

#### Recommendation

Recommendation caching changes from “cache the final filtered result” to “cache the recommendation candidate pool”.

The recommendation candidate pool cache key includes only stable recommendation inputs:

- recommendation seeds and their stable signature

It does not include current:

- `favorite_provider_ids`
- `following_provider_ids`

On read:

1. load the cached candidate pool if valid
2. filter out items already followed or favorited using the current runtime sets
3. return the filtered result

On miss:

1. fetch recommendation rows from TMDB using the current seeds
2. build and persist the candidate pool
3. filter the pool against current follow/favorite sets
4. return the filtered result

This preserves correctness while making cache reuse stable across repeated opens and app restarts.

## Data Flow

### Search

1. User opens `搜索`
2. User enters title and optionally a 4-digit year
3. Dialog validates:
   - invalid non-empty year -> stop and show `请输入 4 位年份`
   - valid year or empty year -> continue
4. Controller dispatches metadata search
5. TMDB search receives the year when applicable
6. Results render as normal search cards

### Recommendation

1. User opens `推荐`
2. Dialog checks in-memory tab state
3. If absent, service checks disk cache for recommendation candidate pool
4. If cache hits, service filters against current follow/favorite sets and returns immediately
5. If cache misses, service fetches and persists the pool, then filters and returns

### Trending

1. User opens `热门`
2. Dialog checks in-memory tab state
3. If absent, service checks disk cache by query key
4. If cache hits, return immediately
5. If cache misses, fetch, persist, and return

## Error Handling

- Invalid year input is a validation error, not a network error
- URL search continues to follow existing direct-resolution error paths
- Recommendation and trending network failures continue to surface as existing dialog errors
- Cache read failures remain soft failures and fall back to normal network fetch

## Testing

### UI Tests

Add dialog coverage for:

- search tab shows the year input and other tabs hide it
- empty year allows search
- invalid year blocks search and shows `请输入 4 位年份`
- valid 4-digit year is passed through search requests
- URL searches ignore year
- search tab cached state key includes both query and year

### Controller Tests

Add coverage for:

- `search_media(year=...)` forwarding the year into `MetadataQuery`
- URL candidate search ignoring the supplied year

### Discovery Service Tests

Add coverage for:

- trending disk cache still hits across service instances
- recommendation disk cache hits across service instances when seed signature is unchanged
- changing follow/favorite exclusion sets does not trigger a new recommendation network request when the cached candidate pool is still valid
- cached recommendation pool is filtered differently for different runtime exclusion sets

## Files Affected

- `src/atv_player/ui/following_search_dialog.py`
- `src/atv_player/controllers/following_controller.py`
- `src/atv_player/metadata/discovery.py`
- `tests/test_following_search_dialog_ui.py`
- `tests/test_following_controller.py`
- `tests/test_metadata_discovery_service.py`

## Implementation Notes

- Use the existing TMDB search support instead of adding a second search path
- Keep validation in the dialog so invalid year input never reaches the controller
- Keep recommendation cache payload format close to `DiscoveryResult` item shape to minimize migration risk
- Do not add automatic refresh-on-hit behavior in this round
