# ruff: noqa: E501
from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    provider_priority_for_media_kind,
)
from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.scrape import MetadataScrapeCandidate
from atv_player.models import VodItem

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
_FIELD_PROVIDER_PRIORITY = {
    "poster": ["tmdb", "bangumi", "official_douban", "local_douban", "douban", "plugin", "iqiyi", "sohu"],
    "backdrop": ["tmdb", "bangumi", "official_douban", "local_douban", "douban", "plugin", "iqiyi", "sohu"],
    "rating": ["official_douban", "bangumi", "local_douban", "douban", "tmdb", "plugin", "iqiyi"],
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


def build_following_from_candidate(candidate, *, now: int) -> tuple[FollowingRecord, FollowingDetailSnapshot]:
    raw = dict(getattr(candidate, "raw", {}) or {})
    provider = str(getattr(candidate, "provider", "") or "").strip()
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    external_key, external_value = _provider_external_id(provider, provider_id)
    raw_episodes = [item for item in raw.get("episodes") or [] if isinstance(item, dict)]
    latest, total = compute_episode_counts(raw_episodes, now=now)
    media_kind = _media_kind_from_provider(provider, getattr(candidate, "subtitle", ""))
    record = FollowingRecord(
        id=0,
        title=str(getattr(candidate, "title", "") or "").strip(),
        media_kind=media_kind,
        provider=provider,
        provider_id=provider_id,
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
        episodes=[_episode_from_raw(item) for item in raw_episodes],
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
) -> tuple[FollowingRecord, FollowingDetailSnapshot]:
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
        detail_following, detail_snapshot = build_snapshot_from_record(
            detail_record,
            now=now,
            media_kind=media_kind or record.media_kind,
        )
        record = merge_following_record(record, detail_following, field_sources=field_sources)
        snapshot = merge_following_snapshot(snapshot, detail_snapshot)
    if not include_related:
        return record, snapshot
    for related in iter_related_following_candidates(
        metadata_search_service,
        candidate,
        record=record,
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


def iter_related_following_candidates(metadata_search_service, candidate, *, record: FollowingRecord):
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
    )
    if not query.title:
        return
    selected_key = _candidate_key(candidate)
    try:
        groups = search(query)
    except Exception:
        return
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
                overview=detail.overview or snapshot.overview,
                metadata_fields=detail.metadata_fields or snapshot.metadata_fields,
                cast=detail.cast or snapshot.cast,
                crew=detail.crew or snapshot.crew,
                episodes=detail.episodes or snapshot.episodes,
                posters=detail.posters or snapshot.posters,
                backdrops=detail.backdrops or snapshot.backdrops,
                refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
            )
        return replace(
            snapshot,
            overview=snapshot.overview or detail.overview,
            metadata_fields=snapshot.metadata_fields or detail.metadata_fields,
            cast=snapshot.cast or detail.cast,
            crew=snapshot.crew or detail.crew,
            episodes=detail.episodes if prefer_episodes and detail.episodes else snapshot.episodes or detail.episodes,
            posters=snapshot.posters or detail.posters,
            backdrops=snapshot.backdrops or detail.backdrops,
            refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
        )
    return replace(
        snapshot,
        overview=detail.overview or snapshot.overview,
        metadata_fields=detail.metadata_fields or snapshot.metadata_fields,
        cast=detail.cast or snapshot.cast,
        crew=detail.crew or snapshot.crew,
        episodes=detail.episodes or snapshot.episodes,
        posters=detail.posters or snapshot.posters,
        backdrops=detail.backdrops or snapshot.backdrops,
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

    raw_episodes = _episode_raw_from_detail_fields(list(getattr(record, "detail_fields", []) or []))
    latest, total = compute_episode_counts(raw_episodes, now=now)
    normalized_kind = media_kind or _media_kind_from_provider(provider)
    following = FollowingRecord(
        id=0,
        title=str(getattr(record, "title", "") or "").strip(),
        original_title=str(getattr(record, "original_title", "") or "").strip(),
        media_kind=normalized_kind,
        poster=str(getattr(record, "poster", "") or "").strip(),
        backdrop=str(getattr(record, "backdrop", "") or "").strip(),
        rating=str(getattr(record, "rating", "") or "").strip(),
        provider=provider,
        provider_id=provider_id,
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
        episodes=[_episode_from_raw(item) for item in raw_episodes],
        posters=[following.poster] if following.poster else [],
        backdrops=[following.backdrop] if following.backdrop else [],
        refreshed_at=now,
    )
    return following, snapshot


def _metadata_fields_from_record(record) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()

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
    for item in list(getattr(record, "detail_fields", []) or []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if label == "episodes":
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

    def refresh(self, record: FollowingRecord, provider: str):
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
