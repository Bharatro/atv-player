# ruff: noqa: E501
from pathlib import Path

from atv_player.controllers.following_controller import FollowingController
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
)
from atv_player.following_repository import FollowingRepository
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup
from atv_player.models import PlayItem, VodItem


class FakeSearchService:
    def search(self, query, provider_filter=""):
        del provider_filter
        return [
            MetadataScrapeGroup(
                provider="bangumi",
                provider_label="Bangumi",
                items=[
                    MetadataScrapeCandidate(
                        provider="bangumi",
                        provider_label="Bangumi",
                        provider_id="subject:1",
                        title=query.title,
                        subtitle="动漫",
                        raw={"episodes": [{"sort": 1, "type": 0, "name": "第一话"}]},
                    )
                ],
            )
        ]


class FakeDetailSearchService(FakeSearchService):
    def __init__(self) -> None:
        self.detail_provider_ids: list[str] = []

    def detail_record(self, candidate):
        assert candidate.provider == "tmdb"
        self.detail_provider_ids.append(candidate.provider_id)
        return MetadataRecord(
            provider="tmdb",
            provider_id=candidate.provider_id,
            title="庆余年",
            poster="poster",
            backdrop="backdrop",
            overview="详情简介",
            rating="8.0",
            actors=["张若昀"],
            directors=["孙皓"],
            detail_fields=[
                {
                    "label": "episodes",
                    "value": [
                        {"episode_number": 1, "name": "第一集", "overview": "剧情", "still_url": "still"},
                        {"episode_number": 2, "name": "第二集"},
                    ],
                }
            ],
        )


class FakeUpdateService:
    def __init__(self) -> None:
        self.manual_checks: list[int] = []
        self.due_checks = 0

    def check_record(self, record_id: int):
        self.manual_checks.append(record_id)
        return None

    def check_due_records(self, limit: int = 3):
        del limit
        self.due_checks += 1
        return []


class SavingUpdateService:
    def __init__(self, repo: FollowingRepository) -> None:
        self.repo = repo
        self.manual_checks: list[int] = []

    def check_record(self, record_id: int):
        self.manual_checks.append(record_id)
        snapshot = FollowingDetailSnapshot(
            following_id=record_id,
            overview="刷新后的简介",
            episodes=[FollowingEpisode(episode_number=1, title="刷新分集")],
        )
        self.repo.save_detail_snapshot(record_id, snapshot)
        self.repo.update_check_state(
            record_id,
            latest_episode=1,
            total_episodes=1,
            checked_at=200,
            next_check_after=300,
            has_update=False,
            new_episode_count=0,
            homepage_prompt_pending=False,
            last_error="",
        )
        return None


def test_following_controller_searches_and_adds_candidate(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    groups = controller.search_media("凡人修仙传")
    record = controller.add_candidate(groups[0].items[0])

    assert groups[0].provider == "bangumi"
    assert record.title == "凡人修仙传"
    assert repo.get(record.id) is not None
    assert repo.get_detail_snapshot(record.id).episodes[0].title == "第一话"


def test_following_controller_adds_candidate_with_detail_snapshot(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeDetailSearchService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)
    candidate = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="tv:456",
        title="庆余年",
        subtitle="剧集",
    )

    record = controller.add_candidate(candidate)
    snapshot = repo.get_detail_snapshot(record.id)

    assert record.poster == "poster"
    assert record.backdrop == "backdrop"
    assert record.provider_id == "tv:456:season:1"
    assert record.latest_episode == 2
    assert record.total_episodes == 2
    assert service.detail_provider_ids == ["tv:456:season:1"]
    assert snapshot is not None
    assert snapshot.overview == "详情简介"
    assert snapshot.episodes[0].title == "第一集"
    assert snapshot.cast[0]["name"] == "张若昀"


def test_following_controller_builds_card_and_detail_models(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi"],
            current_episode=127,
            latest_episode=128,
            total_episodes=156,
            has_update=True,
            new_episode_count=1,
        )
    )
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            overview="简介",
            episodes=[FollowingEpisode(episode_number=128, title="新章")],
        ),
    )
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    cards, total = controller.load_page(page=1, size=20, keyword="", only_updates=True)
    detail = controller.load_detail(following_id)

    assert total == 1
    assert cards[0].progress_text == "看到 127 · 最新 128 / 总 156"
    assert cards[0].updated_hint is True
    assert detail.snapshot.overview == "简介"


def test_following_controller_refreshes_empty_detail_on_open(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi"],
        )
    )
    update_service = SavingUpdateService(repo)
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=update_service, now=lambda: 100)

    detail = controller.load_detail(following_id)

    assert update_service.manual_checks == [following_id]
    assert detail.record.latest_episode == 1
    assert detail.snapshot.overview == "刷新后的简介"
    assert detail.snapshot.episodes[0].title == "刷新分集"


def test_following_controller_omits_unknown_episode_counts_from_card(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="player",
            provider_id="player:vod-1",
            current_episode=127,
            latest_episode=0,
            total_episodes=0,
        )
    )
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    cards, _total = controller.load_page(page=1, size=20, keyword="", only_updates=False)

    assert cards[0].progress_text == "看到 127"
    assert "最新 0" not in cards[0].progress_text
    assert "总 0" not in cards[0].progress_text


def test_following_controller_adds_from_player_and_updates_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)
    vod = VodItem(vod_id="vod-1", vod_name="凡人修仙传", vod_pic="poster", dbid=123)
    item = PlayItem(title="第127集", url="u", media_title="凡人修仙传", vod_id="vod-1")

    record = controller.add_from_player(vod=vod, item=item, source_kind="browse", source_key="", position_seconds=321)
    controller.record_playback_progress(record.id, current_episode=128, position_seconds=15)

    loaded = repo.get(record.id)
    assert loaded.current_episode == 128
    assert loaded.position_seconds == 15
    assert loaded.source_bindings[0].vod_id == "vod-1"
