# Favorite Detail Heart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the playback favorite button next to the "影片详情" heading, render it as a borderless gray/red heart, and clarify browse context menu wording.

**Architecture:** Keep existing favorite callbacks and state flow. Change only `PlayerWindow` layout/state presentation and `BrowsePage` context menu text, with focused UI tests.

**Tech Stack:** Python, PySide6, pytest-qt.

---

### Task 1: Write Failing UI Tests

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_browse_page_ui.py`

- [x] **Step 1: Update player favorite button test**

Change `test_player_window_renders_detail_favorite_icon_button` so it asserts:

```python
assert window._metadata_heading_row.indexOf(window.metadata_heading) >= 0
assert window._metadata_heading_row.indexOf(window.favorite_button) == window._metadata_heading_row.indexOf(window.metadata_heading) + 1
assert window.favorite_button.toolTip() == "取消收藏"
assert "border: none" in window.favorite_button.styleSheet()
assert window.favorite_button.property("favorite_active") is True
```

- [x] **Step 2: Update browse context menu test**

Extend `test_browse_page_video_context_menu_shows_favorite_toggle` to assert both inactive and active labels:

```python
page.set_favorite_handlers(
    is_favorited=lambda item: False,
    toggle_favorite=lambda item: toggles.append(item.vod_id),
)
assert [action.text() for action in page._build_item_context_menu(0).actions()] == ["加入收藏"]

page.set_favorite_handlers(
    is_favorited=lambda item: item.vod_id == "detail-1",
    toggle_favorite=lambda item: toggles.append(item.vod_id),
)
assert [action.text() for action in page._build_item_context_menu(0).actions()] == ["取消收藏"]
```

- [x] **Step 3: Run tests to verify RED**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_renders_detail_favorite_icon_button tests/test_browse_page_ui.py::test_browse_page_video_context_menu_shows_favorite_toggle -q
```

Expected: fail because the favorite button is still in `favorite_action_widget`, tooltip is still `收藏` for inactive state, and browse menu still says `收藏`.

### Task 2: Implement Favorite Button Presentation

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/ui/browse_page.py`

- [x] **Step 1: Move favorite button into heading row**

Remove the standalone `favorite_action_widget` layout and create `favorite_button` before adding widgets to `_metadata_heading_row`. Add it immediately after `metadata_heading` with a small spacing.

- [x] **Step 2: Make the button borderless and tint by state**

In `_refresh_favorite_button`, set:

```python
tooltip = "取消收藏" if active else "加入收藏"
self.favorite_button.setToolTip(tooltip)
self.favorite_button.setAccessibleName(tooltip)
self.favorite_button.setProperty("favorite_active", active)
```

Use `favorite-filled.svg` tinted red for active, `favorite.svg` tinted secondary gray for inactive. Apply a transparent borderless stylesheet in theme application.

- [x] **Step 3: Update browse menu label**

Change inactive label from `收藏` to `加入收藏` in `_build_item_context_menu`.

- [x] **Step 4: Run focused GREEN tests**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_renders_detail_favorite_icon_button tests/test_browse_page_ui.py::test_browse_page_video_context_menu_shows_favorite_toggle -q
```

Expected: pass.

- [x] **Step 5: Run related regression tests**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -q -k "favorite_icon_button or detail_action"
uv run pytest tests/test_browse_page_ui.py -q -k "favorite_toggle or context_menu"
```

Expected: pass.
