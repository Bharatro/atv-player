# Danmaku Hydrate-Before-Playback Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent hydrate-only completion from attempting to attach danmaku while the current media is still being prepared for playback.

**Architecture:** Keep the existing hydrate-only media-control refresh path and gate only its danmaku configuration call. A pending playback prepare suppresses danmaku configuration only when its index matches the current playlist index; normal hydrate-only refreshes and stale prepare state retain immediate configuration.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Structure

- Modify `tests/test_player_window_ui.py`: add a focused hydrate-only regression test for matching and unrelated pending prepare state while retaining the existing no-prepare coverage.
- Modify `src/atv_player/ui/player_window.py`: gate the hydrate-only danmaku configuration call using the existing `_pending_playback_prepare` state.

### Task 1: Defer hydrate-only danmaku during matching media preparation

**Files:**
- Modify: `tests/test_player_window_ui.py:20680`
- Modify: `src/atv_player/ui/player_window.py:4923-4931`

- [ ] **Step 1: Write the failing regression test**

Add this focused regression test immediately after the existing hydrate-only media-control test:

```python
@pytest.mark.parametrize(
    ("pending_prepare_index", "expected_configure_calls"),
    [
        (0, []),
        (1, ["configure-danmaku"]),
    ],
)
def test_player_window_hydrate_only_loader_defers_danmaku_during_matching_playback_prepare(
    qtbot,
    monkeypatch,
    pending_prepare_index: int,
    expected_configure_calls: list[str],
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.session = make_player_session(start_index=0)
    window.current_index = 0
    window._playback_loader_request_id = 7
    window._pending_playback_loader = player_window_module._PendingPlaybackLoader(
        index=0,
        previous_index=0,
        start_position_seconds=0,
        pause=False,
        hydrate_only=True,
    )
    window._pending_playback_prepare = player_window_module._PendingPlaybackPrepare(
        index=pending_prepare_index,
        previous_index=0,
        start_position_seconds=0,
        pause=False,
        source_url="http://m/1.m3u8",
    )
    configure_calls: list[str] = []
    monkeypatch.setattr(
        window,
        "_configure_danmaku_for_current_item",
        lambda: configure_calls.append("configure-danmaku"),
    )

    window._handle_playback_loader_succeeded(window._playback_loader_request_id, None)

    assert configure_calls == expected_configure_calls
```

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_player_window_ui.py::test_player_window_hydrate_only_loader_defers_danmaku_during_matching_playback_prepare -q
```

Expected: the matching-index parameter case fails because it still records `configure-danmaku`; the unrelated-index case passes.

- [ ] **Step 3: Implement the minimal gate**

In the hydrate-only branch, replace the unconditional danmaku configuration with:

```python
pending_prepare = self._pending_playback_prepare
if pending_prepare is None or pending_prepare.index != self.current_index:
    self._configure_danmaku_for_current_item()
```

Keep cache restoration and all subtitle, audio, quality, and detail refresh calls unchanged.

- [ ] **Step 4: Run the regression test and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_player_window_ui.py -k "hydrate_only_loader_refreshes_media_controls or hydrate_only_loader_defers_danmaku_during_matching_playback_prepare" -q
```

Expected: `3 passed` (one existing no-prepare case and two new parameter cases).

- [ ] **Step 5: Run related danmaku lifecycle tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_player_window_ui.py -k "hydrate_only_loader or reconfigures_danmaku_after_matching_video_file_loaded or ignores_stale_file_loaded_danmaku_item or clears_pending_file_loaded_danmaku_item_when_video_load_fails" -q
```

Expected: all selected tests pass with no failures.

- [ ] **Step 6: Run the full player window UI test file**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_player_window_ui.py -q
```

Expected: all tests pass with no failures.

- [ ] **Step 7: Check formatting and diff integrity**

Run:

```bash
.venv/bin/ruff check src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git diff --check
```

Expected: Ruff reports no errors and `git diff --check` exits successfully without output.

- [ ] **Step 8: Commit the fix**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix(danmaku): defer hydrate until playback starts"
```
