from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.discovery import DiscoveryQuery, TMDBDiscoveryService


class StubTMDBClient:
    def __init__(self, *, trending=None) -> None:
        self._trending = list(trending or [])

    def get_trending(self, *, media_type: str, window: str = "week", page: int = 1) -> list[dict[str, object]]:
        assert media_type == "tv"
        assert window == "week"
        assert page == 1
        return list(self._trending)

    def image_base(self, kind: str) -> str:
        if kind == "poster":
            return "https://image.tmdb.org/t/p/original"
        return "https://image.tmdb.org/t/p/w1280"


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
