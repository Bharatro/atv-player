import atv_player.danmaku.direct_parse as direct_parse_module
from atv_player.danmaku.direct_parse import DirectParseDanmakuController
from atv_player.models import PlayItem
from atv_player.network_proxy import ProxyConfig, ProxyDecider


def test_direct_parse_danmaku_controller_refreshes_single_source_candidate() -> None:
    controller = DirectParseDanmakuController(load=lambda _url: {})
    item = PlayItem(
        title="第10话",
        url="",
        original_url="https://v.qq.com/x/cover/demo/ep10.html",
        vod_id="https://v.qq.com/x/cover/demo/ep10.html",
        media_title="剑来 第二季",
    )

    controller.refresh_danmaku_sources(item)

    assert item.danmaku_search_title == "剑来 第二季"
    assert item.danmaku_search_episode == "第10话"
    assert item.danmaku_search_query == "剑来 第二季 第10话"
    assert len(item.danmaku_candidates) == 1
    assert item.danmaku_candidates[0].provider == "direct_parse"
    assert item.danmaku_candidates[0].options[0].url == "https://v.qq.com/x/cover/demo/ep10.html"
    assert item.selected_danmaku_provider == "direct_parse"
    assert item.selected_danmaku_url == "https://v.qq.com/x/cover/demo/ep10.html"


def test_direct_parse_danmaku_controller_switch_source_converts_payload_to_xml() -> None:
    payload = {
        "code": 23,
        "name": "demo",
        "danmuku": [
            [2, "right", "#fff", "32", "✨有 9 条弹幕列队来袭~做好准备吧！✨"],
            [6, "top", "#00994C", "32", "请大家遵守弹幕礼仪"],
            [42.741, "right", "#00CD00", "1205421", "666", "03-15 15:47", "25px"],
        ],
    }
    controller = DirectParseDanmakuController(load=lambda _url: payload)
    item = PlayItem(
        title="第10话",
        url="",
        original_url="https://v.qq.com/x/cover/demo/ep10.html",
        vod_id="https://v.qq.com/x/cover/demo/ep10.html",
        media_title="剑来 第二季",
    )

    controller.refresh_danmaku_sources(item)
    xml_text = controller.switch_danmaku_source(item, "https://v.qq.com/x/cover/demo/ep10.html")

    assert item.selected_danmaku_provider == "direct_parse"
    assert item.selected_danmaku_url == "https://v.qq.com/x/cover/demo/ep10.html"
    assert "✨有 9 条弹幕列队来袭~做好准备吧！✨" in xml_text
    assert "请大家遵守弹幕礼仪" in xml_text
    assert ">666</d>" in xml_text
    assert 'p="6,5,25,39244' in xml_text
    assert item.danmaku_xml == xml_text


def test_direct_parse_danmaku_controller_uses_cached_xml_before_network(monkeypatch) -> None:
    network_calls: list[str] = []
    monkeypatch.setattr(
        direct_parse_module,
        "load_cached_danmaku_xml",
        lambda name, reg_src: '<?xml version="1.0" encoding="UTF-8"?><i><d p="1,1,25,16777215,0,0,0,0">缓存</d></i>',
    )
    monkeypatch.setattr(direct_parse_module, "save_cached_danmaku_xml", lambda name, reg_src, xml_text: None)
    controller = DirectParseDanmakuController(load=lambda url: network_calls.append(url) or {})
    item = PlayItem(
        title="第10话",
        url="",
        original_url="https://v.qq.com/x/cover/demo/ep10.html",
        vod_id="https://v.qq.com/x/cover/demo/ep10.html",
        media_title="剑来 第二季",
    )

    controller.maybe_resolve(item)

    assert item.danmaku_pending is False
    assert "缓存" in item.danmaku_xml
    assert network_calls == []


def test_load_direct_parse_danmaku_passes_proxy_kwargs() -> None:
    seen: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"danmuku": []}

    def fake_get(url: str, **kwargs) -> FakeResponse:
        seen["url"] = url
        seen["proxy"] = kwargs.get("proxy")
        seen["trust_env"] = kwargs.get("trust_env")
        return FakeResponse()

    payload = direct_parse_module.load_direct_parse_danmaku(
        "https://www.youtube.com/watch?v=test123",
        get=fake_get,
        proxy_decider=ProxyDecider(
            ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])
        ),
    )

    assert payload == {"danmuku": []}
    assert seen["url"] == "https://dmku.hls.one/"
    assert seen["proxy"] == "http://127.0.0.1:7890"
    assert seen["trust_env"] is False
