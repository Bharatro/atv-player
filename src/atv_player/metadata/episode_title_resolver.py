from __future__ import annotations

from dataclasses import replace
import re

from atv_player.danmaku.utils import infer_playlist_episode_number
from atv_player.episode_titles import extract_season_number, playlist_has_title_variants, seed_original_titles
from atv_player.episode_titles import apply_episode_title_index_map
from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.query import normalize_metadata_title
from atv_player.metadata.providers.tmdb import infer_tmdb_media_type
from atv_player.models import PlayItem, VodItem

METADATA_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "bangumi", "bilibili", "tmdb", "tencent", "iqiyi"]
_IQIYI_PRIORITIZED_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "bangumi", "bilibili", "iqiyi", "tmdb", "tencent"]
_MOVIE_MARKERS = ("电影", "影片", "movie")
_EPISODE_SORT_SENTINEL = 10**9


def is_high_confidence_iqiyi_episode_candidate(
    vod: VodItem,
    playlist: list[PlayItem],
    candidate,
    *,
    preferred_provider: str = "",
) -> bool:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    if provider != "iqiyi":
        return False
    native_iqiyi_site = _is_native_iqiyi_site_candidate(candidate)
    if (
        str(preferred_provider or "").strip() != "iqiyi"
        and not native_iqiyi_site
        and not _iqiyi_titles_match_vod(vod, candidate)
    ):
        return False
    return (
        build_provider_episode_playlist(
            vod,
            playlist,
            candidate,
            source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
        )
        is not None
    )


def resolve_episode_title_source_priority(
    vod: VodItem,
    playlist: list[PlayItem],
    candidates: list[object],
    *,
    preferred_provider: str = "",
) -> list[str]:
    for candidate in candidates:
        if is_high_confidence_iqiyi_episode_candidate(
            vod,
            playlist,
            candidate,
            preferred_provider=preferred_provider,
        ):
            return list(_IQIYI_PRIORITIZED_EPISODE_TITLE_SOURCE_PRIORITY)
    return list(METADATA_EPISODE_TITLE_SOURCE_PRIORITY)


def build_provider_episode_playlist(
    vod: VodItem,
    playlist: list[PlayItem],
    candidate,
    *,
    source_priority: list[str],
) -> list[PlayItem] | None:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    raw = dict(getattr(candidate, "raw", {}) or {})
    if not _candidate_supports_episode_title_rewrite(vod, provider, provider_id, raw):
        return None
    copied = seed_original_titles([replace(item) for item in playlist])
    titles_by_index = _titles_by_index_for_provider(vod, copied, provider, raw)
    if not titles_by_index:
        return None
    apply_episode_title_index_map(copied, titles_by_index, source=provider, source_priority=source_priority)
    if not playlist_has_title_variants(copied):
        return None
    return _sort_episode_title_playlist(vod, copied)


def _candidate_supports_episode_title_rewrite(
    vod: VodItem,
    provider: str,
    provider_id: str,
    raw: dict[str, object],
) -> bool:
    vod_media_type = infer_tmdb_media_type(
        MetadataQuery(
            title=str(vod.vod_name or "").strip(),
            year=str(vod.vod_year or "").strip(),
            type_name=str(vod.type_name or "").strip(),
            category_name=str(vod.category_name or "").strip(),
        )
    )
    if vod_media_type == "movie":
        return False
    if provider == "tmdb" and not provider_id.startswith("tv:"):
        return False
    if provider == "bilibili" and not _is_confirmed_bilibili_anime_candidate(raw):
        return False
    return not _raw_indicates_movie_category(raw)


def _is_confirmed_bilibili_anime_candidate(raw: dict[str, object]) -> bool:
    season_id = str(raw.get("season_id") or "").strip()
    episodes = raw.get("episodes")
    return bool(season_id and isinstance(episodes, list) and episodes)


def _raw_indicates_movie_category(raw: dict[str, object]) -> bool:
    return any(marker in token for token in _iter_category_tokens(raw) for marker in _MOVIE_MARKERS)


def _iter_category_tokens(raw: dict[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("typeName", "channel", "genres", "categories", "baseTags", "category"):
        values.extend(_category_tokens(raw.get(key)))
    return values


def _category_tokens(value: object) -> list[str]:
    if isinstance(value, dict):
        return _category_tokens(value.get("value"))
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_category_tokens(item))
        return tokens
    text = str(value or "").strip().lower()
    if not text:
        return []
    return [token for token in re.split(r"[,/|、]", text) if token.strip()]


def _titles_by_index_for_provider(
    vod: VodItem,
    playlist: list[PlayItem],
    provider: str,
    raw: dict[str, object],
) -> dict[int, str]:
    if provider == "bangumi":
        return _titles_by_index_for_bangumi(vod, playlist, raw)
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
            episode_number = int(video.get("itemNumber") or video.get("episodeNumber") or video.get("number") or 0)
        except (TypeError, ValueError):
            continue
        episode_title = str(video.get("itemTitle") or video.get("subtitle") or video.get("title") or "").strip()
        if episode_number > 0 and episode_title:
            titles_by_episode[episode_number] = episode_title
    if not titles_by_episode:
        return {}
    return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)


def _titles_by_index_for_bangumi(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for episode in raw.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        try:
            episode_type = int(episode.get("type") or 0)
            episode_number = int(episode.get("sort") or episode.get("ep") or 0)
        except (TypeError, ValueError):
            continue
        episode_title = str(episode.get("name_cn") or episode.get("name") or "").strip()
        if episode_type != 0 or episode_number <= 0 or not episode_title:
            continue
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
    normalized_episodes = raw.get("episodes")
    if isinstance(normalized_episodes, list):
        for episode in normalized_episodes:
            if not isinstance(episode, dict):
                continue
            if str(episode.get("episode_type") or "main").strip() != "main":
                continue
            try:
                episode_number = int(episode.get("episode_number") or episode.get("sort") or 0)
            except (TypeError, ValueError):
                continue
            episode_title = str(episode.get("long_title") or episode.get("title") or "").strip()
            if episode_number > 0 and episode_title:
                titles_by_episode[episode_number] = episode_title
    if titles_by_episode:
        return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)
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


def _season_episode_pairs(vod: VodItem, playlist: list[PlayItem]) -> list[tuple[int, int] | None]:
    season_numbers = _resolved_season_numbers(vod, playlist)
    pairs: list[tuple[int, int] | None] = []
    for index, item in enumerate(playlist):
        episode_number = infer_playlist_episode_number(item, playlist)
        if episode_number is None or episode_number <= 0:
            pairs.append(None)
            continue
        pairs.append((season_numbers[index], episode_number))
    return pairs


def _sort_episode_title_playlist(vod: VodItem, playlist: list[PlayItem]) -> list[PlayItem]:
    if len(playlist) <= 1:
        for index, item in enumerate(playlist):
            item.index = index
        return playlist
    season_episode_pairs = _season_episode_pairs(vod, playlist)
    resolved_pairs = [pair for pair in season_episode_pairs if pair is not None]
    has_multi_version_pairs = len(resolved_pairs) != len(set(resolved_pairs))
    indexed_playlist = list(enumerate(playlist))
    if has_multi_version_pairs:
        occurrence_by_pair: dict[tuple[int, int], int] = {}
        version_slot_by_index: dict[int, int] = {}
        for index, pair in enumerate(season_episode_pairs):
            if pair is None:
                version_slot_by_index[index] = _EPISODE_SORT_SENTINEL
                continue
            version_slot_by_index[index] = occurrence_by_pair.get(pair, 0)
            occurrence_by_pair[pair] = version_slot_by_index[index] + 1
        indexed_playlist.sort(
            key=lambda entry: (
                version_slot_by_index[entry[0]],
                season_episode_pairs[entry[0]] or (_EPISODE_SORT_SENTINEL, _EPISODE_SORT_SENTINEL),
                entry[0],
            )
        )
    else:
        indexed_playlist.sort(
            key=lambda entry: (
                season_episode_pairs[entry[0]] or (_EPISODE_SORT_SENTINEL, _EPISODE_SORT_SENTINEL),
                entry[0],
            )
        )
    sorted_playlist = [item for _original_index, item in indexed_playlist]
    for index, item in enumerate(sorted_playlist):
        item.index = index
    return sorted_playlist


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


def _iqiyi_titles_match_vod(vod: VodItem, candidate) -> bool:
    vod_title = normalize_metadata_title(str(vod.vod_name or "").strip())
    candidate_title = normalize_metadata_title(str(getattr(candidate, "title", "") or "").strip())
    if not vod_title or not candidate_title or vod_title != candidate_title:
        return False
    vod_year = str(vod.vod_year or "").strip()
    candidate_year = str(getattr(candidate, "year", "") or "").strip()
    if vod_year and candidate_year and vod_year != candidate_year:
        return False
    candidate_season = extract_season_number(getattr(candidate, "title", ""))
    if candidate_season is not None and candidate_season != _guess_default_season(vod):
        return False
    return True


def _is_native_iqiyi_site_candidate(candidate) -> bool:
    raw = dict(getattr(candidate, "raw", {}) or {})
    site_name = str(raw.get("siteName") or "").strip()
    site_id = str(raw.get("siteId") or "").strip().lower()
    return site_name == "爱奇艺" or site_id == "iqiyi"


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
