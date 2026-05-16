from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.hydrator import MetadataHydrator
from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataRecord
from atv_player.models import VodItem


class FakeProvider:
    def __init__(
        self,
        name: str,
        *,
        matches: list[MetadataMatch] | None = None,
        record: MetadataRecord | None = None,
        search_error: Exception | None = None,
        detail_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.matches = matches or []
        self.record = record
        self.search_error = search_error
        self.detail_error = detail_error
        self.search_calls = 0
        self.get_detail_calls: list[MetadataMatch] = []

    def can_enrich(self, _context: MetadataContext) -> bool:
        return True

    def search(self, _candidate) -> list[MetadataMatch]:
        self.search_calls += 1
        if self.search_error is not None:
            raise self.search_error
        return list(self.matches)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.get_detail_calls.append(match)
        if self.detail_error is not None:
            raise self.detail_error
        assert self.record is not None
        return self.record


def test_metadata_hydrator_uses_douban_when_plugin_provider_returns_no_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    plugin_provider = FakeProvider(
        "plugin",
        matches=[MetadataMatch(provider="plugin", provider_id="p1", title="插件标题")],
        record=MetadataRecord(provider="plugin", provider_id="p1", title="插件标题"),
    )
    douban_provider = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="d1", title="深空彼岸")],
        record=MetadataRecord(provider="douban", provider_id="d1", overview="豆瓣简介", rating="8.1"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[plugin_provider, douban_provider])
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_content="插件简介")

    updated = hydrator.hydrate(MetadataContext(vod=vod, source_kind="plugin"))

    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"


def test_metadata_hydrator_uses_cached_detail_without_recrawling(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "douban",
        "35746415",
        MetadataRecord(provider="douban", provider_id="35746415", overview="缓存简介", rating="8.1"),
    )
    douban_provider = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(provider="douban", provider_id="35746415", overview="不应命中", rating="9.9"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[douban_provider])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_content == "缓存简介"
    assert douban_provider.get_detail_calls == []


def test_metadata_hydrator_skips_provider_detail_failure_and_keeps_existing_vod(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    douban_provider = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸")],
        detail_error=RuntimeError("metadata补全失败: java.lang.NullPointerException"),
    )
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_content="原始简介")
    hydrator = MetadataHydrator(cache=cache, providers=[douban_provider])

    updated = hydrator.hydrate(MetadataContext(vod=vod, source_kind="browse"))

    assert updated.vod_name == "深空彼岸"
    assert updated.vod_content == "原始简介"
    assert douban_provider.get_detail_calls == [
        MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸")
    ]


def test_metadata_hydrator_keeps_douban_overview_but_uses_tmdb_visual_fields(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="35746415",
            overview="豆瓣简介",
            rating="8.1",
            douban_id=35746415,
        ),
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:42",
            poster="https://img.example/tmdb-poster.jpg",
            year="2026",
            overview="TMDB简介",
            rating="7.2",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[local_douban, tmdb])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert updated.vod_year == "2026"
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"


def test_metadata_hydrator_caches_empty_search_results_and_skips_repeat_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider("local_douban", matches=[])
    hydrator = MetadataHydrator(cache=cache, providers=[provider])
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse")

    first = hydrator.hydrate(context)
    second = hydrator.hydrate(context)

    assert first.vod_name == "深空彼岸"
    assert second.vod_name == "深空彼岸"
    assert provider.search_calls == 1
    assert provider.get_detail_calls == []
