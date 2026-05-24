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
_SEASON_PATTERNS = (
    r"\bS(?:eason)?\s*0*(\d{1,2})\s*(?:E\d+)?\b",
    r"第\s*0*(\d{1,2})\s*季",
    r"(?:^|[\\/])S0*(\d{1,2})(?:[\\/]|$)",
)
_EPISODE_RELEASE_VERSION_RE = re.compile(
    r"(?:^|[\s._\-\[(（])v\s*(\d+(?:\.\d+)*)"
    r"(?=$|[\s._\-\])）]|版(?:本)?)",
    re.IGNORECASE,
)
_DEFAULT_EPISODE_RELEASE_VERSION = (1, 0, 0, 0)


def normalize_episode_title_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _path_basename(value: str) -> str:
    text = str(value or "").strip().rstrip("/\\")
    if not text:
        return ""
    return re.split(r"[\\/]", text)[-1]


def _parse_episode_release_version(value: str) -> tuple[int, int, int, int] | None:
    match = _EPISODE_RELEASE_VERSION_RE.search(str(value or ""))
    if match is None:
        return None
    parts: list[int] = []
    for part in match.group(1).split("."):
        try:
            number = int(part)
        except ValueError:
            return None
        if number < 0:
            return None
        parts.append(number)
    padded = (parts + [0, 0, 0, 0])[:4]
    return (padded[0], padded[1], padded[2], padded[3])


def episode_release_version(item: PlayItem) -> tuple[int, int, int, int]:
    versions: list[tuple[int, int, int, int]] = []
    seen: set[str] = set()
    for value in (item.original_title, item.title, item.path):
        candidate = _path_basename(str(value or ""))
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        version = _parse_episode_release_version(candidate)
        if version is not None:
            versions.append(version)
    return max(versions) if versions else _DEFAULT_EPISODE_RELEASE_VERSION


def episode_version_slots_by_index(
    playlist: list[PlayItem],
    season_episode_pairs: list[tuple[int, int] | None],
    *,
    sentinel: int,
) -> dict[int, int]:
    versions_by_index = [episode_release_version(item) for item in playlist]
    versions_by_pair: dict[tuple[int, int], set[tuple[int, int, int, int]]] = {}
    for index, pair in enumerate(season_episode_pairs):
        if pair is None:
            continue
        versions_by_pair.setdefault(pair, set()).add(versions_by_index[index])

    version_slot_by_pair: dict[
        tuple[int, int],
        dict[tuple[int, int, int, int], int],
    ] = {}
    for pair, versions in versions_by_pair.items():
        if len(versions) <= 1:
            continue
        version_slot_by_pair[pair] = {
            version: slot
            for slot, version in enumerate(sorted(versions, reverse=True))
        }

    occurrence_by_pair: dict[tuple[int, int], int] = {}
    version_slot_by_index: dict[int, int] = {}
    for index, pair in enumerate(season_episode_pairs):
        if pair is None:
            version_slot_by_index[index] = sentinel
            continue
        slots_by_version = version_slot_by_pair.get(pair)
        if slots_by_version is not None:
            version_slot_by_index[index] = slots_by_version.get(
                versions_by_index[index],
                sentinel,
            )
            continue
        version_slot_by_index[index] = occurrence_by_pair.get(pair, 0)
        occurrence_by_pair[pair] = version_slot_by_index[index] + 1
    return version_slot_by_index


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


def _iter_season_numbers(value: str) -> list[int]:
    seasons: list[int] = []
    text = str(value or "")
    for pattern in _SEASON_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                season_number = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if season_number > 0:
                seasons.append(season_number)
    for match in re.finditer(r"第\s*([零一二两三四五六七八九十百千]+)\s*季", text, re.IGNORECASE):
        season_number = _parse_chinese_number(match.group(1))
        if season_number is not None:
            seasons.append(season_number)
    return seasons


def _single_unambiguous_season(value: str) -> int | None:
    unique: list[int] = []
    for season_number in _iter_season_numbers(value):
        if season_number not in unique:
            unique.append(season_number)
    return unique[0] if len(unique) == 1 else None


def extract_season_number(value: object) -> int | None:
    text = str(value or "")
    if not text.strip():
        return None
    segments = [segment for segment in re.split(r"[\\/]", text) if segment.strip()]
    for segment in reversed(segments):
        season_number = _single_unambiguous_season(segment)
        if season_number is not None:
            return season_number
    return _single_unambiguous_season(text)


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
