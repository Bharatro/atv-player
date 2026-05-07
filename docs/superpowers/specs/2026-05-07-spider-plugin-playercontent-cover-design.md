# Spider Plugin `playerContent().cover` Poster Override Design

## Summary

Extend spider-plugin playback so `playerContent()` may return a `cover` value that replaces only the player's video poster after playback resolution succeeds.

The change is intentionally scoped to the existing spider-plugin lazy `playerContent()` resolution flow, a new player-session-level video-poster override state, and the existing player poster rendering path. Existing plugins that do not return `cover` must keep working unchanged.

## Goals

- Accept `cover` from spider-plugin `playerContent()` payloads.
- Replace only the player's video poster when `cover` is a non-blank string.
- Refresh the player video poster immediately after the override is applied.
- Keep the detail poster sourced from `session.vod.vod_pic`.
- Keep playback history and future history poster saves sourced from the original detail poster.
- Keep existing placeholder poster, detail poster, and default poster fallback behavior unchanged when `cover` is missing or blank.
- Reuse the current player poster rendering flow without rewriting the detail poster source.

## Non-Goals

- Add per-episode poster state to `PlayItem`.
- Introduce a new playback loader result field just for poster overrides.
- Validate remote poster reachability before applying the override.
- Block playback when the override poster fails to load as an image.
- Replace the stored detail poster in `session.vod.vod_pic`.
- Persist plugin `cover` values into history poster fields.

## Scope

Primary implementation should live in:

- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_player_controller.py`
- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

This change requires a small `PlayerSession` data-model expansion for a player-only poster override field.

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
- the value must not overwrite the detail poster stored in `vod_pic`
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
- blank or missing `cover` values do not modify the current video-poster override
- a non-blank `cover` value should be made available to the current player session as a dedicated video-poster override value
- malformed or unreachable poster images must not fail playback resolution

The controller should not add new poster state to `PlayItem`. The resolved poster should flow through a new player-session-only poster override field.

## Player Integration

The player should distinguish between:

- detail poster source: `session.vod.vod_pic`
- video poster source: `session.video_cover_override`, then `session.vod.vod_pic`, then the configured default video cover

This keeps metadata and history behavior stable while allowing spider playback to replace only the visible player poster.

Integration rules:

- add a session-level field such as `video_cover_override: str = ""`
- when spider playback resolution applies a non-blank `cover`, update `session.video_cover_override`
- re-render the video poster immediately after updating that override
- metadata rendering should continue to use `session.vod.vod_pic`
- playback history saves should continue to use `session.vod.vod_pic`
- if the poster is currently being shown as the video overlay because no frame is available yet, the refreshed poster should also update that overlay through the existing render path
- if the resolved poster later fails to load, the player should degrade through the existing render behavior without interrupting playback

This keeps detail poster state and video poster state separate without introducing per-item poster plumbing.

## Error Handling

Poster override failures must not interrupt playback.

Rules:

- invalid, blank, or unsupported `cover` values are ignored
- poster image load failures do not roll back the resolved playback URL
- playback start must not wait on poster download success
- no new user-facing error dialog is required for poster override failures in the first release

## Testing Strategy

Add controller tests for:

- applying a non-blank `cover` override during spider playback resolution without changing `request.vod.vod_pic`
- leaving the video-poster override empty when `cover` is blank or missing
- preserving current playback URL, header, subtitle, and quality behavior when `cover` is present

Add player-controller tests for:

- defaulting the new session-level video-poster override field to empty
- preserving that field on session creation without changing existing history payload poster behavior

Add player window tests for:

- preferring `session.video_cover_override` over `session.vod.vod_pic` for the video poster
- refreshing the visible poster after async spider playback resolution updates only the session video-poster override
- leaving the detail poster view sourced from `session.vod.vod_pic`
- keeping playback functional when the poster source changes during lazy playback loading
- preserving current fallback behavior when no override poster is provided

## Implementation Order

1. Add failing controller tests for session-level video-poster override behavior.
2. Add a session-level video-poster override field without changing detail/history poster fields.
3. Implement `cover` normalization and session video-poster override updates in the spider playback resolution flow.
4. Add failing player window tests for video-poster-only refresh behavior.
5. Implement player-side preference for the new override field and refresh after playback-loader resolution.
6. Run focused controller, player-controller, and player-window tests, then a small poster fallback regression pass.
