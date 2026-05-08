# Spider Plugin Manager Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable custom-action mechanism so spider plugins can register actions in the plugin manager dialog and execute plugin-owned QR-login dialogs through a constrained host context.

**Architecture:** Add typed host-side action models in `models.py`, let `SpiderPluginManager` discover and normalize plugin-declared actions plus execute them through a constrained context, and update `PluginManagerDialog` to render per-plugin dynamic action buttons separately from the fixed host management buttons. Keep the host synchronous and keep plugin-specific dialog logic entirely inside the plugin.

**Tech Stack:** Python 3.13, PySide6, pytest, sqlite-backed plugin repository, existing spider plugin loader/manager architecture

---

## File Structure

- `src/atv_player/models.py`
  Adds host-side dataclasses for normalized plugin actions and the constrained action execution context.
- `src/atv_player/plugins/__init__.py`
  Extends `SpiderPluginManager` with action discovery, normalization, execution, plugin log plumbing, and small helper methods for loading and naming plugins consistently.
- `src/atv_player/ui/plugin_manager_dialog.py`
  Adds the dynamic “插件动作” area, updates selection handling, and dispatches custom plugin actions from the dialog.
- `tests/test_spider_plugin_manager.py`
  Covers action normalization, invalid-action filtering, undeclared-action rejection, and action execution context behavior.
- `tests/test_plugin_manager_dialog.py`
  Covers the dialog empty state, dynamic action rendering, action dispatch, and post-action reload behavior.

## Task 1: Add Host-Side Action Models And Manager Action Discovery

**Files:**
- Modify: `src/atv_player/models.py:224-260`
- Modify: `src/atv_player/plugins/__init__.py:1-197`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Write the failing manager discovery tests**

Add these imports near the top of `tests/test_spider_plugin_manager.py`:

```python
from atv_player.models import SpiderPluginAction, SpiderPluginConfig
```

Add these helper classes below `HistoryLoader`:

```python
class ActionSpider(FakeSpider):
    def getManagerActions(self):
        return [
            {"id": "qr_login", "label": "扫码登录"},
            {
                "id": "refresh_cookie",
                "label": "刷新 Cookie",
                "enabled": False,
                "tooltip": "需要先扫码登录",
            },
            {"id": "hidden_action", "label": "隐藏动作", "visible": False},
        ]


class InvalidActionSpider(FakeSpider):
    def getManagerActions(self):
        return [
            "bad-payload",
            {"id": "", "label": "缺少 id"},
            {"id": "missing_label"},
        ]


class ActionLoader(FakeLoader):
    def load(self, config: SpiderPluginConfig, force_refresh: bool = False) -> LoadedSpiderPlugin:
        loaded = super().load(config, force_refresh=force_refresh)
        return LoadedSpiderPlugin(
            config=loaded.config,
            spider=ActionSpider(),
            plugin_name="红果短剧",
            search_enabled=False,
        )


class InvalidActionLoader(FakeLoader):
    def load(self, config: SpiderPluginConfig, force_refresh: bool = False) -> LoadedSpiderPlugin:
        loaded = super().load(config, force_refresh=force_refresh)
        return LoadedSpiderPlugin(
            config=loaded.config,
            spider=InvalidActionSpider(),
            plugin_name="坏动作插件",
            search_enabled=False,
        )
```

Add these tests:

```python
def test_manager_list_plugin_actions_normalizes_visible_actions(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")
    manager = SpiderPluginManager(repository, ActionLoader())

    actions = manager.list_plugin_actions(plugin.id)

    assert actions == [
        SpiderPluginAction(id="qr_login", label="扫码登录"),
        SpiderPluginAction(
            id="refresh_cookie",
            label="刷新 Cookie",
            enabled=False,
            tooltip="需要先扫码登录",
        ),
    ]


def test_manager_list_plugin_actions_ignores_invalid_payloads_and_logs_reasons(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/bad.py", "坏动作插件")
    manager = SpiderPluginManager(repository, InvalidActionLoader())

    actions = manager.list_plugin_actions(plugin.id)
    logs = repository.list_logs(plugin.id)

    assert actions == []
    assert any("插件动作声明无效" in entry.message for entry in logs)


def test_manager_list_plugin_actions_returns_empty_for_plugins_without_action_api(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/plain.py", "普通插件")
    manager = SpiderPluginManager(repository, FakeLoader())

    assert manager.list_plugin_actions(plugin.id) == []
```

- [ ] **Step 2: Run the targeted manager tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "list_plugin_actions" -v
```

Expected:

```text
FAILED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_normalizes_visible_actions
FAILED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_ignores_invalid_payloads_and_logs_reasons
FAILED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_returns_empty_for_plugins_without_action_api
```

The first failure should mention that `SpiderPluginAction` or `SpiderPluginManager.list_plugin_actions` does not exist yet.

- [ ] **Step 3: Add the minimal host-side models**

In `src/atv_player/models.py`, insert these dataclasses after `SpiderPluginLogEntry`:

```python
@dataclass(slots=True)
class SpiderPluginAction:
    id: str
    label: str
    enabled: bool = True
    visible: bool = True
    tooltip: str = ""


@dataclass(slots=True)
class SpiderPluginActionContext:
    parent: object | None
    plugin_id: int
    plugin_name: str
    config_text: str
    set_config_text: Callable[[str], None]
    refresh_plugin: Callable[[], None]
    log: Callable[[str, str], None]
```

In `src/atv_player/plugins/__init__.py`, expand the import to:

```python
from atv_player.models import SpiderPluginAction, SpiderPluginActionContext, SpiderPluginConfig
```

Then add these helpers above `SpiderPluginManager`:

```python
def _coerce_plugin_action(payload: object) -> SpiderPluginAction | None:
    if not isinstance(payload, dict):
        return None
    action_id = str(payload.get("id") or "").strip()
    label = str(payload.get("label") or "").strip()
    if not action_id or not label:
        return None
    return SpiderPluginAction(
        id=action_id,
        label=label,
        enabled=bool(payload.get("enabled", True)),
        visible=bool(payload.get("visible", True)),
        tooltip=str(payload.get("tooltip") or "").strip(),
    )
```

Add these methods inside `SpiderPluginManager`:

```python
    def _get_plugin(self, plugin_id: int) -> SpiderPluginConfig:
        return self._repository.get_plugin(plugin_id)

    def _load_plugin(self, plugin_id: int, *, force_refresh: bool = False) -> tuple[SpiderPluginConfig, LoadedSpiderPlugin]:
        plugin = self._get_plugin(plugin_id)
        return plugin, self._loader.load(plugin, force_refresh=force_refresh)

    def _plugin_title(self, plugin: SpiderPluginConfig, loaded: LoadedSpiderPlugin) -> str:
        return plugin.display_name or loaded.plugin_name or _default_plugin_name(
            plugin.source_type, plugin.source_value
        )

    def list_plugin_actions(self, plugin_id: int) -> list[SpiderPluginAction]:
        plugin, loaded = self._load_plugin(plugin_id)
        get_actions = getattr(loaded.spider, "getManagerActions", None)
        if not callable(get_actions):
            return []
        actions: list[SpiderPluginAction] = []
        for payload in get_actions() or []:
            action = _coerce_plugin_action(payload)
            if action is None:
                self._repository.append_log(plugin.id, "error", f"插件动作声明无效: {payload!r}")
                continue
            if action.visible:
                actions.append(action)
        return actions
```

- [ ] **Step 4: Run the targeted manager tests to verify they pass**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "list_plugin_actions" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_normalizes_visible_actions
PASSED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_ignores_invalid_payloads_and_logs_reasons
PASSED tests/test_spider_plugin_manager.py::test_manager_list_plugin_actions_returns_empty_for_plugins_without_action_api
```

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/plugins/__init__.py tests/test_spider_plugin_manager.py
git commit -m "feat: add spider plugin manager action discovery"
```

## Task 2: Add Action Execution Context And Manager Dispatch

**Files:**
- Modify: `src/atv_player/plugins/__init__.py:33-197`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Write the failing action execution tests**

Add these helper classes below `InvalidActionLoader`:

```python
class RunnableActionSpider(FakeSpider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def getManagerActions(self):
        return [{"id": "qr_login", "label": "扫码登录"}]

    def runManagerAction(self, action_id: str, context) -> None:
        self.calls.append((action_id, context.parent))
        context.log("info", f"执行动作: {action_id}")
        context.set_config_text("token=updated\ncookie=1\n")
        context.refresh_plugin()


class RunnableActionLoader(FakeLoader):
    def __init__(self) -> None:
        self.spider = RunnableActionSpider()
        self.force_refresh_calls: list[bool] = []

    def load(self, config: SpiderPluginConfig, force_refresh: bool = False) -> LoadedSpiderPlugin:
        self.force_refresh_calls.append(force_refresh)
        loaded = super().load(config, force_refresh=force_refresh)
        return LoadedSpiderPlugin(
            config=loaded.config,
            spider=self.spider,
            plugin_name="红果短剧",
            search_enabled=False,
        )
```

Add these tests:

```python
def test_manager_run_plugin_action_provides_context_and_persists_side_effects(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")
    loader = RunnableActionLoader()
    manager = SpiderPluginManager(repository, loader)

    parent = object()

    manager.run_plugin_action(plugin.id, "qr_login", parent=parent)

    saved = repository.get_plugin(plugin.id)
    logs = repository.list_logs(plugin.id)
    assert loader.spider.calls == [("qr_login", parent)]
    assert saved.config_text == "token=updated\ncookie=1\n"
    assert any(entry.message == "执行动作: qr_login" for entry in logs)
    assert loader.force_refresh_calls[-1] is True


def test_manager_run_plugin_action_rejects_undeclared_action(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")
    manager = SpiderPluginManager(repository, ActionLoader())

    with pytest.raises(ValueError, match="插件动作未注册: missing_action"):
        manager.run_plugin_action(plugin.id, "missing_action")
```

If `pytest` is not already imported in the file, add:

```python
import pytest
```

- [ ] **Step 2: Run the targeted manager execution tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "run_plugin_action" -v
```

Expected:

```text
FAILED tests/test_spider_plugin_manager.py::test_manager_run_plugin_action_provides_context_and_persists_side_effects
FAILED tests/test_spider_plugin_manager.py::test_manager_run_plugin_action_rejects_undeclared_action
```

The failure should mention that `SpiderPluginManager.run_plugin_action` does not exist yet.

- [ ] **Step 3: Implement manager action execution**

In `src/atv_player/plugins/__init__.py`, add these helper methods inside `SpiderPluginManager`:

```python
    def _append_plugin_log(self, plugin_id: int, level: str, message: str) -> None:
        self._repository.append_log(plugin_id, level, message)

    def _build_action_context(
        self,
        plugin: SpiderPluginConfig,
        loaded: LoadedSpiderPlugin,
        *,
        parent=None,
    ) -> SpiderPluginActionContext:
        return SpiderPluginActionContext(
            parent=parent,
            plugin_id=plugin.id,
            plugin_name=self._plugin_title(plugin, loaded),
            config_text=plugin.config_text,
            set_config_text=lambda text, plugin_id=plugin.id: self.set_plugin_config(plugin_id, text),
            refresh_plugin=lambda plugin_id=plugin.id: self.refresh_plugin(plugin_id),
            log=lambda level, message, plugin_id=plugin.id: self._append_plugin_log(plugin_id, level, message),
        )
```

Then add the public execution method:

```python
    def run_plugin_action(self, plugin_id: int, action_id: str, parent=None) -> None:
        actions = self.list_plugin_actions(plugin_id)
        action = next((item for item in actions if item.id == action_id), None)
        if action is None:
            raise ValueError(f"插件动作未注册: {action_id}")
        plugin, loaded = self._load_plugin(plugin_id)
        runner = getattr(loaded.spider, "runManagerAction", None)
        if not callable(runner):
            raise ValueError(f"插件不支持动作执行: {action_id}")
        context = self._build_action_context(plugin, loaded, parent=parent)
        try:
            runner(action_id, context)
        except Exception as exc:
            self._repository.append_log(plugin.id, "error", f"插件动作执行失败[{action_id}]: {exc}")
            raise
```

Do not add new repository APIs here. Reuse `set_plugin_config`, `refresh_plugin`, and `append_log`.

- [ ] **Step 4: Run the targeted manager execution tests to verify they pass**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "run_plugin_action" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_manager.py::test_manager_run_plugin_action_provides_context_and_persists_side_effects
PASSED tests/test_spider_plugin_manager.py::test_manager_run_plugin_action_rejects_undeclared_action
```

- [ ] **Step 5: Run the full manager test module**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -v
```

Expected:

```text
... all tests in tests/test_spider_plugin_manager.py pass ...
```

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/plugins/__init__.py tests/test_spider_plugin_manager.py
git commit -m "feat: add spider plugin action execution context"
```

## Task 3: Render Dynamic Plugin Action Buttons In The Dialog

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py:1-252`
- Test: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Write the failing dialog tests**

Update the imports at the top of `tests/test_plugin_manager_dialog.py`:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView

from atv_player.models import SpiderPluginAction, SpiderPluginConfig, SpiderPluginLogEntry
```

Extend `FakePluginManager.__init__` with:

```python
        self.action_calls: list[tuple[int, str, object]] = []
        self.actions = {
            1: [SpiderPluginAction(id="qr_login", label="扫码登录")],
            2: [
                SpiderPluginAction(
                    id="refresh_cookie",
                    label="刷新 Cookie",
                    enabled=False,
                    tooltip="需要先扫码登录",
                )
            ],
        }
```

Add these methods to `FakePluginManager`:

```python
    def list_plugin_actions(self, plugin_id: int):
        return list(self.actions.get(plugin_id, []))

    def run_plugin_action(self, plugin_id: int, action_id: str, parent=None) -> None:
        self.action_calls.append((plugin_id, action_id, parent))
```

Add these tests:

```python
def test_plugin_manager_dialog_shows_empty_custom_action_state_without_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.clearSelection()
    dialog._sync_action_state()

    assert dialog.plugin_actions_empty_label.text() == "请选择插件以查看自定义动作"
    assert dialog.plugin_action_buttons == []


def test_plugin_manager_dialog_renders_dynamic_plugin_action_buttons(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(1)
    dialog._sync_action_state()

    assert [button.text() for button in dialog.plugin_action_buttons] == ["刷新 Cookie"]
    assert dialog.plugin_action_buttons[0].isEnabled() is False
    assert dialog.plugin_action_buttons[0].toolTip() == "需要先扫码登录"


def test_plugin_manager_dialog_dispatches_plugin_action_and_reloads_plugins(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)
    dialog._sync_action_state()

    reload_calls: list[str] = []
    original_reload = dialog.reload_plugins

    def tracked_reload() -> None:
        reload_calls.append("reload")
        original_reload()

    monkeypatch.setattr(dialog, "reload_plugins", tracked_reload)

    qtbot.mouseClick(dialog.plugin_action_buttons[0], Qt.MouseButton.LeftButton)

    assert manager.action_calls == [(1, "qr_login", dialog)]
    assert reload_calls == ["reload"]
```

- [ ] **Step 2: Run the targeted dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "custom_action or dynamic_plugin_action or dispatches_plugin_action" -v
```

Expected:

```text
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_shows_empty_custom_action_state_without_selection
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_renders_dynamic_plugin_action_buttons
FAILED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_dispatches_plugin_action_and_reloads_plugins
```

The first failure should mention missing dialog attributes such as `plugin_actions_empty_label` or `plugin_action_buttons`.

- [ ] **Step 3: Implement the dialog action area**

In `src/atv_player/ui/plugin_manager_dialog.py`, add these imports:

```python
from functools import partial

from PySide6.QtWidgets import QMessageBox, QWidget
```

In `__init__`, after the fixed `actions` layout, add the new widgets:

```python
        self.plugin_actions_label = QLabel("插件动作")
        self.plugin_actions_empty_label = QLabel("请选择插件以查看自定义动作")
        self.plugin_actions_widget = QWidget(self)
        self.plugin_actions_layout = QHBoxLayout(self.plugin_actions_widget)
        self.plugin_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.plugin_action_buttons: list[QPushButton] = []
```

Then add them to the main layout between the fixed action row and the table:

```python
        layout.addWidget(self.plugin_actions_label)
        layout.addWidget(self.plugin_actions_empty_label)
        layout.addWidget(self.plugin_actions_widget)
```

Add these helper methods to the class:

```python
    def _clear_plugin_action_buttons(self) -> None:
        while self.plugin_actions_layout.count():
            item = self.plugin_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.plugin_action_buttons = []

    def _reload_plugin_actions(self) -> None:
        self._clear_plugin_action_buttons()
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            self.plugin_actions_empty_label.setText("请选择插件以查看自定义动作")
            self.plugin_actions_empty_label.show()
            self.plugin_actions_widget.hide()
            return
        actions = self.plugin_manager.list_plugin_actions(plugin_id)
        if not actions:
            self.plugin_actions_empty_label.setText("该插件没有自定义动作")
            self.plugin_actions_empty_label.show()
            self.plugin_actions_widget.hide()
            return
        self.plugin_actions_empty_label.hide()
        self.plugin_actions_widget.show()
        for action in actions:
            button = QPushButton(action.label, self.plugin_actions_widget)
            button.setEnabled(action.enabled)
            if action.tooltip:
                button.setToolTip(action.tooltip)
            button.clicked.connect(partial(self._run_plugin_action, action.id))
            self.plugin_actions_layout.addWidget(button)
            self.plugin_action_buttons.append(button)
        self.plugin_actions_layout.addStretch(1)

    def _run_plugin_action(self, action_id: str) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        try:
            self.plugin_manager.run_plugin_action(plugin_id, action_id, parent=self)
        except Exception as exc:
            QMessageBox.warning(self, "插件动作失败", str(exc))
            return
        self.reload_plugins()
```

Update `reload_plugins()` and `_sync_action_state()` to call `_reload_plugin_actions()` after table selection state has been updated:

```python
        self._sync_action_state()
        self._reload_plugin_actions()
```

and:

```python
        self._reload_plugin_actions()
```

This keeps the dynamic action area synchronized with the current row selection and reload cycles.

- [ ] **Step 4: Run the targeted dialog tests to verify they pass**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -k "custom_action or dynamic_plugin_action or dispatches_plugin_action" -v
```

Expected:

```text
PASSED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_shows_empty_custom_action_state_without_selection
PASSED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_renders_dynamic_plugin_action_buttons
PASSED tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_dispatches_plugin_action_and_reloads_plugins
```

- [ ] **Step 5: Run the full dialog test module**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py -v
```

Expected:

```text
... all tests in tests/test_plugin_manager_dialog.py pass ...
```

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/plugin_manager_dialog.py tests/test_plugin_manager_dialog.py
git commit -m "feat: add plugin manager custom action buttons"
```

## Task 4: Final Verification

**Files:**
- Modify: none
- Test: `tests/test_spider_plugin_manager.py`, `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py -v
```

Expected:

```text
... all tests in both modules pass ...
```

- [ ] **Step 2: Review the changed files**

Run:

```bash
git diff -- src/atv_player/models.py src/atv_player/plugins/__init__.py src/atv_player/ui/plugin_manager_dialog.py tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py
```

Expected:

```text
Diff only shows the new action dataclasses, manager action APIs, dialog action UI, and corresponding tests.
```

- [ ] **Step 3: Commit the final verification checkpoint**

```bash
git add src/atv_player/models.py src/atv_player/plugins/__init__.py src/atv_player/ui/plugin_manager_dialog.py tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py
git commit -m "test: verify spider plugin manager actions flow"
```
