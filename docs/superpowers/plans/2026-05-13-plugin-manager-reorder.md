# Plugin Manager Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated plugin reorder workflow that supports long-distance moves and small adjustments without forcing repeated `上移` / `下移` clicks.

**Architecture:** Keep the current single-step `move_plugin(plugin_id, direction)` path for lightweight tweaks in the main plugin manager, and add a separate batch reorder path that persists one final ordered `plugin_id` list. Implement the new reorder UI as a focused dialog in its own file, then wire it into the existing plugin manager dialog so sorting stays isolated from refresh, delete, and config actions.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, SQLite repository layer

---

## File Structure

- Modify: `src/atv_player/plugins/repository.py`
  - Add `reorder_plugins(plugin_ids_in_order: list[int])` that validates the current plugin id set and rewrites `sort_order` in one pass.
- Modify: `src/atv_player/plugins/__init__.py`
  - Add `SpiderPluginManager.reorder_plugins(...)` as the UI-facing batch reorder entry point.
- Create: `src/atv_player/ui/plugin_reorder_dialog.py`
  - Add a focused `PluginReorderDialog` that owns the reorder draft, button actions, save/cancel flow, and error handling.
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  - Add the `调整顺序` button and wire it to the new reorder dialog while preserving existing selection and reload behavior.
- Modify: `tests/test_storage.py`
  - Add repository tests for final-order persistence and stale id rejection.
- Modify: `tests/test_spider_plugin_manager.py`
  - Add manager tests that prove the UI-facing API persists the requested order and rejects stale snapshots.
- Create: `tests/test_plugin_reorder_dialog.py`
  - Add focused UI tests for draft-only operations, save/cancel, and save error handling in the dedicated reorder dialog.
- Modify: `tests/test_plugin_manager_dialog.py`
  - Add integration tests for the new button and the reload path after a successful reorder.

### Task 1: Repository Batch Reorder

**Files:**
- Modify: [src/atv_player/plugins/repository.py](/home/harold/workspace/atv-player/src/atv_player/plugins/repository.py:132)
- Test: [tests/test_storage.py](/home/harold/workspace/atv-player/tests/test_storage.py:836)

- [ ] **Step 1: Write the failing repository tests**

Add these tests near `test_spider_plugin_repository_round_trip_and_logs` in `tests/test_storage.py`:

```python
def test_spider_plugin_repository_reorder_plugins_rewrites_final_order(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin1 = repo.add_plugin("local", "/plugins/1.py", "插件1")
    plugin2 = repo.add_plugin("local", "/plugins/2.py", "插件2")
    plugin3 = repo.add_plugin("local", "/plugins/3.py", "插件3")

    repo.reorder_plugins([plugin3.id, plugin1.id, plugin2.id])

    plugins = repo.list_plugins()

    assert [(plugin.id, plugin.sort_order) for plugin in plugins] == [
        (plugin3.id, 0),
        (plugin1.id, 1),
        (plugin2.id, 2),
    ]


def test_spider_plugin_repository_reorder_plugins_rejects_stale_plugin_ids(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin1 = repo.add_plugin("local", "/plugins/1.py", "插件1")
    plugin2 = repo.add_plugin("local", "/plugins/2.py", "插件2")
    plugin3 = repo.add_plugin("local", "/plugins/3.py", "插件3")

    with pytest.raises(ValueError, match="插件列表已变化"):
        repo.reorder_plugins([plugin3.id, plugin1.id])

    assert [plugin.id for plugin in repo.list_plugins()] == [plugin1.id, plugin2.id, plugin3.id]
```

- [ ] **Step 2: Run the repository tests to verify they fail**

Run:

```bash
uv run pytest tests/test_storage.py -k "reorder_plugins" -v
```

Expected: `FAIL` because `SpiderPluginRepository` does not yet define `reorder_plugins`.

- [ ] **Step 3: Implement the repository API**

Add this method in `src/atv_player/plugins/repository.py` next to `move_plugin(...)`:

```python
    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        plugins = self.list_plugins()
        current_ids = [item.id for item in plugins]
        if sorted(plugin_ids_in_order) != sorted(current_ids):
            raise ValueError("插件列表已变化，请重新打开排序窗口")
        ordered_plugins = {item.id: item for item in plugins}
        with self._connect() as conn:
            for order, plugin_id in enumerate(plugin_ids_in_order):
                conn.execute(
                    "UPDATE spider_plugins SET sort_order = ? WHERE id = ?",
                    (order, ordered_plugins[plugin_id].id),
                )
```

Keep `move_plugin(...)` unchanged so existing callers still work.

- [ ] **Step 4: Run the repository tests to verify they pass**

Run:

```bash
uv run pytest tests/test_storage.py -k "reorder_plugins or round_trip_and_logs" -v
```

Expected: `PASS` for the two new reorder tests and the existing round-trip test.

- [ ] **Step 5: Commit the repository change**

```bash
git add tests/test_storage.py src/atv_player/plugins/repository.py
git commit -m "feat: add batch spider plugin reordering"
```

### Task 2: Manager Batch Reorder Contract

**Files:**
- Modify: [src/atv_player/plugins/__init__.py](/home/harold/workspace/atv-player/src/atv_player/plugins/__init__.py:107)
- Test: [tests/test_spider_plugin_manager.py](/home/harold/workspace/atv-player/tests/test_spider_plugin_manager.py:398)

- [ ] **Step 1: Write the failing manager tests**

Add these tests after `test_manager_iter_enabled_plugins_prioritizes_requested_plugin_ids`:

```python
def test_manager_reorder_plugins_persists_requested_final_order(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader())
    plugin1 = repository.add_plugin("local", "/tmp/1.py", "插件1")
    plugin2 = repository.add_plugin("local", "/tmp/2.py", "插件2")
    plugin3 = repository.add_plugin("local", "/tmp/3.py", "插件3")

    manager.reorder_plugins([plugin3.id, plugin1.id, plugin2.id])

    assert [plugin.id for plugin in repository.list_plugins()] == [plugin3.id, plugin1.id, plugin2.id]


def test_manager_reorder_plugins_raises_when_plugin_snapshot_is_stale(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader())
    plugin1 = repository.add_plugin("local", "/tmp/1.py", "插件1")
    plugin2 = repository.add_plugin("local", "/tmp/2.py", "插件2")

    with pytest.raises(ValueError, match="插件列表已变化"):
        manager.reorder_plugins([plugin1.id])

    assert [plugin.id for plugin in repository.list_plugins()] == [plugin1.id, plugin2.id]
```

- [ ] **Step 2: Run the manager tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "reorder_plugins" -v
```

Expected: `FAIL` because `SpiderPluginManager` does not yet expose `reorder_plugins`.

- [ ] **Step 3: Implement the manager API**

Add this method in `src/atv_player/plugins/__init__.py` beside `move_plugin(...)`:

```python
    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        self._repository.reorder_plugins(plugin_ids_in_order)
```

Do not add extra UI logic here; the manager should stay a thin boundary over the repository for this feature.

- [ ] **Step 4: Run the manager and repository tests together**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "reorder_plugins or iter_enabled_plugins" -v
```

Expected: `PASS` for the two new manager tests and the existing prioritized ordering test.

- [ ] **Step 5: Commit the manager change**

```bash
git add tests/test_spider_plugin_manager.py src/atv_player/plugins/__init__.py
git commit -m "feat: expose plugin batch reorder API"
```

### Task 3: Dedicated Reorder Dialog

**Files:**
- Create: `src/atv_player/ui/plugin_reorder_dialog.py`
- Create: `tests/test_plugin_reorder_dialog.py`

- [ ] **Step 1: Write the failing reorder dialog tests**

Create `tests/test_plugin_reorder_dialog.py` with a focused fake manager and these tests:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from atv_player.models import SpiderPluginConfig
from atv_player.ui.plugin_reorder_dialog import PluginReorderDialog


class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SpiderPluginConfig(id=1, source_type="local", source_value="/plugins/1.py", display_name="插件1", enabled=True, sort_order=0),
            SpiderPluginConfig(id=2, source_type="local", source_value="/plugins/2.py", display_name="插件2", enabled=False, sort_order=1),
            SpiderPluginConfig(id=3, source_type="local", source_value="/plugins/3.py", display_name="插件3", enabled=True, sort_order=2),
        ]
        self.reorder_calls: list[list[int]] = []
        self.reorder_error: Exception | None = None

    def list_plugins(self):
        return list(self.plugins)

    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        if self.reorder_error is not None:
            raise self.reorder_error
        self.reorder_calls.append(list(plugin_ids_in_order))
        by_id = {plugin.id: plugin for plugin in self.plugins}
        self.plugins = [by_id[plugin_id] for plugin_id in plugin_ids_in_order]
        for sort_order, plugin in enumerate(self.plugins):
            plugin.sort_order = sort_order


def test_plugin_reorder_dialog_uses_current_plugin_order_as_initial_draft(qtbot) -> None:
    dialog = PluginReorderDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    assert [dialog.plugin_list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(dialog.plugin_list.count())] == [1, 2, 3]


def test_plugin_reorder_dialog_buttons_only_change_local_draft_until_save(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_list.setCurrentRow(2)

    dialog._move_to_top()
    dialog._move_down()

    assert [dialog.plugin_list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(dialog.plugin_list.count())] == [1, 3, 2]
    assert manager.reorder_calls == []


def test_plugin_reorder_dialog_save_persists_current_list_order(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    item = dialog.plugin_list.takeItem(2)
    dialog.plugin_list.insertItem(0, item)
    dialog.plugin_list.setCurrentRow(0)

    dialog._save()

    assert manager.reorder_calls == [[3, 1, 2]]
    assert dialog.result() == dialog.DialogCode.Accepted


def test_plugin_reorder_dialog_cancel_discards_changes(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_list.setCurrentRow(1)
    dialog._move_to_bottom()

    dialog.reject()

    assert manager.reorder_calls == []


def test_plugin_reorder_dialog_save_failure_shows_warning_and_keeps_dialog_open(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    manager.reorder_error = ValueError("插件列表已变化，请重新打开排序窗口")
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    warnings: list[str] = []

    monkeypatch.setattr("atv_player.ui.plugin_reorder_dialog.QMessageBox.warning", lambda *args: warnings.append(args[2]))

    dialog._save()

    assert warnings == ["插件列表已变化，请重新打开排序窗口"]
    assert dialog.isVisible() is True
    assert dialog.result() == 0
```

- [ ] **Step 2: Run the reorder dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_reorder_dialog.py -v
```

Expected: `FAIL` because `atv_player.ui.plugin_reorder_dialog` does not exist yet.

- [ ] **Step 3: Implement the dedicated dialog**

Create `src/atv_player/ui/plugin_reorder_dialog.py` with this structure:

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class PluginReorderDialog(QDialog):
    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.setWindowTitle("调整插件顺序")
        self.resize(520, 460)
        self.plugin_list = QListWidget(self)
        self.plugin_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.plugin_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.up_button = QPushButton("上移", self)
        self.down_button = QPushButton("下移", self)
        self.top_button = QPushButton("置顶", self)
        self.bottom_button = QPushButton("置底", self)
        self.save_button = QPushButton("保存", self)
        self.cancel_button = QPushButton("取消", self)

        controls = QHBoxLayout()
        for button in (self.top_button, self.up_button, self.down_button, self.bottom_button):
            controls.addWidget(button)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.plugin_list)
        layout.addLayout(controls)
        layout.addLayout(footer)

        self.top_button.clicked.connect(self._move_to_top)
        self.up_button.clicked.connect(self._move_up)
        self.down_button.clicked.connect(self._move_down)
        self.bottom_button.clicked.connect(self._move_to_bottom)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self.plugin_list.currentRowChanged.connect(self._sync_action_state)

        self._load_plugins()

    def _load_plugins(self) -> None:
        self.plugin_list.clear()
        for plugin in self.plugin_manager.list_plugins():
            label = f"{plugin.display_name}（{'启用' if plugin.enabled else '禁用'}）"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, plugin.id)
            self.plugin_list.addItem(item)
        if self.plugin_list.count():
            self.plugin_list.setCurrentRow(0)
        self._sync_action_state()

    def _current_row(self) -> int:
        return self.plugin_list.currentRow()

    def _move_row(self, target_row: int) -> None:
        row = self._current_row()
        if row < 0 or row == target_row:
            return
        item = self.plugin_list.takeItem(row)
        self.plugin_list.insertItem(target_row, item)
        self.plugin_list.setCurrentRow(target_row)
        self._sync_action_state()

    def _move_to_top(self) -> None:
        self._move_row(0)

    def _move_up(self) -> None:
        row = self._current_row()
        if row > 0:
            self._move_row(row - 1)

    def _move_down(self) -> None:
        row = self._current_row()
        if 0 <= row < self.plugin_list.count() - 1:
            self._move_row(row + 1)

    def _move_to_bottom(self) -> None:
        if self.plugin_list.count():
            self._move_row(self.plugin_list.count() - 1)

    def _ordered_plugin_ids(self) -> list[int]:
        return [
            int(self.plugin_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.plugin_list.count())
        ]

    def _save(self) -> None:
        try:
            self.plugin_manager.reorder_plugins(self._ordered_plugin_ids())
        except Exception as exc:
            QMessageBox.warning(self, "排序保存失败", str(exc))
            return
        self.accept()

    def _sync_action_state(self) -> None:
        row = self._current_row()
        last_row = self.plugin_list.count() - 1
        has_selection = row >= 0
        self.top_button.setEnabled(has_selection and row > 0)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row >= 0 and row < last_row)
        self.bottom_button.setEnabled(has_selection and row >= 0 and row < last_row)
```

- [ ] **Step 4: Run the reorder dialog tests to verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_reorder_dialog.py -v
```

Expected: `PASS` for all reorder dialog tests.

- [ ] **Step 5: Commit the new dialog**

```bash
git add tests/test_plugin_reorder_dialog.py src/atv_player/ui/plugin_reorder_dialog.py
git commit -m "feat: add dedicated plugin reorder dialog"
```

### Task 4: Wire the Reorder Dialog Into Plugin Manager

**Files:**
- Modify: [src/atv_player/ui/plugin_manager_dialog.py](/home/harold/workspace/atv-player/src/atv_player/ui/plugin_manager_dialog.py:52)
- Modify: [tests/test_plugin_manager_dialog.py](/home/harold/workspace/atv-player/tests/test_plugin_manager_dialog.py:30)

- [ ] **Step 1: Write the failing integration tests**

Extend `FakePluginManager` in `tests/test_plugin_manager_dialog.py` and add these tests near the existing move-button coverage:

```python
    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        by_id = {plugin.id: plugin for plugin in self.plugins}
        self.plugins = [by_id[plugin_id] for plugin_id in plugin_ids_in_order]
        for sort_order, plugin in enumerate(self.plugins):
            plugin.sort_order = sort_order
```

```python
def test_plugin_manager_dialog_exposes_reorder_button(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.reorder_button.text() == "调整顺序"


def test_plugin_manager_dialog_opens_reorder_dialog_and_reloads_on_accept(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    reload_calls: list[str] = []
    original_reload = dialog.reload_plugins

    def tracked_reload() -> None:
        reload_calls.append("reload")
        original_reload()

    class FakeReorderDialog:
        def __init__(self, plugin_manager, parent=None) -> None:
            assert plugin_manager is manager
            assert parent is dialog

        def exec(self) -> int:
            manager.reorder_plugins([2, 1])
            return PluginManagerDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "reload_plugins", tracked_reload)
    monkeypatch.setattr(plugin_manager_dialog_module, "PluginReorderDialog", FakeReorderDialog)

    dialog._open_reorder_dialog()

    assert reload_calls == ["reload"]
    assert [plugin.id for plugin in manager.plugins] == [2, 1]


def test_plugin_manager_dialog_does_not_reload_when_reorder_dialog_is_cancelled(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    reload_calls: list[str] = []

    class FakeReorderDialog:
        def __init__(self, plugin_manager, parent=None) -> None:
            pass

        def exec(self) -> int:
            return PluginManagerDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "reload_plugins", lambda: reload_calls.append("reload"))
    monkeypatch.setattr(plugin_manager_dialog_module, "PluginReorderDialog", FakeReorderDialog)

    dialog._open_reorder_dialog()

    assert reload_calls == []
```

- [ ] **Step 2: Run the plugin manager dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "reorder_button or open_reorder_dialog" -v
```

Expected: `FAIL` because the dialog has no `reorder_button` and no `_open_reorder_dialog`.

- [ ] **Step 3: Implement the plugin manager integration**

Update `src/atv_player/ui/plugin_manager_dialog.py`:

```python
from atv_player.ui.plugin_reorder_dialog import PluginReorderDialog
```

Add a new button in `__init__`:

```python
        self.reorder_button = QPushButton("调整顺序")
```

Insert it into the action row after `self.down_button`, then wire it:

```python
        self.reorder_button.clicked.connect(self._open_reorder_dialog)
```

Keep the button enabled unless a refresh is in progress:

```python
            self.reorder_button.setEnabled(False)
```

```python
        self.reorder_button.setEnabled(True)
```

Add the dialog launcher:

```python
    def _open_reorder_dialog(self) -> None:
        dialog = PluginReorderDialog(self.plugin_manager, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()
```

Do not remove `up_button` or `down_button`; the dedicated dialog complements them.

- [ ] **Step 4: Run the UI tests to verify the integration**

Run:

```bash
uv run pytest tests/test_plugin_reorder_dialog.py tests/test_plugin_manager_dialog.py -k "reorder" -v
```

Expected: `PASS` for the new dedicated-dialog tests and the plugin manager integration tests.

- [ ] **Step 5: Run the full plugin-related regression slice**

Run:

```bash
uv run pytest tests/test_storage.py tests/test_spider_plugin_manager.py tests/test_plugin_reorder_dialog.py tests/test_plugin_manager_dialog.py -v
```

Expected: `PASS` across repository, manager, dedicated dialog, and main dialog reorder coverage.

- [ ] **Step 6: Commit the UI integration**

```bash
git add tests/test_plugin_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py
git add tests/test_plugin_reorder_dialog.py src/atv_player/ui/plugin_reorder_dialog.py
git commit -m "feat: wire plugin reorder workflow into manager dialog"
```

## Self-Review

### Spec Coverage

- Dedicated reorder entry in main dialog: covered by Task 4.
- Long-distance moves and small adjustments: covered by Task 3 button operations and drag-ready `QListWidget` setup.
- Save once, cancel discards: covered by Task 3 save/cancel tests and implementation.
- Batch persistence through manager/repository: covered by Tasks 1 and 2.
- Stale snapshot rejection: covered by Tasks 1, 2, and Task 3 save-error handling.
- Main dialog keeps existing `上移` / `下移`: preserved explicitly in Task 4.

### Placeholder Scan

- No `TODO`, `TBD`, or omitted command placeholders remain.
- Each code-changing step includes explicit code snippets.
- Each verification step includes exact commands and expected outcomes.

### Type Consistency

- Repository API: `reorder_plugins(plugin_ids_in_order: list[int])`
- Manager API: `reorder_plugins(plugin_ids_in_order: list[int])`
- Dialog save path: `self.plugin_manager.reorder_plugins(self._ordered_plugin_ids())`
- Error text for stale snapshots is consistently `插件列表已变化，请重新打开排序窗口`

