from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from atv_player.danmaku.models import DanmakuRecord

__all__ = [
    "clean_records",
    "group_by_time_window",
    "convert_top_bottom_to_scroll",
    "apply_time_offset",
]


def clean_records(
    records: Sequence[DanmakuRecord],
    *,
    blocked_words: Sequence[str],
    duplicate_window_minutes: int,
    convert_top_bottom: bool,
) -> list[DanmakuRecord]:
    blocked = tuple(word.strip().casefold() for word in blocked_words if word.strip())
    output = [
        record
        for record in records
        if not any(word in record.content.casefold() for word in blocked)
    ]
    output = group_by_time_window(output, duplicate_window_minutes)
    return convert_top_bottom_to_scroll(output) if convert_top_bottom else output


def group_by_time_window(records: Sequence[DanmakuRecord], minutes: int) -> list[DanmakuRecord]:
    """Keep the earliest instance of identical content in each time window."""
    if minutes <= 0:
        return list(records)
    window = max(1, int(minutes)) * 60
    seen: set[tuple[int, str]] = set()
    output: list[DanmakuRecord] = []
    for record in sorted(records, key=lambda item: item.time_offset):
        key = (int(record.time_offset // window), record.content)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def convert_top_bottom_to_scroll(records: Sequence[DanmakuRecord]) -> list[DanmakuRecord]:
    output: list[DanmakuRecord] = []
    for record in records:
        output.append(replace(record, pos=1) if record.pos in (4, 5) else record)
    return output


def apply_time_offset(
    records: Sequence[DanmakuRecord],
    offset_seconds: float,
) -> list[DanmakuRecord]:
    offset = float(offset_seconds)
    if offset == 0:
        return list(records)
    return [
        replace(record, time_offset=max(0.0, record.time_offset + offset))
        for record in records
    ]
