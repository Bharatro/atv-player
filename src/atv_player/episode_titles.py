from __future__ import annotations

import re

from atv_player.models import PlayItem

_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNIT_VALUES = {
    "十": 10,
    "百": 100,
    "千": 1000,
}


def normalize_episode_title_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _parse_chinese_number(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    total = 0
    current = 0
    saw_value = False
    for char in text:
        if char in _CHINESE_DIGIT_VALUES:
            current = _CHINESE_DIGIT_VALUES[char]
            saw_value = True
            continue
        if char in _CHINESE_UNIT_VALUES:
            saw_value = True
            if current == 0:
                current = 1
            total += current * _CHINESE_UNIT_VALUES[char]
            current = 0
            continue
        return None
    total += current
    if not saw_value or total <= 0:
        return None
    return total


def extract_season_number(value: object) -> int | None:
    text = str(value or "")
    for pattern in (
        r"\bS(?:eason)?\s*0*(\d{1,2})\s*(?:E\d+)?\b",
        r"第\s*0*(\d{1,2})\s*季",
        r"(?:^|[\\/])S0*(\d{1,2})(?:[\\/]|$)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        try:
            season_number = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if season_number > 0:
            return season_number
    match = re.search(r"第\s*([零一二两三四五六七八九十百千]+)\s*季", text, re.IGNORECASE)
    if match is None:
        return None
    return _parse_chinese_number(match.group(1))


def seed_original_titles(playlist: list[PlayItem]) -> list[PlayItem]:
    for item in playlist:
        if not item.original_title.strip():
            item.original_title = item.title.strip()
    return playlist


def _source_rank(source: str, source_priority: list[str]) -> int:
    return source_priority.index(source) if source in source_priority else len(source_priority) + 100


def apply_episode_title_map(
    playlist: list[PlayItem],
    titles_by_episode: dict[int, str],
    *,
    source: str,
    source_priority: list[str],
) -> list[PlayItem]:
    seed_original_titles(playlist)
    for index, item in enumerate(playlist, start=1):
        candidate = str(titles_by_episode.get(index) or "").strip()
        if not candidate:
            continue
        if normalize_episode_title_text(candidate) == normalize_episode_title_text(item.original_title):
            continue
        if item.episode_display_title and _source_rank(source, source_priority) > _source_rank(
            item.episode_title_source,
            source_priority,
        ):
            continue
        item.episode_display_title = candidate
        item.episode_title_source = source
    return playlist


def apply_episode_title_index_map(
    playlist: list[PlayItem],
    titles_by_index: dict[int, str],
    *,
    source: str,
    source_priority: list[str],
) -> list[PlayItem]:
    seed_original_titles(playlist)
    for index, item in enumerate(playlist):
        candidate = str(titles_by_index.get(index) or "").strip()
        if not candidate:
            continue
        if normalize_episode_title_text(candidate) == normalize_episode_title_text(item.original_title):
            continue
        if item.episode_display_title and _source_rank(source, source_priority) > _source_rank(
            item.episode_title_source,
            source_priority,
        ):
            continue
        item.episode_display_title = candidate
        item.episode_title_source = source
    return playlist


def playlist_has_title_variants(playlist: list[PlayItem]) -> bool:
    return any(
        item.original_title.strip()
        and item.episode_display_title.strip()
        and normalize_episode_title_text(item.original_title) != normalize_episode_title_text(item.episode_display_title)
        for item in playlist
    )


def playlist_item_display_title(item: PlayItem, mode: str) -> str:
    if mode == "original":
        return item.original_title.strip() or item.title.strip()
    return item.episode_display_title.strip() or item.title.strip() or item.original_title.strip()
