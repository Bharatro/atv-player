import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.dandan import DandanDanmakuProvider


def test_dandan_search_expands_and_filters_requested_episode() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        path = kwargs["params"]["path"]
        calls.append(path)
        if path.startswith("/v2/search/anime?"):
            return httpx.Response(
                200,
                json={"animes": [{"animeId": 100, "animeTitle": "葬送的芙莉莲"}]},
            )
        if path == "/v2/bangumi/100":
            return httpx.Response(
                200,
                json={
                    "bangumi": {
                        "episodes": [
                            {
                                "episodeId": 10001,
                                "episodeNumber": "1",
                                "episodeTitle": "冒险的终点",
                            },
                            {
                                "episodeId": 10002,
                                "episodeNumber": "2",
                                "episodeTitle": "无需魔法",
                            },
                        ]
                    }
                },
            )
        raise AssertionError(path)

    provider = DandanDanmakuProvider(get=fake_get)

    items = provider.search("葬送的芙莉莲", original_name="葬送的芙莉莲 第2集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("dandan", "葬送的芙莉莲 第2集 无需魔法", "dandan://episode/10002")
    ]
    assert calls == [
        "/v2/search/anime?keyword=%E8%91%AC%E9%80%81%E7%9A%84%E8%8A%99%E8%8E%89%E8%8E%B2",
        "/v2/bangumi/100",
    ]


def test_dandan_resolve_maps_comments_and_skips_invalid_rows() -> None:
    def fake_get(url: str, **kwargs):
        assert kwargs["params"]["path"] == (
            "/v2/comment/10002?from=0&withRelated=true&chConvert=0"
        )
        return httpx.Response(
            200,
            json={
                "comments": [
                    {"cid": 1, "p": "1.25,1,16711680,[dandan]", "m": "滚动"},
                    {"cid": 2, "p": "2.5,5,65280,[dandan]", "m": "顶部"},
                    {"cid": 3, "p": "bad,1,255,[dandan]", "m": "坏时间"},
                    {"cid": 4, "p": "4,4,255,[dandan]", "m": ""},
                ]
            },
        )

    provider = DandanDanmakuProvider(get=fake_get)

    records = provider.resolve("dandan://episode/10002")

    assert [(r.time_offset, r.pos, r.color, r.content) for r in records] == [
        (1.25, 1, "16711680", "滚动"),
        (2.5, 5, "65280", "顶部"),
    ]


def test_dandan_supports_only_valid_internal_episode_urls() -> None:
    provider = DandanDanmakuProvider()

    assert provider.supports("dandan://episode/10002") is True
    assert provider.supports("dandan://episode/") is False
    assert provider.supports("animeko://episode/10002") is False


def test_dandan_search_failure_is_isolated() -> None:
    provider = DandanDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    assert provider.search("葬送的芙莉莲") == []


def test_dandan_resolve_failure_names_the_source() -> None:
    provider = DandanDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    with pytest.raises(DanmakuResolveError, match="弹弹Play弹幕获取失败"):
        provider.resolve("dandan://episode/10002")
