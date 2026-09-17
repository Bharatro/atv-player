from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Sequence

from atv_player.danmaku.models import DanmakuRecord

__all__ = [
    "build_blocked_matchers",
    "clean_records",
    "group_by_time_window",
    "convert_top_bottom_to_scroll",
    "apply_time_offset",
]

_logger = logging.getLogger(__name__)

# /pattern/flags 形式的词条按正则处理；JS 侧的 g/y 等标志对匹配无意义，忽略
_BLOCKED_WORD_ENTRY = re.compile(r"^/(.+)/([A-Za-z]*)$", re.DOTALL)
_REGEX_FLAG_MAP = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
    "a": re.ASCII,
    "L": re.LOCALE,
}


def build_blocked_matchers(blocked_words: Sequence[str]) -> list[tuple[str, re.Pattern[str] | str]]:
    """词条转为匹配器：正则词条 → ("regex", 编译后的 Pattern)，其余 → ("text", casefold 后的字面量)。

    非法正则降级为字面量匹配并告警，不整条丢弃。
    """
    matchers: list[tuple[str, re.Pattern[str] | str]] = []
    for raw in blocked_words:
        word = str(raw or "").strip()
        if not word:
            continue
        entry = _BLOCKED_WORD_ENTRY.match(word)
        if entry is not None:
            flags = 0
            for flag_char in entry.group(2):
                flags |= _REGEX_FLAG_MAP.get(flag_char, 0)
            try:
                matchers.append(("regex", re.compile(entry.group(1), flags)))
                continue
            except re.error:
                _logger.warning("无效的屏蔽词正则，已按字面量处理: %s", word)
        matchers.append(("text", word.casefold()))
    return matchers


def _content_blocked(content: str, matchers: Sequence[tuple[str, re.Pattern[str] | str]]) -> bool:
    for kind, matcher in matchers:
        if kind == "regex":
            if matcher.search(content) is not None:
                return True
        elif matcher in content.casefold():
            return True
    return False


def clean_records(
    records: Sequence[DanmakuRecord],
    *,
    blocked_words: Sequence[str],
    duplicate_window_minutes: int,
    convert_top_bottom: bool,
) -> list[DanmakuRecord]:
    matchers = build_blocked_matchers(blocked_words)
    output = [record for record in records if not _content_blocked(record.content, matchers)]
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
