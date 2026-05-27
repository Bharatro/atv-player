import threading
import time
from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.discovery import DiscoveryQuery, RecommendationSeed, TMDBDiscoveryService


class StubTMDBClient:
    def __init__(self, *, trending=None, discover=None, recommendations=None) -> None:
        self._trending = list(trending or [])
        self._discover = list(discover or [])
        self._recommendations = dict(recommendations or {})
        self.trending_calls = 0
        self.discover_calls = 0
        self.recommendation_calls = 0

    def get_trending(self, *, media_type: str, window: str = "week", page: int = 1) -> list[dict[str, object]]:
        self.trending_calls += 1
        return list(self._trending)

    def discover(
        self,
        *,
        media_type: str,
        page: int = 1,
        sort_by: str = "",
        year: str = "",
        with_genres: str = "",
        with_origin_country: str = "",
    ) -> list[dict[str, object]]:
        self.discover_calls += 1
        return list(self._discover)

    def image_base(self, kind: str) -> str:
        if kind == "poster":
            return "https://image.tmdb.org/t/p/original"
        return "https://image.tmdb.org/t/p/w1280"

    def get_recommendations(self, *, media_type: str, tmdb_id: str | int, page: int = 1) -> list[dict[str, object]]:
        self.recommendation_calls += 1
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


def test_tmdb_discovery_service_fetches_recommendation_seeds_concurrently(tmp_path: Path) -> None:
    class SlowRecommendationClient(StubTMDBClient):
        def __init__(self) -> None:
            super().__init__(
                recommendations={
                    ("tv", str(index)): [
                        {"id": 1000 + index, "name": f"推荐 {index}", "vote_average": 7.0, "popularity": 100.0}
                    ]
                    for index in range(4)
                }
            )
            self._lock = threading.Lock()
            self._active = 0
            self.max_active = 0

        def get_recommendations(self, *, media_type: str, tmdb_id: str | int, page: int = 1) -> list[dict[str, object]]:
            with self._lock:
                self._active += 1
                self.max_active = max(self.max_active, self._active)
            try:
                time.sleep(0.05)
                return super().get_recommendations(media_type=media_type, tmdb_id=tmdb_id, page=page)
            finally:
                with self._lock:
                    self._active -= 1

    client = SlowRecommendationClient()
    service = TMDBDiscoveryService(client=client, cache=MetadataCache(tmp_path))

    result = service.recommend(
        seeds=[
            RecommendationSeed(
                provider_id=f"tv:{index}",
                tmdb_id=str(index),
                media_type="tv",
                seed_source="following",
                activity_weight=5.0,
                activity_timestamp=index,
                reason_flags=[],
            )
            for index in range(4)
        ],
        favorite_provider_ids=set(),
        following_provider_ids=set(),
    )

    assert len(result.items) == 4
    assert client.recommendation_calls == 4
    assert client.max_active > 1


def test_tmdb_discovery_service_uses_disk_cache_for_trending_queries(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        trending=[
            {"id": 76479, "name": "黑袍纠察队", "first_air_date": "2019-07-26"},
        ]
    )
    service = TMDBDiscoveryService(client=client, cache=cache)

    first = service.trending(DiscoveryQuery(kind="trending", media_type="tv", list_key="trending_day", page=1))

    assert first.items[0].provider_id == "tv:76479"
    assert client.trending_calls == 1

    client._trending = [{"id": 999, "name": "不会被读到"}]
    second = TMDBDiscoveryService(client=client, cache=cache).trending(
        DiscoveryQuery(kind="trending", media_type="tv", list_key="trending_day", page=1)
    )

    assert second.items[0].provider_id == "tv:76479"
    assert second.source_label == "今日趋势"
    assert client.trending_calls == 1


def test_tmdb_discovery_service_uses_distinct_cache_keys_for_discover_filters(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        discover=[
            {"id": 100, "name": "Gen V", "first_air_date": "2023-09-29"},
        ]
    )
    service = TMDBDiscoveryService(client=client, cache=cache)

    first = service.discover(
        DiscoveryQuery(kind="discover", media_type="tv", sort_by="popularity.desc", year="2023", page=1)
    )
    cached = TMDBDiscoveryService(client=client, cache=cache).discover(
        DiscoveryQuery(kind="discover", media_type="tv", sort_by="popularity.desc", year="2023", page=1)
    )

    assert first.items[0].provider_id == "tv:100"
    assert cached.items[0].provider_id == "tv:100"
    assert client.discover_calls == 1

    client._discover = [{"id": 200, "title": "Dune", "release_date": "2021-10-22"}]
    changed = TMDBDiscoveryService(client=client, cache=cache).discover(
        DiscoveryQuery(kind="discover", media_type="movie", sort_by="vote_average.desc", year="2021", page=1)
    )

    assert changed.items[0].provider_id == "movie:200"
    assert client.discover_calls == 2


def test_tmdb_discovery_service_uses_disk_cache_for_recommendations_when_seed_signature_is_unchanged(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        recommendations={
            ("tv", "76479"): [
                {"id": 100, "name": "Gen V", "vote_average": 7.8, "popularity": 200.0},
            ]
        }
    )
    service = TMDBDiscoveryService(client=client, cache=cache)
    seeds = [
        RecommendationSeed(
            provider_id="tv:76479",
            tmdb_id="76479",
            media_type="tv",
            seed_source="following",
            activity_weight=5.0,
            activity_timestamp=200,
            reason_flags=["has_update"],
        )
    ]

    first = service.recommend(
        seeds=seeds,
        favorite_provider_ids=set(),
        following_provider_ids={"tv:76479"},
    )

    assert [item.provider_id for item in first.items] == ["tv:100"]
    assert client.recommendation_calls == 1

    client._recommendations = {("tv", "76479"): [{"id": 200, "name": "不会被读到"}]}
    second = TMDBDiscoveryService(client=client, cache=cache).recommend(
        seeds=list(seeds),
        favorite_provider_ids=set(),
        following_provider_ids={"tv:76479"},
    )

    assert [item.provider_id for item in second.items] == ["tv:100"]
    assert client.recommendation_calls == 1


def test_tmdb_discovery_service_reuses_recommendation_cache_when_exclusion_sets_change(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        recommendations={
            ("tv", "76479"): [
                {"id": 100, "name": "Gen V", "vote_average": 7.8, "popularity": 200.0},
                {"id": 200, "name": "The Boys: Mexico", "vote_average": 7.0, "popularity": 150.0},
            ]
        }
    )
    seeds = [
        RecommendationSeed(
            provider_id="tv:76479",
            tmdb_id="76479",
            media_type="tv",
            seed_source="following",
            activity_weight=5.0,
            activity_timestamp=200,
            reason_flags=["has_update"],
        )
    ]

    first = TMDBDiscoveryService(client=client, cache=cache).recommend(
        seeds=seeds,
        favorite_provider_ids=set(),
        following_provider_ids={"tv:76479"},
    )
    second = TMDBDiscoveryService(client=client, cache=cache).recommend(
        seeds=list(seeds),
        favorite_provider_ids={"tv:100"},
        following_provider_ids={"tv:76479"},
    )

    assert [item.provider_id for item in first.items] == ["tv:100", "tv:200"]
    assert [item.provider_id for item in second.items] == ["tv:200"]
    assert client.recommendation_calls == 1


def test_tmdb_discovery_service_recommendation_cache_miss_when_seed_signature_changes(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        recommendations={
            ("tv", "76479"): [{"id": 100, "name": "Gen V", "vote_average": 7.8, "popularity": 200.0}],
            ("movie", "157336"): [{"id": 200, "title": "Dune", "vote_average": 8.2, "popularity": 150.0}],
        }
    )
    service = TMDBDiscoveryService(client=client, cache=cache)

    service.recommend(
        seeds=[
            RecommendationSeed(
                provider_id="tv:76479",
                tmdb_id="76479",
                media_type="tv",
                seed_source="following",
                activity_weight=5.0,
                activity_timestamp=200,
                reason_flags=["has_update"],
            )
        ],
        favorite_provider_ids=set(),
        following_provider_ids={"tv:76479"},
    )
    service.recommend(
        seeds=[
            RecommendationSeed(
                provider_id="movie:157336",
                tmdb_id="157336",
                media_type="movie",
                seed_source="favorite",
                activity_weight=2.0,
                activity_timestamp=100,
                reason_flags=[],
            )
        ],
        favorite_provider_ids=set(),
        following_provider_ids=set(),
    )

    assert client.recommendation_calls == 2
