# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

ANIME_PROVIDER_PRIORITY = ["bangumi", "tmdb", "douban"]
LIVE_ACTION_PROVIDER_PRIORITY = ["tmdb", "douban", "bangumi"]
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class FollowingSourceBinding:
    source_kind: str
    source_key: str = ""
    source_name: str = ""
    vod_id: str = ""
    provider: str = ""
    provider_id: str = ""


@dataclass(slots=True)
class FollowingEpisode:
    episode_number: int
    season_number: int = 0
    title: str = ""
    overview: str = ""
    air_date: str = ""
    still: str = ""
    runtime: int = 0
    is_special: bool = False


@dataclass(slots=True)
class FollowingSeason:
    season_number: int
    title: str = ""
    overview: str = ""
    air_date: str = ""
    poster: str = ""
    episode_count: int = 0
    is_special: bool = False


@dataclass(slots=True)
class FollowingDetailSnapshot:
    following_id: int = 0
    overview: str = ""
    metadata_fields: list[dict[str, str]] = field(default_factory=list)
    cast: list[dict[str, object]] = field(default_factory=list)
    crew: list[dict[str, object]] = field(default_factory=list)
    seasons: list[FollowingSeason] = field(default_factory=list)
    episodes: list[FollowingEpisode] = field(default_factory=list)
    next_episode: FollowingEpisode | None = None
    posters: list[str] = field(default_factory=list)
    backdrops: list[str] = field(default_factory=list)
    refreshed_at: int = 0


@dataclass(slots=True)
class FollowingRecord:
    id: int
    title: str
    original_title: str = ""
    media_kind: str = ""
    season_number: int = 0
    poster: str = ""
    backdrop: str = ""
    rating: str = ""
    provider: str = ""
    provider_id: str = ""
    provider_priority: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    source_bindings: list[FollowingSourceBinding] = field(default_factory=list)
    current_season_number: int = 0
    current_episode: int = 0
    position_seconds: int = 0
    watched_latest_episode: bool = False
    latest_episode: int = 0
    previous_latest_episode: int = 0
    total_episodes: int = 0
    has_update: bool = False
    new_episode_count: int = 0
    homepage_prompt_pending: bool = False
    prompt_snoozed_until: int = 0
    created_at: int = 0
    updated_at: int = 0
    last_played_at: int = 0
    last_checked_at: int = 0
    next_check_after: int = 0
    last_error: str = ""


@dataclass(slots=True)
class FollowingCardItem:
    record: FollowingRecord
    display_title: str
    subtitle: str
    progress_text: str
    update_text: str
    updated_hint: bool
    error_text: str = ""


@dataclass(slots=True)
class FollowingUpdateResult:
    record_id: int
    checked: bool
    latest_episode: int = 0
    total_episodes: int = 0
    has_update: bool = False
    homepage_prompt_pending: bool = False
    error: str = ""


def resolve_progress_season(
    season_number: int,
    episode_number: int,
    *,
    fallback_season: int = 0,
) -> int:
    normalized_season = max(0, int(season_number or 0))
    if normalized_season > 0:
        return normalized_season
    normalized_fallback = max(0, int(fallback_season or 0))
    if normalized_fallback > 0 and episode_number > 0:
        return normalized_fallback
    return 1 if episode_number > 0 else normalized_fallback


def compare_progress(
    current_season_number: int,
    current_episode: int,
    target_season_number: int,
    target_episode: int,
    *,
    current_fallback_season: int = 0,
    target_fallback_season: int = 0,
) -> int:
    current_pair = (
        resolve_progress_season(
            current_season_number,
            current_episode,
            fallback_season=current_fallback_season,
        ),
        max(0, int(current_episode or 0)),
    )
    target_pair = (
        resolve_progress_season(
            target_season_number,
            target_episode,
            fallback_season=target_fallback_season,
        ),
        max(0, int(target_episode or 0)),
    )
    if current_pair < target_pair:
        return -1
    if current_pair > target_pair:
        return 1
    return 0


def progress_at_or_beyond(
    current_season_number: int,
    current_episode: int,
    latest_season_number: int,
    latest_episode: int,
    *,
    current_fallback_season: int = 0,
    latest_fallback_season: int = 0,
) -> bool:
    if max(0, int(latest_episode or 0)) <= 0:
        return False
    return compare_progress(
        current_season_number,
        current_episode,
        latest_season_number,
        latest_episode,
        current_fallback_season=current_fallback_season,
        target_fallback_season=latest_fallback_season,
    ) >= 0


class FollowingEpisodeState:
    WATCHED = "watched"
    RELEASED = "released"
    UPCOMING = "upcoming"
    PENDING = "pending"


def _episode_air_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_following_episode_state(
    *,
    episode: FollowingEpisode,
    current_season_number: int,
    current_episode: int,
    latest_season_number: int,
    latest_episode: int,
    visible_season_number: int,
    next_episode: FollowingEpisode | None,
    today: date | None = None,
) -> str:
    resolved_today = today or datetime.now(BEIJING_TZ).date()
    air_date = _episode_air_date(episode.air_date)
    episode_season = resolve_progress_season(
        episode.season_number,
        episode.episode_number,
        fallback_season=visible_season_number,
    )
    current_season = resolve_progress_season(
        current_season_number,
        current_episode,
        fallback_season=visible_season_number,
    )
    latest_season = resolve_progress_season(
        latest_season_number,
        latest_episode,
        fallback_season=visible_season_number,
    )
    if (
        episode_season == current_season
        and episode.episode_number > 0
        and episode.episode_number <= max(0, int(current_episode or 0))
    ):
        return FollowingEpisodeState.WATCHED
    if next_episode is not None:
        next_episode_season = resolve_progress_season(
            next_episode.season_number,
            next_episode.episode_number,
            fallback_season=visible_season_number,
        )
        next_air_date = _episode_air_date(next_episode.air_date)
        if (
            episode_season == next_episode_season
            and (
                episode.episode_number == next_episode.episode_number
                or (
                    air_date is not None
                    and next_air_date is not None
                    and air_date == next_air_date
                )
            )
        ):
            return FollowingEpisodeState.UPCOMING
    if (
        episode_season == latest_season
        and episode.episode_number > 0
        and episode.episode_number <= max(0, int(latest_episode or 0))
    ):
        return FollowingEpisodeState.RELEASED
    return FollowingEpisodeState.PENDING


def format_progress_episode(
    prefix: str,
    season_number: int,
    episode_number: int,
    *,
    fallback_season: int = 0,
) -> str:
    normalized_episode = max(0, int(episode_number or 0))
    if normalized_episode <= 0:
        return ""
    resolved_season = resolve_progress_season(
        season_number,
        normalized_episode,
        fallback_season=fallback_season,
    )
    if resolved_season > 0:
        return f"{prefix} S{resolved_season}E{normalized_episode}"
    return f"{prefix} {normalized_episode}"


def provider_priority_for_media_kind(media_kind: str) -> list[str]:
    return list(ANIME_PROVIDER_PRIORITY if media_kind == "anime" else LIVE_ACTION_PROVIDER_PRIORITY)
