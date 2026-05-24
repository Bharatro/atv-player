from __future__ import annotations

import re

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    provider_priority_for_media_kind,
)


def following_provider_priority(media_kind: str) -> list[str]:
    return provider_priority_for_media_kind(media_kind)


def _provider_external_id(provider: str, provider_id: str) -> tuple[str, str]:
    if provider == "bangumi" and provider_id.startswith("subject:"):
        return "bangumi", provider_id.split(":", 1)[1]
    if provider == "tmdb":
        match = re.match(r"^(?:tv|movie):([^:]+)", provider_id)
        return ("tmdb", match.group(1)) if match else ("tmdb", provider_id)
    return provider, provider_id


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _episode_from_raw(raw: dict[str, object]) -> FollowingEpisode:
    number = _to_int(raw.get("episode_number") or raw.get("sort") or raw.get("ep"))
    title = str(raw.get("name_cn") or raw.get("name") or raw.get("title") or "").strip()
    return FollowingEpisode(
        episode_number=number,
        season_number=_to_int(raw.get("season_number")),
        title=title,
        overview=str(raw.get("overview") or raw.get("desc") or raw.get("summary") or "").strip(),
        air_date=str(raw.get("air_date") or raw.get("date") or "").strip(),
        still=str(raw.get("still_url") or raw.get("still") or raw.get("image") or "").strip(),
        runtime=_to_int(raw.get("runtime") or raw.get("duration")),
        is_special=number <= 0 or _to_int(raw.get("type")) != 0,
    )


def compute_episode_counts(raw_episodes: list[dict[str, object]]) -> tuple[int, int]:
    episodes = [_episode_from_raw(item) for item in raw_episodes if isinstance(item, dict)]
    normal_numbers = [episode.episode_number for episode in episodes if episode.episode_number > 0 and not episode.is_special]
    return (max(normal_numbers) if normal_numbers else 0, len(set(normal_numbers)))


def _media_kind_from_provider(provider: str, subtitle: object = "") -> str:
    subtitle_text = str(subtitle or "").lower()
    if provider == "bangumi" or any(marker in subtitle_text for marker in ("动漫", "动画", "anime")):
        return "anime"
    return "live_action"


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
    latest, total = compute_episode_counts(raw_episodes)
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
    latest, total = compute_episode_counts(raw_episodes)
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
        cast=[{"name": name} for name in list(getattr(record, "actors", []) or [])],
        crew=[{"name": name, "job": "Director"} for name in list(getattr(record, "directors", []) or [])],
        episodes=[_episode_from_raw(item) for item in raw_episodes],
        posters=[following.poster] if following.poster else [],
        backdrops=[following.backdrop] if following.backdrop else [],
        refreshed_at=now,
    )
    return following, snapshot
