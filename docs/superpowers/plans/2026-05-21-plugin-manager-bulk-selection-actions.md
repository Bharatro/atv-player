# Plugin Manager Bulk Selection Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bulk enable, disable, refresh, and delete support to the plugin manager dialog while preserving current search/filter/sort behavior and keeping single-item edit actions single-select only.

**Architecture:** Keep the entire change inside `PluginManagerDialog` and its dialog tests. Replace the ambiguous single `启用/禁用` button with explicit `启用` and `禁用` buttons, compute actionable targets from the selected visible plugin IDs, and extend reload/restore logic so bulk operations can preserve the remaining visible selection set across table rerenders.

**Tech Stack:** Python 3.13, PySide6, pytest, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  - Replace the single toggle button with explicit enable/disable buttons.
  - Add selected-plugin lookup helpers and visible-selection restoration by `plugin_id`.
  - Extend sync-state logic for bulk-action availability.
  - Update bulk enable/disable/delete dispatch and background refresh dispatch.
- Modify: `tests/test_plugin_manager_dialog.py`
  - Add focused UI tests for new button labels, multi-select button availability, bulk action dispatch, selection persistence, and multi-refresh behavior.

## Task 1: Replace The Ambiguous Toggle Button With Explicit Enable / Disable Buttons

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py:101-181,318-352`
- Test: `tests/test_plugin_manager_dialog.py:400-460`

- [ ] **Step 1: Write the failing tests for the new button labels and selection-state rules**

Add these tests below `test_plugin_manager_dialog_disables_row_actions_without_selection` in `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_dialog_exposes_explicit_enable_and_disable_buttons(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.enable_button.text() == "启用"
    assert dialog.disable_button.text() == "禁用"


def test_plugin_manager_dialog_disables_bulk_buttons_without_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.clearSelection()
    dialog._sync_action_state()

    assert dialog.enable_button.isEnabled() is False
    assert dialog.disable_button.isEnabled() is False
    assert dialog.refresh_button.isEnabled() is False
    assert dialog.delete_button.isEnabled() is False


def test_plugin_manager_dialog_enables_bulk_buttons_based_on_selected_states(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 0, 1)
    dialog._sync_action_state()

    assert dialog.enable_button.isEnabled() is True
    assert dialog.disable_button.isEnabled() is True
    assert dialog.refresh_button.isEnabled() is True
    assert dialog.delete_button.isEnabled() is True


def test_plugin_manager_dialog_keeps_single_item_actions_disabled_for_multi_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 0, 1)
    dialog._sync_action_state()

    assert dialog.rename_button.isEnabled() is False
    assert dialog.config_button.isEnabled() is False
    assert dialog.category_button.isEnabled() is False
    assert dialog.logs_button.isEnabled() is False
```

- [ ] **Step 2: Run the focused dialog tests and verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "explicit_enable_and_disable_buttons or disables_bulk_buttons_without_selection or enables_bulk_buttons_based_on_selected_states or keeps_single_item_actions_disabled_for_multi_selection" -v
```

Expected:

```text
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_exposes_explicit_enable_and_disable_buttons
```

The first failure should mention that `PluginManagerDialog` has no attribute `enable_button`.

- [ ] **Step 3: Replace `toggle_button` with `enable_button` and `disable_button`**

In `src/atv_player/ui/plugin_manager_dialog.py`, replace the current button definitions:

```python
        self.category_button = QPushButton("分类管理")
        self.toggle_button = QPushButton("启用/禁用")
        self.up_button = QPushButton("上移")
```

with:

```python
        self.category_button = QPushButton("分类管理")
        self.enable_button = QPushButton("启用")
        self.disable_button = QPushButton("禁用")
        self.up_button = QPushButton("上移")
```

Update the actions-row button order:

```python
        for button in (
            self.add_local_button,
            self.add_remote_button,
            self.import_github_button,
            self.rename_button,
            self.config_button,
            self.category_button,
            self.enable_button,
            self.disable_button,
            self.up_button,
            self.down_button,
            self.reorder_button,
            self.refresh_button,
            self.logs_button,
            self.delete_button,
        ):
            actions.addWidget(button)
```

Update the signal wiring:

```python
        self.category_button.clicked.connect(self._open_category_manager_dialog)
        self.enable_button.clicked.connect(self._enable_selected)
        self.disable_button.clicked.connect(self._disable_selected)
        self.up_button.clicked.connect(lambda: self._move_selected(-1))
```

Add these helpers above `_sync_action_state()`:

```python
    def _selected_plugins(self) -> list:
        plugin_by_id = {int(plugin.id): plugin for plugin in self._all_plugins}
        plugins = []
        for plugin_id in self._selected_plugin_ids():
            plugin = plugin_by_id.get(int(plugin_id))
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    def _has_selected_enabled_plugin(self) -> bool:
        return any(bool(plugin.enabled) for plugin in self._selected_plugins())

    def _has_selected_disabled_plugin(self) -> bool:
        return any(not bool(plugin.enabled) for plugin in self._selected_plugins())
```

Update `_sync_action_state()` so the non-bulk state section reads:

```python
        has_selection = self._has_selection()
        has_single_selection = self._has_single_selection()
        has_selected_enabled_plugin = self._has_selected_enabled_plugin()
        has_selected_disabled_plugin = self._has_selected_disabled_plugin()
        row = self.plugin_table.currentRow() if has_single_selection else -1
        last_row = self.plugin_table.rowCount() - 1
        allow_reorder_nudge = self._is_current_order_sort()
        self.add_local_button.setEnabled(True)
        self.add_remote_button.setEnabled(True)
        self.import_github_button.setEnabled(not self._import_in_progress)
        self.rename_button.setEnabled(has_single_selection)
        self.config_button.setEnabled(has_single_selection)
        self.category_button.setEnabled(has_single_selection)
        self.enable_button.setEnabled(has_selected_disabled_plugin)
        self.disable_button.setEnabled(has_selected_enabled_plugin)
        self.up_button.setEnabled(has_single_selection and allow_reorder_nudge and row > 0)
        self.down_button.setEnabled(has_single_selection and allow_reorder_nudge and row >= 0 and row < last_row)
        self.reorder_button.setEnabled(True)
        self.refresh_button.setEnabled(has_selection)
        self.logs_button.setEnabled(has_single_selection)
        self.delete_button.setEnabled(has_selection)
```

Also update the refresh-in-progress branch to disable `enable_button` and `disable_button` instead of `toggle_button`.

- [ ] **Step 4: Run the focused dialog tests and verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "explicit_enable_and_disable_buttons or disables_bulk_buttons_without_selection or enables_bulk_buttons_based_on_selected_states or keeps_single_item_actions_disabled_for_multi_selection" -v
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit the button-semantics change**

Run:

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: add explicit plugin bulk enable disable buttons"
```

## Task 2: Add Bulk Enable / Disable Dispatch And Visible Selection Restoration

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py:185-272,421-520`
- Test: `tests/test_plugin_manager_dialog.py:30-40,460-560`

- [ ] **Step 1: Write the failing tests for bulk enable/disable behavior and selection restoration**

First update `FakePluginManager.set_plugin_enabled()` in `tests/test_plugin_manager_dialog.py` so it mutates the fake records:

```python
    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        self.toggle_calls.append((plugin_id, enabled))
        for plugin in self.plugins:
            if int(plugin.id) == int(plugin_id):
                plugin.enabled = enabled
                break
```

Then add these tests below `test_plugin_manager_dialog_actions_call_manager`:

```python
def test_plugin_manager_dialog_bulk_enable_only_updates_disabled_plugins(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 0, 1)

    dialog._enable_selected()

    assert manager.toggle_calls == [(2, True)]


def test_plugin_manager_dialog_bulk_disable_only_updates_enabled_plugins(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 0, 1)

    dialog._disable_selected()

    assert manager.toggle_calls == [(1, False)]


def test_plugin_manager_dialog_bulk_disable_restores_visible_multi_selection(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 0, 1)

    dialog._disable_selected()

    assert manager.toggle_calls == [(1, False)]
    assert dialog._selected_plugin_ids() == [1, 2]


def test_plugin_manager_dialog_bulk_enable_preserves_filter_and_visible_selection(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.enabled_filter_combo.setCurrentText("仅禁用")
    _select_rows(dialog, 0)

    dialog._enable_selected()

    assert dialog.enabled_filter_combo.currentText() == "仅禁用"
    assert _visible_plugin_ids(dialog) == []
    assert dialog._selected_plugin_ids() == []
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "bulk_enable_only_updates_disabled_plugins or bulk_disable_only_updates_enabled_plugins or bulk_disable_restores_visible_multi_selection or bulk_enable_preserves_filter_and_visible_selection" -v
```

Expected:

```text
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_bulk_enable_only_updates_disabled_plugins
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_bulk_disable_only_updates_enabled_plugins
```

The failure should mention that `_enable_selected` / `_disable_selected` does not exist yet.

- [ ] **Step 3: Extend reload and restore logic to preserve multiple visible plugin IDs**

In `src/atv_player/ui/plugin_manager_dialog.py`, first expand the QtCore import from:

```python
from PySide6.QtCore import QObject, QSignalBlocker, Qt, QTimer, Signal
```

to:

```python
from PySide6.QtCore import QItemSelectionModel, QObject, QSignalBlocker, Qt, QTimer, Signal
```

Then change `reload_plugins()` from:

```python
    def reload_plugins(self) -> None:
        selected_plugin_id = self._selected_plugin_id()
        ...
        self._all_plugins = list(plugins)
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_id)
```

to:

```python
    def reload_plugins(self, selected_plugin_ids: list[int] | None = None) -> None:
        if selected_plugin_ids is None:
            selected_plugin_ids = self._selected_plugin_ids()
        self._plugin_action_reload_timer.stop()
        self._pending_plugin_action_id = None
        self._plugin_actions_cache.clear()
        plugins = self.plugin_manager.list_plugins()
        current_snapshot = self._plugin_snapshot(plugins)
        if not self._initial_plugin_snapshot_captured:
            self._initial_plugin_snapshot = current_snapshot
            self._initial_plugin_snapshot_captured = True
        self.changed_plugin_ids = self._diff_plugin_ids(self._initial_plugin_snapshot, current_snapshot)
        self.plugin_tabs_dirty = bool(self.changed_plugin_ids)
        self._all_plugins = list(plugins)
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_ids)
```

Update `_apply_view_filters()` the same way:

```python
    def _apply_view_filters(self) -> None:
        selected_plugin_ids = self._selected_plugin_ids()
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_ids)
```

Replace `_render_plugins()` and `_restore_selection()` with:

```python
    def _render_plugins(self, plugins, selected_plugin_ids: list[int]) -> None:
        self.plugin_table.setRowCount(len(plugins))
        for row, plugin in enumerate(plugins):
            name_item = QTableWidgetItem(plugin.display_name or "")
            name_item.setData(256, plugin.id)
            self.plugin_table.setItem(row, 0, name_item)
            self.plugin_table.setItem(row, 1, QTableWidgetItem(_display_source_type(plugin.source_type)))
            self.plugin_table.setItem(row, 2, QTableWidgetItem(str(plugin.plugin_version)))
            self.plugin_table.setItem(row, 3, QTableWidgetItem(plugin.source_value))
            self.plugin_table.setItem(row, 4, QTableWidgetItem("是" if plugin.enabled else "否"))
            self.plugin_table.setItem(row, 5, QTableWidgetItem(plugin.last_error or "正常"))
            loaded_at = ""
            if plugin.last_loaded_at:
                loaded_at = datetime.fromtimestamp(plugin.last_loaded_at).strftime("%Y-%m-%d %H:%M:%S")
            self.plugin_table.setItem(row, 6, QTableWidgetItem(loaded_at))
        self.empty_state_label.setVisible(len(plugins) == 0)
        self._restore_selection(selected_plugin_ids)
        self._sync_action_state()

    def _restore_selection(self, plugin_ids: list[int]) -> None:
        target_ids = {int(plugin_id) for plugin_id in plugin_ids}
        self.plugin_table.clearSelection()
        self.plugin_table.setCurrentCell(-1, -1)
        selection_model = self.plugin_table.selectionModel()
        if selection_model is None:
            return
        first_row = -1
        for row in range(self.plugin_table.rowCount()):
            item = self.plugin_table.item(row, 0)
            if item is None:
                continue
            if int(item.data(256)) not in target_ids:
                continue
            if first_row < 0:
                first_row = row
            index = self.plugin_table.model().index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
        if first_row >= 0:
            self.plugin_table.setCurrentCell(first_row, 0)
```

- [ ] **Step 4: Add the bulk enable/disable methods**

Insert these methods above `_move_selected()`:

```python
    def _set_selected_enabled(self, enabled: bool) -> None:
        selected_plugin_ids = self._selected_plugin_ids()
        if not selected_plugin_ids:
            return
        plugin_by_id = {int(plugin.id): plugin for plugin in self._all_plugins}
        changed = False
        for plugin_id in selected_plugin_ids:
            plugin = plugin_by_id.get(int(plugin_id))
            if plugin is None or bool(plugin.enabled) == enabled:
                continue
            self.plugin_actions.apply_toggle_enabled(plugin_id, enabled)
            changed = True
        if not changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins(selected_plugin_ids)

    def _enable_selected(self) -> None:
        self._set_selected_enabled(True)

    def _disable_selected(self) -> None:
        self._set_selected_enabled(False)
```

Update `_selected_plugin_id()` so it continues to work after multi-select restore:

```python
    def _selected_plugin_id(self) -> int | None:
        selected_plugin_ids = self._selected_plugin_ids()
        if len(selected_plugin_ids) != 1:
            return None
        return selected_plugin_ids[0]
```

- [ ] **Step 5: Run the focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "bulk_enable_only_updates_disabled_plugins or bulk_disable_only_updates_enabled_plugins or bulk_disable_restores_visible_multi_selection or bulk_enable_preserves_filter_and_visible_selection or restores_single_selection_when_item_remains_visible" -v
```

Expected:

```text
5 passed
```

- [ ] **Step 6: Commit the bulk enable/disable and selection-restore change**

Run:

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: add bulk plugin enable disable actions"
```

## Task 3: Keep Bulk Delete Compatible With The New Multi-Selection Reload Flow

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py:528-535`
- Test: `tests/test_plugin_manager_dialog.py:610-670`

- [ ] **Step 1: Write the failing test for delete preserving the remaining visible selection**

Add this fake-manager mutation to `delete_plugin()` in `tests/test_plugin_manager_dialog.py`:

```python
    def delete_plugin(self, plugin_id: int) -> None:
        self.delete_calls.append(plugin_id)
        self.plugins = [plugin for plugin in self.plugins if int(plugin.id) != int(plugin_id)]
```

Then add this test below `test_plugin_manager_dialog_deletes_all_selected_plugins`:

```python
def test_plugin_manager_dialog_bulk_delete_keeps_remaining_selected_rows_visible(qtbot) -> None:
    manager = FakePluginManager()
    manager.plugins.append(
        SpiderPluginConfig(
            id=3,
            source_type="local",
            source_value="/plugins/c.py",
            display_name="本地C",
            enabled=False,
            sort_order=2,
            plugin_version=1,
        )
    )
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    _select_rows(dialog, 1, 2)

    dialog._delete_selected()

    assert manager.delete_calls == [2, 3]
    assert _visible_plugin_ids(dialog) == [1]
    assert dialog._selected_plugin_ids() == []
```

- [ ] **Step 2: Run the focused delete tests and verify the new one fails**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "deletes_all_selected_plugins or bulk_delete_keeps_remaining_selected_rows_visible" -v
```

Expected:

```text
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_bulk_delete_keeps_remaining_selected_rows_visible
```

The failure should show that fake plugin data was not removed or that selection restoration did not rerender the remaining rows correctly.

- [ ] **Step 3: Reload after delete using the pre-delete selected IDs**

Update `_delete_selected()` in `src/atv_player/ui/plugin_manager_dialog.py` from:

```python
    def _delete_selected(self) -> None:
        plugin_ids = self._selected_plugin_ids()
        if not plugin_ids:
            return
        for plugin_id in plugin_ids:
            self.plugin_manager.delete_plugin(plugin_id)
        self.plugin_tabs_dirty = True
        self.reload_plugins()
```

to:

```python
    def _delete_selected(self) -> None:
        plugin_ids = self._selected_plugin_ids()
        if not plugin_ids:
            return
        for plugin_id in plugin_ids:
            self.plugin_manager.delete_plugin(plugin_id)
        self.plugin_tabs_dirty = True
        self.reload_plugins(plugin_ids)
```

- [ ] **Step 4: Run the focused delete tests and verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "deletes_all_selected_plugins or bulk_delete_keeps_remaining_selected_rows_visible" -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the bulk delete follow-through**

Run:

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: preserve bulk plugin delete view state"
```

## Task 4: Extend Background Refresh To Refresh All Selected Plugins

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py:44-46,516-527`
- Test: `tests/test_plugin_manager_dialog.py:560-640`

- [ ] **Step 1: Write the failing test for multi-refresh**

Add this test below `test_plugin_manager_dialog_refresh_runs_in_background_and_reloads_on_completion`:

```python
def test_plugin_manager_dialog_bulk_refresh_runs_selected_plugins_in_background(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    _select_rows(dialog, 0, 1)

    reload_calls: list[str] = []
    original_reload = dialog.reload_plugins

    def tracked_reload(selected_plugin_ids=None) -> None:
        reload_calls.append("reload")
        if selected_plugin_ids is None:
            original_reload()
        else:
            original_reload(selected_plugin_ids)

    started_threads: list[object] = []

    class FakeThread:
        def __init__(self, *, target, daemon) -> None:
            self.target = target
            self.daemon = daemon
            self.started = False
            started_threads.append(self)

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr(dialog, "reload_plugins", tracked_reload)
    monkeypatch.setattr(
        plugin_manager_dialog_module,
        "threading",
        types.SimpleNamespace(Thread=FakeThread),
        raising=False,
    )

    dialog._refresh_selected()

    assert len(started_threads) == 1
    assert dialog.refresh_button.isEnabled() is False

    started_threads[0].target()
    qtbot.waitUntil(lambda: manager.refresh_calls == [1, 2], timeout=1000)
    qtbot.waitUntil(lambda: reload_calls == ["reload"], timeout=1000)
```

- [ ] **Step 2: Run the focused refresh tests and verify the new one fails**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "refresh_runs_in_background_and_reloads_on_completion or bulk_refresh_runs_selected_plugins_in_background" -v
```

Expected:

```text
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_bulk_refresh_runs_selected_plugins_in_background
```

The failure should show that only one plugin ID was refreshed.

- [ ] **Step 3: Track refresh targets and refresh the whole selected set**

Add a new field in `PluginManagerDialog.__init__` near `_refresh_in_progress`:

```python
        self._refresh_target_plugin_ids: list[int] = []
```

Update `_refresh_selected()` from:

```python
    def _refresh_selected(self) -> None:
        if self._refresh_in_progress:
            return
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        self._refresh_in_progress = True
        self._sync_action_state()

        def run() -> None:
            try:
                self.plugin_manager.refresh_plugin(plugin_id)
            except Exception as exc:
                self._refresh_signals.failed.emit(str(exc))
                return
            self._refresh_signals.completed.emit()

        threading.Thread(target=run, daemon=True).start()
```

to:

```python
    def _refresh_selected(self) -> None:
        if self._refresh_in_progress:
            return
        plugin_ids = self._selected_plugin_ids()
        if not plugin_ids:
            return
        self._refresh_target_plugin_ids = list(plugin_ids)
        self._refresh_in_progress = True
        self._sync_action_state()

        def run() -> None:
            try:
                for plugin_id in plugin_ids:
                    self.plugin_manager.refresh_plugin(plugin_id)
            except Exception as exc:
                self._refresh_signals.failed.emit(str(exc))
                return
            self._refresh_signals.completed.emit()

        threading.Thread(target=run, daemon=True).start()
```

Update `_handle_refresh_completed()` and `_handle_refresh_failed()`:

```python
    def _handle_refresh_completed(self) -> None:
        target_plugin_ids = list(self._refresh_target_plugin_ids)
        self._refresh_target_plugin_ids = []
        self._refresh_in_progress = False
        self.plugin_tabs_dirty = True
        self.reload_plugins(target_plugin_ids)

    def _handle_refresh_failed(self, message: str) -> None:
        target_plugin_ids = list(self._refresh_target_plugin_ids)
        self._refresh_target_plugin_ids = []
        self._refresh_in_progress = False
        self.reload_plugins(target_plugin_ids)
        QMessageBox.warning(self, "刷新失败", message)
```

- [ ] **Step 4: Run the focused refresh tests and verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "refresh_runs_in_background_and_reloads_on_completion or bulk_refresh_runs_selected_plugins_in_background" -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Run the full dialog test file**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 6: Commit the bulk refresh support**

Run:

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: add bulk plugin refresh support"
```
