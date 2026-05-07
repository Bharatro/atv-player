# Karaoke Black Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated spider karaoke subtitles for QQ Music and Kugou render with the same heavy black-backed lyric style for both the main line and translation line while preserving existing `\kf` timing behavior.

**Architecture:** Keep the change isolated to the karaoke `ASS` renderer. First tighten `tests/test_karaoke_ass.py` so it asserts the exact main and translation style lines for the new look, then update `src/atv_player/karaoke/ass.py` to emit those style lines without changing parsing, dialogue timing, or controller integration.

**Tech Stack:** Python, pytest, ASS subtitle styling

---

### Task 1: Update Karaoke Renderer Styles

**Files:**
- Modify: `tests/test_karaoke_ass.py`
- Modify: `src/atv_player/karaoke/ass.py`
- Test: `tests/test_karaoke_ass.py`

- [ ] **Step 1: Write the failing test**

Update `tests/test_karaoke_ass.py` so the existing renderer tests also lock down the new heavy black-backed style lines:

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

    assert (
        "Style: KaraokeMain,Arial,46,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,120,1"
        in subtitle
    )
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

    assert (
        "Style: KaraokeTranslation,Arial,28,&H00E8E8E8,&H00E8E8E8,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,6,0,2,60,60,70,1"
        in subtitle
    )
    assert "Dialogue: 0,0:00:00.00,0:00:01.80,KaraokeTranslation" in subtitle
    assert "Light boat already crossed" in subtitle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_karaoke_ass.py -q`
Expected: `FAIL` because the current renderer still emits the old thinner style lines with `BackColour=&H64000000`, `Outline=2`, and no heavy black-backed effect.

- [ ] **Step 3: Write minimal implementation**

Update `src/atv_player/karaoke/ass.py` so it emits the new explicit style lines while keeping the existing dialogue generation and timing helpers unchanged:

```python
from __future__ import annotations

from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord

_KARAOKE_MAIN_STYLE = (
    "Style: KaraokeMain,Arial,46,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,8,0,2,60,60,120,1"
)
_KARAOKE_TRANSLATION_STYLE = (
    "Style: KaraokeTranslation,Arial,28,&H00E8E8E8,&H00E8E8E8,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,6,0,2,60,60,70,1"
)


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
            _KARAOKE_MAIN_STYLE,
            _KARAOKE_TRANSLATION_STYLE,
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_karaoke_ass.py -q`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/karaoke/ass.py tests/test_karaoke_ass.py
git commit -m "feat: thicken karaoke lyric background styling"
```
