from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery
from atv_player.metadata.providers.douban import DoubanProvider
from atv_player.metadata.providers.local_douban_client import DoubanBlockedError
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


class FakeLocalDoubanClient:
    def __init__(
        self,
        *,
        search_results: list[dict] | None = None,
        detail_result: dict | None = None,
        search_error: Exception | None = None,
        detail_error: Exception | None = None,
    ) -> None:
        self.search_results = list(search_results or [])
        self.detail_result = detail_result
        self.search_error = search_error
        self.detail_error = detail_error
        self.search_calls: list[tuple[str, str]] = []
        self.detail_calls: list[int | str] = []

    def search(self, title: str, year: str = "") -> list[dict]:
        self.search_calls.append((title, year))
        if self.search_error is not None:
            raise self.search_error
        return list(self.search_results)

    def get_detail(self, dbid: int | str) -> dict | None:
        self.detail_calls.append(dbid)
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result


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


def test_douban_provider_uses_local_search_before_backend_fallback() -> None:
    local = FakeLocalDoubanClient(
        search_results=[{"id": "35746415", "title": "深空彼岸", "year": "2026"}],
    )
    api = FakeMetadataApiClient(search_payload={"items": []})
    provider = DoubanProvider(api, local_client=local)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [match.provider_id for match in matches] == ["35746415"]
    assert local.search_calls == [("深空彼岸", "2026")]
    assert api.search_calls == []


def test_douban_provider_falls_back_when_local_search_is_blocked() -> None:
    local = FakeLocalDoubanClient(search_error=DoubanBlockedError("被禁止访问"))
    api = FakeMetadataApiClient(
        search_payload={"items": [{"id": 35746415, "name": "深空彼岸", "year": 2026}]},
    )
    provider = DoubanProvider(api, local_client=local)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [match.provider_id for match in matches] == ["35746415"]
    assert api.search_calls == [("深空彼岸", "2026")]


def test_douban_provider_falls_back_when_local_search_returns_no_results() -> None:
    local = FakeLocalDoubanClient(search_results=[])
    api = FakeMetadataApiClient(
        search_payload={"items": [{"id": 35746415, "name": "深空彼岸", "year": 2026}]},
    )
    provider = DoubanProvider(api, local_client=local)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [match.provider_id for match in matches] == ["35746415"]
    assert api.search_calls == [("深空彼岸", "2026")]


def test_douban_provider_falls_back_when_local_detail_is_missing() -> None:
    local = FakeLocalDoubanClient(detail_result=None)
    api = FakeMetadataApiClient(
        detail_payload={"id": 35746415, "name": "深空彼岸", "description": "豆瓣简介"},
    )
    provider = DoubanProvider(api, local_client=local)

    record = provider.get_detail(
        MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸"),
    )

    assert record.provider_id == "35746415"
    assert local.detail_calls == ["35746415"]
    assert api.detail_calls == ["35746415"]


def test_douban_provider_falls_back_when_local_detail_is_blocked() -> None:
    local = FakeLocalDoubanClient(detail_error=DoubanBlockedError("被禁止访问"))
    api = FakeMetadataApiClient(
        detail_payload={"id": 35746415, "name": "深空彼岸", "description": "豆瓣简介"},
    )
    provider = DoubanProvider(api, local_client=local)

    record = provider.get_detail(
        MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸"),
    )

    assert record.provider_id == "35746415"
    assert api.detail_calls == ["35746415"]
