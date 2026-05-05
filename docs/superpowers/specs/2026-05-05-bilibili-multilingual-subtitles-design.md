# Bilibili Multilingual Subtitles Design

## Summary

Extend Bilibili playback so subtitle entries returned by the backend `subs` payload become switchable subtitle options inside the existing player subtitle UI. The player should expose Bilibili external subtitles alongside embedded mpv subtitle tracks, but it must not auto-enable them during initial playback.

The implementation is intentionally scoped to Bilibili playback items and the player window. It reuses the current subtitle combo box, context menus, mpv external subtitle loading, and existing danmaku behavior.

## Goals

- Parse Bilibili `subs` entries from playback responses.
- Expose valid Bilibili subtitle entries as selectable options in the existing primary and secondary subtitle controls.
- Keep Bilibili external subtitles disabled by default on first playback.
- Allow both primary and secondary subtitle selection to target a Bilibili external subtitle.
- Remove previously loaded Bilibili subtitle tracks when the user switches away from them or changes episodes.
- Preserve current danmaku behavior so danmaku loading and Bilibili subtitle loading do not corrupt each other's subtitle tracks.

## Non-Goals

- Add a new standalone Bilibili subtitle menu or dialog.
- Persist Bilibili subtitle preference globally across unrelated media.
- Auto-select a preferred Bilibili subtitle language.
- Redesign subtitle layout, style, scale, or position behavior.
- Change backend subtitle generation or proxy behavior.
- Replace the current danmaku flow.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/controllers/bilibili_controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_bilibili_controller.py`
- `tests/test_player_window_ui.py`

No API client changes are expected because the backend payload already reaches the controller.

## Data Model

Add a lightweight subtitle option model for playback-time external subtitles. Each option should preserve:

- display name
- language code
- source URL
- MIME format
- provider label or source marker

`PlayItem` should gain a list of external subtitle options populated only after playback source resolution. This keeps the data aligned with the backend contract, where `subs` is returned by `getPlayUrl` rather than by Bilibili detail pages.

The controller should filter out unusable entries:

- empty subtitle URLs
- explicit close entries such as `关闭`

Valid entries should be normalized into a stable display label such as `中文 [B站]` or `English [B站]`.

## Controller Behavior

`BilibiliController.load_playback_item()` should continue to resolve the playable media URL, request headers, and direct danmaku payload exactly as it does today.

In addition, it should parse `subs` from the playback payload and attach normalized subtitle options to the target `PlayItem`.

Parsing rules:

- accept list-like subtitle entries with `url`, `name`, `lang`, and `format`
- ignore entries with blank URLs
- ignore close or off entries
- preserve original order from the backend response

Controller failures in subtitle parsing should not block playback. If the payload is malformed, the controller should fall back to an empty external subtitle list.

## Player Integration

The player should build a unified subtitle option view from two sources:

1. embedded subtitle tracks reported by mpv
2. Bilibili external subtitle options attached to the current `PlayItem`

`auto` behavior remains unchanged and should only operate on embedded subtitle tracks. Bilibili external subtitles must not be auto-loaded.

When the user explicitly selects a Bilibili external subtitle:

1. download the subtitle text through the existing request path with the current play item's headers
2. write it to a temporary local subtitle file
3. load it into mpv through `sub-add`
4. bind the loaded track to the primary or secondary subtitle slot requested by the user

The player should maintain enough local state to distinguish:

- embedded subtitle selections
- externally loaded Bilibili subtitle selections
- danmaku-owned external subtitle tracks

This state must prevent one external subtitle feature from deleting another feature's track.

## Subtitle Slot Rules

Primary and secondary subtitle selection should support both embedded and Bilibili external subtitle options.

Selection rules:

- selecting `auto` keeps existing embedded-track behavior
- selecting `off` disables that slot and unloads any Bilibili subtitle track currently owned by that slot
- selecting an embedded track switches to the embedded track and unloads any Bilibili subtitle track currently owned by that slot
- selecting a Bilibili subtitle loads or reuses that subtitle track and applies it to the requested slot

Track ownership should be slot-specific:

- one external Bilibili subtitle may be loaded for the primary slot
- one external Bilibili subtitle may be loaded for the secondary slot
- danmaku keeps its own external track ownership and lifecycle

If both subtitle slots select Bilibili subtitles, the player may load two separate external tracks. Simplicity and correctness are preferred over de-duplicating them in the first version.

## Episode Changes And Refresh

When the current playlist item changes, the player should:

1. unload any Bilibili subtitle tracks owned by the previous item
2. load the new media item
3. refresh embedded subtitle tracks
4. rebuild the unified subtitle options using the new play item's external subtitle candidates
5. leave Bilibili subtitles disabled until the user explicitly selects one

Track refreshes triggered by mpv must preserve active manual selections when possible, but only within the current item. Bilibili external subtitle choice should not be carried across unrelated items by default.

## UI Behavior

No new controls should be added.

The existing bottom subtitle combo box and right-click subtitle menus should include Bilibili subtitle entries in addition to embedded subtitle tracks.

Display rules:

- keep the existing `字幕`, `自动选择`, and `关闭字幕` entries
- append Bilibili subtitle entries after embedded subtitle tracks
- include a source marker in the label so users can tell they are selecting a Bilibili external subtitle

The same unified option set should drive:

- bottom `subtitle_combo`
- right-click primary subtitle menu
- right-click secondary subtitle menu

## Error Handling

Bilibili subtitle failures must not interrupt playback.

If downloading, writing, loading, or applying a Bilibili subtitle fails:

- keep playback running
- log a concise failure message
- revert that subtitle slot to a safe state
- keep other subtitle slots and danmaku state intact

Malformed subtitle payloads, HTTP failures, or mpv command failures should degrade to "no selectable external subtitle" or "slot remains off" rather than crashing the player.

## Testing Strategy

Add focused controller tests for:

- parsing valid Bilibili `subs` entries into normalized `PlayItem` subtitle options
- filtering close entries and empty URLs
- leaving playback URL and headers behavior unchanged

Add focused player window tests for:

- exposing Bilibili subtitle options in the existing subtitle selector without auto-loading one
- selecting a Bilibili subtitle as the primary subtitle
- selecting a Bilibili subtitle as the secondary subtitle
- unloading a Bilibili subtitle when switching back to `off` or an embedded track
- clearing Bilibili subtitle tracks on episode change without disturbing danmaku tracks
- logging and safe fallback when subtitle download or mpv loading fails

## Implementation Order

1. Add failing controller tests for `subs` parsing.
2. Add the playback-time external subtitle option model and controller mapping.
3. Add failing player window tests for unified subtitle option rendering and manual Bilibili subtitle selection.
4. Implement player state for Bilibili external subtitle loading, ownership, and cleanup.
5. Add failing tests for switching away from external subtitles and episode-change cleanup.
6. Implement cleanup and failure handling paths.
