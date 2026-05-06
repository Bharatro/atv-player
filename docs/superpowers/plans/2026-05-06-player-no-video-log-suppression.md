# Player No-Video Log Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop appending the no-video informational log line in the player while preserving the fallback poster overlay and real playback failure logs.

**Architecture:** Keep the change inside `PlayerWindow`. Update the no-video regression test in `tests/test_player_window_ui.py` to assert the overlay still appears without the extra log line, then remove the `_append_log(...)` call from `PlayerWindow._handle_video_picture_state_changed("unavailable")`. Re-run the nearby playback-failure test to prove real `播放失败: ...` logging still works.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Remove the no-video informational log from `PlayerWindow`

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing regression test**

Change `test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable()` in `tests/test_player_window_ui.py` so it stops expecting the removed log line and instead asserts that the log stays empty:

```python
def test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable(qtbot) -> None:
    image = QImage(24, 36, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)

    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/poster.jpg"),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )
    window._handle_poster_load_finished(window._poster_request_id, image)

    window._handle_video_picture_state_changed("unavailable")

    assert window.video_poster_overlay.isHidden() is False
    assert window.log_view.toPlainText() == ""
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable -q`
Expected: FAIL because the current implementation still appends `当前媒体没有可用视频画面，已显示封面`.

- [ ] **Step 3: Write the minimal implementation**

Update `src/atv_player/ui/player_window.py` by removing only the no-video `_append_log(...)` call from `_handle_video_picture_state_changed()`:

```python
def _handle_video_picture_state_changed(self, state: str) -> None:
    self._video_picture_state = state
    if state == "visible":
        self._video_surface_ready = True
        self.video_poster_overlay.hide()
        return
    self._video_surface_ready = False
    pixmap = self.poster_label.pixmap()
    if pixmap is not None and not pixmap.isNull():
        self._show_video_poster_overlay(pixmap)
```

Do not change `_handle_playback_failed()`.

- [ ] **Step 4: Run the focused regression tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_again_after_playback_failure -q`
Expected: PASS, proving the no-video informational log is gone while the `播放失败: ...` log still remains.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: suppress no-video player info log"
```

### Task 2: Verify the player-window regression surface

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the nearby player-window overlay tests**

Run: `uv run pytest tests/test_player_window_ui.py -k "poster_overlay or visible_picture_signal or playback_failure or picture_becomes_unavailable" -q`
Expected: PASS for the no-video overlay and playback-failure coverage around the changed code path.

- [ ] **Step 2: Run the full player-window test file**

Run: `uv run pytest tests/test_player_window_ui.py -q`
Expected: PASS, or a clearly identified unrelated pre-existing failure with exact output captured before stopping.

## Spec Coverage Check

- Removing the no-video informational UI log is covered by Task 1.
- Preserving the poster overlay behavior for the no-video state is covered by the overlay assertion in Task 1 and the focused verification in Task 2.
- Preserving `播放失败: ...` logging is covered by the playback-failure regression re-run in Task 1.

## Placeholder Scan

- No `TODO`, `TBD`, or incomplete code placeholders remain.
- All commands, test names, and target files are concrete.
- The plan does not require any API, model, or `MpvWidget` changes beyond the approved scope.

## Type Consistency Check

- `PlayerWindow._handle_video_picture_state_changed()` remains the only method touched.
- `PlayerWindow._handle_playback_failed()` remains unchanged by design.
- The only removed text is `当前媒体没有可用视频画面，已显示封面`.
