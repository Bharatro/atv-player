import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.renren import RenrenDanmakuProvider


def test_renren_supports_static_danmaku_urls_and_custom_scheme() -> None:
    provider = RenrenDanmakuProvider()

    assert provider.supports("renren://danmu/series-ep-1") is True
    assert (
        provider.supports(
            "https://static-dm.qwdjapp.com/v1/produce/danmu/EPISODE/ep-1"
        )
        is True
    )
    assert (
        provider.supports(
            "https://static-dm.lequkeji.com/v1/produce/danmu/EPISODE/ep-1"
        )
        is True
    )
    assert (
        provider.supports(
            "https://static-dm.rrmj.plus/v1/produce/danmu/EPISODE/ep-1"
        )
        is True
    )
    assert (
        provider.supports("https://example.com/v1/produce/danmu/EPISODE/ep-1")
        is False
    )


def test_renren_resolve_fetches_tv_with_signed_headers_and_maps_comments() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        assert url == "https://static-dm.qwdjapp.com/v1/produce/danmu/EPISODE/ep-1"
        headers = kwargs["headers"]
        assert headers["clientVersion"] == "1.2.2"
        assert headers["clienttype"] == "android_qwtv_RRSP"
        assert headers["pkt"] == "rrmj"
        assert headers["User-Agent"] == "okhttp/3.12.13"
        assert headers["aliid"].startswith("aY")
        assert headers["sign"]
        assert kwargs["follow_redirects"] is True
        assert kwargs["timeout"] == 10.0
        return httpx.Response(
            200,
            json=[
                {"p": "1.25,1,25,16711680,0,0,user-1,1001", "d": "滚动"},
                {"p": "2.5,4,25,65280,0,0,user-2,1002", "content": "底部"},
                {"p": "3.5,5,25,255,0,0,user-3,1003", "d": "顶部"},
            ],
        )

    provider = RenrenDanmakuProvider(get=fake_get)

    records = provider.resolve("renren://danmu/series-ep-1")

    assert [
        (record.time_offset, record.pos, record.color, record.content)
        for record in records
    ] == [
        (1.25, 1, "16711680", "滚动"),
        (2.5, 4, "65280", "底部"),
        (3.5, 5, "255", "顶部"),
    ]
    assert len(calls) == 1


def test_renren_resolve_treats_document_not_found_as_empty() -> None:
    def fake_get(url: str, **kwargs):
        assert kwargs["follow_redirects"] is True
        return httpx.Response(404, json={"error": "Document not found"})

    provider = RenrenDanmakuProvider(get=fake_get)

    assert provider.resolve("renren://danmu/ep-empty") == []


def test_renren_resolve_falls_back_to_mac_when_tv_endpoint_fails() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if "static-dm.qwdjapp.com" in url:
            raise httpx.HTTPError("tv failed")
        if "static-dm.lequkeji.com" in url:
            assert kwargs["headers"]["User-Agent"].startswith("%E4%BA%BA%E4%BA%BA")
            return httpx.Response(
                200,
                json={"data": [{"p": "4,1,25,16777215", "d": "Mac"}]},
            )
        raise AssertionError(url)

    provider = RenrenDanmakuProvider(get=fake_get)

    records = provider.resolve("renren://danmu/ep-2")

    assert [(record.time_offset, record.content) for record in records] == [
        (4.0, "Mac")
    ]
    assert calls == [
        "https://static-dm.qwdjapp.com/v1/produce/danmu/EPISODE/ep-2",
        "https://static-dm.lequkeji.com/v1/produce/danmu/EPISODE/ep-2",
    ]


def test_renren_resolve_raises_when_all_tiers_fail() -> None:
    def fake_get(url: str, **kwargs):
        raise httpx.HTTPError("network down")

    provider = RenrenDanmakuProvider(get=fake_get)

    with pytest.raises(DanmakuResolveError, match="人人弹幕获取失败"):
        provider.resolve("renren://danmu/ep-3")


def test_renren_search_expands_matching_series_into_episode_candidates() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if url.startswith("https://api.pleasfun.com/search/comprehensive/precise-mixed"):
            assert "keywords=%E5%89%91%E6%9D%A5" in url
            return httpx.Response(
                200,
                json={
                    "code": "0000",
                    "data": {
                        "seasonList": [
                            {
                                "id": 2001,
                                "title": "剑来",
                                "year": 2026,
                                "cover": "https://img.example/jianlai.jpg",
                            }
                        ]
                    },
                },
            )
        if url.startswith("https://api.gorafie.com/qwtv/drama/details"):
            assert "seriesId=2001" in url
            return httpx.Response(
                200,
                json={
                    "code": "0000",
                    "data": {
                        "episodeList": [
                            {"sid": "ep-1", "episodeNo": 1, "title": "第1集"},
                            {"sid": "ep-2", "episodeNo": 2, "title": "第2集"},
                        ]
                    },
                },
            )
        raise AssertionError(url)

    provider = RenrenDanmakuProvider(get=fake_get)

    items = provider.search("剑来", original_name="剑来 2集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("renren", "剑来 第2集", "renren://danmu/2001-ep-2")
    ]
    assert len(calls) == 2
