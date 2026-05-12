# Clickable Player Detail Fields Design

## Summary

Extend spider-plugin player detail fields so `detailContent()` and `playerContent()` may return clickable values in the existing `ext` payload.

This lets plugins expose source-specific detail rows such as:

```python
{
    "label": "演员",
    "value": [
        {
            "label": "演员1",
            "action": {"type": "search", "value": "演员1"},
        },
        {
            "label": "演员2",
            "action": {"type": "detail", "value": "actor-detail-2"},
        },
    ],
}
```

The player should render these entries in the right-side detail area and allow clicking each value item independently.

Supported first-release actions:

- `category`
- `detail`
- `search`
- `link`

The change is intentionally scoped to spider-plugin detail payload mapping, player detail rendering, and main-window navigation. Existing plugins that return plain text `ext` rows must keep working unchanged.

## Goals

- Preserve existing plain-text `ext` behavior.
- Let spider plugins provide clickable detail values at both collection and current-item levels.
- Support one field value containing multiple clickable entries.
- Route `category`, `detail`, and `search` clicks through the current spider plugin controller.
- Route `link` clicks to the system external browser.
- Keep the player window source-agnostic outside the shared callback contract.

## Non-Goals

- Generalize clickable detail fields to every controller in the app.
- Add rich text, icons, badges, or nested menus to detail fields.
- Add custom per-action parameters beyond `type` and `value` in the first release.
- Merge current-item and collection-level field rows by label.
- Persist clicked detail-field navigation state separately from normal browse/search state.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/ui/main_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`
- `tests/test_main_window_ui.py`

Primary documentation follow-up should live in:

- `docs/python-spider-player-actions.md`

## Payload Contract

`detailContent(...).list[0].ext` and `playerContent(...).ext` continue to accept the existing payload:

```python
"ext": [
    {"label": "播放", "value": "12万"},
]
```

They also accept two new value shapes:

```python
"ext": [
    {"label": "演员", "value": ["演员1", "演员2"]},
    {
        "label": "演员",
        "value": [
            {"label": "演员1", "action": {"type": "search", "value": "演员1"}},
            {"label": "演员2", "action": {"type": "detail", "value": "actor-2"}},
        ],
    },
]
```

Contract rules:

- `ext` is optional.
- `ext` must be a list to be considered.
- each entry must provide a non-blank `label`.
- `value` may be:
  - a non-blank scalar value
  - a list of non-blank scalar values
  - a list of objects with non-blank `label`
- clickable object items may provide an optional `action`.
- malformed rows or malformed value items are ignored rather than failing playback.
- source ordering is preserved for rows and value items.
- rows without any remaining displayable value items are dropped.

## Action Contract

Add a shared action model for clickable detail values:

- `PlaybackDetailFieldAction(type: str, value: str)`

Supported action types:

- `category`
- `detail`
- `search`
- `link`

Rules:

- both `type` and `value` are required for an action to be clickable.
- unknown `type` values are treated as non-clickable display text.
- blank `value` disables the action.
- `link.value` must be a full external URL.
- `category`, `detail`, and `search` use the active spider plugin controller associated with the current player session.

## Data Model

Extend the existing detail-field model instead of introducing a parallel structure:

- `PlaybackDetailField(label: str, value_parts: list[PlaybackDetailValuePart])`
- `PlaybackDetailValuePart(label: str, action: PlaybackDetailFieldAction | None = None)`

Reasoning:

- one field label may now map to multiple independently clickable value items
- a normalized `value_parts` list keeps rendering simple and deterministic
- plain-text legacy rows become a single `value_parts` item with no action

The existing collection-level and item-level storage remains:

- `VodItem.detail_fields`
- `PlayItem.detail_fields`

## Controller Behavior

`SpiderPluginController.build_request()` should:

1. parse `detailContent(...).list[0].ext`
2. normalize it into `VodItem.detail_fields`
3. leave every playlist item with empty `detail_fields` at request-build time

`SpiderPluginController._resolve_play_item()` should continue to resolve playback URL, parse requirement, headers, actions, subtitles, qualities, and danmaku. In addition, after `playerContent(...)` succeeds, it should normalize `payload.get("ext")` into the current `PlayItem.detail_fields`.

Normalization rules:

- scalar values become one plain `value_part`
- scalar arrays become multiple plain `value_parts`
- object arrays become `value_parts` with optional normalized actions
- invalid actions downgrade to plain display text instead of rejecting the row
- each playback resolution overwrites any stale `PlayItem.detail_fields`

## Display Priority

The player should keep the current whole-list override model:

1. If the current `PlayItem.detail_fields` is non-empty, display that list.
2. Otherwise, display `VodItem.detail_fields`.
3. If neither level has fields, hide the custom-detail-fields widget.

The first release should not merge collection-level and item-level rows by label.

## Player UI

The right-side detail panel already contains:

- poster
- detail action buttons
- fixed metadata block
- playback log

Replace the current plain-text-only custom-field rendering with a dedicated widget block between the detail action buttons and the fixed metadata block.

Rendering rules:

- one visual row per normalized field
- render the row label once on the left
- render value items on the right in source order
- plain items use normal label text
- clickable items use link-like styling and pointing-hand cursor
- multiple items in one row are separated with ` / `
- hide the block entirely when there are no displayable fields
- preserve the fixed metadata block below it

This avoids trying to make `QTextEdit` partially interactive while keeping the visual placement unchanged.

## Session Callback Contract

Add a dedicated callback to player session wiring:

- `detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None`

This callback is intentionally separate from `detail_action_runner` because:

- detail actions are button-style source actions that return refreshed button state
- detail field clicks are navigation/open-link intents with no action-list refresh contract

`OpenPlayerRequest` should carry the callback and `PlayerController.create_session()` should copy it into `PlayerSession`.

## Navigation Behavior

For spider-plugin sessions, `MainWindow` should supply the detail-field callback.

Action routing rules:

- `category`
  - call the current plugin controller's `load_items(action.value, 1)`
  - switch back to the matching plugin tab
  - show the loaded first-page result list
- `search`
  - call the current plugin controller's `search_items(action.value, 1)`
  - switch back to the matching plugin tab
  - show the loaded first-page result list
- `detail`
  - call the current plugin controller's `build_request(action.value)`
  - open the returned player request immediately
- `link`
  - open `action.value` with the system external browser

The player window only dispatches the click. It does not call spider APIs or open browsers directly.

## Main-Window Integration

The callback provided by `MainWindow` should:

- identify the plugin tab and page associated with the current player session
- run `category` and `search` loads asynchronously using the existing media-load path
- reuse existing player-open flow for `detail`
- report failures into the player log instead of crashing the player window

For `category` and `search`, the main window should be shown again so the user can see the result list immediately.

## Error Handling

Clickable detail fields must never block playback.

Rules:

- invalid `ext` payloads are ignored
- invalid action payloads downgrade to non-clickable text
- unsupported session types simply expose no clickable behavior
- failed `category`, `search`, or `detail` loads append an error message to the player log
- failed external-link open attempts append an error message to the player log

No click should tear down the current player session unless opening a new `detail` request succeeds.

## Testing Strategy

Add controller tests for:

- mapping legacy plain-text `ext` rows unchanged
- mapping scalar-array values into multiple plain display items
- mapping object-array values into clickable items with normalized actions
- downgrading malformed actions to non-clickable text
- preserving collection-level versus item-level override behavior

Add player-window tests for:

- rendering plain custom detail fields
- rendering clickable value items
- showing multiple clickable items with separators
- invoking the session callback with the clicked normalized action
- hiding the custom-detail-fields block when no fields exist

Add main-window tests for:

- `category` click loading plugin category results and switching to the plugin tab
- `search` click loading plugin search results and switching to the plugin tab
- `detail` click opening a new plugin player request
- `link` click attempting to open the external browser
- click failures appending a player status log message
