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
