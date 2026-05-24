# 我的追更 Design

## Summary

Add a full local `我的追更` feature for series tracking. Users can add a title to following from the player after metadata is available, or search external media catalogs from the following page and add a title directly. The feature stores media metadata, episode progress, external/internal IDs, periodically checks for updates, shows update markers on the following page, and shows a homepage prompt only when the user had already watched to the previous latest episode.

The feature is independent from `我的收藏`. It reuses existing metadata providers, poster loading, playback routing, and search/playback flows, but owns its own persistence, update state, reminder state, and detail page.

## Goals

- Add a dedicated `我的追更` page.
- Add a player detail-area button to add/remove the current metadata-identified media from following.
- Let users search TMDB/Bangumi/豆瓣 media records from the following page and add a title before any playback source is chosen.
- Persist basic information: title, original title, cover, backdrop/poster, rating, category, season, provider priority, external IDs, and internal source bindings.
- Persist episode state: current watched episode, playback position, latest known episode, total episodes, last played time, and whether the user had watched to the previous latest episode.
- Persist update-check state: last checked time, next check time, errors, update flags, new episode count, and homepage prompt state.
- Check updates after startup delay and then on a timer, with 5-minute checks during common update windows.
- Show update reminders in `我的追更`.
- Show a homepage prompt only when a user had reached the old latest episode and new episodes appear.
- Provide a rich following detail page with title, cover, backdrop, overview, episode list, episode stills, episode summaries, cast/crew, IDs, episode state, and search-play controls.

## Non-Goals

- Do not merge following into favorites.
- Do not add remote sync, account sync, tags, folders, or sharing.
- Do not block playback when metadata update checks fail.
- Do not treat playback-source episode availability as the canonical latest episode count.
- Do not implement related works/person filmographies in the first release.
- Do not build a separate always-running process outside the Qt app.

## Key Decisions

- Latest episode checks are external-metadata-first.
- Anime priority: `Bangumi > TMDB > 豆瓣`.
- Live-action/movie priority: `TMDB > 豆瓣 > Bangumi`.
- Playback sources are used for playback/search and optional internal bindings, not as the canonical latest episode source.
- Search from the following page searches external media records first. Users can bind or find playback sources from the following detail page with `搜索播放`.
- Homepage prompts appear only for entries where the user had watched to the previous latest episode before new episodes appeared.
- The detail page should reference `/home/harold/Downloads/Telegram Desktop/nostr (5).html#detail` for information hierarchy: a returnable detail sheet/page, large backdrop area, action row, horizontal episode cards, horizontal cast/crew rail, and episode preview behavior.

## Architecture

Create an independent following domain:

- `src/atv_player/following_repository.py`
- `src/atv_player/following_models.py`
- `src/atv_player/controllers/following_controller.py`
- `src/atv_player/following_update_service.py`
- `src/atv_player/ui/following_page.py`
- `src/atv_player/ui/following_detail_page.py`

`MainWindow` should integrate the new page, header button/tab entry, homepage prompt handling, player button callbacks, and search-play routing. `app.py` should construct the repository, controller, update service, and inject existing metadata/search dependencies.

Reuse these existing components:

- `MetadataScrapeService` for catalog search and candidate grouping.
- TMDB/Bangumi/豆瓣 providers for media detail and episode data.
- `MetadataCache` for provider response caching where existing APIs fit.
- Existing poster loading utilities for covers/backdrops/stills.
- Existing playback routing/global search behavior for `搜索播放`.
- Existing player progress reporting/history inference for current episode and playback position where available.

## Data Model

Add following-specific dataclasses in `src/atv_player/following_models.py`:

- `FollowingRecord`
- `FollowingExternalIds`
- `FollowingSourceBinding`
- `FollowingEpisode`
- `FollowingDetailSnapshot`
- `FollowingCardItem`
- `FollowingUpdateResult`

The SQLite store should use a lightweight row table plus JSON snapshots:

### `following`

- `id INTEGER PRIMARY KEY`
- `title TEXT NOT NULL`
- `original_title TEXT NOT NULL DEFAULT ''`
- `media_kind TEXT NOT NULL DEFAULT ''`
- `season_number INTEGER NOT NULL DEFAULT 0`
- `poster TEXT NOT NULL DEFAULT ''`
- `backdrop TEXT NOT NULL DEFAULT ''`
- `rating TEXT NOT NULL DEFAULT ''`
- `provider TEXT NOT NULL DEFAULT ''`
- `provider_id TEXT NOT NULL DEFAULT ''`
- `provider_priority_json TEXT NOT NULL DEFAULT '[]'`
- `external_ids_json TEXT NOT NULL DEFAULT '{}'`
- `source_bindings_json TEXT NOT NULL DEFAULT '[]'`
- `current_episode INTEGER NOT NULL DEFAULT 0`
- `position_seconds INTEGER NOT NULL DEFAULT 0`
- `watched_latest_episode INTEGER NOT NULL DEFAULT 0`
- `latest_episode INTEGER NOT NULL DEFAULT 0`
- `previous_latest_episode INTEGER NOT NULL DEFAULT 0`
- `total_episodes INTEGER NOT NULL DEFAULT 0`
- `has_update INTEGER NOT NULL DEFAULT 0`
- `new_episode_count INTEGER NOT NULL DEFAULT 0`
- `homepage_prompt_pending INTEGER NOT NULL DEFAULT 0`
- `prompt_snoozed_until INTEGER NOT NULL DEFAULT 0`
- `created_at INTEGER NOT NULL DEFAULT 0`
- `updated_at INTEGER NOT NULL DEFAULT 0`
- `last_played_at INTEGER NOT NULL DEFAULT 0`
- `last_checked_at INTEGER NOT NULL DEFAULT 0`
- `next_check_after INTEGER NOT NULL DEFAULT 0`
- `last_error TEXT NOT NULL DEFAULT ''`

Uniqueness should be based on canonical identity:

- preferred key: `(provider, provider_id)`
- fallback key: a normalized title/year/media-kind key if provider identity is unavailable

### `following_detail_snapshots`

- `following_id INTEGER PRIMARY KEY`
- `overview TEXT NOT NULL DEFAULT ''`
- `cast_json TEXT NOT NULL DEFAULT '[]'`
- `crew_json TEXT NOT NULL DEFAULT '[]'`
- `episodes_json TEXT NOT NULL DEFAULT '[]'`
- `posters_json TEXT NOT NULL DEFAULT '[]'`
- `backdrops_json TEXT NOT NULL DEFAULT '[]'`
- `refreshed_at INTEGER NOT NULL DEFAULT 0`

Episode snapshot entries should support:

- `episode_number`
- `season_number`
- `title`
- `overview`
- `air_date`
- `still`
- `runtime`
- `is_special`

## Repository

`FollowingRepository` is responsible for local persistence only:

- initialize tables
- upsert a following record from a metadata candidate/detail
- load paged cards with keyword/filtering
- load one record and detail snapshot
- delete records
- save detail snapshots
- update watched episode/progress
- update source bindings
- update check state
- update reminder state
- query prompt-pending rows for homepage reminders

It should not call metadata providers, open player windows, or show UI.

## Controller

`FollowingController` coordinates repository, metadata search/detail, and view models:

- search external media records by keyword using provider priority
- create following records from selected candidates
- add current player item after metadata is available
- build following page card models
- build following detail view models
- delete/unfollow
- mark watched-to-latest
- record playback progress
- clear homepage prompt state
- request manual update checks for one or many records

Provider priority should be automatic:

- anime: `Bangumi`, `TMDB`, `豆瓣`
- live-action/movie: `TMDB`, `豆瓣`, `Bangumi`

The controller should tolerate provider failures and keep persisted data usable.

## Update Service

`FollowingUpdateService` runs inside the Qt app using `QTimer` for scheduling and worker threads for network-bound metadata checks.

Scheduling:

- startup check: 60 seconds after main window is ready
- normal interval: every 6 hours
- common update windows in Beijing time: `00:00-02:00`, `10:00-13:00`, `18:00-23:30`
- during update windows: check due records every 5 minutes
- concurrency limit: 3 records

Check algorithm:

1. Load due following records.
2. For each record, try providers in the record's priority order.
3. Fetch media detail and episode list.
4. Compute `latest_episode` from normal episodes with positive episode numbers.
5. Compute `total_episodes` from provider total count where available, otherwise the max known episode number.
6. If `latest_episode > previous latest_episode`, set `has_update=true` and `new_episode_count`.
7. If `watched_latest_episode=true` or `current_episode >= previous_latest_episode`, set `homepage_prompt_pending=true`.
8. Persist detail snapshot updates when new or better detail data is available.
9. If one provider fails, try the next provider. If all fail, persist `last_error` and keep previous update flags.

The service should emit or callback update summaries so the page and homepage prompt can refresh without polling the database manually.

## Player Integration

The player detail area should get a following toggle near the existing favorite/metadata actions. The button is visible only when current media identity is known well enough to save.

When adding from playback:

- use the current hydrated metadata as the primary media snapshot
- infer current episode from the current playlist item and existing episode-title inference helpers
- save playback position
- save source binding for the current source kind/key/vod ID where available
- if external IDs are missing, open a compact metadata match picker before saving, rather than silently saving a weak record

When playback progress reports:

- update `current_episode`
- update `position_seconds`
- update `last_played_at`
- set `watched_latest_episode=true` when `current_episode >= latest_episode` and the latest episode is known
- clear `homepage_prompt_pending` when the user starts or completes the newly available latest episode

## Following Page

`FollowingPage` should be a dedicated page next to `我的收藏`.

Top controls:

- keyword search
- `添加追更`
- `检查更新`
- `只看有更新`
- page size and pagination using the existing `20/30/50/100` pattern

Card content:

- cover
- title
- rating
- source/provider badges
- watched episode
- latest episode
- total episode count
- update marker
- last checked time
- error hint if the latest check failed

Interactions:

- activate card to open following detail page
- context menu or inline action to unfollow
- manual refresh/check update
- filter to updated items

The update marker should be visible but not disruptive. Homepage prompts handle the disruptive case.

## Search Add Flow

The following page's `添加追更` opens a search dialog:

- input title/year/category
- provider tabs/groups from metadata search results
- recommended candidate highlighted using automatic provider priority
- each result shows title, year, provider, poster if available, and type hint
- selecting a candidate creates the following record and fetches a detail snapshot

If multiple candidates have close match scores or the same title/year across providers, require explicit user selection. Do not auto-add those results.

## Following Detail Page

The detail page should follow the information hierarchy from the referenced `nostr (5).html#detail` page, adapted to Qt and the current theme.

Layout:

- return button/header
- large backdrop/still area
- poster fallback mode: blurred poster background plus centered poster when no backdrop exists
- title, rating, year, kind, episode summary, provider badges, external IDs
- action row: `搜索播放`, `手动检查`, `标记追到最新`, `取消追更`
- overview text collapsed to five lines by default with an expand/collapse control when the text is longer
- season tabs when multiple seasons exist
- horizontal episode cards with still, episode number, title, air date, overview, and watched/new flags
- episode preview dialog/sheet for full still and complete overview
- horizontal cast/crew rail with avatar, name, and role/job

Out of first-release scope:

- actor filmography/related works navigation

## Homepage Prompt

After update checks, `MainWindow` should query prompt-pending following records and show a compact prompt when the main/home view is available.

Prompt content:

- title
- new episode count
- latest episode number
- actions: `查看详情`, `搜索播放`, `稍后提醒`

Rules:

- only rows with `homepage_prompt_pending=true` are shown
- no prompt if the user had not reached the old latest episode
- opening the following detail page clears `homepage_prompt_pending` but does not clear `has_update`
- starting playback for the new latest episode clears `homepage_prompt_pending`
- `稍后提醒` clears the current prompt and sets `prompt_snoozed_until` to 24 hours later; update checks must not set a new homepage prompt for that record before the snooze time expires

## Error Handling

- Metadata search failures should show provider-level error text without failing other provider groups.
- Add-following should fail visibly if no provider identity can be saved.
- Update checks should preserve previous latest/update state on provider failure.
- Detail pages should show persisted snapshots if fresh provider data is unavailable.
- One broken following item must not block checks for other items.

## Testing

Primary tests:

- `tests/test_following_repository.py`
- `tests/test_following_controller.py`
- `tests/test_following_update_service.py`
- `tests/test_following_page_ui.py`
- `tests/test_following_detail_page_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_main_window_ui.py`
- `tests/test_app.py`

Coverage should include:

- repository upsert/identity/deduplication
- JSON external IDs/source bindings/detail snapshots
- update check state transitions
- homepage prompt only when watched to previous latest
- provider fallback on failure
- automatic provider priority by media kind
- search-add flow requiring selection
- player add-following flow with current episode/progress
- detail page rendering fallback when stills/cast are missing
- prompt clearing when playback reaches the new latest episode

## Open Implementation Notes

- The implementation should prefer small modules over adding more responsibility to `MainWindow` or `player_window.py`.
- Keep following-specific dataclasses in `following_models.py`; import them from UI/controller/repository code instead of adding more following-only types to `models.py`.
- Existing metadata providers may need small extensions to expose richer episode snapshots and image lists in a reusable shape.
- The update service should avoid network work on the UI thread.
