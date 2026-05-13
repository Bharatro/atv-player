# Danmaku Search Trailing Year Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove trailing bracketed years from default danmaku search titles such as `黑夜告白 (2026)` -> `黑夜告白`.

**Architecture:** Keep the change local to `SpiderPluginController` so only default danmaku search title generation changes. Leave provider normalization and user-entered overrides untouched.

**Tech Stack:** Python, pytest

---

### Task 1: Add Regression Test

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing test**

```python
def test_controller_refresh_danmaku_sources_strips_trailing_year_from_default_media_title() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_refresh_danmaku_sources_strips_trailing_year_from_default_media_title -v`
Expected: FAIL because the query still contains `(2026)`.

### Task 2: Implement Minimal Controller Fix

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 3: Write minimal implementation**

```python
def _strip_trailing_title_year_suffix(title: str) -> str:
    ...
```

- [ ] **Step 4: Run targeted test to verify it passes**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_refresh_danmaku_sources_strips_trailing_year_from_default_media_title -v`
Expected: PASS

- [ ] **Step 5: Run a small related regression slice**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_refresh_danmaku_sources_uses_saved_search_title_for_same_series tests/test_spider_plugin_controller.py::test_controller_refresh_danmaku_sources_persists_search_title_only_after_successful_search tests/test_spider_plugin_controller.py::test_controller_refresh_danmaku_sources_strips_trailing_year_from_default_media_title -v`
Expected: PASS
