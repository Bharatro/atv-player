# YouTube Category Config Source Design

## Context

The app already has a built-in YouTube poster-grid source backed by `YouTubeController`.
It defines categories in `_DEFAULT_CATEGORIES`, limited built-in filters in `_DEFAULT_FILTERS`,
and renders those filters through the existing `PosterGridPage` filter panel.

Users need YouTube categories and filters to be configurable from one selected source:

- built-in defaults
- a remote JSON/JSONC file, such as `http://192.168.50.60:4567/zx/json/youtube.json`
- a local JSON/JSONC file

The remote file follows the TVBox `homeContent` shape with top-level `class` and `filters`.
It may include `//` comments, so strict JSON parsing is not enough.

## Goals

- Add a single current YouTube category configuration source: built-in, remote URL, or local file.
- Parse TVBox-style JSONC category files with `class` and `filters`.
- Support `LIST:` category ids by turning the list members into an automatic keyword filter.
- Support YouTube entry ids compatible with the referenced Java service:
  - video id as bare YouTube video id
  - channel as `channel@<channel_id_or_handle>`
  - playlist as `playlist@<playlist_id>`
- Keep old `yt:video:`, `yt:channel:`, and `yt:playlist:` ids readable for history and cached entries.
- Reuse the existing poster-grid filter UI.
- Cache the last successfully loaded remote or local config and fall back safely when loading fails.

## Non-goals

- Managing multiple YouTube category sources.
- Merging multiple remote/local sources.
- Fully reproducing Java downloader search filter semantics when `yt-dlp` cannot expose an equivalent.
- Adding a new top-level YouTube management screen.
- Destructive migration of existing playback history.

## Configuration Storage

Extend `AppConfig` and `app_config` with:

- `youtube_category_source_type`: `builtin`, `remote`, or `local`
- `youtube_category_source_value`: remote URL or local file path
- `youtube_category_cache_json`: last successfully parsed source text
- `youtube_category_cache_refreshed_at`: Unix timestamp of last successful refresh
- `youtube_category_cache_error`: last loading/parsing error, empty on success

The default source type is `builtin`, with empty source value and empty cache.

Loading behavior:

- `builtin`: use current built-in defaults.
- `remote`: fetch the configured URL. If fetch and parse succeed, update cache. If they fail, use cached config when available. If no cache exists, fall back to built-in defaults.
- `local`: read the configured file. If read and parse succeed, update cache. If they fail, use cached config when available. If no cache exists, fall back to built-in defaults.

This mirrors the existing custom live source strategy: remote failure should not make a working page empty if a cache exists.

## Parser

Add a small YouTube category config parser that returns a typed internal model and does not depend on Qt.

Input:

- JSON or JSONC text
- top-level `class`, expected as a list
- top-level `filters`, expected as a mapping keyed by category id

JSONC handling:

- allow `//` line comments and line-end comments
- preserve string contents while stripping comments
- reject malformed JSON after comment stripping with a clear error

Category mapping:

- `class[].type_id` -> raw category id
- `class[].type_name` -> display name
- blank ids or blank names are skipped
- order follows the source file

Filter mapping:

- `filters[category_id][]` -> `CategoryFilter`
- group `key` -> `CategoryFilter.key`
- group `name` -> `CategoryFilter.name`
- group `value[]` -> options
- option `n` -> `CategoryFilterOption.name`
- option `v` -> `CategoryFilterOption.value`
- malformed groups or empty option lists are skipped
- empty option values are preserved because they represent defaults such as `全部`

## `LIST:` Categories

For `type_id` values like:

```text
LIST:HDR,Girls HDR,Landscape HDR,Walk HDR
```

the app keeps one visible category using the source `type_name`, then adds an automatic filter group before any file-provided filters.

Automatic filter:

- key: `list_keyword`
- name: `关键词`
- options:
  - `HDR` -> `HDR`
  - `Girls HDR` -> `Girls HDR`
  - `Landscape HDR` -> `Landscape HDR`
  - `Walk HDR` -> `Walk HDR`

The default query uses the first list keyword when no explicit `list_keyword` value is selected.

If the file also defines filters for the same `LIST:` category id, those filters are appended after the automatic keyword group.

## Query Planning

`YouTubeController.load_items(category_id, page, filters)` first converts the category and selected filters into a query plan.

Supported entry forms:

- bare video id: open a single video detail/play request
- normal text: YouTube search query
- `LIST:a,b,c`: search with the first keyword or selected `list_keyword`
- `@handle`: channel upload listing
- `channel@UC...` or `channel@handle`: channel upload listing
- `playlist@PL...`: playlist video listing

Filter behavior:

- `list_keyword`: replaces the base search text for `LIST:` categories.
- `tid`: replaces the base search text or entry. If the selected value is `@...`, `channel@...`, or `playlist@...`, it becomes that entry type.
- `time`: appends to the search text, for example `電影 2024`.
- `sort`, `type`, and `format`: remain visible in the UI and are included in the query plan. The first implementation maps only values that are reliable with the current `yt-dlp` path. Unsupported values are ignored for loading and logged at debug level.
- other non-empty filter values: append to the search text so custom dimensions from remote files still affect results.

Search continues to use the current `ytsearchall:` path unless the final plan is a channel or playlist entry.

## ID Format

Newly generated YouTube items use:

- video: bare YouTube video id, for example `abc123xyz89`
- channel: `channel@<channel_id_or_handle>`
- playlist: `playlist@<playlist_id>`

Legacy ids remain accepted:

- `yt:video:<id>` -> `<id>`
- `yt:channel:<id_or_url>` -> `channel@<id_or_handle>`
- `yt:playlist:<id>` -> `playlist@<id>`

Normalization happens at controller boundaries:

- list item mapping
- `build_request()`
- playback history reopen paths
- any stored source key read path that may contain the old format

New history entries and newly generated cards should write only the new format.

## UI

Extend the existing Advanced Settings `YouTube` tab with a `分类配置` group.

Style requirements:

- Keep the existing Advanced Settings visual style, spacing, form layout, combo box treatment, button styling, and label hierarchy.
- Reuse the existing local UI helpers and theme tokens used by `AdvancedSettingsDialog`.
- Do not introduce a visually separate management page, card-heavy layout, new color palette, or custom control style.
- Place the new group so it reads as a native continuation of the current YouTube settings.

Controls:

- source type selector: `内置`, `远程 URL`, `本地 JSON`
- remote URL input, enabled only for remote mode
- local file path input and file picker, enabled only for local mode
- status label showing last successful refresh, parsed category count, parsed filter group count, or last error
- `测试加载` button: reads and parses the selected source without saving
- `刷新缓存` button: reads the current saved source and updates cache

Saving settings:

- validates the selected source fields
- saves source type and value
- does not require a network request at save time
- if the YouTube page is already open, refreshes categories after the dialog closes

`测试加载` should be user-facing and precise:

- success: show category count and filter group count
- failure: show parse/load error without changing saved settings or cache

## Failure Handling

- Malformed JSONC should show a clear parse error and not crash category loading.
- Remote HTTP failure should use cache if available.
- Local file read failure should use cache if available.
- Cache parse failure should be treated as no cache and fall back to built-in defaults.
- If both configured source and cache fail, built-in categories should be available.
- Unsupported search filter keys should not prevent loading results.

## Tests

Parser tests:

- parses JSONC with `//` comments
- maps `class` to categories in source order
- maps `filters` to `CategoryFilter` and `CategoryFilterOption`
- preserves empty filter option values
- skips malformed categories and filter groups
- expands `LIST:` into an automatic `关键词` filter
- appends file-provided filters after the automatic `LIST:` filter

Config/source tests:

- built-in source returns built-in defaults
- remote source loads, parses, and updates cache
- remote failure uses existing cache
- remote failure without cache falls back to built-in defaults
- local source loads and updates cache
- cache parse failure falls back to built-in defaults

Controller tests:

- `tid` replaces base query
- `time` appends to base query
- `LIST:` default uses the first keyword
- selected `list_keyword` replaces the default keyword
- `@handle` maps to channel loading
- `channel@...` maps to channel loading
- `playlist@...` maps to playlist loading
- newly mapped video items use bare video ids
- newly mapped channels use `channel@...`
- newly mapped playlists use `playlist@...`
- old `yt:video:`, `yt:channel:`, and `yt:playlist:` ids still build requests

UI tests:

- Advanced Settings YouTube tab shows category source controls
- remote/local fields enable and disable with source type
- invalid source values are rejected on save where applicable
- test-load success reports parsed counts
- test-load failure reports an error without saving settings
- saving settings refreshes the YouTube page categories when it is open

## Risks

- `yt-dlp` search does not expose a direct equivalent for every Java downloader search filter.
  Mitigation: keep `sort`, `type`, and `format` in the query plan and map only reliable values first; ignore unsupported values with debug logging.
- JSONC stripping can corrupt strings if implemented with naive regex.
  Mitigation: use a small scanner that tracks string state and escapes, with focused tests.
- Changing YouTube ids can affect history reopening.
  Mitigation: normalize old ids at read/open boundaries and write only the new format for new records.
- Remote category files may include very large filter groups.
  Mitigation: reuse existing scrollable filter panel and skip malformed groups without failing the whole source.

## Acceptance Criteria

- Users can choose built-in, remote URL, or local JSON category configuration from Advanced Settings.
- The provided remote `youtube.json` shape loads despite comments.
- YouTube categories and filters reflect the selected source.
- `LIST:` categories display as one category with a keyword filter.
- Channel, playlist, and video ids use the new format for newly generated cards.
- Old `yt:*` ids remain openable.
- Remote/local source failures do not break the YouTube tab when cache or built-in defaults are available.
