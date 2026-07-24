# X11 Real-Maximized Playback Topmost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve real X11 maximized state during playback-topmost remapping and reapply topmost whenever the user switches between normal and maximized window states.

**Architecture:** Force Qt to observe a real maximized-state transition while the window is hidden by clearing its cached `WindowMaximized` bit before `showMaximized()`. Route show events and window-state changes through one coalesced zero-delay reapply scheduler so the X11 window manager receives `_NET_WM_STATE_ABOVE` after state transitions without recursive remapping.

**Tech Stack:** Python 3.12, PySide6/Qt, X11 EWMH, pytest, pytest-qt, uv

---

## File map

- Modify `src/atv_player/ui/player_window.py`: correct the maximized remap state transition and schedule native topmost reapplication after show/window-state changes.
- Modify `tests/test_player_window_ui.py`: cover remap ordering, real-maximized/native-surface preservation, state-change reapplication, coalescing, and paused/disabled/minimized guards.
- Reference `docs/superpowers/specs/2026-07-24-player-x11-real-maximize-topmost-design.md`: approved behavior and non-goals.

### Task 1: Force a real maximized transition during X11 remap

**Files:**
- Modify: `tests/test_player_window_ui.py:10018-10128`
- Modify: `src/atv_player/ui/player_window.py:1672-1683`

- [ ] **Step 1: Write the failing remap-order test**

Replace `test_player_window_xcb_always_on_top_remaps_visible_maximized_window` with:

```python
def test_player_window_xcb_always_on_top_remaps_through_real_maximized_state(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    calls: list[tuple[str, object]] = []
    cached_state = Qt.WindowState.WindowMaximized | Qt.WindowState.WindowActive

    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: False)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    monkeypatch.setattr(window, "windowState", lambda: cached_state)
    monkeypatch.setattr(QApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(window, "hide", lambda: calls.append(("hide", None)))
    monkeypatch.setattr(
        window,
        "setWindowState",
        lambda state: calls.append(("state", state)),
    )
    monkeypatch.setattr(
        window,
        "showMaximized",
        lambda: calls.append(("maximized", window._is_always_on_top())),
    )
    monkeypatch.setattr(window, "raise_", lambda: calls.append(("raise", None)))
    monkeypatch.setattr(
        window,
        "activateWindow",
        lambda: calls.append(("activate", None)),
    )
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: calls.append(("native", enabled)),
    )

    window._set_always_on_top(True)

    assert calls == [
        ("native", True),
        ("hide", None),
        ("state", Qt.WindowState.WindowActive),
        ("maximized", True),
        ("raise", None),
    ]

    window._reapply_always_on_top_after_show()

    assert calls[-3:] == [
        ("native", True),
        ("raise", None),
        ("activate", None),
    ]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py::test_player_window_xcb_always_on_top_remaps_through_real_maximized_state -v
```

Expected: FAIL because the current call sequence has no `setWindowState(WindowActive)` between `hide()` and `showMaximized()`.

- [ ] **Step 3: Clear Qt's cached maximized bit while hidden**

Replace `_remap_maximized_xcb_window_for_always_on_top` with:

```python
def _remap_maximized_xcb_window_for_always_on_top(self) -> None:
    if (
        QApplication.platformName().strip().lower() != "xcb"
        or not self.isVisible()
        or not self.isMaximized()
        or self.isMinimized()
    ):
        return
    self._restore_activation_after_always_on_top_remap = self.isActiveWindow()
    cached_state = self.windowState()
    self.hide()
    self.setWindowState(cached_state & ~Qt.WindowState.WindowMaximized)
    self.showMaximized()
```

The window is hidden before clearing the bit, so no normal-sized intermediate frame is shown. `showMaximized()` now sees a genuine state transition and sends a real maximization request to the window manager.

- [ ] **Step 4: Run remap and native-surface tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "xcb_always_on_top_remaps_through_real_maximized_state or xcb_maximized_remap_preserves_native_surface_ids or xcb_topmost_does_not_remap_minimized or always_on_top_preserves_window_state" -v
```

Expected: PASS for the new ordering test and existing normal/maximized/fullscreen, minimized, and native-window-ID regressions.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: preserve real maximized state during x11 remap"
```

### Task 2: Reapply topmost after maximize-button state changes

**Files:**
- Modify: `tests/test_player_window_ui.py:10222-10236`
- Modify: `src/atv_player/ui/player_window.py:730-733`
- Modify: `src/atv_player/ui/player_window.py:9970-9998`
- Modify: `src/atv_player/ui/player_window.py:10058-10063`

- [ ] **Step 1: Write failing state-change and coalescing tests**

Add beside `test_player_window_window_state_change_reapplies_visibility_state`:

```python
def test_player_window_window_state_change_reapplies_playback_topmost(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    native_calls: list[bool] = []
    window._always_on_top_enabled = True
    window._always_on_top_applied = True
    window.is_playing = True
    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: False)
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callback()),
    )

    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowStateChange))

    assert native_calls == [True]
    assert window._is_always_on_top() is True
    assert window._always_on_top_applied is True
```

Add:

```python
def test_player_window_coalesces_playback_topmost_reapply_requests(
    qtbot,
    monkeypatch,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    callbacks: list[object] = []
    native_calls: list[bool] = []
    window._always_on_top_enabled = True
    window._always_on_top_applied = True
    window.is_playing = True
    monkeypatch.setattr(window, "isVisible", lambda: True)
    monkeypatch.setattr(window, "isMinimized", lambda: False)
    monkeypatch.setattr(
        window,
        "_set_native_always_on_top",
        lambda enabled: native_calls.append(enabled),
    )
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )

    window._schedule_always_on_top_reapply()
    window._schedule_always_on_top_reapply()

    assert len(callbacks) == 1
    callback = callbacks.pop()
    assert callable(callback)
    callback()
    assert native_calls == [True]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "window_state_change_reapplies_playback_topmost or coalesces_playback_topmost_reapply_requests" -v
```

Expected: FAIL because `changeEvent()` does not schedule topmost restoration and `_schedule_always_on_top_reapply` does not exist.

- [ ] **Step 3: Add the coalesced reapply scheduler**

After `_restore_activation_after_always_on_top_remap = False` in `__init__`, add:

```python
self._always_on_top_reapply_pending = False
```

Add immediately before `_reapply_always_on_top_after_show`:

```python
def _schedule_always_on_top_reapply(self) -> None:
    if (
        self._always_on_top_reapply_pending
        or not self._should_apply_always_on_top()
        or self.isMinimized()
    ):
        return
    self._always_on_top_reapply_pending = True
    QTimer.singleShot(0, self._run_scheduled_always_on_top_reapply)

def _run_scheduled_always_on_top_reapply(self) -> None:
    self._always_on_top_reapply_pending = False
    self._reapply_always_on_top_after_show()
```

Replace `showEvent` with:

```python
def showEvent(self, event) -> None:
    super().showEvent(event)
    self._schedule_always_on_top_reapply()
```

Extend `changeEvent` to:

```python
def changeEvent(self, event: QEvent) -> None:
    super().changeEvent(event)
    if event.type() == QEvent.Type.WindowStateChange:
        self._apply_visibility_state()
        self._schedule_always_on_top_reapply()
```

- [ ] **Step 4: Add guard tests for paused, disabled, and minimized states**

Add:

```python
@pytest.mark.parametrize(
    ("enabled", "is_playing", "is_minimized"),
    [
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_player_window_window_state_change_skips_inactive_topmost_mode(
    qtbot,
    monkeypatch,
    enabled: bool,
    is_playing: bool,
    is_minimized: bool,
) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    callbacks: list[object] = []
    window._always_on_top_enabled = enabled
    window.is_playing = is_playing
    monkeypatch.setattr(window, "isMinimized", lambda: is_minimized)
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )

    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowStateChange))

    assert callbacks == []
```

- [ ] **Step 5: Run window-state and topmost regressions and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "window_state_change or playback_topmost or always_on_top or xcb_maximized" -v
```

Expected: PASS. State changes while playing reapply topmost once; paused, disabled, and minimized states schedule nothing; existing pause/resume and X11 behavior remains green.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "fix: restore topmost after player maximize changes"
```

### Task 3: Final verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run all topmost, X11, and window-state tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top or topmost or xcb_maximized or window_state_change" -v
```

Expected: PASS with no failures.

- [ ] **Step 2: Run the player UI regression suite excluding the three documented baseline failures**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -q -k "not preloads_ytdlp_passthrough_before_initial_load and not renders_route_selector_and_switches_active_group and not async_loader_with_prefilled_url_starts_immediately_and_does_not_restart_on_hydration"
```

Expected: PASS; the three deselected tests are the failures already reproduced on pre-change commit `665bdf50`.

- [ ] **Step 3: Compile and inspect the final diff**

Run:

```bash
uv run python -m py_compile src/atv_player/ui/player_window.py
git diff --check
git status --short
```

Expected: compile exits 0, `git diff --check` prints nothing, and the worktree is clean after the task commits.
