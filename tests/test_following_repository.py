# ruff: noqa: E501
from pathlib import Path

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingMetadataBundle,
    FollowingMetadataSourceSnapshot,
    FollowingPlaybackPlatformEntry,
    FollowingRatingEntry,
    FollowingRecord,
    FollowingSeason,
)
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
        current_season_number=1,
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
            seasons=[FollowingSeason(season_number=1, title="第一季", episode_count=156)],
            episodes=[FollowingEpisode(episode_number=128, title="新章", overview="剧情", still="still")],
            posters=["poster"],
            backdrops=["backdrop"],
            refreshed_at=110,
        ),
    )
    repo.update_progress(
        following_id,
        current_season_number=1,
        current_episode=128,
        position_seconds=42,
        last_played_at=120,
    )
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
    assert snapshot.seasons[0].title == "第一季"
    assert snapshot.episodes[0].title == "新章"
    assert [item.id for item in prompts] == [following_id]


def test_following_repository_persists_metadata_bundle(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(_record(provider="tmdb", provider_id="tv:272432", external_ids={"tmdb": "272432"}))
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            overview="TMDB简介",
            metadata_bundle=FollowingMetadataBundle(
                merged_snapshot=FollowingMetadataSourceSnapshot(
                    source_key="merged",
                    provider="merged",
                    provider_label="合并",
                    overview="TMDB简介",
                    ratings=[FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1")],
                    playback_platforms=[
                        FollowingPlaybackPlatformEntry(
                            provider="iqiyi",
                            label="爱奇艺",
                            url="https://www.iqiyi.com/a_1.html",
                            metric_label="热度",
                            metric_value="9000",
                        )
                    ],
                ),
                source_snapshots={
                    "merged": FollowingMetadataSourceSnapshot(
                        source_key="merged",
                        provider="merged",
                        provider_label="合并",
                        overview="TMDB简介",
                    ),
                    "tmdb": FollowingMetadataSourceSnapshot(
                        source_key="tmdb",
                        provider="tmdb",
                        provider_label="TMDB",
                        provider_id="tv:272432:season:1",
                        overview="TMDB简介",
                        ratings=[FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1")],
                    ),
                },
                available_source_keys=["merged", "tmdb"],
                default_source_key="merged",
            ),
            refreshed_at=110,
        ),
    )

    reopened = FollowingRepository(tmp_path / "app.db")
    loaded = reopened.get_detail_snapshot(following_id)

    assert loaded is not None
    assert loaded.metadata_bundle is not None
    assert loaded.metadata_bundle.available_source_keys == ["merged", "tmdb"]
    assert loaded.metadata_bundle.source_snapshots["tmdb"].provider_id == "tv:272432:season:1"
    assert loaded.metadata_bundle.merged_snapshot.ratings[0].value == "8.1"
    assert loaded.metadata_bundle.merged_snapshot.playback_platforms[0].label == "爱奇艺"
    assert loaded.metadata_bundle.merged_snapshot.playback_platforms[0].metric_label == "热度"
    assert loaded.metadata_bundle.merged_snapshot.playback_platforms[0].metric_value == "9000"


def test_following_repository_update_progress_clears_update_when_latest_watched(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        _record(
            current_episode=23,
            latest_episode=24,
            has_update=True,
            new_episode_count=1,
            homepage_prompt_pending=True,
            watched_latest_episode=False,
        )
    )

    repo.update_progress(
        following_id,
        current_season_number=1,
        current_episode=24,
        position_seconds=0,
        last_played_at=200,
    )

    record = repo.get(following_id)
    assert record is not None
    assert record.watched_latest_episode is True
    assert record.has_update is False
    assert record.new_episode_count == 0
    assert record.homepage_prompt_pending is False


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


def test_following_repository_normalizes_tmdb_identity_and_migrates_existing_season_key(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    legacy_id = repo.upsert(
        _record(
            title="黑袍纠察队",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:76479:season:1",
            season_number=0,
            external_ids={"tmdb": "76479"},
        )
    )

    reopened = FollowingRepository(tmp_path / "app.db")
    loaded = reopened.get(legacy_id)
    by_identity = reopened.get_by_identity("tmdb", "tv:76479:season:5")

    assert loaded is not None
    assert loaded.provider_id == "tv:76479"
    assert loaded.season_number == 1
    assert by_identity is not None
    assert by_identity.id == legacy_id


def test_following_repository_persists_current_season_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        _record(
            provider="tmdb",
            provider_id="tv:76479",
            season_number=5,
            current_season_number=4,
            current_episode=8,
            latest_episode=8,
            total_episodes=8,
            watched_latest_episode=False,
            has_update=True,
            new_episode_count=1,
            homepage_prompt_pending=True,
        )
    )

    loaded = repo.get(following_id)
    assert loaded is not None
    assert loaded.current_season_number == 4
    assert loaded.watched_latest_episode is False

    repo.update_progress(
        following_id,
        current_season_number=5,
        current_episode=8,
        position_seconds=18,
        last_played_at=300,
    )

    loaded = repo.get(following_id)
    assert loaded is not None
    assert loaded.current_season_number == 5
    assert loaded.current_episode == 8
    assert loaded.position_seconds == 18
    assert loaded.watched_latest_episode is True
    assert loaded.has_update is False
    assert loaded.new_episode_count == 0
    assert loaded.homepage_prompt_pending is False


def test_following_repository_load_recent_recommendation_candidates_prefers_recent_activity(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    repo.upsert(
        _record(
            provider="tmdb",
            provider_id="tv:1",
            media_kind="live_action",
            external_ids={"tmdb": "1"},
            has_update=False,
            updated_at=100,
            last_played_at=50,
        )
    )
    repo.upsert(
        _record(
            provider="tmdb",
            provider_id="tv:2",
            media_kind="live_action",
            external_ids={"tmdb": "2"},
            has_update=True,
            updated_at=300,
            last_played_at=200,
        )
    )

    rows = repo.load_recent_recommendation_candidates(limit=1)

    assert [row.provider_id for row in rows] == ["tv:2"]
