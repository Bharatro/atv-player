# 我的追更详情页分集状态 Design

## Summary

Add explicit per-episode status styling to the `我的追更` detail page so users can distinguish:

- `已看`
- `已更新`
- `即将更新`
- `未更新`

The chosen presentation is an inline status badge placed after the episode title on the same row, plus a matching light border color around the episode card.

This design also extends TMDB-derived following detail data so `next_episode_to_air` can drive a precise `即将更新` state, including same-day cases such as `2026-05-26`.

## Goals

- Show a clear, stable status for each visible episode card in the following detail page.
- Show the same resolved status inside the episode preview dialog opened from the detail page.
- Let users mark the previewed episode as watched from that same preview dialog.
- Keep the status readable in single-column, two-column, and three-column episode layouts.
- Use both text and color so the meaning is understandable without memorizing colors.
- Treat TMDB `next_episode_to_air` as a first-class signal for `即将更新`.
- Avoid marking a same-day scheduled episode as `已更新` just because its `air_date` equals today.
- Keep status logic out of the rendering layer as much as possible.

## Non-Goals

- Do not add new episode rows that are not already present in the loaded episode list.
- Do not redesign the page layout beyond status badges and border accents on episode cards.
- Do not redesign the preview dialog layout beyond adding the episode status to its displayed metadata.
- Do not add a second progress-management flow; reuse the existing following progress write path.
- Do not introduce background refreshes or extra metadata fetches only for status display.
- Do not add hover popovers, tooltips, or separate legend UI in this iteration.
- Do not persist per-episode status in storage; it should be derived from existing detail data.

## User-Approved Decisions

- Visual direction: use the combined `状态标签 + 轻边框` approach.
- Badge placement: the status badge sits after the episode title on the same line.
- Base status definitions:
  - `已看`: current progress has reached the episode
  - `已更新`: not watched, already aired, episode number is within current known latest
  - `即将更新`: future episode, with `next_episode_to_air` taking precedence
  - `未更新`: no clear air signal or placeholder-only data
- Same-day scheduled episode rule:
  - if TMDB returns `next_episode_to_air` for `2026-05-26`, that episode should still display as `即将更新`
  - do not rely on `air_date > today` alone

## Current Problems

The current following detail episode UI already knows whether an episode is watched in the selected season, but it does not distinguish:

- already available but not watched
- scheduled next episode
- placeholder/not-yet-available episode rows

That creates two practical issues:

1. Users cannot quickly scan for the next released episode versus a future scheduled one.
2. TMDB’s `next_episode_to_air` signal is currently ignored in following-detail state rendering, so a same-day scheduled episode can be misread as already available.

## Recommended Approach

Keep the current episode grouping, selection, and card rendering structure, but add a small typed status layer between metadata parsing and UI painting.

Responsibilities by layer:

- metadata/following layer:
  - parse `next_episode_to_air`
  - expose enough typed detail to identify the scheduled next episode
  - resolve per-episode status from current progress, latest known aired episode, and next scheduled episode
- UI layer:
  - consume the resolved status
  - render inline badge text and border color
  - pass the same resolved status into the preview dialog instead of recomputing from raw TMDB fields there
  - avoid embedding TMDB-specific rules directly in widget code

This keeps the UI deterministic and avoids scattering episode-state rules across delegates, cards, and page-level glue.

## Status Rules

The status resolver should evaluate in this order:

1. `已看`
2. `即将更新`
3. `已更新`
4. `未更新`

### `已看`

An episode is `已看` when current progress is at or beyond that episode using the same season-aware comparison semantics already used by the following feature.

### `即将更新`

An episode is `即将更新` when either of these is true:

1. It exactly matches TMDB `next_episode_to_air` by `(season_number, episode_number)`.
2. There is no exact `next_episode_to_air` match, and its `air_date` is after the current Beijing date.

Important consequence:

- If `next_episode_to_air` is `S1E24` with `air_date = 2026-05-26`, that episode remains `即将更新` on `2026-05-26`, even though the date is not greater than today.

### `已更新`

An episode is `已更新` when:

- it is not `已看`
- it is not `即将更新`
- it belongs to the currently loaded episode list
- it is at or below the known latest aired episode for its season/progress context

Season safety rule:

- do not use a latest-aired value from one season to mark episodes in a different season as `已更新`
- comparison should stay within the same resolved season context already used by following progress logic

This should continue to align with current `latest_episode` behavior, including the existing `last_episode_to_air` fallback used in following metadata.

### `未更新`

An episode is `未更新` when none of the higher-priority statuses match, including:

- episode placeholders with no usable `air_date`
- rows beyond the known aired range that also do not match `next_episode_to_air`
- incomplete metadata where future scheduling is unknown

## Data Model Design

### New Typed Snapshot Field

Extend `FollowingDetailSnapshot` with a typed representation of the next scheduled episode, for example:

- `next_episode: FollowingEpisode | None`

Reasoning:

- `episodes` already carries typed episode rows used by the browser
- the next scheduled episode is conceptually part of the same detail snapshot
- the UI should not have to parse raw TMDB detail-field dictionaries to find it

### TMDB Detail Parsing

TMDB detail loading should keep recording raw detail fields as it does today, but also include `next_episode_to_air` in the data path that builds following snapshots.

Expected parsing flow:

- TMDB provider includes `next_episode_to_air` in `detail_fields`
- following metadata adds a helper similar to `_last_episode_to_air_from_detail_fields(...)`
- `build_snapshot_from_record(...)` resolves the raw next-episode payload into a typed `FollowingEpisode`

This keeps provider-specific payload parsing centralized in the metadata layer.

## Status Resolver Boundary

Introduce a small helper in `following_models.py` or an adjacent following-domain module to resolve per-episode status from:

- current season number
- current episode
- visible season number / fallback season
- known latest episode
- typed `next_episode`
- candidate episode row
- current date

The helper should return a stable symbolic state rather than colors or UI strings. Example shape:

- `watched`
- `released`
- `upcoming`
- `pending`

The UI layer can then map those symbols to Chinese badge text and colors.

## UI Design

### Badge Placement

Each episode card title row becomes:

- episode title
- inline status badge immediately after the title on the same row

Example:

- `128. 新章   [已更新]`

This keeps the card compact and avoids introducing a new status row above the title.

### Styling

Each resolved status maps to:

- badge text
- badge background/text color
- light border accent color on the whole card

Recommended palette intent:

- `已看`: green
- `已更新`: blue
- `即将更新`: orange
- `未更新`: gray

The border treatment should stay subtle so the badge remains the primary signal and the episode grid does not become noisy in multi-column modes.

### Rendering Targets

Apply the same status presentation in both right-side episode renderers:

- custom `FollowingEpisodeCard` grid cards
- `EpisodeItemDelegate` list-style row rendering
- `FollowingEpisodePreviewDialog` metadata line / status row

Even if the detail page currently favors the card/grid presentation, the delegate path should stay behaviorally aligned.

### Preview Dialog

When a user opens the episode preview dialog from a card or list row, the dialog should display the same resolved symbolic status as the source card.

Recommended behavior:

- keep the existing title, air date, runtime, overview, and image structure
- add the localized status text to the dialog metadata area
- do not recompute status in the dialog from partial information; pass the already resolved state from the browser/detail-page path
- add a `标记本集已看` action button in the dialog
- clicking that action should advance following progress to the previewed episode's `(season_number, episode_number)` using the existing `record_playback_progress(...)` flow
- after the action succeeds, close the dialog and refresh the detail page state so the source card and metadata update together

## Fallback Rules

- If `next_episode_to_air` is missing, do not infer same-day `即将更新`; fall back to date-based future detection only.
- If `air_date` is missing, the episode cannot become `即将更新` through the date rule.
- If season numbers are incomplete, reuse existing following fallback-season logic rather than inventing new season heuristics.
- If `latest_episode` exceeds the count of loaded rows, only status the rows that actually exist in the current episode list.
- If a row matches both a future-looking date rule and watched progress, `已看` wins.
- If a row matches both `latest_episode` and `next_episode_to_air`, `即将更新` wins.

## Testing Strategy

Update focused tests in:

- `tests/test_following_metadata.py`
- `tests/test_following_episode_browser.py`

Add or update coverage for:

- parsing `next_episode_to_air` into typed following detail data
- same-day `next_episode_to_air` resolving to `即将更新`
- watched state outranking all other states
- upcoming state outranking released state
- missing `air_date` rows falling back to `未更新`
- badge text appearing on the same title row
- card/list render paths using the same symbolic status mapping
- preview dialog showing the same resolved status as the activated episode card
- preview dialog action marking the current episode as watched and calling the existing progress update path with the previewed episode coordinates

## Implementation Plan Shape

Expected files:

- `src/atv_player/following_models.py`
- `src/atv_player/following_metadata.py`
- `src/atv_player/metadata/providers/tmdb.py`
- `src/atv_player/ui/following_episode_browser.py`
- `src/atv_player/ui/following_detail_page.py`
- `tests/test_following_metadata.py`
- `tests/test_following_episode_browser.py`
- `tests/test_following_detail_page_ui.py`

Implementation should stay narrow:

- extend metadata parsing just enough to carry `next_episode_to_air`
- add one small status resolver in the following domain layer
- update episode UI rendering to consume the symbolic status
- cover precedence and same-day scheduling with tests before behavior changes
