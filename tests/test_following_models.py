from datetime import date

from atv_player.following_models import (
    FollowingCompletionState,
    FollowingEpisode,
    resolve_following_completion_state,
)


def test_resolve_following_completion_state_uses_next_episode_signal() -> None:
    state = resolve_following_completion_state(
        episodes=[FollowingEpisode(episode_number=23, air_date="2026-05-19")],
        next_episode=FollowingEpisode(episode_number=24, air_date="2026-05-26"),
        today=date(2026, 5, 26),
    )

    assert state == FollowingCompletionState.ONGOING


def test_resolve_following_completion_state_uses_future_special_episode() -> None:
    state = resolve_following_completion_state(
        episodes=[
            FollowingEpisode(episode_number=23, air_date="2026-05-19"),
            FollowingEpisode(episode_number=24, air_date="2026-06-02", is_special=True),
        ],
        next_episode=None,
        today=date(2026, 5, 26),
    )

    assert state == FollowingCompletionState.ONGOING


def test_resolve_following_completion_state_defaults_to_completed_without_future_signal() -> None:
    state = resolve_following_completion_state(
        episodes=[FollowingEpisode(episode_number=23, air_date="2026-05-19")],
        next_episode=None,
        today=date(2026, 5, 26),
    )

    assert state == FollowingCompletionState.COMPLETED
