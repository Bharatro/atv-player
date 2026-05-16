from __future__ import annotations

from dataclasses import replace

from atv_player.danmaku.utils import infer_playlist_episode_number
from atv_player.episode_titles import extract_season_number, playlist_has_title_variants, seed_original_titles
from atv_player.episode_titles import apply_episode_title_index_map
from atv_player.models import PlayItem, VodItem

METADATA_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "bilibili", "tmdb", "tencent", "iqiyi"]


def build_provider_episode_playlist(
    vod: VodItem,
    playlist: list[PlayItem],
    candidate,
    *,
    source_priority: list[str],
) -> list[PlayItem] | None:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    raw = dict(getattr(candidate, "raw", {}) or {})
    copied = seed_original_titles([replace(item) for item in playlist])
    titles_by_index = _titles_by_index_for_provider(vod, copied, provider, raw)
    if not titles_by_index:
        return None
    apply_episode_title_index_map(copied, titles_by_index, source=provider, source_priority=source_priority)
    return copied if playlist_has_title_variants(copied) else None


def _titles_by_index_for_provider(
    vod: VodItem,
    playlist: list[PlayItem],
    provider: str,
    raw: dict[str, object],
) -> dict[int, str]:
    if provider == "tencent":
        return _titles_by_index_for_tencent(vod, playlist, raw)
    if provider == "iqiyi":
        return _titles_by_index_for_iqiyi(vod, playlist, raw)
    if provider == "bilibili":
        return _titles_by_index_for_bilibili(vod, playlist, raw)
    if provider == "tmdb":
        return _titles_by_index_for_tmdb(vod, playlist, raw)
    return {}


def _titles_by_index_for_tencent(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    episode_rows: list[str] = []
    for site_key in ("episode_sites", "play_sites"):
        for site in raw.get(site_key) or []:
            if not isinstance(site, dict):
                continue
            for episode in site.get("episodeInfoList") or []:
                if not isinstance(episode, dict):
                    continue
                title = str(episode.get("title") or "").strip()
                if title:
                    episode_rows.append(title)
    if not episode_rows:
        return {}
    return _map_sequential_episode_rows(vod, playlist, episode_rows)


def _titles_by_index_for_iqiyi(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for video in raw.get("videos") or []:
        if not isinstance(video, dict):
            continue
        try:
            episode_number = int(video.get("itemNumber") or video.get("episodeNumber") or 0)
        except (TypeError, ValueError):
            continue
        episode_title = str(video.get("itemTitle") or video.get("title") or "").strip()
        if episode_number > 0 and episode_title:
            titles_by_episode[episode_number] = episode_title
    if not titles_by_episode:
        return {}
    return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)


def _titles_by_index_for_tmdb(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for episode in raw.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        try:
            episode_number = int(episode.get("episode_number") or episode.get("episodeNumber") or 0)
        except (TypeError, ValueError):
            continue
        episode_title = str(episode.get("name") or episode.get("title") or "").strip()
        if episode_number > 0 and episode_title:
            titles_by_episode[episode_number] = episode_title
    if not titles_by_episode:
        return {}
    return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)


def _titles_by_index_for_bilibili(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for episode in raw.get("eps") or []:
        if not isinstance(episode, dict):
            continue
        episode_number = _bilibili_episode_number(episode)
        episode_title = _bilibili_episode_title(episode)
        if episode_number is None or episode_number <= 0 or not episode_title:
            continue
        titles_by_episode[episode_number] = episode_title
    if not titles_by_episode:
        return {}
    return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)


def _map_sequential_episode_rows(vod: VodItem, playlist: list[PlayItem], episode_rows: list[str]) -> dict[int, str]:
    titles_by_index: dict[int, str] = {}
    season_numbers = _resolved_season_numbers(vod, playlist)
    include_season_prefix = len(set(season_numbers.values())) > 1
    for index, item in enumerate(playlist):
        episode_number = infer_playlist_episode_number(item, playlist)
        if episode_number is None or episode_number <= 0 or episode_number > len(episode_rows):
            continue
        season_number = season_numbers[index]
        titles_by_index[index] = _format_episode_title(
            season_number,
            episode_number,
            episode_rows[episode_number - 1],
            include_season_prefix=include_season_prefix,
        )
    return titles_by_index


def _map_episode_numbers_to_indices(
    vod: VodItem,
    playlist: list[PlayItem],
    titles_by_episode: dict[int, str],
) -> dict[int, str]:
    titles_by_index: dict[int, str] = {}
    season_numbers = _resolved_season_numbers(vod, playlist)
    include_season_prefix = len(set(season_numbers.values())) > 1
    for index, item in enumerate(playlist):
        episode_number = infer_playlist_episode_number(item, playlist)
        if episode_number is None or episode_number <= 0:
            continue
        episode_title = titles_by_episode.get(episode_number)
        if not episode_title:
            continue
        season_number = season_numbers[index]
        titles_by_index[index] = _format_episode_title(
            season_number,
            episode_number,
            episode_title,
            include_season_prefix=include_season_prefix,
        )
    return titles_by_index


def _resolved_season_numbers(vod: VodItem, playlist: list[PlayItem]) -> dict[int, int]:
    default_season = _guess_default_season(vod)
    resolved: dict[int, int] = {}
    for index, item in enumerate(playlist):
        season_number = None
        for value in (item.original_title, item.title, item.path):
            season_number = extract_season_number(value)
            if season_number is not None:
                break
        resolved[index] = season_number or default_season
    return resolved


def _guess_default_season(vod: VodItem) -> int:
    for value in (vod.vod_name, vod.vod_remarks, vod.category_name):
        season_number = extract_season_number(value)
        if season_number is not None:
            return season_number
    return 1


def _bilibili_episode_number(episode: dict[str, object]) -> int | None:
    for key in ("title", "index_title"):
        try:
            value = int(str(episode.get(key) or "").strip())
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _bilibili_episode_title(episode: dict[str, object]) -> str:
    for key in ("long_title", "share_copy", "show_title", "index_title", "title"):
        value = str(episode.get(key) or "").strip()
        if value:
            return value
    return ""


def _format_episode_title(
    season_number: int,
    episode_number: int,
    episode_title: str,
    *,
    include_season_prefix: bool,
) -> str:
    prefix = f"第{season_number}季 " if include_season_prefix else ""
    return f"{prefix}第{episode_number}集 {episode_title}".strip()
