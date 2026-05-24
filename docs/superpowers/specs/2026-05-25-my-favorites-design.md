# My Favorites Design

## Summary

Add a local `我的收藏` feature for videos. Users can favorite a video from the list-page context menu and from the player window. Favorites are shown in a dedicated poster-card page, can be reopened through their original source, and can be deleted individually or in bulk.

Each favorite stores the original `vod_name` snapshot from the time it was collected. When the favorites page refreshes, the app re-resolves each favorite through its original source and compares the latest `vod_name` against that snapshot. If the title changed, the card shows a weak visual update hint.

## Goals

- Add one shared local favorites store for video items across supported sources.
- Let users add or remove favorites from both the list page and the player window.
- Show favorites in a dedicated card-based `我的收藏` page.
- Persist the original title snapshot and detect later `vod_name` changes.
- Let users reopen favorites through the same source-specific playback routing already used elsewhere.
- Support deleting selected favorites and clearing the current filtered result set.

## Non-Goals

- Track episode-level or playlist-item title changes.
- Add remote sync, sharing, tags, folders, or manual favorite editing.
- Move playback-history behavior into the favorites feature.
- Add intrusive update prompts such as dialogs, toasts, or banners.
- Treat favorites as an `AppConfig` field.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/favorites_repository.py`
- `src/atv_player/controllers/favorites_controller.py`
- `src/atv_player/ui/favorites_page.py`
- `src/atv_player/ui/browse_page.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/app.py`

Primary verification should live in:

- `tests/test_favorites_repository.py`
- `tests/test_favorites_controller.py`
- `tests/test_browse_page_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_main_window_ui.py`
- `tests/test_app.py`

## Design

### Data Model

Favorites should use a dedicated local SQLite repository, following the same pattern as `LocalPlaybackHistoryRepository`.

Add a new favorite record model with fields covering identity, display snapshot, and update state:

- `source_kind: str`
- `source_key: str`
- `source_name: str`
- `vod_id: str`
- `vod_name_snapshot: str`
- `latest_vod_name: str`
- `vod_pic: str`
- `vod_remarks: str`
- `title_changed: bool`
- `created_at: int`
- `updated_at: int`

Identity must be keyed by:

- `source_kind`
- `source_key`
- `vod_id`

This keeps favorites stable across built-in sources and plugin-backed sources without inventing a new global ID format.

Normalization rules:

- `vod_name_snapshot` is required when saving a favorite.
- `latest_vod_name` defaults to the snapshot title on first save.
- `source_key` defaults to `""` for sources that do not need it.
- duplicate favorites overwrite display metadata and timestamps instead of creating extra rows.

### Repository

Create `FavoritesRepository` backed by a new `favorites` table.

Repository responsibilities:

- initialize the table
- upsert one favorite
- delete one or many favorites
- delete a filtered result set
- load paged favorites with keyword filtering
- update stored refresh state such as `latest_vod_name` and `title_changed`
- answer whether a given item is already favorited

Repository non-responsibilities:

- no controller lookups
- no remote detail loading
- no `OpenPlayerRequest` building

This keeps persistence separate from source-specific refresh and playback routing.

### Source Identity and Display Snapshot

A saved favorite must capture the source routing information needed to reopen it later:

- browse/detail items use `source_kind="browse"`
- plugin items use `source_kind="spider_plugin"` plus `source_key=plugin_id`
- built-in media sources reuse the existing kinds already supported by `MainWindow.open_history_detail()`

The save path should persist the best available display metadata at the moment of favoriting:

- title snapshot from `vod.vod_name`
- poster from `vod.vod_pic`
- remarks from `vod.vod_remarks`
- source name from the active controller or tab label

The feature only compares the main video title:

- compare latest `vod_name`
- ignore episode, playlist-item, and per-track title changes

### Favorites Page

Add a dedicated `FavoritesPage` with poster-card presentation, not a table.

The page should follow the app's existing poster-grid visual language, but it should manage favorites-specific actions and loading rather than reusing `HistoryPage`.

Top-level controls:

- search input for title filtering
- `刷新`
- `删除选中`
- `清空当前结果`
- pagination controls
- page-size selector following the existing `20/30/50/100` pattern

Card content should include:

- poster image
- latest title
- source label
- collect time
- optional secondary text with the original snapshot title when the title changed

The update hint should stay subtle:

- use a weak border-color accent on changed cards
- add a small icon indicator
- do not render `标题已更新` as prominent text on the main card surface

Double-clicking or activating a card should reopen the item through its original source.

### Title Refresh and Change Detection

`FavoritesController.load_page(...)` should load persisted favorites first, then resolve the current page of favorites through their original sources.

Refresh algorithm:

1. load one page of favorite records from the repository
2. for each record, look up the matching source adapter
3. fetch the latest detail object for that favorite
4. compare latest `vod_name` with `vod_name_snapshot`
5. persist `latest_vod_name`, poster/remarks refreshes, and `title_changed`
6. return UI view models using the latest available data

Comparison rule:

- `title_changed = latest_vod_name != vod_name_snapshot`

If a title later matches the snapshot again, clear the changed flag.

Failure rule:

- one favorite refresh failure must not fail the whole page
- the card falls back to persisted snapshot data
- delete and reopen actions still remain available

### Add and Remove Entry Points

Two entry points are required in the first release.

List page:

- add a right-click menu action for video items
- label toggles between `收藏` and `取消收藏`
- only video-capable rows should expose the action

Player window:

- add a favorites icon button in the detail-actions area, not the playback transport controls
- the button toggles between unfavorited and favorited icon states
- tooltip toggles between `收藏` and `取消收藏`

The player detail area is the correct placement because this action belongs to the current content item, not to transport control.

### UI Action Model for Player Favorites

This feature should not overload source-defined `PlaybackDetailAction` semantics.

Instead, add one player-managed favorite toggle control near the existing detail area:

- icon-only button
- hidden when there is no current playable item
- state derived from the local favorites store

This avoids conflating local app favorites with remote source actions such as Bilibili or plugin-defined `收藏歌单`.

### Favorites Page Delete Behavior

Delete actions should follow the same simple mental model as playback history:

- `删除选中` removes the selected favorite cards
- `清空当前结果` removes every favorite currently matching the active filter

Both actions should ask for confirmation before deleting.

After deletion:

- refresh the current page
- if the current page becomes empty and there is a previous page, step back one page

### Reopen Routing

Opening a favorite must reuse existing source-specific playback routing instead of replaying stale saved URLs.

`MainWindow` should gain a dedicated favorite-open path that mirrors `open_history_detail()` behavior, keyed by:

- `source_kind`
- `source_key`
- `vod_id`

Supported first-release sources should match the sources already routable from playback history:

- `browse`
- `spider_plugin`
- `telegram`
- `bilibili`
- `youtube`
- `emby`
- `jellyfin`
- `feiniu`
- `direct_parse`

The favorite page should emit one favorite-record signal, and `MainWindow` remains the only place that decides how to build the final `OpenPlayerRequest`.

### Main Window Integration

`MainWindow` should create and register a new trailing tab:

- key: `favorites`
- title: `我的收藏`

The favorites page should keep its own state and should not be folded into playback history or global search history.

Header integration should include:

- add a dedicated header icon button for `我的收藏`
- place it between `文件浏览` and `播放记录`
- clicking it should switch `MainWindow.nav_tabs` to the favorites page

This header button is in scope for the first release and should mirror the existing browse/history header-button behavior.

### Browse-Page Context Menu

`BrowsePage` currently opens items on double-click but does not expose a video-item context menu for favorites.

Add a context menu for file-list video rows with at least:

- `收藏` or `取消收藏`

Non-video rows should either hide the menu entry or suppress the context menu entirely for this feature.

The context menu action should use the currently selected `VodItem` plus the page's known source context to build the favorite record.

### Selection and Card Interaction

The favorites page needs batch delete, so card multi-selection is required.

Implementation decision:

- build a dedicated `FavoritesPage` card view
- reuse poster-grid visual styling where practical
- do not force this feature into `PosterGridPage` if that would compromise multi-selection or bulk delete behavior

The visual system should stay consistent with existing poster-grid cards rather than introducing a separate table-like management UI.

## Error Handling

- if saving a favorite fails, keep the current page usable and show a local error message
- if deleting fails, do not clear current selection silently
- if refresh lookup fails for one source, keep the cached card visible
- if reopening fails because the original source is no longer available, surface the existing `没有可播放的项目` style error

## Testing

Repository coverage should verify:

- save and upsert behavior
- duplicate key handling
- single delete
- batch delete
- filtered clear
- page loading and keyword filtering
- changed-title state persistence

Controller coverage should verify:

- current-page refresh compares only `vod_name`
- successful refresh updates `latest_vod_name` and `title_changed`
- failed refresh falls back to persisted values
- source routing metadata survives round-trip

Browse-page UI coverage should verify:

- video rows expose `收藏` when not favorited
- video rows expose `取消收藏` when favorited
- invoking the context action calls the favorites controller with the expected item

Player-window UI coverage should verify:

- the detail-area icon button reflects favorited state
- clicking the button toggles save and delete behavior
- the button stays out of the playback transport cluster

Favorites-page UI coverage should verify:

- cards render poster, title, source, and update hint
- changed-title cards use the subtle icon and border hint
- multi-selection enables `删除选中`
- `清空当前结果` passes the filtered records
- opening a card emits the expected favorite record

Main-window coverage should verify:

- the `我的收藏` tab is registered
- opening a favorite dispatches through the correct controller per `source_kind`
- unsupported or missing sources surface an error instead of crashing

## Open Questions Resolved

- title-change detection compares only the main video title `vod_name`
- favorites page uses poster cards rather than a table
- changed-title indication should be subtle, using icon and border treatment rather than strong text
- the player favorite toggle belongs in the detail area, not in the playback transport controls
- deletion is required in scope for both selected items and current filtered results
