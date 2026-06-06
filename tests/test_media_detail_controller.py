from __future__ import annotations

from types import SimpleNamespace

from atv_player.controllers.media_detail_controller import MediaDetailController
from atv_player.controllers.media_detail_controller import MediaDetailIdentity
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
            "first_air_date": "2011-04-17",
            "overview": "九大家族争夺铁王座。",
            "poster_url": "https://image.example/poster.jpg",
            "backdrop_url": "https://image.example/backdrop.jpg",
            "vote_average": 8.4,
            "genres": [{"id": 18, "name": "剧情"}, {"id": 10765, "name": "科幻奇幻"}],
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
                        "name": "Emilia Clarke",
                        "roles": [{"character": "Daenerys Targaryen"}],
                        "profile_path": "/emilia.jpg",
                    }
                ],
                "crew": [{"name": "David Benioff", "jobs": [{"job": "Creator"}]}],
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


def test_media_detail_controller_maps_tv_detail_from_vod() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_vod(VodItem(vod_id="tmdb:tv:1399", vod_name="权力的游戏"))

    assert view.identity == MediaDetailIdentity(media_type="tv", tmdb_id="1399", title="权力的游戏")
    assert view.title == "权力的游戏"
    assert view.year == "2011"
    assert view.rating == "8.4"
    assert view.genres == ["剧情", "科幻奇幻"]
    assert view.episodes[0].display_title == "S1E1 凛冬将至"
    assert view.people[0].name == "Emilia Clarke"
    assert view.people[0].role == "Daenerys Targaryen"
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


def test_media_detail_controller_searches_when_heat_item_has_no_tmdb_id() -> None:
    client = FakeTMDBClient()
    controller = MediaDetailController(client=client)

    view = controller.load_from_heat(SimpleNamespace(media_key="", title="王国", year="2019", media_type="tv"))

    assert view.identity.tmdb_id == "1399"
    assert client.tv_search_calls == [("王国", "2019")]


def test_media_detail_controller_builds_following_candidate() -> None:
    controller = MediaDetailController(client=FakeTMDBClient())
    view = controller.load_from_vod(VodItem(vod_id="tmdb:movie:550", vod_name="搏击俱乐部"))

    candidate = controller.candidate_for_following(view)

    assert candidate.provider == "tmdb"
    assert candidate.provider_id == "movie:550"
    assert candidate.title == "搏击俱乐部"
    assert candidate.year == "1999"
    assert candidate.subtitle == "电影"
