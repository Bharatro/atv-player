from __future__ import annotations

from types import SimpleNamespace

from atv_player.following_models import FollowingMetadataBundle
from atv_player.controllers.media_detail_controller import MediaDetailController
from atv_player.controllers.media_detail_controller import MediaDetailIdentity
from atv_player.controllers.media_detail_controller import MediaDetailLookup
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate
from atv_player.metadata.scrape import MetadataScrapeGroup
from atv_player.models import VodItem


class FakeTMDBClient:
    def __init__(self) -> None:
        self.tv_detail_calls: list[tuple[str, int | None]] = []
        self.season_calls: list[tuple[str, int]] = []
        self.recommendation_calls: list[tuple[str, str]] = []
        self.movie_detail_calls: list[str] = []
        self.tv_search_calls: list[tuple[str, str]] = []

    def get_tv_detail_with_season(self, tmdb_id: str, *, season_number: int | None = None):
        self.tv_detail_calls.append((str(tmdb_id), season_number))
        resolved_season = season_number or 1
        return {
            "id": 1399,
            "name": "权力的游戏",
            "original_name": "Game of Thrones",
            "first_air_date": "2011-04-17",
            "overview": "九大家族争夺铁王座。",
            "poster_url": "https://image.example/poster.jpg",
            "backdrop_url": "https://image.example/backdrop.jpg",
            "vote_average": 8.4,
            "genres": [{"id": 18, "name": "剧情"}, {"id": 10765, "name": "科幻奇幻"}],
            "external_ids": {"imdb_id": "tt0944947"},
            "alternative_titles": {"results": [{"name": "冰与火之歌"}]},
            "seasons": [
                {"season_number": 1, "name": "第 1 季", "episode_count": 10},
                {"season_number": 2, "name": "第 2 季", "episode_count": 10},
            ],
            f"season/{resolved_season}": {
                "episodes": [
                    {
                        "season_number": resolved_season,
                        "episode_number": 1,
                        "name": "凛冬将至" if resolved_season == 1 else f"S{resolved_season}E1",
                        "air_date": "2011-04-17",
                        "overview": "故事开始。",
                        "still_url": "https://image.example/ep1.jpg",
                    }
                ]
            },
            "aggregate_credits": {
                "cast": [
                    {
                        "id": 1223786,
                        "name": "Emilia Clarke",
                        "roles": [{"character": "Daenerys Targaryen"}],
                        "profile_path": "/emilia.jpg",
                    }
                ],
                "crew": [
                    {"name": "David Benioff", "jobs": [{"job": "Creator"}]},
                    {"name": "Alan Taylor", "jobs": [{"job": "Director"}]},
                ],
            },
        }

    def get_tv_season_detail(self, tmdb_id: str, season_number: int):
        self.season_calls.append((str(tmdb_id), season_number))
        return {
            "episodes": [
                {
                    "season_number": season_number,
                    "episode_number": 1,
                    "name": f"S{season_number}E1",
                    "air_date": "2012-04-01",
                }
            ]
        }

    def get_recommendations(self, *, media_type: str, tmdb_id: str, page: int = 1):
        self.recommendation_calls.append((media_type, str(tmdb_id)))
        return [
            {
                "id": 1412,
                "name": "绿箭侠",
                "first_air_date": "2012-10-10",
                "poster_path": "/arrow.jpg",
                "vote_average": 6.8,
            }
        ]

    def get_movie_detail(self, tmdb_id: str):
        self.movie_detail_calls.append(str(tmdb_id))
        return {
            "id": 550,
            "title": "搏击俱乐部",
            "release_date": "1999-10-15",
            "overview": "失眠者遇见肥皂商。",
            "vote_average": 8.4,
            "credits": {"cast": [], "crew": []},
        }

    def search_tv(self, title: str, year: str = ""):
        self.tv_search_calls.append((title, year))
        return [{"id": 1399, "name": title, "first_air_date": "2011-04-17"}]


class FakeMetadataSearchService:
    def __init__(self) -> None:
        self.queries = []
        self.detail_candidates = []

    def search_following(self, query):
        self.queries.append(query)
        return [
            MetadataScrapeGroup(
                provider="douban",
                provider_label="豆瓣",
                items=[
                    MetadataScrapeCandidate(
                        provider="douban",
                        provider_label="豆瓣",
                        provider_id="db-1399",
                        title=query.title,
                        year=query.year,
                    )
                ],
            )
        ]

    def detail_record_full(self, candidate):
        self.detail_candidates.append(candidate)
        return MetadataRecord(
            provider="douban",
            provider_id=candidate.provider_id,
            title=candidate.title,
            year=candidate.year,
            overview="豆瓣补充简介",
            rating="9.5",
            genres=["剧情"],
            detail_fields=[{"label": "豆瓣ID", "value": candidate.provider_id}],
        )


class FakeDualDoubanMetadataSearchService:
    def __init__(self, *, fail_official: bool = False) -> None:
        self.fail_official = fail_official
        self.queries = []
        self.detail_candidates = []

    def search_following(self, query):
        self.queries.append(query)
        return [
            MetadataScrapeGroup(
                provider="local_douban",
                provider_label="本地豆瓣",
                items=[
                    MetadataScrapeCandidate(
                        provider="local_douban",
                        provider_label="本地豆瓣",
                        provider_id="local-1399",
                        title=query.title,
                        year=query.year,
                    )
                ],
            ),
            MetadataScrapeGroup(
                provider="official_douban",
                provider_label="豆瓣官方",
                items=[
                    MetadataScrapeCandidate(
                        provider="official_douban",
                        provider_label="豆瓣官方",
                        provider_id="official-1399",
                        title=query.title,
                        year=query.year,
                    )
                ],
            ),
        ]

    def detail_record_full(self, candidate):
        self.detail_candidates.append(candidate)
        if candidate.provider == "official_douban" and self.fail_official:
            raise RuntimeError("official blocked")
        return MetadataRecord(
            provider=candidate.provider,
            provider_id=candidate.provider_id,
            title=candidate.title,
            year=candidate.year,
            overview=f"{candidate.provider} 简介",
            rating="9.5" if candidate.provider == "official_douban" else "9.0",
            genres=["剧情"],
            douban_id=129,
        )


def test_media_detail_controller_maps_tv_detail_from_vod() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert view.identity == MediaDetailIdentity(media_type="tv", tmdb_id="1399", title="权力的游戏")
    assert view.title == "权力的游戏"
    assert view.year == "2011"
    assert view.rating == "8.4"
    assert view.genres == ["剧情", "科幻奇幻"]
    assert isinstance(view.metadata_bundle, FollowingMetadataBundle)
    assert view.metadata_bundle.available_source_keys == ["merged", "tmdb"]
    assert view.metadata_bundle.source_snapshots["tmdb"].provider_label == "TMDB"
    assert {"label": "类型", "value": "剧情 / 科幻奇幻"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "年代", "value": "2011"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "导演", "value": "Alan Taylor"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "演员", "value": "Emilia Clarke"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "别名", "value": "冰与火之歌"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "IMDb ID", "value": "tt0944947"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert {"label": "TMDB ID", "value": "1399"} in view.metadata_bundle.merged_snapshot.metadata_fields
    assert view.episodes[0].display_title == "S1E1 凛冬将至"
    assert view.people[0].name == "Emilia Clarke"
    assert view.people[0].role == "Daenerys Targaryen"
    assert view.people[0].url == "https://www.themoviedb.org/person/1223786"
    assert view.people[1].role == "Creator"
    assert view.related[0].identity == MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠")
    assert client.tv_detail_calls == [("1399", 1)]
    assert client.recommendation_calls == [("tv", "1399")]


def test_media_detail_controller_builds_image_urls_from_tmdb_paths() -> None:
    class PathOnlyTMDBClient(FakeTMDBClient):
        def get_tv_detail_with_season(self, tmdb_id: str, *, season_number: int | None = None):
            raw = super().get_tv_detail_with_season(tmdb_id, season_number=season_number)
            raw.pop("poster_url", None)
            raw.pop("backdrop_url", None)
            raw["poster_path"] = "/poster-path.jpg"
            raw["backdrop_path"] = "/backdrop-path.jpg"
            return raw

    controller = MediaDetailController(client=PathOnlyTMDBClient())

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert view.poster_url == "https://image.tmdb.org/t/p/w500/poster-path.jpg"
    assert view.backdrop_url == "https://image.tmdb.org/t/p/w780/backdrop-path.jpg"


def test_media_detail_controller_loads_tv_detail_for_selected_season() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)
    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    selected = controller.load_season(view, season_number=2)

    assert client.tv_detail_calls == [("1399", 1), ("1399", 2)]
    assert selected.identity == view.identity
    assert selected.episodes[0].season_number == 2
    assert selected.episodes[0].title == "S2E1"


def test_media_detail_controller_uses_credits_fallback_for_tv_people() -> None:
    class CreditsOnlyTMDBClient(FakeTMDBClient):
        def get_tv_detail_with_season(self, tmdb_id: str, *, season_number: int | None = None):
            raw = super().get_tv_detail_with_season(tmdb_id, season_number=season_number)
            raw.pop("aggregate_credits", None)
            raw["credits"] = {
                "cast": [
                    {
                        "name": "Pedro Pascal",
                        "character": "Joel Miller",
                        "profile_path": "/pedro.jpg",
                    }
                ],
                "crew": [{"name": "Craig Mazin", "job": "Creator"}],
            }
            return raw

    controller = MediaDetailController(client=CreditsOnlyTMDBClient())

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="最后生还者"))

    assert [(person.name, person.role) for person in view.people] == [
        ("Pedro Pascal", "Joel Miller"),
        ("Craig Mazin", "Creator"),
    ]


def test_media_detail_controller_loads_heat_recommendation_from_media_key() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_heat(
        SimpleNamespace(media_key="tmdb:tv:1399", title="权力的游戏", year="2011", media_type="tv")
    )

    assert view.identity.tmdb_id == "1399"
    assert view.identity.media_type == "tv"
    assert client.tv_detail_calls == [("1399", 1)]


def test_media_detail_controller_builds_placeholder_from_vod_without_network() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.placeholder_from_vod(
        VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏", vod_year="2011", vod_pic="poster.jpg")
    )

    assert view.title == "权力的游戏"
    assert view.identity == MediaDetailIdentity(media_type="tv", tmdb_id="1399", title="权力的游戏")
    assert view.year == "2011"
    assert view.poster_url == "poster.jpg"
    assert "正在加载" in view.overview
    assert view.metadata_bundle is not None
    assert client.tv_detail_calls == []


def test_media_detail_controller_merges_metadata_search_sources_into_bundle() -> None:
    service = FakeMetadataSearchService()
    controller = MediaDetailController(client=FakeTMDBClient(), metadata_search_service=service)

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert service.queries[0].title == "权力的游戏"
    assert service.queries[0].source_kind == "tmdb"
    assert service.queries[0].vod_id == "tv:1399"
    assert view.metadata_bundle is not None
    assert view.metadata_bundle.available_source_keys == ["merged", "tmdb", "douban"]
    assert view.metadata_bundle.source_snapshots["douban"].provider_label == "豆瓣"
    assert any(item.label == "豆瓣" and item.value == "9.5" for item in view.metadata_bundle.merged_snapshot.ratings)


def test_media_detail_controller_coalesces_official_and_local_douban_into_one_source() -> None:
    service = FakeDualDoubanMetadataSearchService()
    controller = MediaDetailController(client=FakeTMDBClient(), metadata_search_service=service)

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert view.metadata_bundle is not None
    assert view.metadata_bundle.available_source_keys == ["merged", "tmdb", "douban"]
    douban_source = view.metadata_bundle.source_snapshots["douban"]
    assert douban_source.provider_label == "豆瓣"
    assert douban_source.provider == "douban"
    assert douban_source.provider_id == "official-1399"
    assert [candidate.provider for candidate in service.detail_candidates] == ["official_douban"]
    assert all(key not in view.metadata_bundle.source_snapshots for key in ("official_douban", "local_douban"))


def test_media_detail_controller_uses_local_douban_only_when_official_fails() -> None:
    service = FakeDualDoubanMetadataSearchService(fail_official=True)
    controller = MediaDetailController(client=FakeTMDBClient(), metadata_search_service=service)

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert view.metadata_bundle is not None
    assert view.metadata_bundle.available_source_keys == ["merged", "tmdb", "douban"]
    douban_source = view.metadata_bundle.source_snapshots["douban"]
    assert douban_source.provider_label == "豆瓣"
    assert douban_source.provider_id == "local-1399"
    assert [candidate.provider for candidate in service.detail_candidates] == [
        "official_douban",
        "local_douban",
    ]


def test_media_detail_controller_searches_when_heat_item_has_no_tmdb_id() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_heat(SimpleNamespace(media_key="", title="王国", year="2019", media_type="tv"))

    assert view.identity.tmdb_id == "1399"
    assert client.tv_search_calls == [("王国", "2019")]


def test_media_detail_controller_searches_when_lookup_has_no_tmdb_id() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_lookup(
        MediaDetailLookup(title="Gen V", year="2023", provider="official_douban", provider_id="36454318")
    )

    assert view.identity.tmdb_id == "1399"
    assert view.identity.media_type == "tv"
    assert client.tv_search_calls == [("Gen V", "2023")]
    assert client.tv_detail_calls == [("1399", 1)]


def test_media_detail_controller_builds_following_candidate() -> None:
    controller = MediaDetailController(client=FakeTMDBClient())
    view = controller.load_from_vod(VodItem(vod_id="tmdb:movie:550", vod_name="搏击俱乐部"))

    candidate = controller.candidate_for_following(view)

    assert candidate.provider == "tmdb"
    assert candidate.provider_id == "movie:550"
    assert candidate.title == "搏击俱乐部"
    assert candidate.year == "1999"
    assert candidate.subtitle == "电影"
