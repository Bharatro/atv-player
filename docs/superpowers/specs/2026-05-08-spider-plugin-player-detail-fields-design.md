# Spider Plugin Custom Player Detail Fields Design

## Summary

Extend spider-plugin playback detail so `detailContent()` and `playerContent()` may return a custom `ext` field list for the player detail sidebar.

This lets plugins expose source-specific read-only detail rows such as:

```python
{
    "vod_id": vod_id,
    "vod_name": vod_name,
    "vod_play_from": play["vod_play_from"],
    "vod_play_url": play["vod_play_url"],
    "ext": [
        {"label": "播放", "value": "12万"},
    ],
}
```

The player should render that data in the detail area as:

```text
播放: 12万
```

The change is intentionally scoped to spider-plugin detail payload mapping and the existing player detail sidebar. Existing plugins that do not return `ext` must keep working unchanged.

## Goals

- Accept collection-level custom detail fields from `detailContent(...).list[0].ext`.
- Accept current-item custom detail fields from `playerContent(...).ext`.
- Show collection-level fields immediately when the player opens.
- Let current-item `playerContent().ext` replace the displayed collection-level fields for the active episode.
- Fall back to collection-level fields when the current item has no item-level fields.
- Reuse the existing player detail sidebar instead of adding a dialog or context menu.

## Non-Goals

- Change the existing fixed metadata block into a generic schema-driven renderer.
- Merge collection-level and item-level fields row by row in the first release.
- Support nested field groups, icons, links, or rich text in custom fields.
- Persist custom detail fields outside the active player session.
- Add editing or action behavior to these fields.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

Primary documentation follow-up should live in:

- `docs/python-spider-plugin-development-guide.md`

No new top-level window or route is required. The existing right-side player detail panel should be extended in place.

## Payload Contract

`detailContent(...).list[0]` and `playerContent(...)` may each return:

```python
"ext": [
    {"label": "播放", "value": "12万"},
    {"label": "更新", "value": "2026-05-08"},
]
```

Contract rules:

- `ext` is optional.
- `ext` must be a list to be considered.
- each entry must provide a non-blank `label`.
- each entry must provide a non-blank displayable `value`.
- malformed entries are ignored rather than failing playback.
- source ordering is preserved.
- labels and values are rendered as plain text.

An omitted or invalid `ext` payload behaves the same as returning no custom fields.

## Data Model

Add a shared read-only detail-row model:

- `PlaybackDetailField(label: str, value: str)`

Extend:

- `VodItem.detail_fields: list[PlaybackDetailField]`
- `PlayItem.detail_fields: list[PlaybackDetailField]`

Reasoning:

- `VodItem.detail_fields` is the natural home for collection-level fields from `detailContent()`.
- `PlayItem.detail_fields` is the natural home for current-item fields from `playerContent()`.
- keeping both levels explicit avoids overloading `VodItem` with per-episode state.

## Controller Behavior

`SpiderPluginController.build_request()` should:

1. parse `detailContent(...).list[0].ext`
2. normalize it into `VodItem.detail_fields`
3. leave every playlist item's `detail_fields` empty at request-build time

`SpiderPluginController` playback resolution should continue to resolve:

- playback URL
- parse requirement
- request headers
- detail actions
- subtitles
- qualities
- danmaku prefetch

In addition, after `playerContent(...)` succeeds, it should normalize `payload.get("ext")` into the current `PlayItem.detail_fields`.

Normalization rules:

- non-list payloads become an empty field list
- malformed entries are ignored
- blank labels are ignored
- blank values are ignored
- each playback resolution overwrites any stale `PlayItem.detail_fields`

This overwrite behavior matters because one episode may expose different source-specific detail rows than another.

## Display Priority

The player should use a simple whole-list override model:

1. If the current `PlayItem.detail_fields` is non-empty, display that list.
2. Otherwise, display `VodItem.detail_fields`.
3. If neither level has fields, hide the custom-detail-fields widget.

The first release should not merge collection-level and item-level rows by label.

Reasoning:

- whole-list override matches the requested semantics of current-item fields replacing collection fields
- it avoids ambiguous merge rules when both levels contain the same label
- it keeps plugin behavior easy to understand

## Player UI

The right-side detail panel currently contains:

- poster
- detail action buttons
- fixed metadata block
- playback log

Add a new read-only custom-detail-fields block between the detail action buttons and the fixed metadata heading.

Rendering rules:

- one visual row per normalized field
- render each row as `label: value`
- hide the block entirely when there are no displayable fields
- keep it read-only and non-interactive
- preserve the fixed metadata block below it

This keeps source-specific custom rows separate from the app's existing fixed metadata formatting.

## Refresh Lifecycle

The custom-detail-fields block should refresh on the same state transitions that already affect the detail sidebar:

1. `open_session()`
   - render collection-level `VodItem.detail_fields` immediately
2. playlist index changes
   - switch to current-item fields when present
   - otherwise fall back to collection-level fields
3. `playerContent()` resolution completes
   - if the resolved current item received `detail_fields`, rerender immediately
4. resolved `VodItem` replacement is applied
   - rerender in case collection-level fields changed

This ensures:

- placeholder or pre-resolution sessions can still show collection-level fields
- async `playerContent()` responses can update the sidebar without reopening the window
- switching episodes updates the displayed fields consistently

## Error Handling

Custom detail fields must never block playback.

Rules:

- invalid `ext` payloads are ignored
- malformed rows are skipped
- empty normalized field lists simply hide the widget
- playback continues even if a plugin returns unusable custom field data

No extra player log entry is needed for invalid custom field rows in the first release.

## Testing Strategy

Add controller tests for:

- mapping valid `detailContent().ext` entries into `VodItem.detail_fields`
- ignoring malformed collection-level entries
- mapping valid `playerContent().ext` entries into `PlayItem.detail_fields`
- overwriting stale item-level fields when a later `playerContent()` response omits or invalidates rows
- preserving existing playback behavior when `ext` is absent

Add player window tests for:

- showing collection-level custom fields when a session opens
- hiding the custom field block when neither level provides fields
- replacing collection-level fields with current-item fields after playback resolution
- falling back to collection-level fields when switching to an item without item-level fields
- rerendering custom fields when resolved `VodItem` data replaces the session detail payload

## Documentation Follow-Up

Update the spider-plugin player-detail documentation to describe:

- `detailContent(...).list[0].ext`
- `playerContent(...).ext`
- the whole-list override rule
- the simple `{label, value}` row format

The existing action documentation can be extended, but the field behavior should remain clearly separated from actions because fields are display-only.

## Implementation Order

1. Add failing controller tests for collection-level and item-level `ext` normalization.
2. Extend shared models with `PlaybackDetailField` plus storage on `VodItem` and `PlayItem`.
3. Implement `ext` normalization in `SpiderPluginController`.
4. Add failing player window tests for initial render, override, fallback, and hidden state.
5. Add a dedicated custom-detail-fields widget to the player sidebar.
6. Wire the widget into the existing session-open, episode-switch, and async-resolution refresh paths.
7. Update the spider-plugin player-detail documentation.
8. Run focused controller and player tests, then broader sidebar regressions if needed.
