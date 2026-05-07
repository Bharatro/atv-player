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
