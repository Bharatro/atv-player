# ruff: noqa: E501
from atv_player.controllers.following_controller import FollowingController
from atv_player.following_metadata import (
    FollowingMetadataGateway,
    build_following_from_candidate,
    build_following_from_metadata_candidate,
    build_snapshot_from_record,
    compute_episode_counts,
    following_candidate_from_url,
    following_provider_priority,
    merge_following_snapshot,
)
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    FollowingSeason,
)
from atv_player.metadata.models import MetadataMatch, MetadataRecord
from atv_player.metadata.providers.tmdb import TMDBProvider
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup


def test_following_provider_priority_prefers_bangumi_for_anime() -> None:
    assert following_provider_priority("anime") == ["bangumi", "tmdb", "douban"]
    assert following_provider_priority("live_action") == ["tmdb", "douban", "bangumi"]


def test_following_detail_snapshot_defaults_to_empty_metadata_bundle() -> None:
    snapshot = FollowingDetailSnapshot()

    assert snapshot.metadata_bundle is None


def test_following_metadata_bundle_keeps_merged_default_source_key() -> None:
    from atv_player.following_models import (
        FollowingMetadataBundle,
        FollowingMetadataSourceSnapshot,
        FollowingRatingEntry,
    )

    bundle = FollowingMetadataBundle(
        merged_snapshot=FollowingMetadataSourceSnapshot(
            source_key="merged",
            provider="merged",
            provider_label="合并",
        ),
        source_snapshots={
            "merged": FollowingMetadataSourceSnapshot(
                source_key="merged",
                provider="merged",
                provider_label="合并",
            ),
            "tmdb": FollowingMetadataSourceSnapshot(
                source_key="tmdb",
                provider="tmdb",
                provider_label="TMDB",
                ratings=[FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1")],
            ),
        },
        available_source_keys=["merged", "tmdb"],
        default_source_key="merged",
    )

    assert bundle.default_source_key == "merged"
    assert bundle.available_source_keys == ["merged", "tmdb"]
    assert bundle.source_snapshots["tmdb"].ratings[0].value == "8.1"


def test_following_playback_platform_entry_can_represent_link_only_platform() -> None:
    from atv_player.following_models import FollowingPlaybackPlatformEntry

    entry = FollowingPlaybackPlatformEntry(
        provider="iqiyi",
        label="爱奇艺",
        url="https://www.iqiyi.com/a_19rrn1.html",
    )

    assert entry.latest_episode == 0
    assert entry.update_time_text == ""
    assert entry.status_text == ""


def test_build_following_metadata_bundle_keeps_tmdb_primary_and_adds_douban_bangumi_ratings() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:272432:season:1",
        title="凡人修仙传",
        tmdb_id="272432",
        rating="8.1",
        poster="tmdb-poster",
        backdrop="tmdb-backdrop",
        overview="TMDB简介",
        genres=["动画"],
        detail_fields=[
            {
                "label": "watch_providers",
                "value": [
                    {
                        "provider": "iqiyi",
                        "label": "爱奇艺",
                        "url": "https://www.iqiyi.com/a_1.html",
                    }
                ],
            },
            {"label": "episodes", "value": [{"episode_number": 128, "name": "新章"}]},
        ],
    )
    douban_record = MetadataRecord(
        provider="douban",
        provider_id="35517044",
        title="凡人修仙传",
        rating="7.9",
        overview="豆瓣简介",
        directors=["刘海波"],
    )
    bangumi_record = MetadataRecord(
        provider="bangumi",
        provider_id="subject:1",
        title="凡人修仙传",
        rating="8.4",
        aliases=["凡人修仙传 动画版"],
    )
    iqiyi_record = MetadataRecord(
        provider="iqiyi",
        provider_id="iqiyi:album:1",
        title="凡人修仙传",
        detail_fields=[
            {"label": "播放链接", "value": "https://www.iqiyi.com/a_1.html"},
            {"label": "更新时间", "value": "2026-05-25"},
            {"label": "更新状态", "value": "更新至第128集"},
            {"label": "最新集数", "value": "128"},
        ],
    )

    bundle, merged_record, merged_snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="凡人修仙传",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:272432",
            external_ids={"tmdb": "272432"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={
            "douban": (douban_record, 0.92),
            "bangumi": (bangumi_record, 0.94),
            "iqiyi": (iqiyi_record, 0.98),
        },
    )

    assert merged_record.poster == "tmdb-poster"
    assert [item.label for item in bundle.merged_snapshot.ratings] == ["TMDB", "豆瓣", "Bangumi"]
    assert [item.value for item in bundle.merged_snapshot.ratings] == ["8.1", "7.9", "8.4"]
    assert merged_snapshot.overview == "TMDB简介"
    assert any(field["label"] == "导演" and field["value"] == "刘海波" for field in merged_snapshot.metadata_fields)
    assert bundle.merged_snapshot.playback_platforms[0].label == "爱奇艺"
    assert bundle.merged_snapshot.playback_platforms[0].update_time_text == "2026-05-25"
    assert bundle.merged_snapshot.playback_platforms[0].status_text == "更新至第128集"


def test_build_following_metadata_bundle_ignores_provider_below_threshold() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(provider="tmdb", provider_id="tv:1:season:1", title="测试", tmdb_id="1")
    low_confidence = MetadataRecord(provider="douban", provider_id="2", title="错误候选", rating="4.2")

    bundle, _record, _snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="测试",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:1",
            external_ids={"tmdb": "1"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={"douban": (low_confidence, 0.45)},
    )

    assert bundle.available_source_keys == ["merged", "tmdb"]
    assert "douban" not in bundle.source_snapshots


def test_build_following_metadata_bundle_keeps_tmdb_platform_link_without_fake_update_fields() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:1:season:1",
        title="测试",
        tmdb_id="1",
        detail_fields=[
            {
                "label": "watch_providers",
                "value": [
                    {
                        "provider": "youku",
                        "label": "优酷",
                        "url": "https://v.youku.com/v_show/id_x.html",
                    }
                ],
            }
        ],
    )

    bundle, _record, _snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="测试",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:1",
            external_ids={"tmdb": "1"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={},
    )

    platform = bundle.merged_snapshot.playback_platforms[0]
    assert platform.label == "优酷"
    assert platform.url == "https://v.youku.com/v_show/id_x.html"
    assert platform.update_time_text == ""
    assert platform.status_text == ""


def test_build_following_metadata_bundle_uses_douban_official_link_when_tmdb_has_no_platform() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:37854:season:1",
        title="海贼王",
        tmdb_id="37854",
        genres=["动画"],
    )
    douban_record = MetadataRecord(
        provider="official_douban",
        provider_id="1453238",
        title="航海王",
        year="1999",
        douban_id=1453238,
        detail_fields=[
            {
                "label": "official_links",
                "value": [
                    {
                        "provider": "iqiyi",
                        "label": "爱奇艺",
                        "url": "https://www.iqiyi.com/a_19rrhb3xvl.html",
                    }
                ],
            }
        ],
    )

    bundle, _record, _snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="海贼王",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:37854",
            external_ids={"tmdb": "37854"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={"douban": (douban_record, 0.8)},
    )

    platforms = bundle.merged_snapshot.playback_platforms
    assert len(platforms) == 1
    assert platforms[0].provider == "iqiyi"
    assert platforms[0].label == "爱奇艺"
    assert platforms[0].url == "https://www.iqiyi.com/a_19rrhb3xvl.html"


def test_build_following_metadata_bundle_keeps_douban_playbtn_platforms_without_urls() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:30983:season:1",
        title="名侦探柯南",
        tmdb_id="30983",
        genres=["动画"],
    )
    douban_record = MetadataRecord(
        provider="official_douban",
        provider_id="1463371",
        title="名侦探柯南",
        year="1996",
        douban_id=1463371,
        detail_fields=[
            {
                "label": "official_links",
                "value": [
                    {"provider": "tencent", "label": "腾讯视频", "url": ""},
                    {"provider": "bilibili", "label": "哔哩哔哩", "url": ""},
                    {"provider": "youku", "label": "优酷视频", "url": ""},
                    {"provider": "iqiyi", "label": "爱奇艺", "url": ""},
                ],
            }
        ],
    )

    bundle, _record, _snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983",
            external_ids={"tmdb": "30983"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={"douban": (douban_record, 0.8)},
    )

    platforms = bundle.merged_snapshot.playback_platforms
    assert [platform.provider for platform in platforms] == [
        "tencent",
        "bilibili",
        "youku",
        "iqiyi",
    ]
    assert [platform.label for platform in platforms] == [
        "腾讯视频",
        "哔哩哔哩",
        "优酷视频",
        "爱奇艺",
    ]
    assert [platform.url for platform in platforms] == ["", "", "", ""]


def test_following_metadata_gateway_searches_platform_sources_from_tmdb_identity() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def search(self, query, provider_filter=""):
            self.calls.append((provider_filter, query.title, query.year))
            if provider_filter == "douban":
                return [
                    MetadataScrapeGroup(
                        "douban",
                        "豆瓣",
                        [
                            MetadataScrapeCandidate(
                                provider="douban",
                                provider_label="豆瓣",
                                provider_id="35517044",
                                title="凡人修仙传",
                                year="2026",
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                rating="7.9",
            )

    gateway = FollowingMetadataGateway(SearchService())
    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="凡人修仙传",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:272432",
            external_ids={"tmdb": "272432"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="凡人修仙传",
            year="2026",
            tmdb_id="272432",
            aliases=["凡人修仙传 动画版"],
        ),
    )

    assert "douban" in result
    assert result["douban"][0].provider == "douban"
    assert result["douban"][1] >= 0.75


def test_following_metadata_gateway_maps_local_douban_source_into_douban_slot() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def search(self, query, provider_filter=""):
            self.calls.append((provider_filter, query.title, query.year))
            if provider_filter == "local_douban":
                return [
                    MetadataScrapeGroup(
                        "local_douban",
                        "本地豆瓣",
                        [
                            MetadataScrapeCandidate(
                                provider="local_douban",
                                provider_label="本地豆瓣",
                                provider_id="35517044",
                                title="凡人修仙传",
                                year="2026",
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                rating="7.9",
            )

    gateway = FollowingMetadataGateway(SearchService())
    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="凡人修仙传",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:272432",
            external_ids={"tmdb": "272432"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="凡人修仙传",
            year="2026",
            tmdb_id="272432",
        ),
    )

    assert "douban" in result
    assert result["douban"][0].provider == "local_douban"
    assert result["douban"][1] >= 0.75


def test_following_metadata_gateway_passes_existing_douban_id_to_douban_sources() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.douban_query_ids: list[int] = []

        def search(self, query, provider_filter=""):
            if provider_filter == "official_douban":
                self.douban_query_ids.append(query.vod_dbid)
                if query.vod_dbid != 1463371:
                    return []
                return [
                    MetadataScrapeGroup(
                        "official_douban",
                        "豆瓣官方",
                        [
                            MetadataScrapeCandidate(
                                provider="official_douban",
                                provider_label="豆瓣官方",
                                provider_id="1463371",
                                title="名侦探柯南",
                                year="1996",
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            assert candidate.provider == "official_douban"
            assert candidate.provider_id == "1463371"
            return MetadataRecord(
                provider="official_douban",
                provider_id="1463371",
                title="名侦探柯南",
                year="1996",
                douban_id=1463371,
                detail_fields=[
                    {
                        "label": "official_links",
                        "value": [
                            {"provider": "tencent", "label": "腾讯视频", "url": ""},
                            {"provider": "bilibili", "label": "哔哩哔哩", "url": ""},
                            {"provider": "youku", "label": "优酷视频", "url": ""},
                            {"provider": "iqiyi", "label": "爱奇艺", "url": ""},
                        ],
                    }
                ],
            )

    service = SearchService()
    gateway = FollowingMetadataGateway(service)

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983",
            external_ids={"tmdb": "30983", "douban": "1463371"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:30983:season:1",
            title="名侦探柯南",
            year="1996",
            tmdb_id="30983",
            genres=["动画"],
        ),
    )

    assert service.douban_query_ids == [1463371]
    assert result["douban"][0].provider == "official_douban"
    assert result["douban"][0].detail_fields[0]["value"][0]["provider"] == "tencent"


def test_following_metadata_gateway_does_not_search_local_douban_when_official_succeeds() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            self.calls.append(provider_filter)
            if provider_filter != "official_douban":
                return []
            return [
                MetadataScrapeGroup(
                    "official_douban",
                    "豆瓣官方",
                    [
                        MetadataScrapeCandidate(
                            provider="official_douban",
                            provider_label="豆瓣官方",
                            provider_id="1463371",
                            title="名侦探柯南",
                            year="1996",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                year=candidate.year,
                douban_id=1463371,
            )

    service = SearchService()
    gateway = FollowingMetadataGateway(service)

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="名侦探柯南",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:30983",
            external_ids={"tmdb": "30983", "douban": "1463371"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:30983:season:1",
            title="名侦探柯南",
            year="1996",
            tmdb_id="30983",
            genres=["动画"],
        ),
    )

    assert service.calls == ["official_douban", "bangumi"]
    assert result["douban"][0].provider == "official_douban"


def test_following_metadata_gateway_searches_only_tmdb_watch_platform_sources() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            assert query.title == "蜜语纪"
            assert query.year == "2026"
            self.calls.append(provider_filter)
            if provider_filter not in {"iqiyi", "tencent"}:
                return []
            provider_label = {"iqiyi": "爱奇艺", "tencent": "腾讯"}[provider_filter]
            provider_id = {
                "iqiyi": "iqiyi:album:1",
                "tencent": "https://v.qq.com/x/cover/tencent/ep1.html",
            }[provider_filter]
            return [
                MetadataScrapeGroup(
                    provider_filter,
                    provider_label,
                    [
                        MetadataScrapeCandidate(
                            provider=provider_filter,
                            provider_label=provider_label,
                            provider_id=provider_id,
                            title="蜜语纪",
                            year="2026",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[
                    {
                        "label": "播放链接",
                        "value": (
                            "https://www.iqiyi.com/a_1.html"
                            if candidate.provider == "iqiyi"
                            else "https://v.qq.com/x/cover/tencent/ep1.html"
                        ),
                    },
                    {"label": "更新状态", "value": "更新至第12集"},
                ],
            )

    service = SearchService()
    gateway = FollowingMetadataGateway(service)
    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="蜜语纪",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:123",
            external_ids={"tmdb": "123"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:123:season:1",
            title="蜜语纪",
            year="2026",
            tmdb_id="123",
            detail_fields=[
                {
                    "label": "watch_providers",
                    "value": [
                        {
                            "provider": "iqiyi",
                            "label": "爱奇艺",
                            "url": "https://www.iqiyi.com/a_1.html",
                        }
                    ],
                }
            ],
        ),
    )

    assert "iqiyi" in service.calls
    assert "tencent" not in service.calls
    assert "bangumi" not in service.calls
    assert set(result) <= {"douban", "iqiyi"}
    assert result["iqiyi"][0].provider == "iqiyi"


def test_following_metadata_gateway_accepts_exact_tencent_source_without_year() -> None:
    class SearchService:
        def search(self, query, provider_filter=""):
            assert query.title == "吞噬星空"
            if provider_filter != "tencent":
                return []
            return [
                MetadataScrapeGroup(
                    provider="tencent",
                    provider_label="腾讯",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tencent",
                            provider_label="腾讯",
                            provider_id="https://v.qq.com/x/cover/mzc00200np0le5t.html",
                            title="吞噬星空",
                            year="",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    gateway = FollowingMetadataGateway(SearchService())

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="吞噬星空",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:101172",
            external_ids={"tmdb": "101172"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:101172:season:1",
            title="吞噬星空",
            year="2020",
            tmdb_id="101172",
            genres=["动画"],
            detail_fields=[
                {
                    "label": "watch_providers",
                    "value": [
                        {
                            "provider": "tencent",
                            "label": "腾讯",
                            "url": "https://v.qq.com/x/cover/mzc00200np0le5t.html",
                        }
                    ],
                }
            ],
        ),
    )

    assert result["tencent"][0].provider == "tencent"
    assert result["tencent"][1] >= 0.80


def test_following_metadata_gateway_searches_tmdb_unlinked_watch_provider_sources() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            assert query.title == "吞噬星空"
            self.calls.append(provider_filter)
            if provider_filter != "tencent":
                return []
            return [
                MetadataScrapeGroup(
                    provider="tencent",
                    provider_label="腾讯",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tencent",
                            provider_label="腾讯",
                            provider_id="https://v.qq.com/x/cover/mzc00200np0le5t.html",
                            title="吞噬星空",
                            year="",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    service = SearchService()
    gateway = FollowingMetadataGateway(service)

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="吞噬星空",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:101172",
            external_ids={"tmdb": "101172"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:101172:season:1",
            title="吞噬星空",
            year="2020",
            tmdb_id="101172",
            genres=["动画"],
            detail_fields=[
                {
                    "label": "watch_provider_sources",
                    "value": [
                        {"provider": "tencent", "label": "腾讯", "url": ""},
                    ],
                }
            ],
        ),
    )

    assert "tencent" in service.calls
    assert result["tencent"][0].provider == "tencent"


def test_following_metadata_gateway_uses_tmdb_animation_category_for_playback_search() -> None:
    class SearchService:
        def search(self, query, provider_filter=""):
            if provider_filter == "tencent":
                assert query.category_name == "动漫"
                return [
                    MetadataScrapeGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        items=[
                            MetadataScrapeCandidate(
                                provider="tencent",
                                provider_label="腾讯",
                                provider_id="https://v.qq.com/x/cover/mzc00200np0le5t.html",
                                title="吞噬星空",
                                year="2020",
                                raw={"typeName": "动漫"},
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    gateway = FollowingMetadataGateway(SearchService())

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="吞噬星空",
            media_kind="剧集",
            provider="tmdb",
            provider_id="tv:101172",
            external_ids={"tmdb": "101172"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:101172:season:1",
            title="吞噬星空",
            year="2020",
            tmdb_id="101172",
            genres=["动画"],
            detail_fields=[
                {
                    "label": "watch_provider_sources",
                    "value": [{"provider": "tencent", "label": "腾讯", "url": ""}],
                }
            ],
        ),
    )

    assert result["tencent"][0].provider == "tencent"


def test_following_metadata_gateway_uses_douban_official_links_to_search_playback_sources() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            assert query.title == "吞噬星空"
            assert query.year == "2020"
            self.calls.append(provider_filter)
            if provider_filter == "official_douban":
                return [
                    MetadataScrapeGroup(
                        provider="official_douban",
                        provider_label="豆瓣官方",
                        items=[
                            MetadataScrapeCandidate(
                                provider="official_douban",
                                provider_label="豆瓣官方",
                                provider_id="26636712",
                                title="吞噬星空",
                                year="2020",
                            )
                        ],
                    )
                ]
            if provider_filter == "tencent":
                return [
                    MetadataScrapeGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        items=[
                            MetadataScrapeCandidate(
                                provider="tencent",
                                provider_label="腾讯",
                                provider_id="https://v.qq.com/x/cover/mzc00200np0le5t.html",
                                title="吞噬星空",
                                year="",
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            if candidate.provider == "official_douban":
                return MetadataRecord(
                    provider="official_douban",
                    provider_id="26636712",
                    title="吞噬星空",
                    year="2020",
                    rating="7.2",
                    detail_fields=[
                        {
                            "label": "official_links",
                            "value": [
                                {
                                    "provider": "tencent",
                                    "label": "腾讯视频",
                                    "url": "https://v.qq.com/x/cover/mzc00200np0le5t.html",
                                }
                            ],
                        }
                    ],
                )
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    service = SearchService()
    gateway = FollowingMetadataGateway(service)

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="吞噬星空",
            media_kind="anime",
            provider="tmdb",
            provider_id="tv:101172",
            external_ids={"tmdb": "101172"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:101172:season:1",
            title="吞噬星空",
            year="2020",
            tmdb_id="101172",
            genres=["动画"],
        ),
    )

    assert service.calls == ["official_douban", "tencent", "bangumi"]
    assert result["douban"][0].provider == "official_douban"
    assert result["tencent"][0].provider == "tencent"


def test_following_metadata_gateway_skips_playback_source_with_foreign_playback_link() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            self.calls.append(provider_filter)
            if provider_filter == "iqiyi":
                return [
                    type(
                        "Group",
                        (),
                        {
                            "items": [
                                MetadataScrapeCandidate(
                                    provider="iqiyi",
                                    provider_label="爱奇艺",
                                    provider_id="https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                                    title=query.title,
                                    year=query.year,
                                )
                            ]
                        },
                    )()
                ]
            if provider_filter == "youku":
                return [
                    type(
                        "Group",
                        (),
                        {
                            "items": [
                                MetadataScrapeCandidate(
                                    provider="youku",
                                    provider_label="优酷",
                                    provider_id="https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                                    title=query.title,
                                    year=query.year,
                                )
                            ]
                        },
                    )()
                ]
            return []

        def detail_record(self, candidate):
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    gateway = FollowingMetadataGateway(SearchService())

    result = gateway.load_source_records(
        FollowingRecord(
            id=1,
            title="凡人修仙传",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:243224",
            external_ids={"tmdb": "243224"},
        ),
        tmdb_record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:243224:season:1",
            title="凡人修仙传",
            year="2025",
            tmdb_id="243224",
            detail_fields=[
                {
                    "label": "watch_providers",
                    "value": [
                        {
                            "provider": "youku",
                            "label": "优酷",
                            "url": "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                        }
                    ],
                }
            ],
        ),
    )

    assert "iqiyi" not in result
    assert result["youku"][0].provider == "youku"


def test_following_controller_load_detail_attaches_metadata_bundle_from_tmdb_snapshot() -> None:
    class Repository:
        def __init__(self) -> None:
            self.record = FollowingRecord(
                id=1,
                title="凡人修仙传",
                media_kind="anime",
                season_number=1,
                provider="tmdb",
                provider_id="tv:272432",
                external_ids={"tmdb": "272432"},
            )
            self.snapshot = FollowingDetailSnapshot(following_id=1)

        def get(self, following_id: int):
            assert following_id == 1
            return self.record

        def get_detail_snapshot(self, following_id: int):
            assert following_id == 1
            return self.snapshot

    class SearchService:
        def search(self, query, provider_filter=""):
            del query, provider_filter
            return []

        def detail_record_full(self, candidate):
            assert candidate.provider == "tmdb"
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:272432:season:1",
                title="凡人修仙传",
                year="2026",
                tmdb_id="272432",
                overview="TMDB简介",
            )

    controller = FollowingController(Repository(), metadata_search_service=SearchService())

    view = controller.load_detail(1, refresh_if_empty=False)

    assert view.snapshot.metadata_bundle is not None
    assert view.snapshot.metadata_bundle.available_source_keys[0] == "merged"
    assert "tmdb" in view.snapshot.metadata_bundle.source_snapshots


def test_following_controller_load_detail_attaches_bangumi_bundle_from_external_id() -> None:
    class Repository:
        def __init__(self) -> None:
            self.record = FollowingRecord(
                id=1,
                title="牧神记",
                media_kind="anime",
                provider="player",
                provider_id="player:source:vod-1",
                external_ids={"bangumi": "521431"},
            )
            self.snapshot = FollowingDetailSnapshot(following_id=1)
            self.saved_snapshot = None

        def get(self, following_id: int):
            assert following_id == 1
            return self.record

        def get_detail_snapshot(self, following_id: int):
            assert following_id == 1
            return self.snapshot

        def save_detail_snapshot(
            self,
            following_id: int,
            snapshot: FollowingDetailSnapshot,
        ) -> None:
            assert following_id == 1
            self.snapshot = snapshot
            self.saved_snapshot = snapshot

    class SearchService:
        def detail_record(self, candidate):
            assert candidate.provider == "bangumi"
            assert candidate.provider_id == "subject:521431"
            return MetadataRecord(
                provider="bangumi",
                provider_id="subject:521431",
                title="牧神记",
                year="2024",
                rating="7.4",
                overview="Bangumi简介",
                detail_fields=[{"label": "Bangumi ID", "value": "521431"}],
            )

    repository = Repository()
    controller = FollowingController(repository, metadata_search_service=SearchService())

    view = controller.load_detail(1, refresh_if_empty=False)

    assert view.snapshot.metadata_bundle is not None
    assert "bangumi" in view.snapshot.metadata_bundle.source_snapshots
    assert (
        view.snapshot.metadata_bundle.source_snapshots["bangumi"].provider_id
        == "subject:521431"
    )
    assert view.snapshot.metadata_bundle.merged_snapshot.ratings[0].label == "Bangumi"
    assert repository.saved_snapshot is not None


def test_following_controller_load_detail_saves_generated_metadata_bundle() -> None:
    class Repository:
        def __init__(self) -> None:
            self.record = FollowingRecord(
                id=1,
                title="凡人修仙传",
                media_kind="anime",
                season_number=1,
                provider="tmdb",
                provider_id="tv:272432",
                external_ids={"tmdb": "272432"},
            )
            self.snapshot = FollowingDetailSnapshot(following_id=1)
            self.saved_snapshot = None

        def get(self, following_id: int):
            assert following_id == 1
            return self.record

        def get_detail_snapshot(self, following_id: int):
            assert following_id == 1
            return self.snapshot

        def save_detail_snapshot(self, following_id: int, snapshot: FollowingDetailSnapshot) -> None:
            assert following_id == 1
            self.snapshot = snapshot
            self.saved_snapshot = snapshot

    class SearchService:
        def search(self, query, provider_filter=""):
            del query, provider_filter
            return []

        def detail_record_full(self, candidate):
            assert candidate.provider == "tmdb"
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:272432:season:1",
                title="凡人修仙传",
                year="2026",
                tmdb_id="272432",
                overview="TMDB简介",
            )

    repository = Repository()
    controller = FollowingController(repository, metadata_search_service=SearchService())

    view = controller.load_detail(1, refresh_if_empty=False)

    assert view.snapshot.metadata_bundle is not None
    assert repository.saved_snapshot is not None
    assert repository.saved_snapshot.metadata_bundle is not None


def test_following_controller_refresh_metadata_saves_bundle_back_to_snapshot() -> None:
    class Repository:
        def __init__(self) -> None:
            self.record = FollowingRecord(
                id=1,
                title="凡人修仙传",
                media_kind="anime",
                season_number=1,
                provider="tmdb",
                provider_id="tv:272432",
                external_ids={"tmdb": "272432"},
            )
            self.snapshot = FollowingDetailSnapshot(following_id=1)
            self.saved_snapshot = None

        def get(self, following_id: int):
            assert following_id == 1
            return self.record

        def get_detail_snapshot(self, following_id: int):
            assert following_id == 1
            return self.snapshot

        def update_metadata(self, following_id: int, refreshed_record: FollowingRecord) -> None:
            assert following_id == 1
            self.record = refreshed_record
            self.record.id = following_id

        def update_check_state(self, following_id: int, **kwargs) -> None:
            assert following_id == 1
            del kwargs

        def save_detail_snapshot(self, following_id: int, snapshot: FollowingDetailSnapshot) -> None:
            assert following_id == 1
            self.snapshot = snapshot
            self.saved_snapshot = snapshot

    class SearchService:
        def search(self, query, provider_filter=""):
            del query
            if provider_filter == "tmdb":
                return [
                    MetadataScrapeGroup(
                        provider="tmdb",
                        provider_label="TMDB",
                        items=[
                            MetadataScrapeCandidate(
                                provider="tmdb",
                                provider_label="TMDB",
                                provider_id="tv:272432:season:1",
                                title="凡人修仙传",
                                year="2026",
                            )
                        ],
                    )
                ]
            return []

        def detail_record(self, candidate):
            return self.detail_record_full(candidate)

        def detail_record_full(self, candidate):
            return MetadataRecord(
                provider="tmdb",
                provider_id=str(candidate.provider_id or ""),
                title="凡人修仙传",
                year="2026",
                tmdb_id="272432",
                overview="TMDB简介",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集"}],
                    }
                ],
            )

    repository = Repository()
    controller = FollowingController(repository, metadata_search_service=SearchService(), now=lambda: 200)

    view = controller.refresh_metadata(1)

    assert view.snapshot.metadata_bundle is not None
    assert repository.saved_snapshot is not None
    assert repository.saved_snapshot.metadata_bundle is not None


def test_following_metadata_bundle_does_not_let_douban_override_existing_tmdb_overview() -> None:
    from atv_player.following_metadata import build_following_metadata_bundle

    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:1:season:1",
        title="测试",
        tmdb_id="1",
        overview="TMDB简介",
        rating="8.1",
    )
    douban_record = MetadataRecord(
        provider="douban",
        provider_id="2",
        title="测试",
        overview="豆瓣简介",
        rating="7.9",
    )

    bundle, _merged_record, merged_snapshot = build_following_metadata_bundle(
        base_record=FollowingRecord(
            id=1,
            title="测试",
            media_kind="live_action",
            provider="tmdb",
            provider_id="tv:1",
            external_ids={"tmdb": "1"},
        ),
        base_snapshot=FollowingDetailSnapshot(),
        tmdb_detail_record=tmdb_record,
        provider_records={"douban": (douban_record, 0.91)},
    )

    assert bundle.merged_snapshot.ratings[0].label == "TMDB"
    assert merged_snapshot.overview == "TMDB简介"


def test_following_candidate_from_supported_urls() -> None:
    assert following_candidate_from_url("https://bgm.tv/subject/521431").provider_id == "subject:521431"
    assert following_candidate_from_url("https://movie.douban.com/subject/37090537/").provider_id == "37090537"
    assert (
        following_candidate_from_url("https://www.themoviedb.org/tv/256783/season/2").provider_id
        == "tv:256783:season:2"
    )


def test_build_following_from_bangumi_candidate_preserves_ids_and_counts() -> None:
    candidate = MetadataScrapeCandidate(
        provider="bangumi",
        provider_label="Bangumi",
        provider_id="subject:123",
        title="凡人修仙传",
        year="2026",
        subtitle="动漫",
        raw={"episodes": [{"sort": 1, "name_cn": "第一话", "desc": "剧情"}, {"sort": 2, "name": "Episode 2"}]},
    )

    record, snapshot = build_following_from_candidate(candidate, now=100)

    assert record.provider == "bangumi"
    assert record.provider_id == "subject:123"
    assert record.external_ids["bangumi"] == "123"
    assert record.latest_episode == 2
    assert record.total_episodes == 2
    assert snapshot.episodes[0].title == "第一话"


def test_build_following_from_selected_iqiyi_candidate_enriches_with_tmdb_metadata() -> None:
    selected = MetadataScrapeCandidate(
        provider="iqiyi",
        provider_label="爱奇艺",
        provider_id="iqiyi:album:1",
        title="盗妖行",
        year="2026",
        subtitle="动漫",
        raw={"channel": "动漫,4"},
    )

    class TMDBClient:
        def image_base(self, kind: str) -> str:
            del kind
            return "https://image.tmdb.org/t/p/original"

        def get_tv_detail(self, tmdb_id: str | int) -> dict:
            assert str(tmdb_id) == "315088"
            return {
                "id": 315088,
                "name": "盗妖行",
                "first_air_date": "2026-01-01",
                "vote_average": 7.66,
                "poster_url": "tmdb-poster",
                "backdrop_url": "tmdb-backdrop",
                "genres": [{"name": "动画"}],
                "aggregate_credits": {},
                "alternative_titles": {"results": []},
                "external_ids": {},
            }

        def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict:
            assert str(tmdb_id) == "315088"
            assert season_number == 1
            return {
                "season_number": 1,
                "episodes": [{"episode_number": 1, "name": "第一集", "still_url": "still"}],
            }

    tmdb_provider = TMDBProvider(TMDBClient())

    class SearchService:
        def __init__(self) -> None:
            self.detail_provider_ids: list[tuple[str, str]] = []

        def search(self, query, provider_filter=""):
            assert query.title == "盗妖行"
            assert provider_filter == "tmdb"
            return [
                MetadataScrapeGroup(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:315088:season:1",
                            title="盗妖行",
                            year="2026",
                            subtitle="剧集",
                        )
                    ],
                ),
            ]

        def detail_record(self, candidate):
            self.detail_provider_ids.append((candidate.provider, candidate.provider_id))
            if candidate.provider == "iqiyi":
                return MetadataRecord(
                    provider="iqiyi",
                    provider_id="iqiyi:album:1",
                    title="盗妖行",
                    overview="爱奇艺简介",
                )
            return tmdb_provider.get_detail(
                MetadataMatch(
                    provider="tmdb",
                    provider_id="tv:315088:season:1",
                    title="盗妖行",
                    year="2026",
                )
            )

    service = SearchService()

    record, snapshot = build_following_from_metadata_candidate(
        selected,
        metadata_search_service=service,
        now=100,
    )

    assert service.detail_provider_ids == [
        ("iqiyi", "iqiyi:album:1"),
        ("tmdb", "tv:315088:season:1"),
    ]
    assert record.provider == "iqiyi"
    assert record.provider_id == "iqiyi:album:1"
    assert record.external_ids == {"iqiyi": "iqiyi:album:1", "tmdb": "315088"}
    assert record.media_kind == "anime"
    assert record.poster == "tmdb-poster"
    assert record.backdrop == "tmdb-backdrop"
    assert record.rating == "7.7"
    assert record.latest_episode == 1
    assert record.total_episodes == 1
    assert snapshot.overview == "爱奇艺简介"
    assert snapshot.episodes[0].title == "第一集"


def test_build_following_from_tmdb_candidate_searches_only_tmdb_platform_and_third_party_sources() -> None:
    selected = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="tv:243224:season:1",
        title="凡人修仙传",
        year="2025",
        subtitle="剧集",
        raw={"season_number": 1},
    )

    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.detail_provider_ids: list[tuple[str, str]] = []

        def search(self, query, provider_filter=""):
            assert query.title == "凡人修仙传"
            assert query.year == "2025"
            self.calls.append(provider_filter)
            if provider_filter != "youku":
                return []
            return [
                MetadataScrapeGroup(
                    provider="youku",
                    provider_label="优酷",
                    items=[
                        MetadataScrapeCandidate(
                            provider="youku",
                            provider_label="优酷",
                            provider_id="https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                            title="凡人修仙传",
                            year="2025",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            self.detail_provider_ids.append((candidate.provider, candidate.provider_id))
            if candidate.provider == "tmdb":
                return MetadataRecord(
                    provider="tmdb",
                    provider_id="tv:243224:season:1",
                    title="凡人修仙传",
                    year="2025",
                    tmdb_id="243224",
                    genres=["动画"],
                    detail_fields=[
                        {
                            "label": "watch_providers",
                            "value": [
                                {
                                    "provider": "youku",
                                    "label": "优酷",
                                    "url": "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                                }
                            ],
                        }
                    ],
                )
            return MetadataRecord(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                year=candidate.year,
                detail_fields=[{"label": "播放链接", "value": candidate.provider_id}],
            )

    service = SearchService()

    record, _snapshot = build_following_from_metadata_candidate(
        selected,
        metadata_search_service=service,
        now=100,
    )

    assert service.calls == ["official_douban", "local_douban", "douban", "bangumi", "youku"]
    assert record.provider == "tmdb"
    assert ("youku", "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html") in service.detail_provider_ids


def test_build_following_from_tmdb_candidate_skips_bangumi_when_tmdb_is_not_animation() -> None:
    selected = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="tv:243224:season:1",
        title="凡人修仙传",
        year="2025",
        subtitle="剧集",
        raw={"season_number": 1},
    )

    class SearchService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, query, provider_filter=""):
            assert query.title == "凡人修仙传"
            self.calls.append(provider_filter)
            return []

        def detail_record(self, candidate):
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title=candidate.title,
                year=candidate.year,
                genres=["剧情", "Sci-Fi & Fantasy"],
                detail_fields=[],
            )

    service = SearchService()

    build_following_from_metadata_candidate(
        selected,
        metadata_search_service=service,
        now=100,
    )

    assert service.calls == ["official_douban", "local_douban", "douban"]


def test_build_following_from_bangumi_candidate_prefers_tmdb_episode_details() -> None:
    selected = MetadataScrapeCandidate(
        provider="bangumi",
        provider_label="Bangumi",
        provider_id="subject:123",
        title="仙剑奇侠传三",
        year="2026",
        subtitle="动漫",
        raw={"episodes": [{"sort": 1, "type": 0, "name_cn": "Bangumi标题"}]},
    )

    class SearchService:
        def search(self, query, provider_filter=""):
            del query, provider_filter
            return [
                MetadataScrapeGroup("bangumi", "Bangumi", [selected]),
                MetadataScrapeGroup(
                    "tmdb",
                    "TMDB",
                    [
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:233295:season:1",
                            title="仙剑奇侠传三",
                        )
                    ],
                ),
            ]

        def detail_record(self, candidate):
            if candidate.provider == "bangumi":
                return MetadataRecord(
                    provider="bangumi",
                    provider_id="subject:123",
                    title="仙剑奇侠传三",
                    overview="Bangumi简介",
                )
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:233295:season:1",
                title="仙剑奇侠传三",
                tmdb_id="233295",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [
                            {
                                "episode_number": 1,
                                "name": "TMDB标题",
                                "overview": "TMDB分集简介",
                                "still_url": "tmdb-still",
                            }
                        ],
                    }
                ],
            )

    record, snapshot = build_following_from_metadata_candidate(
        selected,
        metadata_search_service=SearchService(),
        now=100,
    )

    assert record.provider == "bangumi"
    assert record.external_ids == {"bangumi": "123", "tmdb": "233295"}
    assert snapshot.overview == "Bangumi简介"
    assert snapshot.episodes[0].title == "TMDB标题"
    assert snapshot.episodes[0].overview == "TMDB分集简介"
    assert snapshot.episodes[0].still == "tmdb-still"


def test_build_snapshot_from_tmdb_record_includes_backdrops_cast_and_episode_stills() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:456:season:1",
        title="庆余年",
        poster="poster",
        backdrop="backdrop",
        rating="8.0",
        tmdb_id="456",
        douban_id=129,
        actors=["张若昀"],
        directors=["孙皓"],
        cast_details=[{"name": "张若昀", "role": "范闲", "avatar": "/actor.jpg"}],
        crew_details=[{"name": "孙皓", "job": "Director", "avatar": "/director.jpg"}],
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 1, "name": "第一集", "overview": "剧情", "still_url": "still"}
                ],
            }
        ],
    )

    following, snapshot = build_snapshot_from_record(record, now=200, media_kind="live_action")

    assert following.external_ids == {"tmdb": "456", "douban": "129"}
    assert following.provider_id == "tv:456"
    assert following.season_number == 1
    assert following.backdrop == "backdrop"
    assert snapshot.cast[0]["name"] == "张若昀"
    assert snapshot.cast[0]["role"] == "范闲"
    assert snapshot.cast[0]["avatar"] == "/actor.jpg"
    assert snapshot.crew[0]["name"] == "孙皓"
    assert snapshot.crew[0]["avatar"] == "/director.jpg"
    assert snapshot.episodes[0].still == "still"


def test_build_snapshot_from_tmdb_record_includes_season_summaries() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:456:season:1",
        title="庆余年",
        tmdb_id="456",
        detail_fields=[
            {
                "label": "seasons",
                "value": [
                    {"season_number": 1, "name": "第一季", "episode_count": 46, "poster_url": "poster-1"},
                    {"season_number": 2, "name": "第二季", "episode_count": 36, "poster_url": "poster-2"},
                ],
            }
        ],
    )

    _following, snapshot = build_snapshot_from_record(record, now=200, media_kind="live_action")

    assert [season.season_number for season in snapshot.seasons] == [1, 2]
    assert snapshot.seasons[1].episode_count == 36
    assert snapshot.seasons[1].poster == "poster-2"


def test_build_snapshot_from_tmdb_record_infers_season_number_from_provider_id() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:76479:season:1",
        title="黑袍纠察队",
        tmdb_id="76479",
    )

    following, _snapshot = build_snapshot_from_record(record, now=200, media_kind="live_action")

    assert following.provider_id == "tv:76479"
    assert following.season_number == 1


def test_build_snapshot_from_record_uses_record_backdrops_list_when_available() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:7:season:1",
        title="深空彼岸",
        poster="poster",
        backdrop="default-backdrop",
        backdrops=["default-backdrop", "alt-backdrop-1", "alt-backdrop-2"],
        tmdb_id="7",
    )

    _, snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert snapshot.backdrops == ["default-backdrop", "alt-backdrop-1", "alt-backdrop-2"]


def test_build_snapshot_from_record_falls_back_to_single_backdrop_when_record_list_empty() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:7",
        title="深空彼岸",
        backdrop="only-backdrop",
        tmdb_id="7",
    )

    _, snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert snapshot.backdrops == ["only-backdrop"]


def test_build_snapshot_from_record_uses_last_episode_to_air_for_latest_and_total() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:30983:season:1",
        title="名侦探柯南",
        tmdb_id="30983",
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 1, "name": "第1集"},
                    {"episode_number": 2, "name": "第2集"},
                ],
            },
            {
                "label": "last_episode_to_air",
                "value": {"episode_number": 1201, "air_date": "2026-05-09"},
            },
        ],
    )

    following, _snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert following.latest_episode == 1201
    assert following.total_episodes == 1201


def test_build_snapshot_from_record_normalizes_global_tmdb_latest() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:256783:season:2",
        title="成何体统 第二季",
        tmdb_id="256783",
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {
                        "episode_number": index,
                        "season_number": 2,
                        "name": f"第 {index} 集",
                    }
                    for index in range(1, 25)
                ],
            },
            {
                "label": "seasons",
                "value": [
                    {"season_number": 2, "name": "第二季", "episode_count": 24}
                ],
            },
            {
                "label": "last_episode_to_air",
                "value": {
                    "episode_number": 112,
                    "season_number": 2,
                    "air_date": "2026-06-21",
                },
            },
        ],
    )

    following, snapshot = build_snapshot_from_record(record, now=300, media_kind="anime")

    assert following.latest_episode == 24
    assert following.total_episodes == 24
    assert snapshot.seasons == [
        FollowingSeason(season_number=2, title="第二季", episode_count=24)
    ]


def test_build_snapshot_from_record_does_not_use_last_episode_to_air_as_total_for_ongoing_series() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:37854:season:23",
        title="航海王",
        tmdb_id="37854",
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 1163, "season_number": 23, "name": "第 1163 集", "air_date": "2026-05-24"},
                    {"episode_number": 1178, "season_number": 23, "name": "第 1178 集", "air_date": "2026-09-06"},
                ],
            },
            {
                "label": "last_episode_to_air",
                "value": {"episode_number": 1163, "season_number": 23, "air_date": "2026-05-24"},
            },
            {
                "label": "next_episode_to_air",
                "value": {"episode_number": 1178, "season_number": 23, "air_date": "2026-09-06"},
            },
        ],
    )

    following, snapshot = build_snapshot_from_record(record, now=1780070400, media_kind="anime")

    assert following.latest_episode == 1163
    assert following.total_episodes == 0
    assert snapshot.next_episode is not None
    assert snapshot.next_episode.episode_number == 1178


def test_build_snapshot_from_record_uses_last_episode_air_date_for_recent_update_metadata() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:233295:season:1",
        title="仙剑奇侠传叁",
        tmdb_id="233295",
        detail_fields=[
            {"label": "last_air_date", "value": "2026-03-31"},
            {
                "label": "last_episode_to_air",
                "value": {"episode_number": 23, "air_date": "2026-05-19"},
            },
        ],
    )

    _following, snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert {"label": "最近更新", "value": "2026-05-19"} in snapshot.metadata_fields
    assert {"label": "last_air_date", "value": "2026-03-31"} not in snapshot.metadata_fields


def test_build_snapshot_from_record_keeps_next_episode_to_air_as_typed_episode() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:233295:season:1",
        title="仙剑奇侠传叁",
        tmdb_id="233295",
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 23, "season_number": 1, "name": "第 23 集"},
                ],
            },
            {
                "label": "next_episode_to_air",
                "value": {
                    "episode_number": 24,
                    "season_number": 1,
                    "name": "第 24 集",
                    "air_date": "2026-05-26",
                    "overview": "",
                    "runtime": None,
                    "still_path": None,
                },
            },
        ],
    )

    _following, snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert snapshot.next_episode is not None
    assert snapshot.next_episode.season_number == 1
    assert snapshot.next_episode.episode_number == 24
    assert snapshot.next_episode.title == "第 24 集"
    assert snapshot.next_episode.air_date == "2026-05-26"


def test_compute_episode_counts_ignores_specials_and_zero_episode_numbers() -> None:
    latest, total = compute_episode_counts(
        [
            {"episode_number": 0, "name": "SP"},
            {"episode_number": 1, "name": "第一集"},
            {"sort": 3, "type": 1, "name": "特别篇"},
            {"sort": 2, "type": 0, "name": "第二集"},
        ]
    )

    assert latest == 2
    assert total == 2


def test_compute_episode_counts_uses_air_date_for_latest_and_all_episodes_for_total() -> None:
    latest, total = compute_episode_counts(
        [
            {"episode_number": 23, "air_date": "2026-05-19"},
            {"episode_number": 24, "air_date": "2026-05-26"},
            {"episode_number": 25, "air_date": "2026-06-02"},
        ],
        now=1779638400,
    )

    assert latest == 23
    assert total == 3


def test_following_metadata_gateway_refreshes_tmdb_tv_as_first_season_detail() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.search_calls = 0
            self.detail_provider_ids: list[str] = []

        def search(self, query, provider_filter=""):
            del query
            self.search_calls += 1
            assert provider_filter == "tmdb"
            return [
                MetadataScrapeGroup(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:315088",
                            title="盗妖行",
                        )
                    ],
                )
            ]

        def detail_record_full(self, candidate):
            self.detail_provider_ids.append(candidate.provider_id)
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="盗妖行",
                poster="poster",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集"}],
                    }
                ],
            )

    service = SearchService()
    record, snapshot = FollowingMetadataGateway(service).refresh(
        FollowingRecord(
            id=2,
            title="盗妖行",
            provider="tmdb",
            provider_id="tv:315088",
            season_number=1,
        ),
        "tmdb",
    )

    assert service.search_calls == 0
    assert service.detail_provider_ids == ["tv:315088:season:1"]
    assert record.latest_episode == 1
    assert record.total_episodes == 1
    assert record.provider_id == ""
    assert record.poster == ""
    assert snapshot.episodes == []


def test_merge_following_snapshot_prefer_episodes_keeps_original_overview_and_cast() -> None:
    snapshot = FollowingDetailSnapshot(
        overview="原始简介",
        cast=[{"name": "原演员"}],
        episodes=[],
    )
    detail = FollowingDetailSnapshot(
        overview="不相关剧集简介",
        cast=[{"name": "不相关演员"}],
        episodes=[FollowingEpisode(episode_number=1, title="TMDB分集")],
    )

    merged = merge_following_snapshot(snapshot, detail, fill_missing=True, prefer_episodes=True)

    assert merged.overview == "原始简介"
    assert merged.cast == [{"name": "原演员"}]
    assert merged.episodes[0].title == "TMDB分集"
