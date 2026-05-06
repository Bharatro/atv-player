# Player No-Video Log Suppression Design

## Summary

The player should keep showing the fallback poster overlay when no visible video picture is available, but it should no longer append the UI log message:

- `当前媒体没有可用视频画面，已显示封面`

Playback failure logs such as `播放失败: ...` must remain unchanged.

## Goals

- Remove the extra no-video informational log line from the player UI.
- Keep poster-overlay behavior unchanged for loading, no-video, and playback-failure states.
- Keep real playback failure logs visible.

## Non-Goals

- Changing when the poster overlay appears or disappears.
- Changing mpv picture-state detection.
- Changing the wording or behavior of `播放失败: ...` logs.
- Adding a setting to toggle this log message.

## User Experience

### No-Video State

When the player determines that the current media has no usable video picture, the fallback poster still appears. The player log should stay quiet unless a real playback failure also occurred.

### Playback Failure

When playback actually fails, the player should continue showing the fallback poster and continue appending the existing failure log line.

## Architecture

The change stays entirely inside `PlayerWindow`.

- `PlayerWindow._handle_video_picture_state_changed("unavailable")` should continue updating overlay visibility.
- That same path should stop calling `_append_log(...)` for the informational no-video message.
- `PlayerWindow._handle_playback_failed()` should remain responsible for user-visible failure logs.

No API, model, or `MpvWidget` contract changes are needed.

## Testing

Update `tests/test_player_window_ui.py` so that:

- the no-video state test still verifies that the poster overlay becomes visible
- it no longer expects the removed informational log line
- the playback-failure test still expects `播放失败: ...` in the log

## Risks And Mitigations

- Risk: removing the log could accidentally hide real failure information.
  Mitigation: leave `_handle_playback_failed()` unchanged and keep the failure-log assertion in tests.

- Risk: implementation could accidentally stop showing the poster for no-video media.
  Mitigation: keep the overlay assertion in the no-video regression test.
