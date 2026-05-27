from pathlib import Path

from atv_player.metadata.bindings import MetadataBindingRepository
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.hydrator import MetadataHydrator
from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataRecord
from atv_player.metadata.providers.local_douban import LocalDoubanProvider
from atv_player.models import (
    PlayItem,
    PlaybackDetailField,
    PlaybackDetailFieldAction,
    PlaybackDetailValuePart,
    VodItem,
)


class FakeProvider:
    def __init__(
        self,
        name: str,
        *,
        matches: list[MetadataMatch] | None = None,
        record: MetadataRecord | None = None,
        search_error: Exception | None = None,
        detail_error: Exception | None = None,
        can_enrich_result: bool = True,
    ) -> None:
        self.name = name
        self.matches = matches or []
        self.record = record
        self.search_error = search_error
        self.detail_error = detail_error
        self.can_enrich_result = can_enrich_result
        self.search_calls = 0
        self.search_queries: list[object] = []
        self.get_detail_calls: list[MetadataMatch] = []
        self.cache_key = None

    def can_enrich(self, _context: MetadataContext) -> bool:
        return self.can_enrich_result

    def search(self, candidate) -> list[MetadataMatch]:
        self.search_calls += 1
        self.search_queries.append(candidate)
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


def test_metadata_hydrator_uses_provider_detail_cache_key(tmp_path: Path) -> None:
    class VersionedDetailProvider(FakeProvider):
        def detail_cache_key(self, provider_id: str) -> str:
            return f"{provider_id}:metadata-v2"

    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "youku",
        "https://v.youku.com/v_show/id_old.html",
        MetadataRecord(provider="youku", provider_id="https://v.youku.com/v_show/id_old.html", overview="旧缓存"),
    )
    provider = VersionedDetailProvider(
        "youku",
        matches=[
            MetadataMatch(
                provider="youku",
                provider_id="https://v.youku.com/v_show/id_old.html",
                title="黑夜告白",
                score=1.0,
            )
        ],
        record=MetadataRecord(
            provider="youku",
            provider_id="https://v.youku.com/v_show/id_old.html",
            overview="新详情",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑夜告白", category_name="剧集"),
            source_kind="plugin",
        )
    )

    assert updated.vod_content == "新详情"
    assert len(provider.get_detail_calls) == 1
    assert (
        cache.load_detail(
            "youku",
            "https://v.youku.com/v_show/id_old.html:metadata-v2",
            ttl_seconds=7 * 24 * 3600,
        )
        is not None
    )


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


def test_metadata_hydrator_directly_uses_bilibili_season_id_for_bilibili_source(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili_provider = FakeProvider(
        "bilibili",
        record=MetadataRecord(
            provider="bilibili",
            provider_id="https://www.bilibili.com/bangumi/play/ss142986",
            title="B站番剧标题",
            poster="https://i0.hdslb.com/bfs/bangumi/image/season.png",
            overview="B站专用接口简介",
            genres=["国创"],
            detail_fields=[{"label": "更新状态", "value": "更新至第12话"}],
        ),
        can_enrich_result=False,
    )
    hydrator = MetadataHydrator(cache=cache, providers=[bilibili_provider])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="ss142986", vod_name="占位标题"),
            source_kind="bilibili",
        )
    )

    assert updated.vod_name == "B站番剧标题"
    assert updated.vod_pic == "https://i0.hdslb.com/bfs/bangumi/image/season.png"
    assert updated.vod_content == "B站专用接口简介"
    assert updated.type_name == "国创"
    assert [(field.label, field.value) for field in updated.detail_fields] == [("更新状态", "更新至第12话")]
    assert bilibili_provider.search_calls == 0
    assert bilibili_provider.get_detail_calls == [
        MetadataMatch(
            provider="bilibili",
            provider_id="https://www.bilibili.com/bangumi/play/ss142986",
            title="占位标题",
            raw={
                "provider_id": "https://www.bilibili.com/bangumi/play/ss142986",
                "season_id": "142986",
            },
        )
    ]


def test_metadata_hydrator_uses_bilibili_season_id_detail_field_for_bilibili_source(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili_provider = FakeProvider(
        "bilibili",
        record=MetadataRecord(
            provider="bilibili",
            provider_id="https://www.bilibili.com/bangumi/play/ss45969",
            title="牧神记",
            overview="B站专用接口简介",
        ),
        can_enrich_result=False,
    )
    hydrator = MetadataHydrator(cache=cache, providers=[bilibili_provider])
    vod = VodItem(
        vod_id="ep3537929",
        vod_name="牧神记",
        detail_fields=[
            PlaybackDetailField(
                label="Season ID",
                value_parts=[
                    PlaybackDetailValuePart(
                        label="45969",
                        action=PlaybackDetailFieldAction(type="link", value="season$45969", target="bilibili"),
                    )
                ],
            )
        ],
    )

    updated = hydrator.hydrate(MetadataContext(vod=vod, source_kind="bilibili"))

    assert updated.vod_content == "B站专用接口简介"
    assert [call.provider_id for call in bilibili_provider.get_detail_calls] == [
        "https://www.bilibili.com/bangumi/play/ss45969"
    ]
    assert bilibili_provider.search_calls == 0


def test_metadata_hydrator_supplements_bilibili_season_detail_with_other_providers(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili_provider = FakeProvider(
        "bilibili",
        matches=[MetadataMatch(provider="bilibili", provider_id="search-should-not-run", title="B站番剧标题")],
        record=MetadataRecord(
            provider="bilibili",
            provider_id="https://www.bilibili.com/bangumi/play/ss142986",
            title="B站番剧标题",
            poster="https://i0.hdslb.com/bfs/bangumi/image/bilibili.png",
            overview="B站专用接口简介",
            genres=["国创"],
            detail_fields=[{"label": "更新状态", "value": "更新至第12话"}],
        ),
    )
    bangumi_provider = FakeProvider(
        "bangumi",
        matches=[MetadataMatch(provider="bangumi", provider_id="bgm-1", title="B站番剧标题", score=1.0)],
        record=MetadataRecord(
            provider="bangumi",
            provider_id="bgm-1",
            title="B站番剧标题",
            rating="8.4",
            detail_fields=[{"label": "Bangumi ID", "value": "12345"}],
        ),
    )
    tmdb_provider = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:999", title="B站番剧标题", score=1.0)],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:999",
            title="B站番剧标题",
            poster="https://image.tmdb.org/t/p/original/poster.jpg",
            tmdb_id="999",
        ),
    )
    douban_provider = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="35746415", title="B站番剧标题", score=1.0)],
        record=MetadataRecord(
            provider="douban",
            provider_id="35746415",
            title="B站番剧标题",
            douban_id=35746415,
        ),
    )
    hydrator = MetadataHydrator(
        cache=cache,
        providers=[bangumi_provider, bilibili_provider, tmdb_provider, douban_provider],
    )

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="ss142986", vod_name="占位标题"),
            source_kind="bilibili",
        )
    )

    assert updated.vod_name == "B站番剧标题"
    assert updated.vod_content == "B站专用接口简介"
    assert updated.vod_pic == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert updated.vod_remarks == "8.4"
    assert updated.dbid == 35746415
    assert [(field.label, field.value) for field in updated.detail_fields] == [
        ("更新状态", "更新至第12话"),
        ("Bangumi ID", "12345"),
        ("TMDB ID", "999"),
    ]
    assert bilibili_provider.search_calls == 0
    assert [call.provider_id for call in bilibili_provider.get_detail_calls] == [
        "https://www.bilibili.com/bangumi/play/ss142986"
    ]
    assert bangumi_provider.search_calls == 1
    assert tmdb_provider.search_calls == 1
    assert douban_provider.search_calls == 1


def test_metadata_hydrator_refetches_stale_iqiyi_empty_detail_cache(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "iqiyi",
        "http://www.iqiyi.com/v_live_action.html",
        MetadataRecord(
            provider="iqiyi",
            provider_id="http://www.iqiyi.com/v_live_action.html",
            title="成何体统",
            year="2026",
        ),
    )
    iqiyi_provider = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="http://www.iqiyi.com/v_live_action.html",
                title="成何体统",
                raw={
                    "channel": "电视剧,2",
                    "promptDesc": "戏精联欢 胡闹开演",
                    "metaTags": [{"name": "古装爱情", "style": ""}],
                },
            )
        ],
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="http://www.iqiyi.com/v_live_action.html",
            title="成何体统",
            year="2026",
            overview="戏精联欢 胡闹开演",
            genres=["电视剧", "古装爱情"],
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[iqiyi_provider])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="成何体统"), source_kind="browse"))

    assert updated.vod_content == "戏精联欢 胡闹开演"
    assert updated.type_name == "电视剧 / 古装爱情"
    assert [(item.provider, item.provider_id, item.title) for item in iqiyi_provider.get_detail_calls] == [
        ("iqiyi", "http://www.iqiyi.com/v_live_action.html", "成何体统")
    ]


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


def test_metadata_hydrator_prefers_promoted_sohu_record_over_tmdb_but_keeps_tmdb_poster(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42", title="谁动了我的隐私", year="2026", score=1.17)],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            title="谁动了我的隐私",
            poster="https://img.example/tmdb-poster.jpg",
            overview="TMDB简介",
        ),
    )
    sohu = FakeProvider(
        "sohu",
        matches=[
            MetadataMatch(
                provider="sohu",
                provider_id="http://tv.sohu.com/s2026/dsjsdlwdys/",
                title="谁动了我的隐私",
                year="2026",
                score=1.52,
                raw={"sohu_preferred_over_tmdb": True},
            )
        ],
        record=MetadataRecord(
            provider="sohu",
            provider_id="http://tv.sohu.com/s2026/dsjsdlwdys/",
            title="谁动了我的隐私",
            overview="搜狐简介",
            genres=["悬疑", "剧情"],
            detail_fields=[{"label": "搜狐标签", "value": "自制 / 独播 / 独家"}],
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, sohu])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="谁动了我的隐私"), source_kind="browse"))

    assert updated.vod_content == "搜狐简介"
    assert updated.type_name == "悬疑 / 剧情"
    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert updated.detail_fields == []


def test_metadata_hydrator_keeps_tmdb_primary_when_sohu_is_exclusive_only_supplement(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42", title="如果可以这样爱", year="2019", score=1.17)],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            title="如果可以这样爱",
            overview="TMDB简介",
        ),
    )
    sohu = FakeProvider(
        "sohu",
        matches=[
            MetadataMatch(
                provider="sohu",
                provider_id="http://tv.sohu.com/s2019/ruguokeyizheyangai/",
                title="如果可以这样爱（DVD版）",
                year="2019",
                score=1.1,
                raw={"sohu_preferred_over_tmdb": False},
            )
        ],
        record=MetadataRecord(
            provider="sohu",
            provider_id="http://tv.sohu.com/s2019/ruguokeyizheyangai/",
            title="如果可以这样爱（DVD版）",
            detail_fields=[{"label": "搜狐标签", "value": "独家"}],
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, sohu])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="如果可以这样爱"), source_kind="browse"))

    assert updated.vod_content == "TMDB简介"
    assert updated.metadata_field_sources["overview"] == "tmdb"
    assert updated.detail_fields == []


def test_metadata_hydrator_prefers_current_item_media_title_for_query(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="36514978", title="成何体统")],
        record=MetadataRecord(provider="local_douban", provider_id="36514978", title="成何体统", overview="豆瓣简介"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="【C】成丨何体统"),
            source_kind="telegram",
            current_item=PlayItem(title="正片", url="https://media.example/movie.m3u8", media_title="成何体统 (2026)"),
        )
    )

    assert provider.search_queries[0].title == "成何体统"
    assert provider.search_queries[0].year == "2026"
    assert updated.vod_name == "成何体统"
    assert updated.vod_content == "豆瓣简介"


def test_metadata_hydrator_cleans_noisy_current_item_media_title_for_query(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="36514978", title="主角")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="36514978",
            title="主角",
            year="2026",
            overview="豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="4K - 01"),
            source_kind="telegram",
            current_item=PlayItem(
                title="4K - 01",
                url="https://media.example/1.m3u8",
                media_title="主角 (2026) [更新至17集] [4K高码率] [HDR] [内嵌简中] [张嘉益/刘浩存]",
            ),
        )
    )

    assert provider.search_queries[0].title == "主角"
    assert provider.search_queries[0].year == "2026"
    assert updated.vod_name == "主角"
    assert updated.vod_year == "2026"
    assert updated.vod_content == "豆瓣简介"


def test_metadata_hydrator_prefers_embedded_title_year_over_conflicting_vod_year(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="1295644", title="西游记", year="1986")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="1295644",
            title="西游记",
            year="1986",
            overview="央视版",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="西游记 (1986) 4K 2025年重新深度修复4K", vod_year="2025"),
            source_kind="telegram",
            current_item=PlayItem(
                title="正片",
                url="https://media.example/1.m3u8",
                media_title="西游记 (1986) 4K 2025年重新深度修复4K",
            ),
        )
    )

    assert provider.search_queries[0].title == "西游记"
    assert provider.search_queries[0].year == "1986"
    assert updated.vod_year == "1986"
    assert updated.vod_content == "央视版"


def test_metadata_hydrator_later_tmdb_overrides_existing_official_douban_poster(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    official_douban = FakeProvider(
        "official_douban",
        matches=[MetadataMatch(provider="official_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="official_douban",
            provider_id="35746415",
            poster="https://img.example/douban-poster.jpg",
            overview="豆瓣简介",
            rating="8.1",
        ),
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:42",
            poster="https://img.example/tmdb-hd-poster.jpg",
            overview="TMDB简介",
            rating="7.2",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[official_douban, tmdb])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-hd-poster.jpg"
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"
    assert updated.metadata_field_sources["poster"] == "tmdb"


def test_metadata_hydrator_later_lower_priority_provider_does_not_override_tmdb_poster(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:42",
            poster="https://img.example/tmdb-hd-poster.jpg",
            overview="TMDB简介",
        ),
    )
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="35746415",
            poster="https://img.example/douban-small-poster.jpg",
            overview="豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-hd-poster.jpg"
    assert updated.metadata_field_sources["poster"] == "tmdb"


def test_metadata_hydrator_local_douban_corrects_noisy_similar_title(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="成何体统")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="35746415",
            title="成何体统",
            overview="豆瓣简介",
            genres=["爱情", "古装"],
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[local_douban])

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="【C】成丨何体统"), source_kind="browse")
    )

    assert updated.vod_name == "成何体统"
    assert updated.vod_content == "豆瓣简介"


def test_metadata_hydrator_supports_async_provider_methods(tmp_path: Path) -> None:
    class AsyncProvider:
        name = "tmdb"

        def __init__(self) -> None:
            self.search_calls = 0
            self.detail_calls = 0

        def can_enrich(self, _context: MetadataContext) -> bool:
            return True

        async def async_search(self, candidate):
            self.search_calls += 1
            return [MetadataMatch(provider="tmdb", provider_id="movie:42", title=candidate.title)]

        async def async_get_detail(self, match):
            self.detail_calls += 1
            return MetadataRecord(
                provider="tmdb",
                provider_id=match.provider_id,
                title=match.title,
                overview="TMDB简介",
            )

    cache = MetadataCache(tmp_path)
    provider = AsyncProvider()
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse")
    )

    assert updated.vod_name == "深空彼岸"
    assert updated.vod_content == "TMDB简介"
    assert provider.search_calls == 1
    assert provider.detail_calls == 1


def test_metadata_hydrator_primes_local_douban_before_full_search_for_telegram_emby_and_jellyfin(tmp_path: Path) -> None:
    original_title = "努力克服自卑的我们 모두가 자신의 무가치함과 싸우고 있다"
    corrected_title = "努力克服自卑的我们"

    class DynamicTMDBProvider(FakeProvider):
        def search(self, candidate) -> list[MetadataMatch]:
            self.search_calls += 1
            self.search_queries.append(candidate)
            if candidate.title == corrected_title:
                return [MetadataMatch(provider="tmdb", provider_id="tv:42", title=corrected_title, year="2026", score=0.95)]
            return []

    for source_kind in ("telegram", "emby", "jellyfin"):
        cache = MetadataCache(tmp_path / source_kind)
        local_douban = FakeProvider(
            "local_douban",
            matches=[MetadataMatch(provider="local_douban", provider_id="37335468", title=corrected_title, year="2026", score=0.95)],
            record=MetadataRecord(
                provider="local_douban",
                provider_id="37335468",
                title=corrected_title,
                year="2026",
                overview="豆瓣简介",
            ),
        )
        tmdb = DynamicTMDBProvider(
            "tmdb",
            record=MetadataRecord(
                provider="tmdb",
                provider_id="tv:42",
                title=corrected_title,
                year="2026",
                poster="https://img.example/tmdb-poster.jpg",
            ),
        )
        hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

        updated = hydrator.hydrate(
            MetadataContext(
                vod=VodItem(vod_id="v1", vod_name=original_title, vod_year="2026"),
                source_kind=source_kind,
            )
        )

        assert updated.vod_name == corrected_title
        assert updated.vod_content == "豆瓣简介"
        assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
        assert [query.title for query in local_douban.search_queries] == [original_title, corrected_title]
        assert [query.title for query in tmdb.search_queries] == [corrected_title]


def test_metadata_hydrator_skips_local_douban_prime_when_year_conflicts_strongly(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="1890547", title="西游记", year="1978")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="1890547",
            title="西游记",
            year="1978",
            overview="错误自动结果",
        ),
    )
    tmdb = FakeProvider("tmdb", matches=[])
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="西游记 (1986) 4K 2025年重新深度修复4K", vod_year="2025"),
            source_kind="telegram",
            current_item=PlayItem(
                title="正片",
                url="https://media.example/1.m3u8",
                media_title="西游记 (1986) 4K 2025年重新深度修复4K",
            ),
        )
    )

    assert local_douban.search_queries[0].year == "1986"
    assert updated.vod_name == "西游记 (1986) 4K 2025年重新深度修复4K"
    assert updated.vod_year == "2025"
    assert updated.vod_content == ""


def test_metadata_hydrator_local_douban_prime_keeps_cleaner_original_title_when_record_title_is_noisier(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    original_title = "努力克服自卑的我们"
    noisier_title = "努力克服自卑的我们 모두가 자신의 무가치함과 싸우고 있다"

    class DynamicTMDBProvider(FakeProvider):
        def search(self, candidate) -> list[MetadataMatch]:
            self.search_calls += 1
            self.search_queries.append(candidate)
            if candidate.title == original_title:
                return [MetadataMatch(provider="tmdb", provider_id="tv:42", title=original_title, year="2026", score=0.95)]
            return []

    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="37335468", title=noisier_title, year="2026", score=0.95)],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="37335468",
            title=noisier_title,
            year="2026",
            overview="豆瓣简介",
        ),
    )
    tmdb = DynamicTMDBProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            title=original_title,
            year="2026",
            poster="https://img.example/tmdb-poster.jpg",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="8@swf2fkq3zrk@t58d", vod_year="2026"),
            source_kind="telegram",
            current_item=PlayItem(title="第1集", url="https://media.example/1.mp4", media_title=original_title),
        )
    )

    assert updated.vod_name == original_title
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert [query.title for query in local_douban.search_queries] == [original_title]
    assert [query.title for query in tmdb.search_queries] == [original_title]


def test_metadata_hydrator_skips_local_douban_prime_for_feiniu(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    original_title = "努力克服自卑的我们 모두가 자신의 무가치함과 싸우고 있다"
    corrected_title = "努力克服自卑的我们"

    class DynamicTMDBProvider(FakeProvider):
        def search(self, candidate) -> list[MetadataMatch]:
            self.search_calls += 1
            self.search_queries.append(candidate)
            if candidate.title == corrected_title:
                return [MetadataMatch(provider="tmdb", provider_id="tv:42", title=corrected_title, year="2026", score=0.95)]
            return []

    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="37335468", title=corrected_title, year="2026", score=0.95)],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="37335468",
            title=corrected_title,
            year="2026",
            overview="豆瓣简介",
        ),
    )
    tmdb = DynamicTMDBProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            title=corrected_title,
            year="2026",
            poster="https://img.example/tmdb-poster.jpg",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name=original_title, vod_year="2026"),
            source_kind="feiniu",
        )
    )

    assert updated.vod_name == corrected_title
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_pic == ""
    assert [query.title for query in local_douban.search_queries] == [original_title]
    assert [query.title for query in tmdb.search_queries] == [original_title]


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


def test_metadata_hydrator_uses_bilibili_binding_when_reopened_without_year(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path / "cache")
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("牧神记", "2024", provider="tmdb", provider_id="tv:999")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:should-not-search", title="牧神记")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:999",
            poster="https://image.tmdb.org/t/p/original/poster.jpg",
            rating="8.6",
        ),
    )
    bilibili = FakeProvider("bilibili", matches=[MetadataMatch(provider="bilibili", provider_id="bili", title="牧神记")])
    hydrator = MetadataHydrator(cache=cache, providers=[bilibili, tmdb], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="ss45969", vod_name="牧神记"),
            source_kind="bilibili",
        )
    )

    assert updated.vod_pic == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert updated.vod_remarks == "8.6"
    assert tmdb.search_calls == 0
    assert bilibili.search_calls == 0


def test_metadata_hydrator_prefers_bilibili_season_binding(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path / "cache")
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("bilibili:season:45969", "", provider="tmdb", provider_id="tv:999")
    bindings.save("牧神记", "2024", provider="tmdb", provider_id="tv:old")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:should-not-search", title="牧神记")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:999",
            poster="https://image.tmdb.org/t/p/original/season-bound.jpg",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb], binding_repository=bindings)
    vod = VodItem(
        vod_id="113410624718197-26615416714-1112253",
        vod_name="牧神记",
        vod_year="2024",
        detail_fields=[
            PlaybackDetailField(
                label="Season ID",
                value_parts=[
                    PlaybackDetailValuePart(
                        label="45969",
                        action=PlaybackDetailFieldAction(type="link", value="season$45969", target="bilibili"),
                    )
                ],
            )
        ],
    )

    updated = hydrator.hydrate(MetadataContext(vod=vod, source_kind="bilibili"))

    assert updated.vod_pic == "https://image.tmdb.org/t/p/original/season-bound.jpg"
    assert tmdb.search_calls == 0
    assert [call.provider_id for call in tmdb.get_detail_calls] == ["tv:999"]


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


def test_metadata_hydrator_manual_binding_survives_noisy_title_with_embedded_year(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save(
        "西游记 (1986) 4K 2025年重新深度修复4K",
        "",
        provider="tmdb",
        provider_id="tv:42",
    )
    tmdb = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42",
            poster="https://img.example/journey-poster.jpg",
            year="1986",
            overview="手动绑定简介",
        ),
    )
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="1978-jp", title="西游记", year="1978")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="1978-jp",
            title="西游记",
            year="1978",
            overview="错误自动结果",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="西游记 (1986) 4K 2025年重新深度修复4K"),
            source_kind="telegram",
            current_item=PlayItem(
                title="正片",
                url="https://media.example/1.m3u8",
                media_title="西游记 (1986) 4K 2025年重新深度修复4K",
            ),
        )
    )

    assert updated.vod_pic == "https://img.example/journey-poster.jpg"
    assert updated.vod_year == "1986"
    assert updated.vod_content == "手动绑定简介"
    assert local_douban.search_calls == 0


def test_metadata_hydrator_remote_auto_search_ignores_prefilled_dbid_for_local_douban_prime(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="1295644", title="西游记", year="1986", score=0.95)],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="1295644",
            title="西游记",
            year="1986",
            overview="央视版西游记",
            douban_id=1295644,
        ),
    )
    tmdb = FakeProvider("tmdb", matches=[])
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="S01E01", dbid=1890547),
            source_kind="telegram",
            current_item=PlayItem(
                title="S01E01",
                url="https://media.example/1.m3u8",
                media_title="西游记 (1986) 4K 2025年重新深度修复4K",
            ),
        )
    )

    assert local_douban.search_calls == 1
    assert [query.vod_dbid for query in local_douban.search_queries] == [0]
    assert [query.title for query in local_douban.search_queries] == ["西游记"]
    assert [query.year for query in local_douban.search_queries] == ["1986"]
    assert updated.vod_name == "西游记"
    assert updated.vod_year == "1986"
    assert updated.dbid == 1295644
    assert updated.vod_content == "央视版西游记"


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


def test_metadata_hydrator_prefers_dbid_douban_match_over_generic_season_title_tmdb(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)

    class FakeApiClient:
        def get_douban_metadata_detail(self, provider_id: str) -> dict[str, object]:
            assert provider_id == "35564470"
            return {
                "id": 35564470,
                "name": "与凤行",
                "year": "2024",
                "genre": "剧情,爱情,奇幻",
                "country": "中国大陆",
                "language": "汉语普通话",
                "directors": "邓科",
                "actors": "赵丽颖,林更新,辛云来",
                "description": "豆瓣简介",
            }

    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:286342:season:1",
                title="Season 1",
                year="2024",
            )
        ],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:286342:season:1",
            title="Season 1",
            year="2024",
            genres=["剧情"],
            country="美国",
            language="英语",
            directors=["凯特·凯罗"],
            actors=["凯西·贝茨"],
            overview="错误简介",
        ),
    )
    douban = LocalDoubanProvider(FakeApiClient())
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(
                vod_id="v1",
                vod_name="Season 1",
                vod_year="2024",
                dbid=35564470,
            ),
            source_kind="plugin",
        )
    )

    assert updated.vod_name == "与凤行"
    assert updated.type_name == "剧情 / 爱情 / 奇幻"
    assert updated.vod_area == "中国大陆"
    assert updated.vod_director == "邓科"
    assert updated.vod_actor == "赵丽颖,林更新,辛云来"
    assert updated.dbid == 35564470
    assert tmdb.get_detail_calls == []


def test_metadata_hydrator_bound_iqiyi_record_overrides_garbage_title(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("J【加@页】", "", provider="iqiyi", provider_id="iqiyi:1", matched_title="国色芳华")
    iqiyi = FakeProvider(
        "iqiyi",
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="iqiyi:1",
            title="国色芳华",
            year="2026",
            overview="爱奇艺简介",
            actors=["杨紫", "韩东君"],
            genres=["古装", "励志"],
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[iqiyi], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="J【加@页】"), source_kind="browse")
    )

    assert updated.vod_name == "国色芳华"
    assert updated.vod_year == "2026"
    assert updated.vod_content == "爱奇艺简介"
    assert updated.vod_actor == "杨紫,韩东君"


def test_metadata_hydrator_bound_iqiyi_record_overrides_custom_user_title(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("我的电视剧", "", provider="iqiyi", provider_id="iqiyi:1", matched_title="国色芳华")
    iqiyi = FakeProvider(
        "iqiyi",
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="iqiyi:1",
            title="国色芳华",
            year="2026",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[iqiyi], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="我的电视剧"), source_kind="browse")
    )

    assert updated.vod_name == "国色芳华"


def test_metadata_hydrator_auto_iqiyi_match_corrects_garbage_title(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="国色芳华",
                year="2026",
                score=1.0,
                raw={"channel": "电视剧,2"},
            )
        ],
        record=MetadataRecord(
            provider="iqiyi",
            provider_id="iqiyi:1",
            title="国色芳华",
            year="2026",
            overview="爱奇艺简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[iqiyi])

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="国色芳华【加@页】"), source_kind="browse")
    )

    assert updated.vod_name == "国色芳华"
    assert updated.vod_content == "爱奇艺简介"
