from atv_player.following_progress import (
    playback_progress_threshold_reached,
    resolve_following_playback_progress,
)
from atv_player.models import PlayItem


def test_resolve_following_playback_progress_prefers_title_episode_number() -> None:
    item = PlayItem(title="第24集", url="https://media.example/1.m3u8")
    playlist = [
        item,
        PlayItem(title="第25集", url="https://media.example/2.m3u8"),
    ]

    decision = resolve_following_playback_progress(
        item,
        playlist,
        current_index=0,
        fallback_season_number=1,
        position_seconds=30,
        duration_seconds=100,
    )

    assert decision is not None
    assert decision.episode_number == 24
    assert decision.threshold_reached is True


def test_resolve_following_playback_progress_falls_back_to_playlist_index() -> None:
    item = PlayItem(title="上集回顾", url="https://media.example/3.m3u8")
    playlist = [
        PlayItem(title="第1集", url="https://media.example/1.m3u8"),
        PlayItem(title="第2集", url="https://media.example/2.m3u8"),
        item,
    ]

    decision = resolve_following_playback_progress(
        item,
        playlist,
        current_index=2,
        fallback_season_number=1,
        position_seconds=30,
        duration_seconds=100,
    )

    assert decision is not None
    assert decision.episode_number == 3


def test_playback_progress_threshold_reached_uses_twenty_percent_boundary() -> None:
    assert playback_progress_threshold_reached(position_seconds=24, duration_seconds=120) is True
    assert playback_progress_threshold_reached(position_seconds=23, duration_seconds=120) is False
    assert playback_progress_threshold_reached(position_seconds=24, duration_seconds=0) is False
