import httpx
import pytest

from atv_player.metadata.providers.official_douban_client import (
    DoubanBlockedError,
    DoubanRateLimitedError,
    LocalDoubanClient,
)
from atv_player.network_proxy import ProxyConfig, ProxyDecider


@pytest.fixture(autouse=True)
def reset_douban_rate_limit() -> None:
    LocalDoubanClient._last_allowed_at = None


def test_local_douban_client_builds_direct_httpx_client_for_bypass() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, text="[]")
        )
        return httpx.Client(transport=transport)

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

    client = LocalDoubanClient(
        cookie="bid=demo;",
        transport=httpx.MockTransport(handler),
    )

    client.search("深空彼岸")

    assert seen["cookie"] == "bid=demo;"


def test_local_douban_client_skips_second_request_inside_rate_limit_window() -> None:
    now = 100.0
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="[]")

    client = LocalDoubanClient(
        transport=httpx.MockTransport(handler),
        monotonic=lambda: now,
    )

    assert client.search("深空彼岸") == []

    with pytest.raises(DoubanRateLimitedError):
        client.search("深空彼岸")

    assert len(calls) == 1


def test_local_douban_client_allows_detail_for_item_returned_by_recent_search() -> None:
    now = 100.0
    calls: list[str] = []
    detail_html = """
    <html>
      <head><title>名侦探柯南 (豆瓣)</title></head>
      <body>
        <span property="v:itemreviewed">名侦探柯南</span>
        <span class="year">(1996)</span>
        <span property="v:summary">高中生侦探。</span>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/j/subject_suggest":
            return httpx.Response(
                200,
                text='[{"id":"1463371","title":"名侦探柯南","year":"1996"}]',
            )
        return httpx.Response(200, text=detail_html)

    client = LocalDoubanClient(
        transport=httpx.MockTransport(handler),
        monotonic=lambda: now,
    )

    assert client.search("名侦探柯南", year="1996")[0]["id"] == "1463371"
    detail = client.get_detail("1463371")

    assert detail is not None
    assert detail["id"] == "1463371"
    assert len(calls) == 2


def test_local_douban_client_allows_request_after_rate_limit_window() -> None:
    now = 100.0
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="[]")

    client = LocalDoubanClient(
        transport=httpx.MockTransport(handler),
        monotonic=lambda: now,
    )

    client.search("深空彼岸")
    now = 110.0
    client.search("深空彼岸")

    assert len(calls) == 2


def test_local_douban_client_parses_search_results_and_filters_year() -> None:
    payload = """
    [
      {"id":"35746415","title":"深空彼岸","year":"2026","img":"https://img.example/poster.jpg"},
      {"id":"123","title":"深空彼岸","year":"2025","img":"https://img.example/old.jpg"}
    ]
    """
    client = LocalDoubanClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=payload)
        ),
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
        <section>
          <a href="https://v.qq.com/x/cover/mzc00200np0le5t.html">腾讯视频</a>
        </section>
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
        "official_links": [
            {
                "provider": "tencent",
                "label": "腾讯视频",
                "url": "https://v.qq.com/x/cover/mzc00200np0le5t.html",
            }
        ],
    }


def test_local_douban_client_parses_douban_playbtn_vendor_entries() -> None:
    html = """
    <html>
      <head><title>名侦探柯南 (豆瓣)</title></head>
      <body>
        <span property="v:itemreviewed">名侦探柯南</span>
        <span class="year">(1996)</span>
        <span property="v:summary">高中生侦探。</span>
        <div class="gray_ad">
          <h2>在哪儿看这部剧集</h2>
          <ul class="bs">
            <li>
              <a class="playBtn" data-cn="腾讯视频"
                 data-click-track="https://frodo.douban.com/rohirrim/video_tracking/click?source=qq"
                 href="javascript: void 0;">腾讯视频</a>
            </li>
            <li>
              <a class="playBtn" data-cn="哔哩哔哩"
                 data-click-track="https://frodo.douban.com/rohirrim/video_tracking/click?source=bilibili"
                 href="javascript: void 0;">哔哩哔哩</a>
            </li>
            <li>
              <a class="playBtn" data-cn="优酷视频"
                 data-click-track="https://frodo.douban.com/rohirrim/video_tracking/click?source=youku"
                 href="javascript: void 0;">优酷视频</a>
            </li>
            <li>
              <a class="playBtn" data-cn="爱奇艺"
                 data-click-track="https://frodo.douban.com/rohirrim/video_tracking/click?source=iqiyi"
                 href="javascript: void 0;">爱奇艺</a>
            </li>
          </ul>
        </div>
      </body>
    </html>
    """
    client = LocalDoubanClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html)),
    )

    detail = client.get_detail("1463371")

    assert detail is not None
    assert detail["official_links"] == [
        {"provider": "tencent", "label": "腾讯视频", "url": ""},
        {"provider": "bilibili", "label": "哔哩哔哩", "url": ""},
        {"provider": "youku", "label": "优酷视频", "url": ""},
        {"provider": "iqiyi", "label": "爱奇艺", "url": ""},
    ]


def test_local_douban_client_parses_douban_sources_play_links() -> None:
    html = """
    <html>
      <head><title>名侦探柯南 (豆瓣)</title></head>
      <body>
        <span property="v:itemreviewed">名侦探柯南</span>
        <span class="year">(1996)</span>
        <div class="gray_ad">
          <ul class="bs">
            <li><a class="playBtn" data-cn="腾讯视频" data-source="1" href="javascript: void 0;">腾讯视频</a></li>
            <li><a class="playBtn" data-cn="哔哩哔哩" data-source="8" href="javascript: void 0;">哔哩哔哩</a></li>
            <li><a class="playBtn" data-cn="优酷视频" data-source="3" href="javascript: void 0;">优酷视频</a></li>
            <li><a class="playBtn" data-cn="爱奇艺" data-source="9" href="javascript: void 0;">爱奇艺</a></li>
          </ul>
        </div>
        <script>
          var sources = {};
          sources[1] = [{
            play_link: "https://www.douban.com/link2/?url=https%3A%2F%2Fv.qq.com%2Fx%2Fcover%2F53q0eh78q97e4d1%2Fx00174aq5no.html%3Fptag%3Dnewdouban.cartoon&amp;subtype=1&amp;type=online-video",
            ep: "1"
          }];
          sources[8] = [{
            play_link: "https://www.douban.com/link2/?url=https%3A%2F%2Fm.bilibili.com%2Fbangumi%2Fplay%2Fep323085%3Fbsource%3Ddoubanh5&amp;subtype=8&amp;type=online-video",
            ep: "1"
          }];
          sources[3] = [{
            play_link: "https://www.douban.com/link2/?url=https%3A%2F%2Fm.youku.com%2Falipay_video%2Fid_XMzk1NjM1MjAw.html%3Frefer%3Desfhz_operation.xuka.xj_00003036_000000_FNZfau_19010900&amp;subtype=3&amp;type=online-video",
            ep: "1"
          }];
          sources[9] = [{
            play_link: "https://www.douban.com/link2/?url=http%3A%2F%2Fwww.iqiyi.com%2Fv_19rrnfnjyw.html%3Fvfm%3Dm_331_dbdy%26fv%3D4904d94982104144a1548dd9040df241&amp;subtype=9&amp;type=online-video",
            ep: "1"
          }];
        </script>
      </body>
    </html>
    """
    client = LocalDoubanClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html)),
    )

    detail = client.get_detail("1463371")

    assert detail is not None
    assert detail["official_links"] == [
        {
            "provider": "tencent",
            "label": "腾讯视频",
            "url": "https://v.qq.com/x/cover/53q0eh78q97e4d1/x00174aq5no.html?ptag=newdouban.cartoon",
        },
        {
            "provider": "bilibili",
            "label": "哔哩哔哩",
            "url": "https://m.bilibili.com/bangumi/play/ep323085?bsource=doubanh5",
        },
        {
            "provider": "youku",
            "label": "优酷视频",
            "url": "https://m.youku.com/alipay_video/id_XMzk1NjM1MjAw.html?refer=esfhz_operation.xuka.xj_00003036_000000_FNZfau_19010900",
        },
        {
            "provider": "iqiyi",
            "label": "爱奇艺",
            "url": "http://www.iqiyi.com/v_19rrnfnjyw.html?vfm=m_331_dbdy&fv=4904d94982104144a1548dd9040df241",
        },
    ]
