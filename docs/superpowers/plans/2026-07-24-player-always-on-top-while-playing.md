# Playback-Time Always-on-Top Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the player window topmost only while media is playing, release native topmost while paused, and restore it on resume without clearing the user's selected mode.

**Architecture:** Keep `_always_on_top_enabled` as the in-memory preference reflected by the title-bar button and context-menu action, and add `_always_on_top_applied` for the last successfully applied native state. Derive the desired native state from `enabled and is_playing`, synchronize it after playback/lifecycle transitions, and retain the existing X11 maximized-window remap and post-show restoration path only when topmost should actually be applied.

**Tech Stack:** Python 3.11+, PySide6/Qt, X11 EWMH, pytest, pytest-qt, uv

---

## File map

- Modify `src/atv_player/ui/player_window.py`: state model, labels, playback/lifecycle synchronization, and X11 remap/show behavior.
- Modify `tests/test_player_window_ui.py`: UI semantics, pause/resume, lifecycle, error, window-state, and X11 regression tests.
- Reference `docs/superpowers/specs/2026-07-24-player-always-on-top-while-playing-design.md`: approved behavior; no config, settings, shortcut, help, or database changes.

### Task 1: Separate the preference from applied native state

**Files:**
- Modify: `tests/test_player_window_ui.py:9657-9840`
- Modify: `src/atv_player/ui/player_window.py:724-731`
- Modify: `src/atv_player/ui/player_window.py:1653-1728`
- Modify: `src/atv_player/ui/player_window.py:7569-7578`

- [ ] **Step 1: Write failing UI and paused-enable tests**

Rename the two existing title-bar tests and replace their assertions with:

```python
def test_player_window_playback_always_on_top_defaults_to_off(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window._is_always_on_top() is False
    assert window.always_on_top_button.isCheckable() is True
    assert window.always_on_top_button.isChecked() is False
    assert window.always_on_top_button.toolTip() == "播放时置顶"


def test_player_window_title_bar_button_toggles_playback_always_on_top(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.always_on_top_button.click()
    assert window._is_always_on_top() is True
    assert window.always_on_top_button.isChecked() is True
    assert window.always_on_top_button.toolTip() == "取消播放时置顶"

    window.always_on_top_button.click()
    assert window._is_always_on_top() is False
    assert window.always_on_top_button.isChecked() is False
    assert window.always_on_top_button.toolTip() == "播放时置顶"
```

Add:

```python
def test_player_window_enabling_playback_topmost_while_paused_defers_native_state(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    native_calls: list[bool] = []
    window.is_playing = False
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )

    window.always_on_top_button.click()

    assert native_calls == []
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False
    assert window.always_on_top_button.isChecked() is True
    assert window.always_on_top_button.toolTip() == "取消播放时置顶"
```

Rename the existing context-menu test to `test_player_window_context_menu_playback_topmost_syncs_with_title_bar`, look up `item.text() == "播放时置顶"`, and change the failure-restoration test's tooltip assertion to `"播放时置顶"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_always_on_top_defaults or title_bar_button_toggles_playback or enabling_playback_topmost_while_paused or context_menu_playback_topmost" -v
```

Expected: FAIL because labels still use `始终置顶`, paused enabling still invokes the native setter, and `_always_on_top_applied` does not exist.

- [ ] **Step 3: Implement the state split and derived-state synchronizer**

After `_always_on_top_enabled = False` in `__init__`, add:

```python
self._always_on_top_applied = False
```

Use `"取消播放时置顶" if enabled else "播放时置顶"` in `_sync_always_on_top_controls`, and create the context-menu action with `menu.addAction("播放时置顶")`.

Add after `_remap_maximized_xcb_window_for_always_on_top`:

```python
def _should_apply_always_on_top(self) -> bool:
    return self._always_on_top_enabled and self.is_playing

def _sync_native_always_on_top(self, *, failure_message: str) -> bool:
    desired = self._should_apply_always_on_top()
    if desired == self._always_on_top_applied:
        return True
    try:
        self._set_native_always_on_top(desired)
    except Exception as exc:
        logger.exception("PlayerWindow playback always-on-top synchronization failed")
        try:
            self._append_log(f"{failure_message}: {exc}")
        except Exception:
            pass
        return False
    self._always_on_top_applied = desired
    if desired:
        self._remap_maximized_xcb_window_for_always_on_top()
        if self.isVisible() and not self.isMinimized():
            self.raise_()
    return True
```

Replace `_set_always_on_top` with:

```python
def _set_always_on_top(
    self,
    enabled: bool,
    *,
    menu_action: QAction | None = None,
) -> None:
    requested = bool(enabled)
    previous = self._always_on_top_enabled
    if requested != previous:
        self._always_on_top_enabled = requested
        if not self._sync_native_always_on_top(failure_message="置顶切换失败"):
            self._always_on_top_enabled = previous
    self._sync_always_on_top_controls(menu_action=menu_action)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_always_on_top_defaults or title_bar_button_toggles_playback or enabling_playback_topmost_while_paused or context_menu_playback_topmost or always_on_top_failure_restores_actual_state" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "refactor: separate playback topmost preference"
```

### Task 2: Release on pause and restore on resume

**Files:**
- Modify: `tests/test_player_window_ui.py:21920-22025`
- Modify: `tests/test_player_window_ui.py:23152-23255`
- Modify: `src/atv_player/ui/player_window.py:9809-9818`

- [ ] **Step 1: Write failing pause/resume tests**

Add beside the playback-toggle tests:

```python
def test_player_window_playback_topmost_releases_on_pause_and_restores_on_resume(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    native_calls.clear()

    window.toggle_playback()

    assert window.is_playing is False
    assert native_calls == [False]
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False
    assert window.always_on_top_button.isChecked() is True

    window.toggle_playback()

    assert window.is_playing is True
    assert native_calls == [False, True]
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is True
```

Add:

```python
def test_player_window_disabling_playback_topmost_while_paused_blocks_restore(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    window.toggle_playback()
    native_calls.clear()

    window.always_on_top_button.click()
    window.toggle_playback()

    assert window.is_playing is True
    assert native_calls == []
    assert window._is_always_on_top() is False
    assert window._always_on_top_applied is False
```

Add the required window-state matrix:

```python
@pytest.mark.parametrize("state", ["normal", "maximized", "fullscreen"])
def test_player_window_playback_topmost_pause_resume_preserves_window_state(
    qtbot,
    monkeypatch,
    state: str,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.show()
    if state == "maximized":
        window.showMaximized()
    elif state == "fullscreen":
        window.showFullScreen()
    qtbot.wait(30)
    monkeypatch.setattr(window, "_set_native_always_on_top", lambda _enabled: None)
    monkeypatch.setattr(
        window,
        "_remap_maximized_xcb_window_for_always_on_top",
        lambda: None,
    )
    window._set_always_on_top(True)
    before = (
        window.isVisible(),
        window.isMinimized(),
        window.isMaximized(),
        window.isFullScreen(),
    )

    window.toggle_playback()
    window.toggle_playback()

    assert (
        window.isVisible(),
        window.isMinimized(),
        window.isMaximized(),
        window.isFullScreen(),
    ) == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_topmost_releases_on_pause or disabling_playback_topmost_while_paused or playback_topmost_pause_resume_preserves_window_state" -v
```

Expected: FAIL because `toggle_playback()` does not synchronize native topmost.

- [ ] **Step 3: Synchronize after the media operation succeeds**

Replace `toggle_playback` with:

```python
def toggle_playback(self) -> None:
    if self.is_playing:
        self.video.pause()
    else:
        self.video.resume()
    self.is_playing = not self.is_playing
    self._sync_native_always_on_top(failure_message="播放时置顶同步失败")
    self._set_last_player_paused(not self.is_playing)
    self._update_play_button_icon()
    self._refresh_window_title()
    self._sync_video_cursor_autohide()
```

- [ ] **Step 4: Write and run non-blocking error tests**

Add:

```python
@pytest.mark.parametrize("transition", ["pause", "resume"])
def test_player_window_playback_continues_when_topmost_sync_fails(
    qtbot,
    monkeypatch,
    transition: str,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    messages: list[str] = []
    monkeypatch.setattr(window, "_set_native_always_on_top", lambda _enabled: None)
    window._set_always_on_top(True)
    if transition == "resume":
        window.toggle_playback()

    def fail_native_state(_enabled: bool) -> None:
        raise RuntimeError("unsupported")

    monkeypatch.setattr(window, "_set_native_always_on_top", fail_native_state)
    monkeypatch.setattr(window, "_append_log", messages.append)

    window.toggle_playback()

    assert window.is_playing is (transition == "resume")
    assert window._is_always_on_top() is True
    assert window.always_on_top_button.isChecked() is True
    assert messages == ["播放时置顶同步失败: unsupported"]
```

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_topmost_releases_on_pause or disabling_playback_topmost_while_paused or playback_topmost_pause_resume_preserves_window_state or playback_continues_when_topmost_sync_fails or pausing_playback_restores_video_cursor or resuming_playback_starts_autohide or toggle_playback_persists" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: tie player topmost state to playback"
```

### Task 3: Synchronize session and main-window lifecycle transitions

**Files:**
- Modify: `tests/test_player_window_ui.py:10250-10315`
- Modify: `tests/test_player_window_ui.py:22448-22542`
- Modify: `tests/test_player_window_ui.py:23516-23533`
- Modify: `src/atv_player/ui/player_window.py:3194-3197`
- Modify: `src/atv_player/ui/player_window.py:5436-5448`
- Modify: `src/atv_player/ui/player_window.py:9737-9799`
- Modify: `src/atv_player/ui/player_window.py:9938-9945`

- [ ] **Step 1: Write failing lifecycle tests**

Add beside the return/resume tests:

```python
def test_player_window_playback_topmost_releases_on_return_and_restores_from_main(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(last_active_window="player"),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(make_player_session(start_index=0))
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    native_calls.clear()

    window._return_to_main()

    assert native_calls == [False]
    assert window.is_playing is False
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False

    window.resume_from_main()

    assert native_calls == [False, True]
    assert window.is_playing is True
    assert window._always_on_top_applied is True
```

Add beside the paused-session test:

```python
def test_player_window_opening_paused_session_releases_playback_topmost(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    native_calls.clear()

    window.open_session(make_player_session(start_index=0), start_paused=True)

    assert window.is_playing is False
    assert native_calls == [False]
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False
```

Add beside the resume-from-main test:

```python
def test_player_window_failed_resume_from_main_does_not_restore_topmost(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(last_active_window="player"),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(make_player_session(start_index=0))
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    window._return_to_main()
    native_calls.clear()
    monkeypatch.setattr(
        window,
        "_play_item_at_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("load failed")),
    )

    window.resume_from_main()

    assert window.is_playing is False
    assert native_calls == []
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False
```

In both existing terminal premature-EOF tests, add `monkeypatch` to the signature and insert this setup immediately before the first playback-finished emission that triggers the terminal failure:

```python
native_calls: list[bool] = []
monkeypatch.setattr(
    window,
    "_set_native_always_on_top",
    lambda enabled: native_calls.append(enabled),
)
window._set_always_on_top(True)
native_calls.clear()
```

After the terminal failure, assert:

```python
assert window.is_playing is False
assert native_calls == [False]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_topmost_releases_on_return or opening_paused_session_releases_playback_topmost or failed_resume_from_main_does_not_restore_topmost or stops_after_repeated_premature_eof or stops_when_premature_eof_reload_fails" -v
```

Expected: FAIL because direct `is_playing` assignments do not synchronize native topmost.

- [ ] **Step 3: Synchronize every final playback-state assignment**

Add the following call immediately after `self.is_playing = not start_paused` in `open_session`, after `self.is_playing = True` in `_replay_current_item`, after `self.is_playing = False` in `_return_to_main`, and after `self.is_playing = False` in `_stop_after_premature_finish_failure`:

```python
self._sync_native_always_on_top(failure_message="播放时置顶同步失败")
```

In `resume_from_main`, add that same call after the `try`/`except` and before `_update_play_button_icon()`, so the final success/failure value of `is_playing` controls the native state.

- [ ] **Step 4: Run lifecycle regressions**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playback_topmost_releases_on_return or opening_paused_session_releases_playback_topmost or failed_resume_from_main_does_not_restore_topmost or stops_after_repeated_premature_eof or stops_when_premature_eof_reload_fails or return_to_main or resume_from_main or opening_session_paused" -v
```

Expected: PASS, including existing shutdown-profile, metadata, danmaku, progress, title, and paused-state tests selected by those expressions.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: synchronize playback topmost lifecycle"
```

### Task 4: Preserve X11 maximized remapping, minimize state, and activation

**Files:**
- Modify: `tests/test_player_window_ui.py:9715-9781`
- Modify: `tests/test_player_window_ui.py:9882-9958`
- Modify: `src/atv_player/ui/player_window.py:1671-1680`
- Modify: `src/atv_player/ui/player_window.py:9947-9968`

- [ ] **Step 1: Write failing X11/show-event tests**

Add beside the existing XCB tests:

```python
def test_player_window_does_not_reapply_playback_topmost_after_show_while_paused(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.show()
    qtbot.wait(30)
    native_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    window._set_always_on_top(True)
    window.toggle_playback()
    native_calls.clear()

    window.hide()
    window.show()
    qtbot.wait(30)

    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is False
    assert native_calls == []
```

Add the maximized-resume seam test:

```python
def test_player_window_xcb_maximized_resume_reuses_topmost_remap(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: False)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    monkeypatch.setattr(QApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(window, "hide", lambda: calls.append(("hide", None)))
    monkeypatch.setattr(
        window,
        "showMaximized",
        lambda: calls.append(("maximized", window._is_always_on_top())),
    )
    monkeypatch.setattr(window, "raise_", lambda: calls.append(("raise", None)))
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: calls.append(("native", enabled)),
    )
    window._set_always_on_top(True)
    calls.clear()

    window.toggle_playback()
    window.toggle_playback()

    assert calls == [
        ("native", False),
        ("native", True),
        ("hide", None),
        ("maximized", True),
        ("raise", None),
    ]
```

Add minimized-from-maximized protection:

```python
def test_player_window_xcb_topmost_does_not_remap_minimized_maximized_window(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    calls: list[str] = []
    monkeypatch.setattr(QApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: True)
    monkeypatch.setattr(window, "hide", lambda: calls.append("hide"))
    monkeypatch.setattr(window, "showMaximized", lambda: calls.append("showMaximized"))
    monkeypatch.setattr(window, "_set_native_always_on_top", lambda _enabled: None)

    window._set_always_on_top(True)

    assert calls == []
```

Add a Qt-level native-surface regression test:

```python
def test_player_window_xcb_maximized_remap_preserves_native_surface_ids(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.showMaximized()
    qtbot.waitUntil(window.isMaximized)
    player_window_id = int(window.winId())
    video_window_id = int(window.video_widget.winId())
    monkeypatch.setattr(QApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(window, "_set_native_always_on_top", lambda _enabled: None)

    window._set_always_on_top(True)
    qtbot.wait(30)

    assert window.isVisible() is True
    assert window.isMaximized() is True
    assert int(window.winId()) == player_window_id
    assert int(window.video_widget.winId()) == video_window_id
```

Add the post-show failure/activation test:

```python
def test_player_window_restores_activation_after_failed_topmost_reapply(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    calls: list[str] = []
    messages: list[str] = []
    window._always_on_top_enabled = True
    window._always_on_top_applied = True
    window.is_playing = True
    window._restore_activation_after_always_on_top_remap = True
    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: False)

    def fail_native_state(_enabled: bool) -> None:
        raise RuntimeError("unsupported")

    monkeypatch.setattr(window, "_set_native_always_on_top", fail_native_state)
    monkeypatch.setattr(window, "raise_", lambda: calls.append("raise"))
    monkeypatch.setattr(window, "activateWindow", lambda: calls.append("activate"))
    monkeypatch.setattr(window, "_append_log", messages.append)

    window._reapply_always_on_top_after_show()

    assert calls == ["raise", "activate"]
    assert messages == ["恢复置顶失败: unsupported"]
    assert window._always_on_top_applied is False
```

- [ ] **Step 2: Run the tests to verify failures**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "does_not_reapply_playback_topmost_after_show_while_paused or xcb_maximized_resume_reuses_topmost_remap or xcb_topmost_does_not_remap_minimized or xcb_maximized_remap_preserves_native_surface_ids or activation_after_failed_topmost" -v
```

Expected: paused show, minimized remap, and failure-path activation tests FAIL against the current implementation.

- [ ] **Step 3: Guard remapping and update post-show derived-state behavior**

Add `or self.isMinimized()` to the early-return conditions in `_remap_maximized_xcb_window_for_always_on_top`.

Replace `_reapply_always_on_top_after_show` and `showEvent` with:

```python
def _reapply_always_on_top_after_show(self) -> None:
    should_apply = self._should_apply_always_on_top()
    if not should_apply or not self.isVisible():
        if not should_apply:
            self._restore_activation_after_always_on_top_remap = False
        return
    restore_activation = self._restore_activation_after_always_on_top_remap
    self._restore_activation_after_always_on_top_remap = False
    self._always_on_top_applied = False
    try:
        self._set_native_always_on_top(True)
    except Exception as exc:
        logger.exception("PlayerWindow always-on-top restore failed")
        try:
            self._append_log(f"恢复置顶失败: {exc}")
        except Exception:
            pass
    else:
        self._always_on_top_applied = True
    finally:
        if restore_activation and not self.isMinimized():
            self.raise_()
            self.activateWindow()

def showEvent(self, event) -> None:
    super().showEvent(event)
    if self._should_apply_always_on_top():
        QTimer.singleShot(0, self._reapply_always_on_top_after_show)
```

The `finally` restores focus independently of EWMH success after an intentional hide/remap. Clearing applied state before the forced call permits a later show/resume retry if restoration failed.

- [ ] **Step 4: Run all focused topmost tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top or topmost" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: preserve x11 playback topmost state"
```

### Task 5: Final regression verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py`
- Verify: `docs/superpowers/specs/2026-07-24-player-always-on-top-while-playing-design.md`

- [ ] **Step 1: Run the complete player-window UI suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -q
```

Expected: PASS with no failures or errors.

- [ ] **Step 2: Compile the production module**

Run:

```bash
uv run python -m py_compile src/atv_player/ui/player_window.py
```

Expected: exit status 0 with no output.

- [ ] **Step 3: Check labels, persistence scope, and diff hygiene**

Run:

```bash
rg -n "player_always_on_top|播放时置顶|始终置顶" src tests docs/superpowers/specs/2026-07-24-player-always-on-top-while-playing-design.md
git diff --check
git diff -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected: no `player_always_on_top` config field, no remaining player-control label `始终置顶`, no whitespace errors, and a diff limited to the approved in-memory preference/applied split, playback/lifecycle synchronization, X11 behavior, and tests.

- [ ] **Step 4: Commit only if verification required a correction**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "test: cover playback topmost regressions"
```

If Steps 1-3 required no correction, do not create an empty commit.
