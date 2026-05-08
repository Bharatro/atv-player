# Spider Plugin Inline Player Detail Fields Design

## Summary

Extend spider-plugin playback detail so `detailContent()` and `playerContent()` may return a custom `ext` field list that is rendered inside the existing player detail text area.

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

The player should render that data in the same text block as the existing metadata:

```text
名称: 示例影片
类型: 剧情
...
豆瓣ID: 123456
播放: 12万

简介:
...
```

The change is intentionally scoped to spider-plugin detail payload mapping and the existing metadata text rendering in the player sidebar. Existing plugins that do not return `ext` must keep working unchanged.

## Goals

- Accept collection-level custom detail fields from `detailContent(...).list[0].ext`.
- Accept current-item custom detail fields from `playerContent(...).ext`.
- Render custom fields inside the existing `metadata_view` text area instead of in a separate widget.
- Place custom fields after `豆瓣ID` and before `简介` in normal detail text.
- Let current-item `playerContent().ext` replace the displayed collection-level fields for the active episode.
- Fall back to collection-level fields when the current item has no item-level fields.

## Non-Goals

- Change the plugin payload contract introduced for `ext`.
- Merge collection-level and item-level fields row by row in the first release.
- Add a separate visual section, card, or widget for custom fields.
- Support nested field groups, icons, links, or rich text in custom fields.
- Persist custom detail fields outside the active player session.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

Primary documentation follow-up should live in:

- `docs/python-spider-player-actions.md`

No new top-level window, route, or sidebar widget is required.

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
- labels and values are rendered as plain text lines in the metadata text block.

An omitted or invalid `ext` payload behaves the same as returning no custom fields.

## Data Model

Keep the shared read-only detail-row model:

- `PlaybackDetailField(label: str, value: str)`

Keep:

- `VodItem.detail_fields: list[PlaybackDetailField]`
- `PlayItem.detail_fields: list[PlaybackDetailField]`

Reasoning:

- collection-level and item-level field ownership is still correct
- only the rendering location changes
- retaining structured field storage keeps plugin parsing and playback refresh logic simple

## Controller Behavior

`SpiderPluginController.build_request()` should:

1. parse `detailContent(...).list[0].ext`
2. normalize it into `VodItem.detail_fields`
3. leave every playlist item's `detail_fields` empty at request-build time

`SpiderPluginController` playback resolution should continue to normalize `playerContent(...).ext` into the current `PlayItem.detail_fields`.

Normalization rules remain unchanged:

- non-list payloads become an empty field list
- malformed entries are ignored
- blank labels are ignored
- blank values are ignored
- each playback resolution overwrites any stale `PlayItem.detail_fields`

## Display Priority

The player should keep the same whole-list override model:

1. If the current `PlayItem.detail_fields` is non-empty, display that list.
2. Otherwise, display `VodItem.detail_fields`.
3. If neither level has fields, render no extra custom-detail lines.

The first release should not merge collection-level and item-level rows by label.

## Player UI

The current detail panel already renders metadata through `PlayerWindow._format_metadata_text()` into `metadata_view`.

Change the rendering approach from:

- fixed metadata rows
- blank line
- `简介`

To:

- fixed metadata rows
- zero or more inline custom-detail rows
- blank line
- `简介`

For normal detail pages:

- insert `ext` rows immediately after `豆瓣ID`
- preserve source ordering

For bilibili detail pages:

- because `豆瓣ID` is already omitted there, insert `ext` rows after the last remaining fixed metadata row and before `简介`

For live detail pages:

- append `ext` rows after the existing fixed live rows when the live branch uses row-based metadata
- if the live branch renders `epg_current` / `epg_schedule`, keep that specialized layout unchanged unless future requirements explicitly ask to mix `ext` into EPG text

The previous standalone `detail_fields_widget` / `detail_fields_view` approach should be removed.

## Refresh Lifecycle

Because custom fields are now part of `metadata_view`, they should refresh whenever metadata text is refreshed:

1. `open_session()`
2. playlist index changes
3. `playerContent()` resolution completes and updates current `PlayItem.detail_fields`
4. resolved `VodItem` replacement is applied

The simplest implementation is to make `_format_metadata_text()` aware of the active custom-detail field list and let existing metadata rerender paths pick up the new lines.

## Error Handling

Custom detail fields must never block playback.

Rules:

- invalid `ext` payloads are ignored
- malformed rows are skipped
- empty normalized field lists simply produce no additional metadata lines
- playback continues even if a plugin returns unusable custom field data

No extra player log entry is needed for invalid custom field rows in the first release.

## Testing Strategy

Keep controller tests for:

- mapping valid `detailContent().ext` entries into `VodItem.detail_fields`
- ignoring malformed collection-level entries
- mapping valid `playerContent().ext` entries into `PlayItem.detail_fields`
- overwriting stale item-level fields when a later `playerContent()` response omits or invalidates rows

Replace standalone-widget UI tests with metadata-text assertions:

- opening a session with collection-level fields shows `ext` lines inside `metadata_view`
- current-item fields replace collection-level lines inside `metadata_view`
- switching to an item without item-level fields falls back to collection-level lines inside `metadata_view`
- no extra blank section appears when there are no custom fields
- existing metadata rows remain in the same order, with `ext` inserted before `简介`

## Documentation Follow-Up

Update the spider-plugin player-detail documentation to describe:

- `detailContent(...).list[0].ext`
- `playerContent(...).ext`
- the whole-list override rule
- the inline rendering behavior inside the metadata text block
- the simple `{label, value}` row format

## Implementation Order

1. Keep the controller-side `ext` normalization tests and implementation.
2. Replace standalone-widget player-window tests with metadata-text tests.
3. Remove the dedicated `detail_fields_widget` / `detail_fields_view` rendering path.
4. Inline custom-detail line rendering into `PlayerWindow._format_metadata_text()`.
5. Reuse existing metadata refresh paths so `ext` updates follow `metadata_view`.
6. Update the plugin-facing documentation to describe inline rendering.
7. Run focused controller and player metadata regressions.
