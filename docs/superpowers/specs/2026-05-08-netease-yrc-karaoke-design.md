# NetEase YRC Karaoke Design

## Summary

Add host-side support for `netease-yrc` spider lyric payloads so NetEase word-timed lyrics are normalized into the existing karaoke model, rendered into cached `ASS` subtitles, and exposed through the current spider external subtitle flow.

This change is intentionally narrow. It extends only the raw karaoke parser and related tests. The player UI, mpv integration, and ASS rendering pipeline remain unchanged.

## Goals

- Accept `lyric.format == "netease-yrc"` in spider plugin playback payloads.
- Parse NetEase YRC main lyric lines with per-word timing into the existing `KaraokeDocument` model.
- Preserve existing `ASS` karaoke generation and spider external subtitle behavior.
- Use best-effort parsing so malformed words or lines do not discard the rest of the lyric.
- Fall back to `subt` only when the YRC payload yields no usable lyric lines.

## Non-Goals

- Parse or render translation lyrics for NetEase YRC in this change.
- Add YRC-specific logic to the player UI or mpv widget.
- Introduce a new karaoke model, cache format, or subtitle option type.
- Filter timed credit lines such as `作词` or `作曲` when they are already encoded as timed lyric lines.

## Scope

Primary implementation should live in:

- `src/atv_player/karaoke/parser.py`

Primary verification should live in:

- `tests/test_karaoke_parser.py`
- `tests/test_spider_plugin_controller.py`

No controller or renderer design changes are required beyond recognizing that `parse_raw_karaoke()` can now return usable documents for `netease-yrc`.

## Source Format

NetEase YRC lines follow this shape:

```text
[20100,4770](20100,470,0)音(20570,270,0)乐(20840,460,0)停(21300,280,0)止(21580,1090,0)了
```

Normalization rules:

- line start is the first number in the `[]` header
- line duration is the second number in the `[]` header
- line end is `line_start + line_duration`
- each word token uses the shape `(start,duration,flag)text`
- token start is the first number inside `()`
- token duration is the second number inside `()`
- token end is `token_start + token_duration`
- the third token field is ignored in the first implementation
- token start is treated as an absolute timestamp in milliseconds
- line text is reconstructed by concatenating parsed token text in order
- spaces and punctuation from token text must be preserved

## Parsing Behavior

The parser should normalize YRC input into `KaraokeLine` and `KaraokeWord` values using the existing model.

Behavior rules:

- blank input produces an empty `KaraokeDocument`
- malformed lines that do not match the YRC line header are skipped
- malformed tokens inside an otherwise valid line are skipped individually
- tokens with blank text are skipped
- tokens with `duration <= 0` are skipped
- lines with no usable parsed tokens are skipped
- a document containing at least one valid lyric line is considered successful
- `translation` input is ignored for `netease-yrc`

Best-effort parsing is required. The parser must preserve all valid lines and words it can recover without treating isolated corruption as a fatal error.

## Controller Behavior

The existing spider controller integration remains the same:

1. `playerContent()` returns a `lyric` payload with `format="netease-yrc"`
2. `parse_raw_karaoke()` returns a normalized document
3. existing karaoke `ASS` rendering writes a cached subtitle file
4. the cached `.ass` file is exposed as `逐字歌词 [插件]`

Fallback rules:

- if parsing yields one or more valid lines, prefer the generated karaoke subtitle over `subt`
- if parsing yields zero valid lines, fall back to existing `subt` handling
- unsupported formats other than `netease-yrc` continue to fall back as before

## Testing

Add parser coverage for:

- parsing representative NetEase YRC lines into normalized absolute word timing
- preserving spaces and punctuation in reconstructed line text
- skipping malformed tokens while keeping the rest of the line or document
- treating blank or fully invalid YRC payloads as empty documents

Add controller coverage for:

- preferring generated `.ass` subtitles for valid `netease-yrc` payloads
- continuing to fall back for unknown karaoke formats
