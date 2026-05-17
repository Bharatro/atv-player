import json
import threading
import time
import zlib

import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.providers.iqiyi import IqiyiDanmakuProvider


class JsonResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200, content: bytes = b"") -> None:
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._payload


def test_iqiyi_search_filters_noise_and_returns_episode_candidates() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        assert kwargs["params"]["key"] == "剑来"
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "albumInfo": {
                                "title": "剑来",
                                "channel": "教育,99",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {"title": "剑来 第1集", "pageUrl": "https://www.iqiyi.com/v_noise.html"}
                                ],
                            }
                        },
                        {
                            "albumInfo": {
                                "title": "剑来 精彩片段",
                                "channel": "动漫,4",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {"title": "剑来 花絮", "pageUrl": "https://www.iqiyi.com/v_clip.html"}
                                ],
                            }
                        },
                        {
                            "albumInfo": {
                                "title": "剑来",
                                "channel": "动漫,4",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {"title": "剑来 第1集", "pageUrl": "https://www.iqiyi.com/v_19rr1lm35o.html"},
                                    {"title": "剑来 第2集", "pageUrl": "https://www.iqiyi.com/v_19rr1lm35p.html"},
                                ],
                            }
                        },
                    ]
                }
            }
        )

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("剑来")

    assert [(item.name, item.url) for item in items] == [
        ("剑来 第1集", "https://www.iqiyi.com/v_19rr1lm35o.html"),
        ("剑来 第2集", "https://www.iqiyi.com/v_19rr1lm35p.html"),
    ]


def test_iqiyi_search_expands_template_112_intent_album_infos_without_videos() -> None:
    album_payload = {
        "albumId": 4222300210214001,
        "epsodelist": [
            {
                "order": 1,
                "shortTitle": "第1集",
                "subtitle": "认亲了",
                "playUrl": "http://www.iqiyi.com/v_ep1.html",
                "tvId": 7171864034925401,
                "duration": "00:45:21",
            },
            {
                "order": 2,
                "shortTitle": "第2集",
                "subtitle": "开会了",
                "playUrl": "http://www.iqiyi.com/v_ep2.html",
                "tvId": 7171864034925402,
                "duration": "00:44:58",
            },
        ],
    }

    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
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
                                        "pageUrl": "http://www.iqiyi.com/v_1xghiumsit0.html",
                                        "qipuId": 4222300210214001,
                                        "playQipuId": 7171864034925400,
                                        "subscriptContent": "32集全",
                                        "superscript": "2026",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_1xghiumsit0.html?jump=0":
            return JsonResponse(
                text=(
                    "<html>"
                    f"<input id=\"album-avlist-data\" value='{json.dumps(album_payload, ensure_ascii=False)}' />"
                    "</html>"
                )
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统 第1集", "https://www.iqiyi.com/v_ep1.html", 2721),
        ("成何体统 第2集", "https://www.iqiyi.com/v_ep2.html", 2698),
    ]


def test_iqiyi_search_expands_album_page_when_album_avlist_data_uses_double_quoted_value() -> None:
    album_payload = {
        "albumId": 4222300210214001,
        "epsodelist": [
            {
                "order": 1,
                "shortTitle": "第1集",
                "subtitle": "认亲了",
                "playUrl": "http://www.iqiyi.com/v_ep1.html",
                "tvId": 7171864034925401,
                "duration": "00:45:21",
            }
        ],
    }
    escaped_payload = json.dumps(album_payload, ensure_ascii=False).replace('"', "&quot;")

    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
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
                                        "pageUrl": "http://www.iqiyi.com/v_1xghiumsit0.html",
                                        "qipuId": 4222300210214001,
                                        "playQipuId": 7171864034925400,
                                        "subscriptContent": "32集全",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_1xghiumsit0.html?jump=0":
            return JsonResponse(
                text=(
                    "<html>"
                    f'<input value="{escaped_payload}" id="album-avlist-data" />'
                    "</html>"
                )
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统 第1集", "https://www.iqiyi.com/v_ep1.html", 2721),
    ]


def test_iqiyi_search_falls_back_to_legacy_search_when_mesh_returns_no_items() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse({"data": {"templates": []}})
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 4222300210214001,
                                    "channel": "电视剧,2",
                                    "albumTitle": "成何体统",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "videoinfos": [
                                        {
                                            "itemTitle": "成何体统 第1集",
                                            "itemLink": "http://www.iqiyi.com/v_ep1.html",
                                            "tvId": 7171864034925401,
                                            "timeLength": 2721,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统 第1集", "https://www.iqiyi.com/v_ep1.html", 2721),
    ]


def test_iqiyi_search_retries_mesh_without_site_filter_when_site_filtered_search_is_empty() -> None:
    album_payload = {
        "albumId": 4222300210214001,
        "epsodelist": [
            {
                "order": 1,
                "shortTitle": "第1集",
                "subtitle": "认亲了",
                "playUrl": "http://www.iqiyi.com/v_ep1.html",
                "tvId": 7171864034925401,
                "duration": "00:45:21",
            }
        ],
    }
    mesh_calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            mesh_calls.append(dict(kwargs["params"]))
            if kwargs["params"].get("site") == "iqiyi":
                return JsonResponse({"data": {"templates": []}})
            return JsonResponse(
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
                                        "pageUrl": "http://www.iqiyi.com/v_1xghiumsit0.html",
                                        "qipuId": 4222300210214001,
                                        "playQipuId": 7171864034925400,
                                        "subscriptContent": "24集全",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_1xghiumsit0.html?jump=0":
            return JsonResponse(
                text=(
                    "<html>"
                    f"<input id=\"album-avlist-data\" value='{json.dumps(album_payload, ensure_ascii=False)}' />"
                    "</html>"
                )
            )
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse({"data": "search result is empty"})
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统 第1集", "https://www.iqiyi.com/v_ep1.html", 2721),
    ]
    assert mesh_calls == [
        {
            "key": "成何体统 1集",
            "pageNum": 1,
            "pageSize": 25,
            "source": "input",
            "suggest": "",
            "site": "iqiyi",
            "mode": 1,
            "current_page": 1,
        },
        {
            "key": "成何体统 1集",
            "pageNum": 1,
            "pageSize": 25,
            "source": "input",
            "suggest": "",
            "mode": 1,
            "current_page": 1,
        },
    ]


def test_iqiyi_search_builds_first_episode_candidate_from_intent_album_info_when_episode_list_unavailable() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
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
                                        "pageUrl": "http://www.iqiyi.com/v_1xghiumsit0.html",
                                        "qipuId": 4222300210214001,
                                        "playQipuId": 7171864034925400,
                                        "subscriptContent": "32集全",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_1xghiumsit0.html?jump=0":
            return JsonResponse(text="<html><body>shell only</body></html>")
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse({"data": "search result is empty"})
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds, item.resolve_context) for item in items] == [
        (
            "成何体统 第1集",
            "https://www.iqiyi.com/v_1xghiumsit0.html",
            0,
            {
                "tv_id": 7171864034925400,
                "album_id": 4222300210214001,
                "category_id": 2,
                "duration_seconds": 0,
                "variety_year": 0,
            },
        )
    ]


def test_iqiyi_search_prefers_explicit_episode_query_for_mesh_results() -> None:
    mesh_keys: list[str] = []

    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            key = str(kwargs["params"]["key"])
            mesh_keys.append(key)
            if "2集" in key and "成何体统" in key:
                return JsonResponse(
                    {
                        "data": {
                            "templates": [
                                {
                                    "template": 101,
                                    "albumInfo": {
                                        "title": "成何体统",
                                        "channel": "电视剧,2",
                                        "siteId": "iqiyi",
                                        "siteName": "爱奇艺",
                                        "qipuId": 4222300210214001,
                                        "videos": [
                                            {
                                                "title": "成何体统第2集",
                                                "number": "2",
                                                "qipuId": 7355560014051900,
                                                "pageUrl": "https://www.iqiyi.com/v_20z4r9g9yz4.html",
                                                "subtitle": "开会了",
                                                "duration": 2787000,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                )
            return JsonResponse({"data": {"templates": []}})
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse({"data": "search result is empty"})
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 2集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统第2集", "https://www.iqiyi.com/v_20z4r9g9yz4.html", 2787),
    ]
    assert len(mesh_keys) == 1
    assert "成何体统" in mesh_keys[0]
    assert "2集" in mesh_keys[0]


def test_iqiyi_search_merges_mesh_and_legacy_results_when_both_have_candidates() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "template": 112,
                                "intentAlbumInfos": [
                                    {
                                        "title": "成何体统 第2季",
                                        "channel": "动漫,4",
                                        "siteId": "iqiyi",
                                        "siteName": "爱奇艺",
                                        "videos": [
                                            {
                                                "title": "成何体统 第2季 第2集 与君同行",
                                                "pageUrl": "http://www.iqiyi.com/v_s2e2.html",
                                                "qipuId": 7531234334704000,
                                                "duration": 1521000,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 4222300210214001,
                                    "channel": "电视剧,2",
                                    "albumTitle": "成何体统",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "videoinfos": [
                                        {
                                            "itemTitle": "成何体统 第1集",
                                            "itemLink": "http://www.iqiyi.com/v_ep1.html",
                                            "tvId": 7171864034925401,
                                            "timeLength": 2721,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("成何体统", original_name="成何体统 1集")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("成何体统 第2季 第2集 与君同行", "https://www.iqiyi.com/v_s2e2.html", 1521),
        ("成何体统 第1集", "https://www.iqiyi.com/v_ep1.html", 2721),
    ]


def test_iqiyi_search_raises_for_invalid_payload() -> None:
    provider = IqiyiDanmakuProvider(get=lambda url, **kwargs: JsonResponse({"oops": 1}))

    with pytest.raises(DanmakuSearchError, match="爱奇艺弹幕搜索结果解析失败"):
        provider.search("剑来")


def test_iqiyi_search_falls_back_to_mesh_results_when_legacy_album_count_is_zero() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "灵武大陆",
                                    "videoinfos": [
                                        {"itemTitle": "灵武大陆 第1集", "itemNumber": 1, "itemLink": "http://www.iqiyi.com/v_2gjv1pyuyik.html"},
                                        {"itemTitle": "灵武大陆 第178集", "itemNumber": 178, "itemLink": "http://www.iqiyi.com/v_1gpns7kbxog.html"},
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "灵武大陆",
                                    "channel": "动漫,4",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 4812694274119401,
                                    "videos": [
                                        {
                                            "title": "灵武大陆 第100集",
                                            "number": "100",
                                            "qipuId": 8142858142151200,
                                            "pageUrl": "https://www.iqiyi.com/v_100.html",
                                            "duration": 625000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("灵武大陆")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("灵武大陆 第100集", "https://www.iqiyi.com/v_100.html", 625)
    ]


def test_iqiyi_search_falls_back_to_mesh_results_when_legacy_search_is_empty() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse({"data": "search result is empty"})
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            assert kwargs["params"]["key"] == "哈哈哈哈哈第六季"
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "哈哈哈哈哈第6季",
                                    "channel": "综艺,6",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 5811390754506701,
                                    "videos": [
                                        {
                                            "title": "五哈6第1期上 邓超陈赫癫狂式唱山歌",
                                            "subtitle": "第1期上 邓超陈赫癫狂式唱山歌",
                                            "number": "30",
                                            "qipuId": 6761155121012800,
                                            "pageUrl": "https://www.iqiyi.com/v_1vqcuneq59o.html",
                                            "year": 20260404,
                                            "duration": 3632000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季")

    assert [(item.name, item.url) for item in items] == [
        ("哈哈哈哈哈第6季 第1期上 邓超陈赫癫狂式唱山歌", "https://www.iqiyi.com/v_1vqcuneq59o.html")
    ]


def test_iqiyi_search_falls_back_to_mesh_results_when_legacy_results_extract_to_empty() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 5811390754506701,
                                    "channel": "综艺,6",
                                    "itemTotalNumber": 12,
                                    "albumTitle": "哈哈哈哈哈第6季 精彩片段",
                                    "videoinfos": [
                                        {
                                            "itemTitle": "哈哈哈哈哈第6季 花絮",
                                            "itemLink": "https://www.iqiyi.com/v_clip.html",
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "哈哈哈哈哈第6季",
                                    "channel": "综艺,6",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 5811390754506701,
                                    "videos": [
                                        {
                                            "title": "五哈6第5期下 五哈团勇闯狗gogo乐园",
                                            "subtitle": "第5期下 五哈团勇闯狗gogo乐园",
                                            "number": "38",
                                            "qipuId": 9990001112223334,
                                            "pageUrl": "https://www.iqiyi.com/v_target5b.html",
                                            "year": 20260503,
                                            "duration": 3650000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季")

    assert [(item.name, item.url) for item in items] == [
        ("哈哈哈哈哈第6季 第5期下 五哈团勇闯狗gogo乐园", "https://www.iqiyi.com/v_target5b.html")
    ]


def test_iqiyi_search_dedupes_repeated_mesh_expansion_results_from_duplicate_albums() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "灵武大陆",
                                    "videoinfos": [
                                        {"itemTitle": "灵武大陆 第1集", "itemNumber": 1, "itemLink": "http://www.iqiyi.com/v_1.html"},
                                    ],
                                }
                            },
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "灵武大陆",
                                    "videoinfos": [
                                        {"itemTitle": "灵武大陆 第178集", "itemNumber": 178, "itemLink": "http://www.iqiyi.com/v_178.html"},
                                    ],
                                }
                            },
                        ]
                    }
                }
            )
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "灵武大陆",
                                    "channel": "动漫,4",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 4812694274119401,
                                    "videos": [
                                        {
                                            "title": "灵武大陆 第104集 五脉之魂",
                                            "number": "104",
                                            "qipuId": 8142858142151200,
                                            "pageUrl": "https://www.iqiyi.com/v_104.html",
                                            "duration": 625000,
                                        },
                                        {
                                            "title": "贺新春 灵武大陆+凌天独尊联动",
                                            "qipuId": 8142858142151299,
                                            "pageUrl": "https://www.iqiyi.com/v_promo.html",
                                            "duration": 180000,
                                        },
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("灵武大陆")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("灵武大陆 第104集 五脉之魂", "https://www.iqiyi.com/v_104.html", 625),
        ("贺新春 灵武大陆+凌天独尊联动", "https://www.iqiyi.com/v_promo.html", 180),
    ]


def test_iqiyi_search_mesh_variety_videos_use_album_title_and_preserve_year_metadata() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 5811390754506701,
                                    "channel": "综艺,6",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "哈哈哈哈哈第6季",
                                    "videoinfos": [
                                        {
                                            "itemTitle": "哈哈哈哈哈第6季",
                                            "itemNumber": 1,
                                            "itemLink": "https://www.iqiyi.com/v_album.html",
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "哈哈哈哈哈第6季",
                                    "channel": "综艺,6",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 5811390754506701,
                                    "videos": [
                                        {
                                            "title": "五哈6第1期上 邓超陈赫癫狂式唱山歌",
                                            "subtitle": "第1期上 邓超陈赫癫狂式唱山歌",
                                            "number": "30",
                                            "qipuId": 6761155121012800,
                                            "pageUrl": "https://www.iqiyi.com/v_1vqcuneq59o.html",
                                            "year": 20260404,
                                            "duration": 3632000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季")

    assert len(items) == 1
    assert items[0].name == "哈哈哈哈哈第6季 第1期上 邓超陈赫癫狂式唱山歌"
    assert items[0].resolve_context["variety_year"] == 20260404


def test_iqiyi_search_mesh_variety_alias_title_without_subtitle_keeps_album_title() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "哈哈哈哈哈第6季",
                                    "channel": "综艺,6",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 5811390754506701,
                                    "videos": [
                                        {
                                            "title": "五哈6第6期上 邓超表情包大师课2.0",
                                            "number": "6",
                                            "qipuId": 6761155121012866,
                                            "pageUrl": "https://www.iqiyi.com/v_target6a.html",
                                            "year": 20260509,
                                            "duration": 5418000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季")

    assert len(items) == 1
    assert items[0].name == "哈哈哈哈哈第6季 五哈6第6期上 邓超表情包大师课2.0"
    assert items[0].resolve_context["variety_year"] == 20260509


def test_iqiyi_search_reuses_mesh_expansion_for_duplicate_album_hits() -> None:
    mesh_calls = 0

    def fake_get(url: str, **kwargs):
        nonlocal mesh_calls
        if url == "https://search.video.iqiyi.com/o":
            return JsonResponse(
                {
                    "data": {
                        "docinfos": [
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "一人之下第六季",
                                    "videoinfos": [
                                        {"itemTitle": "一人之下第六季 第1集", "itemNumber": 1, "itemLink": "http://www.iqiyi.com/v_1.html"},
                                    ],
                                }
                            },
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "一人之下第六季",
                                    "videoinfos": [
                                        {"itemTitle": "一人之下第六季 第2集", "itemNumber": 2, "itemLink": "http://www.iqiyi.com/v_2.html"},
                                    ],
                                }
                            },
                            {
                                "albumDocInfo": {
                                    "albumId": 4812694274119401,
                                    "channel": "动漫,4",
                                    "itemTotalNumber": 0,
                                    "albumTitle": "一人之下第六季",
                                    "videoinfos": [
                                        {"itemTitle": "一人之下第六季 第3集", "itemNumber": 3, "itemLink": "http://www.iqiyi.com/v_3.html"},
                                    ],
                                }
                            },
                        ]
                    }
                }
            )
        if url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3":
            mesh_calls += 1
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "一人之下第六季",
                                    "channel": "动漫,4",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 4812694274119401,
                                    "videos": [
                                        {
                                            "title": "一人之下第六季 第6集",
                                            "number": "6",
                                            "qipuId": 1234567890123400,
                                            "pageUrl": "https://www.iqiyi.com/v_target6.html",
                                            "duration": 1440000,
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("一人之下第六季")

    assert mesh_calls == 1
    assert [(item.name, item.url) for item in items] == [
        ("一人之下第六季 第6集", "https://www.iqiyi.com/v_target6.html")
    ]


def test_iqiyi_search_keeps_episode_items_when_album_score_is_missing() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "albumInfo": {
                                "title": "八千里路云和月",
                                "channel": "电视剧,2",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {
                                        "title": "八千里路云和月第10集",
                                        "pageUrl": "http://www.iqiyi.com/v_kjnf5f02xg.html",
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        )

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("八千里路云和月")

    assert [(item.name, item.url) for item in items] == [
        ("八千里路云和月第10集", "https://www.iqiyi.com/v_kjnf5f02xg.html")
    ]


def test_iqiyi_search_drops_third_party_results_even_when_title_matches() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "albumInfo": {
                                "title": "黑夜告白",
                                "channel": "电视剧,2",
                                "siteName": "优酷",
                                "siteId": "youku",
                                "videos": [
                                    {
                                        "title": "黑夜告白 第1集",
                                        "pageUrl": "http://so.iqiyi.com/links/demo1",
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        )

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("黑夜告白")

    assert items == []


def test_iqiyi_search_expands_album_link_when_search_result_skips_middle_episodes() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "albumInfo": {
                                "title": "八千里路云和月",
                                "channel": "电视剧,2",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {"title": "八千里路云和月第1集", "pageUrl": "http://www.iqiyi.com/v_twylt9v918.html"},
                                    {"title": "八千里路云和月第14集", "pageUrl": "http://www.iqiyi.com/v_target14.html"},
                                    {"title": "八千里路云和月第40集", "pageUrl": "http://www.iqiyi.com/v_last40.html"},
                                ],
                            }
                        }
                    ]
                }
            }
        )

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("八千里路云和月")

    assert ("八千里路云和月第14集", "https://www.iqiyi.com/v_target14.html") in [
        (item.name, item.url) for item in items
    ]


def test_iqiyi_search_expands_album_link_via_album_avlist_api_config() -> None:
    def fake_get(url: str, **kwargs):
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "albumInfo": {
                                "title": "八千里路云和月",
                                "channel": "电视剧,2",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "videos": [
                                    {"title": "八千里路云和月第14集", "pageUrl": "http://www.iqiyi.com/v_target14.html"}
                                ],
                            }
                        }
                    ]
                }
            }
        )

    provider = IqiyiDanmakuProvider(get=fake_get)

    items = provider.search("八千里路云和月")

    assert ("八千里路云和月第14集", "https://www.iqiyi.com/v_target14.html") in [
        (item.name, item.url) for item in items
    ]


def test_iqiyi_search_falls_back_to_partial_search_results_when_album_expansion_times_out() -> None:
    def fake_get(url: str, **kwargs):
        raise httpx.ReadTimeout("timed out")

    provider = IqiyiDanmakuProvider(get=fake_get)

    with pytest.raises(httpx.ReadTimeout):
        provider.search("八千里路云和月")


def test_iqiyi_resolve_falls_back_to_cached_search_metadata_when_page_lacks_play_page_info() -> None:
    segment = zlib.compress(
        (
            "<root>"
            "<bulletInfoList>"
            "<bulletInfo><showTime>1500</showTime><content>缓存元数据解析</content><color>255</color></bulletInfo>"
            "</bulletInfoList>"
            "</root>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        if "mesh.if.iqiyi.com/portal/lw/search/homePageV3" in url:
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "八千里路云和月",
                                    "channel": "电视剧,2",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 6421036798758301,
                                    "videos": [
                                        {
                                            "title": "八千里路云和月第10集",
                                            "qipuId": 123456789000,
                                            "pageUrl": "http://www.iqiyi.com/v_20imo31bths.html",
                                            "duration": 299000,
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_20imo31bths.html":
            return JsonResponse(text="<html><head><title>shell page</title></head><body></body></html>")
        if url.endswith("123456789000_300_1.z"):
            assert kwargs["params"]["categoryid"] == 2
            assert kwargs["params"]["albumid"] == 6421036798758301
            return JsonResponse(content=segment)
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)
    items = provider.search("八千里路云和月")

    records = provider.resolve(items[0].url)

    assert [(record.time_offset, record.content, record.color) for record in records] == [
        (1.5, "缓存元数据解析", "255")
    ]


def test_iqiyi_resolve_uses_cached_duration_to_fetch_multiple_segments_when_page_is_shell() -> None:
    seen_urls: list[str] = []
    segment_1 = zlib.compress(
        (
            "<root><bulletInfoList>"
            "<bulletInfo><showTime>1000</showTime><content>第一页</content><color>255</color></bulletInfo>"
            "</bulletInfoList></root>"
        ).encode("utf-8")
    )
    segment_2 = zlib.compress(
        (
            "<root><bulletInfoList>"
            "<bulletInfo><showTime>301000</showTime><content>第二页</content><color>65280</color></bulletInfo>"
            "</bulletInfoList></root>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        seen_urls.append(url)
        if "mesh.if.iqiyi.com/portal/lw/search/homePageV3" in url:
            return JsonResponse(
                {
                    "data": {
                        "templates": [
                            {
                                "albumInfo": {
                                    "title": "八千里路云和月",
                                    "channel": "电视剧,2",
                                    "siteId": "iqiyi",
                                    "siteName": "爱奇艺",
                                    "qipuId": 6421036798758301,
                                    "videos": [
                                        {
                                            "title": "八千里路云和月第10集",
                                            "qipuId": 3063170563116300,
                                            "pageUrl": "http://www.iqiyi.com/v_20imo31bths.html",
                                            "duration": 301000,
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                }
            )
        if url == "https://www.iqiyi.com/v_20imo31bths.html":
            return JsonResponse(text="<html><body>shell only</body></html>")
        if url.endswith("3063170563116300_300_1.z"):
            return JsonResponse(content=segment_1)
        if url.endswith("3063170563116300_300_2.z"):
            return JsonResponse(content=segment_2)
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)
    items = provider.search("八千里路云和月")

    records = provider.resolve(items[0].url)

    assert [record.content for record in records] == ["第一页", "第二页"]
    assert seen_urls == [
        "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3",
        "https://www.iqiyi.com/v_20imo31bths.html",
        "https://cmts.iqiyi.com/bullet/63/00/3063170563116300_300_1.z",
        "https://cmts.iqiyi.com/bullet/63/00/3063170563116300_300_2.z",
    ]


def test_iqiyi_resolve_parses_page_info_downloads_segments_and_dedupes_records() -> None:
    calls: list[str] = []
    page_info = {
        "duration": "00:08:20",
        "tvName": "剑来 第1集",
        "albumId": 2024,
        "tvId": 987654321,
        "cid": 4,
    }
    segment_1 = zlib.compress(
        (
            "<danmu>"
            "<bulletInfo><showTime>1000</showTime><content>第一条</content><color>16777215</color><font>25</font></bulletInfo>"
            "<bulletInfo><showTime>2000</showTime><content>重复</content><color>255</color><font>18</font></bulletInfo>"
            "</danmu>"
        ).encode("utf-8")
    )
    segment_2 = zlib.compress(
        (
            "<danmu>"
            "<bulletInfo><showTime>2000</showTime><content>重复</content><color>255</color><font>18</font></bulletInfo>"
            "<bulletInfo><showTime>3500</showTime><content>第三条</content><color>65280</color><font>0</font></bulletInfo>"
            "</danmu>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if url == "https://www.iqiyi.com/v_19rr1lm35o.html":
            return JsonResponse(
                text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>'
            )
        if url.endswith("_300_1.z"):
            return JsonResponse(content=segment_1)
        if url.endswith("_300_2.z"):
            return JsonResponse(content=segment_2)
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_19rr1lm35o.html")

    assert [record.content for record in records] == ["第一条", "重复", "第三条"]
    assert [record.time_offset for record in records] == [1.0, 2.0, 3.5]
    assert [record.color for record in records] == ["16777215", "255", "65280"]
    assert calls == [
        "https://www.iqiyi.com/v_19rr1lm35o.html",
        "https://cmts.iqiyi.com/bullet/43/21/987654321_300_1.z",
        "https://cmts.iqiyi.com/bullet/43/21/987654321_300_2.z",
    ]


def test_iqiyi_resolve_treats_small_show_time_values_as_seconds_not_milliseconds() -> None:
    page_info = {
        "duration": "00:46:02",
        "tvName": "八千里路云和月 第17集",
        "albumId": 6421036798758301,
        "tvId": 3831645445180500,
        "cid": 2,
    }
    segment = zlib.compress(
        (
            "<danmu><data><entry><list>"
            "<bulletInfo><showTime>2</showTime><content>第二秒</content><color>ffffff</color></bulletInfo>"
            "<bulletInfo><showTime>175</showTime><content>一百七十五秒</content><color>FFFFFF</color></bulletInfo>"
            "</list></entry></data></danmu>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_demo_seconds.html":
            return JsonResponse(
                text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>'
            )
        return JsonResponse(content=segment)

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_demo_seconds.html")

    assert [(record.time_offset, record.content) for record in records[:2]] == [
        (2.0, "第二秒"),
        (175.0, "一百七十五秒"),
    ]
    assert [record.color for record in records[:2]] == ["16777215", "16777215"]


def test_iqiyi_resolve_parses_hex_color_values() -> None:
    page_info = {
        "duration": "00:05:00",
        "tvName": "彩色弹幕",
        "albumId": 6421036798758301,
        "tvId": 3831645445180500,
        "cid": 2,
    }
    segment = zlib.compress(
        (
            "<danmu><bulletInfoList>"
            "<bulletInfo><showTime>1000</showTime><content>红色</content><color>ff0000</color></bulletInfo>"
            "<bulletInfo><showTime>2000</showTime><content>绿色</content><color>00FF00</color></bulletInfo>"
            "</bulletInfoList></danmu>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_demo_colors.html":
            return JsonResponse(
                text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>'
            )
        return JsonResponse(content=segment)

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_demo_colors.html")

    assert [(record.content, record.color) for record in records] == [
        ("红色", "16711680"),
        ("绿色", "65280"),
    ]


def test_iqiyi_resolve_sanitizes_invalid_numeric_character_references() -> None:
    page_info = {
        "duration": "00:05:00",
        "tvName": "异常字符弹幕",
        "albumId": 6421036798758301,
        "tvId": 3831645445180500,
        "cid": 2,
    }
    segment = zlib.compress(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<danmu><data><entry><list>"
            "<bulletInfo><showTime>1000</showTime><content>正常弹幕</content><color>ffffff</color>"
            "<userInfo><name>檀翊次恋爱&#0;\u200d^</name></userInfo></bulletInfo>"
            "</list></entry></data></danmu>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_demo_invalid_ref.html":
            return JsonResponse(
                text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>'
            )
        return JsonResponse(content=segment)

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_demo_invalid_ref.html")

    assert [(record.content, record.color) for record in records] == [
        ("正常弹幕", "16777215")
    ]


def test_iqiyi_resolve_raises_when_page_info_is_missing() -> None:
    provider = IqiyiDanmakuProvider(get=lambda url, **kwargs: JsonResponse(text="<html></html>"))

    with pytest.raises(DanmakuResolveError, match="爱奇艺页面缺少 playPageInfo"):
        provider.resolve("https://www.iqiyi.com/v_demo.html")


def test_iqiyi_resolve_raises_when_all_segments_fail_to_decompress() -> None:
    page_info = {
        "duration": "00:00:10",
        "tvName": "剑来 第1集",
        "albumId": 2024,
        "tvId": 987654321,
        "cid": 4,
    }

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_demo.html":
            return JsonResponse(
                text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>'
            )
        return JsonResponse(content=b"not-zlib")

    provider = IqiyiDanmakuProvider(get=fake_get)

    with pytest.raises(DanmakuResolveError, match="爱奇艺弹幕分片解析失败"):
        provider.resolve("https://www.iqiyi.com/v_demo.html")


def test_iqiyi_resolve_supports_nested_play_page_data_and_bullet_info_list_payload() -> None:
    page_info = {
        "duration": "00:00:10",
        "tvName": "剑来 第1集",
        "playPageData": {
            "albumId": 2024,
            "tvId": 987654321,
            "cid": 4,
        },
    }
    segment = zlib.compress(
        (
            "<root>"
            "<bulletInfoList>"
            "<bulletInfo><showTime>1250</showTime><content>嵌套结构</content><color>16777215</color></bulletInfo>"
            "</bulletInfoList>"
            "</root>"
        ).encode("utf-8")
    )

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_nested.html":
            return JsonResponse(
                text=(
                    "<html><script>"
                    f"window.Q.PageInfo.playPageInfo={json.dumps(page_info)};"
                    "</script></html>"
                )
            )
        return JsonResponse(content=segment)

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_nested.html")

    assert [(record.time_offset, record.content) for record in records] == [(1.25, "嵌套结构")]


def test_iqiyi_resolve_downloads_segments_with_max_concurrency_of_four() -> None:
    state = {"active": 0, "max_active": 0}
    lock = threading.Lock()

    def fake_get(url: str, **kwargs):
        if url == "https://www.iqiyi.com/v_19rr1lm35o.html":
            page_info = {
                "duration": "00:25:01",
                "tvName": "剑来 第1集",
                "albumId": 2024,
                "tvId": 987654321,
                "cid": 4,
            }
            return JsonResponse(text=f'<html><script>window.Q.PageInfo.playPageInfo={json.dumps(page_info)};</script></html>')
        if "cmts.iqiyi.com" in url and url.endswith(".z"):
            page_index = int(url.rsplit("_", 1)[-1].split(".", 1)[0])
            with lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            time.sleep(0.05)
            with lock:
                state["active"] -= 1
            segment = zlib.compress(
                (
                    "<danmu>"
                    f"<bulletInfo><showTime>{page_index * 1000}</showTime><content>第{page_index}页</content><color>255</color></bulletInfo>"
                    "</danmu>"
                ).encode("utf-8")
            )
            return JsonResponse(content=segment)
        raise AssertionError(f"Unexpected URL: {url}")

    provider = IqiyiDanmakuProvider(get=fake_get)

    records = provider.resolve("https://www.iqiyi.com/v_19rr1lm35o.html")

    assert len(records) == 6
    assert state["max_active"] == 4
