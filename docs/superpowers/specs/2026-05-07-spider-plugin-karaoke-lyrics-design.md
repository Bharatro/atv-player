# Spider Plugin Karaoke Lyrics Design

## Summary

Extend spider-plugin playback so `playerContent()` may return raw karaoke lyric text through `lyric`, and the app will parse that text into word-timed karaoke subtitles rendered as external `ASS` subtitles.

The first implementation is intentionally scoped to spider-plugin playback items and host-side parsing for QQ Music QRC and Kugou KRC. The player should continue to consume only ordinary external subtitle files, while the controller layer handles karaoke parsing, `ASS` generation, caching, and fallback to existing `subt` behavior.

## Goals

- Accept raw karaoke lyric payloads from spider-plugin `playerContent()`.
- Support host-side parsing for `qqmusic-qrc` and `kugou-krc`.
- Reserve a future `netease-yrc` format identifier without implementing it in this change.
- Convert parsed word-timed lyrics into `ASS karaoke` subtitles with per-word highlighting.
- Support an optional translation line displayed as a secondary lyric line without word-level highlighting.
- Reuse the existing `PlayItem.external_subtitles` and mpv external subtitle loading path.
- Preserve existing `subt` compatibility as a fallback when karaoke lyric parsing is unavailable or fails.

## Non-Goals

- Parse or render NetEase raw karaoke lyrics in this change.
- Add a new lyric-specific player panel, menu, or transport control.
- Teach the player UI or mpv widget to understand QRC, KRC, or YRC directly.
- Implement transliteration or per-word highlighting for translation text.
- Support multiple karaoke lyric payloads for one `playerContent()` response.
- Replace existing ordinary subtitle behavior provided through `subt`.

## Scope

Primary implementation should live in:

- `src/atv_player/plugins/controller.py`
- `src/atv_player/karaoke/models.py`
- `src/atv_player/karaoke/parser.py`
- `src/atv_player/karaoke/ass.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_karaoke_parser.py`
- `tests/test_karaoke_ass.py`
- `tests/test_player_window_ui.py`

The player window should not gain protocol-specific karaoke parsing logic. It should continue to operate on normalized external subtitle options only.

## Payload Contract

`playerContent()` may return:

```python
{
    "parse": 0,
    "url": "https://media.example/audio.m4a",
    "subt": "...",
    "lyric": {
        "format": "qqmusic-qrc",
        "text": "<raw lyric text>",
        "translation": "<optional raw translation text>",
    },
}
```

Rules:

- `lyric` is optional.
- `lyric.format` is required when `lyric` is present.
- `lyric.text` is required when `lyric` is present.
- the first implementation must accept `qqmusic-qrc` and `kugou-krc`
- `netease-yrc` is a reserved future format identifier and should be treated as unsupported for now
- `lyric.translation` is optional and may be blank
- `subt` remains available as a compatibility fallback for ordinary subtitles or non-karaoke lyrics

Priority rules:

- if `lyric` is present and successfully parsed, the generated karaoke `ASS` subtitle should be preferred over `subt`
- if `lyric` is missing, malformed, unsupported, or produces no valid lyric lines, the controller should fall back to existing `subt` handling

## Internal Model

Host-side karaoke parsing should normalize all supported raw formats into one internal document model before rendering.

Suggested model:

```python
@dataclass(slots=True)
class KaraokeWord:
    text: str
    start_ms: int
    end_ms: int


@dataclass(slots=True)
class KaraokeLine:
    start_ms: int
    end_ms: int
    text: str
    translation: str = ""
    words: list[KaraokeWord] = field(default_factory=list)


@dataclass(slots=True)
class KaraokeDocument:
    source_format: str
    offset_ms: int = 0
    lines: list[KaraokeLine] = field(default_factory=list)
```

Normalization rules:

- `KaraokeWord.start_ms` and `KaraokeWord.end_ms` must be absolute times after any source offset is applied
- `KaraokeLine.text` should be reconstructed from the ordered word list and preserve spaces and punctuation
- blank or invalid words should be skipped
- lines with no usable text should be skipped
- a document containing at least one valid lyric line should be considered usable

## Raw Format Parsing

### QQ Music QRC

QQ Music raw lines use a line header such as `[29264,3446]` and word-level timing tokens such as `故(29264,390)`.

Parsing rules:

- line start is the first number in the line header
- line duration is the second number in the line header
- line end is `line_start + line_duration`
- each word token contributes one `KaraokeWord`
- token start is the first number inside `(...)`
- token duration is the second number inside `(...)`
- token end is `token_start + token_duration`
- metadata headers such as `ti`, `ar`, `al`, `by`, and `offset` should not be emitted as lyric lines
- if an `offset` header exists, it should be applied to the final normalized word and line timing

### Kugou KRC

Kugou raw lines use a line header such as `[180,5340]` and word-level timing tokens such as `<0,480,0>轻`.

Parsing rules:

- line start is the first number in the line header
- line duration is the second number in the line header
- line end is `line_start + line_duration`
- each word token contributes one `KaraokeWord`
- token offset is the first number inside `<>`
- token duration is the second number inside `<>`
- the third value inside `<>` is ignored in the first implementation
- token start is `line_start + token_offset`
- token end is `token_start + token_duration`
- spaces represented as explicit timed tokens must be preserved

### Translation Handling

The optional `lyric.translation` field should be parsed independently when possible and aligned back onto normalized main lyric lines.

The first implementation should keep translation handling simple:

- translation lines should align to the nearest main lyric line by identical or overlapping time window when the source format provides timing
- if translation timing cannot be parsed reliably, translation may be dropped instead of guessing
- translation should populate `KaraokeLine.translation`
- translation should never block successful rendering of the main karaoke line

## ASS Karaoke Rendering

The host should convert a valid `KaraokeDocument` into one `.ass` subtitle file and expose that file as a spider external subtitle.

Rendering rules:

- render one primary `Dialogue` event per `KaraokeLine`
- render one optional translation `Dialogue` event per `KaraokeLine` when `translation` is non-blank
- use `\kf` tags for primary lyric highlighting
- each word duration should be converted from milliseconds to centiseconds for `\kf`
- each word should be emitted in order with its own `\kf` timing
- each primary dialogue event should use the line's `start_ms` and `end_ms`
- each translation dialogue event should use the same line `start_ms` and `end_ms`
- if a line has text but no valid word timings, render it as a plain static subtitle line instead of failing the document

Style rules:

- define one main karaoke style for the primary lyric line
- define one translation style for the secondary lyric line
- place both styles at the bottom center
- make the translation line smaller and vertically offset below the primary line
- keep the first implementation visually simple and readable; no complex animation beyond standard karaoke highlighting

Timing guards:

- word durations less than one centisecond should be clamped to one centisecond when emitted in `\kf`
- malformed words with `end_ms <= start_ms` should be skipped
- the sum of emitted word durations does not need to equal the line duration exactly
- dialogue end time should continue to use the normalized line end

## Controller Integration

`SpiderPluginController._resolve_play_item()` should remain the integration point.

After playback URL and headers are resolved:

1. inspect `payload.get("lyric")`
2. if valid, parse the raw lyric into `KaraokeDocument`
3. if parsing succeeds, render the document into `ASS`
4. write the generated subtitle into the subtitle cache directory
5. expose the generated file as one `ExternalSubtitleOption`
6. if any step fails or produces no valid lyric lines, fall back to existing `subt` handling

The generated subtitle option should use:

- a stable label such as `逐字歌词 [插件]`
- an empty language code
- the generated local `.ass` path as the subtitle URL
- `format="text/x-ass"`
- `source="spider"`

The generated karaoke subtitle should participate in existing spider subtitle behavior:

- it should appear in the primary subtitle selector like other spider external subtitles
- it should not be added to the secondary subtitle menu
- it should remain compatible with existing spider external subtitle auto-selection behavior when no embedded subtitle tracks are available

## Error Handling

Karaoke lyric failures must not interrupt media playback.

If the raw lyric payload is malformed, unsupported, or unparsable:

- keep playback URL resolution intact
- log a concise parsing or generation failure message
- fall back to `subt` if available
- otherwise expose no external subtitle for that lyric payload

If translation parsing fails but main lyric parsing succeeds:

- continue with main lyric rendering only

If cache writing fails:

- keep playback running
- log the failure
- fall back to `subt` if available

The controller should never expose a partially written or invalid subtitle path as an external subtitle option.

## Testing Strategy

Add parser tests for:

- parsing representative QQ Music QRC lines into normalized line and word timings
- ignoring QQ Music metadata headers
- parsing representative Kugou KRC lines into normalized line and word timings
- preserving spaces, punctuation, and mixed-language tokens
- rejecting malformed tokens without discarding the rest of the document
- treating `netease-yrc` as unsupported in the first implementation

Add `ASS` rendering tests for:

- converting normalized word timings into ordered `\kf` segments
- rendering a translation line beneath the primary karaoke line
- clamping zero or sub-centisecond durations safely
- degrading to plain static subtitle lines when no valid word timings remain

Add spider controller tests for:

- preferring `lyric` over `subt` when karaoke parsing succeeds
- falling back to `subt` when `lyric` is unsupported or malformed
- writing generated karaoke subtitles into the subtitle cache directory
- exposing generated karaoke subtitles as `text/x-ass` spider external subtitles

Add player-window tests for:

- listing generated spider karaoke subtitles in the primary subtitle combo
- reusing existing spider subtitle auto-selection behavior for generated karaoke subtitles
- keeping spider karaoke subtitles out of the secondary subtitle selector

## Implementation Order

1. Add failing parser tests for QQ Music QRC and Kugou KRC normalization.
2. Implement the internal karaoke model and raw format parser dispatch.
3. Add failing `ASS` rendering tests for per-word `\kf` output and translation dialogue generation.
4. Implement karaoke `ASS` rendering and cache writing helpers.
5. Add failing spider controller tests for `lyric` priority, cache output, and `subt` fallback.
6. Integrate karaoke parsing and rendering into `SpiderPluginController._resolve_play_item()`.
7. Run focused parser, renderer, controller, and player subtitle regressions.
