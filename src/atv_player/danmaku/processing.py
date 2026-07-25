from __future__ import annotations

import re
from dataclasses import replace
from typing import Sequence

from atv_player.danmaku.models import DanmakuRecord

__all__ = [
    "filter_blocked_words",
    "group_by_time_window",
    "convert_top_bottom_to_scroll",
    "apply_time_offset",
    "parse_offset_rules",
    "resolve_offset_seconds",
    "OffsetRule",
]


def filter_blocked_words(
    records: Sequence[DanmakuRecord], patterns: Sequence[re.Pattern]
) -> list[DanmakuRecord]:
    """Drop records whose content matches any blocked regex."""
    if not patterns:
        return list(records)
    return [record for record in records if not any(p.search(record.content) for p in patterns)]


def group_by_time_window(records: Sequence[DanmakuRecord], minutes: int) -> list[DanmakuRecord]:
    """Dedupe identical content within each N-minute window.

    Single-source model: within a window, keep only the earliest occurrence of each
    distinct content. ``minutes=0`` disables dedup (return all, stable order).
    """
    if minutes <= 0:
        return list(records)
    window = max(1, int(minutes)) * 60
    seen: set[tuple[int, str]] = set()
    output: list[DanmakuRecord] = []
    for record in sorted(records, key=lambda r: r.time_offset):
        key = (int(record.time_offset // window), record.content)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def convert_top_bottom_to_scroll(records: Sequence[DanmakuRecord]) -> list[DanmakuRecord]:
    """Convert top (5) / bottom (4) danmaku to scroll (1)."""
    output: list[DanmakuRecord] = []
    for record in records:
        if record.pos in (4, 5):
            output.append(replace(record, pos=1))
        else:
            output.append(record)
    return output


def apply_time_offset(
    records: Sequence[DanmakuRecord],
    offset_seconds: float,
    *,
    use_percent: bool = False,
    video_duration_seconds: float = 0.0,
) -> list[DanmakuRecord]:
    """Shift (or scale, in percent mode) each record's time_offset.

    Percent mode scales by ``(duration + offset) / duration`` — used when two sources
    have different total lengths and danmaku must stretch accordingly. Times clamp at 0.
    """
    offset = float(offset_seconds)
    if offset == 0:
        return list(records)
    scale_ratio: float | None = None
    if use_percent:
        duration = float(video_duration_seconds)
        if duration <= 0:
            return list(records)
        scale_ratio = (duration + offset) / duration
        if not (scale_ratio > 0 and scale_ratio != 1 and scale_ratio == scale_ratio):
            scale_ratio = None
    output: list[DanmakuRecord] = []
    for record in records:
        if scale_ratio is not None:
            new_t = round(max(0.0, record.time_offset * scale_ratio), 2)
        else:
            new_t = max(0.0, record.time_offset + offset)
        output.append(replace(record, time_offset=new_t))
    return output


# ---------------- offset rules (DANMU_OFFSET: "剧名:秒" / "剧名/季/集@来源:秒") ----------------


class OffsetRule:
    __slots__ = ("anime", "season", "episode", "sources", "all_sources", "offset", "use_percent")

    def __init__(self, anime, season, episode, sources, all_sources, offset, use_percent):
        self.anime = anime
        self.season = season
        self.episode = episode
        self.sources = sources
        self.all_sources = all_sources
        self.offset = offset
        self.use_percent = use_percent


_SOURCE_ALIASES = {"tencent": "qq", "iqiyi": "qiyi", "bilibili": "bilibili1"}


def _normalize_segment(segment: str) -> str | None:
    m = re.fullmatch(r"[Ss](\d+)", segment)
    if m:
        return f"S{int(m.group(1)):02d}"
    m = re.fullmatch(r"[Ee](\d+)", segment)
    if m:
        return f"E{int(m.group(1)):02d}"
    return None


def parse_offset_rules(env: str) -> list[OffsetRule]:
    """Parse a DANMU_OFFSET-style string into rules.

    Format: ``剧名:秒`` / ``剧名/S01/E03:秒`` / ``剧名@来源:秒`` / ``剧名%:秒`` (percent).
    Entries separated by ``,``, e.g. ``百花杀:-5, 季番/S02@tencent:1.5``.
    """
    if not env or not isinstance(env, str):
        return []
    rules: list[OffsetRule] = []
    for entry in env.split(","):
        trimmed = entry.strip()
        if not trimmed:
            continue
        colon = trimmed.rfind(":")
        if colon == -1:
            continue
        raw_path = trimmed[:colon].strip()
        offset_str = trimmed[colon + 1 :].strip()
        if not raw_path or offset_str == "":
            continue
        try:
            offset = float(offset_str)
        except ValueError:
            continue

        use_percent = False
        if raw_path.endswith("%"):
            use_percent = True
            raw_path = raw_path[:-1].strip()

        at = raw_path.rfind("@")
        sources = None
        all_sources = False
        if at != -1:
            path_part = raw_path[:at].strip()
            source_part = raw_path[at + 1 :].strip().lower()
            if source_part in ("all", "*"):
                all_sources = True
            else:
                sources = [s.strip() for s in re.split(r"[&＆]", source_part) if s.strip()]
                if not sources:
                    continue
        else:
            path_part = raw_path

        m = re.fullmatch(r"(.*?)/([Ss]\d+)(?:/([Ee]\d+))?", path_part)
        if m:
            anime = m.group(1).strip()
            season = _normalize_segment(m.group(2))
            episode = _normalize_segment(m.group(3)) if m.group(3) else None
        else:
            anime = path_part.strip()
            season = None
            episode = None
        if not anime:
            continue
        rules.append(OffsetRule(anime, season, episode, sources, all_sources, offset, use_percent))
    return rules


def resolve_offset_seconds(
    rules: Sequence[OffsetRule],
    *,
    anime: str,
    season: str | None = None,
    episode: str | None = None,
    source: str = "",
) -> float:
    """Resolve the offset seconds for the given context, or 0 if no rule matches.

    Specificity: episode-level > season-level > anime-level; within a level,
    source-specific > all-sources > generic. Source aliases (tencent<->qq) are expanded.
    """
    if not rules or not anime:
        return 0.0
    source_keys: set[str] = set()
    if source:
        for s in re.split(r"[&＆]", source):
            key = s.strip().lower()
            if key:
                source_keys.add(key)
                if key in _SOURCE_ALIASES:
                    source_keys.add(_SOURCE_ALIASES[key])

    def norm(s: str) -> str:
        return re.sub(r"\s+", "", s)

    target_anime = norm(anime)
    levels = [(True, True), (True, False), (False, False)]  # episode, season, anime
    for match_season, match_episode in levels:
        specific = all_match = generic = None
        for rule in rules:
            if norm(rule.anime) != target_anime:
                continue
            if match_episode:
                if not (rule.season and rule.episode and rule.season == season and rule.episode == episode):
                    continue
            elif match_season:
                if not (rule.season and not rule.episode and rule.season == season):
                    continue
            else:
                if rule.season or rule.episode:
                    continue
            if rule.sources:
                if source_keys and any(s in source_keys for s in rule.sources):
                    specific = rule
            elif rule.all_sources:
                all_match = rule
            else:
                generic = rule
        chosen = specific or all_match or generic
        if chosen is not None:
            return chosen.offset
    return 0.0
