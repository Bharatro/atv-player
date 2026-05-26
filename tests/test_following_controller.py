# ruff: noqa: E501
from pathlib import Path

from atv_player.controllers.following_controller import FollowingController
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingMetadataBundle,
    FollowingMetadataSourceSnapshot,
    FollowingPlaybackPlatformEntry,
    FollowingRecord,
)
from atv_player.following_repository import FollowingRepository
from atv_player.favorite_tmdb_bindings import FavoriteTMDBBindingRepository
from atv_player.metadata.discovery import DiscoveryItem, DiscoveryResult
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup
from atv_player.models import PlaybackDetailField, PlayItem, VodItem


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


class FakeFollowingMetadataRefreshService:
    def __init__(self) -> None:
        self.detail_provider_ids: list[tuple[str, str]] = []

    def search(self, query, provider_filter=""):
        assert query.title == "仙逆"
        if provider_filter:
            return []
        return [
            MetadataScrapeGroup(
                provider="bangumi",
                provider_label="Bangumi",
                items=[
                    MetadataScrapeCandidate(
                        provider="bangumi",
                        provider_label="Bangumi",
                        provider_id="subject:1",
                        title="仙逆",
                        subtitle="动漫",
                    )
                ],
            ),
            MetadataScrapeGroup(
                provider="tmdb",
                provider_label="TMDB",
                items=[
                    MetadataScrapeCandidate(
                        provider="tmdb",
                        provider_label="TMDB",
                        provider_id="tv:236534:season:1",
                        title="仙逆",
                        subtitle="剧集",
                    )
                ],
            ),
        ]

    def detail_record(self, candidate):
        self.detail_provider_ids.append((candidate.provider, candidate.provider_id))
        if candidate.provider == "bangumi":
            return MetadataRecord(
                provider="bangumi",
                provider_id="subject:1",
                title="仙逆",
                overview="Bangumi简介",
                rating="8.4",
                aliases=["仙逆动画"],
            )
        return MetadataRecord(
            provider="tmdb",
            provider_id="tv:236534:season:1",
            title="仙逆",
            poster="tmdb-poster",
            backdrop="tmdb-backdrop",
            overview="TMDB简介",
            rating="7.6",
            tmdb_id="236534",
            actors=["史泽鲲"],
            directors=["导演"],
            detail_fields=[
                {
                    "label": "episodes",
                    "value": [
                        {
                            "episode_number": 1,
                            "name": "TMDB第1集",
                            "overview": "TMDB剧情",
                            "still_url": "tmdb-still",
                        }
                    ],
                }
            ],
        )


class FakeTMDBIdRefreshService:
    def __init__(self) -> None:
        self.search_calls = 0
        self.full_detail_provider_ids: list[str] = []

    def search(self, query, provider_filter=""):
        del query, provider_filter
        self.search_calls += 1
        return []

    def detail_record_full(self, candidate):
        self.full_detail_provider_ids.append(candidate.provider_id)
        return MetadataRecord(
            provider="tmdb",
            provider_id=candidate.provider_id,
            title="低智商犯罪",
            poster="tmdb-poster",
            backdrop="tmdb-backdrop",
            overview="TMDB简介",
            tmdb_id="272432",
            actors=["王骁", "田曦薇"],
            cast_details=[
                {"name": "王骁", "role": "Zhang Yi'ang", "avatar": "/wang.jpg"},
                {"name": "田曦薇", "role": "Li Qian", "avatar": "/tian.jpg"},
            ],
        )


class FakeTMDBUrlSearchService:
    def __init__(self) -> None:
        self.detail_provider_ids: list[str] = []

    def detail_record(self, candidate):
        self.detail_provider_ids.append(candidate.provider_id)
        return MetadataRecord(
            provider="tmdb",
            provider_id=candidate.provider_id,
            title="名侦探柯南",
            year="1996",
            tmdb_id="30983",
            overview="高中生侦探化身小学生继续破案。",
        )


class FakeTMDBFollowingSearchService:
    def __init__(self) -> None:
        self.search_following_calls: list[tuple[str, str, str]] = []

    def search_following(self, query, provider_filter=""):
        self.search_following_calls.append((query.title, provider_filter, str(query.year or "")))
        return [
            MetadataScrapeGroup(
                provider="tmdb",
                provider_label="TMDB",
                items=[
                    MetadataScrapeCandidate(
                        provider="tmdb",
                        provider_label="TMDB",
                        provider_id="movie:12",
                        title="Movie First",
                        year="2024",
                        subtitle="电影",
                    ),
                    MetadataScrapeCandidate(
                        provider="tmdb",
                        provider_label="TMDB",
                        provider_id="tv:34:season:1",
                        title="TV Second",
                        year="2025",
                        subtitle="剧集",
                    ),
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


def test_following_controller_adds_candidate_with_manual_current_episode(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    record = controller.add_candidate(controller.search_media("凡人修仙传")[0].items[0], current_episode=1)

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.current_episode == 1
    assert loaded.watched_latest_episode is True
    assert loaded.has_update is False


def test_following_controller_preserves_existing_progress_when_adding_duplicate_candidate(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    candidate = controller.search_media("凡人修仙传")[0].items[0]
    first = controller.add_candidate(candidate)
    controller.record_playback_progress(first.id, current_episode=1, position_seconds=42)

    second = controller.add_candidate(candidate)

    loaded = repo.get(first.id)
    assert second.id == first.id
    assert loaded is not None
    assert loaded.current_episode == 1
    assert loaded.position_seconds == 42
    assert loaded.watched_latest_episode is True
    assert loaded.has_update is False


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
    assert record.provider_id == "tv:456"
    assert record.season_number == 1
    assert record.latest_episode == 2
    assert record.total_episodes == 2
    assert service.detail_provider_ids == ["tv:456:season:1"]
    assert snapshot is not None
    assert snapshot.overview == "详情简介"
    assert snapshot.episodes[0].title == "第一集"
    assert snapshot.cast[0]["name"] == "张若昀"


def test_following_controller_record_playback_progress_ignores_older_episode_reports(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "1"},
            current_season_number=1,
            current_episode=12,
            position_seconds=50,
            latest_episode=24,
            previous_latest_episode=24,
            total_episodes=24,
            created_at=1,
            updated_at=1,
        )
    )
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), now=lambda: 100)

    controller.record_playback_progress(
        following_id,
        current_season_number=1,
        current_episode=10,
        position_seconds=80,
    )

    loaded = repo.get(following_id)
    assert loaded is not None
    assert loaded.current_episode == 12
    assert loaded.position_seconds == 50


def test_following_controller_hydrates_tmdb_url_candidate_for_search_results(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeTMDBUrlSearchService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    groups = controller.search_media("https://www.themoviedb.org/tv/30983-case-closed")

    assert len(groups) == 1
    assert groups[0].provider == "tmdb"
    assert service.detail_provider_ids == ["tv:30983:season:1"]
    candidate = groups[0].items[0]
    assert candidate.provider_id == "tv:30983:season:1"
    assert candidate.title == "名侦探柯南"
    assert candidate.year == "1996"
    assert candidate.subtitle == "剧集"


def test_following_controller_load_page_uses_completed_text_for_idle_record(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "1"},
            current_season_number=1,
            current_episode=24,
            latest_episode=24,
            previous_latest_episode=24,
            total_episodes=24,
            watched_latest_episode=True,
            created_at=1,
            updated_at=1,
        )
    )
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            episodes=[FollowingEpisode(episode_number=24, air_date="2026-05-19")],
            refreshed_at=1779638400,
        ),
    )
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), now=lambda: 1779638400)

    cards, _total = controller.load_page(page=1, size=20, keyword="", only_updates=False)

    assert cards[0].update_text == "已完结"


def test_following_controller_keyword_search_uses_tmdb_only_and_sorts_tv_before_movie(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeTMDBFollowingSearchService()
    controller = FollowingController(repo, metadata_search_service=service)

    groups = controller.search_media("星际")

    assert groups[0].provider == "tmdb"
    assert [item.provider_id for item in groups[0].items] == ["tv:34:season:1", "movie:12"]
    assert service.search_following_calls == [("星际", "tmdb", "")]


def test_following_controller_keyword_search_forwards_year_to_tmdb_search(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeTMDBFollowingSearchService()
    controller = FollowingController(repo, metadata_search_service=service)

    controller.search_media("星际", year="2024")

    assert service.search_following_calls == [("星际", "tmdb", "2024")]


def test_following_controller_load_discovery_search_forwards_year_filter(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeTMDBFollowingSearchService()
    controller = FollowingController(
        repo,
        metadata_search_service=service,
        discovery_service=type("DiscoveryService", (), {})(),
    )

    controller.load_discovery_tab("search", query="星际", filters={"year": "2024"})

    assert service.search_following_calls == [("星际", "tmdb", "2024")]


def test_following_controller_tmdb_url_search_ignores_year_parameter(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    service = FakeTMDBUrlSearchService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    groups = controller.search_media("https://www.themoviedb.org/tv/30983-case-closed", year="2024")

    assert len(groups) == 1
    assert service.detail_provider_ids == ["tv:30983:season:1"]


def test_following_controller_non_tmdb_url_passthrough_still_works(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService())

    groups = controller.search_media("https://bgm.tv/subject/123")

    assert len(groups) == 1
    assert groups[0].provider == "bangumi"
    assert groups[0].items[0].provider_id == "subject:123"


def test_following_controller_douban_url_passthrough_still_works(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService())

    groups = controller.search_media("https://movie.douban.com/subject/1292052/")

    assert len(groups) == 1
    assert groups[0].provider in {"official_douban", "local_douban", "douban"}
    assert groups[0].items[0].provider_id == "1292052"


def test_following_controller_builds_card_and_detail_models(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            season_number=5,
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi"],
            current_season_number=2,
            current_episode=3,
            latest_episode=8,
            total_episodes=8,
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
    assert cards[0].progress_text == "看到 S2E3 · 最新 S5E8 / 总 8"
    assert cards[0].updated_hint is True
    assert detail.snapshot.overview == "简介"


def test_following_controller_loads_recommendations_and_falls_back_to_trending_when_empty(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    repo.upsert(
        FollowingRecord(
            id=0,
            title="黑袍纠察队",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:76479",
            external_ids={"tmdb": "76479"},
            has_update=True,
            updated_at=100,
        )
    )

    class DiscoveryService:
        def recommend(self, **_kwargs):
            return DiscoveryResult(items=[], total=0, source_label="推荐", fallback_reason="")

        def trending(self, query):
            assert query.kind == "trending"
            return DiscoveryResult(
                items=[
                    DiscoveryItem(
                        provider="tmdb",
                        provider_id="tv:100",
                        tmdb_id="100",
                        media_type="tv",
                        title="Gen V",
                        source_label="本周趋势",
                    )
                ],
                total=1,
                source_label="本周趋势",
            )

    controller = FollowingController(
        repo,
        metadata_search_service=FakeSearchService(),
        discovery_service=DiscoveryService(),
        favorite_tmdb_binding_repository=FavoriteTMDBBindingRepository(tmp_path / "app.db"),
    )

    result = controller.load_discovery_tab("recommendation")

    assert result.items[0].provider_id == "tv:100"
    assert result.fallback_reason == "recommendation-empty"


def test_following_controller_recommendation_seeds_include_recent_favorite_tmdb_bindings(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    favorite_bindings = FavoriteTMDBBindingRepository(tmp_path / "app.db")
    favorite_bindings.save(
        source_kind="browse",
        source_key="",
        vod_id="detail-2",
        provider_id="movie:157336",
        tmdb_id="157336",
        media_type="movie",
        title="星际穿越",
        year="2014",
        updated_at=200,
    )
    captured = {}

    class DiscoveryService:
        def recommend(self, **kwargs):
            captured.update(kwargs)
            return DiscoveryResult(items=[], total=0, source_label="推荐", fallback_reason="")

        def trending(self, query):
            return DiscoveryResult(items=[], total=0, source_label="本周趋势", fallback_reason="")

    controller = FollowingController(
        repo,
        metadata_search_service=FakeSearchService(),
        discovery_service=DiscoveryService(),
        favorite_tmdb_binding_repository=favorite_bindings,
    )

    controller.load_discovery_tab("recommendation")

    assert [seed.provider_id for seed in captured["seeds"]] == ["movie:157336"]
    assert captured["seeds"][0].seed_source == "favorite"


def test_following_controller_add_candidate_accepts_discovery_item(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")

    class SearchService:
        def detail_record(self, candidate):
            assert candidate.provider == "tmdb"
            assert candidate.provider_id == "tv:272432:season:1"
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:272432:season:1",
                title="低智商犯罪",
                year="2026",
                tmdb_id="272432",
                overview="剧集简介",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集"}],
                    }
                ],
            )

    controller = FollowingController(
        repo,
        metadata_search_service=SearchService(),
    )

    record = controller.add_candidate(
        DiscoveryItem(
            provider="tmdb",
            provider_id="tv:272432",
            tmdb_id="272432",
            media_type="tv",
            title="低智商犯罪",
            year="2026",
            poster="https://image.tmdb.org/t/p/original/poster.jpg",
            backdrop="https://image.tmdb.org/t/p/w1280/backdrop.jpg",
            rating="8.1",
            overview="搜索简介",
            source_label="搜索",
        )
    )

    assert record.title == "低智商犯罪"
    assert record.provider == "tmdb"
    assert record.provider_id == "tv:272432"


def test_following_controller_records_season_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="黑袍纠察队",
            media_kind="live_action",
            season_number=5,
            provider="tmdb",
            provider_id="tv:76479",
            provider_priority=["tmdb"],
            current_season_number=4,
            current_episode=8,
            latest_episode=8,
            total_episodes=8,
            has_update=True,
            new_episode_count=1,
            homepage_prompt_pending=True,
        )
    )
    controller = FollowingController(
        repo,
        metadata_search_service=FakeSearchService(),
        update_service=FakeUpdateService(),
        now=lambda: 100,
    )

    controller.record_playback_progress(
        following_id,
        current_season_number=5,
        current_episode=8,
        position_seconds=15,
    )

    loaded = repo.get(following_id)
    assert loaded is not None
    assert loaded.current_season_number == 5
    assert loaded.current_episode == 8
    assert loaded.position_seconds == 15
    assert loaded.watched_latest_episode is True
    assert loaded.has_update is False
    assert loaded.new_episode_count == 0


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

    assert cards[0].progress_text == "看到 S1E127"
    assert "最新 0" not in cards[0].progress_text
    assert "总 0" not in cards[0].progress_text


def test_following_controller_adds_from_player_and_updates_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)
    vod = VodItem(
        vod_id="vod-1",
        vod_name="凡人修仙传",
        vod_pic="poster",
        vod_content="简介",
        vod_actor="韩立, 南宫婉",
        vod_director="王裕仁",
        dbid=123,
        detail_fields=[PlaybackDetailField("TMDB ID", "456")],
    )
    playlist = [
        PlayItem(title="第127集", url="u", media_title="凡人修仙传", vod_id="vod-1", episode_display_title="风起"),
        PlayItem(title="第128集", url="u2", media_title="凡人修仙传", vod_id="vod-1", episode_display_title="新章"),
    ]
    item = playlist[0]

    record = controller.add_from_player(
        vod=vod,
        item=item,
        source_kind="browse",
        source_key="",
        position_seconds=321,
        playlist=playlist,
    )
    controller.record_playback_progress(record.id, current_episode=128, position_seconds=15)

    loaded = repo.get(record.id)
    snapshot = repo.get_detail_snapshot(record.id)
    assert loaded.current_episode == 128
    assert loaded.position_seconds == 15
    assert loaded.total_episodes == 2
    assert loaded.external_ids == {"douban": "123", "tmdb": "456"}
    assert loaded.source_bindings[0].vod_id == "vod-1"
    assert snapshot is not None
    assert snapshot.overview == "简介"
    assert snapshot.cast[0]["name"] == "韩立"
    assert snapshot.crew[0]["name"] == "王裕仁"
    assert snapshot.episodes[0].title == "风起"


def test_following_controller_uses_playlist_count_for_latest_and_metadata_count_for_total(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)
    metadata_episodes = [
        {
            "episode_number": episode_number,
            "name": f"TMDB {episode_number}",
            "overview": f"剧情 {episode_number}",
        }
        for episode_number in range(1, 93)
    ]
    vod = VodItem(
        vod_id="vod-1",
        vod_name="牧神记",
        detail_fields=[
            PlaybackDetailField("TMDB ID", "236534"),
            PlaybackDetailField("episodes", repr(metadata_episodes)),
        ],
    )
    playlist = [
        PlayItem(title="第26集", url=f"u{index}", media_title="牧神记", vod_id="vod-1")
        for index in range(84)
    ]
    for index, item in enumerate(playlist):
        item.index = index

    record = controller.add_from_player(
        vod=vod,
        item=playlist[-1],
        source_kind="browse",
        source_key="",
        position_seconds=0,
        playlist=playlist,
    )

    loaded = repo.get(record.id)
    snapshot = repo.get_detail_snapshot(record.id)
    assert loaded is not None
    assert loaded.current_episode == 84
    assert loaded.latest_episode == 84
    assert loaded.total_episodes == 92
    assert loaded.external_ids["tmdb"] == "236534"
    assert snapshot is not None
    assert len(snapshot.episodes) == 92
    assert snapshot.episodes[-1].title == "TMDB 92"


def test_following_controller_refreshes_metadata_with_tmdb_details_for_bangumi_following(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="仙逆",
            media_kind="anime",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi", "tmdb", "douban"],
            external_ids={"bangumi": "1"},
            rating="8.4",
            latest_episode=84,
            total_episodes=92,
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[FollowingEpisode(episode_number=1, title="Bangumi第1集")],
        ),
    )
    service = FakeFollowingMetadataRefreshService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    refreshed = controller.refresh_metadata(record_id)

    loaded = repo.get(record_id)
    snapshot = repo.get_detail_snapshot(record_id)
    assert service.detail_provider_ids == [
        ("tmdb", "tv:236534:season:1"),
        ("bangumi", "subject:1"),
    ]
    assert loaded is not None
    assert loaded.provider == "tmdb"
    assert loaded.provider_id == "tv:236534"
    assert loaded.rating == "7.6"
    assert loaded.poster == "tmdb-poster"
    assert loaded.backdrop == "tmdb-backdrop"
    assert loaded.latest_episode == 84
    assert loaded.total_episodes == 92
    assert refreshed.snapshot.overview == "TMDB简介"
    assert refreshed.snapshot.episodes[0].title == "TMDB第1集"
    assert snapshot is not None
    assert snapshot.episodes[0].overview == "TMDB剧情"
    assert snapshot.episodes[0].still == "tmdb-still"
    assert snapshot.cast[0]["name"] == "史泽鲲"


def test_following_controller_refreshes_live_action_avatars_from_existing_tmdb_id(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="低智商犯罪",
            media_kind="live_action",
            season_number=1,
            provider="player",
            provider_id="player:source:vod-1",
            external_ids={"tmdb": "272432"},
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            overview="原简介",
            cast=[{"name": "王骁"}, {"name": "田曦薇"}],
            episodes=[FollowingEpisode(episode_number=1, title="第一集", still="old-still")],
        ),
    )
    service = FakeTMDBIdRefreshService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    refreshed = controller.refresh_metadata(record_id)

    snapshot = repo.get_detail_snapshot(record_id)
    assert service.search_calls == 1
    assert service.full_detail_provider_ids == ["tv:272432:season:1"]
    assert refreshed.snapshot.cast[0]["avatar"] == "/wang.jpg"
    assert snapshot is not None
    assert snapshot.cast[1]["avatar"] == "/tian.jpg"
    assert snapshot.episodes[0].still == "old-still"


def test_following_controller_refresh_metadata_rebuilds_existing_metadata_bundle_platforms(tmp_path: Path) -> None:
    class SearchService:
        def search(self, query, provider_filter=""):
            assert query.title == "蜜语纪"
            if provider_filter != "tencent":
                return []
            return [
                MetadataScrapeGroup(
                    provider="tencent",
                    provider_label="腾讯",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tencent",
                            provider_label="腾讯",
                            provider_id="https://v.qq.com/x/cover/mzc002006dzzunf/h4102lz1osw.html",
                            title="蜜语纪",
                            year="2026",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            if candidate.provider == "tencent":
                return MetadataRecord(
                    provider="tencent",
                    provider_id=candidate.provider_id,
                    title="蜜语纪",
                    year="2026",
                    detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
                )
            return self.detail_record_full(candidate)

        def detail_record_full(self, candidate):
            assert candidate.provider == "tmdb"
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:281231:season:1",
                title="蜜语纪",
                year="2026",
                tmdb_id="281231",
                overview="TMDB简介",
                detail_fields=[
                    {
                        "label": "watch_providers",
                        "value": [
                            {
                                "provider": "iqiyi",
                                "label": "爱奇艺",
                                "url": "https://www.iqiyi.com/a_1euk1nkfz9l.html",
                            }
                        ],
                    },
                    {"label": "episodes", "value": [{"episode_number": 38, "name": "第38集"}]},
                ],
            )

    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="蜜语纪",
            media_kind="live_action",
            season_number=1,
            provider="tmdb",
            provider_id="tv:281231",
            external_ids={"tmdb": "281231"},
        )
    )
    stale_bundle = FollowingMetadataBundle(
        merged_snapshot=FollowingMetadataSourceSnapshot(
            source_key="merged",
            provider="merged",
            provider_label="合并",
            playback_platforms=[
                FollowingPlaybackPlatformEntry(
                    provider="iqiyi",
                    label="爱奇艺",
                    url="https://www.iqiyi.com/a_1euk1nkfz9l.html",
                )
            ],
        ),
        source_snapshots={
            "merged": FollowingMetadataSourceSnapshot(
                source_key="merged",
                provider="merged",
                provider_label="合并",
            )
        },
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            overview="旧简介",
            metadata_bundle=stale_bundle,
            episodes=[FollowingEpisode(episode_number=1, title="旧第1集")],
        ),
    )
    controller = FollowingController(repo, metadata_search_service=SearchService(), now=lambda: 100)

    refreshed = controller.refresh_metadata(record_id)

    platforms = refreshed.snapshot.metadata_bundle.merged_snapshot.playback_platforms
    assert [(item.provider, item.url) for item in platforms] == [
        ("iqiyi", "https://www.iqiyi.com/a_1euk1nkfz9l.html"),
        ("tencent", "https://v.qq.com/x/cover/mzc002006dzzunf/h4102lz1osw.html"),
    ]


def test_following_controller_refresh_metadata_keeps_existing_episode_entries_when_refresh_returns_subset(
    tmp_path: Path,
) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="低智商犯罪",
            media_kind="live_action",
            season_number=1,
            provider="player",
            provider_id="player:source:vod-1",
            external_ids={"tmdb": "272432"},
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            episodes=[
                FollowingEpisode(episode_number=1, season_number=1, title="第一集", still="old-1"),
                FollowingEpisode(episode_number=2, season_number=1, title="第二集", still="old-2"),
                FollowingEpisode(episode_number=3, season_number=1, title="第三集", still="old-3"),
            ],
        ),
    )

    class PartialEpisodeRefreshService(FakeTMDBIdRefreshService):
        def detail_record_full(self, candidate):
            self.full_detail_provider_ids.append(candidate.provider_id)
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="低智商犯罪",
                tmdb_id="272432",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [
                            {"episode_number": 1, "season_number": 1, "name": "第一集", "still_url": "new-1"},
                            {"episode_number": 2, "season_number": 1, "name": "第二集", "still_url": ""},
                        ],
                    }
                ],
            )

    controller = FollowingController(repo, metadata_search_service=PartialEpisodeRefreshService(), now=lambda: 100)

    refreshed = controller.refresh_metadata(record_id)

    snapshot = repo.get_detail_snapshot(record_id)
    assert snapshot is not None
    assert [episode.episode_number for episode in snapshot.episodes] == [1, 2, 3]
    assert snapshot.episodes[0].still == "new-1"
    assert snapshot.episodes[1].still == "old-2"
    assert snapshot.episodes[2].still == "old-3"
    assert [episode.episode_number for episode in refreshed.snapshot.episodes] == [1, 2, 3]


def test_following_controller_load_detail_season_replaces_episode_list_for_requested_tmdb_season(
    tmp_path: Path,
) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="低智商犯罪",
            media_kind="live_action",
            season_number=1,
            provider="player",
            provider_id="player:source:vod-1",
            external_ids={"tmdb": "272432"},
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            overview="总简介",
            episodes=[FollowingEpisode(episode_number=1, season_number=1, title="S1E1")],
        ),
    )

    class SeasonDetailService(FakeSearchService):
        def __init__(self) -> None:
            self.provider_ids: list[str] = []

        def detail_record_full(self, candidate):
            self.provider_ids.append(candidate.provider_id)
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="低智商犯罪",
                overview="总简介",
                tmdb_id="272432",
                detail_fields=[
                    {
                        "label": "seasons",
                        "value": [
                            {"season_number": 1, "name": "第一季", "episode_count": 24},
                            {"season_number": 2, "name": "第二季", "episode_count": 20},
                        ],
                    },
                    {
                        "label": "episodes",
                        "value": [
                            {"episode_number": 1, "season_number": 2, "name": "S2E1"},
                            {"episode_number": 2, "season_number": 2, "name": "S2E2"},
                        ],
                    },
                ],
            )

    service = SeasonDetailService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    detail = controller.load_detail_season(record_id, season_number=2)

    snapshot = repo.get_detail_snapshot(record_id)
    assert service.provider_ids == ["tv:272432:season:2"]
    assert [episode.title for episode in detail.snapshot.episodes] == ["S2E1", "S2E2"]
    assert snapshot is not None
    assert [season.season_number for season in snapshot.seasons] == [1, 2]
    assert [episode.season_number for episode in snapshot.episodes] == [2, 2]


def test_following_controller_load_detail_season_overrides_existing_tmdb_provider_season(
    tmp_path: Path,
) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="黑袍纠察队",
            media_kind="live_action",
            season_number=5,
            provider="tmdb",
            provider_id="tv:76479:season:1",
            external_ids={"tmdb": "76479"},
        )
    )

    class SeasonOverrideService(FakeSearchService):
        def __init__(self) -> None:
            self.provider_ids: list[str] = []

        def detail_record_full(self, candidate):
            self.provider_ids.append(candidate.provider_id)
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="黑袍纠察队",
                tmdb_id="76479",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [
                            {"episode_number": 1, "season_number": 5, "name": "S5E1"},
                        ],
                    }
                ],
            )

    service = SeasonOverrideService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    detail = controller.load_detail_season(record_id, season_number=5)

    assert service.provider_ids == ["tv:76479:season:5"]
    assert [episode.season_number for episode in detail.snapshot.episodes] == [5]


class FakeFullEpisodeRefreshService:
    def __init__(self, latest: int, total: int) -> None:
        self._latest = latest
        self._total = total
        self.search_calls = 0

    def search(self, query, provider_filter=""):
        del query, provider_filter
        self.search_calls += 1
        return []

    def detail_record_full(self, candidate):
        episodes = [
            {"episode_number": index, "name": f"第{index}集", "type": 0, "air_date": ""}
            for index in range(1, self._latest + 1)
        ]
        episodes.extend(
            {"episode_number": index, "name": f"第{index}集", "type": 0, "air_date": "2099-01-01"}
            for index in range(self._latest + 1, self._total + 1)
        )
        return MetadataRecord(
            provider="tmdb",
            provider_id=candidate.provider_id,
            title="新元数据剧集",
            poster="new-poster",
            backdrop="new-backdrop",
            overview="新简介",
            tmdb_id="999",
            detail_fields=[{"label": "episodes", "value": episodes}],
        )


def test_following_controller_refresh_metadata_corrects_wrong_episode_counts(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="错误集数剧集",
            media_kind="live_action",
            season_number=1,
            provider="player",
            provider_id="player:source:vod-1",
            external_ids={"tmdb": "999"},
            current_episode=12,
            latest_episode=12,
            previous_latest_episode=12,
            total_episodes=12,
            watched_latest_episode=True,
            has_update=False,
            new_episode_count=0,
            homepage_prompt_pending=False,
        )
    )
    service = FakeFullEpisodeRefreshService(latest=24, total=30)
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    controller.refresh_metadata(record_id)

    loaded = repo.get(record_id)
    assert loaded is not None
    assert loaded.latest_episode == 24
    assert loaded.total_episodes == 30
    assert loaded.current_episode == 12
    assert loaded.watched_latest_episode is False
    assert loaded.has_update is True
    assert loaded.new_episode_count == 12


def test_following_controller_add_from_player_captures_season_number_from_title(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)
    vod = VodItem(
        vod_id="vod-1",
        vod_name="黑袍纠察队 第五季",
        detail_fields=[PlaybackDetailField("TMDB ID", "76479")],
    )
    item = PlayItem(title="第1集", url="u", media_title="黑袍纠察队 第五季", vod_id="vod-1")

    record = controller.add_from_player(
        vod=vod,
        item=item,
        source_kind="browse",
        source_key="",
        position_seconds=0,
        playlist=[item],
    )

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.season_number == 5


def test_following_controller_refresh_metadata_skips_tmdb_when_season_unknown(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="未知季剧集",
            media_kind="live_action",
            provider="player",
            provider_id="player:source:vod-1",
            external_ids={"tmdb": "272432"},
        )
    )
    service = FakeTMDBIdRefreshService()
    controller = FollowingController(repo, metadata_search_service=service, now=lambda: 100)

    try:
        controller.refresh_metadata(record_id)
    except RuntimeError:
        pass

    assert service.full_detail_provider_ids == []
