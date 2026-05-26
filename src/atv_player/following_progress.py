from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from atv_player.danmaku.utils import _play_item_episode_number
from atv_player.following_models import resolve_progress_season
from atv_player.models import PlayItem


@dataclass(slots=True)
class FollowingPlaybackProgressDecision:
    season_number: int
    episode_number: int
    threshold_reached: bool


def playback_progress_threshold_reached(*, position_seconds: int, duration_seconds: int) -> bool:
    if duration_seconds <= 0:
        return False
    return (max(0, int(position_seconds or 0)) / duration_seconds) >= 0.2


def resolve_following_playback_progress(
    item: PlayItem,
    playlist: Sequence[PlayItem] | None,
    *,
    current_index: int,
    fallback_season_number: int,
    position_seconds: int,
    duration_seconds: int,
) -> FollowingPlaybackProgressDecision | None:
    title_episode = _play_item_episode_number(item) or 0
    index_episode = current_index + 1 if current_index >= 0 else 0
    episode_number = max(0, int(title_episode or index_episode or 0))
    if episode_number <= 0:
        return None
    return FollowingPlaybackProgressDecision(
        season_number=resolve_progress_season(
            fallback_season_number,
            episode_number,
            fallback_season=fallback_season_number,
        ),
        episode_number=episode_number,
        threshold_reached=playback_progress_threshold_reached(
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
        ),
    )
