# Following TMDB Related Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add asynchronous TMDB related recommendations to the following detail page, with left-click global search and right-click resource search / add-following actions.

**Architecture:** Extend `TMDBDiscoveryService` with a single-media recommendation method, expose it through `FollowingController`, then render it from `FollowingDetailPage` as an async section below episodes. `MainWindow` wires the detail-page search signal into the existing global search entry point.

**Tech Stack:** Python, PySide6, pytest, pytest-qt, existing `DiscoveryItem` / `DiscoveryResult` models.

---

## File Structure

- Modify `src/atv_player/metadata/discovery.py`: add a `related()` service method with cache and exclusion filtering.
- Modify `tests/test_metadata_discovery_service.py`: cover single-media related recommendations and cache behavior.
- Modify `src/atv_player/controllers/following_controller.py`: add TMDB identity resolution and `load_related_recommendations()`.
- Modify `tests/test_following_controller.py`: cover identity resolution and service delegation.
- Modify `src/atv_player/ui/following_detail_page.py`: add recommendation section, card widget, async loading, left/right click interactions.
- Modify `tests/test_following_detail_page_ui.py`: cover async load, left-click signal, right-click menu actions.
- Modify `src/atv_player/ui/main_window.py`: connect detail-page related search signal to existing global search.
- Modify `tests/test_main_window_ui.py`: cover signal-driven global search.

## Tasks

### Task 1: Discovery Service Related Recommendations

- [ ] Add failing tests in `tests/test_metadata_discovery_service.py`.
- [ ] Implement `TMDBDiscoveryService.related()`.
- [ ] Run `uv run pytest tests/test_metadata_discovery_service.py -k "related" -v`.

### Task 2: Following Controller Related Recommendations

- [ ] Add failing tests in `tests/test_following_controller.py`.
- [ ] Implement `FollowingController.load_related_recommendations()`.
- [ ] Run `uv run pytest tests/test_following_controller.py -k "related_recommendations" -v`.

### Task 3: Following Detail Page Recommendation UI

- [ ] Add failing tests in `tests/test_following_detail_page_ui.py`.
- [ ] Implement async recommendation section and card interactions.
- [ ] Run `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "related_recommend" -v`.

### Task 4: Main Window Wiring

- [ ] Add failing test in `tests/test_main_window_ui.py`.
- [ ] Connect `related_global_search_requested` to global search.
- [ ] Run `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "following_detail_related_global_search" -v`.

### Task 5: Focused Regression

- [ ] Run focused pytest set over touched tests.
- [ ] Run `uv run ruff check` over touched source and tests.
