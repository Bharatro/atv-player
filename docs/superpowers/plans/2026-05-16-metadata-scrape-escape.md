# Metadata Scrape Escape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Esc` close the player `刮削` dialog without returning to the main window or stopping playback.

**Architecture:** Keep the fix inside `PlayerWindow`'s existing escape-dispatch path instead of adding a new dialog-local shortcut. Add one focused regression test first, then extend the existing dialog-closing helpers so the scrape dialog participates in the same flow as help, danmaku source, and danmaku settings dialogs.

**Tech Stack:** Python, PySide6, pytest-qt, pytest

---

### Task 1: Add the regression test for scrape-dialog escape handling

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing test**

Add this test next to the existing `Esc` dialog-behavior tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_escape_closes_metadata_scrape_dialog_without_returning_to_main(qtbot) -> None:
    config = AppConfig(last_active_window="player")
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(window)
    pauses = {"count": 0}
    emitted = {"count": 0}

    class FakeVideo:
        def pause(self) -> None:
            pauses["count"] += 1

        def position_seconds(self) -> int:
            return 0

        def duration_seconds(self) -> int:
            return 120

    session = make_player_session()
    session.metadata_scrape_service = object()
    window.video = FakeVideo()
    window.open_session(session)
    window.closed_to_main.connect(lambda: emitted.__setitem__("count", emitted["count"] + 1))
    window.show()
    window.activateWindow()
    window.setFocus()

    window._open_metadata_scrape_dialog()
    qtbot.waitUntil(lambda: len(visible_metadata_scrape_dialogs()) == 1)
    dialog = visible_metadata_scrape_dialogs()[0]

    window.escape_shortcut.activated.emit()

    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert window.isVisible() is True
    assert pauses["count"] == 0
    assert emitted["count"] == 0
    assert config.last_active_window == "player"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "escape_closes_metadata_scrape_dialog" -v
```

Expected: one failing test because the dialog stays open or the player returns to main, proving the regression is real.

- [ ] **Step 3: Commit the red test**

Run:

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover metadata scrape escape handling"
```

Expected: a commit containing only the new failing regression test.

### Task 2: Route scrape-dialog escape through the existing player escape helper

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the minimal implementation**

In `src/atv_player/ui/player_window.py`, add a close helper and wire it into the same call sites as the other auxiliary dialogs:

```python
    def _close_metadata_scrape_dialog(self) -> None:
        dialog = self._metadata_scrape_dialog
        if dialog is None or not dialog.isVisible():
            return
        dialog.close()

    def _dismiss_escape_dialog(self) -> bool:
        dialog = self._danmaku_settings_dialog
        if dialog is not None and dialog.isVisible():
            self._close_danmaku_settings_dialog()
            return True
        dialog = self._danmaku_source_dialog
        if dialog is not None and dialog.isVisible():
            self._close_danmaku_source_dialog()
            return True
        dialog = self._metadata_scrape_dialog
        if dialog is not None and dialog.isVisible():
            self._close_metadata_scrape_dialog()
            return True
        if self.help_dialog is not None and self.help_dialog.isVisible():
            self._close_help_dialog()
            return True
        return False

    def _return_to_main(self) -> None:
        self._close_help_dialog()
        self._close_danmaku_source_dialog()
        self._close_danmaku_settings_dialog()
        self._close_metadata_scrape_dialog()
        self._close_video_context_menu()
```

Keep the rest of `_return_to_main()` unchanged.

- [ ] **Step 2: Run the focused tests to verify green**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "escape_closes_metadata_scrape_dialog or escape_closes_danmaku_source_dialog or escape_closes_danmaku_settings_dialog or escape_shortcut_returns_to_main_when_not_fullscreen" -v
```

Expected: all selected tests pass, showing the new dialog behavior works and existing `Esc` behavior still holds.

- [ ] **Step 3: Run the broader player-window shortcut slice**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "metadata_scrape_dialog or keyboard_shortcuts_control_playback_navigation_and_view or escape_" -v
```

Expected: the broader shortcut and scrape-dialog slice passes without new regressions.

- [ ] **Step 4: Commit the implementation**

Run:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: close metadata scrape dialog on escape"
```

Expected: a commit containing the player-window fix and the passing regression coverage.
