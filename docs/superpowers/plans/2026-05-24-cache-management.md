# Cache Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cache inspection and clearing controls to Advanced Settings.

**Architecture:** Add a focused `atv_player.cache_management` module for file-system scanning and deletion. Extend `AdvancedSettingsDialog` with a `缓存管理` tab that displays snapshots from that module and refreshes after actions.

**Tech Stack:** Python, pathlib, shutil, PySide6, pytest, pytest-qt.

---

### Task 1: Cache Management Core

**Files:**
- Create: `src/atv_player/cache_management.py`
- Create: `tests/test_cache_management.py`

- [ ] Write failing tests for `build_cache_summary()` using a temporary cache root containing known category files and unknown root entries.
- [ ] Run `uv run pytest tests/test_cache_management.py -q` and verify the tests fail because the module does not exist.
- [ ] Implement dataclasses `CacheCategory`, `CacheCategoryStats`, and `CacheSummary`.
- [ ] Implement `build_cache_summary(cache_root: Path | None = None) -> CacheSummary`.
- [ ] Implement `clear_cache_category(category_id: str, cache_root: Path | None = None) -> None`.
- [ ] Implement `clear_all_cache(cache_root: Path | None = None) -> None`.
- [ ] Implement `clear_cache_older_than(days: int, cache_root: Path | None = None) -> CacheCleanupResult`.
- [ ] Run `uv run pytest tests/test_cache_management.py -q` and verify it passes.

### Task 2: Advanced Settings UI

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] Write failing UI tests for the `缓存管理` tab, total labels, category table rows, refresh, and category clear action.
- [ ] Run the new `tests/test_main_window_ui.py` tests and verify they fail because the tab does not exist.
- [ ] Add the cache tab widgets and wire them to the core cache management module.
- [ ] Add open-directory actions using `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`.
- [ ] Add confirmation dialogs for clearing one category and clearing all cache.
- [ ] Add an age spinbox and a `清理旧缓存` action that deletes files older than the selected day count.
- [ ] Refresh the summary after clear actions.
- [ ] Run the focused UI tests and verify they pass.

### Task 3: Verification

**Files:**
- Existing tests only.

- [ ] Run `uv run pytest tests/test_cache_management.py tests/test_main_window_ui.py -q`.
- [ ] Run `uv run ruff check src/atv_player/cache_management.py src/atv_player/ui/advanced_settings_dialog.py tests/test_cache_management.py tests/test_main_window_ui.py`.
- [ ] Inspect `git diff --stat` and `git diff --check`.
