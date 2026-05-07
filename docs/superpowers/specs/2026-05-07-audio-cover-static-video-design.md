# Audio Cover Static Video Design

## Summary

When the current media is audio-only, render the item poster as a static video background so mpv can keep drawing subtitles on top of an actual video target.

This change is specifically intended to make subtitle rendering reliable for audio playback such as `mp3 + spider subtitle`, while preserving the existing subtitle selection system and normal video playback behavior.

## Goals

- Automatically enable a static cover-backed video surface for audio-only media.
- Prefer `vod_pic` as the cover source and fall back to the existing default cover when `vod_pic` is unavailable.
- Keep primary and secondary subtitle rendering inside mpv rather than introducing a separate Qt subtitle renderer.
- Preserve existing subtitle behavior:
  - embedded subtitle selection
  - external subtitle selection
  - spider auto subtitle fallback
  - manual subtitle switching
- Exit the mode automatically if a real video track becomes available.

## Non-Goals

- Do not change spider plugin subtitle payload structure.
- Do not change subtitle menu layout or persisted subtitle preferences.
- Do not add a user-visible setting to toggle this behavior.
- Do not redesign poster UI for normal video playback.
- Do not implement a parallel Qt-based subtitle rendering path.

## Trigger Rules

Enable audio cover static video mode only when all of the following are true:

- the current media has no real video track
- mpv reports at least one playable audio track for the current media
- a usable cover image is available from either:
  - `session.vod.vod_pic`
  - the existing default video cover loader

Do not enable this mode for normal video media, even if a poster is available.

If no usable cover image is available, continue audio playback without failing and keep the existing empty-background fallback.

## Runtime Behavior

### Normal video media

- Load and play as today.
- Keep current poster overlay behavior until a real video frame becomes visible.
- Do not synthesize a background video from the poster.

### Audio-only media

- Resolve the preferred cover image.
- Hand the cover image to mpv as a static visual background so subtitles can be rendered by mpv on top of it.
- Keep audio playback sourced from the original media item.
- Keep subtitle loading and subtitle switching rules unchanged.

### Track-state transitions

- `loading`: media and cover are being prepared.
- `audio-cover`: no video track is present and the cover-backed static video mode is active.
- `visible`: a real video track is present and normal video playback is active.
- `unavailable`: no real video track exists and no usable cover image could be prepared.

If mpv later reports a real video track for the same item, the player must leave `audio-cover` mode and treat playback as normal video.

## Design

### `src/atv_player/player/mpv_widget.py`

Responsibilities:

- expose the mpv capability needed for audio-only media to keep a visible rendering target
- ensure mpv keeps a window/output target even for audio playback
- support loading audio-only media with a static poster-backed visual surface

Expected behavior:

- mpv must be configured so audio playback still has a drawable window
- the widget must expose a poster-backed rendering path without changing the existing subtitle selection API

### `src/atv_player/ui/player_window.py`

Responsibilities:

- decide when the current item should use audio cover static video mode
- provide the resolved cover source for the current item
- keep poster overlay behavior from masking active subtitles during audio-only playback

Expected behavior:

- the window must use `vod_pic` first and the default cover second
- if primary subtitles are active in audio-only mode, the Qt poster overlay must not cover the mpv render target
- existing subtitle retry and auto-selection logic must remain authoritative

### `src/atv_player/plugins/controller.py`

Responsibilities:

- preserve local absolute subtitle paths returned by spider plugins

Expected behavior:

- `subt="/tmp/example.srt"` must remain a local path when it points to a real local file
- relative subtitle paths such as `/files/subtitles/a.ass` must continue to resolve against the plugin base URL

## Subtitle Semantics

This feature does not change subtitle policy. It only changes the rendering carrier used by audio-only playback.

That means:

- embedded subtitles still win when present under the existing rules
- spider external subtitles still auto-load only under the existing spider-only fallback rule
- Bilibili and other non-spider subtitles must not gain new auto-load behavior
- manual user subtitle actions remain authoritative

## Error Handling

Failure must degrade safely without interrupting playback.

Cases:

- cover download or decode fails:
  - continue audio playback
  - fall back to empty background
  - do not break subtitle loading
- mpv cannot activate static cover rendering:
  - continue audio playback
  - log a concise failure
  - keep existing fallback visuals
- external subtitle load or subtitle track apply fails:
  - keep the existing retry/logging behavior
  - do not introduce new infinite retry loops
- a real video track later appears:
  - immediately leave audio cover static video mode
  - restore normal video playback behavior

## Testing Strategy

Add or update tests covering:

- mpv widget keeps a drawable window for audio playback
- audio-only playback can use a poster-backed render target
- player window prefers `vod_pic` and falls back to default cover for audio-only media
- active primary subtitles are not hidden by the poster overlay in audio-only mode
- local absolute spider subtitle paths remain local
- local absolute subtitle files are loaded without going through `httpx`
- existing spider subtitle auto-load and manual subtitle switching regressions remain green
- normal video playback does not accidentally enter audio cover mode

## Implementation Order

1. Add failing tests for audio-only cover-backed rendering prerequisites.
2. Add failing tests for local spider subtitle path preservation and local file loading.
3. Update spider subtitle path normalization so real local absolute paths stay local.
4. Update external subtitle loading so local absolute subtitle files are read directly.
5. Add mpv/player-window support for audio-only cover-backed rendering.
6. Adjust poster overlay behavior so active subtitles remain visible in audio-only mode.
7. Run focused regressions, then full touched-module verification.
