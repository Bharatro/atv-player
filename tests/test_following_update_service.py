from pathlib import Path

from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.following_repository import FollowingRepository
from atv_player.following_update_service import FollowingUpdateService


class FakeMetadataGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failures: set[str] = set()

    def refresh(self, record: FollowingRecord, provider: str):
        self.calls.append((record.title, provider))
        if provider in self.failures:
            raise RuntimeError(f"{provider} failed")
        return (
            record,
            FollowingDetailSnapshot(
                following_id=record.id,
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
