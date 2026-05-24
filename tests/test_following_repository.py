from pathlib import Path

from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.following_repository import FollowingRepository


def _record(**overrides):
    values = dict(
        id=0,
        title="凡人修仙传",
        original_title="",
        media_kind="anime",
        season_number=1,
        poster="poster",
        backdrop="backdrop",
        rating="8.2",
        provider="bangumi",
        provider_id="subject:123",
        provider_priority=["bangumi", "tmdb", "douban"],
        external_ids={"bangumi": "123", "tmdb": "456"},
        source_bindings=[],
        current_episode=127,
        position_seconds=300,
        watched_latest_episode=True,
        latest_episode=127,
        previous_latest_episode=127,
        total_episodes=156,
        has_update=False,
        new_episode_count=0,
        homepage_prompt_pending=False,
        prompt_snoozed_until=0,
        created_at=100,
        updated_at=100,
        last_played_at=90,
        last_checked_at=80,
        next_check_after=0,
        last_error="",
    )
    values.update(overrides)
    return FollowingRecord(**values)


def test_following_repository_upserts_by_provider_identity(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    first_id = repo.upsert(_record(title="旧标题"))
    second_id = repo.upsert(_record(title="新标题", poster="poster-b", updated_at=200))

    records, total = repo.load_page(page=1, size=20, keyword="", only_updates=False)

    assert first_id == second_id
    assert total == 1
    assert records[0].title == "新标题"
    assert records[0].poster == "poster-b"
    assert records[0].external_ids == {"bangumi": "123", "tmdb": "456"}


def test_following_repository_saves_snapshot_progress_and_prompt_state(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(_record())
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            overview="动画简介",
            cast=[{"name": "韩立", "role": "角色"}],
            crew=[{"name": "导演", "job": "Director"}],
            episodes=[FollowingEpisode(episode_number=128, title="新章", overview="剧情", still="still")],
            posters=["poster"],
            backdrops=["backdrop"],
            refreshed_at=110,
        ),
    )
    repo.update_progress(following_id, current_episode=128, position_seconds=42, last_played_at=120)
    repo.update_check_state(
        following_id,
        latest_episode=128,
        total_episodes=156,
        checked_at=130,
        next_check_after=140,
        has_update=True,
        new_episode_count=1,
        homepage_prompt_pending=True,
        last_error="",
    )

    record = repo.get(following_id)
    snapshot = repo.get_detail_snapshot(following_id)
    prompts = repo.load_homepage_prompt_records(now=131)

    assert record is not None
    assert record.current_episode == 128
    assert record.latest_episode == 128
    assert record.has_update is True
    assert record.homepage_prompt_pending is True
    assert snapshot is not None
    assert snapshot.episodes[0].title == "新章"
    assert [item.id for item in prompts] == [following_id]


def test_following_repository_filters_updates_and_snoozes_prompt(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    updated_id = repo.upsert(
        _record(title="有更新", provider_id="subject:1", has_update=True, homepage_prompt_pending=True)
    )
    repo.upsert(_record(title="无更新", provider_id="subject:2", has_update=False))

    updated, total = repo.load_page(page=1, size=20, keyword="", only_updates=True)
    repo.snooze_prompt(updated_id, until=999)

    assert total == 1
    assert updated[0].title == "有更新"
    assert repo.load_homepage_prompt_records(now=998) == []
