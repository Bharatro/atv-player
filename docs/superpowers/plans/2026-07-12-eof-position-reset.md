# EOF Position Reset Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent mpv's EOF-time `time-pos=None/0` transition from overwriting the last meaningful playback position and causing normal endings to be misclassified as premature EOF.

**Architecture:** Keep the fix inside `PlayerWindow`'s existing per-item playback observation state. Treat zero as a valid initial observation, but once the same item has a positive observed position, ignore a later zero-position sample; item changes still reset the observation explicitly, and recent user seeks continue through the existing seek-recovery path.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

### Task 1: Reproduce EOF-time position reset

**Files:**
- Modify: `tests/test_player_window_ui.py:9581`

- [ ] **Step 1: Add a failing normal-ending regression test**

Add this test next to the existing premature EOF tests:

```python
def test_player_window_advances_when_mpv_resets_position_before_normal_eof(qtbot) -> None:
    class ResettingNearEndVideo(RecordingVideo):
        def __init__(self) -> None:
            super().__init__()
            self.position = 2679

        def duration_seconds(self) -> int:
            return 2681

        def position_seconds(self) -> int:
            return self.position

    video = ResettingNearEndVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    video.position = 0
    window._sync_progress_slider()
    window.video_widget.playback_finished.emit()

    assert window.current_index == 1
    assert video.load_calls == [("http://m/2.m3u8", 0)]
    assert "播放提前结束，正在恢复" not in window.log_view.toPlainText()
```

- [ ] **Step 2: Run the normal-ending test and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py::test_player_window_advances_when_mpv_resets_position_before_normal_eof -v
```

Expected: FAIL because the zero sample replaces `2679`, so the player reloads the current item instead of advancing to index 1.

- [ ] **Step 3: Add a failing premature-ending recovery regression test**

Add this test beside the normal-ending regression:

```python
def test_player_window_recovers_last_position_when_mpv_resets_before_premature_eof(qtbot) -> None:
    class ResettingPrematureEofVideo(RecordingVideo):
        def __init__(self) -> None:
            super().__init__()
            self.position = 1003

        def duration_seconds(self) -> int:
            return 2681

        def position_seconds(self) -> int:
            return self.position

    video = ResettingPrematureEofVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    video.position = 0
    window._sync_progress_slider()
    window.video_widget.playback_finished.emit()

    assert window.current_index == 0
    assert video.load_calls == [("http://m/1.m3u8", 1003)]
    assert "播放提前结束，正在恢复: 16:43 / 44:41" in window.log_view.toPlainText()
```

- [ ] **Step 4: Run both regression tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "mpv_resets_position_before_normal_eof or recovers_last_position_when_mpv_resets_before_premature_eof" -v
```

Expected: 2 failures. The normal EOF test remains on index 0, and the premature EOF test reloads at 0 instead of 1003.

### Task 2: Preserve the last meaningful playback position

**Files:**
- Modify: `src/atv_player/ui/player_window.py:8605`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Implement the minimal observation guard**

Change the position update in `_update_playback_observation()` to keep an existing positive position when a later sample is zero:

```python
        if (
            position >= 0
            and (effective_duration <= 0 or position <= effective_duration + 2)
            and (position > 0 or self._last_playback_position_seconds <= 0)
        ):
            self._last_playback_position_seconds = int(position)
```

Do not change `_reset_playback_observation()`: loading a different item must still clear the cached position to zero.

- [ ] **Step 2: Run both regression tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "mpv_resets_position_before_normal_eof or recovers_last_position_when_mpv_resets_before_premature_eof" -v
```

Expected: 2 passed.

- [ ] **Step 3: Run all premature EOF and duration observation tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "duration_shrinks or premature_eof or eof_is_near_observed_end or duration_is_unknown or mpv_resets_position" -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run seek-recovery regression tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_fails_after_progress_seek or seek_finished_unloads_media or ignores_playback_finished_immediately_after_progress_seek" -q
```

Expected: all selected tests pass, confirming that explicit seek handling still owns seek-related EOF events.

- [ ] **Step 5: Check formatting and diff quality**

Run:

```bash
git diff --check
git diff -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: `git diff --check` prints nothing; the diff contains only the two regression tests and the observation guard.

- [ ] **Step 6: Commit the fix**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: preserve playback position across EOF reset"
```

