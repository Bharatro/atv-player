# Player Playlist Title Tabs Cursor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the playback window's `剧集标题` / `原始文件名` tab bar show a pointing-hand cursor without changing any playlist item behavior.

**Architecture:** Reuse the existing `PlayerWindow` pattern of assigning `Qt.CursorShape.PointingHandCursor` directly during widget construction. Lock the behavior with a focused UI test in `tests/test_player_window_ui.py` so future player-window refactors keep the cursor semantics on this tab bar.

**Tech Stack:** Python, PySide6, pytest-qt

---

### Task 1: Add a regression test for the playlist title tabs cursor

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing test in `tests/test_player_window_ui.py`**

```python
def test_player_window_playlist_title_tabs_use_pointing_hand_cursor(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.playlist_title_tabs.cursor().shape() == Qt.CursorShape.PointingHandCursor
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "playlist_title_tabs_use_pointing_hand_cursor" -v`

Expected: FAIL because `playlist_title_tabs` still uses the default arrow cursor.

- [ ] **Step 3: Write the minimal implementation in `src/atv_player/ui/player_window.py`**

```python
        self.playlist_title_tabs = QTabBar()
        self.playlist_title_tabs.addTab("剧集标题")
        self.playlist_title_tabs.addTab("原始文件名")
        self.playlist_title_tabs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_title_tabs.setHidden(True)
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k "playlist_title_tabs_use_pointing_hand_cursor" -v`

Expected: PASS

- [ ] **Step 5: Run broader verification for player window cursor behavior**

Run: `uv run pytest tests/test_player_window_ui.py -k "pointing_cursor or playlist_title_tabs_use_pointing_hand_cursor" -v`

Expected: PASS, including the existing playback-controls pointing-cursor test.

- [ ] **Step 6: Commit the test and implementation**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: use pointing cursor for player title tabs"
```
