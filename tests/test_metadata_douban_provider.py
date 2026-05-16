from atv_player.metadata.models import MetadataContext
from atv_player.metadata.providers.douban import DoubanProvider
from atv_player.models import VodItem


class FakeMetadataApiClient:
    def __init__(self, *, search_payload: dict | None = None, detail_payload: dict | None = None) -> None:
        self.search_payload = search_payload or {"items": []}
        self.detail_payload = detail_payload or {}
        self.search_calls: list[tuple[str, str]] = []
        self.detail_calls: list[int | str] = []

    def search_douban_metadata(self, title: str, year: str = "") -> dict:
        self.search_calls.append((title, year))
        return self.search_payload

    def get_douban_metadata_detail(self, dbid: int | str) -> dict:
        self.detail_calls.append(dbid)
        return self.detail_payload


def test_douban_provider_prefers_dbid_detail_lookup_before_search() -> None:
    api = FakeMetadataApiClient(
        detail_payload={"id": 35746415, "name": "深空彼岸", "description": "豆瓣简介", "dbScore": "8.1", "year": 2026},
    )
    provider = DoubanProvider(api)
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", dbid=35746415), source_kind="plugin")

    matches = provider.search(context.to_query())
    record = provider.get_detail(matches[0])

    assert record.douban_id == 35746415
    assert api.search_calls == []
    assert api.detail_calls == [35746415]


def test_douban_provider_cleans_fold_markers_and_prefers_douban_overview() -> None:
    api = FakeMetadataApiClient(
        search_payload={"items": [{"id": 35746415, "name": "深空彼岸", "year": 2026}]},
        detail_payload={
            "id": 35746415,
            "name": "深空彼岸",
            "description": "豆瓣简介[展开全部] 豆瓣简介[收起部分]",
            "dbScore": "8.1",
            "year": 2026,
        },
    )
    provider = DoubanProvider(api)
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="plugin")

    matches = provider.search(context.to_query())
    record = provider.get_detail(matches[0])

    assert record.overview == "豆瓣简介"


def test_douban_provider_maps_core_movie_fields() -> None:
    api = FakeMetadataApiClient(
        search_payload={"items": [{"id": 35746415, "name": "深空彼岸", "year": 2026}]},
        detail_payload={
            "id": 35746415,
            "name": "深空彼岸",
            "description": "豆瓣简介",
            "dbScore": "8.1",
            "year": 2026,
            "genre": "动画,科幻",
            "country": "中国大陆",
            "language": "汉语普通话",
            "directors": "周琛",
            "actors": "梁达伟,唐雅菁",
        },
    )
    provider = DoubanProvider(api)
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="plugin")

    matches = provider.search(context.to_query())
    record = provider.get_detail(matches[0])

    assert record.genres == ["动画", "科幻"]
    assert record.country == "中国大陆"
    assert record.language == "汉语普通话"
    assert record.directors == ["周琛"]
    assert record.actors == ["梁达伟", "唐雅菁"]
