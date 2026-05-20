# Player Poster Arrow Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the player detail poster arrows to the left and right sides of the poster, switch them to Qt built-in arrow buttons, and soften their visual treatment without changing poster-switching behavior.

**Architecture:** Keep the existing poster source selection and index-reset logic intact. Replace the current svg-backed navigation buttons with lightweight `QToolButton` arrows, fold them into the same row as `poster_label`, and update UI tests to verify the new control type and layout relationships while preserving existing interaction coverage.

**Tech Stack:** Python 3, PySide6 widgets/layouts, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/ui/player_window.py`
  - Replace svg navigation buttons with built-in-arrow `QToolButton`s, move them into the poster row, and apply low-emphasis styling.
- Modify: `tests/test_player_window_ui.py`
  - Update navigation tests to assert the new layout structure and control type while keeping click behavior checks.

### Task 1: Refine Poster Arrow Layout And Styling

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing UI tests**

Add a layout-focused test near the current poster-navigation tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_places_builtin_arrow_buttons_on_both_sides_of_poster(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert isinstance(window._poster_previous_button, QToolButton)
    assert isinstance(window._poster_next_button, QToolButton)
    assert window._poster_previous_button.arrowType() == Qt.ArrowType.LeftArrow
    assert window._poster_next_button.arrowType() == Qt.ArrowType.RightArrow

    layout = window._poster_row_layout
    assert layout.indexOf(window._poster_previous_button) < layout.indexOf(window.poster_label)
    assert layout.indexOf(window.poster_label) < layout.indexOf(window._poster_next_button)
```

Extend the existing multi-poster visibility test with one weak-style assertion that does not depend on theme colors:

```python
assert window._poster_previous_button.autoRaise() is True
assert window._poster_next_button.autoRaise() is True
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen /home/harold/.local/bin/uv run pytest tests/test_player_window_ui.py -k "poster_navigation or builtin_arrow_buttons" -v
```

Expected:

```text
FAILED tests/test_player_window_ui.py::test_player_window_places_builtin_arrow_buttons_on_both_sides_of_poster
```

The failure should show that the current implementation still uses svg-backed push buttons and a separate navigation row below the poster.

- [ ] **Step 3: Write the minimal implementation**

In `src/atv_player/ui/player_window.py`, import `QToolButton` if it is not already imported, then replace the current button construction:

```python
self._poster_previous_button = QToolButton()
self._poster_previous_button.setToolTip("上一张海报")
self._poster_previous_button.setArrowType(Qt.ArrowType.LeftArrow)
self._poster_previous_button.setAutoRaise(True)
self._poster_previous_button.setCursor(Qt.CursorShape.PointingHandCursor)
self._poster_previous_button.setFixedSize(24, 24)
self._poster_previous_button.setHidden(True)

self._poster_next_button = QToolButton()
self._poster_next_button.setToolTip("下一张海报")
self._poster_next_button.setArrowType(Qt.ArrowType.RightArrow)
self._poster_next_button.setAutoRaise(True)
self._poster_next_button.setCursor(Qt.CursorShape.PointingHandCursor)
self._poster_next_button.setFixedSize(24, 24)
self._poster_next_button.setHidden(True)
```

Replace the separate poster widget + navigation widget arrangement with one shared row:

```python
self._poster_row_widget = QWidget()
self._poster_row_layout = QHBoxLayout(self._poster_row_widget)
self._poster_row_layout.setContentsMargins(0, 0, 0, 0)
self._poster_row_layout.setSpacing(6)
self._poster_row_layout.addStretch(1)
self._poster_row_layout.addWidget(self._poster_previous_button, 0, Qt.AlignmentFlag.AlignVCenter)
self._poster_row_layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignVCenter)
self._poster_row_layout.addWidget(self._poster_next_button, 0, Qt.AlignmentFlag.AlignVCenter)
self._poster_row_layout.addStretch(1)
metadata_layout.addWidget(self._poster_row_widget)
```

Keep `_refresh_poster_navigation()` behavior the same, but stop toggling a dedicated navigation widget that no longer exists:

```python
def _refresh_poster_navigation(self) -> None:
    visible = len(self._current_metadata_poster_sources()) > 1
    self._poster_previous_button.setHidden(not visible)
    self._poster_next_button.setHidden(not visible)
```

Apply a low-emphasis stylesheet near the existing widget styling section so the arrows stay subdued:

```python
self._poster_previous_button.setStyleSheet(
    "QToolButton { border: none; background: transparent; padding: 0; }"
    "QToolButton:hover { background: rgba(127, 127, 127, 0.10); border-radius: 12px; }"
)
self._poster_next_button.setStyleSheet(self._poster_previous_button.styleSheet())
```

Do not change `_step_metadata_poster(...)`, `_preferred_detail_poster_source(...)`, or any metadata reset path in this task.

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:

```bash
QT_QPA_PLATFORM=offscreen /home/harold/.local/bin/uv run pytest tests/test_player_window_ui.py -k "poster_navigation or builtin_arrow_buttons" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_places_builtin_arrow_buttons_on_both_sides_of_poster
PASSED tests/test_player_window_ui.py::test_player_window_shows_poster_navigation_for_multiple_candidates
PASSED tests/test_player_window_ui.py::test_player_window_hides_poster_navigation_for_single_candidate
PASSED tests/test_player_window_ui.py::test_player_window_poster_navigation_loops_at_boundaries
```

- [ ] **Step 5: Run the broader poster regressions**

Run:

```bash
QT_QPA_PLATFORM=offscreen /home/harold/.local/bin/uv run pytest tests/test_player_window_ui.py -k "renders_poster or poster_navigation or resets_detail_poster" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_renders_poster_when_session_has_vod_pic
PASSED tests/test_player_window_ui.py::test_player_window_places_builtin_arrow_buttons_on_both_sides_of_poster
PASSED tests/test_player_window_ui.py::test_player_window_shows_poster_navigation_for_multiple_candidates
PASSED tests/test_player_window_ui.py::test_player_window_hides_poster_navigation_for_single_candidate
PASSED tests/test_player_window_ui.py::test_player_window_poster_navigation_loops_at_boundaries
PASSED tests/test_player_window_ui.py::test_player_window_toggling_original_metadata_resets_detail_poster_to_first_candidate
PASSED tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_resets_detail_poster_index
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "refactor: refine player poster arrow controls"
```

## Coverage Check

- Spec section `Layout` is covered by Task 1 through the new shared poster row and layout-order assertions.
- Spec section `Button widget choice` is covered by Task 1 through `QToolButton` and `arrowType()` assertions.
- Spec section `Visual styling` is covered by Task 1 through `autoRaise`, borderless styling, and transparent default background.
- Spec section `Behavior` is covered by Task 1 through the retained navigation and reset regression tests.

## Placeholder Scan

- No `TODO`, `TBD`, or “similar to above” placeholders remain.
- The task includes exact files, code, commands, and expected outcomes.
- All helper names referenced in test steps map directly to existing or newly defined symbols in this plan.
