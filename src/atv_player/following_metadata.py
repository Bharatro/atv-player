# ruff: noqa: E501
from __future__ import annotations

import re
import time
import logging
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlparse

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingMetadataBundle,
    FollowingMetadataSourceSnapshot,
    FollowingPlaybackPlatformEntry,
    FollowingRatingEntry,
    FollowingRecord,
    FollowingSeason,
    provider_priority_for_media_kind,
)
from atv_player.metadata.models import MetadataQuery, MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate
from atv_player.models import VodItem
from atv_player.time_utils import beijing_timezone

BEIJING_TZ = beijing_timezone()
logger = logging.getLogger(__name__)
_FIELD_PROVIDER_PRIORITY = {
    "poster": ["tmdb", "bangumi", "official_douban", "local_douban", "douban", "plugin", "iqiyi", "sohu"],
    "backdrop": ["tmdb", "bangumi", "official_douban", "local_douban", "douban", "plugin", "iqiyi", "sohu"],
    "rating": ["tmdb", "official_douban", "bangumi", "local_douban", "douban", "plugin", "iqiyi"],
}
_FOLLOWING_SOURCE_THRESHOLDS = {
    "bangumi": 0.75,
    "douban": 0.75,
    "bilibili": 0.80,
    "iqiyi": 0.80,
    "tencent": 0.80,
    "youku": 0.80,
    "mgtv": 0.80,
    "sohu": 0.80,
}
_FOLLOWING_SOURCE_PROVIDER_FILTERS = {
    "douban": ("official_douban", "local_douban", "douban"),
}
_THIRD_PARTY_SOURCE_PROVIDERS = ("douban",)
_TMDB_ANIMATION_TOKENS = ("动画", "动漫", "anime", "animation")
_PLAYBACK_SOURCE_PROVIDERS = ("bilibili", "iqiyi", "tencent", "youku", "mgtv", "sohu")
_PLAYBACK_SOURCE_PROVIDER_DOMAINS = {
    "bilibili": ("bilibili.com",),
    "iqiyi": ("iqiyi.com",),
    "tencent": ("v.qq.com", "m.v.qq.com"),
    "youku": ("youku.com",),
    "mgtv": ("mgtv.com",),
    "sohu": ("sohu.com",),
}
_PLAYBACK_SOURCE_LABEL_KEYS = {
    "b站": "bilibili",
    "bilibili": "bilibili",
    "哔哩哔哩": "bilibili",
    "爱奇艺": "iqiyi",
    "iqiyi": "iqiyi",
    "腾讯": "tencent",
    "腾讯视频": "tencent",
    "tencent": "tencent",
    "tencentvideo": "tencent",
    "优酷": "youku",
    "youku": "youku",
    "芒果": "mgtv",
    "芒果tv": "mgtv",
    "mgtv": "mgtv",
    "搜狐": "sohu",
    "搜狐视频": "sohu",
    "sohutv": "sohu",
}


def following_provider_priority(media_kind: str) -> list[str]:
    return provider_priority_for_media_kind(media_kind)


def _provider_external_id(provider: str, provider_id: str) -> tuple[str, str]:
    if provider == "bangumi" and provider_id.startswith("subject:"):
        return "bangumi", provider_id.split(":", 1)[1]
    if provider == "tmdb":
        match = re.match(r"^(?:tv|movie):([^:]+)", provider_id)
        return ("tmdb", match.group(1)) if match else ("tmdb", provider_id)
    return provider, provider_id


def following_candidate_from_url(url: str, *, available_providers: set[str] | None = None) -> MetadataScrapeCandidate | None:
    text = str(url or "").strip()
    if not text:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    available = available_providers or set()

    def allowed(provider: str) -> bool:
        return not available or provider in available

    if host in {"bgm.tv", "bangumi.tv", "chii.in"}:
        match = re.match(r"^subject/(\d+)", path)
        if match and allowed("bangumi"):
            return MetadataScrapeCandidate(
                provider="bangumi",
                provider_label="Bangumi",
                provider_id=f"subject:{match.group(1)}",
                title="",
                subtitle="动漫",
            )
    if host in {"movie.douban.com", "www.movie.douban.com"}:
        match = re.match(r"^subject/(\d+)", path)
        provider = next((item for item in ("official_douban", "local_douban", "douban") if allowed(item)), "")
        if match and provider:
            label = {"official_douban": "豆瓣官方", "local_douban": "本地豆瓣", "douban": "豆瓣"}.get(provider, "豆瓣")
            return MetadataScrapeCandidate(
                provider=provider,
                provider_label=label,
                provider_id=match.group(1),
                title="",
                subtitle="豆瓣",
            )
    if host in {"www.themoviedb.org", "themoviedb.org"}:
        tv_match = re.match(r"^tv/(\d+)(?:/season/(\d+))?", path)
        movie_match = re.match(r"^movie/(\d+)", path)
        if tv_match and allowed("tmdb"):
            season = tv_match.group(2) or "1"
            return MetadataScrapeCandidate(
                provider="tmdb",
                provider_label="TMDB",
                provider_id=f"tv:{tv_match.group(1)}:season:{season}",
                title="",
                subtitle="剧集",
                raw={"season_number": _to_int(season) or 1},
            )
        if movie_match and allowed("tmdb"):
            return MetadataScrapeCandidate(
                provider="tmdb",
                provider_label="TMDB",
                provider_id=f"movie:{movie_match.group(1)}",
                title="",
                subtitle="电影",
            )
    return None


def normalize_following_candidate(candidate):
    provider = str(getattr(candidate, "provider", "") or "").strip()
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    if provider != "tmdb" or not provider_id.startswith("tv:") or ":season:" in provider_id:
        return candidate
    raw = dict(getattr(candidate, "raw", {}) or {})
    season_number = _to_int(raw.get("season_number")) or 1
    return replace(
        candidate,
        provider_id=f"{provider_id}:season:{season_number}",
        raw={**raw, "season_number": season_number},
    )


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _season_number_from_provider_id(provider_id: object) -> int:
    match = re.search(r":season:(\d+)$", str(provider_id or "").strip())
    if match is None:
        return 0
    return _to_int(match.group(1))


def _canonical_following_provider_id(provider: object, provider_id: object) -> str:
    text = str(provider_id or "").strip()
    if str(provider or "").strip() != "tmdb":
        return text
    if not text.startswith("tv:"):
        return text
    return text.split(":season:", 1)[0]


def _episode_from_raw(raw: dict[str, object]) -> FollowingEpisode:
    number = _to_int(raw.get("episode_number") or raw.get("sort") or raw.get("ep"))
    title = str(raw.get("name_cn") or raw.get("name") or raw.get("long_title") or raw.get("title") or "").strip()
    return FollowingEpisode(
        episode_number=number,
        season_number=_to_int(raw.get("season_number")),
        title=title,
        overview=str(raw.get("overview") or raw.get("desc") or raw.get("summary") or "").strip(),
        air_date=str(raw.get("air_date") or raw.get("airdate") or raw.get("date") or "").strip(),
        still=str(raw.get("still_url") or raw.get("still") or raw.get("cover") or raw.get("image") or "").strip(),
        runtime=_to_int(raw.get("runtime") or raw.get("duration")),
        is_special=number <= 0 or _to_int(raw.get("type")) != 0,
    )


def _season_title(season_number: int, title: str) -> str:
    normalized = title.strip()
    if normalized:
        return normalized
    if season_number <= 0:
        return "特别篇"
    return f"第 {season_number} 季"


def _season_from_raw(raw: dict[str, object]) -> FollowingSeason:
    season_number = _to_int(raw.get("season_number"))
    return FollowingSeason(
        season_number=season_number,
        title=_season_title(
            season_number,
            str(raw.get("name") or raw.get("title") or "").strip(),
        ),
        overview=str(raw.get("overview") or raw.get("summary") or "").strip(),
        air_date=str(raw.get("air_date") or raw.get("date") or "").strip(),
        poster=str(raw.get("poster_url") or raw.get("poster") or raw.get("poster_path") or "").strip(),
        episode_count=_to_int(raw.get("episode_count")),
        is_special=season_number <= 0,
    )


def _air_date(raw_value: object):
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_episode_counts(raw_episodes: list[dict[str, object]], *, now: int | None = None) -> tuple[int, int]:
    episodes = [_episode_from_raw(item) for item in raw_episodes if isinstance(item, dict)]
    normal_numbers = [episode.episode_number for episode in episodes if episode.episode_number > 0 and not episode.is_special]
    today = datetime.fromtimestamp(now if now is not None else int(time.time()), BEIJING_TZ).date()
    aired_numbers = [
        episode.episode_number
        for episode in episodes
        if episode.episode_number > 0
        and not episode.is_special
        and (_air_date(episode.air_date) is None or _air_date(episode.air_date) <= today)
    ]
    return (max(aired_numbers) if aired_numbers else 0, len(set(normal_numbers)))


def _has_future_episode(raw_episodes: list[dict[str, object]], *, now: int | None) -> bool:
    today = datetime.fromtimestamp(now if now is not None else int(time.time()), BEIJING_TZ).date()
    for raw in raw_episodes:
        episode = _episode_from_raw(raw)
        if episode.is_special or episode.episode_number <= 0:
            continue
        air_date = _air_date(episode.air_date)
        if air_date is not None and air_date > today:
            return True
    return False


def _media_kind_from_provider(provider: str, subtitle: object = "") -> str:
    subtitle_text = str(subtitle or "").lower()
    if provider == "bangumi" or any(marker in subtitle_text for marker in ("动漫", "动画", "anime")):
        return "anime"
    return "live_action"


def _media_kind_category(media_kind: str) -> str:
    return {
        "anime": "动漫",
        "movie": "电影",
        "live_action": "剧集",
    }.get(media_kind, "")


def _episode_raw_from_detail_fields(detail_fields: list[dict[str, object]]) -> list[dict[str, object]]:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "episodes":
            continue
        value = field.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _season_raw_from_detail_fields(detail_fields: list[dict[str, object]]) -> list[dict[str, object]]:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "seasons":
            continue
        value = field.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _last_episode_to_air_from_detail_fields(detail_fields: list[dict[str, object]]) -> int:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "last_episode_to_air":
            continue
        value = field.get("value")
        if not isinstance(value, dict):
            continue
        return _to_int(value.get("episode_number"))
    return 0


def _season_local_latest_episode(
    raw_episodes: list[dict[str, object]],
    raw_seasons: list[dict[str, object]],
    *,
    season_number: int,
    latest_episode: int,
) -> int:
    normalized_season = _to_int(season_number)
    normalized_latest = _to_int(latest_episode)
    if normalized_season <= 0 or normalized_latest <= 0:
        return 0

    season_episode_count = 0
    for raw_season in raw_seasons:
        if _to_int(raw_season.get("season_number")) == normalized_season:
            season_episode_count = _to_int(raw_season.get("episode_count"))
            break
    if season_episode_count <= 0:
        return 0

    local_numbers = {
        episode.episode_number
        for episode in (_episode_from_raw(item) for item in raw_episodes)
        if episode.episode_number > 0
        and not episode.is_special
        and (episode.season_number or normalized_season) == normalized_season
    }
    if not local_numbers:
        return 0
    local_latest = max(local_numbers)
    if normalized_latest > local_latest and local_latest >= season_episode_count:
        return local_latest
    return 0


def _next_episode_to_air_from_detail_fields(
    detail_fields: list[dict[str, object]],
) -> FollowingEpisode | None:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "next_episode_to_air":
            continue
        value = field.get("value")
        if not isinstance(value, dict):
            continue
        episode = _episode_from_raw(value)
        return episode if episode.episode_number > 0 else None
    return None


def _tmdb_recent_update_date_from_detail_fields(detail_fields: list[dict[str, object]]) -> str:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "last_episode_to_air":
            continue
        value = field.get("value")
        if not isinstance(value, dict):
            continue
        air_date = str(value.get("air_date") or "").strip()
        if air_date:
            return air_date
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "last_air_date":
            continue
        air_date = str(field.get("value") or "").strip()
        if air_date:
            return air_date
    return ""


def build_following_from_candidate(candidate, *, now: int) -> tuple[FollowingRecord, FollowingDetailSnapshot]:
    raw = dict(getattr(candidate, "raw", {}) or {})
    provider = str(getattr(candidate, "provider", "") or "").strip()
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    external_key, external_value = _provider_external_id(provider, provider_id)
    raw_seasons = [item for item in raw.get("seasons") or [] if isinstance(item, dict)]
    raw_episodes = [item for item in raw.get("episodes") or [] if isinstance(item, dict)]
    raw_next_episode = raw.get("next_episode_to_air")
    latest, total = compute_episode_counts(raw_episodes, now=now)
    season_number = _to_int(raw.get("season_number")) or _season_number_from_provider_id(provider_id)
    media_kind = _media_kind_from_provider(provider, getattr(candidate, "subtitle", ""))
    record = FollowingRecord(
        id=0,
        title=str(getattr(candidate, "title", "") or "").strip(),
        media_kind=media_kind,
        season_number=season_number,
        provider=provider,
        provider_id=_canonical_following_provider_id(provider, provider_id),
        provider_priority=following_provider_priority(media_kind),
        external_ids={external_key: str(external_value)} if external_value else {},
        latest_episode=latest,
        previous_latest_episode=latest,
        total_episodes=total,
        created_at=now,
        updated_at=now,
        next_check_after=now,
    )
    snapshot = FollowingDetailSnapshot(
        seasons=[_season_from_raw(item) for item in raw_seasons],
        episodes=[_episode_from_raw(item) for item in raw_episodes],
        next_episode=_episode_from_raw(raw_next_episode) if isinstance(raw_next_episode, dict) else None,
        refreshed_at=now,
    )
    return record, snapshot


def build_following_from_metadata_candidate(
    candidate,
    *,
    metadata_search_service,
    now: int,
    media_kind: str = "",
    include_related: bool = True,
    use_full_detail: bool = False,
    detail_record_sink: list[MetadataRecord] | None = None,
) -> tuple[FollowingRecord, FollowingDetailSnapshot]:
    candidate = normalize_following_candidate(candidate)
    if not (
        use_full_detail
        and str(getattr(candidate, "provider", "") or "").strip() == "tmdb"
    ):
        candidate = hydrate_following_candidate(metadata_search_service, candidate)
    record, snapshot = build_following_from_candidate(candidate, now=now)
    field_sources = _initial_field_sources(record)
    if use_full_detail:
        detail_record, detail_error = load_candidate_detail_record_full(metadata_search_service, candidate)
    else:
        detail_record, detail_error = load_candidate_detail_record(metadata_search_service, candidate)
    if detail_record is None:
        if detail_error:
            record.last_error = f"详情拉取失败: {detail_error}"
    else:
        if detail_record_sink is not None:
            detail_record_sink.append(detail_record)
        detail_following, detail_snapshot = build_snapshot_from_record(
            detail_record,
            now=now,
            media_kind=media_kind or record.media_kind,
        )
        record = merge_following_record(record, detail_following, field_sources=field_sources)
        snapshot = merge_following_snapshot(snapshot, detail_snapshot)
    if not include_related:
        return record, snapshot
    related_source_providers = None
    if str(getattr(candidate, "provider", "") or "").strip() == "tmdb" and detail_record is not None:
        related_source_providers = _source_providers_for_tmdb_record(detail_record)
    for related in iter_related_following_candidates(
        metadata_search_service,
        candidate,
        record=record,
        source_providers=related_source_providers,
    ):
        related = hydrate_following_candidate(metadata_search_service, related)
        related_detail, _detail_error = load_candidate_detail_record(metadata_search_service, related)
        if related_detail is None:
            continue
        related_following, related_snapshot = build_snapshot_from_record(
            related_detail,
            now=now,
            media_kind=record.media_kind,
        )
        record = merge_following_record(
            record,
            related_following,
            preserve_identity=True,
            fill_episode_counts=True,
            field_sources=field_sources,
        )
        snapshot = merge_following_snapshot(
            snapshot,
            related_snapshot,
            fill_missing=True,
            prefer_episodes=related_following.provider == "tmdb",
        )
    return record, snapshot


def hydrate_following_candidate(metadata_search_service, candidate):
    candidate = normalize_following_candidate(candidate)
    provider = str(getattr(candidate, "provider", "") or "").strip()
    if provider == "tmdb":
        hydrate = getattr(metadata_search_service, "_hydrate_tmdb_episode_candidate", None)
        if callable(hydrate):
            candidate = hydrate(
                VodItem(vod_id="", vod_name=str(getattr(candidate, "title", "") or "")),
                candidate,
            )
    if provider == "bangumi":
        hydrate = getattr(metadata_search_service, "_hydrate_bangumi_episode_candidate", None)
        if callable(hydrate):
            candidate = hydrate(candidate)
    if provider == "bilibili":
        hydrate = getattr(metadata_search_service, "_hydrate_bilibili_episode_candidate", None)
        if callable(hydrate):
            candidate = hydrate(candidate)
    return normalize_following_candidate(candidate)


def load_candidate_detail_record(metadata_search_service, candidate):
    detail_record = getattr(metadata_search_service, "detail_record", None)
    if not callable(detail_record):
        return None, ""
    try:
        return detail_record(candidate), ""
    except Exception as exc:
        return None, str(exc)


def load_candidate_detail_record_full(metadata_search_service, candidate):
    detail_record = getattr(metadata_search_service, "detail_record_full", None)
    if not callable(detail_record):
        return load_candidate_detail_record(metadata_search_service, candidate)
    try:
        return detail_record(candidate), ""
    except Exception as exc:
        return None, str(exc)


def _normalize_tmdb_refresh_provider_id(provider_id: str, *, media_kind: str, season_number: int) -> str:
    text = str(provider_id or "").strip()
    if not text:
        return ""
    normalized_kind = str(media_kind or "").strip().lower()
    if text.startswith("movie:"):
        return text
    default_season = season_number if season_number > 0 else 1
    if text.startswith("tv:"):
        parts = text.split(":")
        if len(parts) >= 4 and parts[2] == "season":
            return text
        return f"{text}:season:{default_season}"
    if not text.isdigit():
        return ""
    if normalized_kind == "movie" or "电影" in normalized_kind:
        return f"movie:{text}"
    return f"tv:{text}:season:{default_season}"


def _tmdb_refresh_candidate_from_record(record: FollowingRecord):
    provider_id = ""
    if record.provider == "tmdb":
        provider_id = record.provider_id
    if not provider_id:
        provider_id = str(record.external_ids.get("tmdb") or "").strip()
    normalized = _normalize_tmdb_refresh_provider_id(
        provider_id,
        media_kind=record.media_kind,
        season_number=record.season_number,
    )
    if not normalized:
        return None
    season_number = 0
    if normalized.startswith("tv:"):
        parts = normalized.split(":")
        if len(parts) >= 4 and parts[2] == "season":
            season_number = _to_int(parts[3]) or 1
    raw = {"season_number": season_number} if season_number > 0 else {}
    return MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id=normalized,
        title=record.title,
        subtitle="电影" if normalized.startswith("movie:") else "剧集",
        raw=raw,
    )


def _refresh_tmdb_counts_only(metadata_search_service, record: FollowingRecord, *, now: int):
    candidate = _tmdb_refresh_candidate_from_record(record)
    if candidate is None:
        return None
    detail_record, detail_error = load_candidate_detail_record_full(metadata_search_service, candidate)
    if detail_record is None:
        raise RuntimeError(detail_error or "tmdb returned no following detail")
    refreshed_record, _snapshot = build_snapshot_from_record(
        detail_record,
        now=now,
        media_kind=record.media_kind,
    )
    return (
        FollowingRecord(
            id=0,
            title="",
            latest_episode=refreshed_record.latest_episode,
            previous_latest_episode=refreshed_record.latest_episode,
            total_episodes=refreshed_record.total_episodes,
        ),
        FollowingDetailSnapshot(),
    )


def iter_related_following_candidates(
    metadata_search_service,
    candidate,
    *,
    record: FollowingRecord,
    source_providers: tuple[str, ...] | None = None,
):
    search = getattr(metadata_search_service, "search", None)
    if not callable(search):
        return
    media_kind = record.media_kind or _media_kind_from_provider(
        str(getattr(candidate, "provider", "") or "").strip(),
        getattr(candidate, "subtitle", ""),
    )
    query = MetadataQuery(
        title=str(record.title or getattr(candidate, "title", "") or "").strip(),
        year=str(getattr(candidate, "year", "") or "").strip(),
        category_name=_media_kind_category(media_kind) or str(getattr(candidate, "subtitle", "") or "").strip(),
        vod_dbid=_to_int(record.external_ids.get("douban"))
        or (_to_int(record.provider_id) if record.provider in {"official_douban", "local_douban", "douban"} else 0),
    )
    if not query.title:
        return
    selected_key = _candidate_key(candidate)
    if source_providers is None:
        try:
            groups = search(query, provider_filter="tmdb")
        except Exception:
            return
    else:
        groups = []
        for provider in source_providers:
            if provider == "douban":
                for provider_filter in _source_provider_filters(provider):
                    try:
                        provider_groups = search(query, provider_filter=provider_filter)
                    except Exception:
                        continue
                    groups.extend(provider_groups)
                    if any(list(getattr(group, "items", []) or []) for group in provider_groups):
                        break
                continue
            try:
                groups.extend(search(query, provider_filter=provider))
            except Exception:
                continue
    for group in groups:
        for item in list(getattr(group, "items", []) or [])[:1]:
            if _candidate_key(item) == selected_key:
                continue
            yield item


def _candidate_key(candidate) -> tuple[str, str]:
    return (
        str(getattr(candidate, "provider", "") or "").strip(),
        str(getattr(candidate, "provider_id", "") or "").strip(),
    )


def _douban_id_from_following_sources(record: FollowingRecord, tmdb_record: MetadataRecord) -> int:
    tmdb_douban_id = _to_int(getattr(tmdb_record, "douban_id", 0))
    if tmdb_douban_id:
        return tmdb_douban_id
    external_douban_id = _to_int(record.external_ids.get("douban"))
    if external_douban_id:
        return external_douban_id
    if record.provider in {"official_douban", "local_douban", "douban"}:
        return _to_int(record.provider_id)
    return 0


def _source_provider_filters(provider: str) -> tuple[str, ...]:
    return _FOLLOWING_SOURCE_PROVIDER_FILTERS.get(provider, (provider,))


def _source_providers_for_tmdb_record(tmdb_record: MetadataRecord) -> tuple[str, ...]:
    providers: list[str] = list(_THIRD_PARTY_SOURCE_PROVIDERS)
    if _tmdb_record_is_animation(tmdb_record):
        providers.append("bangumi")
    for entry in _playback_platform_source_entries_from_tmdb(tmdb_record):
        provider = _playback_provider_key(entry.provider, entry.label, entry.url)
        if provider in _PLAYBACK_SOURCE_PROVIDERS and provider not in providers:
            providers.append(provider)
    return tuple(providers)


def _playback_provider_key(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = re.sub(r"[\s\-_:.：,，/\\|·•'\"`()（）《》【】\[\]]+", "", text.lower())
        key = _PLAYBACK_SOURCE_LABEL_KEYS.get(normalized)
        if key:
            return key
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower().strip(".")
        if not host:
            continue
        for provider, domains in _PLAYBACK_SOURCE_PROVIDER_DOMAINS.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                return provider
    return ""


def _tmdb_record_is_animation(tmdb_record: MetadataRecord) -> bool:
    values: list[object] = [
        *list(getattr(tmdb_record, "genres", []) or []),
        getattr(tmdb_record, "title", ""),
        getattr(tmdb_record, "original_title", ""),
        *list(getattr(tmdb_record, "aliases", []) or []),
    ]
    for field in list(getattr(tmdb_record, "detail_fields", []) or []):
        if not isinstance(field, dict):
            continue
        label = str(field.get("label") or "").strip()
        if label in {"类型", "分类", "genres"}:
            values.append(field.get("value"))
    normalized = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    return any(token in normalized for token in _TMDB_ANIMATION_TOKENS)


def _initial_field_sources(record: FollowingRecord) -> dict[str, str]:
    return {
        "poster": record.provider if record.poster else "",
        "backdrop": record.provider if record.backdrop else "",
        "rating": record.provider if record.rating else "",
    }


def _provider_rank(field_name: str, provider: str) -> int:
    order = _FIELD_PROVIDER_PRIORITY.get(field_name, [])
    return order.index(provider) if provider in order else len(order) + 100


def _should_replace_field(field_name: str, current_provider: str, next_provider: str) -> bool:
    if not current_provider:
        return True
    return _provider_rank(field_name, next_provider) <= _provider_rank(field_name, current_provider)


def _merge_visual_field(
    field_name: str,
    current_value: str,
    next_value: str,
    next_provider: str,
    field_sources: dict[str, str] | None,
) -> str:
    if not next_value:
        return current_value
    if field_sources is None:
        return next_value or current_value
    if current_value and not _should_replace_field(field_name, field_sources.get(field_name, ""), next_provider):
        return current_value
    field_sources[field_name] = next_provider
    return next_value


def merge_following_record(
    record: FollowingRecord,
    detail: FollowingRecord,
    *,
    preserve_identity: bool = False,
    fill_episode_counts: bool = False,
    field_sources: dict[str, str] | None = None,
) -> FollowingRecord:
    external_ids = dict(record.external_ids)
    external_ids.update(detail.external_ids)
    latest_episode = record.latest_episode or detail.latest_episode if fill_episode_counts else detail.latest_episode or record.latest_episode
    total_episodes = max(record.total_episodes, detail.total_episodes) if fill_episode_counts else detail.total_episodes or record.total_episodes
    return replace(
        record,
        title=record.title if preserve_identity else detail.title or record.title,
        original_title=record.original_title or detail.original_title if preserve_identity else detail.original_title or record.original_title,
        media_kind=record.media_kind or detail.media_kind if preserve_identity else detail.media_kind or record.media_kind,
        season_number=detail.season_number or record.season_number,
        poster=_merge_visual_field("poster", record.poster, detail.poster, detail.provider, field_sources),
        backdrop=_merge_visual_field("backdrop", record.backdrop, detail.backdrop, detail.provider, field_sources),
        rating=_merge_visual_field("rating", record.rating, detail.rating, detail.provider, field_sources),
        provider=record.provider if preserve_identity else detail.provider or record.provider,
        provider_id=record.provider_id if preserve_identity else detail.provider_id or record.provider_id,
        provider_priority=record.provider_priority if preserve_identity else detail.provider_priority or record.provider_priority,
        external_ids=external_ids,
        latest_episode=latest_episode,
        previous_latest_episode=latest_episode or detail.previous_latest_episode or record.previous_latest_episode,
        total_episodes=total_episodes,
        updated_at=detail.updated_at or record.updated_at,
    )


def merge_following_snapshot(
    snapshot: FollowingDetailSnapshot,
    detail: FollowingDetailSnapshot,
    *,
    fill_missing: bool = False,
    prefer_episodes: bool = False,
) -> FollowingDetailSnapshot:
    if fill_missing:
        if prefer_episodes:
            return replace(
                snapshot,
                overview=snapshot.overview or detail.overview,
                metadata_fields=snapshot.metadata_fields or detail.metadata_fields,
                cast=snapshot.cast or detail.cast,
                crew=snapshot.crew or detail.crew,
                seasons=snapshot.seasons or detail.seasons,
                episodes=detail.episodes or snapshot.episodes,
                next_episode=detail.next_episode or snapshot.next_episode,
                posters=snapshot.posters or detail.posters,
                backdrops=snapshot.backdrops or detail.backdrops,
                metadata_bundle=detail.metadata_bundle or snapshot.metadata_bundle,
                refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
            )
        return replace(
            snapshot,
            overview=snapshot.overview or detail.overview,
            metadata_fields=snapshot.metadata_fields or detail.metadata_fields,
            cast=snapshot.cast or detail.cast,
            crew=snapshot.crew or detail.crew,
            seasons=snapshot.seasons or detail.seasons,
            episodes=detail.episodes if prefer_episodes and detail.episodes else snapshot.episodes or detail.episodes,
            next_episode=detail.next_episode or snapshot.next_episode,
            posters=snapshot.posters or detail.posters,
            backdrops=snapshot.backdrops or detail.backdrops,
            metadata_bundle=detail.metadata_bundle or snapshot.metadata_bundle,
            refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
        )
    return replace(
        snapshot,
        overview=detail.overview or snapshot.overview,
        metadata_fields=detail.metadata_fields or snapshot.metadata_fields,
        cast=detail.cast or snapshot.cast,
        crew=detail.crew or snapshot.crew,
        seasons=detail.seasons or snapshot.seasons,
        episodes=detail.episodes or snapshot.episodes,
        next_episode=detail.next_episode or snapshot.next_episode,
        posters=detail.posters or snapshot.posters,
        backdrops=detail.backdrops or snapshot.backdrops,
        metadata_bundle=detail.metadata_bundle or snapshot.metadata_bundle,
        refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
    )


def build_snapshot_from_record(record, *, now: int, media_kind: str = "") -> tuple[FollowingRecord, FollowingDetailSnapshot]:
    provider = str(getattr(record, "provider", "") or "").strip()
    provider_id = str(getattr(record, "provider_id", "") or "").strip()
    external_ids: dict[str, str] = {}
    external_key, external_value = _provider_external_id(provider, provider_id)
    if external_value:
        external_ids[external_key] = str(external_value)
    tmdb_id = str(getattr(record, "tmdb_id", "") or "").strip()
    if tmdb_id:
        external_ids["tmdb"] = tmdb_id
    douban_id = _to_int(getattr(record, "douban_id", 0))
    if douban_id:
        external_ids["douban"] = str(douban_id)

    detail_fields = list(getattr(record, "detail_fields", []) or [])
    raw_episodes = _episode_raw_from_detail_fields(detail_fields)
    raw_seasons = _season_raw_from_detail_fields(detail_fields)
    season_number = _season_number_from_provider_id(provider_id)
    latest, total = compute_episode_counts(raw_episodes, now=now)
    last_ep_to_air = _last_episode_to_air_from_detail_fields(detail_fields)
    next_episode = _next_episode_to_air_from_detail_fields(detail_fields)
    ongoing = next_episode is not None or _has_future_episode(raw_episodes, now=now)
    season_local_latest = _season_local_latest_episode(
        raw_episodes,
        raw_seasons,
        season_number=season_number,
        latest_episode=last_ep_to_air,
    )
    if season_local_latest > 0:
        last_ep_to_air = season_local_latest
    if last_ep_to_air > 0 and last_ep_to_air > latest:
        latest = last_ep_to_air
    if last_ep_to_air > 0 and last_ep_to_air > total:
        total = 0 if ongoing else last_ep_to_air
    if ongoing and total > 0 and latest > 0 and total <= latest:
        total = 0
    normalized_kind = media_kind or _media_kind_from_provider(provider)
    following = FollowingRecord(
        id=0,
        title=str(getattr(record, "title", "") or "").strip(),
        original_title=str(getattr(record, "original_title", "") or "").strip(),
        media_kind=normalized_kind,
        season_number=season_number,
        poster=str(getattr(record, "poster", "") or "").strip(),
        backdrop=str(getattr(record, "backdrop", "") or "").strip(),
        rating=str(getattr(record, "rating", "") or "").strip(),
        provider=provider,
        provider_id=_canonical_following_provider_id(provider, provider_id),
        provider_priority=following_provider_priority(normalized_kind),
        external_ids=external_ids,
        latest_episode=latest,
        previous_latest_episode=latest,
        total_episodes=total,
        created_at=now,
        updated_at=now,
        next_check_after=now,
    )
    snapshot = FollowingDetailSnapshot(
        overview=str(getattr(record, "overview", "") or "").strip(),
        metadata_fields=_metadata_fields_from_record(record),
        cast=_people_details(
            list(getattr(record, "cast_details", []) or []),
            list(getattr(record, "actors", []) or []),
        ),
        crew=_people_details(
            list(getattr(record, "crew_details", []) or []),
            list(getattr(record, "directors", []) or []),
            fallback_job="Director",
        ),
        seasons=[_season_from_raw(item) for item in raw_seasons],
        episodes=[_episode_from_raw(item) for item in raw_episodes],
        next_episode=next_episode,
        posters=[following.poster] if following.poster else [],
        backdrops=list(getattr(record, "backdrops", []) or []) or ([following.backdrop] if following.backdrop else []),
        refreshed_at=now,
    )
    return following, snapshot


def _provider_label(provider: str) -> str:
    return {
        "tmdb": "TMDB",
        "douban": "豆瓣",
        "bangumi": "Bangumi",
        "bilibili": "B站",
        "iqiyi": "爱奇艺",
        "tencent": "腾讯",
        "youku": "优酷",
        "mgtv": "芒果",
        "sohu": "搜狐",
    }.get(str(provider or "").strip(), str(provider or "").strip())


def _normalize_match_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _provider_rating_label(provider: str) -> str:
    return {
        "tmdb": "TMDB",
        "douban": "豆瓣",
        "bangumi": "Bangumi",
    }.get(str(provider or "").strip(), _provider_label(provider))


def _rating_entry(provider: str, label: str, value: object) -> FollowingRatingEntry:
    return FollowingRatingEntry(
        provider=str(provider or "").strip(),
        label=str(label or "").strip(),
        value=str(value or "").strip(),
    )


def _merge_metadata_fields_fill_missing(
    current_fields: list[dict[str, str]],
    next_fields: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged = [dict(item) for item in current_fields]
    seen = {str(item.get("label") or "").strip() for item in merged}
    for field in next_fields:
        label = str(field.get("label") or "").strip()
        value = str(field.get("value") or "").strip()
        if not label or not value or label in seen:
            continue
        merged.append({"label": label, "value": value})
        seen.add(label)
    return merged


def _playback_platform_entries_from_tmdb(record: MetadataRecord) -> list[FollowingPlaybackPlatformEntry]:
    entries: list[FollowingPlaybackPlatformEntry] = []
    detail_fields = list(getattr(record, "detail_fields", []) or [])
    for field in detail_fields:
        if not isinstance(field, dict) or str(field.get("label") or "").strip() != "watch_providers":
            continue
        values = field.get("value")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            entries.append(
                FollowingPlaybackPlatformEntry(
                    provider=str(item.get("provider") or "").strip(),
                    label=str(item.get("label") or item.get("provider_name") or "").strip(),
                    url=str(item.get("url") or item.get("link") or "").strip(),
                )
            )
    return entries


def _playback_platform_source_entries_from_tmdb(record: MetadataRecord) -> list[FollowingPlaybackPlatformEntry]:
    entries = _playback_platform_entries_from_tmdb(record)
    detail_fields = list(getattr(record, "detail_fields", []) or [])
    for field in detail_fields:
        if not isinstance(field, dict) or str(field.get("label") or "").strip() != "watch_provider_sources":
            continue
        values = field.get("value")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            provider = _playback_provider_key(item.get("provider"), item.get("label"), item.get("url"), item.get("link"))
            if not provider:
                continue
            entries.append(
                FollowingPlaybackPlatformEntry(
                    provider=provider,
                    label=str(item.get("label") or _provider_label(provider)).strip(),
                    url=str(item.get("url") or item.get("link") or "").strip(),
                )
            )
    return entries


def _playback_platform_entries_from_official_links(record: MetadataRecord) -> list[FollowingPlaybackPlatformEntry]:
    entries: list[FollowingPlaybackPlatformEntry] = []
    detail_fields = list(getattr(record, "detail_fields", []) or [])
    for field in detail_fields:
        if not isinstance(field, dict) or str(field.get("label") or "").strip() != "official_links":
            continue
        values = field.get("value")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            provider = _playback_provider_key(item.get("provider"), item.get("label"), item.get("url"), item.get("link"))
            if not provider:
                continue
            entries.append(
                FollowingPlaybackPlatformEntry(
                    provider=provider,
                    label=str(item.get("label") or _provider_label(provider)).strip(),
                    url=str(item.get("url") or item.get("link") or "").strip(),
                )
            )
    return entries


def _playback_platform_entries_from_record(record: MetadataRecord) -> list[FollowingPlaybackPlatformEntry]:
    official_entries = _playback_platform_entries_from_official_links(record)
    if official_entries:
        return official_entries
    field_map = {
        str(item.get("label") or "").strip(): str(item.get("value") or "").strip()
        for item in list(getattr(record, "detail_fields", []) or [])
        if isinstance(item, dict)
    }
    provider = str(getattr(record, "provider", "") or "").strip()
    entry = FollowingPlaybackPlatformEntry(
        provider=provider,
        label=_provider_label(provider),
        url=field_map.get("播放链接") or "",
        latest_episode=_to_int(field_map.get("最新集数")),
        update_time_text=field_map.get("更新时间") or "",
        status_text=field_map.get("更新状态") or "",
    )
    if not any((entry.url, entry.latest_episode, entry.update_time_text, entry.status_text)):
        return []
    return [entry]


def _record_detail_field_value(record: MetadataRecord, label: str) -> str:
    for item in list(getattr(record, "detail_fields", []) or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("label") or "").strip() == label:
            return str(item.get("value") or "").strip()
    return ""


def _playback_source_record_has_native_link(provider: str, record: MetadataRecord) -> bool:
    provider_key = str(provider or "").strip()
    expected_domains = _PLAYBACK_SOURCE_PROVIDER_DOMAINS.get(provider_key)
    if not expected_domains:
        return True
    url = _record_detail_field_value(record, "播放链接")
    if not url:
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return True
    return any(host == domain or host.endswith(f".{domain}") for domain in expected_domains)


def _merge_playback_platform_updates(
    entries: list[FollowingPlaybackPlatformEntry],
    detail_record: MetadataRecord,
) -> list[FollowingPlaybackPlatformEntry]:
    mapped = {entry.provider: entry for entry in entries}
    for new_entry in _playback_platform_entries_from_record(detail_record):
        current = mapped.get(new_entry.provider)
        if current is None:
            mapped[new_entry.provider] = new_entry
            continue
        mapped[new_entry.provider] = replace(
            current,
            url=new_entry.url or current.url,
            latest_episode=new_entry.latest_episode or current.latest_episode,
            update_time_text=new_entry.update_time_text or current.update_time_text,
            status_text=new_entry.status_text or current.status_text,
        )
    return list(mapped.values())


def _source_snapshot_from_record(
    provider: str,
    provider_label: str,
    detail_record: MetadataRecord,
    *,
    confidence: float,
    now: int,
    media_kind: str,
) -> FollowingMetadataSourceSnapshot:
    _following, snapshot = build_snapshot_from_record(
        detail_record,
        now=now,
        media_kind=media_kind,
    )
    ratings: list[FollowingRatingEntry] = []
    rating = str(getattr(detail_record, "rating", "") or "").strip()
    if rating:
        ratings.append(_rating_entry(provider, _provider_rating_label(provider), rating))
    playback_platforms = (
        _playback_platform_entries_from_tmdb(detail_record)
        if provider == "tmdb"
        else _playback_platform_entries_from_record(detail_record)
    )
    return FollowingMetadataSourceSnapshot(
        source_key=provider,
        provider=provider,
        provider_label=provider_label,
        provider_id=str(getattr(detail_record, "provider_id", "") or "").strip(),
        matched=True,
        confidence=float(confidence or 0.0),
        overview=snapshot.overview,
        metadata_fields=list(snapshot.metadata_fields),
        ratings=ratings,
        playback_platforms=playback_platforms,
        episodes=list(snapshot.episodes),
        seasons=list(snapshot.seasons),
    )


def build_following_metadata_bundle(
    *,
    base_record: FollowingRecord,
    base_snapshot: FollowingDetailSnapshot,
    tmdb_detail_record: MetadataRecord,
    provider_records: dict[str, tuple[MetadataRecord, float]],
) -> tuple[FollowingMetadataBundle, FollowingRecord, FollowingDetailSnapshot]:
    now = max(int(base_snapshot.refreshed_at or 0), int(time.time()))
    tmdb_record, tmdb_snapshot = build_snapshot_from_record(
        tmdb_detail_record,
        now=now,
        media_kind=base_record.media_kind,
    )
    field_sources = _initial_field_sources(base_record)
    merged_record = merge_following_record(
        base_record,
        tmdb_record,
        field_sources=field_sources,
    )
    merged_snapshot = merge_following_snapshot(base_snapshot, tmdb_snapshot)
    source_snapshots = {
        "merged": FollowingMetadataSourceSnapshot(
            source_key="merged",
            provider="merged",
            provider_label="合并",
        ),
        "tmdb": _source_snapshot_from_record(
            "tmdb",
            "TMDB",
            tmdb_detail_record,
            confidence=1.0,
            now=now,
            media_kind=merged_record.media_kind,
        ),
    }
    ratings = [_rating_entry("tmdb", "TMDB", tmdb_detail_record.rating)]
    playback_platforms = _playback_platform_entries_from_tmdb(tmdb_detail_record)

    for provider, (detail_record, confidence) in provider_records.items():
        if float(confidence or 0.0) < _FOLLOWING_SOURCE_THRESHOLDS.get(provider, 1.0):
            continue
        detail_following, detail_snapshot = build_snapshot_from_record(
            detail_record,
            now=now,
            media_kind=merged_record.media_kind,
        )
        merged_record = merge_following_record(
            merged_record,
            detail_following,
            preserve_identity=True,
            fill_episode_counts=provider in {"bilibili", "iqiyi", "tencent", "youku", "mgtv", "sohu"},
            field_sources=field_sources,
        )
        merged_snapshot = merge_following_snapshot(
            merged_snapshot,
            detail_snapshot,
            fill_missing=True,
            prefer_episodes=False,
        )
        merged_snapshot.metadata_fields = _merge_metadata_fields_fill_missing(
            merged_snapshot.metadata_fields,
            detail_snapshot.metadata_fields,
        )
        source_snapshots[provider] = _source_snapshot_from_record(
            provider,
            _provider_label(provider),
            detail_record,
            confidence=confidence,
            now=now,
            media_kind=merged_record.media_kind,
        )
        if provider in {"douban", "bangumi"}:
            ratings.append(_rating_entry(provider, _provider_rating_label(provider), detail_record.rating))
        if provider in {"douban", "bilibili", "iqiyi", "tencent", "youku", "mgtv", "sohu"}:
            playback_platforms = _merge_playback_platform_updates(playback_platforms, detail_record)

    merged_source = FollowingMetadataSourceSnapshot(
        source_key="merged",
        provider="merged",
        provider_label="合并",
        overview=merged_snapshot.overview,
        metadata_fields=list(merged_snapshot.metadata_fields),
        ratings=[item for item in ratings if item.value],
        playback_platforms=playback_platforms,
        episodes=list(merged_snapshot.episodes),
        seasons=list(merged_snapshot.seasons),
    )
    source_snapshots["merged"] = merged_source
    bundle = FollowingMetadataBundle(
        merged_snapshot=merged_source,
        source_snapshots=source_snapshots,
        available_source_keys=["merged", *[key for key in source_snapshots if key != "merged"]],
        default_source_key="merged",
    )
    merged_snapshot.metadata_bundle = bundle
    return bundle, merged_record, merged_snapshot


def build_following_source_metadata_bundle(
    *,
    base_record: FollowingRecord,
    base_snapshot: FollowingDetailSnapshot,
    provider: str,
    provider_label: str,
    detail_record: MetadataRecord,
    confidence: float = 1.0,
) -> tuple[FollowingMetadataBundle, FollowingRecord, FollowingDetailSnapshot]:
    now = max(int(base_snapshot.refreshed_at or 0), int(time.time()))
    detail_following, detail_snapshot = build_snapshot_from_record(
        detail_record,
        now=now,
        media_kind=base_record.media_kind,
    )
    field_sources = _initial_field_sources(base_record)
    merged_record = merge_following_record(
        base_record,
        detail_following,
        preserve_identity=True,
        field_sources=field_sources,
    )
    merged_snapshot = merge_following_snapshot(base_snapshot, detail_snapshot)
    source_snapshot = _source_snapshot_from_record(
        provider,
        provider_label,
        detail_record,
        confidence=confidence,
        now=now,
        media_kind=merged_record.media_kind,
    )
    ratings: list[FollowingRatingEntry] = []
    rating = str(getattr(detail_record, "rating", "") or "").strip()
    if rating and provider in {"bangumi", "douban", "tmdb"}:
        ratings.append(_rating_entry(provider, _provider_rating_label(provider), rating))
    merged_source = FollowingMetadataSourceSnapshot(
        source_key="merged",
        provider="merged",
        provider_label="合并",
        overview=merged_snapshot.overview,
        metadata_fields=list(merged_snapshot.metadata_fields),
        ratings=ratings,
        playback_platforms=list(source_snapshot.playback_platforms),
        episodes=list(merged_snapshot.episodes),
        seasons=list(merged_snapshot.seasons),
    )
    source_snapshots = {
        "merged": merged_source,
        provider: source_snapshot,
    }
    bundle = FollowingMetadataBundle(
        merged_snapshot=merged_source,
        source_snapshots=source_snapshots,
        available_source_keys=["merged", provider],
        default_source_key="merged",
    )
    merged_snapshot.metadata_bundle = bundle
    return bundle, merged_record, merged_snapshot


def _metadata_fields_from_record(record) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()
    detail_fields = list(getattr(record, "detail_fields", []) or [])

    def put(label: str, value: object) -> None:
        normalized = str(value or "").strip()
        if not normalized or label in seen:
            return
        fields.append({"label": label, "value": normalized})
        seen.add(label)

    put("类型", " / ".join(str(item).strip() for item in list(getattr(record, "genres", []) or []) if str(item).strip()))
    put("年代", getattr(record, "year", ""))
    put("地区", getattr(record, "country", ""))
    put("语言", getattr(record, "language", ""))
    put("导演", ", ".join(str(item).strip() for item in list(getattr(record, "directors", []) or []) if str(item).strip()))
    put("演员", ", ".join(str(item).strip() for item in list(getattr(record, "actors", []) or []) if str(item).strip()))
    put("别名", " / ".join(str(item).strip() for item in list(getattr(record, "aliases", []) or []) if str(item).strip()))
    douban_id = _to_int(getattr(record, "douban_id", 0))
    if douban_id:
        put("豆瓣ID", str(douban_id))
    put("IMDb ID", getattr(record, "imdb_id", ""))
    put("TMDB ID", getattr(record, "tmdb_id", ""))
    if str(getattr(record, "provider", "") or "").strip() == "tmdb":
        put("最近更新", _tmdb_recent_update_date_from_detail_fields(detail_fields))
    for item in detail_fields:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if label in (
            "episodes",
            "last_episode_to_air",
            "next_episode_to_air",
            "seasons",
            "last_air_date",
            "watch_provider_sources",
        ):
            continue
        value = item.get("value")
        if isinstance(value, list):
            continue
        put(label, value)
    return fields


def _people_details(
    details: list[object],
    names: list[object],
    *,
    fallback_job: str = "",
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in details:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        normalized = {key: value for key, value in item.items() if value}
        normalized["name"] = name
        if fallback_job and not normalized.get("job"):
            normalized["job"] = fallback_job
        result.append(normalized)
        seen.add(name)
    for name_value in names:
        name = str(name_value or "").strip()
        if not name or name in seen:
            continue
        item = {"name": name}
        if fallback_job:
            item["job"] = fallback_job
        result.append(item)
        seen.add(name)
    return result


class FollowingMetadataGateway:
    def __init__(self, metadata_search_service) -> None:
        self._metadata_search_service = metadata_search_service

    def _source_confidence(self, provider: str, candidate, tmdb_record: MetadataRecord) -> float:
        score = 0.0
        candidate_title = _normalize_match_text(getattr(candidate, "title", ""))
        expected_titles = {
            _normalize_match_text(getattr(tmdb_record, "title", "")),
            *{
                _normalize_match_text(item)
                for item in list(getattr(tmdb_record, "aliases", []) or [])
                if _normalize_match_text(item)
            },
        }
        expected_titles.discard("")
        if candidate_title and candidate_title in expected_titles:
            score += 0.7
            if provider in _PLAYBACK_SOURCE_PROVIDERS:
                score += 0.1
        candidate_year = str(getattr(candidate, "year", "") or "").strip()
        tmdb_year = str(getattr(tmdb_record, "year", "") or "").strip()
        if candidate_year and tmdb_year and candidate_year == tmdb_year:
            score += 0.2
        if provider in {"bangumi", "douban"}:
            score += 0.1
        return round(min(score, 1.0), 4)

    def _best_source_candidate(self, provider: str, candidates: list[object], tmdb_record: MetadataRecord):
        best = None
        best_score = -1.0
        for candidate in candidates:
            score = self._source_confidence(provider, candidate, tmdb_record)
            if score > best_score:
                best = candidate
                best_score = score
        return best

    def _source_provider_filters(self, provider: str) -> tuple[str, ...]:
        return _source_provider_filters(provider)

    def _source_providers_for_tmdb_record(self, tmdb_record: MetadataRecord) -> tuple[str, ...]:
        return _source_providers_for_tmdb_record(tmdb_record)

    def load_source_records(
        self,
        record: FollowingRecord,
        *,
        tmdb_record: MetadataRecord,
    ) -> dict[str, tuple[MetadataRecord, float]]:
        results: dict[str, tuple[MetadataRecord, float]] = {}
        category_name = "动漫" if record.media_kind == "anime" or _tmdb_record_is_animation(tmdb_record) else "剧集"
        query = MetadataQuery(
            title=str(getattr(tmdb_record, "title", "") or record.title or "").strip(),
            year=str(getattr(tmdb_record, "year", "") or "").strip(),
            category_name=category_name,
            vod_dbid=_douban_id_from_following_sources(record, tmdb_record),
        )
        source_providers = self._source_providers_for_tmdb_record(tmdb_record)
        logger.info(
            "Following metadata source providers title=%s tmdb_id=%s providers=%s",
            query.title,
            str(getattr(tmdb_record, "tmdb_id", "") or "").strip(),
            ",".join(source_providers),
            extra={"log_category": "metadata", "log_source": "app"},
        )
        for provider in source_providers:
            source_record = self._load_source_record(
                provider,
                query,
                tmdb_record=tmdb_record,
            )
            if source_record is None:
                continue
            detail_record, _confidence = source_record
            results[provider] = source_record
            for entry in _playback_platform_entries_from_record(detail_record):
                linked_provider = _playback_provider_key(entry.provider, entry.label, entry.url)
                if (
                    linked_provider in _PLAYBACK_SOURCE_PROVIDERS
                    and linked_provider not in results
                    and linked_provider != provider
                ):
                    linked_record = self._load_single_source_record(
                        linked_provider,
                        query,
                        tmdb_record=tmdb_record,
                    )
                    if linked_record is not None:
                        results[linked_provider] = linked_record
        return results

    def _load_source_record(
        self,
        provider: str,
        query: MetadataQuery,
        *,
        tmdb_record: MetadataRecord,
    ) -> tuple[MetadataRecord, float] | None:
        if provider != "douban":
            return self._load_single_source_record(
                provider,
                query,
                tmdb_record=tmdb_record,
            )
        for provider_filter in self._source_provider_filters(provider):
            result = self._load_single_source_record(
                provider,
                query,
                tmdb_record=tmdb_record,
                provider_filters=(provider_filter,),
            )
            if result is not None:
                return result
        return None

    def _load_single_source_record(
        self,
        provider: str,
        query: MetadataQuery,
        *,
        tmdb_record: MetadataRecord,
        provider_filters: tuple[str, ...] | None = None,
    ) -> tuple[MetadataRecord, float] | None:
        candidates: list[object] = []
        for provider_filter in provider_filters or self._source_provider_filters(provider):
            try:
                groups = self._metadata_search_service.search(query, provider_filter=provider_filter)
            except Exception:
                continue
            candidates.extend(item for group in groups for item in list(getattr(group, "items", []) or []))
        best = self._best_source_candidate(provider, candidates, tmdb_record)
        if best is None:
            return None
        confidence = self._source_confidence(provider, best, tmdb_record)
        detail_record, _error = load_candidate_detail_record(self._metadata_search_service, best)
        if detail_record is None:
            return None
        if not _playback_source_record_has_native_link(provider, detail_record):
            return None
        return detail_record, confidence

    def refresh(self, record: FollowingRecord, provider: str):
        if provider == "tmdb":
            tmdb_result = _refresh_tmdb_counts_only(
                self._metadata_search_service,
                record,
                now=int(time.time()),
            )
            if tmdb_result is not None:
                return tmdb_result
        category_name = "动漫" if provider == "bangumi" else ""
        groups = self._metadata_search_service.search(
            MetadataQuery(title=record.title, category_name=category_name),
            provider_filter=provider,
        )
        candidates = [item for group in groups for item in group.items]
        preferred = next(
            (item for item in candidates if item.provider_id == record.provider_id),
            None,
        )
        candidate = preferred or (candidates[0] if candidates else None)
        if candidate is None:
            raise RuntimeError(f"{provider} returned no following candidate")
        return build_following_from_metadata_candidate(
            candidate,
            metadata_search_service=self._metadata_search_service,
            now=int(time.time()),
            media_kind=record.media_kind,
            include_related=False,
        )
