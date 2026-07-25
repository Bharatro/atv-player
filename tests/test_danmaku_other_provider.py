from atv_player.danmaku.models import DanmakuRecord
from atv_player.danmaku.providers.other import OtherDanmakuProvider


class JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_other_provider_resolve_parses_danmuku_payload() -> None:
    def fake_get(url, **kwargs):
        assert kwargs["params"] == {"ac": "dm", "url": "https://v.qq.com/x/cover/abc/def.html"}
        return JsonResponse(
            {
                "danmuku": [
                    [12.5, "right", "#65ffff", "25", "真实弹幕一"],
                    [30.0, "top", "#ffffff", "25", "顶部弹幕"],
                    [5.0, "bottom", "#ff0000", "25", ""],
                    [8.0, "bottom", "#fff", "25", "底部弹幕"],
                ]
            }
        )

    provider = OtherDanmakuProvider(get=fake_get, server="https://dmku.hls.one/")
    records = provider.resolve("https://v.qq.com/x/cover/abc/def.html")

    assert [r.content for r in records] == ["真实弹幕一", "顶部弹幕", "底部弹幕"]
    assert records[0].pos == 1  # right
    assert records[1].pos == 5  # top
    assert records[2].pos == 4  # bottom
    assert provider.supports("anything") is True
    assert provider.search("x") == []
    assert provider.expand_page_url("u", "q") == []


def test_other_provider_resolve_returns_empty_on_http_error() -> None:
    import httpx

    def fake_get(url, **kwargs):
        raise httpx.HTTPError("boom")

    provider = OtherDanmakuProvider(get=fake_get, server="https://dmku.hls.one/")
    assert provider.resolve("https://v.qq.com/x/cover/abc/def.html") == []
