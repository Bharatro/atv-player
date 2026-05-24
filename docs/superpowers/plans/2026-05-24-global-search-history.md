# Global Search Playback History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add playback history to global search as a separate `播放记录(n)` tab using the existing history table UI and detail-opening route.

**Architecture:** Add a thin global-search adapter around `HistoryController.load_page`, register a global-search-only history tab in `MainWindow`, and let `_GlobalSearchResult` carry either `PosterGridPage` or `HistoryPage`. Poster sources continue to render through `show_external_results`; history renders through a new history-page external result method.

**Tech Stack:** Python 3.12, PySide6 widgets, pytest/pytest-qt, existing `HistoryPage`, `HistoryController`, and `MainWindow` global search flow.

---

### Task 1: Add History External Result Rendering

**Files:**
- Modify: `src/atv_player/ui/history_page.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing UI tests**

Add tests that construct `MainWindow` with a fake history controller returning one matching `HistoryRecord`, start global search, assert a `播放记录(1)` tab appears, assert the row is rendered in `window.global_history_page`, double-click it, and assert `open_history_detail()` receives the record.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_main_window_ui.py -k "global_search_includes_playback_history_results or global_search_history_result_opens_existing_history_route" -q`

Expected: FAIL because `MainWindow` does not expose `global_history_page` and history is not a global search source.

- [ ] **Step 3: Implement history external result methods**

Add `HistoryPage.show_external_results(records, total, page=1, page_loader=None)` and `HistoryPage.clear_external_results()`. These methods should set `records`, `total_items`, `current_page`, update the table using the same rendering path as normal loads, and use `page_loader` for previous/next pagination when present.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "global_search_includes_playback_history_results or global_search_history_result_opens_existing_history_route" -q`

Expected: tests may still fail until Task 2 wires `MainWindow`.

### Task 2: Wire History Into Global Search

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add adapter and tab wiring**

Add a private `_HistoryGlobalSearchAdapter` with `search_items(keyword, page)` delegating to `history_controller.load_page(page=page, size=100, keyword=keyword)`. Create `self.global_history_page = HistoryPage(history_controller)`, connect its `open_detail_requested` to `open_history_detail`, and register `_TabDefinition("history:global", "播放记录", self.global_history_page, adapter, global_search_only=True)`.

- [ ] **Step 2: Render global history results**

Extend `_GlobalSearchResult.page` typing to support `HistoryPage`; update `_show_global_search_result()` to call `HistoryPage.show_external_results()` when result.page is a history page. Update `_clear_global_search()` to clear both poster external results and history external results.

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "global_search_includes_playback_history_results or global_search_history_result_opens_existing_history_route or clear_global_search_restores_original_tabs_and_titles" -q`

Expected: PASS.

### Task 3: Regression Verification

**Files:**
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_history_controller.py`

- [ ] **Step 1: Run global search and history regression tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "global_search or history_detail" tests/test_history_controller.py -q`

Expected: PASS.
