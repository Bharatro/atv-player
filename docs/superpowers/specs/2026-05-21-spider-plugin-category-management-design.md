# Spider Plugin Category Management Design

## Goal

Allow users to customize a spider plugin's `homeContent().class` category list without changing the plugin's internal category ids.

Users can:

- reorder categories
- rename category display labels
- hide categories
- restore defaults for the current plugin

The feature must be available from:

- the existing `插件管理` dialog for a single selected plugin
- the main-window plugin tab right-click menu
- the hidden-plugin overflow drawer item right-click menu

## Scope

This change covers:

- per-plugin persistence for category override state
- applying override state when a plugin page loads categories
- a category-management dialog for one plugin at a time
- entry points from plugin manager and main-window plugin tab context menus
- test coverage for persistence, controller mapping, dialog behavior, and menu entry points

This change does not cover:

- changing the plugin protocol
- changing category `type_id`
- affecting history display
- using renamed labels as search or request parameters

## Confirmed Requirements

- The stable key for all category behavior remains the original plugin `type_id`.
- Renaming changes only the displayed category name.
- Plugin category requests and plugin search category parameters continue using the original `type_id`.
- History does not need any category-name integration.
- If the plugin later returns new categories, keep existing customizations and append new categories to the end.
- `恢复默认` clears all category customizations for the current plugin.

## Current Context

The existing spider-plugin flow already has the right boundaries:

- `SpiderPluginController._ensure_home_loaded()` reads `homeContent(False)` and maps `class` into `DoubanCategory`
- `PosterGridPage` already uses `DoubanCategory.type_id` as the selected category key
- plugin management already has:
  - plugin-level sorting
  - plugin tab context menus
  - overflow-drawer plugin context menus
  - partial plugin-tab reload paths

What is missing is a persisted, plugin-local category override layer between raw plugin categories and the UI.

## Design Overview

Add a persisted category-override JSON field to each plugin record and apply that override when `SpiderPluginController` exposes categories to the UI.

The raw plugin payload remains the source of truth for category existence and ids. The override layer changes only:

- returned category order
- returned display labels
- visibility in the category list

This keeps plugin protocol compatibility and avoids mixing UI preferences into plugin runtime config.

## Persistence Model

Store category overrides on the plugin record itself instead of in `config_text` or global app config.

### Why store on `spider_plugins`

Recommended storage: add `category_overrides_json` to `spider_plugins`.

Reasons:

- category customizations are local UI state tied to one plugin
- deleting a plugin should naturally delete its category customizations
- plugin runtime config and plugin category UI overrides stay separate
- the feature needs only a small JSON payload and does not justify a separate table yet

Rejected alternatives:

- storing in `config_text`: mixes plugin runtime config with app-owned UI preferences and risks conflicts with plugin actions that rewrite config
- storing in `app_config`: works, but spreads plugin-owned state across unrelated storage layers

### JSON shape

```json
{
  "order": ["movie", "tv", "variety"],
  "hidden": ["adult"],
  "renames": {
    "movie": "影片",
    "tv": "剧集"
  }
}
```

Rules:

- `order` is a preferred ordering of known `type_id` values
- `hidden` lists category ids that should not be shown in the browsing UI
- `renames` maps original `type_id` to user-defined display labels
- missing or malformed sections are treated as empty
- unknown ids are tolerated and preserved in storage

### Restore defaults

`恢复默认` clears the override JSON for the current plugin. After clearing:

- original plugin category order is used
- original `type_name` labels are used
- no categories are hidden

## Runtime Category Mapping

`SpiderPluginController` continues loading raw categories from `homeContent(False)`, then applies overrides before returning them from `load_categories()`.

### Mapping rules

For each raw category:

- keep the original `type_id`
- use renamed `type_name` if `renames[type_id]` is non-empty
- exclude the category if its `type_id` is in `hidden`

After filtering and renaming:

- categories mentioned in `order` appear first, in that sequence, if they still exist
- remaining visible categories not listed in `order` are appended in raw plugin order

### New categories from plugin updates

If the plugin returns a new category not present in saved overrides:

- do not modify stored overrides automatically
- show the new category at the end of the visible list

This satisfies the confirmed rule: keep existing customizations and append newly discovered categories to the end.

### Missing categories from plugin updates

If a saved override references a `type_id` that the plugin no longer returns:

- ignore it at runtime
- keep it in storage unchanged

If the plugin later returns that category id again, the old rename/order/hidden customization becomes effective again.

## UI Entry Points

### Plugin Manager Dialog

Add a `分类管理` button to `PluginManagerDialog`.

Behavior:

- enabled only when exactly one plugin is selected
- opens the category-management dialog for that plugin
- after a successful save, reload plugin data and mark plugin tabs dirty

This follows the user's requested primary entry point.

### Main-Window Visible Plugin Tabs

Extend the existing plugin tab right-click menu with `分类管理`.

Behavior:

- only shown for spider-plugin tabs
- opens the category-management dialog for the clicked plugin
- after a successful save, reload only the affected plugin tab state

### Hidden Plugin Overflow Drawer

Extend the existing hidden-plugin drawer item right-click menu with the same `分类管理` action.

Behavior:

- the menu targets the plugin represented by the drawer item
- action behavior matches visible plugin tabs

The main window should use the same category-management action path for both right-click entry points.

## Category Management Dialog

Add a dedicated dialog for one plugin at a time.

### Data source

The dialog should work from the plugin's current raw category list plus the saved override state.

This means the dialog needs:

- current plugin metadata
- current raw categories from `homeContent().class`
- current saved overrides

The dialog should not edit live page category objects directly.

### List model

Show all current raw categories in one reorderable list. Hidden categories remain visible inside the dialog so they can be restored without needing a second screen.

Each row should represent one raw `type_id` and include:

- effective display label
- original label when renamed, if useful for clarity
- hidden state

The dialog should preserve a stable association to the raw `type_id` regardless of row moves or label edits.

### Supported actions

The dialog supports:

- `置顶`
- `上移`
- `下移`
- `置底`
- `重命名`
- `隐藏/显示`
- `恢复默认`
- `保存`
- `取消`

### Hidden category presentation

Hidden categories should remain in the list with a clear marker such as `已隐藏`.

This is preferable to removing them from the list because the user needs a direct way to unhide them.

### Rename behavior

Renaming a category:

- edits only the stored override label for that category `type_id`
- does not mutate the raw category id
- if the saved rename is cleared back to empty, fall back to the plugin-provided `type_name`

### Save behavior

Saving writes the full override state for the current plugin:

- current list order converted to `type_id` sequence
- hidden ids collected from row state
- renames collected from edited labels that differ from raw names

The dialog then closes successfully.

### Restore-default behavior

`恢复默认` resets the dialog draft to the plugin's raw category state and clears all pending overrides for that plugin.

This is a current-plugin-wide reset, not a single-category reset.

## Main-Window Refresh Behavior

After category override changes are saved from any entry point:

- rebuild only the affected plugin tab definition
- preserve the rest of the plugin tabs
- if the edited plugin tab is currently open, refresh its page so the category list reflects the new effective categories

No plugin runtime reload is required because category overrides are app-owned UI preferences. The partial tab rebuild path is sufficient.

## Failure Handling

- malformed or empty `category_overrides_json` should be treated as default behavior
- malformed plugin `homeContent().class` payloads should follow existing plugin category error behavior
- if category loading for the dialog fails, show a warning and do not open a broken editor
- save failures should show a warning and keep the dialog open

## Data Model Changes

Add a new field to `SpiderPluginConfig`:

- `category_overrides_json: str = ""`

Add repository migration logic:

- create new column on fresh databases
- add the column to existing databases if missing

Update repository read/write methods so the field round-trips through:

- `add_plugin`
- `get_plugin`
- `list_plugins`
- `update_plugin`
- plugin delete behavior remains unchanged because the field lives on the same row

Add manager methods for:

- reading current category overrides for a plugin
- saving category overrides for a plugin
- loading current raw categories for category management

The category-management flow can reuse the plugin loader/controller path or a lighter raw-category loader helper, but it should not require opening a visible plugin page first.

## Testing

### Repository and manager

- new plugin rows default `category_overrides_json` to empty
- repository migration adds the new column for old databases
- saved override JSON round-trips through repository and manager APIs
- restore-default clears saved overrides

### Controller

- categories are returned in overridden order
- renamed categories keep the original `type_id`
- hidden categories are omitted from returned browsing categories
- categories not mentioned in saved order are appended after ordered categories
- newly returned plugin categories appear at the end without destroying existing overrides

### Category management dialog

- loads raw plugin categories into editable rows
- supports local reorder before save
- supports rename
- supports hide/unhide
- restore-default resets the draft
- save persists the expected override JSON payload

### Plugin manager dialog

- `分类管理` is enabled only for a single selected plugin
- opening and saving category management reloads plugin rows and marks tabs dirty

### Main window and overflow drawer

- visible plugin tab context menu includes `分类管理`
- hidden plugin drawer item context menu includes `分类管理`
- saving category management for one plugin triggers partial plugin-tab refresh only for that plugin

## Non-goals And Future Extensions

This version does not add:

- per-category reset
- import/export of category customizations
- cross-device sync
- user-defined grouping or nested category trees

If the override model grows later, the JSON field can be replaced by a normalized table without changing the user-facing behavior.
