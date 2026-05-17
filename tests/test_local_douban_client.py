import httpx
import pytest

from atv_player.metadata.providers.local_douban_client import DoubanBlockedError, LocalDoubanClient
from atv_player.network_proxy import ProxyConfig, ProxyDecider


def test_local_douban_client_builds_direct_httpx_client_for_bypass() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="[]")))

    client = LocalDoubanClient(
        cookie="bid=demo;",
        proxy_decider=ProxyDecider(
            ProxyConfig(
                mode="socks5",
                proxy_url="socks5://127.0.0.1:1080",
                bypass_rules=["movie.douban.com"],
            )
        ),
        client_factory=fake_client_factory,
    )

    assert captured["trust_env"] is False
    assert "proxy" not in captured
    client._client.close()


def test_local_douban_client_raises_when_html_matches_block_markers() -> None:
    html = '<html><body>有异常请求从你的 IP 发出 <a href="https://sec.douban.com/">sec</a></body></html>'
    client = LocalDoubanClient(
        cookie="bid=demo;",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html)),
    )

    with pytest.raises(DoubanBlockedError):
        client.search("深空彼岸", year="2026")


def test_local_douban_client_sends_cookie_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("Cookie", "")
        return httpx.Response(200, text="[]")

    client = LocalDoubanClient(cookie="bid=demo;", transport=httpx.MockTransport(handler))

    client.search("深空彼岸")

    assert seen["cookie"] == "bid=demo;"


def test_local_douban_client_parses_search_results_and_filters_year() -> None:
    payload = """
    [
      {"id":"35746415","title":"深空彼岸","year":"2026","img":"https://img.example/poster.jpg"},
      {"id":"123","title":"深空彼岸","year":"2025","img":"https://img.example/old.jpg"}
    ]
    """
    client = LocalDoubanClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=payload)),
    )

    results = client.search("深空彼岸", year="2026")

    assert results == [
        {
            "id": "35746415",
            "title": "深空彼岸",
            "year": "2026",
            "cover": "https://img.example/poster.jpg",
        }
    ]


def test_local_douban_client_parses_subject_detail_html() -> None:
    html = """
    <html>
      <head><title>深空彼岸 (豆瓣)</title></head>
      <body>
        <span property="v:itemreviewed">深空彼岸</span>
        <span class="year">(2026)</span>
        <div id="mainpic"><img src="https://img.example/poster.jpg" /></div>
        <strong class="ll rating_num" property="v:average">8.1</strong>
        <span rel="v:directedBy">周琛</span>
        <span class="actor"><span class="attrs"><a>梁达伟</a><a>唐雅菁</a></span></span>
        <span property="v:genre">动画</span>
        <span property="v:genre">科幻</span>
        <div id="info">
          制片国家/地区: 中国大陆<br/>
          语言: 汉语普通话<br/>
        </div>
        <span property="v:summary">
          崇尚科技修仙的新术崛起。
        </span>
      </body>
    </html>
    """
    client = LocalDoubanClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html)),
    )

    detail = client.get_detail("35746415")

    assert detail == {
        "id": "35746415",
        "name": "深空彼岸",
        "year": "2026",
        "cover": "https://img.example/poster.jpg",
        "dbScore": "8.1",
        "directors": "周琛",
        "actors": "梁达伟,唐雅菁",
        "genre": "动画,科幻",
        "country": "中国大陆",
        "language": "汉语普通话",
        "description": "崇尚科技修仙的新术崛起。",
    }
