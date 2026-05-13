# Plugin Tab Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a right-click context menu to visible plugin tabs and hidden overflow-drawer plugin items so users can reload, rename, reconfigure, and enable or disable a spider plugin directly from the main window.

**Architecture:** Keep plugin management capabilities in one place by extracting the existing rename/config/toggle/reload flows from `PluginManagerDialog` into a shared UI helper. Let `MainWindow` invoke that helper from visible-tab and drawer-item context menus, then reuse `MainWindow._reload_changed_plugin_tabs(...)` to rebuild only the affected plugin tab state and refresh overflow visibility.

**Tech Stack:** Python 3.13, PySide6, pytest, pytest-qt, existing `MainWindow`, `PluginManagerDialog`, `PluginTabDrawer`, and spider-plugin manager interfaces

---

## File Structure

- Create: `src/atv_player/ui/plugin_actions.py`
  Add a focused helper for plugin rename/config/toggle/reload flows, including prompt handling, warning dialogs, and a structured result describing whether a plugin changed.
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  Replace duplicated rename/config/toggle/reload prompt-and-dispatch logic with calls into the shared helper while keeping the dialog's current table behavior intact.
- Modify: `src/atv_player/ui/plugin_tab_drawer.py`
  Add item-level context menu support and emit a signal with the target plugin key when the user right-clicks a hidden plugin entry.
- Modify: `src/atv_player/ui/main_window.py`
  Add context-menu handling for visible plugin tabs and hidden drawer items, use the shared helper to execute plugin actions, and refresh changed plugin tabs by id while keeping overflow state synchronized.
- Modify: `tests/test_main_window_ui.py`
  Extend the main-window fixtures so fake plugin managers can simulate plugin state changes, then add tests for visible-tab context menus, hidden-drawer context menus, active-tab fallback, and overflow refresh behavior.
- Create: `tests/test_plugin_actions.py`
  Add focused unit tests for the shared helper's cancel paths, manager dispatch, and warning dialog handling.

## Task 1: Lock The Shared Plugin Action Contract With Failing Helper Tests

**Files:**
- Create: `tests/test_plugin_actions.py`
- Test: `tests/test_plugin_actions.py`

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_plugin_actions.py` with:

```python
from types import SimpleNamespace

from atv_player.ui.plugin_actions import PluginActionResult, PluginActions
import atv_player.ui.plugin_actions as plugin_actions_module


class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SimpleNamespace(id=1, display_name="插件一", enabled=True, config_text="token=1\n"),
            SimpleNamespace(id=2, display_name="插件二", enabled=False, config_text="token=2\n"),
        ]
        self.rename_calls: list[tuple[int, str]] = []
        self.config_calls: list[tuple[int, str]] = []
        self.toggle_calls: list[tuple[int, bool]] = []
        self.refresh_calls: list[int] = []

    def list_plugins(self):
        return list(self.plugins)

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        self.rename_calls.append((plugin_id, display_name))

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        self.config_calls.append((plugin_id, config_text))

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        self.toggle_calls.append((plugin_id, enabled))

    def refresh_plugin(self, plugin_id: int) -> None:
        self.refresh_calls.append(plugin_id)


def test_plugin_actions_rename_returns_changed_result_for_trimmed_name(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_display_name", lambda parent, current: "  新名称  ")

    result = actions.rename_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.rename_calls == [(1, "新名称")]


def test_plugin_actions_rename_returns_unchanged_when_prompt_is_empty(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_display_name", lambda parent, current: "")

    result = actions.rename_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=False, plugin_id=None)
    assert manager.rename_calls == []


def test_plugin_actions_edit_config_returns_changed_result(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_config_text", lambda parent, current: "cookie=1\n")

    result = actions.edit_plugin_config(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.config_calls == [(1, "cookie=1\n")]


def test_plugin_actions_toggle_uses_inverse_enabled_state() -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)

    result = actions.toggle_plugin_enabled(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.toggle_calls == [(1, False)]


def test_plugin_actions_refresh_returns_changed_result() -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)

    result = actions.refresh_plugin(parent=None, plugin_id=2)

    assert result == PluginActionResult(changed=True, plugin_id=2)
    assert manager.refresh_calls == [2]


def test_plugin_actions_shows_warning_and_returns_unchanged_on_manager_error(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    warning_messages: list[str] = []

    def raise_refresh(plugin_id: int) -> None:
        raise RuntimeError("boom")

    manager.refresh_plugin = raise_refresh
    monkeypatch.setattr(
        plugin_actions_module.QMessageBox,
        "warning",
        lambda parent, title, message: warning_messages.append(message),
    )

    result = actions.refresh_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=False, plugin_id=None)
    assert warning_messages == ["boom"]
```

- [ ] **Step 2: Run the helper tests to verify the shared module does not exist yet**

Run:

```bash
uv run pytest tests/test_plugin_actions.py -q
```

Expected: FAIL with `ModuleNotFoundError` or import errors because `atv_player.ui.plugin_actions` has not been created.

- [ ] **Step 3: Commit the red helper tests**

Run:

```bash
git add tests/test_plugin_actions.py
git commit -m "test: cover shared plugin actions"
```

## Task 2: Implement The Shared Plugin Action Helper And Reuse It In The Plugin Manager Dialog

**Files:**
- Create: `src/atv_player/ui/plugin_actions.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Test: `tests/test_plugin_actions.py`

- [ ] **Step 1: Create the shared helper module**

Create `src/atv_player/ui/plugin_actions.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QInputDialog, QMessageBox


@dataclass(slots=True, frozen=True)
class PluginActionResult:
    changed: bool
    plugin_id: int | None = None


class PluginActions:
    def __init__(self, plugin_manager) -> None:
        self.plugin_manager = plugin_manager

    def list_plugins(self):
        return list(self.plugin_manager.list_plugins())

    def get_plugin(self, plugin_id: int):
        return next((plugin for plugin in self.list_plugins() if int(plugin.id) == int(plugin_id)), None)

    def prompt_display_name(self, parent, current: str) -> str:
        value, accepted = QInputDialog.getText(parent, "编辑名称", "显示名称", text=current)
        return value.strip() if accepted else ""

    def prompt_config_text(self, parent, current: str) -> str | None:
        value, accepted = QInputDialog.getMultiLineText(parent, "编辑配置", "配置文本", current)
        return value if accepted else None

    def _warning(self, parent, title: str, exc: Exception) -> PluginActionResult:
        QMessageBox.warning(parent, title, str(exc))
        return PluginActionResult(changed=False, plugin_id=None)

    def refresh_plugin(self, parent, plugin_id: int) -> PluginActionResult:
        try:
            self.plugin_manager.refresh_plugin(plugin_id)
        except Exception as exc:
            return self._warning(parent, "刷新失败", exc)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def rename_plugin(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        display_name = self.prompt_display_name(parent, plugin.display_name or "")
        if not display_name:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            self.plugin_manager.rename_plugin(plugin_id, display_name)
        except Exception as exc:
            return self._warning(parent, "编辑名称失败", exc)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def edit_plugin_config(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        config_text = self.prompt_config_text(parent, plugin.config_text)
        if config_text is None:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            self.plugin_manager.set_plugin_config(plugin_id, config_text)
        except Exception as exc:
            return self._warning(parent, "编辑配置失败", exc)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def toggle_plugin_enabled(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            self.plugin_manager.set_plugin_enabled(plugin_id, not bool(plugin.enabled))
        except Exception as exc:
            return self._warning(parent, "更新插件状态失败", exc)
        return PluginActionResult(changed=True, plugin_id=plugin_id)
```

- [ ] **Step 2: Run the helper tests to verify the new module passes**

Run:

```bash
uv run pytest tests/test_plugin_actions.py -q
```

Expected: PASS with `6 passed`.

- [ ] **Step 3: Replace dialog-local prompt logic with the shared helper**

In `src/atv_player/ui/plugin_manager_dialog.py`, add this import:

```python
from atv_player.ui.plugin_actions import PluginActions
```

In `PluginManagerDialog.__init__`, add:

```python
        self.plugin_actions = PluginActions(plugin_manager)
```

Replace the local prompt methods and action bodies with:

```python
    def _rename_selected(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        result = self.plugin_actions.rename_plugin(self, plugin_id)
        if not result.changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _edit_selected_config(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        result = self.plugin_actions.edit_plugin_config(self, plugin_id)
        if not result.changed:
            return
        self.reload_plugins()

    def _toggle_selected_enabled(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        result = self.plugin_actions.toggle_plugin_enabled(self, plugin_id)
        if not result.changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _refresh_selected(self) -> None:
        if self._refresh_in_progress:
            return
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        self._refresh_in_progress = True
        self._sync_action_state()

        def run() -> None:
            result = self.plugin_actions.refresh_plugin(self, plugin_id)
            if not result.changed:
                self._refresh_signals.failed.emit("")
                return
            self._refresh_signals.completed.emit()
```
```

Then update `_handle_refresh_failed` so it only shows a warning when `message` is non-empty:

```python
    def _handle_refresh_failed(self, message: str) -> None:
        self._refresh_in_progress = False
        self.reload_plugins()
        if message:
            QMessageBox.warning(self, "刷新失败", message)
```

- [ ] **Step 4: Run the helper and plugin-manager dialog tests**

Run:

```bash
uv run pytest tests/test_plugin_actions.py tests/test_plugin_manager_dialog.py -q
```

Expected: PASS, confirming the shared helper preserves existing dialog behavior.

- [ ] **Step 5: Commit the shared helper integration**

Run:

```bash
git add src/atv_player/ui/plugin_actions.py src/atv_player/ui/plugin_manager_dialog.py tests/test_plugin_actions.py
git commit -m "refactor: share plugin action flows"
```

## Task 3: Lock Main Window Context Menu Behavior With Failing UI Tests

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Extend the fake plugin manager used by main-window tests**

In `tests/test_main_window_ui.py`, replace the current `FakePluginManager` and `WidthAwarePluginManager` with:

```python
from types import SimpleNamespace
```

```python
class FakePluginManager:
    def __init__(self) -> None:
        self.dialog_opened = 0
        self.plugins = [
            SimpleNamespace(id=1, display_name="插件1", enabled=True, config_text="token=1\n", sort_order=0),
            SimpleNamespace(id=2, display_name="插件2", enabled=True, config_text="token=2\n", sort_order=1),
            SimpleNamespace(id=3, display_name="插件3", enabled=True, config_text="token=3\n", sort_order=2),
        ]
        self.rename_calls: list[tuple[int, str]] = []
        self.config_calls: list[tuple[int, str]] = []
        self.toggle_calls: list[tuple[int, bool]] = []
        self.refresh_calls: list[int] = []
        self.load_plugins_calls: list[list[str]] = []

    def list_plugins(self):
        return list(self.plugins)

    def load_plugins(self, plugin_ids, drive_detail_loader=None, offline_download_detail_loader=None):
        requested = {str(plugin_id) for plugin_id in plugin_ids}
        self.load_plugins_calls.append(sorted(requested))
        definitions = []
        for plugin in self.plugins:
            if not plugin.enabled or str(plugin.id) not in requested:
                continue
            definitions.append(
                {
                    "id": str(plugin.id),
                    "title": plugin.display_name,
                    "controller": FakeSpiderController(plugin.display_name),
                    "search_enabled": True,
                }
            )
        return definitions

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        self.rename_calls.append((plugin_id, display_name))
        for plugin in self.plugins:
            if plugin.id == plugin_id:
                plugin.display_name = display_name
                return

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        self.config_calls.append((plugin_id, config_text))
        for plugin in self.plugins:
            if plugin.id == plugin_id:
                plugin.config_text = config_text
                return

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        self.toggle_calls.append((plugin_id, enabled))
        for plugin in self.plugins:
            if plugin.id == plugin_id:
                plugin.enabled = enabled
                return

    def refresh_plugin(self, plugin_id: int) -> None:
        self.refresh_calls.append(plugin_id)
```

Keep:

```python
class WidthAwarePluginManager(FakePluginManager):
    pass
```

- [ ] **Step 2: Add failing visible-tab and hidden-drawer context-menu tests**

Add these tests near the existing overflow tests in `tests/test_main_window_ui.py`:

```python
def test_main_window_plugin_tab_context_menu_reload_refreshes_changed_plugin(qtbot, monkeypatch) -> None:
    manager = WidthAwarePluginManager()
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
        spider_plugins=manager.load_plugins(["1", "2", "3"]),
        plugin_manager=manager,
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 600)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)
    window.show()
    window._refresh_navigation_tabs()

    result = window._run_plugin_context_action("refresh", "1")

    assert result is True
    assert manager.refresh_calls == [1]
    assert manager.load_plugins_calls[-1] == ["1"]
    assert "插件1" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]


def test_main_window_hidden_plugin_context_menu_rename_updates_drawer_items(qtbot, monkeypatch) -> None:
    manager = WidthAwarePluginManager()
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
        spider_plugins=manager.load_plugins(["1", "2", "3"]),
        plugin_manager=manager,
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)
    monkeypatch.setattr(window._plugin_actions, "prompt_display_name", lambda parent, current: "重命名插件")

    window.show()
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()

    result = window._run_plugin_context_action("rename", "2")

    assert result is True
    assert manager.rename_calls == [(2, "重命名插件")]
    assert [item.text() for item in window._plugin_overflow_drawer.visible_items()] == ["重命名插件", "插件3"]


def test_main_window_disabling_active_plugin_falls_back_to_first_visible_tab(qtbot, monkeypatch) -> None:
    manager = WidthAwarePluginManager()
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
        spider_plugins=manager.load_plugins(["1", "2", "3"]),
        plugin_manager=manager,
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 600)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)
    window.show()
    window._refresh_navigation_tabs()
    window.nav_tabs.setCurrentWidget(window._plugin_pages[1][0])

    result = window._run_plugin_context_action("toggle_enabled", "2")

    assert result is True
    assert manager.toggle_calls == [(2, False)]
    assert window.nav_tabs.currentWidget() is window.douban_page
```

- [ ] **Step 3: Run the targeted main-window tests to verify the capability is still missing**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "plugin_tab_context_menu_reload or hidden_plugin_context_menu_rename or disabling_active_plugin_falls_back" -q
```

Expected: FAIL because `MainWindow` does not yet expose shared plugin actions, context-menu dispatch, or drawer item right-click handling.

- [ ] **Step 4: Commit the red main-window tests**

Run:

```bash
git add tests/test_main_window_ui.py
git commit -m "test: cover plugin tab context menus"
```

## Task 4: Add Drawer And Main Window Context Menu Support

**Files:**
- Modify: `src/atv_player/ui/plugin_tab_drawer.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add a context-menu signal to the overflow drawer**

In `src/atv_player/ui/plugin_tab_drawer.py`, update the imports to include `QPoint` and add a new signal:

```python
from PySide6.QtCore import Qt, Signal, QSize, QPoint
```

```python
    plugin_context_requested = Signal(str, QPoint)
```

In `__init__`, configure the list widget for custom context menus:

```python
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._handle_context_menu_requested)
```

Add:

```python
    def _handle_context_menu_requested(self, pos: QPoint) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        plugin_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(plugin_key, str) and plugin_key:
            self.plugin_context_requested.emit(plugin_key, self.list_widget.viewport().mapToGlobal(pos))
```

- [ ] **Step 2: Add plugin-action and context-menu helpers to the main window**

In `src/atv_player/ui/main_window.py`, update imports:

```python
from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal, QSize, QPoint
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QShortcut, QIcon, QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)
from atv_player.ui.plugin_actions import PluginActions
```

In `MainWindow.__init__`, add:

```python
        self._plugin_actions = PluginActions(plugin_manager) if plugin_manager is not None else None
        self.nav_tabs.tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.nav_tabs.tab_bar.customContextMenuRequested.connect(self._handle_plugin_tab_context_menu_requested)
```

Also connect the drawer signal:

```python
        self._plugin_overflow_drawer.plugin_context_requested.connect(self._open_plugin_context_menu)
```

Add these helpers:

```python
    def _plugin_definition_by_id(self, plugin_id: str) -> _TabDefinition | None:
        return next((definition for definition in self._plugin_tab_definitions if definition.key == f"plugin:{plugin_id}"), None)

    def _plugin_row_by_id(self, plugin_id: str):
        if self._plugin_manager is None:
            return None
        for plugin in self._plugin_manager.list_plugins():
            if str(plugin.id) == str(plugin_id):
                return plugin
        return None

    def _plugin_id_for_visible_tab_index(self, index: int) -> str | None:
        definition = self.nav_tabs.widget(index)
        if definition is None:
            return None
        tab_key = self._tab_key_for_widget(definition)
        if tab_key is None or not tab_key.startswith("plugin:"):
            return None
        return tab_key.removeprefix("plugin:")

    def _handle_plugin_tab_context_menu_requested(self, pos: QPoint) -> None:
        index = self.nav_tabs.tab_bar.tabAt(pos)
        if index < 0:
            return
        plugin_id = self._plugin_id_for_visible_tab_index(index)
        if not plugin_id:
            return
        self._open_plugin_context_menu(plugin_id, self.nav_tabs.tab_bar.mapToGlobal(pos))

    def _plugin_toggle_action_text(self, plugin_id: str) -> str:
        plugin = self._plugin_row_by_id(plugin_id)
        if plugin is None:
            return "启用"
        return "禁用" if bool(plugin.enabled) else "启用"
```

- [ ] **Step 3: Implement context-menu dispatch and changed-plugin refresh**

Add these methods to `MainWindow`:

```python
    def _open_plugin_context_menu(self, plugin_id: str, global_pos: QPoint) -> None:
        if self._plugin_actions is None:
            return
        menu = QMenu(self)
        reload_action = menu.addAction("重新加载")
        rename_action = menu.addAction("编辑名称")
        config_action = menu.addAction("编辑配置")
        toggle_action = menu.addAction(self._plugin_toggle_action_text(plugin_id))
        chosen = menu.exec(global_pos)
        if chosen is reload_action:
            self._run_plugin_context_action("refresh", plugin_id)
        elif chosen is rename_action:
            self._run_plugin_context_action("rename", plugin_id)
        elif chosen is config_action:
            self._run_plugin_context_action("edit_config", plugin_id)
        elif chosen is toggle_action:
            self._run_plugin_context_action("toggle_enabled", plugin_id)

    def _run_plugin_context_action(self, action_name: str, plugin_id: str) -> bool:
        if self._plugin_actions is None:
            return False
        active_plugin_id = None
        if self._active_widget is not None:
            active_key = self._tab_key_for_widget(self._active_widget)
            if active_key and active_key.startswith("plugin:"):
                active_plugin_id = active_key.removeprefix("plugin:")
        action_map = {
            "refresh": self._plugin_actions.refresh_plugin,
            "rename": self._plugin_actions.rename_plugin,
            "edit_config": self._plugin_actions.edit_plugin_config,
            "toggle_enabled": self._plugin_actions.toggle_plugin_enabled,
        }
        action = action_map[action_name]
        result = action(self, int(plugin_id))
        if not result.changed or result.plugin_id is None:
            return False
        if action_name == "toggle_enabled" and active_plugin_id == plugin_id:
            self.nav_tabs.setCurrentIndex(0)
        self._reload_changed_plugin_tabs([str(result.plugin_id)])
        self._sync_plugin_overflow_drawer(reset_search=False)
        return True
```

- [ ] **Step 4: Run the targeted main-window tests to verify the feature now passes**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "plugin_tab_context_menu_reload or hidden_plugin_context_menu_rename or disabling_active_plugin_falls_back" -q
```

Expected: PASS.

- [ ] **Step 5: Commit the main-window context-menu implementation**

Run:

```bash
git add src/atv_player/ui/plugin_tab_drawer.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: add plugin tab context menus"
```

## Task 5: Run Focused Regression Coverage And Close The Branch Cleanly

**Files:**
- Modify: none
- Test: `tests/test_plugin_actions.py`
- Test: `tests/test_plugin_manager_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
uv run pytest tests/test_plugin_actions.py tests/test_plugin_manager_dialog.py tests/test_main_window_ui.py -q
```

Expected: PASS with all targeted plugin-action and main-window UI tests green.

- [ ] **Step 2: Review the diff before finalizing**

Run:

```bash
git diff --stat HEAD~3..HEAD
```

Expected: only `plugin_actions.py`, `plugin_manager_dialog.py`, `plugin_tab_drawer.py`, `main_window.py`, `tests/test_plugin_actions.py`, and `tests/test_main_window_ui.py` should be listed for this feature.

- [ ] **Step 3: Create the final feature commit if the branch is not already cleanly grouped**

Run:

```bash
git status --short
```

If files are still unstaged or partially committed, run:

```bash
git add src/atv_player/ui/plugin_actions.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/plugin_tab_drawer.py src/atv_player/ui/main_window.py tests/test_plugin_actions.py tests/test_main_window_ui.py
git commit -m "feat: support plugin tab context menus"
```

Expected: working tree becomes clean or only contains unrelated pre-existing changes.

## Self-Review

### Spec Coverage

- Visible plugin tab context menu: covered by Task 3 and Task 4.
- Hidden overflow-drawer plugin context menu: covered by Task 3 and Task 4.
- Shared action helper reused by plugin manager and main window: covered by Task 1 and Task 2.
- Reload uses plugin refresh plus changed-tab rebuild: covered by Task 4.
- Rename and config edits rebuild the affected plugin tab state: covered by Task 3 and Task 4.
- Enable or disable updates tab membership and active-tab fallback: covered by Task 3 and Task 4.
- Drawer synchronization after plugin changes: covered by Task 3 and Task 4.
- Focused regression coverage for helper and UI behavior: covered by Task 1, Task 3, and Task 5.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred implementation markers remain.
- Every test step includes an exact command and expected result.
- Every code-writing step names exact files and includes concrete code snippets to anchor the implementation.

### Type Consistency

- Shared helper result type is consistently `PluginActionResult`.
- Main-window dispatch uses action names `refresh`, `rename`, `edit_config`, and `toggle_enabled` consistently across tests and implementation steps.
- Plugin ids are treated as `int` at the helper boundary and `str` in main-window tab keys, with explicit conversions shown where they cross.
