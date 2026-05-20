from pathlib import Path

import atv_player.metadata.cache as metadata_cache_module
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


def test_metadata_cache_round_trips_empty_search_results(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)

    cache.save_search("douban", "查无此片", "2026", [])
    loaded = cache.load_search("douban", "查无此片", "2026", ttl_seconds=86400, empty_ttl_seconds=3600)

    assert loaded == []


def test_metadata_cache_expires_empty_search_results_with_shorter_ttl(tmp_path: Path, monkeypatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(metadata_cache_module, "time", lambda: clock["now"])
    cache = MetadataCache(tmp_path)

    cache.save_search("douban", "查无此片", "2026", [])
    assert cache.load_search("douban", "查无此片", "2026", ttl_seconds=86400, empty_ttl_seconds=3600) == []

    clock["now"] += 3601

    assert cache.load_search("douban", "查无此片", "2026", ttl_seconds=86400, empty_ttl_seconds=3600) is None


def test_metadata_cache_round_trips_generic_payload(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)

    cache.save_payload("tmdb_episode_search", "掩耳盗邻\x1f", [{"id": 42, "name": "掩耳盗邻"}])

    loaded = cache.load_payload("tmdb_episode_search", "掩耳盗邻\x1f", ttl_seconds=86400)

    assert loaded == [{"id": 42, "name": "掩耳盗邻"}]


def test_metadata_cache_expires_empty_generic_payload_with_shorter_ttl(tmp_path: Path, monkeypatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(metadata_cache_module, "time", lambda: clock["now"])
    cache = MetadataCache(tmp_path)

    cache.save_payload("tmdb_episode_search", "查无此剧\x1f", [])
    assert cache.load_payload(
        "tmdb_episode_search",
        "查无此剧\x1f",
        ttl_seconds=86400,
        empty_ttl_seconds=3600,
    ) == []

    clock["now"] += 3601

    assert (
        cache.load_payload(
            "tmdb_episode_search",
            "查无此剧\x1f",
            ttl_seconds=86400,
            empty_ttl_seconds=3600,
        )
        is None
    )


def test_metadata_cache_delete_payload_namespace_removes_only_target_namespace(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)

    cache.save_payload("tmdb_episode_search", "家业\x1f2026", [{"id": 275966}])
    cache.save_payload("episode_title_playlist", "playlist", {"order": [0], "titles": [{"display": "第7集"}]})
    cache.save_payload("other_namespace", "keep-me", {"ok": True})

    cache.delete_payload_namespace("tmdb_episode_search")

    assert cache.load_payload("tmdb_episode_search", "家业\x1f2026", ttl_seconds=86400) is None
    assert cache.load_payload("episode_title_playlist", "playlist", ttl_seconds=86400) == {
        "order": [0],
        "titles": [{"display": "第7集"}],
    }
    assert cache.load_payload("other_namespace", "keep-me", ttl_seconds=86400) == {"ok": True}
