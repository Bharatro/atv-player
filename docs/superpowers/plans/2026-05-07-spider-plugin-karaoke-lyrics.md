# Spider Plugin Karaoke Lyrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let spider-plugin `playerContent()` return raw karaoke lyric payloads through `lyric`, parse QQ Music QRC and Kugou KRC in the host, render them into `ASS karaoke` subtitles with per-word highlighting, and expose the result through the existing spider external subtitle flow.

**Architecture:** Keep raw karaoke protocol parsing and `ASS` generation out of the player UI. Add a focused `atv_player.karaoke` package for normalized karaoke models, QQ/KRC parser dispatch, and `ASS` rendering, then integrate it in `SpiderPluginController` so generated `.ass` files land in the subtitle cache and become standard `ExternalSubtitleOption` entries. Reuse the current spider primary-subtitle behavior, including auto-selection when no embedded subtitles exist, and fall back to `subt` whenever `lyric` is unsupported or invalid.

**Tech Stack:** Python 3.12, dataclasses, regex, hashlib, pathlib, PySide6, pytest, pytest-qt, `uv`

---

## File Structure

- `src/atv_player/karaoke/__init__.py`
  - Export the normalized karaoke model and parsing/rendering entry points used by the controller.
- `src/atv_player/karaoke/models.py`
  - Define `KaraokeWord`, `KaraokeLine`, and `KaraokeDocument`.
- `src/atv_player/karaoke/parser.py`
  - Parse `qqmusic-qrc` and `kugou-krc` raw text into the normalized karaoke model, and reject unsupported formats such as `netease-yrc`.
- `src/atv_player/karaoke/ass.py`
  - Render a normalized karaoke document into `.ass` text with primary `\kf` highlighting and optional translation dialogue lines.
- `src/atv_player/plugins/controller.py`
  - Prefer `lyric` over `subt`, generate cached `.ass` files for valid karaoke payloads, and fall back safely when parsing or rendering fails.
- `tests/test_karaoke_parser.py`
  - Lock down deterministic QQ/KRC parsing behavior and unsupported-format fallback.
- `tests/test_karaoke_ass.py`
  - Lock down deterministic `ASS karaoke` output and timing clamping behavior.
- `tests/test_spider_plugin_controller.py`
  - Verify lyric priority, `.ass` cache output, and `subt` fallback behavior.
- `tests/test_player_window_ui.py`
  - Verify generated spider karaoke subtitles behave like ordinary spider `text/x-ass` external subtitles in the primary subtitle flow.

### Task 1: Add The Karaoke Model And Raw Parser

**Files:**
- Create: `src/atv_player/karaoke/__init__.py`
- Create: `src/atv_player/karaoke/models.py`
- Create: `src/atv_player/karaoke/parser.py`
- Create: `tests/test_karaoke_parser.py`
- Test: `tests/test_karaoke_parser.py`

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_karaoke_parser.py` with these focused tests:

```python
from atv_player.karaoke.parser import parse_raw_karaoke


def test_parse_qqmusic_qrc_normalizes_word_timing_and_ignores_metadata() -> None:
    document = parse_raw_karaoke(
        "qqmusic-qrc",
        """<?xml version="1.0" encoding="utf-8"?>
<QrcInfos>
<LyricInfo LyricCount="1">
<Lyric_1 LyricType="1" LyricContent="[ti:晴天]
[offset:0]
[29264,3446]故(29264,390)事(29654,392)的(30046,448)小(30494,922)黄(31416,374)花(31790,504)
"/>
</LyricInfo>
</QrcInfos>
""",
    )

    assert document.source_format == "qqmusic-qrc"
    assert document.lines[0].start_ms == 29264
    assert document.lines[0].end_ms == 32710
    assert document.lines[0].text == "故事的小黄花"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("故", 29264, 29654),
        ("事", 29654, 30046),
        ("的", 30046, 30494),
        ("小", 30494, 31416),
        ("黄", 31416, 31790),
        ("花", 31790, 32294),
    ]


def test_parse_kugou_krc_normalizes_relative_offsets_and_preserves_spaces() -> None:
    document = parse_raw_karaoke(
        "kugou-krc",
        """[180,5340]<0,480,0>轻<480,570,0>舟<1050,480,0>已<1530,900,0>过<2430,0,0> <2430,570,0>万<3000,750,0>重<3750,1080,0>山""",
    )

    assert document.source_format == "kugou-krc"
    assert document.lines[0].text == "轻舟已过 万重山"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("轻", 180, 660),
        ("舟", 660, 1230),
        ("已", 1230, 1710),
        ("过", 1710, 2610),
        (" ", 2610, 2610),
        ("万", 2610, 3180),
        ("重", 3180, 3930),
        ("山", 3930, 5010),
    ]


def test_parse_raw_karaoke_rejects_unsupported_format() -> None:
    document = parse_raw_karaoke("netease-yrc", "[0,1000](0,1000,0)测试")
    assert document.lines == []
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run:

```bash
uv run pytest tests/test_karaoke_parser.py -q
```

Expected: `FAIL` with `ModuleNotFoundError: No module named 'atv_player.karaoke'`.

- [ ] **Step 3: Write the minimal karaoke model and parser implementation**

Create `src/atv_player/karaoke/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


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

Create `src/atv_player/karaoke/parser.py`:

```python
from __future__ import annotations

import re
from html import unescape

from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord

_QQ_LINE_RE = re.compile(r"^\[(?P<start>\d+),(?P<duration>\d+)\](?P<body>.+)$")
_QQ_WORD_RE = re.compile(r"(?P<text>.*?)[(](?P<start>\d+),(?P<duration>\d+)[)]")
_KG_LINE_RE = re.compile(r"^\[(?P<start>\d+),(?P<duration>\d+)\](?P<body>.+)$")
_KG_WORD_RE = re.compile(r"<(?P<offset>\d+),(?P<duration>\d+),(?P<flag>\d+)>(?P<text>[^<]*)")
_QQ_OFFSET_RE = re.compile(r"^\[offset:(?P<offset>-?\d+)\]$")


def parse_raw_karaoke(format_name: str, text: str, translation: str = "") -> KaraokeDocument:
    normalized = str(format_name or "").strip().lower()
    if normalized == "qqmusic-qrc":
        return parse_qqmusic_qrc(text, translation=translation)
    if normalized == "kugou-krc":
        return parse_kugou_krc(text, translation=translation)
    return KaraokeDocument(source_format=normalized)


def parse_qqmusic_qrc(text: str, translation: str = "") -> KaraokeDocument:
    content = unescape(str(text or ""))
    offset_ms = 0
    lines: list[KaraokeLine] = []
    for raw_line in _extract_qrc_lyric_lines(content):
        offset_match = _QQ_OFFSET_RE.match(raw_line)
        if offset_match is not None:
            offset_ms = int(offset_match.group("offset"))
            continue
        match = _QQ_LINE_RE.match(raw_line)
        if match is None:
            continue
        line_start = int(match.group("start")) + offset_ms
        line_duration = int(match.group("duration"))
        words: list[KaraokeWord] = []
        cursor = 0
        for word_match in _QQ_WORD_RE.finditer(match.group("body")):
            token_text = word_match.group("text")
            if not token_text:
                continue
            word_start = int(word_match.group("start")) + offset_ms
            word_end = word_start + int(word_match.group("duration"))
            words.append(KaraokeWord(text=token_text, start_ms=word_start, end_ms=word_end))
            cursor = word_match.end()
        line_text = "".join(word.text for word in words)
        if line_text:
            lines.append(
                KaraokeLine(
                    start_ms=line_start,
                    end_ms=line_start + line_duration,
                    text=line_text,
                    translation="",
                    words=words,
                )
            )
    return KaraokeDocument(source_format="qqmusic-qrc", offset_ms=offset_ms, lines=lines)


def parse_kugou_krc(text: str, translation: str = "") -> KaraokeDocument:
    lines: list[KaraokeLine] = []
    for raw_line in str(text or "").splitlines():
        match = _KG_LINE_RE.match(raw_line)
        if match is None:
            continue
        line_start = int(match.group("start"))
        line_duration = int(match.group("duration"))
        words: list[KaraokeWord] = []
        for word_match in _KG_WORD_RE.finditer(match.group("body")):
            token_text = word_match.group("text")
            if token_text == "":
                continue
            word_start = line_start + int(word_match.group("offset"))
            word_end = word_start + int(word_match.group("duration"))
            words.append(KaraokeWord(text=token_text, start_ms=word_start, end_ms=word_end))
        line_text = "".join(word.text for word in words)
        if line_text:
            lines.append(
                KaraokeLine(
                    start_ms=line_start,
                    end_ms=line_start + line_duration,
                    text=line_text,
                    translation="",
                    words=words,
                )
            )
    return KaraokeDocument(source_format="kugou-krc", lines=lines)


def _extract_qrc_lyric_lines(content: str) -> list[str]:
    match = re.search(r'LyricContent="(?P<body>.*)"\s*/>', content, re.S)
    if match is None:
        return []
    lyric_body = match.group("body").replace("\\n", "\n")
    return [line.strip() for line in lyric_body.splitlines() if line.strip()]
```

Create `src/atv_player/karaoke/__init__.py`:

```python
from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord
from atv_player.karaoke.parser import parse_raw_karaoke

__all__ = [
    "KaraokeDocument",
    "KaraokeLine",
    "KaraokeWord",
    "parse_raw_karaoke",
]
```

- [ ] **Step 4: Run the parser tests to verify they pass**

Run:

```bash
uv run pytest tests/test_karaoke_parser.py -q
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/karaoke/__init__.py src/atv_player/karaoke/models.py src/atv_player/karaoke/parser.py tests/test_karaoke_parser.py
git commit -m "feat: parse spider karaoke lyrics"
```

### Task 2: Render Normalized Karaoke Into ASS

**Files:**
- Create: `src/atv_player/karaoke/ass.py`
- Create: `tests/test_karaoke_ass.py`
- Modify: `src/atv_player/karaoke/__init__.py`
- Test: `tests/test_karaoke_ass.py`

- [ ] **Step 1: Write the failing ASS renderer tests**

Create `tests/test_karaoke_ass.py`:

```python
from atv_player.karaoke.ass import render_karaoke_ass
from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord


def test_render_karaoke_ass_emits_kf_segments_for_each_word() -> None:
    document = KaraokeDocument(
        source_format="qqmusic-qrc",
        lines=[
            KaraokeLine(
                start_ms=29264,
                end_ms=32710,
                text="故事的小黄花",
                words=[
                    KaraokeWord(text="故", start_ms=29264, end_ms=29654),
                    KaraokeWord(text="事", start_ms=29654, end_ms=30046),
                    KaraokeWord(text="的", start_ms=30046, end_ms=30494),
                ],
            )
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert "Style: KaraokeMain" in subtitle
    assert "Dialogue: 0,0:00:29.26,0:00:32.71,KaraokeMain" in subtitle
    assert r"{\kf39}故{\kf39}事{\kf45}的" in subtitle


def test_render_karaoke_ass_adds_static_translation_dialogue() -> None:
    document = KaraokeDocument(
        source_format="kugou-krc",
        lines=[
            KaraokeLine(
                start_ms=0,
                end_ms=1800,
                text="轻舟已过",
                translation="Light boat already crossed",
                words=[
                    KaraokeWord(text="轻", start_ms=0, end_ms=450),
                    KaraokeWord(text="舟", start_ms=450, end_ms=900),
                    KaraokeWord(text="已", start_ms=900, end_ms=1200),
                    KaraokeWord(text="过", start_ms=1200, end_ms=1800),
                ],
            )
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert "Style: KaraokeTranslation" in subtitle
    assert "Dialogue: 0,0:00:00.00,0:00:01.80,KaraokeTranslation" in subtitle
    assert "Light boat already crossed" in subtitle


def test_render_karaoke_ass_clamps_zero_length_tokens_and_degrades_to_static_line() -> None:
    document = KaraokeDocument(
        source_format="kugou-krc",
        lines=[
            KaraokeLine(
                start_ms=180,
                end_ms=1200,
                text="轻 舟",
                words=[
                    KaraokeWord(text="轻", start_ms=180, end_ms=180),
                    KaraokeWord(text=" ", start_ms=180, end_ms=180),
                    KaraokeWord(text="舟", start_ms=180, end_ms=660),
                ],
            ),
            KaraokeLine(start_ms=1500, end_ms=2200, text="静态行", words=[]),
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert r"{\kf1}轻" in subtitle
    assert "Dialogue: 0,0:00:01.50,0:00:02.20,KaraokeMain,,0,0,0,,静态行" in subtitle
```

- [ ] **Step 2: Run the ASS renderer tests to verify they fail**

Run:

```bash
uv run pytest tests/test_karaoke_ass.py -q
```

Expected: `FAIL` with `ModuleNotFoundError: No module named 'atv_player.karaoke.ass'`.

- [ ] **Step 3: Write the minimal ASS renderer**

Create `src/atv_player/karaoke/ass.py`:

```python
from __future__ import annotations

from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord


def render_karaoke_ass(document: KaraokeDocument) -> str:
    events: list[str] = []
    for line in document.lines:
        events.append(_render_main_dialogue(line))
        if line.translation.strip():
            events.append(_render_translation_dialogue(line))
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: KaraokeMain,Arial,46,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,120,1",
            "Style: KaraokeTranslation,Arial,28,&H00E8E8E8,&H00E8E8E8,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,70,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
        ]
    )


def _render_main_dialogue(line: KaraokeLine) -> str:
    text = "".join(_render_word(word) for word in line.words) if line.words else line.text
    return f"Dialogue: 0,{_ass_time(line.start_ms)},{_ass_time(line.end_ms)},KaraokeMain,,0,0,0,,{text}"


def _render_translation_dialogue(line: KaraokeLine) -> str:
    return f"Dialogue: 0,{_ass_time(line.start_ms)},{_ass_time(line.end_ms)},KaraokeTranslation,,0,0,0,,{line.translation}"


def _render_word(word: KaraokeWord) -> str:
    duration_cs = max(1, round((word.end_ms - word.start_ms) / 10))
    return rf"{{\kf{duration_cs}}}{word.text}"


def _ass_time(value_ms: int) -> str:
    total_cs = max(0, round(value_ms / 10))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, centiseconds = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
```

Update `src/atv_player/karaoke/__init__.py` so the `render_karaoke_ass` import resolves from the created module:

```python
from atv_player.karaoke.ass import render_karaoke_ass
from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord
from atv_player.karaoke.parser import parse_raw_karaoke

__all__ = [
    "KaraokeDocument",
    "KaraokeLine",
    "KaraokeWord",
    "parse_raw_karaoke",
    "render_karaoke_ass",
]
```

- [ ] **Step 4: Run the ASS renderer tests to verify they pass**

Run:

```bash
uv run pytest tests/test_karaoke_ass.py -q
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/karaoke/__init__.py src/atv_player/karaoke/ass.py tests/test_karaoke_ass.py
git commit -m "feat: render spider karaoke ass subtitles"
```

### Task 3: Integrate `lyric` In Spider Plugin Controller With `subt` Fallback

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing controller tests**

Add these helpers and tests to `tests/test_spider_plugin_controller.py` near `SubtitlePayloadSpider`:

```python
class LyricPayloadSpider(FakeSpider):
    def __init__(self, lyric: object, subt: str = "") -> None:
        self._lyric = lyric
        self._subt = subt

    def playerContent(self, flag, id, vipFlags):
        payload = {
            "parse": 0,
            "url": f"https://stream.example{id}.m3u8",
            "header": {"Referer": "https://site.example"},
        }
        if self._lyric is not None:
            payload["lyric"] = self._lyric
        if self._subt:
            payload["subt"] = self._subt
        return payload


def test_controller_build_request_prefers_generated_karaoke_subtitle_over_subt(tmp_path, monkeypatch) -> None:
    cache_root = tmp_path / "app-cache"
    monkeypatch.setattr(controller_module, "app_cache_dir", lambda: cache_root)
    controller = SpiderPluginController(
        LyricPayloadSpider(
            {
                "format": "kugou-krc",
                "text": "[0,1800]<0,450,0>轻<450,450,0>舟<900,450,0>已<1350,450,0>过",
            },
            subt="https://cdn.example/fallback.srt",
        ),
        plugin_name="歌词插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert len(first.external_subtitles) == 1
    subtitle = first.external_subtitles[0]
    assert subtitle.name == "逐字歌词 [插件]"
    assert subtitle.format == "text/x-ass"
    assert subtitle.source == "spider"
    assert Path(subtitle.url).suffix == ".ass"
    assert r"{\kf45}轻{\kf45}舟{\kf45}已{\kf45}过" in Path(subtitle.url).read_text(encoding="utf-8")


def test_controller_build_request_falls_back_to_subt_when_lyric_format_is_unsupported() -> None:
    controller = SpiderPluginController(
        LyricPayloadSpider(
            {"format": "netease-yrc", "text": "[0,1000](0,1000,0)测试"},
            subt="https://cdn.example/fallback.srt",
        ),
        plugin_name="歌词插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert [(sub.name, sub.url, sub.format, sub.source) for sub in first.external_subtitles] == [
        ("外挂字幕 [插件]", "https://cdn.example/fallback.srt", "application/x-subrip", "spider"),
    ]


def test_controller_build_request_ignores_invalid_lyric_without_breaking_playback() -> None:
    controller = SpiderPluginController(
        LyricPayloadSpider({"format": "qqmusic-qrc", "text": ""}),
        plugin_name="歌词插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1.m3u8"
    assert first.external_subtitles == []
```

- [ ] **Step 2: Run the focused controller tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_spider_plugin_controller.py::test_controller_build_request_prefers_generated_karaoke_subtitle_over_subt \
  tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_subt_when_lyric_format_is_unsupported \
  tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_invalid_lyric_without_breaking_playback \
  -q
```

Expected: `FAIL` because `SpiderPluginController` ignores `lyric` and never generates `.ass` subtitles.

- [ ] **Step 3: Implement the minimal controller helpers and integration**

In `src/atv_player/plugins/controller.py`, extend imports:

```python
from atv_player.karaoke import parse_raw_karaoke, render_karaoke_ass
```

Add helpers near the subtitle cache helpers:

```python
def _write_inline_spider_karaoke_to_cache(text: str) -> Path:
    cache_dir = app_cache_dir() / "subtitles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    target_path = cache_dir / f"karaoke_{digest}.ass"
    if not target_path.exists():
        target_path.write_text(text, encoding="utf-8")
    return target_path
```

Add karaoke normalization helpers inside `SpiderPluginController`:

```python
    def _map_spider_karaoke_subtitle(self, payload: object) -> list[ExternalSubtitleOption]:
        if not isinstance(payload, Mapping):
            return []
        format_name = str(payload.get("format") or "").strip()
        text = str(payload.get("text") or "")
        translation = str(payload.get("translation") or "")
        if not format_name or not text.strip():
            return []
        document = parse_raw_karaoke(format_name, text, translation=translation)
        if not document.lines:
            return []
        subtitle_path = _write_inline_spider_karaoke_to_cache(render_karaoke_ass(document))
        return [
            ExternalSubtitleOption(
                name="逐字歌词 [插件]",
                lang="",
                url=str(subtitle_path),
                format="text/x-ass",
                source="spider",
            )
        ]
```

In `_resolve_play_item()`, replace the plain `subt` assignment:

```python
        item.external_subtitles = self._map_spider_karaoke_subtitle(payload.get("lyric"))
        if not item.external_subtitles:
            item.external_subtitles = self._map_spider_external_subtitles(payload.get("subt"))
```

Do not change `PlayerWindow` logic in this task.

- [ ] **Step 4: Run the focused controller tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_spider_plugin_controller.py::test_controller_build_request_prefers_generated_karaoke_subtitle_over_subt \
  tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_subt_when_lyric_format_is_unsupported \
  tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_invalid_lyric_without_breaking_playback \
  -q
```

Expected: `3 passed`

- [ ] **Step 5: Run the broader spider controller regression suite**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -q
```

Expected: `PASS` with existing `subt`, danmaku, drive, and quality tests still green.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: generate spider karaoke subtitles"
```

### Task 4: Add Player Regression Coverage For Generated Spider Karaoke Subtitles

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the player regression test**

Add this test near the existing spider subtitle auto-load tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_auto_loads_generated_spider_karaoke_ass_from_local_path(qtbot, tmp_path) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[tuple[str, bool]] = []
            self.subtitle_apply_calls: list[tuple[str, int | None]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            self.subtitle_apply_calls.append((mode, track_id))
            return track_id

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append((path, select_for_secondary))
            return 91

        def position_seconds(self) -> int:
            return 0

    subtitle_path = tmp_path / "plugin-karaoke.ass"
    subtitle_path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: KaraokeMain,Arial,46,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,120,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:00.00,0:00:01.80,KaraokeMain,,0,0,0,,{\kf45}轻{\kf45}舟{\kf45}已{\kf45}过\n",
        encoding="utf-8",
    )

    session = PlayerSession(
        vod=VodItem(vod_id="sp1", vod_name="插件视频"),
        playlist=[
            PlayItem(
                title="第1集",
                url="http://m/1.m3u8",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="逐字歌词 [插件]",
                        lang="",
                        url=str(subtitle_path),
                        format="text/x-ass",
                        source="spider",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    assert [select_for_secondary for _path, select_for_secondary in window.video.loaded_external_subtitles] == [False]
    assert window.video.subtitle_apply_calls == [("track", 91)]
    assert window.subtitle_combo.currentText() == "逐字歌词 [插件]"
```

- [ ] **Step 2: Run the focused player regression test**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_auto_loads_generated_spider_karaoke_ass_from_local_path -q
```

Expected: `PASS` after Task 3 because `PlayerWindow` already treats local spider `text/x-ass` subtitles like other spider external subtitles.

- [ ] **Step 3: Run the broader spider subtitle UI regression tests**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_lists_spider_external_subtitle_in_primary_combo \
  tests/test_player_window_ui.py::test_player_window_auto_loads_spider_subtitle_when_no_embedded_tracks \
  tests/test_player_window_ui.py::test_player_window_auto_loads_generated_spider_karaoke_ass_from_local_path \
  tests/test_player_window_ui.py::test_player_window_secondary_menu_excludes_spider_external_subtitles \
  -q
```

Expected: `PASS`

- [ ] **Step 4: Commit**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover generated spider karaoke subtitles"
```

## Self-Review

- Spec coverage:
  - `lyric` payload contract is implemented in Task 3.
  - normalized karaoke model is implemented in Task 1.
  - QQ Music QRC and Kugou KRC parsing are covered in Task 1.
  - per-word `ASS karaoke` rendering and translation dialogue are covered in Task 2.
  - controller-side `.ass` caching and `subt` fallback are covered in Task 3.
  - player reuse of spider primary subtitle flow is verified in Task 4.
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to” references remain.
  - each code-changing step includes concrete file paths, commands, and code.
- Type consistency:
  - the plan uses `KaraokeWord`, `KaraokeLine`, `KaraokeDocument`, `parse_raw_karaoke`, and `render_karaoke_ass` consistently across tasks.
