import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.bahamut import BahamutDanmakuProvider


def test_bahamut_search_uses_traditional_query_and_expands_episode() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs.get("params") or {}))
        if url.endswith("/mobile_app/anime/v1/search.php"):
            assert kwargs["params"]["kw"] == "葬送的芙莉蓮"
            return httpx.Response(
                200,
                json={"anime": [{"title": "葬送的芙莉蓮", "video_sn": 5001}]},
            )
        if url.endswith("/anime/v1/video.php"):
            assert kwargs["params"]["videoSn"] == "5001"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "anime": {
                            "episodes": {
                                "0": [
                                    {"episode": "1", "videoSn": 5101},
                                    {"episode": "2", "videoSn": 5102},
                                ]
                            }
                        }
                    }
                },
            )
        raise AssertionError(url)

    provider = BahamutDanmakuProvider(
        get=fake_get,
        traditionalize=lambda value: value.replace("莲", "蓮"),
    )

    items = provider.search("葬送的芙莉莲", original_name="葬送的芙莉莲 第2集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("bahamut", "葬送的芙莉莲 第2集", "bahamut://episode/5102")
    ]
    assert len(calls) == 2


def test_bahamut_resolve_maps_time_position_and_hex_color() -> None:
    def fake_get(url: str, **kwargs):
        assert url.endswith("/anime/v1/danmu.php")
        assert kwargs["params"] == {"geo": "TW,HK", "videoSn": "5102"}
        return httpx.Response(
            200,
            json={
                "data": {
                    "danmu": [
                        {
                            "sn": 1,
                            "time": 15,
                            "position": 0,
                            "color": "#ff0000",
                            "text": "滚动",
                        },
                        {
                            "sn": 2,
                            "time": 25,
                            "position": 1,
                            "color": "#00ff00",
                            "text": "顶部",
                        },
                        {
                            "sn": 3,
                            "time": 35,
                            "position": 2,
                            "color": "zzzzzz",
                            "text": "底部",
                        },
                        {
                            "sn": 4,
                            "time": "bad",
                            "position": 0,
                            "color": "#ffffff",
                            "text": "坏时间",
                        },
                    ]
                }
            },
        )

    provider = BahamutDanmakuProvider(get=fake_get)

    records = provider.resolve("bahamut://episode/5102")

    assert [(r.time_offset, r.pos, r.color, r.content) for r in records] == [
        (1.5, 1, "16711680", "滚动"),
        (2.5, 5, "65280", "顶部"),
        (3.5, 4, "16777215", "底部"),
    ]


def test_bahamut_supports_only_valid_internal_episode_urls() -> None:
    provider = BahamutDanmakuProvider()

    assert provider.supports("bahamut://episode/5102") is True
    assert provider.supports("bahamut://episode/") is False
    assert provider.supports("dandan://episode/5102") is False


def test_bahamut_search_failure_is_isolated() -> None:
    provider = BahamutDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    assert provider.search("葬送的芙莉莲") == []


def test_bahamut_resolve_failure_names_the_source() -> None:
    provider = BahamutDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    with pytest.raises(DanmakuResolveError, match="巴哈姆特弹幕获取失败"):
        provider.resolve("bahamut://episode/5102")
