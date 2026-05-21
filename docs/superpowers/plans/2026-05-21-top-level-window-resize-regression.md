# Top-Level Window Resize Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore frameless edge-resize behavior for `MainWindow`, `PlayerWindow`, and `LoginWindow` without breaking normal button clicks.

**Architecture:** Keep the fix in `src/atv_player/ui/window_chrome.py`. First add a regression test that delivers resize drag events through a descendant widget at the window edge, then update the shared chrome mixin so resize event filtering covers the full descendant tree while still allowing non-edge clicks to reach the target widgets.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Reproduce the descendant-edge resize failure

**Files:**
- Modify: `tests/test_window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the failing test**

```python
def test_themed_widget_window_dragging_edge_through_descendant_resizes_window(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)
    edge_button = QPushButton("edge", window.content_widget())
    edge_button.setGeometry(0, 60, 40, 120)
    window.show()
    qtbot.wait(50)

    start_rect = window.geometry()
    press_global = edge_button.mapToGlobal(edge_button.rect().centerLeft() + QPoint(1, 0))
    press_local = edge_button.mapFromGlobal(press_global)

    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global + QPoint(-40, 0)
    move_local = edge_button.mapFromGlobal(move_global)
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseMove,
            move_local,
            move_global,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        edge_button,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            move_local,
            move_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert window.geometry().width() > start_rect.width()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -k descendant_resizes_window -q`
Expected: FAIL because the current resize event filter does not consistently cover descendant widgets at the edge.

- [ ] **Step 3: Commit**

```bash
git add tests/test_window_chrome.py
git commit -m "test: reproduce top-level resize regression"
```

### Task 2: Fix the shared window chrome event coverage

**Files:**
- Modify: `src/atv_player/ui/window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the minimal implementation**

```python
class _ThemedChromeMixin:
    def _install_resize_event_filter(self, widget: QWidget) -> None:
        widget.installEventFilter(self)
        widget.setMouseTracking(True)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)
            child.setMouseTracking(True)
```

Add deduplication so widgets are not reinstalled repeatedly, and keep `childEvent()` so newly added descendants also receive the filter.

- [ ] **Step 2: Preserve normal click behavior**

```python
def _handle_resize_mouse_press(self, event: QMouseEvent) -> bool:
    if event.button() != Qt.MouseButton.LeftButton:
        return False
    region = self._resize_region_at(self._mouse_event_pos_in_self(event))
    if region == _ResizeRegion.NONE:
        return False
```

Do not intercept mouse presses away from the resize border. Only edge and corner presses should be accepted by the chrome mixin.

- [ ] **Step 3: Run focused chrome tests**

Run: `uv run pytest tests/test_window_chrome.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/atv_player/ui/window_chrome.py tests/test_window_chrome.py
git commit -m "fix: restore top-level edge resize handling"
```

### Task 3: Verify the affected app windows still behave correctly

**Files:**
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_login_window_ui.py`

- [ ] **Step 1: Run focused regression coverage**

Run: `uv run pytest tests/test_main_window_ui.py -k "resize_support or global_search_button" -q`
Expected: PASS

Run: `uv run pytest tests/test_player_window_ui.py -k "resize_support or title_bar_return_button or mute_button or toggle_details_button" -q`
Expected: PASS

Run: `uv run pytest tests/test_login_window_ui.py -k "resize_support or click_login" -q`
Expected: PASS

- [ ] **Step 2: Review final diff**

Run: `git diff -- src/atv_player/ui/window_chrome.py tests/test_window_chrome.py`
Expected: Only the shared chrome fix and focused regression test changes appear.
