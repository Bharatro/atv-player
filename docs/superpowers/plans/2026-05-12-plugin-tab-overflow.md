# Plugin Tab Overflow Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the current top-tab navigation for plugins, but when plugin tabs overflow the available width, show only the visible subset in the top bar and move the rest into a searchable right-side “更多” drawer without recreating plugin page instances.

**Architecture:** Refactor main-window navigation so the tab strip and page content are no longer coupled to `QTabWidget`. Replace the existing `QTabWidget`-centric model with a lightweight navigation layer built from `QTabBar` plus `QStackedWidget`, then add overflow allocation logic, a “更多” button, and a right-side drawer that lists only hidden plugin tabs. This separation is required because a hidden plugin must still be able to become the active content page while remaining absent from the visible top tab strip.

**Tech Stack:** Python 3.13, PySide6, pytest-qt, existing `PosterGridPage`-based plugin pages, current `MainWindow` navigation/state persistence

---

## File Structure

- Modify: `src/atv_player/ui/main_window.py`
  Refactor top navigation away from `QTabWidget`, introduce visible/hidden plugin tab allocation, “更多” button state, drawer opening/closing, search filtering, resize-driven recomputation, and content-page switching via a stacked widget.
- Create: `src/atv_player/ui/plugin_tab_drawer.py`
  Add a focused drawer widget with search box, list rendering, active-item highlighting, and a signal/callback for plugin selection.
- Modify: `tests/test_main_window_ui.py`
  Add coverage for overflow allocation, more-button visibility/count text, drawer search/filtering, hidden-plugin activation, and the “no page recreation on resize” constraint.

## Task 1: Lock The Overflow Allocation Behavior With Failing Main Window Tests

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing tests for visible vs. hidden plugin allocation**

Add these helper classes near the top of `tests/test_main_window_ui.py` after `FakePluginManager`:

```python
class WidthAwarePluginManager(FakePluginManager):
    pass


class CountingSpiderController(FakeSpiderController):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.load_calls = 0

    def load_categories(self):
        self.load_calls += 1
        return []
```

Add these tests near the existing plugin-tab tests:

```python
def test_main_window_hides_overflow_plugin_tabs_behind_more_button(qtbot, monkeypatch) -> None:
    controllers = [FakeSpiderController(f"插件{i}") for i in range(1, 6)]
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 220)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()

    assert [window.nav_tab_bar.tabText(i) for i in range(window.nav_tab_bar.count())] == [
        "豆瓣电影",
        "电报影视",
        "网络直播",
        "Emby",
        "Jellyfin",
        "插件1",
        "插件2",
        "文件浏览",
        "播放记录",
    ]
    assert window.plugin_overflow_button.isVisible() is True
    assert window.plugin_overflow_button.text() == "更多(3)"
    assert [definition.title for definition in window._hidden_plugin_tab_definitions] == ["插件3", "插件4", "插件5"]


def test_main_window_hides_more_button_when_all_plugin_tabs_fit(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "插件1", "controller": FakeSpiderController("插件1"), "search_enabled": True},
            {"id": "plugin-2", "title": "插件2", "controller": FakeSpiderController("插件2"), "search_enabled": True},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 600)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()

    assert window.plugin_overflow_button.isVisible() is False
    assert window._hidden_plugin_tab_definitions == []
```

- [ ] **Step 2: Run the targeted overflow tests to verify the capability is missing**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "overflow_plugin_tabs or all_plugin_tabs_fit" -q
```

Expected: FAIL because `MainWindow` does not yet expose separate navigation controls, overflow state, or width helpers.

- [ ] **Step 3: Commit the red test state**

Run:

```bash
git add tests/test_main_window_ui.py
git commit -m "test: cover plugin tab overflow allocation"
```

## Task 2: Decouple Navigation From QTabWidget And Add Overflow State

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Replace `QTabWidget`-centric navigation with `QTabBar` + `QStackedWidget`**

In `src/atv_player/ui/main_window.py`, update imports to include:

```python
from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal, QSize
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)
```

Replace the single `self.nav_tabs = QTabWidget()` field with:

```python
        self.nav_tab_bar = QTabBar()
        self.nav_tab_bar.setExpanding(False)
        self.nav_tab_bar.setMovable(False)
        self.nav_tab_bar.setDocumentMode(True)
        self.content_stack = QStackedWidget()
        self.plugin_overflow_button = QPushButton("更多")
        self.plugin_overflow_button.hide()
        self._visible_navigation_definitions: list[_TabDefinition] = []
        self._hidden_plugin_tab_definitions: list[_TabDefinition] = []
        self._active_widget: QWidget | None = None
```

In the layout section, replace the old `nav_tabs` placement with:

```python
        self.nav_row = QHBoxLayout()
        self.nav_row.setContentsMargins(0, 0, 0, 0)
        self.nav_row.setSpacing(8)
        self.nav_row.addWidget(self.nav_tab_bar, 1)
        self.nav_row.addWidget(self.plugin_overflow_button, 0)
        container_layout.addLayout(self.nav_row)
        container_layout.addWidget(self.content_stack)
```

- [ ] **Step 2: Add width helpers and visible/hidden plugin allocation**

In `MainWindow`, add these helpers:

```python
    def _plugin_tab_title_width(self, title: str) -> int:
        metrics = self.nav_tab_bar.fontMetrics()
        return metrics.horizontalAdvance(title) + 36

    def _plugin_overflow_button_width(self) -> int:
        return max(self.plugin_overflow_button.sizeHint().width(), 84)

    def _available_plugin_tab_width(self) -> int:
        return max(self.nav_tab_bar.width() - self._non_plugin_tab_width(), 0)

    def _non_plugin_tab_width(self) -> int:
        width = 0
        for definition in [*self._static_tab_definitions, *self._trailing_tab_definitions]:
            width += self._plugin_tab_title_width(definition.title)
        return width

    def _split_visible_and_hidden_plugin_tabs(self) -> tuple[list[_TabDefinition], list[_TabDefinition]]:
        available = self._available_plugin_tab_width()
        if not self._plugin_tab_definitions:
            return [], []
        visible: list[_TabDefinition] = []
        hidden: list[_TabDefinition] = []
        used = 0
        overflow_width = self._plugin_overflow_button_width()
        for index, definition in enumerate(self._plugin_tab_definitions):
            width = self._plugin_tab_title_width(definition.title)
            remaining = self._plugin_tab_definitions[index + 1 :]
            reserve = overflow_width if remaining else 0
            if used + width + reserve <= available:
                visible.append(definition)
                used += width
            else:
                hidden.append(definition)
        return visible, hidden
```

- [ ] **Step 3: Build a new `_refresh_navigation_tabs()` path and keep current page stable**

Replace `_refresh_visible_tabs()` with a navigation refresh that updates the tab bar and content stack separately:

```python
    def _refresh_navigation_tabs(self) -> None:
        current_widget = self._active_widget or self.content_stack.currentWidget()
        if self._global_search_active:
            definitions = [definition for definition in self._all_tab_definitions() if definition.key in self._global_search_results]
            self._hidden_plugin_tab_definitions = []
            self.plugin_overflow_button.hide()
        else:
            visible_plugins, hidden_plugins = self._split_visible_and_hidden_plugin_tabs()
            self._hidden_plugin_tab_definitions = hidden_plugins
            self.plugin_overflow_button.setVisible(bool(hidden_plugins))
            self.plugin_overflow_button.setText(f"更多({len(hidden_plugins)})" if hidden_plugins else "更多")
            definitions = [*self._static_tab_definitions, *visible_plugins, *self._trailing_tab_definitions]
        self._visible_navigation_definitions = definitions
        self._rebuild_nav_tab_bar(definitions)
        self._sync_content_stack(definitions)
        self._restore_active_widget(current_widget, definitions)
```

Add helper shells:

```python
    def _rebuild_nav_tab_bar(self, definitions: list[_TabDefinition]) -> None: ...
    def _sync_content_stack(self, definitions: list[_TabDefinition]) -> None: ...
    def _restore_active_widget(self, current_widget: QWidget | None, definitions: list[_TabDefinition]) -> None: ...
```

Use `_active_widget` to preserve the selected page even if it is currently hidden from the top bar.

- [ ] **Step 4: Run the targeted overflow allocation tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "overflow_plugin_tabs or all_plugin_tabs_fit" -q
```

Expected: PASS

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: add plugin tab overflow allocation"
```

## Task 3: Add The Right-Side Drawer And Hidden Plugin Search

**Files:**
- Create: `src/atv_player/ui/plugin_tab_drawer.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing drawer interaction tests**

Add these tests to `tests/test_main_window_ui.py` below the overflow tests:

```python
def test_main_window_plugin_overflow_drawer_filters_hidden_plugins(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "短剧一号", "controller": FakeSpiderController("短剧一号"), "search_enabled": True},
            {"id": "plugin-2", "title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": True},
            {"id": "plugin-3", "title": "音乐插件", "controller": FakeSpiderController("音乐插件"), "search_enabled": True},
        ],
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()

    assert [item.text() for item in window._plugin_overflow_drawer.visible_items()] == ["短剧二号", "音乐插件"]

    window._plugin_overflow_drawer.search_edit.setText("音乐")

    assert [item.text() for item in window._plugin_overflow_drawer.visible_items()] == ["音乐插件"]


def test_main_window_selecting_hidden_plugin_from_drawer_switches_content_without_rebuilding_pages(qtbot, monkeypatch) -> None:
    controllers = [CountingSpiderController(f"插件{i}") for i in range(1, 4)]
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    original_pages = [page for page, _controller, _plugin_id in window._plugin_pages]
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()

    window._plugin_overflow_drawer.select_plugin_by_title("插件3")

    assert window._active_widget is original_pages[2]
    assert window._plugin_pages[2][0] is original_pages[2]
    assert controllers[2].load_calls <= 1
```

- [ ] **Step 2: Run the targeted drawer tests to verify the UI does not exist yet**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "plugin_overflow_drawer" -q
```

Expected: FAIL because there is no overflow drawer widget, search box, or hidden-plugin activation path.

- [ ] **Step 3: Create the focused drawer widget**

Create `src/atv_player/ui/plugin_tab_drawer.py` with a widget like:

```python
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class PluginTabDrawer(QWidget):
    plugin_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.SubWindow)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索隐藏插件")
        self.empty_label = QLabel("没有匹配的插件", self)
        self.list_widget = QListWidget(self)
        self._items: list[tuple[str, str, bool]] = []
        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.list_widget)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.list_widget.itemActivated.connect(lambda item: self.plugin_selected.emit(str(item.data(Qt.ItemDataRole.UserRole))))

    def set_plugins(self, items: list[tuple[str, str, bool]]) -> None:
        self._items = list(items)
        self._apply_filter()

    def _apply_filter(self) -> None:
        keyword = self.search_edit.text().strip().lower()
        self.list_widget.clear()
        for key, title, active in self._items:
            if keyword and keyword not in title.lower():
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            if active:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list_widget.addItem(item)
        self.empty_label.setVisible(self.list_widget.count() == 0)
```

- [ ] **Step 4: Integrate the drawer into `MainWindow`**

In `src/atv_player/ui/main_window.py`:

```python
from atv_player.ui.plugin_tab_drawer import PluginTabDrawer
```

Add fields in `__init__`:

```python
        self._plugin_overflow_drawer = PluginTabDrawer(self)
        self._plugin_overflow_drawer.hide()
        self._plugin_overflow_drawer.plugin_selected.connect(self._select_hidden_plugin_tab)
```

Add helpers:

```python
    def _open_plugin_overflow_drawer(self) -> None: ...
    def _close_plugin_overflow_drawer(self) -> None: ...
    def _toggle_plugin_overflow_drawer(self) -> None: ...
    def _hidden_plugin_drawer_items(self) -> list[tuple[str, str, bool]]: ...
    def _select_hidden_plugin_tab(self, tab_key: str) -> None: ...
```

Wire the button:

```python
        self.plugin_overflow_button.clicked.connect(self._toggle_plugin_overflow_drawer)
```

When selecting a hidden plugin, set `self._active_widget`, switch `self.content_stack`, close the drawer, and call the existing page-load path for that widget.

- [ ] **Step 5: Run the targeted drawer tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "plugin_overflow_drawer" -q
```

Expected: PASS

- [ ] **Step 6: Commit**

Run:

```bash
git add src/atv_player/ui/main_window.py src/atv_player/ui/plugin_tab_drawer.py tests/test_main_window_ui.py
git commit -m "feat: add plugin overflow drawer"
```

## Task 4: Preserve Existing Main Window Behaviors While Using The New Navigation Layer

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing regression tests for tab persistence and resize stability**

Add these tests:

```python
def test_main_window_resize_recomputes_plugin_overflow_without_recreating_pages(qtbot, monkeypatch) -> None:
    controllers = [FakeSpiderController(f"插件{i}") for i in range(1, 5)]
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    pages_before = []
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)
    widths = iter([120, 400])
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: next(widths))

    window.show()
    pages_before = [page for page, _controller, _plugin_id in window._plugin_pages]
    window._refresh_navigation_tabs()
    hidden_before = [definition.title for definition in window._hidden_plugin_tab_definitions]
    window._refresh_navigation_tabs()
    hidden_after = [definition.title for definition in window._hidden_plugin_tab_definitions]

    assert hidden_before != hidden_after
    assert [page for page, _controller, _plugin_id in window._plugin_pages] == pages_before


def test_main_window_hidden_active_plugin_is_highlighted_in_overflow_drawer(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "插件1", "controller": FakeSpiderController("插件1"), "search_enabled": True},
            {"id": "plugin-2", "title": "插件2", "controller": FakeSpiderController("插件2"), "search_enabled": True},
            {"id": "plugin-3", "title": "插件3", "controller": FakeSpiderController("插件3"), "search_enabled": True},
        ],
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()
    window._select_hidden_plugin_tab("plugin:plugin-3")
    window._open_plugin_overflow_drawer()

    active_titles = [item.text() for item in window._plugin_overflow_drawer.visible_items() if item.font().bold()]
    assert active_titles == ["插件3"]
```

- [ ] **Step 2: Run the targeted regression tests to verify gaps**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "resize_recomputes_plugin_overflow or hidden_active_plugin_is_highlighted" -q
```

Expected: FAIL until resize recomputation, active-widget persistence, and drawer highlighting are complete.

- [ ] **Step 3: Finish integration with existing state and load behavior**

Complete these integration points in `MainWindow`:

- convert `_handle_tab_changed()` to read from `self._active_widget` / `self.content_stack.currentWidget()`
- keep `_remember_selected_tab()` semantics by mapping the current widget back to `_all_tab_definitions()`
- on resize, schedule `_refresh_navigation_tabs()` only when not in global search mode
- keep `_global_search_active` behavior by bypassing plugin overflow and showing only search-result tabs
- keep `_rebuild_spider_plugin_tabs()` creating plugin pages only when plugin definitions structurally change

Add a resize hook:

```python
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._global_search_active:
            self._refresh_navigation_tabs()
```

- [ ] **Step 4: Run the full main window UI test file**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/ui/main_window.py src/atv_player/ui/plugin_tab_drawer.py tests/test_main_window_ui.py
git commit -m "feat: optimize plugin tab overflow navigation"
```

## Task 5: Final Verification

**Files:**
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_app.py`
- Test: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Run the focused navigation and plugin-management regression suite**

Run:

```bash
uv run pytest tests/test_main_window_ui.py tests/test_app.py -k "plugin_manager or plugin or tab" tests/test_plugin_manager_dialog.py -q
```

Expected: PASS

- [ ] **Step 2: Run a broader UI regression pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py tests/test_plugin_manager_dialog.py tests/test_app.py -q
```

Expected: PASS

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff --stat HEAD~3..HEAD
```

Expected: only the planned main-window navigation, drawer widget, and test files are changed.

## Self-Review

- Spec coverage: the plan covers top-tab preservation, overflow allocation, “更多” drawer, hidden-plugin search, active hidden-plugin navigation, and the “do not recreate page instances on layout change” constraint.
- Placeholder scan: no `TODO`, `TBD`, or vague “handle appropriately” steps remain; each code-changing step points to concrete files and helper names.
- Type consistency: the plan consistently uses `_TabDefinition` for navigation, `plugin:...` keys for plugin pages, and a dedicated `PluginTabDrawer` widget for hidden-plugin search/navigation rather than mixing drawer state into unrelated widgets.
