# Global Search Tabs Design

## Summary

Add a global search box to the main window header on the same row as `插件管理`. Submitting a keyword should search `电报影视`, `Emby`, `Jellyfin`, `飞牛影视`, and every enabled spider plugin that supports search in parallel.

The main window should enter a temporary global-search mode:

- only tabs with search results remain visible
- each visible tab title shows its result count, for example `电报影视(12)`
- clicking cards continues to use the existing per-source open behavior
- clearing the global search restores the original tab order, titles, and page behavior

This should be implemented as orchestration in `MainWindow`, not as a new search page.

## Goals

- Add a top-level search input to the main window header.
- Keep the search input on the same row as `插件管理`.
- Search all supported media sources in parallel from one keyword submission.
- Show only tabs with results while global-search mode is active.
- Show result counts in tab titles during global-search mode.
- Ignore stale results when a newer search starts before an older one completes.
- Restore the normal tab layout when the search is cleared.

## Non-Goals

- Adding global search to `豆瓣电影`, `网络直播`, `文件浏览`, or `播放记录`.
- Changing controller or API search signatures.
- Adding cross-source merged sorting or ranking.
- Adding global-search pagination beyond the first page.
- Creating a separate search-results window or page.
- Changing card click or playback behavior for any existing source.

## Scope

Primary implementation lives in:

- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/poster_grid_page.py`

Primary verification lives in:

- `tests/test_main_window_ui.py`
- `tests/test_poster_grid_page_ui.py`

## Design

### Search Sources

Global search should query these sources when available:

- `电报影视`
- `Emby`
- `Jellyfin`
- `飞牛影视`
- every enabled spider plugin whose controller supports search

Spider plugins that do not support search must be skipped without surfacing an error.

`豆瓣电影`, `网络直播`, `文件浏览`, and `播放记录` do not participate in global search and should not appear in global-search mode.

### Header Layout

The main window header should become a single horizontal row containing:

- a global keyword input
- a global `搜索` button
- a global `清空` button
- `插件管理`
- `直播源管理`
- `退出登录`

The search controls should be placed before the existing management buttons so search remains visually primary.

The global search box is a main-window concern. It is separate from any page-local search box already rendered inside `PosterGridPage`.

### Global Search Mode

`MainWindow` should own a dedicated global-search state rather than mutating each page ad hoc.

The state needs to track:

- whether global-search mode is active
- the current search keyword
- the current global search request id
- the original tab definitions and base tab titles
- the active result set for each searchable tab

Submitting a non-empty keyword enters global-search mode. Clearing the keyword exits global-search mode.

When global-search mode exits:

- all original tabs reappear in their original order
- all original tab titles are restored
- non-search tabs become visible again
- each page resumes its own normal state and loading behavior

### Tab Definitions and Restoration

The main window already creates tabs from a mix of fixed pages and dynamic spider plugin pages. That construction should be normalized into one internal tab-definition list containing:

- page widget
- base title
- whether the tab is eligible for global search
- the controller used for global search when eligible
- stable ordering position

The original tab-definition list is the source of truth for restoration.

During global-search mode, `MainWindow` should rebuild the visible tab list from the original definitions but include only tabs whose latest search returned at least one result.

Result tabs should keep their original relative order. They should not be sorted by result count.

### Search Execution

Global search should reuse the project’s existing threaded UI pattern:

- increment a request counter in `MainWindow`
- start one background worker per searchable source
- call `controller.search_items(keyword, 1)` in each worker
- emit completion signals back to the Qt main thread

Each completion signal should include:

- the global request id
- a stable source key
- the returned items
- the returned total count
- any failure state

The request id is mandatory so stale completions can be ignored.

### Result Handling

Each participating tab should show the first page of its own result set. The tab title count should use the number returned by the controller, not just the number of currently rendered cards.

If a source returns:

- `items` empty and `total` zero: the tab is hidden in global-search mode
- `items` non-empty: the tab is shown with title `名称(total)`
- an error: treat it as no result for this search round

If every source yields no results or failures, global-search mode still remains active but no result tabs are shown. The window should surface a clear empty-result status near the global search controls rather than switching back to normal mode automatically.

When the last worker for the active request completes:

- rebuild visible tabs from the collected results
- switch to the first visible result tab if one exists
- otherwise keep the tab widget empty of result tabs and show the empty-result status

### Controlled Result Injection

`PosterGridPage` should gain a narrow external-result API instead of having `MainWindow` mutate many internal fields directly.

The page should support:

- showing an externally supplied result set and total count
- showing an externally supplied empty-state message
- leaving that external-result state and returning to normal page behavior

This API should only update page presentation state:

- cards
- total count
- page label
- status text
- button enabled state as needed for the injected result

It should not invoke controller loading itself when the result comes from `MainWindow`.

This keeps `PosterGridPage` responsible for rendering while `MainWindow` remains responsible for cross-source orchestration.

### Interaction Rules

Global search behavior should follow these rules:

- pressing Enter in the global input triggers search
- clicking global `搜索` triggers search
- blank or whitespace-only keywords do nothing
- global `搜索` is disabled while a search round is in progress
- global `清空` stays enabled while global-search mode is active
- starting a new search before an older one finishes invalidates the older round

Page-local search controls can remain visible inside tabs that already support local search, but once global-search mode is active the displayed content should reflect the externally injected global results for that tab.

### Error Handling

A single source failure must not block the full search.

Required behavior:

- per-source failures are logged or ignored internally
- no modal error dialog is shown for partial failure
- unauthorized results from a single source should not force immediate logout from global search alone
- stale completions from previous search rounds are ignored completely

If a source later succeeds in a newer round, its tab should appear again normally.

### Testing Strategy

Add focused main-window tests for:

- header renders the global search input and buttons on the same row as `插件管理`
- global search fans out to all supported sources
- unsupported plugins are skipped
- only tabs with results remain visible in global-search mode
- visible tab titles include result counts
- visible tab order matches original tab order
- clearing global search restores original tabs and titles
- stale completions from an older request do not overwrite the latest request

Add focused page tests for:

- injected external results render cards and page totals correctly
- injected empty states render without reloading from the page controller
- leaving external-result mode restores normal page-managed behavior

## Implementation Order

1. Add failing `MainWindow` tests for header controls, result-only tabs, title counts, stale request handling, and clear-to-restore behavior.
2. Add failing `PosterGridPage` tests for externally injected result rendering and exit from external-result mode.
3. Extend `PosterGridPage` with the small controlled-result API.
4. Implement `MainWindow` global search state, threaded fan-out, result collection, and tab rebuilding.
5. Re-run the focused UI test suite and fix integration gaps before broader verification.
