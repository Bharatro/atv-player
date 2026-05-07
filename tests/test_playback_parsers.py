import base64
import json

import httpx
import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from atv_player.playback_parsers import BuiltInPlaybackParserService


def _encrypt_xm_payload(text: str, key: str, iv: str) -> str:
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    return base64.b64encode(cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))).decode("utf-8")


def test_parser_service_tries_saved_parser_first_and_falls_back() -> None:
    calls: list[str] = []
    post_calls: list[str] = []

    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        calls.append(url)
        if "sspa8.top:8100/api/?key=1060089351&" in url:
            return httpx.Response(200, json={"parse": 1, "jx": 1, "url": "https://page.example/watch"})
        if "bd.jx.cn" in url:
            return httpx.Response(200, json={"parse": 1, "jx": 1, "url": "https://page.example/watch"})
        if "kalbim.xatut.top/kalbim2025/781718/play/video_player.php" in url:
            return httpx.Response(200, json={"parse": 1, "jx": 1, "url": "https://page.example/watch"})
        return httpx.Response(200, json={"parse": 0, "jx": 0, "url": "https://media.example/real.m3u8"})

    def fake_post(url: str, data: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        post_calls.append(url)
        return httpx.Response(200, json={})

    service = BuiltInPlaybackParserService(get=fake_get, post=fake_post)

    result = service.resolve("qq", "https://site.example/play?id=1", preferred_key="jx1")

    assert result.parser_key == "jx2"
    assert result.url == "https://media.example/real.m3u8"
    assert post_calls == ["https://api.hls.one:4433/Api"]
    assert calls == [
        "http://sspa8.top:8100/api/?key=1060089351&",
        "https://kalbim.xatut.top/kalbim2025/781718/play/video_player.php",
        "http://sspa8.top:8100/api/?cat_ext=eyJmbGFnIjpbInFxIiwi6IW+6K6vIiwicWl5aSIsIueIseWlh+iJuiIsIuWlh+iJuiIsInlvdWt1Iiwi5LyY6YW3Iiwic29odSIsIuaQnOeLkCIsImxldHYiLCLkuZDop4YiLCJtZ3R2Iiwi6IqS5p6cIiwidG5tYiIsInNldmVuIiwiYmlsaWJpbGkiLCIxOTA1Il0sImhlYWRlciI6eyJVc2VyLUFnZW50Ijoib2todHRwLzQuOS4xIn19&key=星睿4k&",
    ]


def test_parser_service_uses_response_headers_payload() -> None:
    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        return httpx.Response(
            200,
            json={
                "parse": 0,
                "jx": 0,
                "url": "https://media.example/real.m3u8",
                "header": {"Referer": "https://site.example"},
            },
        )

    service = BuiltInPlaybackParserService(get=fake_get)

    result = service.resolve("qq", "https://site.example/play?id=2", preferred_key="fish")

    assert result.parser_key == "fish"
    assert result.headers == {"Referer": "https://site.example"}


def test_parser_service_uses_response_headers_alias_payload() -> None:
    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        return httpx.Response(
            200,
            json={
                "parse": 0,
                "jx": 0,
                "url": "https://media.example/real.m3u8",
                "headers": '{"User-Agent":"UA","Referer":"https://site.example"}',
            },
        )

    service = BuiltInPlaybackParserService(get=fake_get)

    result = service.resolve("qq", "https://site.example/play?id=2", preferred_key="fish")

    assert result.headers == {
        "User-Agent": "UA",
        "Referer": "https://site.example",
    }


def test_parser_service_raises_when_all_parsers_fail() -> None:
    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        return httpx.Response(200, json={"parse": 1, "jx": 1, "url": "https://page.example/watch"})

    service = BuiltInPlaybackParserService(get=fake_get)

    with pytest.raises(ValueError, match="解析失败"):
        service.resolve("qq", "https://site.example/play?id=3")


def test_parser_service_resolves_xmflv_wrapper_url() -> None:
    get_calls: list[tuple[str, dict[str, str]]] = []
    post_calls: list[tuple[str, dict[str, str], dict[str, str]]] = []
    decrypted_payload = (
        'tg:@xmflv'
        + json.dumps(
            {
                "url": "https://media.example/xm-real.m3u8",
                "header": {"Referer": "https://jx.xmflv.com/"},
            }
        )
    )

    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        get_calls.append((url, params))
        return httpx.Response(200, json={"parse": 1, "jx": 1, "url": "https://page.example/watch"})

    def fake_post(url: str, data: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        post_calls.append((url, data, headers))
        return httpx.Response(
            200,
            json={
                "code": 200,
                "key": "1234567890abcdef",
                "iv": "fedcba0987654321",
                "data": _encrypt_xm_payload(decrypted_payload, "1234567890abcdef", "fedcba0987654321"),
            },
        )

    service = BuiltInPlaybackParserService(get=fake_get, post=fake_post)

    result = service.resolve(
        "qq",
        "https://jx.xmflv.com/?url=https://v.qq.com/x/cover/demo/vid123.html",
    )

    assert result.parser_key == "xm"
    assert result.url == "https://media.example/xm-real.m3u8"
    assert result.headers == {"Referer": "https://jx.xmflv.com/"}
    assert get_calls == []
    assert [call[0] for call in post_calls] == ["https://api.hls.one:4433/Api"]
    assert post_calls[0][1]["url"] == "https://v.qq.com/x/cover/demo/vid123.html"
    assert len(post_calls[0][1]["key"]) == 32
    assert post_calls[0][1]["sign"]


def test_parser_service_uses_defined_order_by_default_including_xm() -> None:
    get_calls: list[str] = []
    post_calls: list[str] = []
    decrypted_payload = (
        'tg:@xmflv'
        + json.dumps(
            {
                "url": "https://media.example/xm-default.m3u8",
                "header": {"Referer": "https://jx.xmflv.com/"},
            }
        )
    )

    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        get_calls.append(url)
        return httpx.Response(200, json={"parse": 0, "jx": 0, "url": "https://media.example/fallback.m3u8"})

    def fake_post(url: str, data: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        post_calls.append(url)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "key": "1234567890abcdef",
                "iv": "fedcba0987654321",
                "data": _encrypt_xm_payload(decrypted_payload, "1234567890abcdef", "fedcba0987654321"),
            },
        )

    service = BuiltInPlaybackParserService(get=fake_get, post=fake_post)

    result = service.resolve("qq", "https://v.qq.com/x/cover/demo/vid123.html")

    assert result.parser_key == "xm"
    assert result.url == "https://media.example/xm-default.m3u8"
    assert post_calls == ["https://api.hls.one:4433/Api"]
    assert get_calls == []


def test_parser_service_normalizes_duplicate_port_in_xm_media_url() -> None:
    decrypted_payload = (
        'tg:@xmflv'
        + json.dumps(
            {
                "url": "https://api.hls.one:4433:4433/Cache/qiyi/demo.m3u8?vkey=demo",
            }
        )
    )

    def fake_post(url: str, data: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        return httpx.Response(
            200,
            json={
                "code": 200,
                "key": "1234567890abcdef",
                "iv": "fedcba0987654321",
                "data": _encrypt_xm_payload(decrypted_payload, "1234567890abcdef", "fedcba0987654321"),
            },
        )

    service = BuiltInPlaybackParserService(post=fake_post)

    result = service.resolve("qiyi", "http://www.iqiyi.com/v_mo3lbdn60s.html", preferred_key="xm")

    assert result.url == "https://api.hls.one:4433/Cache/qiyi/demo.m3u8?vkey=demo"
