# Danmaku Count Intro Design

## Summary

When danmaku is rendered for playback, prepend one synthetic display-only danmaku message that announces the number of real danmaku records for the current item. The message should appear as the first visible danmaku and use the fixed text pattern `X条弹幕来袭！`.

This change is intentionally limited to the playback rendering layer. It must not modify provider payloads, persisted XML, cache contents, or danmaku source selection behavior.

## Goals

- Show one synthetic introductory danmaku before the real danmaku stream starts.
- Base the number on the count of real parsed danmaku records in the loaded XML.
- Keep the feature source-agnostic so it applies to all danmaku providers.
- Ensure the injected message participates in existing danmaku rendering modes without special player-side handling.

## Non-Goals

- Modify cached danmaku XML or provider responses.
- Add a setting to enable or disable the intro message.
- Change danmaku source selection, search, ranking, or persistence behavior.
- Display the count in the settings dialog or other static UI.

## Scope

Primary implementation should live in:

- `src/atv_player/danmaku/subtitle.py`

Primary verification should live in:

- `tests/test_danmaku_subtitle.py`

`src/atv_player/ui/player_window.py` should remain unchanged unless a small integration adjustment is required by the rendering API.

## Rendering Behavior

The danmaku renderer already parses XML into in-memory records before generating subtitle output. Extend that in-memory record sequence with one synthetic record only when at least one real danmaku record exists.

Synthetic intro record requirements:

- content: `X条弹幕来袭！`
- count source: total number of parsed real danmaku records
- position intent: treat it like a normal top-aligned danmaku-compatible record so it renders safely across existing modes
- color: use the default white source value so current color-mode logic remains valid

Timing requirements:

- the intro message must be the first rendered danmaku
- place it slightly before the earliest real danmaku when possible
- clamp the start time at `0.0` so negative timestamps are never introduced

The renderer should continue to treat all real danmaku records exactly as before after the synthetic record is inserted.

## Data and Cache Constraints

The synthetic intro message must exist only in the render pipeline's in-memory record list.

It must not:

- alter `item.danmaku_xml`
- alter danmaku XML cache files
- alter provider payload-to-XML conversion
- require a new cache key, because the rendered subtitle text already depends on the input XML and this feature is deterministic from that XML

## Testing

Add targeted subtitle-rendering tests that verify:

- rendering output includes `X条弹幕来袭！` when real danmaku records exist
- the intro message is emitted before the first real danmaku line in the rendered subtitle output
- empty or invalid danmaku XML still produces no output and no intro message

Static and dynamic rendering paths should both remain covered by the existing subtitle test suite where possible, with at least one new focused regression test for the intro message.
