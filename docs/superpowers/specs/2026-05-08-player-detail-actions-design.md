# Player Detail Actions Design

## Summary

Add a unified player-detail action model so the playback sidebar can show source-defined action buttons such as favorite playlist, favorite album, favorite track, and like. The player window should render one shared action area while allowing different playback sources to supply and execute actions through source-specific adapters.

The first implementation scope includes:

- Python spider plugins
- the built-in Bilibili controller

The design keeps the player UI source-agnostic. The player must not infer business meaning such as whether a collection is a playlist or an album. Each source decides which actions exist, what they are called, whether they are active, and how they execute.

## Goals

- Add a shared player-detail action model that can be rendered by the player window for multiple playback sources.
- Let sources provide initial action state when playback detail is resolved.
- Let sources execute an action and return a refreshed action list for state replay.
- Support both collection-level actions and current-track actions without the player needing to understand those concepts.
- Keep current playback running while actions succeed or fail independently.
- Reuse the existing player sidebar instead of adding a new dialog, menu, or management surface.

## Non-Goals

- Introduce a generic action framework for every app surface.
- Expand this first change to all controllers or all plugin types.
- Persist player-detail action state locally inside the player.
- Infer labels like `收藏歌单` or `收藏专辑` in the player.
- Add nested menus, badges, or grouped action sections in the first release.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/controllers/bilibili_controller.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_bilibili_controller.py`
- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

## Design

### Unified Action Model

The player should consume one normalized action model regardless of source.

Add a new lightweight model, for example `PlaybackDetailAction`, with these fields:

- `id: str`
- `label: str`
- `active: bool = False`
- `enabled: bool = True`
- `visible: bool = True`
- `tooltip: str = ""`

Normalization rules:

- `id` and `label` are required
- invisible actions are dropped before rendering
- malformed actions are ignored rather than failing playback
- action order is preserved exactly as provided by the source

The model is intentionally generic. It does not include built-in target types like album, playlist, or track because the player must not encode those business semantics.

### Session and Item State

The player still renders one action list from the current play item, but Python spider plugins may source the initial state from two layers:

- collection-level initial actions from `detailContent(...).list[0].actions`
- current-item actions from `playerContent(...).actions`

Add action state to `PlayItem`:

- `detail_actions: list[PlaybackDetailAction]`

Add an execution callback to `PlayerSession`:

- `detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None`

This keeps the player window simple:

- render from `current_item.detail_actions`
- execute through `session.detail_action_runner`

For Python spider plugins, collection-level initial actions are copied into each play item during request construction, and current-item actions are merged in during playback resolution. This keeps the UI contract unchanged while allowing plugins to declare collection actions at detail-load time, where full container context already exists.

### Source Adapter Pattern

The player window should not know whether an action came from a Python spider plugin or Bilibili. Each source adapter should map its own raw payload and expose the same normalized execution callback.

Two adapters are required in the first release:

- Python spider plugin adapter
- Bilibili controller adapter

### Python Spider Plugin Contract

Extend spider-plugin playback detail so `detailContent(...).list[0]` may optionally return collection-level initial actions:

```python
{
    "vod_id": "detail-1",
    "vod_name": "示例专辑",
    "vod_play_from": "默认线",
    "vod_play_url": "第1首$/play/1#第2首$/play/2",
    "actions": [
        {"id": "favorite_album", "label": "收藏专辑", "active": True},
    ],
}
```

These actions are copied into each generated `PlayItem.detail_actions` before `playerContent()` runs.

`playerContent()` may then optionally return current-item actions:

```python
{
    "parse": 0,
    "url": "https://media.example/song.m4a",
    "actions": [
        {"id": "favorite_track", "label": "收藏歌曲", "active": False},
    ],
}
```

Merge rule:

- `detailContent(...).actions` seeds the initial list
- `playerContent(...).actions` merges into the current play item
- if both layers provide the same action `id`, the `playerContent()` action replaces the earlier one

This split is preferred because `playerContent(flag, id, vipFlags)` only receives the play id and route label, which is often insufficient to infer collection state like playlist, album, or artist membership.

Add an optional spider API:

- `runPlayerAction(action_id, context)`

Execution result contract:

- the method returns either `{"actions": [...]}` or a raw action list
- the returned actions replace the current play item's `detail_actions`
- returning no valid actions means the player refreshes to an empty action list

Suggested context fields:

- `vod`
- `play_item`
- `playlist`
- `playlist_index`
- `play_index`
- `log`

The player should not require plugin authors to declare collection type. If a plugin wants to show `收藏歌单` for one item and `收藏专辑` for another, it does so through `label`.

Recommended plugin guidance:

- use `detailContent(...).actions` for collection-level initial actions such as `收藏歌单`, `收藏专辑`, or `关注歌手`
- use `playerContent(...).actions` for current-item actions such as `收藏歌曲` or `点赞`

### Bilibili Adapter Contract

Bilibili does not use `playerContent()`, so it should adapt its own playback-source payloads into the same `detail_actions` model.

Controller responsibilities:

- when `load_playback_item()` resolves the current playable item, also populate `item.detail_actions`
- provide a `detail_action_runner` callback in the built `OpenPlayerRequest`
- execute Bilibili-specific actions through existing or newly added API client calls, then return a refreshed normalized action list

The Bilibili adapter may support examples such as:

- `收藏歌单`
- `收藏专辑`
- `收藏歌曲`
- `点赞`

Whether one of those appears is entirely decided by Bilibili-side business logic and available metadata.

### Open Request Wiring

`OpenPlayerRequest` should gain:

- `detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None`

`PlayerController.create_session()` should copy this into `PlayerSession`.

This lets every source opt in without special-casing the player window constructor or branching on source kind inside the UI.

### Player Window UI

Add a dedicated action area to the details sidebar:

- place it below the poster
- place it above the `影片详情` heading
- render actions as one wrapping row or stacked rows of `QPushButton`

Behavior rules:

- hide the action container when the current item has no visible actions
- preserve source ordering
- use `active` to render an obvious selected/highlighted state
- use `enabled` to control clickability
- use `tooltip` as the button tooltip

The player window should not create specialized icons or text transformations for actions in the first release. It renders the provided label as-is.

### Refresh Rules

The action area should refresh when:

- a session opens
- the current play item finishes async playback resolution
- the user switches to another play item
- the user switches playlist groups
- an action execution succeeds or returns a replacement action list

The player should always use the current play item's `detail_actions` as the source of truth.

### Execution Flow

When the user clicks a detail action:

1. Verify the session, current item, and action runner still exist.
2. Disable the entire action area to avoid double submission.
3. Execute the action through `session.detail_action_runner(current_item, action_id)`.
4. Replace `current_item.detail_actions` with the returned normalized list.
5. Re-render the action area.
6. Re-enable the action area.

If the current item changes while an async action is in flight, the player should avoid applying stale results to a different item. The simplest safe rule is to capture the current item object or index at dispatch time and discard returned actions if the active item no longer matches.

### Error Handling

Action failures must not interrupt playback.

Rules:

- invalid action payloads are ignored
- missing action runners leave the area visible but action clicks fail gracefully
- source execution exceptions append a concise log message and restore interactivity
- playback continues unchanged after any action failure
- if action execution returns malformed payloads, normalize what is valid and drop the rest

Suggested log messages:

- `详情动作执行失败[favorite_track]: ...`
- `详情动作未注册[favorite_album]`

### Compatibility

Backward compatibility requirements:

- spider plugins that never return `actions` continue to work unchanged
- Bilibili playback continues to work if no detail actions are provided
- existing `playerContent()` fields such as `cover`, `qualities`, `subt`, and `lyric` remain unaffected
- non-Bilibili built-in controllers and other source types do not need to implement anything in this change

## Testing Strategy

Add spider-controller tests for:

- mapping valid `playerContent().actions` into normalized `PlayItem.detail_actions`
- ignoring invalid action payloads without breaking playback resolution
- replacing action state with the returned result from `runPlayerAction`

Add Bilibili-controller tests for:

- populating normalized `detail_actions` during playback item resolution
- exposing a `detail_action_runner` through `build_request`
- returning refreshed action state after an action executes

Add player-window tests for:

- hiding the action area when the current item has no actions
- rendering visible actions in provided order
- reflecting `active`, `enabled`, and `tooltip` in the UI
- executing an action and refreshing the current item action list
- keeping playback active when action execution fails
- switching songs and showing the new current item's action list
- discarding stale async action results when the active item changes before completion

## Implementation Order

1. Add failing model and controller tests for normalized playback detail actions.
2. Introduce the shared `PlaybackDetailAction` model and wire it through `PlayItem`, `OpenPlayerRequest`, and `PlayerSession`.
3. Implement spider-plugin action normalization and execution.
4. Implement the Bilibili adapter and execution callback wiring.
5. Add failing player-window tests for action rendering, refresh, and execution.
6. Implement the player sidebar action container and action runner flow.
7. Run focused controller and player-window tests, then broader playback regressions.
