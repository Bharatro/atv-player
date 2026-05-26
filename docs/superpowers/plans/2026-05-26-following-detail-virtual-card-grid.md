# Following Detail Virtual Card Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the following-detail episode area visually identical to the existing full cards while replacing the per-episode QWidget grid with a virtualized card grid that remains responsive for 1200-episode seasons.

**Architecture:** `FollowingDetailPage` keeps the existing three-pane shell and continues delegating episode rendering to `FollowingEpisodeBrowser`. Inside the browser, the right pane moves to a single `QListView`-based virtual card grid where `EpisodeListModel` remains the data source and `EpisodeItemDelegate` becomes responsible for painting the full-card layout for 1/2/3-column densities. The legacy `QScrollArea + QGridLayout + FollowingEpisodeCard` rendering path is removed from the active episode pane so column changes and thumbnail refreshes become model/view redraws instead of mass widget churn.

**Tech Stack:** Python, PySide6 model/view + delegate painting, pytest, pytest-qt, existing `EpisodeThumbnailStore` image caching.

---

## File Structure

- Modify: `src/atv_player/ui/following_episode_browser.py`
  - Keep season grouping, episode model, thumbnail cache, and season detail panel.
  - Rework the episode list pane into a virtual card grid using `QListView` layout settings and delegate-driven full-card painting.
  - Map `following_episode_grid_columns` to card density metrics instead of real widget columns.
- Modify: `tests/test_following_episode_browser.py`
  - Replace widget-grid expectations with virtual-grid expectations.
  - Add large-season regression coverage proving the browser no longer materializes per-episode card widgets.
- Modify: `tests/test_following_detail_page_ui.py`
  - Keep page-level interaction coverage, but assert the detail page uses the browser-owned virtual card pane and still opens episode previews.

## Task 1: Lock the Browser to a Virtual Card Grid

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Test: `tests/test_following_episode_browser.py`

- [ ] **Step 1: Write the failing browser tests for the virtual card pane**

```python
def test_following_episode_browser_uses_virtual_list_instead_of_card_grid(qtbot) -> None:
    ...
```

- [ ] **Step 2: Run the targeted browser tests to verify failure**

Run: `uv run pytest tests/test_following_episode_browser.py -k "virtual_list or large_season" -q`

Expected: FAIL because the browser still hides `episode_list`, shows `episode_scroll`, and populates `episode_cards`.

- [ ] **Step 3: Update column-switch expectations to describe density mode instead of widget relayout**

```python
def test_following_episode_browser_switches_virtual_list_display_mode(qtbot) -> None:
    ...
```

- [ ] **Step 4: Run the display-mode test to verify failure**

Run: `uv run pytest tests/test_following_episode_browser.py -k "switches_virtual_list_display_mode" -q`

Expected: FAIL because `set_grid_columns()` still relayouts widgets instead of changing model display mode.

## Task 2: Replace the Widget Grid with a Delegate-Drawn Card Grid

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Test: `tests/test_following_episode_browser.py`

- [ ] **Step 1: Add explicit density mapping for the existing full-card visual**
- [ ] **Step 2: Reconfigure `FollowingEpisodeBrowser` to use only the list view for the active pane**
- [ ] **Step 3: Remove widget-grid rebuilds from the season-apply and column-switch paths**
- [ ] **Step 4: Add a helper that recalculates the virtual grid dimensions from the pane width**
- [ ] **Step 5: Rework `EpisodeItemDelegate` painting so all three display modes still draw full cards**
- [ ] **Step 6: Stop refreshing real card widgets when thumbnails arrive**
- [ ] **Step 7: Run the focused browser tests to verify green**

Run: `uv run pytest tests/test_following_episode_browser.py -k "virtual_list or large_season or switches_virtual_list_display_mode" -q`

Expected: PASS with `3 passed`.

- [ ] **Step 8: Run the full browser test file**

Run: `uv run pytest tests/test_following_episode_browser.py -q`

Expected: PASS with all browser tests green.

## Task 3: Prove the Detail Page Still Uses the Browser Correctly

**Files:**
- Modify: `tests/test_following_detail_page_ui.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Add a page-level regression proving the detail page still uses the browser-owned episode pane**
- [ ] **Step 2: Keep the existing preview interaction check against the browser index activation**
- [ ] **Step 3: Run the new detail-page regression to verify it fails before the browser change is merged**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "virtual_card_grid" -q`

Expected: FAIL if the browser still exposes the widget-grid pane.

- [ ] **Step 4: Run the full detail-page and following-page UI coverage after the browser change**

Run: `uv run pytest tests/test_following_detail_page_ui.py tests/test_following_page_ui.py tests/test_following_controller.py -q`

Expected: PASS with all page-level interactions intact.

## Task 4: Final Verification

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Modify: `tests/test_following_episode_browser.py`
- Modify: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Run the focused browser and detail-page suites together**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -q`

Expected: PASS with both suites green.

- [ ] **Step 2: Run the broader following regressions**

Run: `uv run pytest tests/test_following_page_ui.py tests/test_following_controller.py -q`

Expected: PASS with broader following flows green.
