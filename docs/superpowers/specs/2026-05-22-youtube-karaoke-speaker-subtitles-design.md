# YouTube Karaoke Speaker Subtitles Design

## Summary

Add a host-side YouTube subtitle styling pipeline that converts `yt-dlp` subtitle text into external `ASS` subtitles with two enhancements:

- approximate per-character karaoke highlighting
- per-speaker color differentiation based on simple text-prefix detection

The first implementation is intentionally narrow. It applies only to YouTube subtitles discovered through the existing `yt-dlp` playback flow, supports uploaded subtitles plus automatic captions, and falls back to the original subtitle text whenever conversion is unsupported or fails.

## Goals

- Reuse the existing `yt-dlp -> ExternalSubtitleOption -> PlayerWindow -> external subtitle file -> mpv` playback flow.
- Support both uploaded YouTube subtitles and YouTube automatic captions when they arrive as ordinary `vtt` or `srt` text.
- Convert eligible subtitle text into one generated `.ass` file before loading it into `mpv`.
- Detect simple speaker prefixes such as `Alice:`, `Alice：`, `[Alice]`, and `【Alice】` and map different speakers to different subtitle colors.
- Render approximate karaoke timing by splitting each subtitle cue duration across visible characters.
- Keep playback working even when subtitle conversion is impossible or partially degraded.

## Non-Goals

- Modify YouTube's web player, DOM, CSS, or native web subtitle rendering.
- Require `mpv` or `PlayerWindow` to understand YouTube-specific subtitle formats directly.
- Add a settings UI for speaker palettes, conversion toggles, or karaoke timing configuration.
- Parse semantic speaker metadata from richer YouTube caption formats such as `json3` or `srv3` in this change.
- Achieve exact YouTube word-level timing parity with the web player.
- Apply this conversion flow to non-YouTube subtitle sources.

## Scope

Primary implementation should live in:

- `src/atv_player/youtube_subtitle_ass.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_youtube_subtitle_ass.py`
- `tests/test_player_window_ui.py`

`src/atv_player/yt_dlp_service.py` should keep its current responsibility: discover available subtitle options and expose them as `ExternalSubtitleOption` values. It should not become the subtitle conversion layer.

## Architecture

The existing playback path remains intact:

1. `yt-dlp` resolves the YouTube item and exposes subtitle options.
2. `PlayerWindow` fetches the selected subtitle text.
3. the app writes a local subtitle file and asks `mpv` to load it.

This change adds one conversion step between subtitle fetch and subtitle file write:

1. fetch subtitle text
2. decide whether the subtitle is an eligible YouTube subtitle
3. if eligible, attempt `vtt/srt -> styled ASS`
4. if conversion succeeds, write `.ass`
5. otherwise write the original subtitle text using the existing suffix logic

The player window remains the integration point because it already owns subtitle text fetch, local subtitle file creation, and the decision of what file format gets passed to `mpv`.

## Eligibility Rules

The conversion attempt should run only when all of these are true:

- `subtitle.source == "ytdlp"`
- the current playback item resolved through the YouTube extractor path
- the fetched subtitle text is recognized as `vtt` or `srt`
- the subtitle is not already `ass` or `ssa`

If any condition is false, the app should skip conversion and preserve current behavior.

YouTube uploaded subtitles and YouTube automatic captions should use the same conversion path once their text is fetched successfully.

## Subtitle Conversion Module

Create a focused helper module dedicated to ordinary subtitle text to `ASS` conversion.

Suggested internal structures:

```python
@dataclass(slots=True)
class Cue:
    start_ms: int
    end_ms: int
    raw_text: str


@dataclass(slots=True)
class StyledCue:
    start_ms: int
    end_ms: int
    speaker: str
    content_text: str
    style_name: str
    segments: list[tuple[str, int]]
```

The helper should expose a narrow API such as:

```python
def convert_youtube_subtitle_text_to_ass(text: str) -> str | None:
    ...
```

Return rules:

- return generated `ASS` text when conversion succeeds
- return `None` when the input is unsupported or cannot be converted safely

The helper should not perform network requests, write files, or reference Qt widgets.

## Subtitle Parsing

The first implementation should support:

- WebVTT text beginning with `WEBVTT`
- ordinary SubRip text with numbered or unnumbered cue blocks

Parsing behavior:

- preserve cue order
- parse cue start and end timestamps into milliseconds
- skip malformed cue blocks individually instead of failing the whole document
- normalize multi-line cue text into one visible line by joining lines with spaces
- trim outer whitespace
- skip cues whose visible text is blank after normalization
- skip cues with `end_ms <= start_ms`

Best-effort parsing is required. A document containing at least one usable cue is considered convertible.

## Speaker Detection

Speaker detection should use plain text prefixes only, in this priority order:

1. bracketed prefixes such as `[Alice] hello` and `【Alice】你好`
2. colon prefixes such as `Alice: hello` and `Alice：你好`
3. dash prefixes such as `Alice - hello`

Normalization rules:

- strip outer whitespace around detected speaker names
- collapse repeated inner whitespace in speaker names
- treat speaker matching as case-sensitive display text but use a normalized key for palette reuse
- remove the detected prefix from the rendered subtitle content
- if the remaining content is blank, treat the cue as having no speaker prefix and render the original text instead

No semantic guessing should be added. If a cue does not match one of the supported prefix patterns, it should be treated as a normal non-speaker cue.

## Style And Color Rules

Generated `ASS` should define:

- one default karaoke style for cues without a detected speaker
- a small fixed set of speaker styles with distinct primary colors

Recommended palette order:

- default: white
- speaker 1: cyan
- speaker 2: yellow
- speaker 3: green
- speaker 4: orange-pink

Rules:

- the first distinct detected speaker in one subtitle file gets speaker style 1
- later speakers consume the remaining palette in order
- when palette capacity is exceeded, wrap around deterministically
- the same speaker within one generated subtitle file must always map to the same style
- all styles should remain bottom-centered and visually close to existing readable subtitle defaults

This change should not add persistent cross-video speaker color memory.

## Approximate Karaoke Timing

The first implementation should use simple duration splitting rather than exact word timing.

Rules:

- determine the cue duration as `end_ms - start_ms`
- identify visible characters from `content_text`
- whitespace-only characters should not receive standalone highlight durations
- punctuation and spaces should attach to the previous visible character when possible
- split the cue duration as evenly as possible across the participating visible characters
- convert per-character durations to centiseconds for `\kf`
- clamp each emitted `\kf` duration to at least one centisecond

If a cue has no usable visible characters after normalization, conversion for that cue should degrade to a static subtitle line rather than failing the whole subtitle file.

If the cue duration is too short or otherwise unsuitable for reasonable splitting, the cue may degrade to a static `Dialogue` line with the assigned style.

## ASS Rendering

Each usable cue should render as one `Dialogue` event using the cue start and end time.

Rendering rules:

- use the detected speaker style or the default style
- emit karaoke `\kf` segments when segment timing was built successfully
- emit a plain static line when karaoke segmentation is unavailable for that cue
- render only the cleaned cue content, not the speaker prefix
- escape `ASS` special characters as needed

The generated script should remain compatible with the current external subtitle loading path, which already accepts `.ass` files.

## Player Integration

`PlayerWindow._load_external_subtitle()` should remain the narrow integration point.

Suggested behavior:

1. fetch subtitle text using the existing helper
2. validate the fetched text using current YouTube HTML guard behavior
3. decide whether the subtitle is eligible for conversion
4. if eligible, call the new conversion helper
5. if conversion returns `ASS` text, write it with `.ass` suffix
6. otherwise continue with the original subtitle text and existing suffix selection

No YouTube-specific parsing logic should be added to `mpv_widget.py`.

## Error Handling And Fallbacks

Subtitle styling failures must never interrupt playback.

Fallback rules:

- parse failure for the whole document: keep the original subtitle text
- malformed individual cues: skip or degrade only those cues
- no detected speaker prefixes: still allow karaoke conversion with the default style
- cue-level karaoke segmentation failure: render that cue as static text
- unsupported format or already-ASS input: keep the original subtitle text
- any unexpected conversion exception: log a concise failure and keep the original subtitle text

The app should prefer a degraded but readable subtitle over a hard failure.

## Testing

Add focused coverage in `tests/test_youtube_subtitle_ass.py` for:

- parsing representative `vtt` cues
- parsing representative `srt` cues
- detecting `[Alice]`, `【Alice】`, `Alice:`, and `Alice：` prefixes
- preserving non-speaker text when no prefix matches
- assigning stable speaker styles across multiple cues
- generating `\kf` karaoke output for normal cues
- degrading short or unsuitable cues to static `Dialogue` lines
- returning `None` for unsupported or unusable input

Add focused coverage in `tests/test_player_window_ui.py` for:

- YouTube `ytdlp` subtitles that convert to `.ass` before loading
- non-YouTube or non-eligible subtitles that continue loading unchanged
- conversion failure paths that fall back to original subtitle text
- existing HTML guard behavior remaining intact for blocked YouTube caption responses

## Implementation Sequence

1. Add failing unit tests for subtitle parsing, speaker detection, and `ASS` generation.
2. Implement the isolated conversion helper module.
3. Add failing player-window tests for YouTube subtitle conversion and fallback behavior.
4. Integrate the conversion helper into `PlayerWindow._load_external_subtitle()`.
5. Run focused subtitle conversion and player subtitle regression tests.
