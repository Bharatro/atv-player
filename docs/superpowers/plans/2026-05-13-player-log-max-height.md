# Player Log Max Height Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Limit the player window playback log section so it never grows beyond one quarter of the right-side details panel height.

**Architecture:** Keep the existing `details -> metadata_section + log_section` sidebar structure and add one small `PlayerWindow` helper that recalculates `log_section.maximumHeight()` from `details.height()`. Reuse the existing widget lifecycle by triggering that helper after UI construction and whenever the details widget receives resize/show events.

**Tech Stack:** Python, PySide6, pytest-qt

---

### Task 1: Add a failing UI test for the log-height cap

**Files:**
- Modify: `tests/test_player_window_ui.py:1580-1592`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_player_window_limits_playback_log_height_to_one_quarter_of_details(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qtbot.waitExposed(window)

    window.details.resize(window.details.width(), 480)
    QApplication.processEvents()

    assert window.log_section.maximumHeight() == 120

    window.details.resize(window.details.width(), 640)
    QApplication.processEvents()

    assert window.log_section.maximumHeight() == 160
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "limits_playback_log_height_to_one_quarter_of_details" -v`

Expected: `FAIL` because `window.log_section.maximumHeight()` still uses the default unconstrained value instead of tracking `details.height() // 4`.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover player log height cap"
```

### Task 2: Implement the height cap and turn the test green

**Files:**
- Modify: `src/atv_player/ui/player_window.py:535-566`
- Modify: `src/atv_player/ui/player_window.py:681-717`
- Modify: `src/atv_player/ui/player_window.py:5218-5296`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add the minimal implementation**

```python
class PlayerWindow(QWidget, AsyncGuardMixin):
    _DETAIL_LOG_MAX_HEIGHT_DIVISOR = 4

    def __init__(self, ...):
        ...
        self.details = QWidget()
        self.details.installEventFilter(self)
        ...
        self._apply_visibility_state()
        self._update_log_section_max_height()

    def _update_log_section_max_height(self) -> None:
        details_height = max(self.details.height(), 1)
        self.log_section.setMaximumHeight(max(details_height // self._DETAIL_LOG_MAX_HEIGHT_DIVISOR, 1))

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.details and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._update_log_section_max_height()
        ...
```

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k "limits_playback_log_height_to_one_quarter_of_details" -v`

Expected: `PASS`

- [ ] **Step 3: Run the nearby detail/log tests to catch regressions**

Run: `uv run pytest tests/test_player_window_ui.py -k "uses_detail_container_with_metadata_and_log_views or can_hide_only_playback_log_section" -v`

Expected: both tests `PASS`

- [ ] **Step 4: Commit the implementation**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: cap player log height"
```
