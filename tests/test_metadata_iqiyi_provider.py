from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.iqiyi import IqiyiMetadataProvider


class JsonResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def json(self):
        return self._payload


def test_iqiyi_metadata_provider_search_prefers_exact_season_match_and_omits_cover_and_rating() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        assert kwargs["params"]["key"] == "剑来 第二季"
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来",
                                "channel": "动漫,4",
                                "siteId": "qq",
                                "siteName": "腾讯",
                                "year": {"value": "2024"},
                                "brief": {"value": "第一季简介"},
                                "videos": [],
                            }
                        },
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来 第二季",
                                "channel": "动漫,4",
                                "siteId": "qq",
                                "siteName": "腾讯",
                                "pageUrl": "https://www.iqiyi.com/common/redirect.html?url=https://v.qq.com/demo",
                                "year": {"value": "2025"},
                                "region": {"value": "中国大陆"},
                                "language": {"value": "汉语普通话"},
                                "directors": {"value": [{"title": "导演甲"}]},
                                "actors": {"value": [{"title": "演员甲"}, {"title": "演员乙"}]},
                                "baseTags": [
                                    {"value": "动画"},
                                    {"value": "冒险"},
                                ],
                                "brief": {"value": "第二季简介"},
                                "score": 9.1,
                                "img": "https://pic.example/poster.avif",
                                "videos": [],
                            }
                        },
                    ]
                }
            }
        )

    provider = IqiyiMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="剑来 第二季", year="2025", category_name="动漫"))

    assert [match.title for match in matches] == ["剑来 第二季", "剑来"]
    assert matches[0].provider == "iqiyi"
    assert matches[0].year == "2025"
    assert matches[0].score > matches[1].score

    record = provider.get_detail(matches[0])

    assert record.provider == "iqiyi"
    assert record.title == "剑来 第二季"
    assert record.year == "2025"
    assert record.poster == ""
    assert record.rating == ""
    assert record.overview == "第二季简介"
    assert record.country == "中国大陆"
    assert record.language == "汉语普通话"
    assert record.directors == ["导演甲"]
    assert record.actors == ["演员甲", "演员乙"]
    assert record.genres == ["动画", "冒险"]


def test_iqiyi_metadata_provider_maps_movie_people_and_detail_fields() -> None:
    payload = {
        "data": {
            "templates": [
                {
                    "template": 103,
                    "albumInfo": {
                        "title": "疯狂动物城2",
                        "siteId": "iqiyi",
                        "siteName": "爱奇艺",
                        "pageUrl": "https://www.iqiyi.com/v_demo.html",
                        "year": {"value": "2025"},
                        "region": {"value": "美国"},
                        "language": {"value": "英语"},
                        "directors": {"value": [{"title": "拜恩·霍华德"}, {"title": "杰拉德·布什"}]},
                        "actors": {"value": [{"title": "金妮弗·古德温"}, {"title": "杰森·贝特曼"}]},
                        "brief": {"value": "兔子朱迪与狐狸尼克正式组成搭档。"},
                        "releaseTime": {"key": "上映时间", "value": "2025-11-26"},
                        "timeLength": {"key": "片长", "value": "01:43:26"},
                        "baseTags": [{"value": "冒险"}, {"value": "动画"}, {"value": "喜剧"}],
                        "rating": 9.0,
                        "img": "https://pic5.iqiyipic.com/image/demo.avif",
                        "videos": [],
                    }
                }
            ]
        }
    }
    provider = IqiyiMetadataProvider(get=lambda url, **kwargs: JsonResponse(payload))

    match = provider.search(MetadataQuery(title="疯狂动物城2", year="2025", category_name="电影"))[0]
    record = provider.get_detail(match)

    assert match == MetadataMatch(
        provider="iqiyi",
        provider_id="https://www.iqiyi.com/v_demo.html",
        title="疯狂动物城2",
        year="2025",
        score=match.score,
        raw=match.raw,
    )
    assert record.poster == ""
    assert record.rating == ""
    assert record.directors == ["拜恩·霍华德", "杰拉德·布什"]
    assert record.actors == ["金妮弗·古德温", "杰森·贝特曼"]
    assert record.genres == ["冒险", "动画", "喜剧"]
    assert record.detail_fields == [
        {"label": "上映时间", "value": "2025-11-26"},
        {"label": "片长", "value": "01:43:26"},
    ]


def test_iqiyi_metadata_provider_ignores_templates_outside_101_102_103() -> None:
    provider = IqiyiMetadataProvider(
        get=lambda url, **kwargs: JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 104,
                            "albumInfo": {
                                "title": "不应命中",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_skip.html",
                            },
                        },
                        {
                            "template": 102,
                            "albumInfo": {
                                "title": "应该命中",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_keep.html",
                            },
                        },
                    ]
                }
            }
        )
    )

    matches = provider.search(MetadataQuery(title="应该命中"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("应该命中", "https://www.iqiyi.com/v_keep.html")
    ]


def test_iqiyi_metadata_provider_search_preserves_album_videos_in_raw() -> None:
    provider = IqiyiMetadataProvider(
        get=lambda url, **kwargs: JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "黑袍纠察队 第五季",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_demo.html",
                                "year": {"value": "2026"},
                                "videos": [{"itemNumber": 1, "itemTitle": "终局开篇"}],
                            },
                        }
                    ]
                }
            }
        )
    )

    match = provider.search(MetadataQuery(title="黑袍纠察队第五季"))[0]

    assert match.raw["videos"][0]["itemTitle"] == "终局开篇"


def test_iqiyi_metadata_provider_search_normalizes_search_videoinfos_into_videos() -> None:
    provider = IqiyiMetadataProvider(
        get=lambda url, **kwargs: JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "家业",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_demo.html",
                                "year": {"value": "2026"},
                                "videos": [],
                            },
                            "videoinfos": [
                                {
                                    "number": 7,
                                    "subtitle": "超品？成了！",
                                    "title": "家业 第7集",
                                    "pageUrl": "https://www.iqiyi.com/v_ep7.html",
                                },
                                {
                                    "number": 8,
                                    "subtitle": "当街竞价，怕了吗！",
                                    "title": "家业 第8集",
                                    "pageUrl": "https://www.iqiyi.com/v_ep8.html",
                                },
                            ],
                        }
                    ]
                }
            }
        )
    )

    match = provider.search(MetadataQuery(title="家业", year="2026"))[0]

    assert match.raw["videos"] == [
        {
            "number": 7,
            "subtitle": "超品？成了！",
            "title": "家业 第7集",
            "pageUrl": "https://www.iqiyi.com/v_ep7.html",
        },
        {
            "number": 8,
            "subtitle": "当街竞价，怕了吗！",
            "title": "家业 第8集",
            "pageUrl": "https://www.iqiyi.com/v_ep8.html",
        },
    ]


def test_iqiyi_metadata_provider_search_penalizes_non_native_site_results() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来 第二季",
                                "siteId": "qq",
                                "siteName": "腾讯视频",
                                "pageUrl": "https://www.iqiyi.com/v_third_party.html",
                                "year": {"value": "2025"},
                            },
                        },
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来 第二季",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_native.html",
                                "year": {"value": "2025"},
                            },
                        },
                    ]
                }
            }
        )

    provider = IqiyiMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="剑来 第二季", year="2025", category_name="动漫"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("剑来 第二季", "https://www.iqiyi.com/v_native.html"),
        ("剑来 第二季", "https://www.iqiyi.com/v_third_party.html"),
    ]
    assert matches[0].score > matches[1].score


def test_iqiyi_metadata_provider_detail_omits_source_site_field() -> None:
    payload = {
        "data": {
            "templates": [
                {
                    "template": 103,
                    "albumInfo": {
                        "title": "疯狂动物城2",
                        "siteId": "iqiyi",
                        "siteName": "爱奇艺",
                        "pageUrl": "https://www.iqiyi.com/v_demo.html",
                        "year": {"value": "2025"},
                        "brief": {"value": "兔子朱迪与狐狸尼克正式组成搭档。"},
                        "releaseTime": {"key": "上映时间", "value": "2025-11-26"},
                        "timeLength": {"key": "片长", "value": "01:43:26"},
                        "baseTags": [{"value": "冒险"}, {"value": "动画"}, {"value": "喜剧"}],
                    }
                }
            ]
        }
    }
    provider = IqiyiMetadataProvider(get=lambda url, **kwargs: JsonResponse(payload))

    match = provider.search(MetadataQuery(title="疯狂动物城2", year="2025", category_name="电影"))[0]
    record = provider.get_detail(match)

    assert record.detail_fields == [
        {"label": "上映时间", "value": "2025-11-26"},
        {"label": "片长", "value": "01:43:26"},
    ]


def test_iqiyi_metadata_provider_search_prefers_category_matched_result_for_same_title() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        assert kwargs["params"]["key"] == "仙剑奇侠传3"
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "仙剑奇侠传三",
                                "channel": "电视剧,2",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_drama.html",
                                "year": {"value": "2025"},
                            }
                        },
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "仙剑奇侠传三",
                                "channel": "动漫,4",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_anime.html",
                                "year": {"value": "2025"},
                            }
                        },
                    ]
                }
            }
        )

    provider = IqiyiMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="仙剑奇侠传3", year="2025", category_name="动漫"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("仙剑奇侠传三", "https://www.iqiyi.com/v_anime.html"),
        ("仙剑奇侠传三", "https://www.iqiyi.com/v_drama.html"),
    ]
    assert matches[0].score > matches[1].score


def test_iqiyi_metadata_provider_search_reads_template_112_intent_album_infos() -> None:
    provider = IqiyiMetadataProvider(
        get=lambda url, **kwargs: JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 112,
                            "intentAlbumInfos": [
                                {
                                    "title": "成何体统",
                                    "channel": "电视剧,2",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "pageUrl": "http://www.iqiyi.com/v_live_action.html",
                                    "superscript": "2026",
                                    "promptDesc": "戏精联欢 胡闹开演",
                                    "metaTags": [
                                        {"name": "热度破9000", "style": "special"},
                                        {"name": "古装爱情", "style": ""},
                                        {"name": "喜剧", "style": ""},
                                    ],
                                },
                                {
                                    "title": "成何体统 第2季",
                                    "channel": "动漫,4",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "pageUrl": "http://www.iqiyi.com/v_anime_s2.html",
                                    "superscript": "2026",
                                },
                            ],
                        }
                    ]
                }
            }
        )
    )

    matches = provider.search(MetadataQuery(title="成何体统", year="2026", category_name="电视剧"))

    assert [(match.title, match.provider_id, match.year) for match in matches] == [
        ("成何体统", "http://www.iqiyi.com/v_live_action.html", "2026"),
        ("成何体统 第2季", "http://www.iqiyi.com/v_anime_s2.html", "2026"),
    ]
    assert matches[0].score > matches[1].score

    record = provider.get_detail(matches[0])

    assert record.title == "成何体统"
    assert record.year == "2026"
    assert record.overview == "戏精联欢 胡闹开演"
    assert record.genres == ["电视剧", "古装爱情", "喜剧"]
