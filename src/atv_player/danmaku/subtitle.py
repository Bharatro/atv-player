from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

_VALID_RENDER_MODES = {"static", "scroll_only", "mixed"}
_VALID_COLOR_MODES = {"uniform", "source"}
_VALID_POSITION_PRESETS = {"top", "upper", "mid_upper", "bottom"}
_PLAY_RES_X = 1920
_PLAY_RES_Y = 1080
_LANE_HEIGHT = 40
_DEFAULT_FONT_SIZE = 32
_DEFAULT_UNIFORM_COLOR = "#FFFFFF"


@dataclass(frozen=True, slots=True)
class _ParsedDanmaku:
    time_offset: float
    pos: int
    color: str
    content: str


@dataclass(frozen=True, slots=True)
class _SubtitleLine:
    start: float
    end: float
    line_index: int
    content: str
    color: str


@dataclass(frozen=True, slots=True)
class _SubtitleCue:
    start: float
    end: float
    lines: tuple[_SubtitleLine, ...]


@dataclass(frozen=True, slots=True)
class _TimedDanmaku:
    record: _ParsedDanmaku
    line_index: int
    start: float
    end: float


def _format_srt_timestamp(value: float) -> str:
    total_milliseconds = max(0, int(round(value * 1000)))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _format_ass_timestamp(value: float) -> str:
    total_centiseconds = max(0, int(round(value * 100)))
    hours, remainder = divmod(total_centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _normalize_render_mode(value: str) -> str:
    return value if value in _VALID_RENDER_MODES else "static"


def _normalize_color_mode(value: str) -> str:
    return value if value in _VALID_COLOR_MODES else "uniform"


def _normalize_position_preset(value: str) -> str:
    return value if value in _VALID_POSITION_PRESETS else "top"


def _normalize_hex_color(value: str) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
        except ValueError:
            return _DEFAULT_UNIFORM_COLOR
        return text
    return _DEFAULT_UNIFORM_COLOR


def _hex_color_to_ass(value: str) -> str:
    normalized = _normalize_hex_color(value)
    red = normalized[1:3]
    green = normalized[3:5]
    blue = normalized[5:7]
    return f"&H{blue}{green}{red}&"


def _source_color_to_ass(value: str) -> str:
    try:
        color = int(str(value or "").strip())
    except ValueError:
        return _hex_color_to_ass(_DEFAULT_UNIFORM_COLOR)
    color = max(0, min(color, 0xFFFFFF))
    red = (color >> 16) & 0xFF
    green = (color >> 8) & 0xFF
    blue = color & 0xFF
    return f"&H{blue:02X}{green:02X}{red:02X}&"


def _position_band_start(position_preset: str) -> int:
    return {
        "top": 60,
        "upper": 150,
        "mid_upper": 280,
        "bottom": 760,
    }.get(position_preset, 60)


def _parse_danmaku_xml_records(xml_text: str) -> list[_ParsedDanmaku]:
    if not xml_text.strip():
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    records: list[_ParsedDanmaku] = []
    for node in root.findall(".//d"):
        payload = str(node.attrib.get("p") or "")
        pieces = payload.split(",")
        if not pieces:
            continue
        try:
            time_offset = max(0.0, float(pieces[0]))
        except (TypeError, ValueError):
            continue
        try:
            pos = int(pieces[1]) if len(pieces) > 1 else 1
        except (TypeError, ValueError):
            pos = 1
        color = str(pieces[3]) if len(pieces) > 3 else "16777215"
        content = "".join(node.itertext()).strip()
        if not content:
            continue
        records.append(_ParsedDanmaku(time_offset=time_offset, pos=pos, color=color, content=content))
    records.sort(key=lambda item: item.time_offset)
    return records


def _parse_danmaku_xml(xml_text: str) -> list[tuple[float, str]]:
    return [(record.time_offset, record.content) for record in _parse_danmaku_xml_records(xml_text)]


def _assign_lines(records: list[tuple[float, str]], line_count: int, duration_seconds: float) -> list[_SubtitleLine]:
    available_at = [0.0] * line_count
    lines: list[_SubtitleLine] = []
    for start, content in records:
        slot = next((index for index, end in enumerate(available_at) if end <= start), None)
        if slot is None:
            continue
        end = start + duration_seconds
        available_at[slot] = end
        lines.append(
            _SubtitleLine(
                start=start,
                end=end,
                line_index=slot,
                content=content,
                color=_hex_color_to_ass(_DEFAULT_UNIFORM_COLOR),
            )
        )
    return lines


def _assign_static_lines(records: list[_ParsedDanmaku], line_count: int, duration_seconds: float) -> list[_SubtitleLine]:
    available_at = [0.0] * line_count
    lines: list[_SubtitleLine] = []
    for record in records:
        slot = next((index for index, end in enumerate(available_at) if end <= record.time_offset), None)
        if slot is None:
            continue
        end = record.time_offset + duration_seconds
        available_at[slot] = end
        lines.append(
            _SubtitleLine(
                start=record.time_offset,
                end=end,
                line_index=slot,
                content=record.content,
                color=_source_color_to_ass(record.color),
            )
        )
    return lines


def _build_cues(lines: list[_SubtitleLine], line_count: int) -> list[_SubtitleCue]:
    if not lines:
        return []
    time_points = sorted({line.start for line in lines} | {line.end for line in lines})
    cues: list[_SubtitleCue] = []
    for start, end in zip(time_points, time_points[1:], strict=False):
        active = [line for line in lines if line.start <= start < line.end]
        if not active:
            continue
        ordered: list[_SubtitleLine | None] = [None] * line_count
        for line in active:
            ordered[line.line_index] = line
        cue_lines = tuple(line for line in ordered if line is not None)
        if not cue_lines:
            continue
        if cues and cues[-1].lines == cue_lines and abs(cues[-1].end - start) < 0.001:
            previous = cues[-1]
            cues[-1] = _SubtitleCue(start=previous.start, end=end, lines=previous.lines)
            continue
        cues.append(_SubtitleCue(start=start, end=end, lines=cue_lines))
    return cues


def _assign_timed_records(records: list[_ParsedDanmaku], line_count: int, duration_seconds: float) -> list[_TimedDanmaku]:
    available_at = [0.0] * line_count
    timed: list[_TimedDanmaku] = []
    for record in records:
        slot = next((index for index, end in enumerate(available_at) if end <= record.time_offset), None)
        if slot is None:
            continue
        end = record.time_offset + duration_seconds
        available_at[slot] = end
        timed.append(_TimedDanmaku(record=record, line_index=slot, start=record.time_offset, end=end))
    return timed


def render_danmaku_srt(xml_text: str, line_count: int = 1, duration_seconds: float = 4.0) -> str:
    normalized_line_count = max(1, min(int(line_count), 5))
    normalized_duration = max(1.0, float(duration_seconds))
    records = _parse_danmaku_xml(xml_text)
    lines = _assign_lines(records, normalized_line_count, normalized_duration)
    cues = _build_cues(lines, normalized_line_count)
    if not cues:
        return ""
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        text = "\n".join(line.content for line in cue.lines if line.content)
        blocks.extend(
            [
                str(index),
                f"{_format_srt_timestamp(cue.start)} --> {_format_srt_timestamp(cue.end)}",
                text,
                "",
            ]
        )
    return "\n".join(blocks)


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _build_ass_header(primary_color: str) -> str:
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {_PLAY_RES_X}",
            f"PlayResY: {_PLAY_RES_Y}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Danmaku,sans-serif,{_DEFAULT_FONT_SIZE},{primary_color},{primary_color},&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,1,0,8,24,24,4,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )


def _line_color(color_mode: str, uniform_color: str, source_color: str) -> str:
    if color_mode == "source":
        return _source_color_to_ass(source_color)
    return _hex_color_to_ass(uniform_color)


def _render_static_text(cue: _SubtitleCue, color_mode: str, uniform_color: str) -> str:
    parts: list[str] = []
    for line in cue.lines:
        text = _escape_ass_text(line.content)
        if color_mode == "source":
            text = rf"{{\c{line.color}}}{text}"
        parts.append(text)
    return r"\N".join(parts)


def _mode_for_record(render_mode: str, pos: int) -> str:
    if render_mode == "scroll_only":
        return "scroll"
    if pos == 5:
        return "top"
    if pos == 4:
        return "bottom"
    return "scroll"


def _lane_y(position_preset: str, line_index: int, mode: str) -> int:
    band_start = _position_band_start(position_preset)
    if mode == "bottom":
        return min(_PLAY_RES_Y - 80, band_start + (line_index * _LANE_HEIGHT))
    return min(_PLAY_RES_Y - 80, band_start + (line_index * _LANE_HEIGHT))


def _event_override(mode: str, y: int, color: str) -> str:
    if mode == "scroll":
        return rf"{{\an8\move({_PLAY_RES_X + 80},{y},-400,{y})\c{color}}}"
    if mode == "bottom":
        return rf"{{\an2\pos(960,{y})\c{color}}}"
    return rf"{{\an8\pos(960,{y})\c{color}}}"


def _build_dynamic_events(
    records: list[_ParsedDanmaku],
    *,
    line_count: int,
    duration_seconds: float,
    render_mode: str,
    color_mode: str,
    uniform_color: str,
    position_preset: str,
) -> list[str]:
    grouped = {"scroll": [], "top": [], "bottom": []}
    for record in records:
        grouped[_mode_for_record(render_mode, record.pos)].append(record)
    timed_records = [
        *_assign_timed_records(grouped["scroll"], line_count, duration_seconds),
        *_assign_timed_records(grouped["top"], line_count, duration_seconds),
        *_assign_timed_records(grouped["bottom"], line_count, duration_seconds),
    ]
    timed_records.sort(key=lambda item: (item.start, item.line_index, item.record.content))
    events: list[str] = []
    for item in timed_records:
        mode = _mode_for_record(render_mode, item.record.pos)
        color = _line_color(color_mode, uniform_color, item.record.color)
        y = _lane_y(position_preset, item.line_index, mode)
        text = _escape_ass_text(item.record.content)
        override = _event_override(mode, y, color)
        events.append(
            f"Dialogue: 0,{_format_ass_timestamp(item.start)},{_format_ass_timestamp(item.end)},Danmaku,,0,0,0,,{override}{text}"
        )
    return events


def render_danmaku_ass(
    xml_text: str,
    line_count: int = 1,
    duration_seconds: float = 4.0,
    *,
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = _DEFAULT_UNIFORM_COLOR,
    position_preset: str = "top",
) -> str:
    normalized_line_count = max(1, min(int(line_count), 5))
    normalized_duration = max(1.0, float(duration_seconds))
    normalized_render_mode = _normalize_render_mode(render_mode)
    normalized_color_mode = _normalize_color_mode(color_mode)
    normalized_uniform_color = _normalize_hex_color(uniform_color)
    normalized_position_preset = _normalize_position_preset(position_preset)
    records = _parse_danmaku_xml_records(xml_text)
    if not records:
        return ""

    header = _build_ass_header(_hex_color_to_ass(normalized_uniform_color))
    if normalized_render_mode == "static":
        lines = _assign_static_lines(records, normalized_line_count, normalized_duration)
        cues = _build_cues(lines, normalized_line_count)
        events = [
            f"Dialogue: 0,{_format_ass_timestamp(cue.start)},{_format_ass_timestamp(cue.end)},Danmaku,,0,0,0,,{_render_static_text(cue, normalized_color_mode, normalized_uniform_color)}"
            for cue in cues
        ]
        return "\n".join([header, *events, ""])

    events = _build_dynamic_events(
        records,
        line_count=normalized_line_count,
        duration_seconds=normalized_duration,
        render_mode=normalized_render_mode,
        color_mode=normalized_color_mode,
        uniform_color=normalized_uniform_color,
        position_preset=normalized_position_preset,
    )
    return "\n".join([header, *events, ""])
