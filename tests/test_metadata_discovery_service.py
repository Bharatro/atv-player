from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.discovery import DiscoveryQuery, RecommendationSeed, TMDBDiscoveryService


class StubTMDBClient:
    def __init__(self, *, trending=None, recommendations=None) -> None:
        self._trending = list(trending or [])
        self._recommendations = dict(recommendations or {})

    def get_trending(self, *, media_type: str, window: str = "week", page: int = 1) -> list[dict[str, object]]:
        assert media_type == "tv"
        assert window == "week"
        assert page == 1
        return list(self._trending)

    def image_base(self, kind: str) -> str:
        if kind == "poster":
            return "https://image.tmdb.org/t/p/original"
        return "https://image.tmdb.org/t/p/w1280"

    def get_recommendations(self, *, media_type: str, tmdb_id: str | int, page: int = 1) -> list[dict[str, object]]:
        assert page == 1
        return list(self._recommendations.get((str(media_type), str(tmdb_id)), []))


def test_tmdb_discovery_service_maps_trending_items_to_shared_cards(tmp_path: Path) -> None:
    client = StubTMDBClient(
        trending=[
            {
                "id": 76479,
                "name": "黑袍纠察队",
                "first_air_date": "2019-07-26",
                "overview": "超英黑色喜剧",
                "vote_average": 8.7,
                "poster_path": "/boys.jpg",
            }
        ]
    )
    service = TMDBDiscoveryService(client=client, cache=MetadataCache(tmp_path))

    result = service.trending(DiscoveryQuery(kind="trending", media_type="tv", list_key="trending_week", page=1))

    assert result.total == 1
    assert result.source_label == "本周趋势"
    assert result.items[0].provider_id == "tv:76479"
    assert result.items[0].title == "黑袍纠察队"
    assert result.items[0].year == "2019"
    assert result.items[0].media_type == "tv"
    assert result.items[0].rating == "8.7"
    assert result.items[0].poster == "https://image.tmdb.org/t/p/original/boys.jpg"
    assert result.items[0].source_label == "本周趋势"


def test_tmdb_discovery_service_recommendation_aggregates_recent_following_and_favorites(tmp_path: Path) -> None:
    client = StubTMDBClient(
        recommendations={
            ("tv", "76479"): [
                {"id": 100, "name": "Gen V", "vote_average": 7.8, "popularity": 200.0},
            ],
            ("movie", "157336"): [
                {"id": 100, "name": "Gen V", "vote_average": 7.8, "popularity": 200.0},
                {"id": 200, "title": "Dune", "vote_average": 8.2, "popularity": 150.0},
            ],
        }
    )
    service = TMDBDiscoveryService(client=client, cache=MetadataCache(tmp_path))

    result = service.recommend(
        seeds=[
            RecommendationSeed(
                provider_id="tv:76479",
                tmdb_id="76479",
                media_type="tv",
                seed_source="following",
                activity_weight=5.0,
                activity_timestamp=200,
                reason_flags=["has_update"],
            ),
            RecommendationSeed(
                provider_id="movie:157336",
                tmdb_id="157336",
                media_type="movie",
                seed_source="favorite",
                activity_weight=2.0,
                activity_timestamp=100,
                reason_flags=[],
            ),
        ],
        favorite_provider_ids={"movie:157336"},
        following_provider_ids={"tv:76479"},
    )

    assert result.source_label == "推荐"
    assert [item.provider_id for item in result.items] == ["tv:100", "movie:200"]
    assert result.items[0].title == "Gen V"
