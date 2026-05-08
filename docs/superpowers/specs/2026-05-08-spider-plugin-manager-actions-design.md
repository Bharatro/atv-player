# Spider Plugin Manager Actions Design

## Summary

Add a host-defined custom action mechanism for spider plugins in the plugin manager dialog. The first target is QR-code login flows: the plugin manager should discover per-plugin custom actions, render them for the selected plugin, and let the plugin open and manage its own secondary dialog when the user triggers an action.

## Goals

- Let a spider plugin declare one or more custom actions for the plugin manager.
- Keep the plugin manager dialog responsible only for action discovery, presentation, and dispatch.
- Let the plugin own the action business logic and any secondary dialog UI, including QR-code rendering and login polling.
- Provide a controlled host context so plugins can update config, refresh themselves, and append plugin logs without touching repository internals.
- Keep the action contract reusable for future host entry points without implementing a global command system now.

## Non-Goals

- Building a host-provided generic QR-code login dialog.
- Adding a global plugin command framework for the whole application.
- Supporting arbitrary action parameter forms in the host UI.
- Moving plugin action execution onto a new async task framework.
- Exposing repository or other internal persistence primitives directly to plugins.

## Scope

Primary implementation lives in:

- `src/atv_player/models.py`
- `src/atv_player/plugins/loader.py`
- `src/atv_player/plugins/__init__.py`
- `src/atv_player/ui/plugin_manager_dialog.py`

Primary verification lives in:

- `tests/test_spider_plugin_manager.py`
- `tests/test_plugin_manager_dialog.py`

## Design

### Plugin-side contract

Spider plugins may optionally implement two new methods:

```python
def getManagerActions(self) -> list[dict]:
    ...


def runManagerAction(self, action_id: str, context) -> None:
    ...
```

`getManagerActions()` is a declaration-only API. It should not open dialogs or perform login work. Each returned dict must include:

- `id`: stable action identifier, for example `qr_login`
- `label`: button text, for example `扫码登录`

Supported optional keys:

- `enabled`: bool, default `True`
- `visible`: bool, default `True`
- `tooltip`: short explanatory text, typically for disabled actions

`runManagerAction()` is the execution API. The plugin is responsible for opening and managing its own secondary dialog, polling QR-code status, handling success and cancellation, and updating its own config through the provided host context.

If a plugin implements neither method, the host behaves exactly as it does today.

### Host action model

The host should not pass raw plugin dicts directly into the UI. Instead, it normalizes valid declarations into a host-side data model, for example:

```python
@dataclass(slots=True)
class SpiderPluginAction:
    id: str
    label: str
    enabled: bool = True
    visible: bool = True
    tooltip: str = ""
```

This model should live with the other spider-plugin-facing models so the UI and manager can exchange typed data without depending on plugin-owned dictionary shape.

Invalid action payloads should be ignored individually instead of failing the entire plugin. The host should log why an action was ignored.

### Action discovery

Action discovery belongs in the plugin manager service, not directly in the dialog.

Add a manager method such as:

```python
def list_plugin_actions(self, plugin_id: int) -> list[SpiderPluginAction]:
    ...
```

The manager should:

1. load the plugin through the existing loader path
2. inspect the spider instance for `getManagerActions`
3. normalize any declared actions into `SpiderPluginAction`
4. filter out actions with `visible=False` before returning them to the dialog

The dialog should not care whether the plugin is local or remote, whether it required refresh, or how the action definitions were normalized.

### Action execution context

When the user triggers an action, the host calls the plugin through a controlled context instead of exposing repository access.

Add a manager method such as:

```python
def run_plugin_action(self, plugin_id: int, action_id: str, parent=None) -> None:
    ...
```

The manager loads the plugin, validates the requested action against the normalized action list, builds a context object, and passes that context into `runManagerAction(action_id, context)`.

The context should expose only the minimum host services needed for QR-code login style flows:

- `parent`: the Qt parent for plugin-created dialogs
- `plugin_id`
- `plugin_name`
- `config_text`
- `set_config_text(text)`: persist config safely through the manager
- `refresh_plugin()`: trigger the existing plugin refresh flow
- `log(level, message)`: append to plugin logs

The context should not expose raw database connections, the repository instance, or the whole main window.

### Plugin manager dialog

`PluginManagerDialog` should gain a dedicated dynamic action area for the currently selected plugin. The fixed operational buttons remain in place for add/remove/rename/config/refresh management tasks. Custom plugin actions are rendered separately so users can distinguish host management operations from plugin-owned capabilities.

Recommended behavior:

- no selection: hide the action area or show a short empty state
- selected plugin with no actions: show `该插件没有自定义动作`
- selected plugin with actions: render one button per visible action

Button behavior:

- use `label` as the button text
- disable the button when `enabled=False`
- attach `tooltip` when present
- on click, call `plugin_manager.run_plugin_action(plugin_id, action_id, parent=self)`

After action execution returns, the dialog should call `reload_plugins()` to refresh visible plugin state such as `last_error` and `最近加载`.

### Execution flow

The intended flow is:

1. user selects a plugin row
2. dialog asks the manager for current actions
3. dialog renders action buttons
4. user clicks an action button
5. dialog calls `run_plugin_action(...)`
6. manager loads the plugin and validates the action
7. manager calls `runManagerAction(action_id, context)`
8. plugin opens its own secondary dialog and completes its workflow
9. plugin calls `context.set_config_text(...)`, `context.log(...)`, and `context.refresh_plugin()` as needed
10. dialog reloads plugin rows after control returns

The host entry point remains synchronous. The plugin may open a modal dialog and perform its own timers or polling within that UI. The host does not need a new async dispatch mechanism for this first version.

### Compatibility

This feature must remain fully optional:

- old plugins without action APIs continue to work unchanged
- plugins that return no actions simply show no custom actions
- plugin browsing, search, playback, config editing, and refresh behavior remain unchanged

### Error handling

Error handling should be centralized in the manager.

Cases to handle:

- plugin load failure: refuse action execution and surface the current load error
- missing `runManagerAction`: treat as unsupported action execution
- action id not declared by `getManagerActions()`: reject as unregistered action
- invalid action declarations: skip only those actions and log the reason
- exception during action execution: catch it, append a plugin log entry, and surface a concise user-facing error

Config persistence from `context.set_config_text(...)` should use the existing plugin update flow so action-driven config writes behave the same as manual config edits.

`context.refresh_plugin()` should call the existing refresh path so successful QR-code login flows can immediately update cached plugin state and clear any stale load errors.

## Testing

Tests should cover:

- manager normalizes valid plugin action declarations
- manager ignores invalid action payloads without failing the plugin
- manager returns no actions for plugins without `getManagerActions()`
- manager dispatches `run_plugin_action(...)` with a context that can update config and append logs
- manager rejects undeclared actions
- dialog shows the empty state when no plugin action is available
- dialog renders dynamic action buttons for the selected plugin
- dialog dispatches the selected action through the manager and reloads plugin rows afterward

## Result

After this change, spider plugins can optionally declare custom manager actions such as `扫码登录`. The plugin manager dialog discovers and renders those actions for the selected plugin, while the plugin itself retains full control over the secondary dialog and the login workflow. The host provides only a thin, reusable action contract and a constrained execution context.
