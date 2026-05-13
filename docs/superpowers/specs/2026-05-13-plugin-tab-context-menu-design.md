# Plugin Tab Context Menu Design

## Goal

Add a right-click context menu to spider-plugin entries in the main window so users can manage a plugin directly from:

- visible plugin tabs in the main tab bar
- hidden plugin entries inside the overflow drawer

The menu should provide:

- `重新加载`
- `编辑名称`
- `编辑配置`
- `启用` or `禁用` depending on current state

This feature should reuse the existing plugin-manager capabilities instead of introducing a second management path with different behavior.

## Scope

This change covers:

- main-window plugin tab context menus
- overflow-drawer plugin item context menus
- shared execution logic for the four plugin actions
- partial tab rebuild behavior in the main window after plugin changes
- tests for the new menu actions and refresh behavior

This change does not cover:

- adding new actions to the plugin manager dialog
- changing plugin manager table interactions
- changing plugin ordering behavior
- changing overflow layout rules

## Current Context

The project already has:

- `PluginManagerDialog` with implementations for rename, config edit, enable toggle, and plugin refresh
- `MainWindow._reload_changed_plugin_tabs(...)` for rebuilding only changed plugin tabs by plugin id
- `PluginTabDrawer` for hidden plugin navigation when tabs overflow

The missing piece is a direct management entry point from the plugin tab UI itself.

## Design Overview

Introduce a shared plugin-action helper that encapsulates the four plugin management actions and the associated prompts. The main window will use that helper from two entry points:

- right-click on a visible plugin tab in the tab bar
- right-click on a hidden plugin item in `PluginTabDrawer`

After a successful action, the main window will refresh only the affected plugin tab state using existing plugin-manager APIs and the existing partial tab rebuild path.

`PluginManagerDialog` may also use the same helper so prompts and action semantics stay aligned across both UIs.

## Interaction Design

### Visible Plugin Tabs

When the user right-clicks a visible spider-plugin tab:

- show a context menu anchored to that tab
- include `重新加载`, `编辑名称`, `编辑配置`, and either `启用` or `禁用`
- left-click tab switching remains unchanged

Only spider-plugin tabs should show this menu. Built-in tabs such as `豆瓣电影`, `电报影视`, `网络直播`, `文件浏览`, and `播放记录` should not expose it.

### Hidden Plugin Drawer Items

When the user right-clicks a hidden plugin item in the overflow drawer:

- show the same context menu
- target the plugin represented by that drawer item
- keep existing left-click selection behavior unchanged

This ensures the same management operations are available whether the plugin is visible in the top row or currently hidden by overflow.

### Toggle Label

The enable action label should reflect the current state:

- enabled plugin: show `禁用`
- disabled plugin: show `启用`

This is clearer than a fixed `启用/禁用` label because the user can see the exact action that will happen.

## Shared Action Execution

Create a shared action executor around the existing `plugin_manager` methods:

- `refresh_plugin(plugin_id)`
- `rename_plugin(plugin_id, display_name)`
- `set_plugin_config(plugin_id, config_text)`
- `set_plugin_enabled(plugin_id, enabled)`

The shared helper should also own:

- prompting for display name
- prompting for config text
- consistent cancel handling
- consistent warning dialogs for action failures

This keeps action semantics in one place and avoids duplicating prompt and error logic between `MainWindow` and `PluginManagerDialog`.

## Post-Action Main-Window Behavior

After a successful action from the main window:

- treat the plugin as changed by id
- refresh the main-window plugin definitions for that plugin id
- rebuild only the affected plugin tab state instead of rebuilding every plugin tab

The existing `MainWindow._reload_changed_plugin_tabs(...)` path is the primary mechanism for this.

## Action-Specific Behavior

### Reload

`重新加载` should:

- call `plugin_manager.refresh_plugin(plugin_id)`
- then call the changed-plugin tab reload path in the main window

This is a plugin-level refresh, not a page-content reload. The plugin source, cached file, and loaded controller definition should be refreshed first, and the corresponding tab/page should then be rebuilt.

If refresh succeeds and the plugin still loads normally, the old plugin page instance is replaced with a new one.

If refresh updates repository state but the plugin can no longer be loaded into a controller definition, the plugin tab disappears from the enabled tab set. This matches the existing plugin-manager behavior and keeps the UI consistent with actual loadability.

### Edit Name

`编辑名称` should:

- prompt with the current display name
- do nothing on cancel or empty trimmed input
- save the new display name through `rename_plugin(...)`
- trigger changed-plugin tab reload in the main window

Although title-only updates do not strictly require recreating the controller, using the same changed-plugin reload path keeps behavior simple and consistent.

### Edit Config

`编辑配置` should:

- prompt with the current raw config text
- do nothing on cancel
- save through `set_plugin_config(...)`
- trigger changed-plugin tab reload in the main window

This ensures the current plugin tab gets rebuilt with a fresh controller/page bound to the updated config instead of leaving an older in-memory instance alive.

### Enable or Disable

The menu should inspect current plugin state and offer:

- `禁用` if the plugin is enabled
- `启用` if the plugin is disabled

Executing the action should:

- call `set_plugin_enabled(plugin_id, target_state)`
- trigger changed-plugin tab reload in the main window

If disabling removes the currently active plugin tab:

- the main window should switch to a stable fallback visible tab
- prefer preserving normal navigation flow rather than leaving the current widget on a removed plugin page
- falling back to the first available visible tab is acceptable

If enabling restores the plugin:

- insert it back according to current plugin sort order
- re-apply normal overflow splitting rules

## Overflow Drawer Synchronization

After a successful action triggered from the overflow drawer:

- refresh the hidden-plugin drawer item list immediately
- preserve the current overflow logic

If the target plugin:

- remains enabled but hidden, keep it in the drawer with updated title/state
- becomes visible because the plugin set changed, remove it from the drawer naturally through normal recomputation
- becomes disabled or unloadable, remove it from the drawer

If no hidden plugins remain after the update:

- close the drawer
- hide the `更多` button if appropriate under the existing rules

## Error Handling

`refresh_plugin(...)` already records refresh failures in repository state and plugin logs instead of raising. The main-window action flow should keep using that contract.

For main-window initiated actions:

- rename/config/enable-toggle exceptions should show `QMessageBox.warning(...)`
- on those failures, do not mutate current tab structure

For reload:

- call the changed-plugin reload path after refresh completes
- if the plugin can no longer be loaded into a definition, remove it from the active plugin tab set

This preserves consistency between stored plugin state and the tabs shown in the main window.

## UI Architecture

### Main Window

`MainWindow` should gain:

- a way to map tab-bar right-click positions back to plugin tab definitions
- a method to open a plugin context menu for a specific plugin id
- a shared success path that reloads changed plugin tabs by id

The context menu should operate by plugin id, not by current visibility mode, so both visible tabs and hidden drawer items can use the same action handler.

### Plugin Overflow Drawer

`PluginTabDrawer` should gain:

- a context-menu signal carrying the target plugin key
- right-click support on list items

It should remain focused on item presentation and event emission, not on plugin management logic.

### Shared Helper

Introduce a reusable helper or controller for plugin actions that:

- receives a `plugin_manager`
- can fetch current plugin rows
- exposes methods for reload, rename, config edit, and enable toggle
- returns a structured result indicating whether a plugin changed and which plugin id was affected

This helper should be UI-oriented enough to own prompts and warnings, but not tied specifically to the plugin manager dialog.

## Testing

Add coverage in `tests/test_main_window_ui.py` for:

- right-clicking a visible plugin tab and invoking `重新加载`
- right-clicking a visible plugin tab and invoking `编辑名称`
- right-clicking a visible plugin tab and invoking `编辑配置`
- right-clicking a visible plugin tab and invoking `启用` or `禁用`
- right-clicking a hidden plugin drawer item and invoking the same actions
- disabling the currently active plugin tab and switching to a fallback visible tab
- drawer contents refreshing after plugin rename/disable/reload

Add focused tests for the shared helper covering:

- prompt cancel or empty-input behavior
- correct plugin-manager method dispatch
- warning dialog behavior on exceptions
- changed-plugin result reporting

## Acceptance Criteria

The feature is complete when:

- visible spider-plugin tabs show the right-click menu
- hidden overflow-drawer plugin items show the same right-click menu
- built-in non-plugin tabs do not show the menu
- reload refreshes plugin source/definition and rebuilds the corresponding tab
- editing name updates the plugin tab title through the shared reload path
- editing config rebuilds the plugin with the new config
- enable/disable updates plugin visibility and tab membership correctly
- disabling the active plugin does not leave the main window on a removed page
- drawer content stays in sync with hidden plugin state after actions
- failures show warnings or follow existing refresh semantics without corrupting tab state
