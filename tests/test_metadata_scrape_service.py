from dataclasses import replace
from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.scrape import (
    MetadataScrapeCandidate,
    MetadataScrapeGroup,
    MetadataScrapeService,
    normalize_metadata_scrape_title,
)
from atv_player.metadata.providers.tencent import TencentMetadataProvider
from atv_player.models import PlayItem, PlaybackDetailField, VodItem


class FakeProvider:
    def __init__(self, name: str, *, matches=None, record=None, search_error: Exception | None = None) -> None:
        self.name = name
        self.matches = list(matches or [])
        self.record = record
        self.search_error = search_error
        self.search_calls: list[MetadataQuery] = []
        self.detail_calls: list[MetadataMatch] = []
        self.cache_key: tuple[str, str] | None = None

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

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str] | None:
        del candidate
        return self.cache_key


class FakeTMDBClient:
    def __init__(self, episodes: list[dict[str, object]]) -> None:
        self.episodes = episodes

    def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, object]:
        assert str(tmdb_id) == "42"
        assert season_number == 1
        return {"episodes": list(self.episodes)}


def test_normalize_metadata_scrape_title_strips_leading_media_prefix_and_episode_marker() -> None:
    assert normalize_metadata_scrape_title("📺 电视剧：雨霖铃 (2026) S01E04") == "雨霖铃 (2026)"


def test_normalize_metadata_scrape_title_keeps_bilingual_title_but_drops_release_noise_after_year() -> None:
    value = "木乃伊 Lee Cronin's The Mummy (2026) 4K高码.外挂繁体中字.2160p.AMZN.WEB-DL.HDR.H.265.DDP5.1.Atmos.mkv ( 14.8G )"

    assert normalize_metadata_scrape_title(value) == "木乃伊 Lee Cronin's The Mummy (2026)"


def test_normalize_metadata_scrape_title_strips_trailing_media_kind_suffix() -> None:
    assert normalize_metadata_scrape_title("仙剑奇侠传叁动漫") == "仙剑奇侠传叁"


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


def test_metadata_scrape_service_cache_only_reuses_cached_results_without_provider_calls(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cached_match = MetadataMatch(provider="tmdb", provider_id="movie:1", title="深空彼岸", year="2026")
    cache.save_search("tmdb", "深空彼岸", "2026", [cached_match])
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:2", title="不该触发实时搜索", year="2026")],
    )
    service = MetadataScrapeService(cache=cache, providers=[tmdb])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="", cache_only=True)

    assert groups == [
        MetadataScrapeGroup(
            provider="tmdb",
            provider_label="TMDB",
            items=[
                MetadataScrapeCandidate(
                    provider="tmdb",
                    provider_label="TMDB",
                    provider_id="movie:1",
                    title="深空彼岸",
                    year="2026",
                    subtitle="电影",
                )
            ],
        )
    ]
    assert tmdb.search_calls == []


def test_metadata_scrape_service_tencent_bypasses_stale_pre_area_box_empty_cache(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_search("tencent", "三体", "2023", [])
    post_calls = 0

    class JsonResponse:
        def json(self):
            return {
                "data": {
                    "normalList": {"itemList": []},
                    "areaBoxList": [
                        {
                            "itemList": [
                                {
                                    "doc": {"dataType": 2, "id": "mzc002007knmh3g"},
                                    "videoInfo": {
                                        "title": "三体",
                                        "year": 2023,
                                        "typeName": "电视剧",
                                        "episodeSites": [
                                            {
                                                "showName": "腾讯视频",
                                                "episodeInfoList": [
                                                    {
                                                        "url": "https://v.qq.com/x/cover/mzc002007knmh3g/i0045u918s5.html"
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    ],
                }
            }

    def fake_post(url: str, **kwargs):
        nonlocal post_calls
        post_calls += 1
        assert url == "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
        assert kwargs["json"]["query"] == "三体"
        return JsonResponse()

    service = MetadataScrapeService(cache=cache, providers=[TencentMetadataProvider(post=fake_post)])

    groups = service.search(MetadataQuery(title="三体", year="2023", category_name="剧集"), provider_filter="tencent")

    assert post_calls == 1
    assert [(item.title, item.year, item.provider_id) for item in groups[0].items] == [
        ("三体", "2023", "https://v.qq.com/x/cover/mzc002007knmh3g/i0045u918s5.html")
    ]


def test_metadata_scrape_service_filters_explicit_category_mismatches_for_manual_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:anime-1",
                title="仙剑奇侠传三",
                year="2025",
                raw={"channel": "动漫,4"},
            ),
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:anime-2",
                title="仙剑奇侠传三 特别篇",
                year="2025",
                raw={"category": {"value": "动画/奇幻"}},
            ),
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:drama-1",
                title="仙剑奇侠传三",
                year="2025",
                raw={"channel": "电视剧,2"},
            ),
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[iqiyi])

    groups = service.search(MetadataQuery(title="仙剑奇侠传3", year="2025", category_name="动漫"), provider_filter="")

    assert [item.provider_id for item in groups[0].items] == ["iqiyi:anime-1", "iqiyi:anime-2"]


def test_metadata_scrape_service_extracts_type_subtitle_from_provider_raw(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:movie-1",
                title="流浪地球",
                year="2019",
                raw={"channel": "电影,1", "s3": "电影类长视频"},
            )
        ],
    )
    tencent = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:anime-1",
                title="牧神记",
                year="2024",
                raw={"typeName": "动漫"},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[iqiyi, tencent])

    groups = service.search(MetadataQuery(title="测试", category_name=""), provider_filter="")

    assert groups[0].items[0].subtitle == "电影"
    assert groups[1].items[0].subtitle == "动漫"


def test_metadata_scrape_service_prefers_standard_type_subtitle_over_provider_specific_text(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss45969",
                title="牧神记",
                year="2024",
                raw={
                    "genres": ["动画", "奇幻"],
                    "subtitle": "国创 · 更新至第83话",
                },
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[bilibili])

    groups = service.search(MetadataQuery(title="牧神记", category_name="动漫"), provider_filter="")

    assert groups[0].items[0].subtitle == "动漫"


def test_metadata_scrape_service_prefers_explicit_selected_category_over_conflicting_type_name(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:anime-1",
                title="示例作品",
                year="2025",
                raw={"channel": "动漫,4"},
            ),
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:drama-1",
                title="示例作品",
                year="2025",
                raw={"channel": "电视剧,2"},
            ),
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[iqiyi])

    groups = service.search(
        MetadataQuery(title="示例作品", year="2025", category_name="剧集", type_name="动画"),
        provider_filter="",
    )

    assert [item.provider_id for item in groups[0].items] == ["iqiyi:drama-1"]


def test_metadata_scrape_service_can_build_episode_title_playlist_for_selected_candidate(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:1",
                title="米小圈上学记4",
                year="2026",
                raw={
                    "episode_sites": [
                        {
                            "episodeInfoList": [
                                {"title": "第01话 金银米小圈1"},
                                {"title": "第02话 金银米小圈2"},
                            ]
                        }
                    ]
                },
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
        preferred_candidate=MetadataScrapeCandidate(
            provider="tencent",
            provider_label="腾讯",
            provider_id="tx:1",
            title="米小圈上学记4",
            year="2026",
            raw=provider.matches[0].raw,
        ),
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tencent"
    assert updated[0].episode_display_title == "第1集 第01话 金银米小圈1"


def test_metadata_scrape_service_skips_movie_classified_candidate_for_episode_title_rewrite(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:1",
                title="长安的荔枝",
                year="2026",
                raw={
                    "category": {"value": "电影"},
                    "episode_sites": [
                        {
                            "episodeInfoList": [
                                {"title": "第01话 误匹配标题"},
                            ]
                        }
                    ],
                },
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="长安的荔枝", vod_year="2026", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
        preferred_candidate=MetadataScrapeCandidate(
            provider="tencent",
            provider_label="腾讯",
            provider_id="tx:1",
            title="长安的荔枝",
            year="2026",
            raw=provider.matches[0].raw,
        ),
    )

    assert updated is None


def test_metadata_scrape_service_prefers_selected_candidate_over_auto_priority(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tencent = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:1",
                title="米小圈上学记4",
                year="2026",
                raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 金银米小圈1"}]}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:42:season:1",
                title="米小圈上学记4",
                year="2026",
                raw={"episodes": [{"episode_number": 1, "name": "TMDB标题"}]},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[tencent, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", category_name="少儿"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
        preferred_candidate=MetadataScrapeCandidate(
            provider="tencent",
            provider_label="腾讯",
            provider_id="tx:1",
            title="米小圈上学记4",
            year="2026",
            raw=tencent.matches[0].raw,
        ),
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tencent"
    assert updated[0].episode_display_title == "第1集 第01话 金银米小圈1"


def test_metadata_scrape_service_auto_search_prefers_high_confidence_iqiyi_over_tmdb_and_tencent(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tencent = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:1",
                title="米小圈上学记4",
                year="2026",
                raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 金银米小圈1"}]}]},
            )
        ],
    )
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="米小圈上学记4",
                year="2026",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "终局开篇"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:42:season:1",
                title="米小圈上学记4",
                year="2026",
            )
        ],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[tencent, iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", category_name="少儿"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "iqiyi"
    assert updated[0].episode_display_title == "第1集 终局开篇"


def test_metadata_scrape_service_prefers_high_confidence_iqiyi_over_tmdb(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="临江仙",
                year="2025",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "iqiyi"
    assert updated[0].episode_display_title == "第1集 缘起"


def test_metadata_scrape_service_keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="临江仙 特别篇",
                year="2025",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第1集 TMDB标题"


def test_metadata_scrape_service_auto_search_prefers_bilibili_over_tmdb_tencent_and_iqiyi(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss45969",
                title="牧神记",
                year="2024",
                raw={"season_id": 45969, "season_type_name": "国创"},
            )
        ],
    )
    bilibili._hydrate_episode_candidate = lambda candidate: replace(
        candidate,
        raw={
            **candidate.raw,
            "episodes": [{"episode_number": 1, "long_title": "天黑别出门", "episode_type": "main", "sort": 1}],
        },
    )
    tencent = FakeProvider(
        "tencent",
        matches=[
            MetadataMatch(
                provider="tencent",
                provider_id="tx:1",
                title="牧神记",
                year="2024",
                raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 旧标题"}]}]},
            )
        ],
    )
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="牧神记",
                year="2024",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "爱奇艺标题"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:42:season:1",
                title="牧神记",
                year="2024",
            )
        ],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[bilibili, tencent, iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "bilibili"
    assert updated[0].episode_display_title == "第1集 天黑别出门"


def test_metadata_scrape_service_auto_search_prefers_confirmed_bilibili_over_tmdb(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss148433",
                title="凸变英雄X",
                year="2025",
                raw={"season_id": 148433, "season_type_name": "国创"},
            )
        ],
    )
    bilibili._hydrate_episode_candidate = lambda candidate: replace(
        candidate,
        raw={
            **candidate.raw,
            "episodes": [{"episode_number": 28, "long_title": "答案", "episode_type": "main", "sort": 28}],
        },
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="凸变英雄X", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 28, "name": ""}])
    service = MetadataScrapeService(cache=cache, providers=[bilibili, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫"),
        [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "bilibili"
    assert updated[0].episode_display_title == "第28集 答案"


def test_metadata_scrape_service_auto_search_falls_back_to_tmdb_when_bilibili_candidate_is_unconfirmed(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss148433",
                title="凸变英雄X",
                year="2025",
                raw={"season_type_name": "国创", "eps": [{"title": "28", "long_title": "摘要标题"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:315088:season:1",
                title="凸变英雄X",
                year="2025",
                raw={"episodes": [{"episode_number": 28, "name": "TMDB回退标题"}]},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[bilibili, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫"),
        [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第28集 TMDB回退标题"


def test_metadata_scrape_service_auto_search_prefers_bangumi_over_bilibili_tmdb_tencent_and_iqiyi(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bangumi = FakeProvider(
        "bangumi",
        matches=[
            MetadataMatch(
                provider="bangumi",
                provider_id="subject:1",
                title="牧神记",
                year="2024",
            )
        ],
    )
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss45969",
                title="牧神记",
                year="2024",
                raw={"eps": [{"title": "1", "index_title": "1", "long_title": "旧B站标题"}]},
            )
        ],
    )
    bangumi._client = type(
        "BangumiClient",
        (),
        {"get_episodes": lambda self, subject_id: [{"sort": 1, "type": 0, "name_cn": "天黑别出门"}]},
    )()
    service = MetadataScrapeService(cache=cache, providers=[bangumi, bilibili, FakeProvider("tmdb"), FakeProvider("tencent"), FakeProvider("iqiyi")])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "bangumi"
    assert updated[0].episode_display_title == "第1集 天黑别出门"


def test_metadata_scrape_service_provider_options_include_tencent_label(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(cache=cache, providers=[FakeProvider("bilibili"), FakeProvider("tencent")])

    assert service.provider_options() == [("bilibili", "B站"), ("tencent", "腾讯")]


def test_metadata_scrape_service_provider_options_include_sohu_label(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(cache=cache, providers=[FakeProvider("sohu"), FakeProvider("tmdb")])

    assert service.provider_options() == [("sohu", "搜狐视频"), ("tmdb", "TMDB")]


def test_metadata_scrape_service_provider_options_hide_bangumi_for_non_anime_query(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(cache=cache, providers=[FakeProvider("bangumi"), FakeProvider("tmdb")])

    options = service.provider_options(MetadataQuery(title="深空彼岸", category_name="电影"))

    assert ("bangumi", "Bangumi") not in options
    assert ("tmdb", "TMDB") in options


def test_metadata_scrape_service_provider_options_show_bangumi_for_anime_query(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(cache=cache, providers=[FakeProvider("bangumi"), FakeProvider("tmdb")])

    options = service.provider_options(MetadataQuery(title="牧神记", category_name="动漫"))

    assert ("bangumi", "Bangumi") in options


def test_metadata_scrape_service_episode_title_rewrite_ignores_sohu_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    sohu = FakeProvider(
        "sohu",
        matches=[
            MetadataMatch(
                provider="sohu",
                provider_id="http://tv.sohu.com/s2026/demo/",
                title="谁动了我的隐私",
                year="2026",
                raw={"videos": [{"video_order": 1, "video_name": "搜狐标题"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:42:season:1",
                title="谁动了我的隐私",
                year="2026",
                raw={"episodes": [{"episode_number": 1, "name": "TMDB标题"}]},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[sohu, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="谁动了我的隐私", vod_year="2026", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第1集 TMDB标题"
    assert sohu.search_calls == []


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


def test_metadata_scrape_service_uses_cached_search_results_before_retrying_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cached_match = MetadataMatch(provider="tmdb", provider_id="movie:1", title="深空彼岸", year="2026")
    cache.save_search("tmdb", "深空彼岸", "2026", [cached_match])
    broken = FakeProvider("tmdb", search_error=RuntimeError("tmdb timeout"))
    service = MetadataScrapeService(cache=cache, providers=[broken])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="")

    assert groups == [
        MetadataScrapeGroup(
            provider="tmdb",
            provider_label="TMDB",
            items=[
                MetadataScrapeCandidate(
                    provider="tmdb",
                    provider_label="TMDB",
                    provider_id="movie:1",
                    title="深空彼岸",
                    year="2026",
                    subtitle="电影",
                    raw={},
                )
            ],
        )
    ]
    assert broken.search_calls == []


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


def test_metadata_scrape_service_apply_still_replaces_poster_even_after_hydration_override_change(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:1",
            title="新标题",
            poster="https://img.example/tmdb-poster.jpg",
            overview="新简介",
            rating="7.8",
        ),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.apply(
        VodItem(
            vod_id="v1",
            vod_name="旧标题",
            vod_pic="https://img.example/old-poster.jpg",
            vod_content="旧简介",
            vod_remarks="9.9",
            metadata_field_sources={
                "poster": "local_douban",
                "overview": "local_douban",
                "rating": "local_douban",
            },
        ),
        MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id="movie:1",
            title="新标题",
            year="2026",
        ),
    )

    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert updated.vod_content == "新简介"
    assert updated.vod_remarks == "7.8"
    assert updated.metadata_field_sources["poster"] == "tmdb"
    assert updated.metadata_field_sources["overview"] == "tmdb"
    assert updated.metadata_field_sources["rating"] == "tmdb"


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


def test_metadata_scrape_service_reset_clears_search_cache_and_selected_detail_cache(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider("tmdb")
    tmdb.cache_key = ("黑袍纠察队", "")
    douban = FakeProvider("local_douban")
    cache.save_search("tmdb", "黑袍纠察队", "", [MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队")])
    cache.save_search("local_douban", "黑袍纠察队第五季", "2026", [MetadataMatch(provider="local_douban", provider_id="357", title="黑袍纠察队")])
    cache.save_detail("tmdb", "tv:42:season:5", MetadataRecord(provider="tmdb", provider_id="tv:42:season:5", overview="第五季简介"))
    cache.save_detail("local_douban", "357", MetadataRecord(provider="local_douban", provider_id="357", overview="豆瓣简介"))
    service = MetadataScrapeService(cache=cache, providers=[tmdb, douban])

    service.reset(
        MetadataQuery(title="黑袍纠察队第五季", year="2026", category_name="电视剧"),
        bound_provider="tmdb",
        bound_provider_id="tv:42:season:5",
        detail_keys=[("local_douban", "357")],
    )

    assert cache.load_search("tmdb", "黑袍纠察队", "", ttl_seconds=7 * 24 * 3600) is None
    assert cache.load_search("local_douban", "黑袍纠察队第五季", "2026", ttl_seconds=7 * 24 * 3600) is None
    assert cache.load_detail("tmdb", "tv:42:season:5", ttl_seconds=7 * 24 * 3600) is None
    assert cache.load_detail("local_douban", "357", ttl_seconds=7 * 24 * 3600) is None


def test_metadata_scrape_service_reset_clears_bilibili_direct_season_detail_cache(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider("bilibili")
    cache.save_detail(
        "bilibili",
        "https://www.bilibili.com/bangumi/play/ss45969",
        MetadataRecord(
            provider="bilibili",
            provider_id="https://www.bilibili.com/bangumi/play/ss45969",
            country="中国大陆",
        ),
    )
    service = MetadataScrapeService(cache=cache, providers=[bilibili])

    service.reset(
        MetadataQuery(
            title="牧神记",
            source_kind="bilibili",
            vod_id="ss45969",
        )
    )

    assert (
        cache.load_detail(
            "bilibili",
            "https://www.bilibili.com/bangumi/play/ss45969",
            ttl_seconds=7 * 24 * 3600,
        )
        is None
    )


def test_metadata_scrape_service_apply_raises_when_provider_returns_none(tmp_path: Path) -> None:
    import pytest

    class _NoneDetailProvider:
        name = "tmdb"

        def __init__(self) -> None:
            self.detail_calls: list[MetadataMatch] = []

        def can_enrich(self, _context) -> bool:
            return True

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return []

        def get_detail(self, match: MetadataMatch):
            self.detail_calls.append(match)
            return None

    cache = MetadataCache(tmp_path)
    provider = _NoneDetailProvider()
    service = MetadataScrapeService(cache=cache, providers=[provider])
    candidate = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="movie:1",
        title="深空彼岸",
        year="2026",
    )

    with pytest.raises(RuntimeError, match="TMDB"):
        service.apply(VodItem(vod_id="v1", vod_name="深空彼岸"), candidate)

    assert len(provider.detail_calls) == 1
    assert cache.load_detail("tmdb", "movie:1", ttl_seconds=7 * 24 * 3600) is None


def test_metadata_scrape_service_supports_async_provider_methods(tmp_path: Path) -> None:
    class AsyncProvider:
        name = "tmdb"

        def can_enrich(self, _context) -> bool:
            return True

        async def async_search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [
                MetadataMatch(
                    provider="tmdb",
                    provider_id="movie:1",
                    title=candidate.title,
                    year=candidate.year,
                )
            ]

        async def async_get_detail(self, match: MetadataMatch) -> MetadataRecord:
            return MetadataRecord(provider="tmdb", provider_id=match.provider_id, title=match.title)

    cache = MetadataCache(tmp_path)
    provider = AsyncProvider()
    service = MetadataScrapeService(cache=cache, providers=[provider])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="")

    assert [group.provider for group in groups] == ["tmdb"]
    assert groups[0].items[0].provider_id == "movie:1"
