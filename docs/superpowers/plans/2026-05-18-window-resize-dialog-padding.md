# Window Resize And Dialog Padding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add default inner padding to all `ThemedDialogBase` dialogs and enable frameless resize behavior for `MainWindow`, `PlayerWindow`, and `LoginWindow`.

**Architecture:** Keep the change centered in `src/atv_player/ui/window_chrome.py`. `ThemedDialogBase` should own the default dialog content margins, and `_ThemedChromeMixin` should expose an opt-in `resizable` capability that only top-level app windows enable. Existing business window classes stay structurally unchanged and only pass the new constructor flag plus small assertion-oriented test updates.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Lock the chrome contract with failing base-class tests

**Files:**
- Modify: `tests/test_window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the failing tests**

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from atv_player.ui.window_chrome import (
    ThemedDialogBase,
    ThemedWidgetWindowBase,
)


class DemoWindow(ThemedWidgetWindowBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Window", allow_minimize=True, allow_maximize=True, resizable=True)
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


class DemoDialog(ThemedDialogBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Dialog")
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


def test_themed_dialog_applies_default_content_padding(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    margins = dialog.content_layout().contentsMargins()

    assert margins.left() > 0
    assert margins.top() > 0
    assert margins.right() > 0
    assert margins.bottom() > 0


def test_themed_widget_window_can_enable_resize_support(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)

    assert window.is_window_resizable() is True


def test_themed_dialog_keeps_resize_support_disabled(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.is_window_resizable() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -q`
Expected: FAIL because `ThemedWidgetWindowBase` does not accept `resizable`, `ThemedDialogBase` still has zero content margins, and `is_window_resizable()` does not exist yet.

- [ ] **Step 3: Write minimal implementation in the chrome base**

```python
class _ThemedChromeMixin:
    _window_resizable: bool = False

    def _init_window_chrome(
        self,
        *,
        title: str,
        allow_minimize: bool,
        allow_maximize: bool,
        resizable: bool = False,
    ) -> None:
        self._window_resizable = resizable
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._window_chrome_root = QWidget(self)
        self._window_chrome_root.setObjectName("windowChromeRoot")
        self._window_chrome_layout = QVBoxLayout(self._window_chrome_root)
        self._window_chrome_layout.setContentsMargins(0, 0, 0, 0)
        self._window_chrome_layout.setSpacing(0)

    def is_window_resizable(self) -> bool:
        return self._window_resizable


self._init_window_chrome(
    title=title,
    allow_minimize=allow_minimize,
    allow_maximize=allow_maximize,
    resizable=resizable,
)


self._init_window_chrome(
    title=title,
    allow_minimize=False,
    allow_maximize=allow_maximize,
    resizable=False,
)
self._window_chrome_content_layout.setContentsMargins(12, 12, 12, 12)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_window_chrome.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_window_chrome.py src/atv_player/ui/window_chrome.py
git commit -m "feat: add dialog padding and resizable chrome flag"
```

### Task 2: Add failing app-window integration tests

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_login_window_ui.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_login_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_main_window_enables_resize_support(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    assert window.is_window_resizable() is True


def test_player_window_enables_resize_support(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.is_window_resizable() is True


def test_login_window_enables_resize_support(qtbot) -> None:
    window = LoginWindow(FakeLoginController())
    qtbot.addWidget(window)

    assert window.is_window_resizable() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k resize_support -q`
Expected: FAIL because `MainWindow` is still using the default non-resizable chrome configuration.

Run: `uv run pytest tests/test_player_window_ui.py -k resize_support -q`
Expected: FAIL because `PlayerWindow` is still using the default non-resizable chrome configuration.

Run: `uv run pytest tests/test_login_window_ui.py -k resize_support -q`
Expected: FAIL because `LoginWindow` is still using the default non-resizable chrome configuration.

- [ ] **Step 3: Wire the three top-level windows to opt into resize support**

```python
super().__init__(title="alist-tvbox Desktop Player", resizable=True)


super().__init__(
    title="alist-tvbox 播放器",
    allow_minimize=True,
    allow_maximize=True,
    resizable=True,
)


super().__init__(
    title="alist-tvbox 登录",
    allow_minimize=True,
    allow_maximize=True,
    resizable=True,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k resize_support -q`
Expected: PASS

Run: `uv run pytest tests/test_player_window_ui.py -k resize_support -q`
Expected: PASS

Run: `uv run pytest tests/test_login_window_ui.py -k resize_support -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py src/atv_player/ui/login_window.py
git commit -m "feat: enable resize support on app windows"
```

### Task 3: Implement frameless edge resizing and verify the full behavior set

**Files:**
- Modify: `src/atv_player/ui/window_chrome.py`
- Test: `tests/test_window_chrome.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_login_window_ui.py`

- [ ] **Step 1: Add one focused failing test for the resize hit-test contract**

```python
def test_themed_widget_window_reports_resize_region_near_edges(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.wait(50)

    assert window._resize_region_at(window.rect().topLeft()).name == "TOP_LEFT"
    assert window._resize_region_at(window.rect().center()).name == "NONE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -k resize_region -q`
Expected: FAIL because `_resize_region_at()` and the resize-region model do not exist yet.

- [ ] **Step 3: Implement the minimal frameless resize model**

```python
from enum import IntFlag, auto


class _ResizeRegion(IntFlag):
    NONE = 0
    LEFT = auto()
    TOP = auto()
    RIGHT = auto()
    BOTTOM = auto()
    TOP_LEFT = TOP | LEFT
    TOP_RIGHT = TOP | RIGHT
    BOTTOM_LEFT = BOTTOM | LEFT
    BOTTOM_RIGHT = BOTTOM | RIGHT


class _ThemedChromeMixin:
    _resize_region: _ResizeRegion
    _resize_start_geometry: QRect | None
    _resize_start_global_pos: QPoint | None
    _RESIZE_BORDER = 6

    def _can_resize_window(self) -> bool:
        return self._window_resizable and not self.isMaximized() and not self.isFullScreen()

    def _resize_region_at(self, pos: QPoint) -> _ResizeRegion:
        if not self._can_resize_window():
            return _ResizeRegion.NONE
        rect = self.rect()
        left = pos.x() <= self._RESIZE_BORDER
        right = pos.x() >= rect.width() - self._RESIZE_BORDER
        top = pos.y() <= self._RESIZE_BORDER
        bottom = pos.y() >= rect.height() - self._RESIZE_BORDER
        region = _ResizeRegion.NONE
        if left:
            region |= _ResizeRegion.LEFT
        elif right:
            region |= _ResizeRegion.RIGHT
        if top:
            region |= _ResizeRegion.TOP
        elif bottom:
            region |= _ResizeRegion.BOTTOM
        return region

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            region = self._resize_region_at(event.position().toPoint())
            if region != _ResizeRegion.NONE:
                self._resize_region = region
                self._resize_start_geometry = self.geometry()
                self._resize_start_global_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resize_region != _ResizeRegion.NONE:
            self._perform_resize(event.globalPosition().toPoint())
            event.accept()
            return
        self._update_resize_cursor(self._resize_region_at(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._resize_region = _ResizeRegion.NONE
        self._resize_start_geometry = None
        self._resize_start_global_pos = None
        super().mouseReleaseEvent(event)
```

- [ ] **Step 4: Run the targeted and regression tests**

Run: `uv run pytest tests/test_window_chrome.py -q`
Expected: PASS

Run: `uv run pytest tests/test_main_window_ui.py -k "custom_title_bar or resize_support" -q`
Expected: PASS

Run: `uv run pytest tests/test_player_window_ui.py -k "custom_title_bar or resize_support" -q`
Expected: PASS

Run: `uv run pytest tests/test_login_window_ui.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/window_chrome.py tests/test_window_chrome.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py
git commit -m "feat: add frameless resize behavior to app windows"
```

### Task 4: Final verification sweep

**Files:**
- Modify: none
- Test: `tests/test_window_chrome.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_login_window_ui.py`

- [ ] **Step 1: Run the full targeted suite**

Run: `uv run pytest tests/test_window_chrome.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py -q`
Expected: PASS

- [ ] **Step 2: Sanity-check the diff**

Run: `git show --stat --oneline HEAD -- src/atv_player/ui/window_chrome.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py src/atv_player/ui/login_window.py tests/test_window_chrome.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py`
Expected: the show output only lists the chrome base, the three window classes, and the four UI test files for this feature.

- [ ] **Step 3: Create the final integration commit if the task was squashed locally**

```bash
git add src/atv_player/ui/window_chrome.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py src/atv_player/ui/login_window.py tests/test_window_chrome.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py
git commit -m "feat: polish frameless window resizing and dialog spacing"
```

- [ ] **Step 4: Record verification output in the work log or PR body**

```text
Verified:
- uv run pytest tests/test_window_chrome.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_login_window_ui.py -q
```
