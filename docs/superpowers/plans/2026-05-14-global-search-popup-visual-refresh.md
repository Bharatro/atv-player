# Global Search Popup Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the global-search popup into a warmer, content-oriented search panel without changing its current behavior.

**Architecture:** Keep all behavior in `MainWindow` and `GlobalSearchPopup` unchanged at the interaction level, but refactor `GlobalSearchPopup` so visual styling is centralized around section-level helpers and richer row widgets. Add a small amount of test-facing structure so UI tests can verify stable row height and ranked hot-search rendering without coupling to fragile stylesheet text.

**Tech Stack:** Python, PySide6, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/main_window.py`
  Purpose: Refactor `GlobalSearchPopup` styling, add richer history/hot item widget structure, and keep popup behavior unchanged.
- Modify: `tests/test_main_window_ui.py`
  Purpose: Add focused UI assertions for fixed history row height and ranked hot-search item structure while preserving existing popup-behavior coverage.

## Task 1: Lock Down the New Visual Structure with Tests

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add failing helper accessors for popup row structure**

```python
def _popup_history_row(window: MainWindow, keyword: str):
    return window._global_search_popup.history_item_row(keyword)


def _popup_hot_ranks(window: MainWindow) -> list[str]:
    return window._global_search_popup.hot_item_ranks()
```

- [ ] **Step 2: Add a failing test for fixed history row height**

```python
def test_main_window_global_search_popup_history_rows_use_fixed_height(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(global_search_history=["庆余年"]),
        global_search_hotkey_loader=lambda hot_type: [],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    qtbot.mouseClick(window.global_search_popup_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: _popup_history_texts(window) == ["庆余年"])
    assert _popup_history_row(window, "庆余年").height() == window._global_search_popup.HISTORY_ITEM_HEIGHT
```

- [ ] **Step 3: Add a failing test for ranked hot-search items**

```python
def test_main_window_global_search_popup_hot_items_show_rank_numbers(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(global_search_history=[]),
        global_search_hotkey_loader=lambda hot_type: [
            {"title": "热搜一", "query": "热搜一"},
            {"title": "热搜二", "query": "热搜二"},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    qtbot.mouseClick(window.global_search_popup_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: _popup_hot_texts(window) == ["热搜一", "热搜二"])
    assert _popup_hot_ranks(window) == ["01", "02"]
```

- [ ] **Step 4: Run the two new tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup_history_rows_use_fixed_height or global_search_popup_hot_items_show_rank_numbers" -q
```

Expected:

```text
FAILED tests/test_main_window_ui.py::test_main_window_global_search_popup_history_rows_use_fixed_height
FAILED tests/test_main_window_ui.py::test_main_window_global_search_popup_hot_items_show_rank_numbers
```

- [ ] **Step 5: Commit the red test state**

```bash
git add tests/test_main_window_ui.py
git commit -m "test: cover global search popup visual structure"
```

## Task 2: Implement the Warm Search-Panel Styling in `GlobalSearchPopup`

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add centralized popup style constants and test helpers**

```python
class GlobalSearchPopup(QWidget):
    item_clicked = Signal(str)
    clear_history_requested = Signal()
    delete_history_requested = Signal(str)
    hot_tab_changed = Signal(str)
    HISTORY_ITEM_HEIGHT = 40
    HOT_ITEM_HEIGHT = 48

    _CONTAINER_QSS = """
    QWidget {
        background: #f7f1e8;
        border: 1px solid #dccfbe;
        border-radius: 0;
        color: #2f241c;
    }
    """

    _SECTION_TITLE_QSS = """
    QLabel {
        color: #7a5c47;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 1px;
    }
    """

    def history_item_row(self, text: str) -> QWidget:
        return self._history_item_rows[text]

    def hot_item_ranks(self) -> list[str]:
        return [label.text() for label in self._hot_rank_labels]
```

- [ ] **Step 2: Replace the raw history-row widgets with styled row containers**

```python
def _add_history_item(self, keyword: str) -> None:
    row = QWidget(self._history_items_widget)
    row.setFixedHeight(self.HISTORY_ITEM_HEIGHT)
    row.setStyleSheet(
        "QWidget { background: transparent; }"
        "QWidget:hover { background: #efe2d3; }"
    )

    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(12, 4, 10, 4)
    row_layout.setSpacing(8)

    item_button = QPushButton(keyword, row)
    item_button.setFixedHeight(self.HISTORY_ITEM_HEIGHT - 8)
    item_button.setFlat(True)
    item_button.setStyleSheet(
        "QPushButton { text-align: left; color: #2f241c; font-size: 13px; border: none; }"
    )

    delete_button = QPushButton("删除", row)
    delete_button.setFixedHeight(self.HISTORY_ITEM_HEIGHT - 8)
    delete_button.setFlat(True)
    delete_button.setStyleSheet(
        "QPushButton { color: #a98268; font-size: 12px; border: none; padding: 0 6px; }"
        "QPushButton:hover { color: #8e5f40; }"
    )

    self._history_item_rows[keyword] = row
```

- [ ] **Step 3: Replace simple hot buttons with ranked hot rows**

```python
def _add_hot_item(self, index: int, text: str, query: str) -> None:
    row = QWidget(self._hot_items_widget)
    row.setFixedHeight(self.HOT_ITEM_HEIGHT)
    row.setStyleSheet(
        "QWidget { background: transparent; }"
        "QWidget:hover { background: #f2dfcc; }"
    )

    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(12, 6, 12, 6)
    row_layout.setSpacing(10)

    rank_label = QLabel(f\"{index:02d}\", row)
    rank_label.setStyleSheet("color: #b06b3c; font-weight: 700; font-size: 12px;")

    button = QPushButton(text, row)
    button.setFlat(True)
    button.setStyleSheet(
        "QPushButton { text-align: left; color: #2d2017; font-size: 14px; font-weight: 600; border: none; }"
    )
    button.clicked.connect(lambda checked=False, current_query=query: self._on_item_clicked(current_query))

    row_layout.addWidget(rank_label)
    row_layout.addWidget(button, 1)
    self._hot_rank_labels.append(rank_label)
    self._hot_item_buttons[text] = button
    self._hot_item_texts.append(text)
    self._hot_items_layout.addWidget(row)
```

- [ ] **Step 4: Restyle headers, divider, tabs, and empty states**

```python
separator.setStyleSheet("QFrame { color: #e7d8c8; background: #e7d8c8; min-width: 1px; }")
title.setStyleSheet(self._SECTION_TITLE_QSS)
self.hot_tab_bar.setStyleSheet(
    """
    QTabBar::tab {
        background: transparent;
        color: #866652;
        padding: 8px 12px;
        margin-right: 6px;
        border: none;
    }
    QTabBar::tab:selected {
        background: #ead2bb;
        color: #7f4d2a;
        font-weight: 600;
    }
    """
)
empty_label.setStyleSheet("color: #9a7b63; font-size: 12px;")
```

- [ ] **Step 5: Run targeted popup tests and make them pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup" -q
```

Expected:

```text
8 passed
```

- [ ] **Step 6: Commit the popup visual refresh**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: refresh global search popup visuals"
```

## Task 3: Run Regression Coverage for Search Behavior

**Files:**
- Modify: `src/atv_player/ui/main_window.py` if cleanup is needed
- Modify: `tests/test_main_window_ui.py` if a brittle assertion needs adjustment
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Run the full global-search regression set**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search" tests/test_storage.py -q
```

Expected:

```text
26 passed
```

- [ ] **Step 2: Run a syntax sanity check on touched files**

Run:

```bash
uv run python -m py_compile src/atv_player/ui/main_window.py tests/test_main_window_ui.py
```

Expected:

```text
<no output>
```

- [ ] **Step 3: If any brittle visual assertions fail, make the minimal test-safe cleanup**

```python
# Keep helper-based assertions stable and avoid asserting on full stylesheet text.
assert _popup_history_texts(window) == ["庆余年"]
assert _popup_hot_ranks(window) == ["01", "02"]
```

- [ ] **Step 4: Re-run the regression command after cleanup**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search" tests/test_storage.py -q
```

Expected:

```text
26 passed
```

- [ ] **Step 5: Commit the verified regression-safe finish**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "test: verify global search popup visual refresh"
```

## Self-Review

### Spec coverage

- warm cinema-like palette: covered in Task 2 styling constants and tab/row restyling
- balanced panel layout: covered in Task 2 header/divider/section restyling
- fixed history rows: covered in Task 1 and Task 2
- ranked hot-search presentation: covered in Task 1 and Task 2
- no behavior changes: protected by Task 3 regression run

### Placeholder scan

- no `TODO`, `TBD`, or cross-task “similar to” placeholders remain
- all commands, file paths, and proposed helper names are explicit

### Type consistency

- helper names used consistently:
  - `history_item_row`
  - `hot_item_ranks`
  - `_history_item_rows`
  - `_hot_rank_labels`

