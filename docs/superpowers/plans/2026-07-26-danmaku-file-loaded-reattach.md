# Danmaku File-Loaded Reattach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reattach the current episode's danmaku after mpv confirms the replacement media has reached `file-loaded`.

**Architecture:** Keep the existing immediate player configuration path intact, but associate each real `MpvWidget` media load with its `PlayItem` through a dedicated pending reference. Consume that reference on `file-loaded`, verify object identity against the current playlist item, and re-run only danmaku configuration unless the existing deferred post-load path will already do so.

**Tech Stack:** Python 3.12, PySide6, python-mpv, pytest, pytest-qt

---

## File Structure

### Existing files to modify

- `src/atv_player/ui/player_window.py`
  Responsibility: record which `PlayItem` owns the pending mpv load, discard failed or stale loads, and reconfigure danmaku after the matching `file-loaded` event.

- `tests/test_player_window_ui.py`
  Responsibility: cover matching, stale, and failed media-load behavior without requiring a live mpv process.

### Design constraints

- Keep `_should_defer_post_load_player_configuration()` returning `False`.
- Keep the first immediate `_configure_danmaku_for_current_item()` call.
- Use object identity (`is`) for stale-result protection, matching existing async handlers.
- Track only real `video_widget` loads; fake video objects keep their synchronous behavior.
- Clear the pending reference before invoking danmaku configuration so one event is consumed once.

---

### Task 1: Add File-Loaded Danmaku Regression Coverage

**Files:**
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the matching file-loaded regression test**

Add the following near the existing post-load configuration tests:

```python
def test_player_window_reconfigures_danmaku_after_matching_video_file_loaded(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), save_config=lambda: None)
    qtbot.addWidget(window)
    window.session = make_player_session(start_index=0)
    window.current_index = 0
    current_item = window.session.playlist[0]

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        window.video_widget,
        "load",
        lambda url, pause=False, start_seconds=0, **_kwargs: calls.append(("load", url)),
    )
    monkeypatch.setattr(window.video_widget, "set_speed", lambda value: None)
    monkeypatch.setattr(window.video_widget, "set_volume", lambda value: None)
    monkeypatch.setattr(window.video_widget, "set_muted", lambda value: None)
    monkeypatch.setattr(
        window,
        "_configure_danmaku_for_current_item",
        lambda: calls.append(("danmaku", window.session.playlist[window.current_index])),
    )

    window._start_current_item_playback()

    assert calls == [("load", current_item.url), ("danmaku", current_item)]
    assert window._pending_file_loaded_danmaku_item is current_item

    window._handle_video_file_loaded()

    assert calls == [
        ("load", current_item.url),
        ("danmaku", current_item),
        ("danmaku", current_item),
    ]
    assert window._pending_file_loaded_danmaku_item is None
```

- [ ] **Step 2: Write the stale file-loaded regression test**

```python
def test_player_window_ignores_stale_file_loaded_danmaku_item(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), save_config=lambda: None)
    qtbot.addWidget(window)
    window.session = make_player_session(start_index=0)
    window.current_index = 0
    original_item = window.session.playlist[0]

    configure_items: list[PlayItem] = []
    monkeypatch.setattr(window.video_widget, "load", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window.video_widget, "set_speed", lambda value: None)
    monkeypatch.setattr(window.video_widget, "set_volume", lambda value: None)
    monkeypatch.setattr(window.video_widget, "set_muted", lambda value: None)
    monkeypatch.setattr(
        window,
        "_configure_danmaku_for_current_item",
        lambda: configure_items.append(window.session.playlist[window.current_index]),
    )

    window._start_current_item_playback()
    window.current_index = 1
    window._handle_video_file_loaded()

    assert configure_items == [original_item]
    assert window._pending_file_loaded_danmaku_item is None
```

- [ ] **Step 3: Write the failed media-load cleanup regression test**

```python
def test_player_window_clears_pending_file_loaded_danmaku_item_when_video_load_fails(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), save_config=lambda: None)
    qtbot.addWidget(window)
    window.session = make_player_session(start_index=0)
    window.current_index = 0

    def fail_load(*_args, **_kwargs) -> None:
        raise RuntimeError("load failed")

    monkeypatch.setattr(window, "_video_load", fail_load)

    with pytest.raises(RuntimeError, match="load failed"):
        window._start_current_item_playback()

    assert window._pending_file_loaded_danmaku_item is None
```

- [ ] **Step 4: Run the three tests and verify RED**

Run:

```bash
uv run --cache-dir /tmp/atv-player-uv-cache pytest \
  tests/test_player_window_ui.py::test_player_window_reconfigures_danmaku_after_matching_video_file_loaded \
  tests/test_player_window_ui.py::test_player_window_ignores_stale_file_loaded_danmaku_item \
  tests/test_player_window_ui.py::test_player_window_clears_pending_file_loaded_danmaku_item_when_video_load_fails \
  -v
```

Expected: all three tests fail because `PlayerWindow` does not define `_pending_file_loaded_danmaku_item` and does not reconfigure danmaku from `file-loaded`.

---

### Task 2: Reattach Matching Danmaku After File-Loaded

**Files:**
- Modify: `src/atv_player/ui/player_window.py:929-933`
- Modify: `src/atv_player/ui/player_window.py:3218-3222`
- Modify: `src/atv_player/ui/player_window.py:3695-3744`
- Modify: `src/atv_player/ui/player_window.py:3791-3811`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Initialize and reset the pending item reference**

Initialize it beside the existing post-load state:

```python
self._pending_post_load_item: PlayItem | None = None
self._pending_post_load_pause = False
self._pending_file_loaded_danmaku_item: PlayItem | None = None
```

Reset it at the start of `open_session()` so callbacks from the previous session cannot be consumed:

```python
def open_session(self, session, start_paused: bool = False) -> None:
    self._pending_file_loaded_danmaku_item = None
    self._reset_auto_switched_failure_sources()
```

- [ ] **Step 2: Associate real mpv loads with the current item and clear failures**

Immediately before `_video_load()`:

```python
if self.video is self.video_widget:
    self._pending_file_loaded_danmaku_item = current_item
```

Extend the existing exception handler without masking a newer request:

```python
except Exception:
    if self._pending_file_loaded_danmaku_item is current_item:
        self._pending_file_loaded_danmaku_item = None
    if defer_post_load_configuration:
        self._pending_post_load_item = None
        self._pending_post_load_pause = False
    raise
```

- [ ] **Step 3: Consume the matching item on file-loaded**

At the start of `_handle_video_file_loaded()`, capture and clear the pending danmaku item. If the generic deferred configuration is not responsible for the same item, configure danmaku only when the session and object identity still match:

```python
def _handle_video_file_loaded(self) -> None:
    self._schedule_window_single_shot(1500, self._start_pending_ytdlp_metadata_hydration_if_current)
    pending_danmaku_item = self._pending_file_loaded_danmaku_item
    self._pending_file_loaded_danmaku_item = None
    pending_item = self._pending_post_load_item
    if (
        pending_danmaku_item is not None
        and pending_item is not pending_danmaku_item
        and self.session is not None
        and 0 <= self.current_index < len(self.session.playlist)
        and self.session.playlist[self.current_index] is pending_danmaku_item
    ):
        self._configure_danmaku_for_current_item()
    if pending_item is None:
        return
```

Keep the remainder of the existing deferred `apply_if_still_current()` implementation unchanged. When `pending_item is pending_danmaku_item`, `_apply_post_load_player_configuration()` remains the single caller that configures danmaku.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the three-test command from Task 1.

Expected: `3 passed`.

- [ ] **Step 5: Run adjacent behavior tests**

Run:

```bash
uv run --cache-dir /tmp/atv-player-uv-cache pytest tests/test_player_window_ui.py \
  -k 'enables_danmaku_by_default_when_current_item_has_danmaku or uses_saved_off_danmaku_preference_on_open_session or hydrate_only_loader_refreshes_media_controls or applies_post_load_configuration_immediately_on_windows or deferred_file_loaded_callback_does_not_run_after_window_is_deleted' \
  -q
```

Expected: `5 passed` with the remaining tests deselected.

- [ ] **Step 6: Commit the fix**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix(danmaku): reattach after media file loads"
```

---

### Task 3: Full Verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the complete PlayerWindow UI suite**

```bash
uv run --cache-dir /tmp/atv-player-uv-cache pytest tests/test_player_window_ui.py -q
```

Expected: all PlayerWindow UI tests pass with zero failures.

- [ ] **Step 2: Run static syntax validation**

```bash
uv run --cache-dir /tmp/atv-player-uv-cache python -m py_compile \
  src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: exit code 0 with no output.

- [ ] **Step 3: Inspect the final diff**

```bash
git diff HEAD^ --check
git diff HEAD^ -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: no whitespace errors; the diff contains only the pending item lifecycle, matching `file-loaded` reconfiguration, and the three regression tests.
