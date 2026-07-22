# Player Always-On-Top Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a session-scoped always-on-top toggle to the player window with synchronized title-bar and video context-menu controls.

**Architecture:** Keep the behavior in `PlayerWindow` and derive the authoritative state from Qt's `WindowStaysOnTopHint`. One setter preserves the current hidden, normal, maximized, minimized, or fullscreen state while changing the flag, then synchronizes the title-bar button and current context-menu action. No settings, database, shortcut, theme, or base-window changes are required.

**Tech Stack:** Python 3, PySide6, pytest-qt, the existing custom title bar, and SVG assets.

---

## File map

- Modify `src/atv_player/ui/player_window.py`: title-bar control, Qt flag setter, control synchronization, and context-menu action.
- Create `src/atv_player/icons/pin.svg`: inactive pin icon.
- Create `src/atv_player/icons/pin-filled.svg`: active pin icon.
- Modify `tests/test_player_window_ui.py`: red-first behavior tests.
- Do not modify `src/atv_player/models.py`, `src/atv_player/storage.py`, `src/atv_player/ui/window_chrome.py`, `src/atv_player/ui/theme.py`, or `src/atv_player/ui/help_dialog.py`.

## Task 1: Add failing UI tests

**Files:**
- Test: `tests/test_player_window_ui.py`, beside the existing title-bar and video-context-menu tests.

- [ ] **Step 1: Add the flag helper and focused tests.**

```python
def _player_window_is_always_on_top(window: PlayerWindow) -> bool:
    return bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)


def test_player_window_always_on_top_defaults_to_off(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert _player_window_is_always_on_top(window) is False
    assert window.always_on_top_button.isCheckable() is True
    assert window.always_on_top_button.isChecked() is False
    assert window.always_on_top_button.toolTip() == "始终置顶"


def test_player_window_title_bar_button_toggles_always_on_top(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.always_on_top_button.click()
    assert _player_window_is_always_on_top(window) is True
    assert window.always_on_top_button.isChecked() is True

    window.always_on_top_button.click()
    assert _player_window_is_always_on_top(window) is False
    assert window.always_on_top_button.isChecked() is False


def test_player_window_always_on_top_does_not_persist_to_config(qtbot) -> None:
    saved: list[bool] = []
    config = AppConfig()
    window = PlayerWindow(
        FakePlayerController(),
        config=config,
        save_config=lambda: saved.append(True),
    )
    qtbot.addWidget(window)

    window.always_on_top_button.click()

    assert saved == []
    assert not hasattr(config, "player_always_on_top")


def test_player_window_always_on_top_failure_restores_actual_state(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    messages: list[str] = []

    def fail_to_set_window_flag(*_args, **_kwargs) -> None:
        raise RuntimeError("unsupported")

    monkeypatch.setattr(window, "setWindowFlag", fail_to_set_window_flag)
    monkeypatch.setattr(window, "_append_log", messages.append)

    window.always_on_top_button.click()

    assert _player_window_is_always_on_top(window) is False
    assert window.always_on_top_button.isChecked() is False
    assert window.always_on_top_button.toolTip() == "始终置顶"
    assert messages == ["置顶切换失败: unsupported"]


def test_player_window_context_menu_always_on_top_action_syncs_with_title_bar(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    menu = window._build_video_context_menu()
    action = next(item for item in menu.actions() if item.text() == "始终置顶")

    assert action.isCheckable() is True
    assert action.isChecked() is False

    window.always_on_top_button.click()
    assert action.isChecked() is True

    action.trigger()
    assert _player_window_is_always_on_top(window) is False
    assert window.always_on_top_button.isChecked() is False


def test_player_window_always_on_top_survives_hide_but_not_new_instance(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.always_on_top_button.click()
    window.hide()

    assert _player_window_is_always_on_top(window) is True
    window.show()
    assert _player_window_is_always_on_top(window) is True

    new_window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(new_window)
    assert _player_window_is_always_on_top(new_window) is False


@pytest.mark.parametrize("state", ["normal", "maximized", "fullscreen"])
def test_player_window_always_on_top_preserves_window_state(qtbot, state: str) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    if state == "maximized":
        window.showMaximized()
    elif state == "fullscreen":
        window.showFullScreen()
    qtbot.wait(30)

    before = (
        window.isVisible(),
        window.isMinimized(),
        window.isMaximized(),
        window.isFullScreen(),
    )
    window._set_always_on_top(True)
    qtbot.wait(30)

    assert (
        window.isVisible(),
        window.isMinimized(),
        window.isMaximized(),
        window.isFullScreen(),
    ) == before
```

- [ ] **Step 2: Run the new tests and verify RED.**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top" -v
```

Expected: test collection succeeds, then failures report missing `always_on_top_button`, `_set_always_on_top`, or the “始终置顶” menu action. Fix fixture or syntax errors until failures are exclusively caused by the missing feature.

- [ ] **Step 3: Commit the red tests.**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: specify player always-on-top behavior"
```

## Task 2: Add the title-bar control and icon assets

**Files:**
- Create: `src/atv_player/icons/pin.svg`
- Create: `src/atv_player/icons/pin-filled.svg`
- Modify: `src/atv_player/ui/player_window.py`, near `_video_context_menu`, the existing return-button setup, and `_format_tooltip`.

- [ ] **Step 1: Add the two SVG assets.**

Create `src/atv_player/icons/pin.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#c0c0c0">
  <path d="M17 9V4h1V2H6v2h1v5c0 1.1-.9 2-2 2v2h6v7h2v-7h6v-2c-1.1 0-2-.9-2-2Zm-8.01 2C9.62 10.45 10 9.66 10 9V4h4v5c0 .66.38 1.45 1.01 2H8.99Z"/>
</svg>
```

Create `src/atv_player/icons/pin-filled.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#c0c0c0">
  <path d="M17 9V4h1V2H6v2h1v5c0 1.1-.9 2-2 2v2h6v7h2v-7h6v-2c-1.1 0-2-.9-2-2Z"/>
</svg>
```

- [ ] **Step 2: Track the current context-menu action and add the title-bar button.**

Near `self._video_context_menu`, add:

```python
self._always_on_top_menu_action: QAction | None = None
```

Immediately before the existing `title_bar_return_button` construction, add:

```python
self.always_on_top_button = QPushButton("", self.title_bar())
self.always_on_top_button.setObjectName("customTitleBarAlwaysOnTopButton")
self.always_on_top_button.setCheckable(True)
self.always_on_top_button.setIconSize(QSize(16, 16))
self.always_on_top_button.setCursor(Qt.CursorShape.PointingHandCursor)
```

Replace the single-button title-bar registration with:

```python
self.title_bar().set_extra_action_buttons(
    [self.always_on_top_button, self.title_bar_return_button]
)
self._sync_always_on_top_controls()
```

- [ ] **Step 3: Add the authoritative flag reader and control synchronizer.**

Place these methods immediately after `_format_tooltip`:

```python
def _is_always_on_top(self) -> bool:
    return bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)


def _sync_always_on_top_controls(self, *, menu_action: QAction | None = None) -> bool:
    enabled = self._is_always_on_top()
    action = menu_action or self._always_on_top_menu_action
    button = getattr(self, "always_on_top_button", None)
    label = "取消始终置顶" if enabled else "始终置顶"
    if button is not None:
        previous_block_state = button.blockSignals(True)
        try:
            button.setChecked(enabled)
            button.setToolTip(label)
            button.setAccessibleName(label)
            icon_name = "pin-filled.svg" if enabled else "pin.svg"
            button.setProperty("icon_name", icon_name)
            button.setIcon(load_icon(self._icons_dir / icon_name))
        finally:
            button.blockSignals(previous_block_state)
    if action is not None:
        previous_block_state = action.blockSignals(True)
        try:
            action.setChecked(enabled)
        finally:
            action.blockSignals(previous_block_state)
    return enabled
```

- [ ] **Step 4: Run the default-state test and verify the first GREEN slice.**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top_defaults_to_off" -v
```

Expected: PASS. Other always-on-top tests remain red until the setter and menu action are added.

- [ ] **Step 5: Commit the control slice.**

```bash
git add src/atv_player/icons/pin.svg src/atv_player/icons/pin-filled.svg src/atv_player/ui/player_window.py
git commit -m "feat: add player always-on-top control"
```

## Task 3: Implement safe Qt flag toggling

**Files:**
- Modify: `src/atv_player/ui/player_window.py`, immediately after `_sync_always_on_top_controls`.
- Test: the title-button, config-isolation, session-scope, and window-state tests from Task 1.

- [ ] **Step 1: Add the state-preserving setter.**

```python
def _set_always_on_top(
    self,
    enabled: bool,
    *,
    menu_action: QAction | None = None,
) -> None:
    requested = bool(enabled)
    if requested != self._is_always_on_top():
        was_visible = self.isVisible()
        was_minimized = self.isMinimized()
        was_fullscreen = self.isFullScreen()
        was_maximized = self.isMaximized()
        try:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, requested)
            if was_visible:
                if was_minimized:
                    self.showMinimized()
                elif was_fullscreen:
                    self.showFullScreen()
                elif was_maximized:
                    self.showMaximized()
                else:
                    self.show()
                if not was_minimized:
                    self.raise_()
        except Exception as exc:
            logger.exception("PlayerWindow always-on-top toggle failed")
            try:
                self._append_log(f"置顶切换失败: {exc}")
            except Exception:
                pass
    self._sync_always_on_top_controls(menu_action=menu_action)
```

This method must not access `self.config` or call `_save_config`. The final control state comes from `windowFlags()`, so a platform rejection automatically rolls the UI back to the actual result.

- [ ] **Step 2: Connect the title-bar button to the completed setter.**

After the button's cursor setup in `__init__`, add:

```python
self.always_on_top_button.toggled.connect(self._set_always_on_top)
```

- [ ] **Step 3: Run the setter-related tests.**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top and not context_menu" -v
```

Expected: the title-button toggle, config-isolation, failure rollback/logging, hide/re-show, new-instance, and normal/maximized/fullscreen preservation tests pass. If offscreen Qt normalizes a requested window state before the toggle, compare against the state actually observed immediately before `_set_always_on_top`, as the test already does.

- [ ] **Step 4: Commit the Qt flag implementation.**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: toggle player window stay-on-top flag"
```

## Task 4: Add and synchronize the context-menu action

**Files:**
- Modify: `src/atv_player/ui/player_window.py` in `_build_video_context_menu` and `_handle_video_context_menu_hidden`.
- Test: `tests/test_player_window_ui.py::test_player_window_context_menu_always_on_top_action_syncs_with_title_bar`.

- [ ] **Step 1: Add a checkable action initialized from the current flag.**

Replace the existing final `menu.addAction("退出播放", self._return_to_main)` line in `_build_video_context_menu` with this block:

```python
always_on_top_action = menu.addAction("始终置顶")
always_on_top_action.setCheckable(True)
always_on_top_action.toggled.connect(
    lambda checked, action=always_on_top_action: self._set_always_on_top(
        checked,
        menu_action=action,
    )
)
self._always_on_top_menu_action = always_on_top_action
self._sync_always_on_top_controls(menu_action=always_on_top_action)
menu.addAction("退出播放", self._return_to_main)
```

The final menu order must remain `视频信息`, `始终置顶`, `退出播放`.

- [ ] **Step 2: Clear the transient action after the menu hides.**

Replace `_handle_video_context_menu_hidden` with:

```python
def _handle_video_context_menu_hidden(self, menu: QMenu) -> None:
    if self._video_context_menu is menu:
        self._video_context_menu = None
    action = self._always_on_top_menu_action
    if action is not None and action.parent() is menu:
        self._always_on_top_menu_action = None
```

This lets a title-bar click synchronize an action while its menu is alive, while avoiding a reference to a deleted `QAction` after `aboutToHide`/`deleteLater`.

- [ ] **Step 3: Run the new feature tests and the player-window suite.**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top" -v
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -q
```

Expected: all always-on-top tests pass, followed by the existing player-window UI suite passing with no warnings or errors.

- [ ] **Step 4: Commit the menu integration.**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: expose player always-on-top in context menu"
```

## Task 5: Final verification and focused cleanup

**Files:**
- Review only: `src/atv_player/ui/player_window.py`, `tests/test_player_window_ui.py`, `src/atv_player/icons/pin.svg`, and `src/atv_player/icons/pin-filled.svg`.

- [ ] **Step 1: Check the diff and confirm there is no persistence or shortcut change.**

Run:

```bash
git diff HEAD~4..HEAD --check
git diff HEAD~4..HEAD -- src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/help_dialog.py
rg -n "player_always_on_top|always_on_top|WindowStaysOnTopHint" src/atv_player tests/test_player_window_ui.py
```

Expected: no whitespace errors; the model, storage, and shortcut-help diff is empty; all feature references are confined to the planned player code, icon assets, and tests.

- [ ] **Step 2: Run final verification.**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top" -v
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_window_chrome.py tests/test_player_window_ui.py -q
```

Expected: both commands exit 0 with all tests passing.

- [ ] **Step 3: Confirm unrelated work remains untouched.**

Run:

```bash
git status --short
git diff -- src/atv_player/ui/poster_loader.py
```

Expected: the pre-existing `poster_loader.py` modification remains present and is not included in any feature commit; only the planned feature files are changed by this work.

- [ ] **Step 4: Make a cleanup commit only for a concrete verified defect.**

If the preceding checks expose a real defect, fix only that defect, rerun both verification commands, and use:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py src/atv_player/icons/pin.svg src/atv_player/icons/pin-filled.svg
git commit -m "fix: polish player always-on-top behavior"
```

Do not add persistence, shortcuts, platform-specific APIs, or unrelated refactors after the tests pass.
