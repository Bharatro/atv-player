# Top-Level Window Resize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore frameless edge resize for `MainWindow`, `PlayerWindow`, and `LoginWindow` when mouse events land on child widgets at the window boundary.

**Architecture:** Keep the fix in `src/atv_player/ui/window_chrome.py`. First add a regression test that reproduces the real failure path by dragging through a child widget at the edge, then update `_ThemedChromeMixin` so resize event filtering covers the full descendant widget tree, including widgets added after chrome initialization. Finish by rerunning the shared chrome tests and the top-level window smoke tests that already assert resize support is enabled.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Lock the regression with a child-widget edge-resize test

**Files:**
- Modify: `tests/test_window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the failing test**

```python
class EdgeToEdgeWindow(ThemedWidgetWindowBase):
    def __init__(self) -> None:
        super().__init__(title="Edge Window", allow_minimize=True, allow_maximize=True, resizable=True)
        self.edge_child = QWidget(self.content_widget())
        self.edge_child.setObjectName("edgeChild")
        self.content_layout().addWidget(self.edge_child)


def test_themed_widget_window_dragging_right_edge_through_child_widget_resizes_window(qtbot) -> None:
    window = EdgeToEdgeWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)
    window.show()
    qtbot.wait(50)

    start_rect = window.geometry()
    press_global = window.mapToGlobal(QPoint(window.width() - 2, window.height() // 2))
    press_local = window.edge_child.mapFromGlobal(press_global)
    QApplication.sendEvent(
        window.edge_child,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global + QPoint(40, 0)
    move_local = window.edge_child.mapFromGlobal(move_global)
    QApplication.sendEvent(
        window.edge_child,
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
        window.edge_child,
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

Run: `uv run pytest tests/test_window_chrome.py -k child_widget_resizes_window -q`

Expected: FAIL because the mouse events are delivered to `edge_child`, but `_ThemedChromeMixin` only watches the outer chrome widgets, so the resize interaction never starts and the width stays unchanged.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_window_chrome.py
git commit -m "test: cover child widget window edge resize regression"
```

### Task 2: Make the chrome resize filter cover the full widget tree

**Files:**
- Modify: `src/atv_player/ui/window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the minimal implementation**

```python
class _ThemedChromeMixin:
    _resize_tracked_widgets: set[QWidget]

    def _init_window_chrome(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
        resizable: bool = False,
    ) -> None:
        self._window_resizable = resizable
        self._resize_tracked_widgets = set()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMouseTracking(True)
        self._window_chrome_root = QWidget(self)
        self._window_chrome_root.setObjectName("windowChromeRoot")
        self._window_chrome_layout = QVBoxLayout(self._window_chrome_root)
        self._window_chrome_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_layout.setSpacing(0)
        self._install_resize_event_filter_tree(self._window_chrome_root)
        ...
        self._install_resize_event_filter_tree(self._title_bar)
        ...
        self._install_resize_event_filter_tree(self._window_chrome_content)
        ...

    def _install_resize_event_filter(self, widget: QWidget) -> None:
        if widget in self._resize_tracked_widgets:
            return
        widget.installEventFilter(self)
        widget.setMouseTracking(True)
        self._resize_tracked_widgets.add(widget)

    def _install_resize_event_filter_tree(self, widget: QWidget) -> None:
        self._install_resize_event_filter(widget)
        for child in widget.findChildren(QWidget):
            self._install_resize_event_filter(child)

    def childEvent(self, event) -> None:
        super().childEvent(event)
        child = event.child()
        if isinstance(child, QWidget):
            self._install_resize_event_filter_tree(child)
```

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_window_chrome.py -k child_widget_resizes_window -q`

Expected: PASS because the child widget now has the resize event filter and the drag updates the window geometry.

- [ ] **Step 3: Run the shared chrome suite**

Run: `uv run pytest tests/test_window_chrome.py -q`

Expected: PASS with the existing dialog-resize and title-bar behavior unchanged.

- [ ] **Step 4: Commit the shared fix**

```bash
git add src/atv_player/ui/window_chrome.py tests/test_window_chrome.py
git commit -m "fix: track resize events through child widgets"
```

### Task 3: Re-run affected top-level window smoke tests

**Files:**
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_login_window_ui.py`

- [ ] **Step 1: Run the main-window resize-support smoke test**

Run: `uv run pytest tests/test_main_window_ui.py -k resize_support -q`

Expected: PASS and confirms `MainWindow` still opts into resizable chrome after the shared fix.

- [ ] **Step 2: Run the player-window resize-support smoke test**

Run: `uv run pytest tests/test_player_window_ui.py -k resize_support -q`

Expected: PASS and confirms `PlayerWindow` still opts into resizable chrome after the shared fix.

- [ ] **Step 3: Run the login-window resize-support smoke test**

Run: `uv run pytest tests/test_login_window_ui.py -k resize_support -q`

Expected: PASS and confirms `LoginWindow` still opts into resizable chrome after the shared fix.

- [ ] **Step 4: Commit the verification checkpoint**

```bash
git add docs/superpowers/plans/2026-05-20-top-level-window-resize.md
git commit -m "docs: add top-level window resize implementation plan"
```
