# Spider Plugin `playerContent().subt` Subtitle Design

## Summary

Extend spider-plugin playback so `playerContent()` may return a subtitle path through `subt`, and the resolved subtitle becomes a manually selectable external subtitle in the existing primary subtitle UI.

The implementation is intentionally scoped to spider-plugin playback items, existing external subtitle models, and the current player subtitle selector. The subtitle must remain disabled by default until the user explicitly selects it.

## Goals

- Accept `subt` from spider-plugin `playerContent()` payloads.
- Normalize that subtitle into the existing `PlayItem.external_subtitles` model.
- Expose the subtitle as a manual option in the existing primary subtitle selector.
- Keep external plugin subtitles disabled by default on initial playback.
- Reuse the existing external subtitle fetch and mpv load path instead of introducing plugin-specific subtitle plumbing.

## Non-Goals

- Auto-enable plugin subtitles when playback starts.
- Add plugin subtitles to the secondary subtitle selector in this change.
- Introduce a new subtitle panel, menu, or dialog.
- Support multiple plugin subtitle entries in one `playerContent()` response.
- Change the plugin API beyond reading the existing `subt` field.

## Scope

Primary implementation should live in:

- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

No data model expansion is required because `PlayItem.external_subtitles` already exists.

## Payload Contract

`playerContent()` may return:

- `subt` as an absolute URL
- `subt` as a server-relative path such as `/path/to/subtitle.srt`

Normalization rules:

- blank `subt` values are ignored
- absolute `http://` and `https://` values are used as-is
- server-relative paths are resolved against the app base URL
- unsupported relative values without a leading slash are ignored for now

The normalized subtitle should be stored as one `ExternalSubtitleOption` with:

- a stable label such as `外挂字幕 [插件]`
- an empty language code
- the normalized subtitle URL
- an inferred format when possible from the subtitle path suffix
- `source="spider"`

## Controller Behavior

`SpiderPluginController._resolve_play_item()` should continue to resolve:

- parse requirement
- playback URL
- request headers
- danmaku prefetch

In addition, after playback URL resolution succeeds, it should inspect `subt` and populate `item.external_subtitles` with zero or one normalized entry.

Behavior rules:

- each playback resolution should overwrite any stale `item.external_subtitles` value
- malformed or unsupported `subt` values should degrade to an empty subtitle option list
- subtitle normalization failures must not block playback URL resolution

## Player Integration

The player already supports runtime external subtitle options through `PlayItem.external_subtitles`. This change should reuse that model instead of adding spider-specific player state.

The player should generalize the current helper names and log messages so external subtitle behavior is source-agnostic rather than Bilibili-specific.

Primary subtitle behavior:

- append plugin external subtitle options after embedded subtitle tracks
- keep the existing `字幕` and `关闭字幕` entries
- do not auto-fetch or auto-load the external subtitle on open
- when the user selects the plugin subtitle, fetch it with the current play item headers, write it to a temp file, load it into mpv, and switch the primary subtitle slot to that new track
- when the user switches back to `自动选择`, `关闭字幕`, or an embedded track, unload the previously owned plugin external track

Secondary subtitle behavior remains unchanged in this change. Plugin external subtitles must not be added to the secondary subtitle menu.

## Error Handling

Plugin subtitle failures must not interrupt playback.

If subtitle fetching, file writing, loading, or applying fails:

- keep media playback running
- log a concise primary subtitle failure message
- leave the primary subtitle slot in its previous safe state
- avoid clearing danmaku-owned tracks

If `subt` normalization fails, the player should simply behave as if no external plugin subtitle exists.

## Testing Strategy

Add controller tests for:

- mapping absolute `subt` URLs into `PlayItem.external_subtitles`
- resolving server-relative `subt` paths against the base URL
- ignoring blank or unsupported `subt` values
- preserving current playback URL and header behavior

Add player window tests for:

- listing plugin external subtitles in the bottom primary subtitle combo
- not auto-loading plugin subtitles on open
- loading a plugin subtitle when the user explicitly selects it from the primary subtitle combo
- excluding plugin external subtitles from the secondary subtitle menu
- keeping existing generic external subtitle behavior intact after helper renaming

## Implementation Order

1. Add failing spider controller tests for `subt` normalization.
2. Implement `subt` mapping into `PlayItem.external_subtitles`.
3. Add failing player window tests for primary-only plugin subtitle exposure.
4. Generalize player external subtitle helpers from Bilibili-specific naming to source-agnostic behavior.
5. Implement plugin subtitle selection and primary-only menu filtering.
6. Run focused controller and player tests, then broader regression tests for external subtitles.
