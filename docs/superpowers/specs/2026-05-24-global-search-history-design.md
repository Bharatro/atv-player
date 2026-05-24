# Global Search Playback History Design

## Goal

Global search should include playback history as its own result source. When a keyword matches watched items, global search shows a `播放记录(n)` tab. Opening a history result should reuse the existing playback-history detail routing.

## Design

Playback history stays in the existing `HistoryPage` table UI because history records have fields that poster cards do not show well: episode, progress, timestamp, and source. `MainWindow` will create a separate global-search history page so the normal trailing `播放记录` tab keeps its own filters and loaded state.

The global-search flow will use a small adapter with `search_items(keyword, page)` that delegates to `HistoryController.load_page(page=page, size=100, keyword=keyword)`. `MainWindow` will register this adapter as a global-search-only tab definition and render history results through a history-page method instead of `PosterGridPage.show_external_results`.

Clearing global search will clear the global-search-only history page results and restore the normal tab list. Double-clicking a global history row will emit the existing `open_detail_requested` signal, so `MainWindow.open_history_detail()` remains the only history routing path.

## Testing

Tests cover:

- global search shows `播放记录(n)` when history matches;
- the history adapter passes keyword and page to `HistoryController.load_page`;
- double-clicking a global history result opens the existing history detail route;
- clearing global search removes the global-only history tab.
