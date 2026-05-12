# Player Log Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated top-of-sidebar icon button that shows or hides the player window's `播放日志` section without hiding the rest of the detail area, and persist that preference across window recreation.

**Architecture:** Extend `AppConfig` with one focused `player_log_visible` flag, then split the detail sidebar into a stable detail-content block plus a dedicated log-section container in `PlayerWindow`. Reuse the existing `_apply_visibility_state()` path so fullscreen and wide mode keep one visibility authority, and save the new preference immediately when the log toggle changes.

**Tech Stack:** Python 3, dataclasses, PySide6 widgets/layouts, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/models.py`
  - add persisted `player_log_visible` preference with default `True`
- Modify: `src/atv_player/ui/player_window.py`
  - add a new checkable log-toggle icon button
  - wrap the log title and `log_view` in a dedicated container widget
  - update visibility and config-save logic for the new toggle
- Modify: `tests/test_player_window_ui.py`
  - add focused UI tests for the new button, section visibility, fullscreen interaction, and persistence
- Create: `src/atv_player/icons/logs.svg`
  - provide a dedicated icon asset for the new button

### Task 1: Add the Playback Log Toggle UI Contract

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`
- Create: `src/atv_player/icons/logs.svg`

- [ ] **Step 1: Write the failing UI tests for the new button and log section**

```python
def test_player_window_exposes_playback_log_toggle_button(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.toggle_log_button.text() == ""
    assert window.toggle_log_button.toolTip() == "播放日志"
    assert window.toggle_log_button.isCheckable() is True
    assert window.toggle_log_button.isChecked() is True


def test_player_window_can_hide_only_playback_log_section(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    window.toggle_log_button.click()

    assert window.details.isHidden() is False
    assert window.metadata_view.isHidden() is False
    assert window.log_section.isHidden() is True

    window.toggle_log_button.click()

    assert window.details.isHidden() is False
    assert window.log_section.isHidden() is False
```

- [ ] **Step 2: Run the focused player-window tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "playback_log_toggle_button or hide_only_playback_log_section" -v`

Expected: FAIL because `PlayerWindow` does not expose `toggle_log_button` or `log_section`, and there is no standalone log visibility control yet.

- [ ] **Step 3: Add the new icon asset**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">
  <path d="M5 6h14"/>
  <path d="M5 12h14"/>
  <path d="M5 18h10"/>
</svg>
```

- [ ] **Step 4: Add the minimal player-window UI structure**

```python
self.toggle_log_button = self._create_icon_button("logs.svg", "播放日志")
self.toggle_log_button.setCheckable(True)
self.toggle_log_button.setChecked(True)

self.log_section = QWidget()
log_layout = QVBoxLayout(self.log_section)
log_layout.setContentsMargins(0, 0, 0, 0)
log_layout.setSpacing(6)
log_layout.addWidget(QLabel("播放日志"))
log_layout.addWidget(self.log_view, 1)

details_layout.addWidget(QLabel("影片详情"))
details_layout.addWidget(self.metadata_view, 3)
details_layout.addWidget(self.log_section, 1)

sidebar_actions.addWidget(self.toggle_playlist_button)
sidebar_actions.addWidget(self.toggle_details_button)
sidebar_actions.addWidget(self.toggle_log_button)

self.toggle_log_button.clicked.connect(self._toggle_log_visibility)
```

- [ ] **Step 5: Add the minimal visibility handler**

```python
def _toggle_log_visibility(self) -> None:
    self._apply_visibility_state()


def _apply_visibility_state(self) -> None:
    is_fullscreen = self.isFullScreen()
    sidebar_hidden = is_fullscreen or self.wide_button.isChecked()
    self.bottom_area.setHidden(is_fullscreen)
    self.sidebar_actions_widget.setHidden(is_fullscreen)
    self.sidebar_container.setHidden(sidebar_hidden)
    self.playlist.setHidden(is_fullscreen or not self.toggle_playlist_button.isChecked())
    self.details.setHidden(is_fullscreen or not self.toggle_details_button.isChecked())
    self.log_section.setHidden(
        is_fullscreen
        or not self.toggle_details_button.isChecked()
        or not self.toggle_log_button.isChecked()
    )
```

- [ ] **Step 6: Run the focused player-window tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "playback_log_toggle_button or hide_only_playback_log_section" -v`

Expected: PASS

- [ ] **Step 7: Commit the UI contract slice**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py src/atv_player/icons/logs.svg
git commit -m "feat: add player playback log toggle"
```

### Task 2: Persist the Toggle and Keep Existing Visibility Semantics

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing persistence and fullscreen regression tests**

```python
def test_player_window_hides_details_in_fullscreen_even_when_log_toggle_is_on(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    assert window.toggle_log_button.isChecked() is True

    window.toggle_fullscreen()

    assert window.isFullScreen() is True
    assert window.sidebar_actions_widget.isHidden() is True
    assert window.details.isHidden() is True
    assert window.log_section.isHidden() is True


def test_player_window_persists_playback_log_visibility(qtbot) -> None:
    saved = {"count": 0}
    config = AppConfig()
    window = PlayerWindow(
        FakePlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("count", saved["count"] + 1),
    )
    qtbot.addWidget(window)
    window.show()

    window.toggle_log_button.click()

    assert config.player_log_visible is False
    assert saved["count"] >= 1

    restored = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(restored)

    assert restored.toggle_log_button.isChecked() is False
    assert restored.log_section.isHidden() is True
```

- [ ] **Step 2: Run the focused regression tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "fullscreen_even_when_log_toggle_is_on or persists_playback_log_visibility" -v`

Expected: FAIL because `AppConfig` has no `player_log_visible` field and the log-toggle state is not saved or restored.

- [ ] **Step 3: Add the persisted config field**

```python
@dataclass(slots=True)
class AppConfig:
    ...
    player_wide_mode: bool = False
    player_log_visible: bool = True
    preferred_parse_key: str = ""
    ...
```

- [ ] **Step 4: Restore and save the toggle state in `PlayerWindow`**

```python
self.toggle_log_button = self._create_icon_button("logs.svg", "播放日志")
self.toggle_log_button.setCheckable(True)
if self.config is not None:
    self.toggle_log_button.setChecked(bool(self.config.player_log_visible))
else:
    self.toggle_log_button.setChecked(True)
```

```python
def _toggle_log_visibility(self) -> None:
    if self.config is not None and self.config.player_log_visible != self.toggle_log_button.isChecked():
        self.config.player_log_visible = self.toggle_log_button.isChecked()
        self._save_config()
    self._apply_visibility_state()
```

- [ ] **Step 5: Run the focused regression tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "fullscreen_even_when_log_toggle_is_on or persists_playback_log_visibility" -v`

Expected: PASS

- [ ] **Step 6: Run the broader player-window regression slice**

Run: `uv run pytest tests/test_player_window_ui.py -k "can_hide_playlist_and_details or toggle_fullscreen_changes_window_state or playback_log_visibility or wide_button_hides_sidebar" -v`

Expected: PASS, confirming the new log toggle does not regress the existing detail/sidebar behavior.

- [ ] **Step 7: Commit the persistence slice**

```bash
git add tests/test_player_window_ui.py src/atv_player/models.py src/atv_player/ui/player_window.py
git commit -m "feat: persist player playback log visibility"
```

### Task 3: Final Verification

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/ui/player_window.py`
- Create: `src/atv_player/icons/logs.svg`

- [ ] **Step 1: Run the complete player-window test module**

Run: `uv run pytest tests/test_player_window_ui.py -v`

Expected: PASS

- [ ] **Step 2: Run lint on the touched files**

Run: `uv run ruff check src/atv_player/models.py src/atv_player/ui/player_window.py tests/test_player_window_ui.py`

Expected: PASS with no new diagnostics

- [ ] **Step 3: Commit the final verified state if verification required follow-up edits**

```bash
git add src/atv_player/models.py src/atv_player/ui/player_window.py tests/test_player_window_ui.py src/atv_player/icons/logs.svg
git commit -m "test: verify player playback log toggle"
```
