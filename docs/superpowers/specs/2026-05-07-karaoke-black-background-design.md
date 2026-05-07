# Karaoke Black Background Design

## Summary

Adjust generated spider karaoke `ASS` subtitles so QQ Music and Kugou lyrics both render with a thick black background-like outline that visually matches the existing Kugou-style screenshot: the dark shape follows the lyric text height instead of appearing as one full-width footer bar.

This change is intentionally scoped to generated karaoke subtitle styling only. Parsing, subtitle selection, and playback flow stay unchanged.

## Goals

- Make generated QQ Music karaoke lyrics render with the same black-backed look currently expected from Kugou playback.
- Apply the same visual treatment to both the main karaoke line and the translation line.
- Keep the black shape tied to glyph height and line content, not a full-width bottom strip.
- Preserve per-word `\kf` highlighting for the primary lyric line.
- Keep spider karaoke output as standard local `ASS` subtitles.

## Non-Goals

- Change QRC or KRC parsing rules.
- Add source-specific style branches for QQ and Kugou.
- Add new player controls, config, or lyric-specific UI.
- Replace the karaoke renderer with a custom mpv subtitle pipeline.

## Scope

Primary implementation should stay within:

- `src/atv_player/karaoke/ass.py`

Primary verification should stay within:

- `tests/test_karaoke_ass.py`

No controller or player-window behavior changes are required unless verification proves the renderer output alone is insufficient.

## Style Direction

The desired effect is closer to a thick black package around the text than to a thin subtitle outline:

- main lyric text remains white with yellow karaoke highlighting
- translation text remains smaller and visually subordinate
- both lines gain a much heavier black surround so the subtitle reads like it has a black background
- the dark area should grow and shrink with the actual lyric glyph height and text width
- the subtitle should still look like lyric text, not a rigid rectangular box

## Rendering Approach

Use explicit `ASS` style values to make the effect deterministic for all generated karaoke subtitles:

- keep one `KaraokeMain` style and one `KaraokeTranslation` style
- continue rendering the main line as one `Dialogue` event with `\kf` tags
- continue rendering the translation line as a separate `Dialogue` event with the same time window
- increase black outline and/or shadow values enough to create a visually continuous dark backing around the glyphs
- keep bottom-center alignment and current two-line stacking behavior

The renderer should not branch on `document.source_format`. QQ and Kugou must share the same output style so visual parity comes from one explicit renderer definition.

## Acceptance Criteria

- A generated QQ Music karaoke `.ass` file uses the updated heavy black-backed lyric styles.
- A generated Kugou karaoke `.ass` file uses the same updated styles.
- Main karaoke highlighting still emits ordered `\kf` tags with clamped centisecond durations.
- Translation lines still render as separate static dialogue events.
- The resulting style values are covered by tests so future refactors do not silently revert the appearance.

## Test Strategy

- Update renderer tests to assert the new `KaraokeMain` and `KaraokeTranslation` style lines.
- Keep existing tests that verify `\kf` output, translation dialogue emission, and static-line fallback.
- Do not add UI or integration tests unless renderer-only verification proves insufficient.
