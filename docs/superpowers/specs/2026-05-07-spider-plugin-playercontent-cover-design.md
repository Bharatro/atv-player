# Spider Plugin `playerContent().cover` Poster Override Design

## Summary

Extend spider-plugin playback so `playerContent()` may return a `cover` value that replaces the current player poster after playback resolution succeeds.

The change is intentionally scoped to the existing spider-plugin lazy `playerContent()` resolution flow, the current session-level `vod_pic` poster source, and the existing player poster rendering path. Existing plugins that do not return `cover` must keep working unchanged.

## Goals

- Accept `cover` from spider-plugin `playerContent()` payloads.
- Replace the current session poster when `cover` is a non-blank string.
- Refresh the player poster immediately after the override is applied.
- Keep existing placeholder poster, detail poster, and default poster fallback behavior unchanged when `cover` is missing or blank.
- Reuse the current session poster state and poster rendering flow instead of introducing spider-specific poster state.

## Non-Goals

- Add per-episode poster state to `PlayItem`.
- Introduce a new playback loader result field just for poster overrides.
- Validate remote poster reachability before applying the override.
- Block playback when the override poster fails to load as an image.
- Persist a separate plugin poster field outside the existing `session.vod.vod_pic` flow.

## Scope

Primary implementation should live in:

- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

No data model expansion is required if the override is applied directly to the existing session `VodItem`.

## Payload Contract

`playerContent()` may return:

```python
{
    "parse": 0,
    "url": "https://stream.example/play.m3u8",
    "header": {"Referer": "https://site.example"},
    "cover": "https://img.example/resolved-poster.jpg",
}
```

Contract rules:

- top-level `cover` is optional
- blank `cover` values are ignored
- non-string values are coerced through the existing string-normalization pattern and then trimmed
- the value is treated as a poster source under the same rules already used by the player poster renderer
- if `cover` is absent or blank, playback behaves exactly as it does today

## Controller Behavior

`SpiderPluginController._resolve_play_item()` should continue to resolve:

- parse requirement
- playback URL
- request headers
- external subtitles
- playback qualities
- danmaku prefetch

In addition, after playback URL resolution succeeds, it should inspect `cover`.

Behavior rules:

- each playback resolution may produce zero or one normalized poster override
- blank or missing `cover` values do not modify the current poster
- a non-blank `cover` value should be made available to the current player session as the new `vod_pic`
- malformed or unreachable poster images must not fail playback resolution

The controller should not add new poster state to `PlayItem`. The resolved poster should flow through the existing session poster source.

## Player Integration

The player already uses `session.vod.vod_pic` as the highest-priority poster source before falling back to the configured default video cover. This change should keep that priority model and only update the current session poster when the spider plugin provides an override.

Integration rules:

- when spider playback resolution applies a non-blank `cover`, update `session.vod.vod_pic`
- re-render the poster immediately after updating the session poster
- if the poster is currently being shown as the video overlay because no frame is available yet, the refreshed poster should also update that overlay through the existing render path
- if the resolved poster later fails to load, the player should degrade through the existing render behavior without interrupting playback

This keeps the poster source of truth in one place and avoids adding a separate player-only override channel.

## Error Handling

Poster override failures must not interrupt playback.

Rules:

- invalid, blank, or unsupported `cover` values are ignored
- poster image load failures do not roll back the resolved playback URL
- playback start must not wait on poster download success
- no new user-facing error dialog is required for poster override failures in the first release

## Testing Strategy

Add controller tests for:

- applying a non-blank `cover` override during spider playback resolution
- leaving the existing poster unchanged when `cover` is blank or missing
- preserving current playback URL, header, subtitle, and quality behavior when `cover` is present

Add player window tests for:

- refreshing the visible poster after async spider playback resolution updates the session poster
- keeping playback functional when the poster source changes during lazy playback loading
- preserving current fallback behavior when no override poster is provided

## Implementation Order

1. Add a failing spider controller test for `cover` override behavior.
2. Implement `cover` normalization and session poster override in the spider playback resolution flow.
3. Add a failing player window test for poster refresh after async spider playback resolution.
4. Implement the player-side poster refresh hook after playback-loader resolution updates the session poster.
5. Run focused spider controller and player window tests, then a small playback regression pass around poster fallback behavior.
