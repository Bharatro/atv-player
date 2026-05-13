# Player Log Bottom When Details Hidden Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the player details panel is hidden but playback logs remain enabled, show the log section docked at the bottom of the right sidebar and let the playlist fill the remaining height above it.

**Architecture:** Keep the existing `sidebar_splitter` plus `details` structure for normal states. Add a small `PlayerWindow` layout-switch helper that moves `log_section` between the `details` layout and the outer sidebar layout based on the current visibility state, then reuse `_apply_visibility_state()` as the single place that decides where the log section lives.

**Tech Stack:** Python, PySide6, pytest-qt

---

### Task 1: Add failing UI coverage for bottom-docked logs

**Files:**
- Modify: `tests/test_player_window_ui.py:3918-3955`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Replace the old behavior test with a bottom-dock test**

```python
def test_player_window_hides_details_and_docks_log_to_sidebar_bottom(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    window.toggle_details_button.click()

    assert window.playlist.isHidden() is False
    assert window.details.isHidden() is True
    assert window.log_section.isHidden() is False
    assert window.details.layout().indexOf(window.log_section) == -1
    assert window.sidebar_layout.indexOf(window.log_section) == window.sidebar_layout.count() - 1

    window.toggle_details_button.click()

    assert window.details.isHidden() is False
    assert window.details.layout().indexOf(window.log_section) != -1
    assert window.sidebar_layout.indexOf(window.log_section) == -1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "docks_log_to_sidebar_bottom" -v`

Expected: `FAIL` because `log_section` still remains inside the `details` layout when `详情` is hidden.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover docked player log layout"
```

### Task 2: Implement log reparenting and verify regressions

**Files:**
- Modify: `src/atv_player/ui/player_window.py:535-661`
- Modify: `src/atv_player/ui/player_window.py:4960-4977`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add minimal layout-switch helpers in `PlayerWindow`**

```python
    def _should_dock_log_to_sidebar_bottom(self) -> bool:
        return (
            not self.isFullScreen()
            and not self.wide_button.isChecked()
            and not self.toggle_details_button.isChecked()
            and self.toggle_log_button.isChecked()
        )

    def _move_log_section_to_layout(self, layout: QVBoxLayout) -> None:
        current_layout = self.log_section.parentWidget().layout() if self.log_section.parentWidget() is not None else None
        if current_layout is layout:
            return
        if current_layout is not None:
            current_layout.removeWidget(self.log_section)
        layout.addWidget(self.log_section)

    def _update_log_section_host_layout(self) -> None:
        if self._should_dock_log_to_sidebar_bottom():
            self._move_log_section_to_layout(self.sidebar_layout)
            return
        self._move_log_section_to_layout(self.details_layout)
```

- [ ] **Step 2: Wire the helpers into the existing layout state**

```python
        self.details_layout = details_layout
        ...
        self.sidebar_layout = sidebar_layout
        ...
        self._update_log_section_host_layout()
        self.details.setHidden(is_fullscreen or (not metadata_visible and not log_visible))
        self.metadata_section.setHidden(is_fullscreen or not metadata_visible)
        self.log_section.setHidden(is_fullscreen or not log_visible)
```

The implementation should preserve the existing `details_layout` order when restoring the log section:

```python
        self.details_layout.addWidget(self.log_section, 1)
```

- [ ] **Step 3: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k "docks_log_to_sidebar_bottom" -v`

Expected: `PASS`

- [ ] **Step 4: Run nearby regression tests**

Run: `uv run pytest tests/test_player_window_ui.py -k "can_hide_only_playback_log_section or toggle_fullscreen_changes_window_state or hides_details_in_fullscreen_even_when_log_toggle_is_on" -v`

Expected: all selected tests `PASS`

- [ ] **Step 5: Commit the implementation**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: dock player log below playlist"
```
