# Player Default Video Cover Design

## Summary

The player should show a poster overlay when there is no visible video frame. The poster source should prefer the current item's `vod_pic`, and fall back to the server setting `/api/settings/video_cover` when the item does not provide a poster.

This overlay should cover three situations:

- playback is starting and no visible frame has appeared yet
- the current media has no usable video picture, such as audio-only or no video track
- playback fails

The existing right-side details poster and the in-player poster overlay should continue to use the same resolved poster source so the UI stays consistent.

## Goals

- Show a poster in the player area before the first visible frame appears.
- Keep showing a poster when the current media has no visible video picture.
- Show a poster again when playback fails.
- Prefer the current `VodItem.vod_pic` and only fall back to the global `video_cover` setting when that field is empty.
- Reuse existing poster-loading code paths instead of introducing a second image-loading stack.

## Non-Goals

- Adding a new local persisted setting for the fallback poster.
- Changing browse cards or other non-player UI behavior outside existing poster rendering paths.
- Replacing the current mpv playback flow with image playback or mpv-native poster switching.
- Querying the global setting on every playback start.
- Blocking playback when the fallback setting or image cannot be loaded.

## User Experience

### Normal Video Playback

When playback starts, the player shows a poster overlay until visible video is confirmed. As soon as the current media produces a visible video picture, the overlay disappears.

### Audio-Only Or No-Video Media

If the current media does not have a usable video picture, the player keeps the poster overlay visible instead of leaving the video area blank or black.

### Playback Failure

If playback fails, the player keeps the window open, preserves the failure log entry, and shows the poster overlay again.

### Poster Priority

Poster resolution follows this order:

1. current `session.vod.vod_pic`
2. global `/api/settings/video_cover`
3. no poster

If neither source is available, playback behavior stays unchanged apart from logs.

## Architecture

### Ownership

`PlayerWindow` owns poster-overlay visibility and poster-source resolution for player display.

`MpvWidget` should expose high-level playback picture state signals, not UI behavior. It is responsible for translating mpv events into player-facing signals such as:

- visible video is available
- current media has no usable video picture
- playback failed

`ApiClient` should expose a small helper for retrieving the `video_cover` setting value from the backend.

### Why UI Overlay Instead Of mpv Poster Switching

The player already uses `video_poster_overlay` and already renders the details poster from `vod_pic`. Extending that path is lower risk than teaching mpv to swap in a static image source.

Keeping this behavior in Qt also makes failure handling and source fallback consistent with the existing placeholder-player behavior.

## Data Flow

### Global Fallback Setting

Add a lightweight `ApiClient` method that requests:

- `GET /api/settings/video_cover`

The method should return the setting value string when present, or an empty string when the payload is missing or invalid.

### Fallback Loading Strategy

`PlayerWindow` should receive a `default_video_cover_loader` callable when it is constructed. The window should not resolve the fallback immediately. Instead, it should:

1. try the current `session.vod.vod_pic`
2. if empty, lazily call `default_video_cover_loader()`
3. cache the returned URL in the `PlayerWindow` instance
4. reuse that cached value for later playback sessions in the same window

This fits the current app structure because `MainWindow` reuses a single `PlayerWindow` instance.

### Poster Rendering

`PlayerWindow._render_poster()` should expand from a single-source render into a resolved-source render:

1. resolve the preferred poster source using the priority rules
2. load local file posters directly when applicable
3. load remote posters through the existing asynchronous poster loader
4. apply the same resolved image to both `poster_label` and `video_poster_overlay`

No second remote-image pipeline should be added.

## Playback State Model

`PlayerWindow` should track poster-overlay visibility with a small explicit state model:

- `loading`
- `video_visible`
- `audio_only_or_no_video`
- `playback_failed`

### Entering States

- `open_session()`, replay, and episode switches enter `loading`
- a positive "video is visible" signal enters `video_visible`
- a "no usable video picture" signal enters `audio_only_or_no_video`
- the existing playback failure signal enters `playback_failed`

### Leaving States

- any new playback attempt resets the state back to `loading`
- only a fresh positive "video is visible" signal hides the overlay again
- failure and no-video states do not auto-clear on timers

This avoids conflating slow startup with genuinely missing video.

## mpv Integration

`MpvWidget` should expose a clearer signal for playback picture state instead of relying on `duration_seconds()` or `position_seconds()` as a proxy.

The widget should translate lower-level player observations into a higher-level signal contract used by `PlayerWindow`. The exact mpv properties can be chosen during implementation, but the consumer contract should distinguish between:

- media is still loading
- visible video is present
- no usable video picture is available

`PlayerWindow` should stop inferring "video ready" from progress alone once the explicit signal exists.

## Error Handling

- Failure to fetch `/api/settings/video_cover` must not block player open or playback start.
- Failure to load the fallback image must not crash the player and should simply leave the overlay hidden if no other poster source exists.
- Playback failures should continue to append the current `播放失败: ...` log text.
- No-video states should append a clear log entry such as `当前媒体没有可用视频画面，已显示封面`.
- No modal dialogs should be introduced for poster fallback failures.

## Testing

Add focused tests for:

- `ApiClient` reading `/api/settings/video_cover` and returning the setting value
- `ApiClient` handling invalid or missing setting payloads as an empty string
- `PlayerWindow` preferring `session.vod.vod_pic` over the global fallback
- `PlayerWindow` falling back to the global cover when `vod_pic` is empty
- `PlayerWindow` keeping the overlay visible during `loading`
- `PlayerWindow` hiding the overlay after an explicit visible-video signal
- `PlayerWindow` showing the overlay after an explicit no-video signal
- `PlayerWindow` showing the overlay after playback failure
- `PlayerWindow` resetting overlay state to `loading` on replay or item switch
- `PlayerWindow` tolerating fallback-setting or fallback-image load failures without interrupting playback

Existing tests that assert the overlay hides after nonzero duration should be updated to reflect the new explicit picture-state behavior instead of progress-based inference.

## Risks And Mitigations

- Risk: progress-based heuristics may hide the overlay for audio-only media.
  Mitigation: move overlay visibility to explicit picture-state signals from `MpvWidget`.

- Risk: repeatedly loading the global fallback setting could add unnecessary latency.
  Mitigation: use lazy resolution plus `PlayerWindow`-instance caching.

- Risk: separate logic for details poster and video overlay could drift.
  Mitigation: resolve one poster source and feed both surfaces from the same path.

- Risk: fallback failures could create noisy or blocking UX.
  Mitigation: treat setting and image fallback as best-effort only and keep playback independent.
