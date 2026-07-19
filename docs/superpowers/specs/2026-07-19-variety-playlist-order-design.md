# Variety Playlist Order Preservation Design

## Problem

Episode title enhancement currently sorts every successfully mapped playlist by
inferred season and episode number. Variety playlists are commonly ordered by
air date and contain several videos for the same issue, such as previews,
full episodes, bonus clips, and pure cuts. Sorting them by issue number changes
the backend order and makes previous/next navigation misleading.

The affected Telegram example is not reliably marked as variety in its media
metadata, but most filenames contain air dates, `第 N 期`, `加更`, or similar
variety markers.

## Decision

Preserve the backend playlist order only when the content is identified as a
variety show. Continue applying enhanced episode titles without moving items.
Other media types retain the existing episode sorting behavior.

Variety detection uses either:

- explicit variety metadata such as `综艺`, `真人秀`, `脱口秀`, or `variety`;
- a majority of playlist items recognized by the existing
  `is_likely_variety_title` helper, with at least two recognized items.

The filename heuristic is required because remote metadata can be missing or
incorrect. Reusing the existing detector keeps variety semantics consistent
with danmaku matching.

## Data Flow

1. Keep the controller mapping order unchanged as today.
2. Run episode title providers and title mapping as today.
3. Before returning an enhanced variety playlist, restore item order by stable
   playlist identity from the original playlist.
4. Reassign sequential item indexes after restoring order.
5. Store the preserved order in the final-title cache.

The cache schema version is incremented so existing cached reordered playlists
cannot be restored after the fix.

## Scope

This behavior is source-independent: Telegram, Telegram channels, browse,
Emby, Jellyfin, and other supported sources preserve order when the playlist
is identified as variety. Non-variety shuffled episode playlists continue to
be sorted by inferred episode number.

## Testing

- Add a regression test using date-prefixed, interleaved variety issue files
  and assert enhanced titles do not change their original order.
- Keep the existing shuffled drama test to verify non-variety sorting remains.
- Verify final-title cache restoration preserves the same variety order.
- Run the focused episode-title enhancement and metadata resolver suites.
