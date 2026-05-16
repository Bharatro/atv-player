from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeService
from atv_player.models import PlaybackDetailField, VodItem


class FakeProvider:
    def __init__(self, name: str, *, matches=None, record=None, search_error: Exception | None = None) -> None:
        self.name = name
        self.matches = list(matches or [])
        self.record = record
        self.search_error = search_error
        self.search_calls: list[MetadataQuery] = []
        self.detail_calls: list[MetadataMatch] = []

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls.append(candidate)
        if self.search_error is not None:
            raise self.search_error
        return list(self.matches)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls.append(match)
        assert self.record is not None
        return self.record


def test_metadata_scrape_service_groups_parallel_results_by_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:1", title="深空彼岸", year="2026")],
    )
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸", year="2026")],
    )
    service = MetadataScrapeService(cache=cache, providers=[tmdb, douban])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="")

    assert [group.provider for group in groups] == ["tmdb", "local_douban"]
    assert groups[0].items[0].provider_id == "movie:1"
    assert groups[1].items[0].provider_id == "35746415"


def test_metadata_scrape_service_keeps_failed_provider_group_for_all_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    broken = FakeProvider("tmdb", search_error=RuntimeError("tmdb timeout"))
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
    )
    service = MetadataScrapeService(cache=cache, providers=[broken, douban])

    groups = service.search(MetadataQuery(title="深空彼岸"), provider_filter="")

    assert groups[0].provider == "tmdb"
    assert groups[0].error_text == "tmdb timeout"
    assert groups[0].items == []
    assert groups[1].provider == "local_douban"
    assert groups[1].items[0].provider_id == "35746415"


def test_metadata_scrape_service_apply_uses_cached_detail_before_fetching_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "tmdb",
        "movie:1",
        MetadataRecord(provider="tmdb", provider_id="movie:1", poster="https://img.example/poster.jpg"),
    )
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(provider="tmdb", provider_id="movie:1", poster="https://img.example/new.jpg"),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])
    candidate = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="movie:1",
        title="深空彼岸",
        year="2026",
    )

    updated = service.apply(VodItem(vod_id="v1", vod_name="深空彼岸"), candidate)

    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert provider.detail_calls == []


def test_metadata_scrape_service_apply_replaces_all_metadata_fields_from_selected_result(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:1",
            title="新标题",
            year="2026",
            poster="https://img.example/poster.jpg",
            overview="新简介",
            genres=["动画"],
            detail_fields=[{"label": "TMDB ID", "value": "1"}],
        ),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])
    candidate = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="movie:1",
        title="新标题",
        year="2026",
    )

    updated = service.apply(
        VodItem(
            vod_id="v1",
            vod_name="旧标题",
            vod_pic="https://img.example/old.jpg",
            vod_content="旧简介",
            vod_year="2024",
            vod_area="中国大陆",
            vod_lang="汉语普通话",
            vod_director="旧导演",
            vod_actor="旧演员",
            vod_remarks="9.9",
            type_name="剧情",
            dbid=12345,
            detail_fields=[PlaybackDetailField(label="旧字段", value="旧值")],
            metadata_field_sources={
                "poster": "local_douban",
                "overview": "local_douban",
                "year": "local_douban",
                "country": "local_douban",
                "language": "local_douban",
                "directors": "local_douban",
                "actors": "local_douban",
                "rating": "local_douban",
                "genres": "local_douban",
                "detail_fields": "local_douban",
                "douban_id": "local_douban",
            },
        ),
        candidate,
    )

    assert updated.vod_name == "新标题"
    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert updated.vod_content == "新简介"
    assert updated.vod_year == "2026"
    assert updated.type_name == "动画"
    assert updated.vod_area == ""
    assert updated.vod_lang == ""
    assert updated.vod_director == ""
    assert updated.vod_actor == ""
    assert updated.vod_remarks == ""
    assert updated.dbid == 0
    assert [(field.label, field.value) for field in updated.detail_fields] == [("TMDB ID", "1")]


def test_metadata_scrape_service_apply_uses_distinct_tmdb_tv_season_cache_keys(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            title="黑袍纠察队",
            overview="第五季简介",
        ),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.apply(
        VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_content="旧简介"),
        MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id="tv:42:season:5",
            title="黑袍纠察队",
            year="2019",
        ),
    )

    assert updated.vod_content == "第五季简介"
    assert provider.detail_calls[0].provider_id == "tv:42:season:5"
