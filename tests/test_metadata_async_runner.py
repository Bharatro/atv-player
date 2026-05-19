import asyncio

from atv_player.metadata.async_runner import run_provider_detail, run_provider_searches
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class SyncProvider:
    name = "sync"

    def __init__(self) -> None:
        self.search_calls = 0
        self.detail_calls = 0

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls += 1
        return [MetadataMatch(provider="sync", provider_id="1", title=candidate.title)]

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls += 1
        return MetadataRecord(provider="sync", provider_id=match.provider_id, title=match.title)


class AsyncProvider:
    name = "async"

    def __init__(self) -> None:
        self.search_calls = 0
        self.detail_calls = 0

    async def async_search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls += 1
        await asyncio.sleep(0)
        return [MetadataMatch(provider="async", provider_id="2", title=candidate.title)]

    async def async_get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls += 1
        await asyncio.sleep(0)
        return MetadataRecord(provider="async", provider_id=match.provider_id, title=match.title)


def test_run_provider_searches_uses_async_search_when_available() -> None:
    provider = AsyncProvider()

    results = run_provider_searches([provider], MetadataQuery(title="深空彼岸", year="2026"))

    assert len(results) == 1
    assert results[0].provider is provider
    assert results[0].matches[0].provider == "async"
    assert results[0].error is None
    assert provider.search_calls == 1


def test_run_provider_searches_falls_back_to_sync_search() -> None:
    provider = SyncProvider()

    results = run_provider_searches([provider], MetadataQuery(title="成何体统", year="2026"))

    assert len(results) == 1
    assert results[0].provider is provider
    assert results[0].matches[0].provider == "sync"
    assert results[0].error is None
    assert provider.search_calls == 1


def test_run_provider_detail_uses_async_get_detail_when_available() -> None:
    provider = AsyncProvider()
    match = MetadataMatch(provider="async", provider_id="2", title="牧神记")

    record = run_provider_detail(provider, match)

    assert record.provider == "async"
    assert record.provider_id == "2"
    assert provider.detail_calls == 1


def test_run_provider_searches_collects_provider_error_without_failing_whole_batch() -> None:
    class BrokenProvider(SyncProvider):
        name = "broken"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            raise RuntimeError(f"boom:{candidate.title}")

    good = SyncProvider()
    bad = BrokenProvider()

    results = run_provider_searches([bad, good], MetadataQuery(title="剑来", year=""))

    assert results[0].provider is bad
    assert isinstance(results[0].error, RuntimeError)
    assert results[0].matches == []
    assert results[1].provider is good
    assert results[1].error is None
    assert results[1].matches[0].title == "剑来"
