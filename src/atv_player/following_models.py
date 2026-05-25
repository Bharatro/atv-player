# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass, field

ANIME_PROVIDER_PRIORITY = ["bangumi", "tmdb", "douban"]
LIVE_ACTION_PROVIDER_PRIORITY = ["tmdb", "douban", "bangumi"]


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
class FollowingDetailSnapshot:
    following_id: int = 0
    overview: str = ""
    metadata_fields: list[dict[str, str]] = field(default_factory=list)
    cast: list[dict[str, object]] = field(default_factory=list)
    crew: list[dict[str, object]] = field(default_factory=list)
    episodes: list[FollowingEpisode] = field(default_factory=list)
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


def provider_priority_for_media_kind(media_kind: str) -> list[str]:
    return list(ANIME_PROVIDER_PRIORITY if media_kind == "anime" else LIVE_ACTION_PROVIDER_PRIORITY)
