# 115 Seek Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep 115 proxy playback running after a progress-bar seek triggers mpv `-16`, a seek-command exception, or an EOF-style media unload.

**Architecture:** Keep the recovery policy in `PlayerWindow`, where recent user-seek state and playlist state already live. Reuse the existing `start_position_seconds` load path so mpv applies the target during media loading, and intercept only playback failures that occur in the short recent-seek window; ordinary failures continue through the existing auto-switch and failed-startup handling.

**Tech Stack:** Python 3.12, PySide6, python-mpv/libmpv, pytest, pytest-qt

---

## File Structure

- Modify `src/atv_player/ui/player_window.py`: detect recent-seek playback failures, recover the current item at the requested position, and remove obsolete polling-based resume seek code.
- Modify `tests/test_player_window_ui.py`: cover mpv `playback_failed`, seek-command failure, EOF-style unload, unchanged ordinary failure handling, and removal of polling recovery.

### Task 1: Recover recent absolute seeks through load-time start position

**Files:**
- Modify: `tests/test_player_window_ui.py:9607-9705`
- Modify: `src/atv_player/ui/player_window.py:4143-4153`
- Modify: `src/atv_player/ui/player_window.py:9174-9187`
- Modify: `src/atv_player/ui/player_window.py:9597-9645`

- [ ] **Step 1: Add the failing `playback_failed (-16)` regression test**

Add this test beside the existing progress-seek recovery tests:

```python
def test_player_window_recovers_current_item_when_playback_fails_after_progress_seek(
    qtbot,
    monkeypatch,
) -> None:
    class SeekableRecordingVideo(RecordingVideo):
        def __init__(self) -> None:
            super().__init__()
            self.seek_calls: list[int] = []

        def seek(self, seconds: int) -> None:
            self.seek_calls.append(seconds)

        def duration_seconds(self) -> int:
            return 120

    controller = RecordingPlayerController()
    video = SeekableRecordingVideo()
    window = PlayerWindow(controller)
    qtbot.addWidget(window)
    window.video = video
    window.open_session(make_player_session(start_index=0))
    auto_switch_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_try_auto_switch_source_after_failure",
        lambda: auto_switch_calls.append(True) or False,
    )

    video.load_calls.clear()
    window.progress.setMaximum(120)
    window.progress.setValue(75)

    window._seek_from_slider()
    window._handle_playback_failed("播放失败: 没有可播放的音视频流 (-16)")

    assert window.current_index == 0
    assert window.playlist.currentRow() == 0
    assert video.seek_calls == [75]
    assert video.load_calls == [("http://m/1.m3u8", 75)]
    assert auto_switch_calls == []
    assert "没有可播放的音视频流 (-16)" in window.log_view.toPlainText()
    assert "正在恢复播放进度: 01:15" in window.log_view.toPlainText()
```

- [ ] **Step 2: Change the two existing unload recovery tests to require load-time seeking**

In `test_player_window_reloads_current_item_when_seek_finished_unloads_media`, remove the `_attempt_resume_seek` monkeypatch and its `try/finally`, then require:

```python
assert video.load_calls == [("http://m/1.m3u8", 75)]
```

In `test_player_window_reloads_current_item_when_progress_seek_fails_after_unloading_media`, make the same change and require:

```python
assert video.load_calls == [("http://m/1.m3u8", 75)]
assert "跳转失败" in window.log_view.toPlainText()
assert "正在恢复播放进度: 01:15" in window.log_view.toPlainText()
```

- [ ] **Step 3: Run the three recovery tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "recovers_current_item_when_playback_fails_after_progress_seek or reloads_current_item_when_seek_finished_unloads_media or reloads_current_item_when_progress_seek_fails_after_unloading_media" -v
```

Expected: all three tests fail because recovery currently reloads at `0`, calls `_attempt_resume_seek`, and does not intercept `playback_failed` before ordinary failure handling.

- [ ] **Step 4: Add recent-seek failure detection before ordinary playback failure handling**

Change `_handle_playback_failed` and add the focused helper immediately below it:

```python
def _handle_playback_failed(self, message: str) -> None:
    if self._should_recover_recent_seek_failure():
        self._append_log(message)
        self._recover_current_item_after_seek()
        return
    if self._try_auto_switch_source_after_failure():
        return
    self._show_failed_startup_state(message)
    self._append_log(message)
    self._video_surface_ready = False
    pixmap = self.video_poster_overlay.pixmap()
    if pixmap is not None and not pixmap.isNull():
        self._show_video_poster_overlay(pixmap)

def _should_recover_recent_seek_failure(self) -> bool:
    target_seconds = self._recent_user_seek_target_seconds
    if target_seconds is None or time.monotonic() >= self._ignore_playback_finished_until:
        return False
    try:
        duration = int(self.video.duration_seconds() or 0)
    except Exception:
        duration = 0
    if duration <= 0:
        return True
    ending_seconds = self.ending_spin.value() if hasattr(self, "ending_spin") else 0
    end_margin = max(2, int(ending_seconds or 0))
    return int(target_seconds) + end_margin < duration
```

This check must run before `_try_auto_switch_source_after_failure()` so a transient seek failure reloads the current 115 item instead of changing source.

- [ ] **Step 5: Replace polling recovery with a load-time start position**

In `_seek_to_position`, preserve the original error in the log and call the renamed recovery method:

```python
def _seek_to_position(self, seconds: int) -> None:
    try:
        self.video.seek(seconds)
        self._mark_recent_user_seek(seconds)
    except Exception as exc:
        self._recent_user_seek_target_seconds = seconds
        if self._current_media_duration_seconds() <= 0:
            self._append_log(f"跳转失败: {exc}")
            self._recover_current_item_after_seek()
            return
        self._append_log(f"跳转失败: {exc}")
```

Update `_handle_playback_finished` to call `_recover_current_item_after_seek()` for its existing `"reload"` action. Rename `_reload_current_item_after_seek_finished` and replace its body with:

```python
def _recover_current_item_after_seek(self) -> None:
    if self.session is None or not (0 <= self.current_index < len(self.session.playlist)):
        return
    start_position_seconds = max(0, int(self._recent_user_seek_target_seconds or 0))
    self._ignore_playback_finished_until = 0.0
    self._recent_user_seek_target_seconds = None
    self._append_log(f"正在恢复播放进度: {self._format_time(start_position_seconds)}")
    try:
        self._start_current_item_playback(
            start_position_seconds=start_position_seconds,
            pause=not self.is_playing,
        )
    except Exception as exc:
        self._append_log(f"播放恢复失败: {exc}")
```

Clearing the recent-seek state before loading makes a failure from the recovery load follow the ordinary error path instead of recursively reloading.

- [ ] **Step 6: Run the three recovery tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "recovers_current_item_when_playback_fails_after_progress_seek or reloads_current_item_when_seek_finished_unloads_media or reloads_current_item_when_progress_seek_fails_after_unloading_media" -v
```

Expected: `3 passed`.

- [ ] **Step 7: Run adjacent behavior tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "does_not_auto_switch_when_playback_has_already_started or shows_video_poster_overlay_again_after_playback_failure or appends_mpv_failure_messages or ignores_playback_finished_immediately_after_progress_seek or advances_after_progress_seek_near_end or passes_resume_offset_into_video_load" -v
```

Expected: all selected tests pass, proving non-seek failures, normal seek suppression, near-end advancement, and ordinary resume behavior remain unchanged.

- [ ] **Step 8: Commit the behavioral fix**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: recover 115 playback after seek failure"
```

### Task 2: Remove obsolete polling recovery and verify the player suite

**Files:**
- Modify: `src/atv_player/ui/player_window.py:5040-5059`
- Modify: `tests/test_player_window_ui.py:7970-8022`

- [ ] **Step 1: Confirm the polling helper has no production callers**

Run:

```bash
rg -n "_attempt_resume_seek" src tests
```

Expected: only the helper definition and its two dedicated tests remain.

- [ ] **Step 2: Remove obsolete code and tests**

Delete `PlayerWindow._attempt_resume_seek()` from `src/atv_player/ui/player_window.py`.

Delete these tests from `tests/test_player_window_ui.py` because the fixed-duration polling behavior no longer exists:

```python
test_player_window_retries_resume_seek_when_player_is_not_ready
test_player_window_reports_failure_after_seek_retries_are_exhausted
```

- [ ] **Step 3: Verify no stale references remain**

Run:

```bash
rg -n "_attempt_resume_seek|媒体尚未进入可跳转状态" src tests
```

Expected: no matches.

- [ ] **Step 4: Run the complete player window and mpv widget tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py tests/test_mpv_widget.py -q
```

Expected: all tests pass with no errors or warnings caused by the seek recovery change.

- [ ] **Step 5: Run formatting and static checks used by the project**

Run:

```bash
uv run ruff check src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: `All checks passed!`.

- [ ] **Step 6: Commit the cleanup**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "test: remove obsolete seek polling coverage"
```

### Task 3: Final verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py`
- Verify: `tests/test_mpv_widget.py`

- [ ] **Step 1: Inspect the final diff**

Run:

```bash
git diff HEAD~2 --check
git diff HEAD~2 -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: no whitespace errors; the diff is limited to recent-seek failure recovery, direct load-time start, diagnostics, and obsolete polling removal.

- [ ] **Step 2: Run the focused regression tests once more**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_fails_after_progress_seek or seek_finished_unloads_media or progress_seek_fails_after_unloading_media or ignores_playback_finished_immediately_after_progress_seek or advances_after_progress_seek_near_end" -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Confirm the worktree is clean**

Run:

```bash
git status --short
```

Expected: no output.
