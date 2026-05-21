# Plugin Manager Search Sort Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add search, enabled-state filtering, and view-only sorting to the plugin manager dialog without changing persistent plugin order semantics.

**Architecture:** Keep all new state and behavior inside `PluginManagerDialog` as a pure view-layer enhancement. `reload_plugins()` still fetches the full plugin list and updates dirty-state snapshots, then a local view pipeline filters, sorts, and renders the visible subset while preserving row identity by `plugin_id`.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  - Add the condition bar widgets, local view-state helpers, filtered/sorted rendering pipeline, empty-result handling, and move-button guardrails.
- Modify: `tests/test_plugin_manager_dialog.py`
  - Extend the fake manager and add focused dialog tests for search, filter, sort, clear, empty-state, selection restoration, and condition persistence across reloads.

### Task 1: Add The Condition Bar And Search / Filter Rendering

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:1)
- Test: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:1)

- [ ] **Step 1: Write the failing UI tests for the new controls and search/filter behavior**

Add these helpers and tests near the existing selection helpers in `tests/test_plugin_manager_dialog.py`:

```python
def _visible_plugin_ids(dialog: PluginManagerDialog) -> list[int]:
    plugin_ids: list[int] = []
    for row in range(dialog.plugin_table.rowCount()):
        item = dialog.plugin_table.item(row, 0)
        assert item is not None
        plugin_ids.append(int(item.data(256)))
    return plugin_ids


def test_plugin_manager_dialog_renders_search_filter_sort_controls(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.search_input.placeholderText() == "搜索名称或地址"
    assert dialog.enabled_filter_combo.currentText() == "全部"
    assert dialog.sort_combo.currentText() == "当前顺序"
    assert dialog.clear_filters_button.text() == "清空"


def test_plugin_manager_dialog_searches_name_and_source_case_insensitively(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.search_input.setText("远程b")
    assert _visible_plugin_ids(dialog) == [2]

    dialog.search_input.setText(" EXAMPLE.COM/B.PY ")
    assert _visible_plugin_ids(dialog) == [2]


def test_plugin_manager_dialog_filters_enabled_state(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.enabled_filter_combo.setCurrentText("仅启用")
    assert _visible_plugin_ids(dialog) == [1]

    dialog.enabled_filter_combo.setCurrentText("仅禁用")
    assert _visible_plugin_ids(dialog) == [2]
```

- [ ] **Step 2: Run the focused dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "renders_search_filter_sort_controls or searches_name_and_source_case_insensitively or filters_enabled_state" -v
```

Expected: `FAIL` because `PluginManagerDialog` does not yet expose `search_input`, `enabled_filter_combo`, `sort_combo`, or `clear_filters_button`.

- [ ] **Step 3: Add the condition bar widgets and local view pipeline**

In `src/atv_player/ui/plugin_manager_dialog.py`, update the imports and add the new widgets, layout, and helpers:

```python
from PySide6.QtCore import QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
```

Inside `PluginManagerDialog.__init__`, immediately after `warning_label`:

```python
        self._all_plugins = []
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("搜索名称或地址")
        self.enabled_filter_combo = QComboBox(self)
        self.enabled_filter_combo.addItem("全部", "all")
        self.enabled_filter_combo.addItem("仅启用", "enabled")
        self.enabled_filter_combo.addItem("仅禁用", "disabled")
        self.sort_combo = QComboBox(self)
        self.sort_combo.addItem("当前顺序", "sort_order")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.addItem("最近加载", "last_loaded_at")
        self.clear_filters_button = QPushButton("清空")
        self.empty_state_label = QLabel("没有匹配的插件", self)
        self.empty_state_label.hide()

        filters = QHBoxLayout()
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.enabled_filter_combo)
        filters.addWidget(self.sort_combo)
        filters.addWidget(self.clear_filters_button)
```

Insert the new layout and empty-state label into the main layout:

```python
        layout = self.content_layout()
        layout.addWidget(self.warning_label)
        layout.addLayout(filters)
        layout.addLayout(actions)
        layout.addWidget(self.plugin_actions_label)
        layout.addWidget(self.plugin_actions_empty_label)
        layout.addWidget(self.plugin_actions_widget)
        layout.addWidget(self.plugin_table)
        layout.addWidget(self.empty_state_label)
```

Connect the new signals:

```python
        self.search_input.textChanged.connect(self._apply_view_filters)
        self.enabled_filter_combo.currentIndexChanged.connect(self._apply_view_filters)
        self.sort_combo.currentIndexChanged.connect(self._apply_view_filters)
        self.clear_filters_button.clicked.connect(self._clear_view_filters)
```

Add the rendering helpers near `reload_plugins()`:

```python
    def _apply_view_filters(self) -> None:
        selected_plugin_id = self._selected_plugin_id()
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_id)

    def _clear_view_filters(self) -> None:
        blockers = [
            QSignalBlocker(self.search_input),
            QSignalBlocker(self.enabled_filter_combo),
            QSignalBlocker(self.sort_combo),
        ]
        self.search_input.clear()
        self.enabled_filter_combo.setCurrentIndex(0)
        self.sort_combo.setCurrentIndex(0)
        del blockers
        self._apply_view_filters()

    def _visible_plugins(self, plugins) -> list:
        search_term = self.search_input.text().strip().casefold()
        enabled_filter = self.enabled_filter_combo.currentData()
        filtered = []
        for plugin in plugins:
            if not self._matches_search(plugin, search_term):
                continue
            if enabled_filter == "enabled" and not plugin.enabled:
                continue
            if enabled_filter == "disabled" and plugin.enabled:
                continue
            filtered.append(plugin)
        return self._sort_plugins(filtered)

    def _matches_search(self, plugin, search_term: str) -> bool:
        if not search_term:
            return True
        display_name = (plugin.display_name or "").casefold()
        source_value = (plugin.source_value or "").casefold()
        return search_term in display_name or search_term in source_value

    def _sort_plugins(self, plugins) -> list:
        return sorted(plugins, key=lambda plugin: int(plugin.sort_order))

    def _render_plugins(self, plugins, selected_plugin_id: int | None) -> None:
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
        self._restore_selection(selected_plugin_id)
        self._sync_action_state()
```

Update `reload_plugins()` to cache the full list and delegate to the renderer:

```python
        self._all_plugins = list(plugins)
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_id)
```

- [ ] **Step 4: Run the focused dialog tests to verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "renders_search_filter_sort_controls or searches_name_and_source_case_insensitively or filters_enabled_state" -v
```

Expected: `PASS` for the three new tests.

- [ ] **Step 5: Commit the search/filter control work**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: add plugin manager search and enabled filter controls"
```

### Task 2: Add View-Only Sorting And Move Button Guardrails

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:1)
- Test: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:1)

- [ ] **Step 1: Write the failing sorting tests**

Add these tests below the search/filter tests in `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_dialog_sorts_by_name_without_mutating_manager_order(qtbot) -> None:
    manager = FakePluginManager()
    manager.plugins = [
        SpiderPluginConfig(
            id=1,
            source_type="local",
            source_value="/plugins/zeta.py",
            display_name="Zeta",
            enabled=True,
            sort_order=0,
            plugin_version=1,
        ),
        SpiderPluginConfig(
            id=2,
            source_type="remote",
            source_value="https://example.com/alpha.py",
            display_name="Alpha",
            enabled=True,
            sort_order=1,
            plugin_version=1,
        ),
        SpiderPluginConfig(
            id=3,
            source_type="local",
            source_value="/plugins/beta.py",
            display_name="Beta",
            enabled=False,
            sort_order=2,
            plugin_version=1,
        ),
    ]
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.sort_combo.setCurrentText("名称")

    assert _visible_plugin_ids(dialog) == [2, 3, 1]
    assert [plugin.id for plugin in manager.plugins] == [1, 2, 3]


def test_plugin_manager_dialog_sorts_by_recently_loaded_descending(qtbot) -> None:
    manager = FakePluginManager()
    manager.plugins[0].last_loaded_at = 1713206400
    manager.plugins[1].last_loaded_at = 1713292800
    manager.plugins.append(
        SpiderPluginConfig(
            id=3,
            source_type="local",
            source_value="/plugins/c.py",
            display_name="本地C",
            enabled=True,
            sort_order=2,
            plugin_version=1,
        )
    )
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.sort_combo.setCurrentText("最近加载")

    assert _visible_plugin_ids(dialog) == [2, 1, 3]


def test_plugin_manager_dialog_disables_move_buttons_when_view_sort_is_not_current_order(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)

    dialog.sort_combo.setCurrentText("名称")
    dialog._sync_action_state()

    assert dialog.up_button.isEnabled() is False
    assert dialog.down_button.isEnabled() is False
    assert dialog.reorder_button.isEnabled() is True
```

- [ ] **Step 2: Run the sorting tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "sorts_by_name_without_mutating_manager_order or sorts_by_recently_loaded_descending or disables_move_buttons_when_view_sort_is_not_current_order" -v
```

Expected: `FAIL` because the dialog still renders in raw manager order and `上移` / `下移` do not yet respect the active sort mode.

- [ ] **Step 3: Gate persistent move actions behind the default sort mode**

In `src/atv_player/ui/plugin_manager_dialog.py`, first extend `_sort_plugins(...)` to support the non-default view orders:

```python
    def _sort_plugins(self, plugins) -> list:
        sort_mode = self.sort_combo.currentData()
        if sort_mode == "sort_order":
            return sorted(plugins, key=lambda plugin: int(plugin.sort_order))
        if sort_mode == "name":
            return sorted(
                plugins,
                key=lambda plugin: ((plugin.display_name or plugin.source_value or "").casefold(), int(plugin.sort_order)),
            )
        return sorted(
            plugins,
            key=lambda plugin: (
                int(plugin.last_loaded_at) <= 0,
                -int(plugin.last_loaded_at) if int(plugin.last_loaded_at) > 0 else 0,
                int(plugin.sort_order),
            ),
        )
```

Then add this helper near `_has_single_selection()`:

```python
    def _is_current_order_sort(self) -> bool:
        return self.sort_combo.currentData() == "sort_order"
```

Update `_sync_action_state()` so `up_button` and `down_button` only enable in current-order mode:

```python
        allow_reorder_nudge = self._is_current_order_sort()
        self.up_button.setEnabled(has_single_selection and allow_reorder_nudge and row > 0)
        self.down_button.setEnabled(has_single_selection and allow_reorder_nudge and row >= 0 and row < last_row)
```

Add the same guard to `_move_selected(...)` so direct method calls also stay safe:

```python
    def _move_selected(self, direction: int) -> None:
        if not self._is_current_order_sort():
            return
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        self.plugin_manager.move_plugin(plugin_id, direction)
        self.plugin_tabs_dirty = True
        self.reload_plugins()
```

Leave `reorder_button` behavior unchanged.

- [ ] **Step 4: Run the sorting tests to verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "sorts_by_name_without_mutating_manager_order or sorts_by_recently_loaded_descending or disables_move_buttons_when_view_sort_is_not_current_order" -v
```

Expected: `PASS` for the three new sorting tests.

- [ ] **Step 5: Commit the view-sorting behavior**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: add plugin manager view sorting"
```

### Task 3: Preserve Conditions Across Reloads, Support Clear, And Handle Empty Results

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:1)
- Test: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:1)

- [ ] **Step 1: Write the failing reload/empty-state tests**

Add these tests below the sorting tests in `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_dialog_clear_button_restores_default_conditions(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.search_input.setText("远程")
    dialog.enabled_filter_combo.setCurrentText("仅禁用")
    dialog.sort_combo.setCurrentText("名称")
    dialog.clear_filters_button.click()

    assert dialog.search_input.text() == ""
    assert dialog.enabled_filter_combo.currentText() == "全部"
    assert dialog.sort_combo.currentText() == "当前顺序"
    assert _visible_plugin_ids(dialog) == [1, 2]


def test_plugin_manager_dialog_reload_preserves_active_view_conditions(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.search_input.setText("远程")
    manager.plugins.append(
        SpiderPluginConfig(
            id=3,
            source_type="local",
            source_value="/plugins/c.py",
            display_name="本地C",
            enabled=True,
            sort_order=2,
            plugin_version=1,
        )
    )
    dialog.reload_plugins()

    assert dialog.search_input.text() == "远程"
    assert dialog.enabled_filter_combo.currentText() == "全部"
    assert dialog.sort_combo.currentText() == "当前顺序"
    assert _visible_plugin_ids(dialog) == [2]


def test_plugin_manager_dialog_restores_single_selection_when_item_remains_visible(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(1)

    dialog.search_input.setText("远程")

    assert dialog._selected_plugin_id() == 2


def test_plugin_manager_dialog_clears_selection_and_shows_empty_state_when_no_rows_match(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)

    dialog.search_input.setText("not-found")

    assert dialog.plugin_table.rowCount() == 0
    assert dialog._selected_plugin_id() is None
    assert dialog.empty_state_label.isHidden() is False
    assert dialog.rename_button.isEnabled() is False
    assert dialog.delete_button.isEnabled() is False
```

- [ ] **Step 2: Run the reload/empty-state tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "clear_button_restores_default_conditions or reload_preserves_active_view_conditions or restores_single_selection_when_item_remains_visible or clears_selection_and_shows_empty_state_when_no_rows_match" -v
```

Expected: `FAIL` because the dialog does not yet preserve conditions across `reload_plugins()`, and the empty-state label behavior is not fully covered.

- [ ] **Step 3: Finish the condition-preservation and empty-state behavior**

In `src/atv_player/ui/plugin_manager_dialog.py`, make these final adjustments:

```python
    def reload_plugins(self) -> None:
        selected_plugin_id = self._selected_plugin_id()
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
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_id)
```

Keep `_restore_selection(...)` unchanged so single-selection restoration stays keyed on `plugin_id`, and rely on `_render_plugins(...)` to call:

```python
        self.empty_state_label.setVisible(len(plugins) == 0)
        self._restore_selection(selected_plugin_id)
        self._sync_action_state()
```

No extra manager calls are needed when the user changes local view controls.

- [ ] **Step 4: Run the full plugin manager dialog suite**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -v
```

Expected: `PASS` for the full dialog suite, including the newly added search/filter/sort tests and the existing reorder/category/action tests.

- [ ] **Step 5: Commit the finishing behavior**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git commit -m "feat: finish plugin manager view controls"
```

## Self-Review

- Spec coverage check:
  - 常驻条件栏: Task 1
  - 搜索名称/地址: Task 1
  - 启用/禁用筛选: Task 1
  - 视图层名称/最近加载排序: Task 2
  - 非默认排序禁用 `上移` / `下移`: Task 2
  - `清空`、空结果、条件保留、选中恢复: Task 3
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every code-changing step includes concrete code or tests
  - Every verification step includes an exact command and expected result
- Type consistency:
  - New widget names stay consistent across tasks: `search_input`, `enabled_filter_combo`, `sort_combo`, `clear_filters_button`, `empty_state_label`
  - View helpers stay consistent across tasks: `_apply_view_filters`, `_clear_view_filters`, `_visible_plugins`, `_sort_plugins`, `_render_plugins`, `_is_current_order_sort`
