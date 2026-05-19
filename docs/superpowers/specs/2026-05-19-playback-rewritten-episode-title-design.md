# Playback Rewritten Episode Title Design

**Goal:** Make playback history and current-playback messaging use the rewritten episode title when one exists.

## Scope

- Playback history payloads should save the rewritten episode title instead of the raw playlist item title.
- PlayerWindow current-playback logging should show the same rewritten title so the UI and saved history stay consistent.

## Design

- Reuse the existing episode-title display fallback logic rather than adding a separate title formatter.
- Keep the change local to the playback save path in `PlayerController` and the current-playback log path in `PlayerWindow`.
- Fall back to the original `title` when `episode_display_title` is empty so unchanged playlists keep existing behavior.

## Testing

- Add a controller test proving `vodRemarks` prefers `episode_display_title`.
- Add a player-window UI test proving the current-playback log prefers `episode_display_title`.
