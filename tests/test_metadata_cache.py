from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataRecord


def test_metadata_cache_round_trips_search_results(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    match = MetadataMatch(
        provider="douban",
        provider_id="35746415",
        title="深空彼岸",
        year="2026",
        score=0.98,
        raw={"dbid": 35746415},
    )

    cache.save_search("douban", "深空彼岸", "2026", [match])
    loaded = cache.load_search("douban", "深空彼岸", "2026", ttl_seconds=86400)

    assert loaded is not None
    assert loaded[0].provider_id == "35746415"


def test_metadata_cache_round_trips_detail_records(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        title="深空彼岸",
        year="2026",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    cache.save_detail("douban", "35746415", record)
    loaded = cache.load_detail("douban", "35746415", ttl_seconds=86400)

    assert loaded is not None
    assert loaded.overview == "豆瓣简介"
    assert loaded.douban_id == 35746415
