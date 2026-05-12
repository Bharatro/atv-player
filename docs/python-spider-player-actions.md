# Python Spider Player Actions

## Overview

Python spider plugins can provide custom action buttons in the player detail sidebar.

Typical examples:

- `收藏歌单`
- `收藏专辑`
- `收藏歌曲`
- `点赞`

The player is intentionally source-agnostic:

- the plugin decides which actions exist
- the plugin decides labels like `收藏歌单` or `收藏专辑`
- the plugin decides whether an action is active, enabled, or visible
- the player only renders actions and replays refreshed state after execution

## Action Model

Each action is normalized into the shared playback detail action model:

- `id: str`
- `label: str`
- `active: bool = False`
- `enabled: bool = True`
- `visible: bool = True`
- `tooltip: str = ""`

Normalization rules:

- `id` and `label` are required
- invisible actions are dropped
- malformed actions are ignored
- source ordering is preserved

## Custom Detail Fields

Python spider plugins can also provide read-only custom detail rows in the player sidebar.

Supported payload shape:

```python
"ext": [
    {"label": "播放", "value": "12万"},
    {"label": "更新", "value": "2026-05-08"},
]
```

Rules:

- `detailContent(...).list[0].ext` sets collection-level fields for the whole detail page
- `playerContent(...).ext` sets current-item fields for the active episode or track
- if the current play item has non-empty `playerContent().ext`, those rows replace the collection-level rows
- if the current play item has no valid rows, the player falls back to `detailContent().ext`
- each row must provide non-blank `label` and `value`
- rows are display-only and are rendered as `label: value`
- these rows are inserted into the existing player metadata text block
- on normal detail pages, they appear after `豆瓣ID` and before `简介`

## Clickable Detail Fields

Custom detail rows can also expose clickable value items.

Supported `value` shapes:

```python
{"label": "播放", "value": "12万"}
{"label": "演员", "value": ["演员1", "演员2"]}
{
    "label": "演员",
    "value": [
        {"label": "演员1", "action": {"type": "search", "value": "演员1"}},
        {"label": "演员2", "action": {"type": "detail", "value": "actor-2"}},
    ],
}
```

Supported action types:

- `category`
- `detail`
- `search`
- `link`

Behavior:

- `category` loads the current spider plugin's `categoryContent(...)` result in the plugin tab
- `search` loads the current spider plugin's `searchContent(...)` result in the plugin tab
- `detail` opens a new player detail request through the current spider plugin's `detailContent(...)`
- `link` opens the given URL in the system browser

Rules:

- object items must provide non-blank `label`
- malformed actions fall back to plain display text
- rows with no remaining displayable values are ignored
- multiple value items are rendered in source order and shown as separate clickable/plain entries

## Two Action Sources

Python spider plugins now have two different places to provide player-detail actions:

1. `detailContent(...)`
2. `playerContent(flag, id, vipFlags)`

They serve different purposes.

### `detailContent.actions`

Use `detailContent(...).list[0].actions` for collection-level initial actions.

This is the right place for actions whose state belongs to the container rather than the current track, for example:

- `收藏歌单`
- `收藏专辑`
- `关注歌手`

Reason:

- `detailContent(...)` has full container context
- `playerContent(...)` only receives `flag` and play `id`
- many plugins cannot infer album/playlist/artist state from the play id alone

Example:

```python
def detailContent(self, ids):
    return {
        "list": [
            {
                "vod_id": ids[0],
                "vod_name": "红果短剧",
                "vod_play_from": "默认线",
                "vod_play_url": "第1集$/play/1#第2集$/play/2",
                "actions": [
                    {
                        "id": "favorite_album",
                        "label": "收藏专辑",
                        "active": True,
                        "tooltip": "已收藏",
                    }
                ],
            }
        ]
    }
```

Behavior:

- these actions are copied into the initial `detail_actions` of each play item in the playlist
- they are visible before `playerContent(...)` runs

### `playerContent.actions`

Use `playerContent(...).actions` for current-item actions.

Typical examples:

- `收藏歌曲`
- `点赞`
- `不喜欢`

Example:

```python
def playerContent(self, flag, id, vipFlags):
    return {
        "parse": 0,
        "url": self.get_play_url(id),
        "actions": [
            {
                "id": "favorite_track",
                "label": "收藏歌曲",
                "active": False,
            },
            {
                "id": "like_track",
                "label": "点赞",
                "enabled": True,
            },
        ],
    }
```

Behavior:

- item actions are merged into the current play item's existing action list
- if an item action uses the same `id` as a collection action, the item action replaces that action

This lets plugins override collection-level state when they need a more specific current-item state.

## Initial Render Rules

When the player opens:

1. the plugin `detailContent(...)` result is loaded
2. collection actions from `detailContent(...).list[0].actions` are applied
3. when the current item resolves, `playerContent(...).actions` is merged in

So the initial sidebar action area may contain:

- only collection actions
- only item actions
- both collection and item actions

## Action Execution

To make buttons clickable, implement:

```python
def runPlayerAction(self, action_id, context):
    ...
```

The player calls:

```python
runPlayerAction(action_id, context)
```

Current context fields:

- `context["action_id"]`
- `context["vod"]`
- `context["play_item"]`
- `context["playlist"]`
- `context["playlist_index"]`
- `context["play_index"]`
- `context["log"]`

Use:

- `vod` for collection-level operations
- `play_item` for current-track operations

## Execution Result Contract

After an action executes, return the refreshed full action list.

Supported forms:

```python
return {
    "actions": [
        {"id": "favorite_album", "label": "已收藏专辑", "active": True},
        {"id": "favorite_track", "label": "已收藏歌曲", "active": True},
    ]
}
```

or:

```python
return [
    {"id": "favorite_album", "label": "已收藏专辑", "active": True},
    {"id": "favorite_track", "label": "已收藏歌曲", "active": True},
]
```

Behavior:

- the returned actions replace the current play item's `detail_actions`
- the player re-renders the entire action area

Recommended practice:

- always return the full latest action list
- do not return only the clicked button

## Minimal Example

```python
def detailContent(self, ids):
    return {
        "list": [
            {
                "vod_id": ids[0],
                "vod_name": "示例专辑",
                "vod_play_from": "默认线",
                "vod_play_url": "第1首$/play/1#第2首$/play/2",
                "actions": [
                    {
                        "id": "favorite_album",
                        "label": "收藏专辑",
                        "active": self.is_album_favorited(ids[0]),
                    }
                ],
            }
        ]
    }


def playerContent(self, flag, id, vipFlags):
    return {
        "parse": 0,
        "url": self.get_play_url(id),
        "actions": [
            {
                "id": "favorite_track",
                "label": "收藏歌曲",
                "active": self.is_track_favorited(id),
            }
        ],
    }


def runPlayerAction(self, action_id, context):
    vod = context["vod"]
    item = context["play_item"]

    if action_id == "favorite_album":
        self.favorite_album(vod)
    elif action_id == "favorite_track":
        self.favorite_track(item)
    else:
        raise ValueError(f"unknown action: {action_id}")

    return {
        "actions": [
            {
                "id": "favorite_album",
                "label": "已收藏专辑" if self.is_album_favorited(vod.vod_id) else "收藏专辑",
                "active": self.is_album_favorited(vod.vod_id),
            },
            {
                "id": "favorite_track",
                "label": "已收藏歌曲" if self.is_track_favorited(item.vod_id or item.url) else "收藏歌曲",
                "active": self.is_track_favorited(item.vod_id or item.url),
            },
        ]
    }
```

## Error Handling

If `runPlayerAction(...)` is missing:

- the action is considered unsupported
- clicking logs a failure

If `runPlayerAction(...)` raises:

- playback continues
- the player logs the failure
- the action area remains interactive after refresh

Recommended:

- raise clear messages for login or API failures

Example:

```python
if not self.is_login():
    raise ValueError("请先登录后再收藏")
```

## Recommendations

Recommended:

- put collection initial actions in `detailContent.actions`
- put item actions in `playerContent.actions`
- return the full refreshed action list from `runPlayerAction(...)`
- keep stable action ids and let labels express state

Not recommended:

- encoding collection context into play ids unless absolutely necessary
- inferring collection type inside the player
- returning only partial post-click state
