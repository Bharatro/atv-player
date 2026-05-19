# Resizable Dialogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all `ThemedDialogBase` dialogs resizable by default while preserving a per-dialog opt-out and the existing title-bar button behavior.

**Architecture:** Keep the change centralized in `src/atv_player/ui/window_chrome.py`. `ThemedDialogBase` should expose a new `resizable` constructor argument defaulting to `True`, and the existing `_ThemedChromeMixin` resize machinery should remain the only implementation. Base-class tests in `tests/test_window_chrome.py` lock the new default contract and the explicit opt-out path.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Lock the dialog resize contract with failing base-class tests

**Files:**
- Modify: `tests/test_window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the failing tests**

Update `tests/test_window_chrome.py` so the demo dialog suite expresses the new default and keeps an explicit fixed-size variant:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

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


class FixedSizeDemoDialog(ThemedDialogBase):
    def __init__(self) -> None:
        super().__init__(title="Fixed Demo Dialog", resizable=False)
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


def test_themed_dialog_defaults_to_resize_support(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.is_window_resizable() is True


def test_themed_dialog_can_disable_resize_support_explicitly(qtbot) -> None:
    dialog = FixedSizeDemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.is_window_resizable() is False
```

Remove the old `test_themed_dialog_keeps_resize_support_disabled(...)` assertion, because that contract is what this feature is changing.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -k "defaults_to_resize_support or disable_resize_support_explicitly" -q`

Expected: FAIL because `ThemedDialogBase` still hard-codes `resizable=False`, so `DemoDialog().is_window_resizable()` returns `False`.

- [ ] **Step 3: Commit the failing test change**

```bash
git add tests/test_window_chrome.py
git commit -m "test: define resizable dialog chrome contract"
```

### Task 2: Implement the new dialog default and turn the suite green

**Files:**
- Modify: `src/atv_player/ui/window_chrome.py`
- Modify: `tests/test_window_chrome.py`
- Test: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the minimal implementation**

Change `ThemedDialogBase` in `src/atv_player/ui/window_chrome.py` to accept and forward the new constructor argument:

```python
class ThemedDialogBase(QDialog, _ThemedChromeMixin):
    def __init__(
        self,
        *,
        title: str,
        parent: QWidget | None = None,
        allow_maximize: bool = False,
        resizable: bool = True,
    ) -> None:
        super().__init__(parent)
        self._init_window_chrome(
            title=title,
            allow_minimize=False,
            allow_maximize=allow_maximize,
            resizable=resizable,
        )
        self._window_chrome_content_layout.setContentsMargins(12, 12, 12, 12)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._window_chrome_root)
```

Do not change `_ThemedChromeMixin`, top-level windows, or any business dialog classes in this task. The feature is complete once the base dialog forwards the new default.

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_window_chrome.py -k "defaults_to_resize_support or disable_resize_support_explicitly" -q`

Expected: PASS

- [ ] **Step 3: Run the full chrome regression suite**

Run: `uv run pytest tests/test_window_chrome.py -q`

Expected: PASS, including:
- `test_themed_dialog_hides_maximize_button_by_default`
- `test_themed_dialog_applies_default_content_padding`
- `test_themed_widget_window_reports_resize_region_near_edges`

- [ ] **Step 4: Sanity-check the diff scope**

Run: `git diff --stat HEAD~1..HEAD`

Expected: only these files appear:
- `src/atv_player/ui/window_chrome.py`
- `tests/test_window_chrome.py`

- [ ] **Step 5: Commit the implementation**

```bash
git add src/atv_player/ui/window_chrome.py tests/test_window_chrome.py
git commit -m "feat: make themed dialogs resizable by default"
```

- [ ] **Step 6: Record verification output**

```text
Verified:
- uv run pytest tests/test_window_chrome.py -k "defaults_to_resize_support or disable_resize_support_explicitly" -q
- uv run pytest tests/test_window_chrome.py -q
```
