import json

import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.migu import MiguDanmakuProvider, migu_decrypt


def test_migu_search_expands_long_media_into_episode_candidates() -> None:
    calls: list[tuple[str, dict | None]] = []

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs.get("json") or json.loads(kwargs["content"])))
        assert url == "https://jadeite.migu.cn/search/v3/open-search"
        return httpx.Response(
            200,
            json={
                "body": {
                    "contentInfoList": [
                        {
                            "shortMediaAsset": {
                                "name": "深空彼岸",
                                "isLong": 1,
                                "pID": "album-1",
                                "year": "2026",
                                "contDisplayName": "动漫",
                            }
                        },
                        {
                            "shortMediaAsset": {
                                "name": "深空彼岸 花絮",
                                "isLong": 0,
                                "pID": "short-1",
                            }
                        },
                    ]
                }
            },
        )

    def fake_get(url: str, **kwargs):
        assert url == "https://v3-sc.miguvideo.com/program/v4/cont/content-info/album-1/1"
        return httpx.Response(
            200,
            json={
                "body": {
                    "data": {
                        "datas": [
                            {"name": "第1集", "pID": "ep-1", "duration": "00:24:30"},
                            {"name": "第2集", "pID": "ep-2", "duration": "00:24:31"},
                        ]
                    }
                }
            },
        )

    provider = MiguDanmakuProvider(get=fake_get, post=fake_post)

    items = provider.search("深空彼岸")

    assert calls[0][1]["k"] == "深空彼岸"
    assert [(item.provider, item.name, item.url, item.duration_seconds) for item in items] == [
        (
            "migu",
            "深空彼岸 第1集",
            "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1",
            1470,
        ),
        (
            "migu",
            "深空彼岸 第2集",
            "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-2",
            1471,
        ),
    ]


def test_migu_resolve_uses_primed_context_and_maps_segment_comments() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if url.endswith("/0/30/020"):
            return httpx.Response(
                200,
                json={
                    "body": {
                        "result": [
                            {
                                "cid": "1",
                                "playtime": 1.5,
                                "textcolor": "FF0000",
                                "msg": "第一条",
                            },
                            {
                                "cid": "2",
                                "playtime": "2.5",
                                "textcolor": "#00ff00",
                                "msg": "顶部不支持也按滚动处理",
                            },
                        ]
                    }
                },
            )
        if url.endswith("/30/60/020"):
            return httpx.Response(200, text='{"body":{"result":[{"playtime":31,"msg":"第二段"}]}}')
        raise AssertionError(url)

    provider = MiguDanmakuProvider(get=fake_get)
    provider.prime_resolve_context(
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1",
        {"album_id": "album-1", "episode_id": "ep-1", "duration_seconds": 60},
    )

    records = provider.resolve(
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1"
    )

    assert [(record.time_offset, record.pos, record.color, record.content) for record in records] == [
        (1.5, 1, "16711680", "第一条"),
        (2.5, 1, "65280", "顶部不支持也按滚动处理"),
        (31.0, 1, "16777215", "第二段"),
    ]
    assert calls == [
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1/0/30/020",
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1/30/60/020",
    ]


def test_migu_resolve_fetches_detail_when_context_has_no_duration() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://v3-sc.miguvideo.com/program/v4/cont/content-info/ep-1/1":
            return httpx.Response(
                200,
                json={"body": {"data": {"epsID": "album-1", "playing": {"duration": "00:00:30"}}}},
            )
        if url.endswith("/0/30/020"):
            return httpx.Response(200, json={"body": {"result": [{"playtime": 3, "msg": "详情解析"}]}})
        raise AssertionError(url)

    provider = MiguDanmakuProvider(get=fake_get)

    records = provider.resolve(
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1"
    )

    assert [(record.time_offset, record.content) for record in records] == [(3.0, "详情解析")]


def test_migu_decrypt_decodes_known_gateway_ciphertext() -> None:
    plaintext = migu_decrypt(
        "JC+ssUOw2pdJ5AAPHofIXIGfii6fufgztv6qaxe5nyVDLrlLYrwj1AI/alkv8v4tjlnY0dMsus7PGURb5dAEDZq4F3DnE2WlVrcNcRTDTqg="
    )

    assert json.loads(plaintext) == {
        "code": 200,
        "message": None,
        "body": {"result": []},
        "timeStamp": 1780275235703,
    }


def test_migu_resolve_raises_when_all_segments_fail() -> None:
    def fake_get(url: str, **kwargs):
        raise httpx.HTTPError("boom")

    provider = MiguDanmakuProvider(get=fake_get)
    provider.prime_resolve_context(
        "https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1",
        {"album_id": "album-1", "episode_id": "ep-1", "duration_seconds": 30},
    )

    with pytest.raises(DanmakuResolveError, match="咪咕弹幕分段解析失败"):
        provider.resolve("https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/album-1/ep-1")


def test_migu_supports_migu_urls() -> None:
    provider = MiguDanmakuProvider()

    assert provider.supports("https://webapi.miguvideo.com/gateway/live_barrage/videox/barrage/v2/list/a/b") is True
    assert provider.supports("https://www.miguvideo.com/p/detail/123") is True
