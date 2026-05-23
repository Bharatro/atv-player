from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.bilibili import BilibiliMetadataProvider


class JsonResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def json(self):
        return self._payload


def test_bilibili_metadata_provider_search_maps_bangumi_results_and_prefers_exact_match() -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs.get("params")))
        if "x/frontend/finger/spi" in url:
            return JsonResponse({"code": 0, "data": {"b_3": "buvid3-demo", "b_4": "buvid4-demo"}})
        if "x/web-interface/nav" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "data": {
                        "wbi_img": {
                            "img_url": "https://i0.hdslb.com/bfs/wbi/abc123.png",
                            "sub_url": "https://i0.hdslb.com/bfs/wbi/def456.png",
                        }
                    },
                }
            )
        if "x/web-interface/wbi/search/type" in url:
            assert kwargs["params"]["search_type"] == "media_bangumi"
            assert kwargs["params"]["keyword"] == "牧神记"
            assert "wts" in kwargs["params"]
            assert "w_rid" in kwargs["params"]
            return JsonResponse(
                {
                    "code": 0,
                    "data": {
                        "result": [
                            {
                                "media_id": 1,
                                "season_id": 45969,
                                "title": "<em class=\"keyword\">牧神记</em>",
                                "season_type_name": "国创",
                                "styles": "小说改/玄幻/热血/战斗",
                                "areas": "中国大陆",
                                "desc": "主角秦牧在大墟成长。",
                                "cover": "https://i0.hdslb.com/bfs/bangumi/image/demo.png",
                                "pubtime": 1729958400,
                                "index_show": "更新至第82话",
                                "url": "https://www.bilibili.com/bangumi/play/ss45969",
                                "eps": [
                                    {"title": "1", "index_title": "1", "long_title": "天黑别出门"},
                                    {"title": "2", "index_title": "2", "long_title": "我是霸体"},
                                ],
                                "media_score": {"score": 9.6, "user_count": 19280},
                            },
                            {
                                "media_id": 2,
                                "season_id": 45970,
                                "title": "牧神",
                                "season_type_name": "国创",
                                "styles": "玄幻",
                                "areas": "中国大陆",
                                "pubtime": 1729958400,
                                "url": "https://www.bilibili.com/bangumi/play/ss45970",
                            },
                        ]
                    },
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    provider = BilibiliMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="牧神记", category_name="动漫"))

    assert [match.title for match in matches] == ["牧神记", "牧神"]
    assert matches[0].provider == "bilibili"
    assert matches[0].provider_id == "https://www.bilibili.com/bangumi/play/ss45969"
    assert matches[0].year == "2024"
    assert matches[0].score > matches[1].score
    assert matches[0].raw["subtitle"] == "国创 · 更新至第82话"
    assert matches[0].raw["genres"] == ["小说改", "玄幻", "热血", "战斗"]
    assert matches[0].raw["eps"][0]["long_title"] == "天黑别出门"
    assert [url for url, _params in calls[:3]] == [
        "https://api.bilibili.com/x/frontend/finger/spi",
        "https://api.bilibili.com/x/web-interface/nav",
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
    ]


def test_bilibili_metadata_provider_get_detail_maps_minimal_metadata_and_omits_rating() -> None:
    provider = BilibiliMetadataProvider(get=lambda url, **kwargs: JsonResponse({"code": 0, "data": {}}))
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        title="牧神记",
        year="2024",
        raw={
            "title": "牧神记",
            "desc": "主角秦牧在大墟成长。",
            "styles": "小说改/玄幻/热血/战斗",
            "genres": ["小说改", "玄幻", "热血", "战斗"],
            "areas": "中国大陆",
            "cover": "https://i0.hdslb.com/bfs/bangumi/image/demo.png",
            "media_score": {"score": 9.6, "user_count": 19280},
            "staff": "总导演：沈乐平",
            "cv": "少年秦牧：张若瑜",
            "season_type_name": "国创",
            "index_show": "更新至第82话",
            "subtitle": "国创 · 更新至第82话",
        },
    )

    record = provider.get_detail(match)

    assert record.provider == "bilibili"
    assert record.provider_id == "https://www.bilibili.com/bangumi/play/ss45969"
    assert record.title == "牧神记"
    assert record.year == "2024"
    assert record.poster == ""
    assert record.rating == ""
    assert record.overview == "主角秦牧在大墟成长。"
    assert record.country == "中国大陆"
    assert record.genres == ["小说改", "玄幻", "热血", "战斗"]
    assert record.detail_fields == [
        {"label": "分区", "value": "国创"},
        {"label": "更新状态", "value": "更新至第82话"},
        {"label": "声优", "value": "少年秦牧：张若瑜"},
        {"label": "制作信息", "value": "总导演：沈乐平"},
    ]


def test_bilibili_metadata_provider_can_enrich_only_anime_context() -> None:
    provider = BilibiliMetadataProvider(get=lambda url, **kwargs: JsonResponse({"code": 0, "result": {}}))

    anime = MetadataQuery(title="牧神记", category_name="动漫")
    movie = MetadataQuery(title="长安的荔枝", category_name="电影")

    class Ctx:
        def __init__(self, query) -> None:
            self._query = query

        def to_query(self):
            return self._query

    assert provider.can_enrich(Ctx(anime)) is True
    assert provider.can_enrich(Ctx(movie)) is False


def test_bilibili_metadata_provider_get_detail_fetches_season_detail_and_normalizes_main_episodes() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if "pgc/view/web/season" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "season_id": 148433,
                        "title": "凸变英雄X",
                        "evaluate": "这是番剧详情简介",
                        "cover": "https://i0.hdslb.com/bfs/bangumi/image/season.png",
                        "areas": [{"name": "中国大陆"}],
                        "styles": [{"name": "热血"}, {"name": "战斗"}],
                        "stat": {"followers": 12345},
                        "up_info": {},
                        "publish": {"is_finish": 0},
                        "new_ep": {"desc": "更新至第28话"},
                        "actors": "声优A\n声优B",
                        "staff": "导演A\n编剧B",
                        "episodes": [
                            {"title": "1", "long_title": "启程", "badge": "", "ep_id": 1},
                            {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                        ],
                    },
                }
            )
        if "pgc/web/season/section" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "main_section": {
                            "episodes": [
                                {"title": "1", "long_title": "启程", "badge": "", "ep_id": 1},
                                {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                            ]
                        },
                        "section": [
                            {
                                "title": "SP",
                                "episodes": [
                                    {"title": "SP", "long_title": "特别篇", "badge": "SP", "ep_id": 999}
                                ],
                            }
                        ],
                    },
                }
            )
        raise AssertionError(url)

    provider = BilibiliMetadataProvider(get=fake_get)
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss148433",
        title="凸变英雄X",
        year="2025",
        raw={"title": "凸变英雄X", "season_id": 148433, "season_type_name": "国创"},
    )

    record = provider.get_detail(match)

    assert any("pgc/view/web/season" in url for url in calls)
    assert any("pgc/web/season/section" in url for url in calls)
    assert record.title == "凸变英雄X"
    assert record.poster == "https://i0.hdslb.com/bfs/bangumi/image/season.png"
    assert record.country == "中国大陆"
    assert record.genres == ["热血", "战斗"]
    assert record.overview == "这是番剧详情简介"
    assert {"label": "更新状态", "value": "更新至第28话"} in record.detail_fields
    assert match.raw["episodes"] == [
        {"episode_number": 1, "title": "1", "long_title": "启程", "badge": "", "episode_type": "main", "sort": 1},
        {"episode_number": 28, "title": "28", "long_title": "答案", "badge": "", "episode_type": "main", "sort": 28},
    ]


def test_bilibili_metadata_provider_filters_verbose_staff_to_creative_credits() -> None:
    provider = BilibiliMetadataProvider(get=lambda url, **kwargs: JsonResponse({"code": 0, "data": {}}))
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        title="牧神记",
        raw={
            "title": "牧神记",
            "staff": (
                "原作：宅猪 / 出品人：李旎 沈乐平 / 总制片人：张圣晏 / 总监制：朱贝宁 / "
                "监制：魏本娜 龚磊 曹继炜 / 制片人：陈卿 姚琼 / 制片：陈晓璐 / "
                "版权支持：刘綦 易小丽 / IP管理与合作总负责：茶仙 / 内容宣发总策划：王蓉 乔理文 / "
                "市场中心总策划：杨亮 / 执行制片人：王媛 薛小明 魏江涛 / 品牌运营：尹蓉 / "
                "联合导演：姚青 / 总编剧、总导演：沈乐平"
            ),
            "cv": "少年秦牧：张若瑜/姚铭舜 / 灵毓秀：李欣",
            "season_type_name": "国创",
            "index_show": "连载中, 每周日 11:00更新",
        },
    )

    record = provider.get_detail(match)

    assert {"label": "制作信息", "value": "原作：宅猪 / 联合导演：姚青 / 总编剧、总导演：沈乐平"} in record.detail_fields
    assert all("出品人" not in field["value"] for field in record.detail_fields)
    assert all("制片" not in field["value"] for field in record.detail_fields)
    assert {"label": "声优", "value": "少年秦牧：张若瑜/姚铭舜 / 灵毓秀：李欣"} in record.detail_fields


def test_bilibili_metadata_provider_maps_rich_season_metadata_without_rating() -> None:
    def fake_get(url: str, **kwargs):
        if "pgc/view/web/season" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "season_id": 45969,
                        "media_id": 21082961,
                        "title": "牧神记",
                        "evaluate": "主角秦牧逐渐成长，为芸芸众生而战。",
                        "cover": "https://i0.hdslb.com/bfs/bangumi/image/cover.png",
                        "areas": [{"name": "中国大陆"}],
                        "styles": ["小说改", "玄幻", "热血", "战斗"],
                        "new_ep": {"desc": "连载中, 每周日 11:00更新"},
                        "publish": {"pub_time": "2024-10-27 11:00:00", "pub_time_show": "2024年10月27日11:00"},
                        "rating": {"count": 19560, "score": 9.6},
                        "stat": {
                            "views": 1795347758,
                            "favorites": 6534663,
                            "follow_text": "653.5万追番",
                            "likes": 11747404,
                            "coins": 6451277,
                            "favorite": 1449838,
                            "reply": 333402,
                            "danmakus": 3480419,
                            "share": 145093,
                        },
                        "actors": "少年秦牧：张若瑜/姚铭舜\n灵毓秀：李欣",
                        "staff": "原作：宅猪\n联合导演：姚青\n总编剧、总导演：沈乐平",
                    },
                }
            )
        if "pgc/web/season/section" in url:
            return JsonResponse({"code": 0, "result": {"main_section": {"episodes": []}}})
        raise AssertionError(url)

    provider = BilibiliMetadataProvider(get=fake_get)
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        title="牧神记",
        raw={"season_id": 45969},
    )

    record = provider.get_detail(match)

    assert record.title == "牧神记"
    assert record.year == "2024"
    assert record.rating == ""
    assert record.poster == "https://i0.hdslb.com/bfs/bangumi/image/cover.png"
    assert record.overview == "主角秦牧逐渐成长，为芸芸众生而战。"
    assert record.country == "中国大陆"
    assert record.genres == ["小说改", "玄幻", "热血", "战斗"]
    assert record.detail_fields == [
        {"label": "更新状态", "value": "连载中, 每周日 11:00更新"},
        {"label": "开播", "value": "2024年10月27日11:00"},
        {"label": "播放", "value": "18.0亿"},
        {"label": "追番", "value": "653.5万追番"},
        {"label": "点赞", "value": "1174.7万"},
        {"label": "投币", "value": "645.1万"},
        {"label": "收藏", "value": "145.0万"},
        {"label": "回复", "value": "33.3万"},
        {"label": "弹幕", "value": "348.0万"},
        {"label": "分享", "value": "14.5万"},
        {"label": "声优", "value": "少年秦牧：张若瑜/姚铭舜 / 灵毓秀：李欣"},
        {"label": "制作信息", "value": "原作：宅猪 / 联合导演：姚青 / 总编剧、总导演：沈乐平"},
    ]
    assert all(field["label"] != "Season ID" for field in record.detail_fields)


def test_bilibili_metadata_provider_get_detail_tolerates_integer_type_field_in_season_detail() -> None:
    def fake_get(url: str, **kwargs):
        if "pgc/view/web/season" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "season_id": 148433,
                        "title": "凸变英雄X",
                        "type": 1,
                        "evaluate": "这是番剧详情简介",
                        "cover": "https://i0.hdslb.com/bfs/bangumi/image/season.png",
                        "areas": [{"name": "中国大陆"}],
                        "styles": [{"name": "热血"}],
                        "new_ep": {"desc": "更新至第28话"},
                        "episodes": [
                            {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                        ],
                    },
                }
            )
        if "pgc/web/season/section" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "main_section": {
                            "episodes": [
                                {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                            ]
                        }
                    },
                }
            )
        raise AssertionError(url)

    provider = BilibiliMetadataProvider(get=fake_get)
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss148433",
        title="凸变英雄X",
        year="2025",
        raw={"title": "凸变英雄X", "season_id": 148433, "season_type_name": "国创"},
    )

    record = provider.get_detail(match)

    assert record.title == "凸变英雄X"
    assert {"label": "分区", "value": "国创"} in record.detail_fields
