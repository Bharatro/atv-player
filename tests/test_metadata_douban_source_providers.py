from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.local_douban import OfficialDoubanProvider
from atv_player.metadata.providers.local_douban_client import DoubanBlockedError
from atv_player.metadata.providers.remote_douban import LocalDoubanProvider


class FakeLocalClient:
    def __init__(
        self,
        *,
        search_results=None,
        detail_result=None,
        search_error=None,
        detail_error=None,
    ) -> None:
        self.search_results = list(search_results or [])
        self.detail_result = detail_result
        self.search_error = search_error
        self.detail_error = detail_error

    def search(self, title: str, year: str = "") -> list[dict]:
        if self.search_error is not None:
            raise self.search_error
        return list(self.search_results)

    def get_detail(self, dbid: str) -> dict | None:
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result


class FakeRemoteApi:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str]] = []

    def search_douban_metadata(self, title: str, year: str = "") -> dict:
        self.search_calls.append((title, year))
        return {"items": [{"id": 35746415, "name": title, "year": year or 2026}]}

    def get_douban_metadata_detail(self, dbid: str) -> dict:
        return {"id": dbid, "name": "深空彼岸", "description": "远程豆瓣简介", "dbScore": "8.1"}


def test_local_douban_provider_returns_no_matches_when_blocked() -> None:
    provider = OfficialDoubanProvider(FakeLocalClient(search_error=DoubanBlockedError("blocked")))

    assert provider.search(MetadataQuery(title="深空彼岸", year="2026")) == []


def test_remote_douban_provider_maps_search_and_detail_from_api() -> None:
    provider = LocalDoubanProvider(FakeRemoteApi())

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))
    record = provider.get_detail(matches[0])

    assert matches == [
        MetadataMatch(provider="remote_douban", provider_id="35746415", title="深空彼岸", year="2026")
    ]
    assert record.provider == "remote_douban"
    assert record.overview == "远程豆瓣简介"
    assert record.rating == "8.1"


def test_local_douban_provider_normalizes_season_title_before_api_search() -> None:
    api = FakeRemoteApi()
    provider = LocalDoubanProvider(api)

    provider.search(MetadataQuery(title="黑袍纠察队第五季", year=""))

    assert api.search_calls == [("黑袍纠察队 第五季", "")]
