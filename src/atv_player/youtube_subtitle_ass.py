from __future__ import annotations

from dataclasses import dataclass
import html
import re


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


_VTT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
_SRT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
_BRACKET_SPEAKER_RE = re.compile(r"^(?:\[(?P<speaker1>[^\]]+)\]|【(?P<speaker2>[^】]+)】)\s*(?P<text>.+)$")
_COLON_SPEAKER_RE = re.compile(r"^(?P<speaker>[^:：]{1,40})[:：]\s*(?P<text>.+)$")
_DASH_SPEAKER_RE = re.compile(r"^(?P<speaker>[^-]{1,40})\s-\s(?P<text>.+)$")
_WEBVTT_INLINE_TAG_RE = re.compile(r"<[^>]+>")
_ATTACHED_PUNCTUATION = ".,!?;:，。！？；：…"
_SPEAKER_PALETTE = ("YouTubeSpeaker1", "YouTubeSpeaker2", "YouTubeSpeaker3", "YouTubeSpeaker4")


def convert_youtube_subtitle_text_to_ass(text: str) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    cues = _parse_subtitle_cues(normalized)
    if not cues:
        return None
    styled_cues = _style_cues(cues)
    if not styled_cues:
        return None
    return _render_ass(styled_cues)


def _parse_subtitle_cues(text: str) -> list[Cue]:
    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        return _parse_webvtt_cues(stripped)
    if "-->" in stripped and "," in stripped:
        return _parse_srt_cues(stripped)
    return []


def _parse_webvtt_cues(text: str) -> list[Cue]:
    lines = text.splitlines()
    cues: list[Cue] = []
    index = 0
    while index < len(lines):
        timing_match = _VTT_TIMING_RE.search(lines[index].strip())
        if timing_match is None:
            index += 1
            continue
        index += 1
        payload: list[str] = []
        while index < len(lines) and lines[index].strip():
            payload.append(_clean_webvtt_payload_text(lines[index]))
            index += 1
        cue_text = " ".join(part for part in payload if part).strip()
        if cue_text:
            cues.append(
                Cue(
                    start_ms=_parse_timestamp_ms(timing_match.group("start")),
                    end_ms=_parse_timestamp_ms(timing_match.group("end")),
                    raw_text=cue_text,
                )
            )
        index += 1
    return [cue for cue in cues if cue.end_ms > cue.start_ms]


def _clean_webvtt_payload_text(text: str) -> str:
    without_tags = _WEBVTT_INLINE_TAG_RE.sub("", str(text or ""))
    unescaped = html.unescape(without_tags)
    return unescaped.strip()


def _parse_srt_cues(text: str) -> list[Cue]:
    blocks = re.split(r"\n\s*\n", text.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if _SRT_TIMING_RE.search(lines[0]):
            timing_line = lines[0]
            payload_lines = lines[1:]
        elif len(lines) >= 2 and _SRT_TIMING_RE.search(lines[1]):
            timing_line = lines[1]
            payload_lines = lines[2:]
        else:
            continue
        timing_match = _SRT_TIMING_RE.search(timing_line)
        if timing_match is None:
            continue
        cue_text = " ".join(payload_lines).strip()
        if not cue_text:
            continue
        cues.append(
            Cue(
                start_ms=_parse_timestamp_ms(timing_match.group("start")),
                end_ms=_parse_timestamp_ms(timing_match.group("end")),
                raw_text=cue_text,
            )
        )
    return [cue for cue in cues if cue.end_ms > cue.start_ms]


def _style_cues(cues: list[Cue]) -> list[StyledCue]:
    style_by_speaker: dict[str, str] = {}
    styled: list[StyledCue] = []
    for cue in cues:
        speaker, content_text = _split_speaker_prefix(cue.raw_text)
        normalized_content = content_text.strip()
        style_name = "YouTubeDefault"
        if speaker:
            speaker_key = " ".join(speaker.split()).casefold()
            if speaker_key not in style_by_speaker:
                style_by_speaker[speaker_key] = _SPEAKER_PALETTE[len(style_by_speaker) % len(_SPEAKER_PALETTE)]
            style_name = style_by_speaker[speaker_key]
        styled.append(
            StyledCue(
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                speaker=speaker,
                content_text=normalized_content,
                style_name=style_name,
                segments=_build_segments(normalized_content, cue.end_ms - cue.start_ms),
            )
        )
    return [cue for cue in styled if cue.content_text]


def _split_speaker_prefix(text: str) -> tuple[str, str]:
    stripped = text.strip()
    for pattern in (_BRACKET_SPEAKER_RE, _COLON_SPEAKER_RE, _DASH_SPEAKER_RE):
        match = pattern.match(stripped)
        if match is None:
            continue
        speaker = (
            match.groupdict().get("speaker")
            or match.groupdict().get("speaker1")
            or match.groupdict().get("speaker2")
            or ""
        )
        content = str(match.group("text") or "").strip()
        if content:
            return " ".join(speaker.split()), content
    return "", stripped


def _build_segments(text: str, duration_ms: int) -> list[tuple[str, int]]:
    visible_units = [char for char in text if not char.isspace() and char not in _ATTACHED_PUNCTUATION]
    if len(visible_units) < 2 or duration_ms < len(visible_units) * 10:
        return []
    base_duration = max(1, round(duration_ms / len(visible_units) / 10))
    segments: list[tuple[str, int]] = []
    for char in text:
        if char.isspace() or char in _ATTACHED_PUNCTUATION:
            if segments:
                previous_text, previous_duration = segments[-1]
                segments[-1] = (previous_text + char, previous_duration)
            continue
        segments.append((char, base_duration))
    return segments


def _render_ass(cues: list[StyledCue]) -> str:
    events = [_render_dialogue(cue) for cue in cues]
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: YouTubeDefault,Arial,44,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker1,Arial,44,&H00FFF27A,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker2,Arial,44,&H0078F0FF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker3,Arial,44,&H0090FF9A,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker4,Arial,44,&H0099B6FF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
        ]
    )


def _render_dialogue(cue: StyledCue) -> str:
    if cue.segments:
        text = "".join(rf"{{\kf{duration}}}{_escape_ass(segment)}" for segment, duration in cue.segments)
    else:
        text = _escape_ass(cue.content_text)
    return (
        f"Dialogue: 0,{_ass_time(cue.start_ms)},{_ass_time(cue.end_ms)},"
        f"{cue.style_name},,0,0,0,,{text}"
    )


def _parse_timestamp_ms(value: str) -> int:
    normalized = value.replace(",", ".")
    hours, minutes, seconds = normalized.split(":")
    whole_seconds, millis = seconds.split(".")
    return (
        int(hours) * 3600 * 1000
        + int(minutes) * 60 * 1000
        + int(whole_seconds) * 1000
        + int(millis)
    )


def _ass_time(value_ms: int) -> str:
    total_cs = max(0, round(value_ms / 10))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, centiseconds = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
