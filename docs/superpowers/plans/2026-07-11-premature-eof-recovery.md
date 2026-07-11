# Premature EOF Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent cloud-drive proxy streams from skipping to the next episode when mpv reports EOF far before the last trusted media position reaches the real ending.

**Architecture:** `PlayerWindow` will cache per-item playback observations: maximum valid duration, last valid position, and premature-EOF recovery count. Both timer-driven ending detection and mpv EOF handling will use this stable state; one premature EOF reloads the current item at the last position, while a repeated premature EOF stops on the current item instead of looping or advancing.

**Tech Stack:** Python 3.12, PySide6, python-mpv/libmpv, pytest, pytest-qt

---

## File Structure

- Modify `src/atv_player/ui/player_window.py`: own per-item observation state, stable-duration selection, premature EOF classification, one-shot recovery, and transition logging.
- Modify `tests/test_player_window_ui.py`: cover duration shrinkage, early EOF recovery, repeated early EOF, real endings, and unknown-duration compatibility.

### Task 1: Track stable duration and prevent timer-driven false auto-advance

**Files:**
- Modify: `tests/test_player_window_ui.py:9520-9730`
- Modify: `src/atv_player/ui/player_window.py:788-800`
- Modify: `src/atv_player/ui/player_window.py:3546-3565`
- Modify: `src/atv_player/ui/player_window.py:9190-9215`

- [ ] **Step 1: Add a failing duration-shrink regression test**

Add this test near the existing progress slider and auto-advance tests:

```python
def test_player_window_uses_max_observed_duration_after_proxy_duration_shrinks(qtbot) -> None:
    class ShrinkingDurationVideo(RecordingVideo):
        def __init__(self) -> None:
            super().__init__()
            self.duration = 2681
            self.position = 1000

        def duration_seconds(self) -> int:
            return self.duration

        def position_seconds(self) -> int:
            return self.position

    video = ShrinkingDurationVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))

    window._sync_progress_slider()
    video.duration = 1100
    video.position = 1003
    window._sync_progress_slider()

    assert window.current_index == 0
    assert window.progress.maximum() == 2681
    assert window.duration_label.text() == "44:41"
```

- [ ] **Step 2: Run the duration-shrink test and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py::test_player_window_uses_max_observed_duration_after_proxy_duration_shrinks -v
```

Expected: FAIL because the second sync replaces the slider maximum with `1100` and may trigger the current ending logic.

- [ ] **Step 3: Add observation state and reset it only for a newly loaded item**

Add these fields beside `_auto_advance_locked` in `PlayerWindow.__init__`:

```python
self._observed_media_duration_seconds = 0
self._last_playback_position_seconds = 0
self._premature_finish_recovery_attempts = 0
```

Add this helper near `_current_media_duration_seconds()`:

```python
def _reset_playback_observation(self) -> None:
    self._observed_media_duration_seconds = 0
    self._last_playback_position_seconds = 0
    self._premature_finish_recovery_attempts = 0

def _update_playback_observation(self, *, position: int, duration: int) -> int:
    if duration > 0:
        self._observed_media_duration_seconds = max(
            self._observed_media_duration_seconds,
            int(duration),
        )
    effective_duration = self._observed_media_duration_seconds
    if position >= 0 and (
        effective_duration <= 0 or position <= effective_duration + 2
    ):
        self._last_playback_position_seconds = int(position)
    return effective_duration if effective_duration > 0 else max(0, int(duration))
```

Call `_reset_playback_observation()` in `_load_current_item()` immediately after the session guard and before resetting recent-seek state. Do not call it from `_start_current_item_playback()`, because premature EOF recovery reloads the same item through that method and must preserve the trusted duration and retry count.

- [ ] **Step 4: Make progress syncing use the maximum observed duration**

After reading `duration` and `position` in `_sync_progress_slider()`, calculate:

```python
effective_duration = self._update_playback_observation(
    position=int(position),
    duration=int(duration),
)
```

Replace every duration use in the auto-advance condition and slider update with `effective_duration`. Before timer-driven `play_next()`, add:

```python
logger.info(
    "PlayerWindow auto advance reason=ending index=%s position=%s duration=%s ending=%s",
    self.current_index,
    position,
    effective_duration,
    self.ending_spin.value(),
)
```

- [ ] **Step 5: Run the duration-shrink test and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py::test_player_window_uses_max_observed_duration_after_proxy_duration_shrinks -v
```

Expected: PASS.

- [ ] **Step 6: Run existing progress and ending tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "syncs_progress_slider_and_seeks_from_it or ignores_playback_finished_immediately_after_progress_seek or advances_after_progress_seek_near_end" -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit stable-duration tracking**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: keep stable duration for proxy playback"
```

### Task 2: Recover once from premature EOF and never skip on repetition

**Files:**
- Modify: `tests/test_player_window_ui.py:9540-9750`
- Modify: `src/atv_player/ui/player_window.py:9595-9650`

- [ ] **Step 1: Add failing premature EOF behavior tests**

Add these tests near the existing playback-finished tests:

```python
def test_player_window_reloads_current_item_after_premature_eof(qtbot) -> None:
    class PrematureEofVideo(RecordingVideo):
        def duration_seconds(self) -> int:
            return 2681

        def position_seconds(self) -> int:
            return 1003

    video = PrematureEofVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    window.video_widget.playback_finished.emit()

    assert window.current_index == 0
    assert video.load_calls == [("http://m/1.m3u8", 1003)]
    assert "播放提前结束，正在恢复" in window.log_view.toPlainText()


def test_player_window_stops_after_repeated_premature_eof(qtbot) -> None:
    class PrematureEofVideo(RecordingVideo):
        def duration_seconds(self) -> int:
            return 2681

        def position_seconds(self) -> int:
            return 1003

    controller = RecordingPlayerController()
    video = PrematureEofVideo()
    window = PlayerWindow(controller)
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    window.video_widget.playback_finished.emit()
    video.load_calls.clear()
    window.video_widget.playback_finished.emit()

    assert window.current_index == 0
    assert video.load_calls == []
    assert window.is_playing is False
    assert "播放提前结束，恢复失败" in window.log_view.toPlainText()


def test_player_window_advances_when_eof_is_near_observed_end(qtbot) -> None:
    class NearEndVideo(RecordingVideo):
        def duration_seconds(self) -> int:
            return 2681

        def position_seconds(self) -> int:
            return 2679

    video = NearEndVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    window.video_widget.playback_finished.emit()

    assert window.current_index == 1
    assert video.load_calls == [("http://m/2.m3u8", 0)]


def test_player_window_keeps_existing_eof_behavior_when_duration_is_unknown(qtbot) -> None:
    class UnknownDurationVideo(RecordingVideo):
        def duration_seconds(self) -> int:
            return 0

        def position_seconds(self) -> int:
            return 1003

    video = UnknownDurationVideo()
    window = PlayerWindow(RecordingPlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    video.load_calls.clear()
    window._sync_progress_slider()

    window.video_widget.playback_finished.emit()

    assert window.current_index == 1
```

- [ ] **Step 2: Run the four EOF tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "reloads_current_item_after_premature_eof or stops_after_repeated_premature_eof or advances_when_eof_is_near_observed_end or keeps_existing_eof_behavior_when_duration_is_unknown" -v
```

Expected: the two premature-EOF tests fail because `_handle_playback_finished()` currently advances unconditionally; the compatibility tests document behavior that must remain green after implementation.

- [ ] **Step 3: Add premature EOF classification**

Add this helper before `_handle_playback_finished()`:

```python
def _playback_finished_is_premature(self) -> bool:
    duration = self._observed_media_duration_seconds
    if duration <= 0:
        return False
    position = self._last_playback_position_seconds
    ending_seconds = self.ending_spin.value() if hasattr(self, "ending_spin") else 0
    end_margin = max(2, int(ending_seconds or 0))
    return position + end_margin < duration
```

- [ ] **Step 4: Add one-shot current-item recovery**

Add this helper next to `_recover_current_item_after_seek()`:

```python
def _recover_current_item_after_premature_finish(self) -> None:
    position = max(0, int(self._last_playback_position_seconds))
    duration = max(0, int(self._observed_media_duration_seconds))
    if self._premature_finish_recovery_attempts > 0:
        message = (
            "播放提前结束，恢复失败: "
            f"index={self.current_index} position={position} duration={duration}"
        )
        logger.warning("PlayerWindow %s", message)
        self._append_log(message)
        self.is_playing = False
        self._set_last_player_paused(True)
        self._update_play_button_icon()
        self._refresh_window_title()
        self._stop_current_playback()
        return
    self._premature_finish_recovery_attempts += 1
    logger.warning(
        "PlayerWindow premature EOF recovery index=%s position=%s duration=%s",
        self.current_index,
        position,
        duration,
    )
    self._append_log(
        f"播放提前结束，正在恢复: {self._format_time(position)} / {self._format_time(duration)}"
    )
    try:
        self._start_current_item_playback(
            start_position_seconds=position,
            pause=not self.is_playing,
        )
    except Exception as exc:
        self._append_log(f"播放提前结束，恢复失败: {exc}")
```

- [ ] **Step 5: Route playback-finished events through the classifier**

In `_handle_playback_finished()`, keep the existing recent-seek branches first. Immediately afterward add:

```python
if self._playback_finished_is_premature():
    self._recover_current_item_after_premature_finish()
    return
logger.info(
    "PlayerWindow auto advance reason=eof-near-end index=%s position=%s duration=%s",
    self.current_index,
    self._last_playback_position_seconds,
    self._observed_media_duration_seconds,
)
```

The unknown-duration case reaches the log and existing next-item behavior because the classifier returns `False`.

- [ ] **Step 6: Run the four EOF tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "reloads_current_item_after_premature_eof or stops_after_repeated_premature_eof or advances_when_eof_is_near_observed_end or keeps_existing_eof_behavior_when_duration_is_unknown" -v
```

Expected: `4 passed`.

- [ ] **Step 7: Run existing seek recovery tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_fails_after_progress_seek or seek_finished_unloads_media or progress_seek_fails_after_unloading_media or advances_after_progress_seek_near_end" -v
```

Expected: all selected tests pass, proving premature EOF handling composes with the earlier seek recovery.

- [ ] **Step 8: Commit premature EOF recovery**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: recover cloud drive playback from premature EOF"
```

### Task 3: Final verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py`
- Verify: `tests/test_mpv_widget.py`

- [ ] **Step 1: Run the focused regression set**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "duration_shrinks or premature_eof or eof_is_near_observed_end or duration_is_unknown or playback_fails_after_progress_seek or seek_finished_unloads_media" -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the complete player window and mpv widget suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py tests/test_mpv_widget.py -q
```

Expected: no failures beyond the three already documented baseline failures:

```text
test_player_window_preloads_ytdlp_passthrough_before_initial_load
test_player_window_renders_route_selector_and_switches_active_group
test_player_window_async_loader_with_prefilled_url_starts_immediately_and_does_not_restart_on_hydration
```

- [ ] **Step 3: Run static and syntax checks**

Run:

```bash
uv run ruff check src/atv_player/ui/player_window.py tests/test_player_window_ui.py --ignore E501,I001,F401,F811 --output-format concise
uv run python -m py_compile src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git diff --check
```

Expected: all commands exit successfully.

- [ ] **Step 4: Inspect commits and worktree state**

Run:

```bash
git log -3 --oneline
git status --short
```

Expected: the two implementation commits are present and the worktree is clean.
