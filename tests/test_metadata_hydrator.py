from pathlib import Path

from atv_player.metadata.bindings import MetadataBindingRepository
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
        self.cache_key = None

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

    def search_cache_key(self, candidate):
        if self.cache_key is None:
            return None
        return self.cache_key


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
    assert [(item.provider, item.provider_id, item.title) for item in douban_provider.get_detail_calls] == [
        ("douban", "35746415", "深空彼岸")
    ]


def test_metadata_hydrator_keeps_official_douban_overview_but_uses_tmdb_visual_fields(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    official_douban = FakeProvider(
        "official_douban",
        matches=[MetadataMatch(provider="official_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="official_douban",
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
    hydrator = MetadataHydrator(cache=cache, providers=[official_douban, tmdb])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert updated.vod_year == "2026"
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"


def test_metadata_hydrator_prefers_tmdb_season_over_local_douban_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="357",
            overview="本地豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "第五季简介"


def test_metadata_hydrator_tmdb_season_primary_is_not_overridden_by_official_douban(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    official_douban = FakeProvider(
        "official_douban",
        matches=[MetadataMatch(provider="official_douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="official_douban",
            provider_id="357",
            overview="豆瓣官方简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, official_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "第五季简介"


def test_metadata_hydrator_non_season_tmdb_overview_still_loses_to_douban(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            overview="整剧简介",
        ),
    )
    douban = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="douban",
            provider_id="357",
            overview="豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "豆瓣简介"


def test_metadata_hydrator_tmdb_season_overview_beats_douban(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    douban = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="douban",
            provider_id="357",
            overview="豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "第五季简介"


def test_metadata_hydrator_skips_incompatible_secondary_anime_record_after_live_action_primary(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    tencent = FakeProvider(
        "tencent",
        matches=[MetadataMatch(provider="tencent", provider_id="tx:1", title="成何体统", score=1.0)],
        record=MetadataRecord(
            provider="tencent",
            provider_id="tx:1",
            title="成何体统",
            genres=["电视剧", "古装"],
            overview="真人版简介",
        ),
    )
    bangumi = FakeProvider(
        "bangumi",
        matches=[MetadataMatch(provider="bangumi", provider_id="subject:1", title="成何体统 第二季", score=0.99)],
        record=MetadataRecord(
            provider="bangumi",
            provider_id="subject:1",
            title="成何体统 第二季",
            genres=["动漫"],
            rating="8.8",
            overview="动漫版简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tencent, bangumi])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="成何体统"),
            source_kind="browse",
        )
    )

    assert updated.type_name == "电视剧 / 古装"
    assert updated.vod_content == "真人版简介"
    assert updated.vod_remarks == ""
    assert bangumi.get_detail_calls == []


def test_metadata_hydrator_uses_primary_match_kind_when_primary_record_lacks_genres(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="成何体统",
                score=1.0,
                raw={"channel": "电视剧,2"},
            )
        ],
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="iqiyi:1",
            title="成何体统",
            overview="真人版简介",
        ),
    )
    bangumi = FakeProvider(
        "bangumi",
        matches=[MetadataMatch(provider="bangumi", provider_id="subject:1", title="成何体统 第二季", score=0.99)],
        record=MetadataRecord(
            provider="bangumi",
            provider_id="subject:1",
            title="成何体统 第二季",
            genres=["动漫"],
            rating="8.8",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[iqiyi, bangumi])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="成何体统"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "真人版简介"
    assert updated.vod_remarks == ""
    assert bangumi.get_detail_calls == []


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


def test_metadata_hydrator_uses_provider_specific_search_cache_key(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_search("tmdb", "掩耳盗邻第二季", "2025", [])
    provider = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42", title="掩耳盗邻", year="2025")],
        record=MetadataRecord(provider="tmdb", provider_id="tv:42", poster="https://img.example/poster.jpg"),
    )
    provider.cache_key = ("掩耳盗邻", "2025")
    hydrator = MetadataHydrator(cache=cache, providers=[provider])
    context = MetadataContext(
        vod=VodItem(vod_id="v1", vod_name="掩耳盗邻第二季", vod_year="2025", category_name="电视剧"),
        source_kind="plugin",
    )

    updated = hydrator.hydrate(context)

    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert provider.search_calls == 1


def test_metadata_hydrator_prefers_manual_binding_before_provider_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:99", title="错误结果")],
        record=MetadataRecord(provider="tmdb", provider_id="tv:42", poster="https://img.example/poster.jpg"),
    )
    douban = FakeProvider("local_douban", matches=[])
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"), source_kind="browse")
    )

    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert tmdb.search_calls == 0


def test_metadata_hydrator_manual_binding_blocks_other_provider_overrides(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    tmdb = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            poster="https://img.example/manual-poster.jpg",
            overview="手动绑定简介",
            rating="9.2",
        ),
    )
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="35746415",
            overview="自动搜索简介",
            rating="8.1",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"), source_kind="browse")
    )

    assert updated.vod_pic == "https://img.example/manual-poster.jpg"
    assert updated.vod_content == "手动绑定简介"
    assert updated.vod_remarks == "9.2"
    assert douban.search_calls == 0
    assert douban.get_detail_calls == []


def test_metadata_hydrator_deletes_invalid_manual_binding_and_falls_back_to_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:99", title="深空彼岸")],
        record=MetadataRecord(provider="tmdb", provider_id="tv:99", poster="https://img.example/recovered.jpg"),
        detail_error=RuntimeError("detail missing"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"), source_kind="browse")
    )

    assert bindings.load("深空彼岸", "2026") is None
    assert updated.vod_name == "深空彼岸"


def test_metadata_hydrator_uses_highest_scored_primary_match_and_only_fills_missing_fields_from_supplements(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:404", title="错误结果", year="2026", score=0.1)],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:404",
            poster="https://img.example/wrong-poster.jpg",
            overview="错误简介",
        ),
    )
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(provider="iqiyi", provider_id="iqiyi:s1", title="剑来", year="2024", score=0.4),
            MetadataMatch(provider="iqiyi", provider_id="iqiyi:s2", title="剑来 第二季", year="2025", score=1.2),
        ],
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="iqiyi:s2",
            overview="爱奇艺简介",
            year="2025",
            actors=["演员甲"],
        ),
    )
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="357", title="剑来 第二季", year="2025", score=0.95)],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="357",
            overview="豆瓣简介",
            rating="8.8",
            poster="https://img.example/right-poster.jpg",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, iqiyi, douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="剑来 第二季", vod_year="2025", category_name="动漫"),
            source_kind="browse",
        )
    )

    assert iqiyi.get_detail_calls[0].provider_id == "iqiyi:s2"
    assert tmdb.get_detail_calls == []
    assert updated.vod_content == "爱奇艺简介"
    assert updated.vod_year == "2025"
    assert updated.vod_actor == "演员甲"
    assert updated.vod_pic == "https://img.example/right-poster.jpg"
    assert updated.vod_remarks == "8.8"
