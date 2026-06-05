# Homepage Modes — Phase 4: Classic Mode (经典模式)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Classic (TvBox) home mode: one source shown full-window, its categories as the top tab bar, a source-picker to switch sources, in-source search + filters retained, nav tab bar hidden.

**Architecture:** Classic mode reuses the existing `PosterGridPage` in a new layout mode (`category_layout="tabs"`). A `ClassicHomePage` widget wraps the active source's `PosterGridPage` plus a source-picker combo and a category tab bar. When `apply_home_mode("classic")` is called, `MainWindow` shows this page in `_home_stack`.

**Tech Stack:** Python, PySide6 (Qt), pytest

**Spec:** `docs/superpowers/specs/2026-06-03-homepage-modes-design.md` (Classic section)

**Depends on:** Phase 1 framework (already merged)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/atv_player/ui/classic_home_page.py` | Classic mode page (source picker + category tabs + source PosterGridPage) |
| Modify | `src/atv_player/ui/poster_grid_page.py` | Add `category_layout` param (`"list"` default / `"tabs"`) — hides left list, exposes categories |
| Modify | `src/atv_player/ui/main_window.py` | Create `ClassicHomePage`, wire into `apply_home_mode`, pass source list + controllers |
| Create | `tests/test_classic_home_page.py` | Tests for Classic mode |

---

### Task 1: Add `category_layout="tabs"` option to `PosterGridPage`

**Files:**
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Test: `tests/test_classic_home_page.py`

This adds the ability to hide the left `category_list` and expose categories through a `QTabBar` that `ClassicHomePage` will drive externally.

- [ ] **Step 1: Write the failing test**

Create `tests/test_classic_home_page.py`:

```python
from atv_player.models import DoubanCategory
from atv_player.ui.poster_grid_page import PosterGridPage


class FakeCategoryController:
    def load_categories(self):
        return [
            DoubanCategory(type_id="1", type_name="电影"),
            DoubanCategory(type_id="2", type_name="电视剧"),
            DoubanCategory(type_id="3", type_name="综艺"),
        ]

    def load_items(self, category_id, page, filters=None):
        return [], 0


def test_poster_grid_page_category_layout_tabs_hides_list(qtbot) -> None:
    page = PosterGridPage(FakeCategoryController(), category_layout="tabs")
    qtbot.addWidget(page)

    page.reload_categories()
    assert page.category_list.isHidden()
    assert len(page.categories) == 3
    assert page.categories[0].type_name == "电影"


def test_poster_grid_page_default_category_layout_shows_list(qtbot) -> None:
    page = PosterGridPage(FakeCategoryController())
    qtbot.addWidget(page)

    page.reload_categories()
    assert not page.category_list.isHidden()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classic_home_page.py::test_poster_grid_page_category_layout_tabs_hides_list -xvs 2>&1 | tail -10`
Expected: FAIL — `PosterGridPage.__init__() got an unexpected keyword argument 'category_layout'`

- [ ] **Step 3: Add `category_layout` parameter to `PosterGridPage.__init__`**

In `src/atv_player/ui/poster_grid_page.py`, find the `__init__` method. After the `initial_category_id` parameter (line ~137), add:

```python
        category_layout: str = "list",
```

Store it in the constructor body (after `self._initial_category_id = initial_category_id`):

```python
        self._category_layout = category_layout
```

- [ ] **Step 4: Update `_handle_categories_loaded` to hide list when `category_layout="tabs"`**

In `src/atv_player/ui/poster_grid_page.py`, in `_handle_categories_loaded` (line 348), after `self.categories = list(categories)` and the `category_list.clear()` loop, add at the end of the method (before any early returns):

Find the line `self.category_list.setCurrentRow(target_row)` (line 364). Before it, add:

```python
        if self._category_layout == "tabs":
            self.category_list.setHidden(True)
```

Also, in the `__init__` method, after `self.category_list = QListWidget()` (line ~156), add:

```python
        if self._category_layout == "tabs":
            self.category_list.setHidden(True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_classic_home_page.py -xvs 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 6: Run existing poster grid page tests**

Run: `uv run pytest tests/ -k "poster" -xvs 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/poster_grid_page.py tests/test_classic_home_page.py
git commit -m "feat: add category_layout=tabs option to PosterGridPage"
```

---

### Task 2: Create `ClassicHomePage` widget

**Files:**
- Create: `src/atv_player/ui/classic_home_page.py`
- Test: `tests/test_classic_home_page.py`

This is the composed page for Classic mode: source-picker combo at top, category tab bar below, then the active source's `PosterGridPage` filling the rest.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_classic_home_page.py`:

```python
from PySide6.QtCore import Signal


class FakePluginController:
    def __init__(self, name: str) -> None:
        self.name = name

    def load_categories(self):
        return [
            DoubanCategory(type_id="1", type_name="电影"),
            DoubanCategory(type_id="2", type_name="电视剧"),
        ]

    def load_items(self, category_id, page, filters=None):
        return [], 0


def _make_source_entries():
    from atv_player.ui.classic_home_page import SourceEntry
    return [
        SourceEntry(key="plugin:1", title="源A", controller=FakePluginController("A")),
        SourceEntry(key="plugin:2", title="源B", controller=FakePluginController("B")),
    ]


def test_classic_home_page_shows_source_picker_and_category_tabs(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    assert page.source_combo.count() == 2
    assert page.source_combo.currentData() == "plugin:1"
    assert page.category_tab_bar.count() == 2
    assert page.category_tab_bar.tabText(0) == "电影"
    assert page.category_tab_bar.tabText(1) == "电视剧"


def test_classic_home_page_switches_source(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    assert page.category_tab_bar.tabText(0) == "电影"

    page.source_combo.setCurrentIndex(1)
    assert page.source_combo.currentData() == "plugin:2"
    # Categories reload from source B
    assert page.category_tab_bar.tabText(0) == "电影"


def test_classic_home_page_click_category_emits_signal(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    emitted = []
    page.category_selected.connect(lambda cat_id: emitted.append(cat_id))
    page.category_tab_bar.setCurrentIndex(1)
    assert len(emitted) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classic_home_page.py::test_classic_home_page_shows_source_picker_and_category_tabs -xvs 2>&1 | tail -10`
Expected: FAIL — `ModuleNotFoundError: No module named 'atv_player.ui.classic_home_page'`

- [ ] **Step 3: Create `ClassicHomePage`**

Create `src/atv_player/ui/classic_home_page.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import DoubanCategory
from atv_player.ui.poster_grid_page import PosterGridPage


@dataclass(slots=True)
class SourceEntry:
    key: str
    title: str
    controller: object


class ClassicHomePage(QWidget):
    category_selected = Signal(str)
    source_changed = Signal(str)

    def __init__(
        self,
        source_entries: list[SourceEntry],
        initial_source_key: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_entries = source_entries
        self._current_source_key = initial_source_key
        self._categories: list[DoubanCategory] = []

        # Source picker
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(120)
        for entry in source_entries:
            self.source_combo.addItem(entry.title, entry.key)
        if initial_source_key:
            idx = self.source_combo.findData(initial_source_key)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        self.source_combo.currentIndexChanged.connect(self._handle_source_changed)

        # Category tab bar
        self.category_tab_bar = QTabBar()
        self.category_tab_bar.setDrawBase(False)
        self.category_tab_bar.currentChanged.connect(self._handle_category_changed)

        # Poster grid page (reuses existing component with hidden category list)
        initial_entry = self._current_entry()
        self.grid_page = PosterGridPage(
            initial_entry.controller if initial_entry else FakeEmptyController(),
            click_action="open",
            search_enabled=True,
            category_layout="tabs",
        )

        # Layout
        top_row = QHBoxLayout()
        top_row.addWidget(self.source_combo)
        top_row.addWidget(self.category_tab_bar, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_row)
        layout.addWidget(self.grid_page, 1)

        # Load initial categories
        if initial_entry is not None:
            self._load_categories_from_controller(initial_entry.controller)

    def _current_entry(self) -> SourceEntry | None:
        for entry in self._source_entries:
            if entry.key == self._current_source_key:
                return entry
        return self._source_entries[0] if self._source_entries else None

    def _handle_source_changed(self, index: int) -> None:
        key = self.source_combo.itemData(index)
        if not key or key == self._current_source_key:
            return
        self._current_source_key = key
        entry = self._current_entry()
        if entry is None:
            return
        # Replace the grid page's controller
        self.grid_page = PosterGridPage(
            entry.controller,
            click_action="open",
            search_enabled=True,
            category_layout="tabs",
        )
        # Swap widget in layout
        layout = self.layout()
        old_page = layout.itemAt(layout.count() - 1).widget()
        layout.replaceWidget(old_page, self.grid_page)
        old_page.deleteLater()
        self._load_categories_from_controller(entry.controller)
        self.source_changed.emit(key)

    def _handle_category_changed(self, index: int) -> None:
        if not (0 <= index < len(self._categories)):
            return
        category_id = self._categories[index].type_id
        self.category_selected.emit(category_id)
        self.grid_page.load_items(category_id, 1)

    def _load_categories_from_controller(self, controller) -> None:
        try:
            categories = controller.load_categories()
        except Exception:
            categories = []
        self._categories = list(categories)
        self.category_tab_bar.clear()
        for cat in self._categories:
            self.category_tab_bar.addTab(cat.type_name)
        if self._categories:
            self.category_tab_bar.setCurrentIndex(0)
            self.grid_page.selected_category_id = self._categories[0].type_id
            self.grid_page.load_items(self._categories[0].type_id, 1)

    def current_source_key(self) -> str:
        return self._current_source_key


class FakeEmptyController:
    def load_categories(self):
        return []

    def load_items(self, category_id, page, filters=None):
        return [], 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_classic_home_page.py -xvs 2>&1 | tail -15`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/classic_home_page.py tests/test_classic_home_page.py
git commit -m "feat: add ClassicHomePage with source picker and category tabs"
```

---

### Task 3: Wire Classic mode into `MainWindow.apply_home_mode`

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_home_mode.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_home_mode.py`:

```python
def test_main_window_apply_home_mode_classic_shows_classic_page(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    assert hasattr(window, "_classic_home_page")
    assert window._home_stack.currentWidget() is window._classic_home_page
    assert window.nav_tabs.isHidden()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_home_mode.py::test_main_window_apply_home_mode_classic_shows_classic_page -xvs 2>&1 | tail -10`
Expected: FAIL — `AssertionError` (no `_classic_home_page`)

- [ ] **Step 3: Build plugin source entries helper + wire into `apply_home_mode`**

In `src/atv_player/ui/main_window.py`, add an import at the top (near other `from atv_player.ui.` imports):

```python
from atv_player.ui.classic_home_page import ClassicHomePage, SourceEntry
```

Add a helper method on `MainWindow` (near `apply_home_mode`):

```python
    def _build_plugin_source_entries(self) -> list[SourceEntry]:
        entries: list[SourceEntry] = []
        for definition in self._plugin_tab_definitions:
            key = definition.key
            title = definition.title
            controller = definition.search_controller
            if controller is not None:
                entries.append(SourceEntry(key=key, title=title, controller=controller))
        return entries
```

Update `apply_home_mode` to handle `"classic"`:

```python
        elif normalized == "classic":
            entries = self._build_plugin_source_entries()
            initial_key = entries[0].key if entries else ""
            if not hasattr(self, "_classic_home_page"):
                self._classic_home_page = ClassicHomePage(entries, initial_source_key=initial_key)
                self._classic_home_page.grid_page.item_open_requested.connect(
                    lambda item: self._open_spider_item(
                        self._classic_home_page.grid_page.controller
                        if hasattr(self._classic_home_page.grid_page, "controller")
                        else None,
                        "",
                        item,
                    )
                )
                self._home_stack.addWidget(self._classic_home_page)
            self._home_stack.setCurrentWidget(self._classic_home_page)
            self.nav_tabs.setVisible(False)
            self.global_search_container.setVisible(True)
```

Note: The item_open_requested wiring should match how plugin pages open items. The existing pattern is `_open_spider_item(controller, plugin_id, item)`. The ClassicHomePage's grid_page needs to trigger the same path. Since the grid_page is a `PosterGridPage` with the source's controller, connecting `item_open_requested` to the existing `_handle_plugin_item_open`-style handler is correct.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_home_mode.py -xvs 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 5: Run full core test suite**

Run: `uv run pytest tests/test_home_mode.py tests/test_main_window_ui.py tests/test_classic_home_page.py -xvs 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_home_mode.py
git commit -m "feat: wire Classic mode into MainWindow.apply_home_mode"
```

---

### Task 4: Connect Classic mode item clicks to playback

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_home_mode.py`

The grid page's `item_open_requested` signal needs to trigger the same playback path as Browse mode's plugin pages.

- [ ] **Step 1: Wire item_open_requested to the existing open flow**

In `src/atv_player/ui/main_window.py`, in the `"classic"` branch of `apply_home_mode`, the `item_open_requested` connection should call the same handler that plugin tab pages use. Find the existing plugin open handler:

The plugin pages connect like this (main_window.py ~3859):
```python
page.item_open_requested.connect(
    lambda item, controller=controller, plugin_id=plugin_id: self._open_spider_item(
        controller, plugin_id, item,
    )
)
```

For Classic mode, the grid page's controller is the active source's controller. Store the current entry's plugin_id when switching sources. Update the classic branch:

```python
        elif normalized == "classic":
            entries = self._build_plugin_source_entries()
            initial_key = entries[0].key if entries else ""
            if not hasattr(self, "_classic_home_page"):
                self._classic_home_page = ClassicHomePage(entries, initial_source_key=initial_key)
                self._classic_home_page.grid_page.item_open_requested.connect(self._handle_classic_item_open)
                self._home_stack.addWidget(self._classic_home_page)
            self._home_stack.setCurrentWidget(self._classic_home_page)
            self.nav_tabs.setVisible(False)
            self.global_search_container.setVisible(True)
```

Add the handler method:

```python
    def _handle_classic_item_open(self, item) -> None:
        if not hasattr(self, "_classic_home_page"):
            return
        source_key = self._classic_home_page.current_source_key()
        entry = next(
            (e for e in self._build_plugin_source_entries() if e.key == source_key),
            None,
        )
        if entry is None:
            return
        controller = entry.controller
        plugin_id = source_key.replace("plugin:", "", 1) if source_key.startswith("plugin:") else ""
        self._open_spider_item(controller, plugin_id, item)
```

- [ ] **Step 2: Run all home mode tests**

Run: `uv run pytest tests/test_home_mode.py tests/test_classic_home_page.py -xvs 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/atv_player/ui/main_window.py
git commit -m "feat: connect Classic mode item clicks to playback"
```

---

### Task 5: Persist and restore Classic mode source selection

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_home_mode.py`

The source picker defaults to `last_selected_tab` when it's a plugin key, or the first available source.

- [ ] **Step 1: Use `last_selected_tab` config to restore source**

In the classic branch of `apply_home_mode`, before creating `ClassicHomePage`, check if `self.config.last_selected_tab` is a plugin key and use it as `initial_source_key`:

Change the `initial_key` logic:

```python
            initial_key = ""
            saved_tab = getattr(self.config, "last_selected_tab", "") or ""
            if saved_tab.startswith("plugin:"):
                matching = [e for e in entries if e.key == saved_tab]
                if matching:
                    initial_key = saved_tab
            if not initial_key:
                initial_key = entries[0].key if entries else ""
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_home_mode.py tests/test_classic_home_page.py -xvs 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/atv_player/ui/main_window.py
git commit -m "feat: persist and restore Classic mode source selection"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run core test suite**

Run: `uv run pytest tests/test_home_mode.py tests/test_classic_home_page.py tests/test_main_window_ui.py tests/test_storage.py -xvs 2>&1 | tail -15`
Expected: ALL PASS

- [ ] **Step 2: Manual verification — launch app**

Run: `uv run python -m atv_player`
1. Open 高级设置 → switch 首页模式 to "经典 (TvBox)" → save
2. Should see: source-picker combo + category tabs (电影/电视剧/…) + poster grid + in-source search + filters
3. Header global search box stays visible
4. Nav tab bar is hidden
5. Click a poster → player opens
6. Switch source via picker → categories reload
7. Switch back to 浏览 mode → all tabs restored

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: Classic mode verification fixes"
```
