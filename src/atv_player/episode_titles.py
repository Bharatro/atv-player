from __future__ import annotations

import re

from atv_player.models import PlayItem


def normalize_episode_title_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


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
