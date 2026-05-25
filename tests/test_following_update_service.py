# ruff: noqa: E501
from dataclasses import replace
from pathlib import Path

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
)
from atv_player.following_repository import FollowingRepository
from atv_player.following_update_service import FollowingUpdateService


class FakeMetadataGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failures: set[str] = set()
        self.responses: dict[str, tuple[FollowingRecord, FollowingDetailSnapshot]] = {}

    def refresh(self, record: FollowingRecord, provider: str):
        self.calls.append((record.title, provider))
        if provider in self.failures:
            raise RuntimeError(f"{provider} failed")
        if provider in self.responses:
            return self.responses[provider]
        return (
            replace(
                record,
                provider_id="subject:1:detail",
                poster="poster",
                backdrop="backdrop",
                rating="8.0",
                latest_episode=2,
                total_episodes=2,
            ),
            FollowingDetailSnapshot(
                following_id=record.id,
                overview="简介",
                episodes=[
                    FollowingEpisode(episode_number=1, title="第一集"),
                    FollowingEpisode(episode_number=2, title="第二集"),
                ],
                refreshed_at=200,
            ),
        )


def _record(**overrides):
    values = dict(
        id=0,
        title="凡人修仙传",
        media_kind="anime",
        provider="bangumi",
        provider_id="subject:1",
        provider_priority=["bangumi", "tmdb", "douban"],
        external_ids={"bangumi": "1"},
        latest_episode=1,
        previous_latest_episode=1,
        total_episodes=1,
        current_season_number=1,
        current_episode=1,
        watched_latest_episode=True,
        next_check_after=0,
        created_at=1,
        updated_at=1,
    )
    values.update(overrides)
    return FollowingRecord(**values)


def test_update_service_sets_homepage_prompt_when_caught_up(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record())
    gateway = FakeMetadataGateway()
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 200)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert results[0].has_update is True
    assert record is not None
    assert record.latest_episode == 2
    assert record.has_update is True
    assert record.homepage_prompt_pending is True
    assert record.poster == "poster"
    assert record.provider_id == "subject:1:detail"
    assert repo.get_detail_snapshot(record_id).overview == "简介"


def test_update_service_does_not_prompt_when_user_is_behind(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record(current_episode=0, watched_latest_episode=False))
    service = FollowingUpdateService(repo, metadata_gateway=FakeMetadataGateway(), now=lambda: 200)

    service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert record is not None
    assert record.has_update is True
    assert record.homepage_prompt_pending is False


def test_update_service_falls_back_to_next_provider_and_keeps_errors(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record())
    gateway = FakeMetadataGateway()
    gateway.failures.add("bangumi")
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 200)

    service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert gateway.calls[:2] == [("凡人修仙传", "bangumi"), ("凡人修仙传", "tmdb")]
    assert record is not None
    assert record.last_error == ""
    assert record.latest_episode == 2


def test_update_service_falls_back_to_bangumi_after_tmdb_failure_and_clears_stale_update(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        _record(
            title="盗妖行",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:315088:season:1",
            provider_priority=["tmdb", "douban", "bangumi"],
            external_ids={"tmdb": "315088"},
            current_episode=29,
            latest_episode=60,
            previous_latest_episode=29,
            total_episodes=60,
            has_update=True,
            new_episode_count=31,
            watched_latest_episode=True,
        )
    )
    gateway = FakeMetadataGateway()
    gateway.failures.add("tmdb")
    gateway.failures.add("douban")
    gateway.responses["bangumi"] = (
        _record(
            id=record_id,
            title="盗妖行",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:315088",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "315088"},
            current_episode=29,
            latest_episode=29,
            total_episodes=60,
        ),
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[
                FollowingEpisode(
                    episode_number=episode_number,
                    air_date="2026-05-21" if episode_number <= 29 else "2026-05-26",
                )
                for episode_number in range(1, 61)
            ],
            refreshed_at=1779638400,
        ),
    )
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 1779638400)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert gateway.calls[:3] == [("盗妖行", "tmdb"), ("盗妖行", "douban"), ("盗妖行", "bangumi")]
    assert results[0].latest_episode == 29
    assert results[0].has_update is False
    assert record is not None
    assert record.provider == "bangumi"
    assert record.latest_episode == 29
    assert record.total_episodes == 60
    assert record.has_update is False
    assert record.new_episode_count == 0
    assert record.homepage_prompt_pending is False


def test_update_service_prefers_tmdb_first_when_tmdb_id_exists(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        _record(
            title="名侦探柯南",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "1", "tmdb": "30983"},
            current_episode=1200,
            latest_episode=1200,
            previous_latest_episode=1200,
            total_episodes=1200,
            watched_latest_episode=True,
        )
    )
    gateway = FakeMetadataGateway()
    gateway.responses["tmdb"] = (
        _record(
            id=record_id,
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983:season:1",
            provider_priority=["tmdb", "bangumi", "douban"],
            external_ids={"tmdb": "30983"},
            latest_episode=1201,
            total_episodes=1201,
        ),
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[FollowingEpisode(episode_number=1201, air_date="2026-05-09")],
            refreshed_at=1779638400,
        ),
    )
    gateway.responses["bangumi"] = (
        _record(
            id=record_id,
            title="名侦探柯南",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "1"},
            latest_episode=1200,
            total_episodes=1200,
        ),
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[FollowingEpisode(episode_number=1200, air_date="2026-05-02")],
            refreshed_at=1779638400,
        ),
    )
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 1779638400)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert gateway.calls[0] == ("名侦探柯南", "tmdb")
    assert results[0].latest_episode == 1201
    assert record is not None
    assert record.latest_episode == 1201


def test_update_service_prefers_tmdb_record_latest_over_season_local_episode_numbers(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        _record(
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983:season:1",
            provider_priority=["tmdb", "bangumi", "douban"],
            external_ids={"tmdb": "30983"},
            current_episode=1200,
            latest_episode=1200,
            previous_latest_episode=1200,
            total_episodes=1200,
            watched_latest_episode=True,
        )
    )
    gateway = FakeMetadataGateway()
    gateway.responses["tmdb"] = (
        _record(
            id=record_id,
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983:season:1",
            provider_priority=["tmdb", "bangumi", "douban"],
            external_ids={"tmdb": "30983"},
            latest_episode=1201,
            total_episodes=1201,
        ),
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[
                FollowingEpisode(episode_number=1, air_date="2026-05-02"),
                FollowingEpisode(episode_number=2, air_date="2026-05-09"),
            ],
            refreshed_at=1779638400,
        ),
    )
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 1779638400)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert results[0].latest_episode == 1201
    assert results[0].has_update is True
    assert record is not None
    assert record.latest_episode == 1201
    assert record.new_episode_count == 1
    assert record.homepage_prompt_pending is True


def test_update_service_detects_cross_season_tmdb_updates(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        _record(
            title="黑袍纠察队",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:76479",
            provider_priority=["tmdb", "douban", "bangumi"],
            external_ids={"tmdb": "76479"},
            season_number=4,
            current_season_number=4,
            current_episode=8,
            latest_episode=8,
            previous_latest_episode=8,
            total_episodes=8,
            watched_latest_episode=True,
        )
    )
    gateway = FakeMetadataGateway()
    gateway.responses["tmdb"] = (
        _record(
            id=record_id,
            title="黑袍纠察队",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:76479",
            provider_priority=["tmdb", "douban", "bangumi"],
            external_ids={"tmdb": "76479"},
            season_number=5,
            latest_episode=1,
            total_episodes=8,
        ),
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[FollowingEpisode(episode_number=1, season_number=5, air_date="2026-05-09")],
            refreshed_at=1779638400,
        ),
    )
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 1779638400)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert results[0].latest_episode == 1
    assert results[0].has_update is True
    assert record is not None
    assert record.season_number == 5
    assert record.has_update is True
    assert record.new_episode_count == 1
    assert record.homepage_prompt_pending is True


def test_update_service_tmdb_check_keeps_existing_metadata_identity(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        _record(
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983:season:1",
            provider_priority=["tmdb", "bangumi", "douban"],
            external_ids={"tmdb": "30983"},
            poster="old-poster",
            backdrop="old-backdrop",
            rating="9.0",
            current_episode=1200,
            latest_episode=1200,
            previous_latest_episode=1200,
            total_episodes=1200,
            watched_latest_episode=True,
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            overview="旧简介",
            episodes=[FollowingEpisode(episode_number=1, title="旧分集")],
        ),
    )
    gateway = FakeMetadataGateway()
    gateway.responses["tmdb"] = (
        FollowingRecord(
            id=0,
            title="",
            latest_episode=1201,
            previous_latest_episode=1201,
            total_episodes=1201,
        ),
        FollowingDetailSnapshot(),
    )
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 1779638400)

    service.check_record(record_id)

    record = repo.get(record_id)
    snapshot = repo.get_detail_snapshot(record_id)
    assert record is not None
    assert record.provider == "tmdb"
    assert record.provider_id == "tv:30983"
    assert record.external_ids == {"tmdb": "30983"}
    assert record.poster == "old-poster"
    assert record.backdrop == "old-backdrop"
    assert record.rating == "9.0"
    assert record.latest_episode == 1201
    assert record.total_episodes == 1201
    assert snapshot is not None
    assert snapshot.overview == "旧简介"
    assert snapshot.episodes[0].title == "旧分集"
