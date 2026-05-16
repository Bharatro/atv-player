import pytest

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.tencent import TencentMetadataProvider


class JsonResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def json(self):
        return self._payload


def test_tencent_metadata_provider_search_keeps_only_datatype_2_and_omits_rating() -> None:
    def fake_post(url: str, **kwargs):
        assert url == "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
        assert kwargs["params"] == {"vversion_platform": "2"}
        assert kwargs["json"]["query"] == "米小圈上学记4"
        return JsonResponse(
            {
                "data": {
                    "normalList": {
                        "itemList": [
                            {
                                "doc": {"dataType": 1, "id": "skip"},
                                "videoInfo": {
                                    "title": "应跳过的图文结果",
                                },
                            },
                            {
                                "doc": {"dataType": 2, "id": "mzc002008bgugk0"},
                                "videoInfo": {
                                    "title": "米小圈上学记4",
                                    "year": 2026,
                                    "typeName": "少儿",
                                    "area": "内地",
                                    "language": ["普通话版"],
                                    "directors": ["赵聪"],
                                    "actors": ["郭赫轩", "陈芷琰"],
                                    "richTags": [
                                        {"text": "儿童剧榜第2名", "type": 110, "uiType": 3},
                                        {"text": "儿童剧", "type": 80, "uiType": 1},
                                        {"text": "情景喜剧", "type": 80, "uiType": 1},
                                    ],
                                    "descrip": "第一条不应被使用",
                                    "imgUrl": "https://vcover.example/poster.jpg",
                                    "extraFields": {"score": 9.8},
                                    "playSites": [
                                        {
                                            "episodeInfoList": [
                                                {
                                                    "url": "https://v.qq.com/x/cover/mzc002008bgugk0/d4101lrdi9t.html"
                                                }
                                            ]
                                        }
                                    ],
                                },
                            },
                            {
                                "doc": {"dataType": 2, "id": "mzc002008older"},
                                "videoInfo": {
                                    "title": "米小圈上学记",
                                    "year": 2022,
                                    "playSites": [
                                        {
                                            "episodeInfoList": [
                                                {
                                                    "url": "https://v.qq.com/x/cover/mzc002008older/a4101older.html"
                                                }
                                            ]
                                        }
                                    ],
                                },
                            },
                        ]
                    }
                }
            }
        )

    provider = TencentMetadataProvider(post=fake_post)

    matches = provider.search(MetadataQuery(title="米小圈上学记4", year="2026", category_name="少儿"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("米小圈上学记4", "https://v.qq.com/x/cover/mzc002008bgugk0/d4101lrdi9t.html"),
        ("米小圈上学记", "https://v.qq.com/x/cover/mzc002008older/a4101older.html"),
    ]
    assert matches[0].provider == "tencent"
    assert matches[0].score > matches[1].score

    record = provider.get_detail(matches[0])

    assert record.provider == "tencent"
    assert record.title == "米小圈上学记4"
    assert record.year == "2026"
    assert record.poster == ""
    assert record.rating == ""
    assert record.overview == "第一条不应被使用"
    assert record.country == "内地"
    assert record.language == "普通话版"
    assert record.directors == ["赵聪"]
    assert record.actors == ["郭赫轩", "陈芷琰"]
    assert record.genres == ["少儿", "儿童剧", "情景喜剧"]
    assert record.detail_fields == [{"label": "来源站点", "value": "腾讯视频"}]


def test_tencent_metadata_provider_search_preserves_episode_sites_in_raw() -> None:
    def fake_post(url: str, **kwargs):
        assert url == "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
        return JsonResponse(
            {
                "data": {
                    "normalList": {
                        "itemList": [
                            {
                                "doc": {"dataType": 2, "id": "mzc002008bgugk0"},
                                "videoInfo": {
                                    "title": "米小圈上学记4",
                                    "year": 2026,
                                    "episodeSites": [
                                        {
                                            "showName": "腾讯视频",
                                            "episodeInfoList": [
                                                {"title": "第01话 金银米小圈1"},
                                                {"title": "第02话 金银米小圈2"},
                                            ],
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                }
            }
        )

    provider = TencentMetadataProvider(post=fake_post)

    match = provider.search(MetadataQuery(title="米小圈上学记4"))[0]

    assert "episode_sites" in match.raw
    assert match.raw["episode_sites"][0]["episodeInfoList"][0]["title"] == "第01话 金银米小圈1"


def test_tencent_exact_match_bonus_is_point_two() -> None:
    query = MetadataQuery(title="剑来 第二季")

    tencent_score = score_match(
        query,
        MetadataMatch(provider="tencent", provider_id="tx:1", title="剑来 第二季"),
    )
    iqiyi_score = score_match(
        query,
        MetadataMatch(provider="iqiyi", provider_id="iqiyi:1", title="剑来 第二季"),
    )

    assert tencent_score == pytest.approx(iqiyi_score + 0.05)
