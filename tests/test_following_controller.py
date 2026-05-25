# ruff: noqa: E501
from pathlib import Path

from atv_player.controllers.following_controller import FollowingController
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
)
from atv_player.following_repository import FollowingRepository
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


def test_following_controller_searches_and_adds_candidate(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    groups = controller.search_media("凡人修仙传")
    record = controller.add_candidate(groups[0].items[0])

    assert groups[0].provider == "bangumi"
    assert record.title == "凡人修仙传"
    assert repo.get(record.id) is not None
    assert repo.get_detail_snapshot(record.id).episodes[0].title == "第一话"


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
