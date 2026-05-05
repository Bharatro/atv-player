import errno
from io import BytesIO

from atv_player.player.m3u8_ad_filter import M3U8AdFilter
from atv_player.proxy.server import LocalHlsProxyServer
from atv_player.proxy.session import PlaylistSegment
import httpx


def test_m3u8_ad_filter_returns_proxy_url_for_remote_m3u8() -> None:
    class FakeServer:
        def start(self) -> None:
            return None

        def create_playlist_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            assert headers == {"Referer": "https://site.example"}
            return "http://127.0.0.1:2323/m3u?v=test-token"

        def close(self) -> None:
            return None

    ad_filter = M3U8AdFilter(proxy_server=FakeServer())

    prepared = ad_filter.prepare(
        "https://media.example/path/index.m3u8",
        {"Referer": "https://site.example"},
    )

    assert prepared == "http://127.0.0.1:2323/m3u?v=test-token"


def test_m3u8_ad_filter_leaves_non_m3u8_url_unchanged() -> None:
    ad_filter = M3U8AdFilter()

    assert ad_filter.should_prepare("https://media.example/video.mp4") is False


def test_m3u8_ad_filter_treats_dash_data_uri_as_proxy_candidate() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.calls: list[tuple[str, dict[str, str]]] = []

        def start(self) -> None:
            self.started = True

        def create_dash_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            self.calls.append((url, dict(headers or {})))
            return "http://127.0.0.1:2323/dash/dash-token.mpd"

        def close(self) -> None:
            return None

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server)
    url = "data:application/dash+xml;base64,PE1QRD48L01QRD4="

    prepared = ad_filter.prepare(url, {"Referer": "https://www.bilibili.com/"})

    assert ad_filter.should_prepare(url) is True
    assert prepared == "http://127.0.0.1:2323/dash/dash-token.mpd"
    assert server.started is True
    assert server.calls == [(url, {"Referer": "https://www.bilibili.com/"})]


def test_m3u8_ad_filter_treats_remote_png_media_url_as_proxy_candidate() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.calls: list[tuple[str, dict[str, str]]] = []

        def start(self) -> None:
            self.started = True

        def create_media_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            self.calls.append((url, dict(headers or {})))
            return "http://127.0.0.1:2323/raw?v=test-token"

        def close(self) -> None:
            return None

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server)

    prepared = ad_filter.prepare(
        "https://media.example/path/disguised.png",
        {"Referer": "https://site.example"},
    )

    assert ad_filter.should_prepare("https://media.example/path/disguised.png") is True
    assert prepared == "http://127.0.0.1:2323/raw?v=test-token"
    assert server.started is True
    assert server.calls == [
        (
            "https://media.example/path/disguised.png",
            {"Referer": "https://site.example"},
        )
    ]


def test_m3u8_ad_filter_proxies_extensionless_url_when_probe_looks_like_disguised_ts() -> None:
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.calls: list[tuple[str, dict[str, str]]] = []

        def start(self) -> None:
            self.started = True

        def create_media_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            self.calls.append((url, dict(headers or {})))
            return "http://127.0.0.1:2323/raw?v=extensionless-token"

        def close(self) -> None:
            return None

    requests: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool) -> FakeResponse:
        requests.append((url, headers))
        return FakeResponse(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + b"\x00" * 32
            + b"IEND\xaeB`\x82"
            + (b"\x47" + b"\x00" * 187) * 2
        )

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server, get=fake_get)
    url = "https://media.example/path/disguised"

    prepared = ad_filter.prepare(url, {"Referer": "https://site.example"})

    assert ad_filter.should_prepare(url) is True
    assert prepared == "http://127.0.0.1:2323/raw?v=extensionless-token"
    assert requests == [(url, {"Referer": "https://site.example", "Range": "bytes=0-2047"})]
    assert server.calls == [(url, {"Referer": "https://site.example"})]


def test_m3u8_ad_filter_keeps_extensionless_url_when_probe_is_not_disguised_ts() -> None:
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    requests: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool) -> FakeResponse:
        requests.append((url, headers))
        return FakeResponse(b"{\"ok\":true}")

    ad_filter = M3U8AdFilter(get=fake_get)
    url = "https://media.example/path/plain"

    prepared = ad_filter.prepare(url, {"Referer": "https://site.example"})

    assert ad_filter.should_prepare(url) is True
    assert prepared == url
    assert requests == [(url, {"Referer": "https://site.example", "Range": "bytes=0-2047"})]


def test_m3u8_ad_filter_adds_default_xiaohongshu_headers_for_probe_and_proxy() -> None:
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str]]] = []

        def start(self) -> None:
            return None

        def create_media_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            self.calls.append((url, dict(headers or {})))
            return "http://127.0.0.1:2323/raw?v=xhs-token"

        def close(self) -> None:
            return None

    requests: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool) -> FakeResponse:
        requests.append((url, headers))
        return FakeResponse(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + b"\x00" * 32
            + b"IEND\xaeB`\x82"
            + (b"\x47" + b"\x00" * 187) * 2
        )

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server, get=fake_get)
    url = "https://sns-open-qc.xhscdn.com/professionalpc/test-token"

    prepared = ad_filter.prepare(url)

    assert prepared == "http://127.0.0.1:2323/raw?v=xhs-token"
    assert requests == [
        (
            url,
            {
                "Referer": "https://www.xiaohongshu.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "Range": "bytes=0-2047",
            },
        )
    ]
    assert server.calls == [
        (
            url,
            {
                "Referer": "https://www.xiaohongshu.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            },
        )
    ]


def test_m3u8_ad_filter_still_proxies_xiaohongshu_url_when_probe_fails() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str]]] = []

        def start(self) -> None:
            return None

        def create_media_url(self, url: str, headers: dict[str, str] | None = None) -> str:
            self.calls.append((url, dict(headers or {})))
            return "http://127.0.0.1:2323/raw?v=xhs-fallback-token"

        def close(self) -> None:
            return None

    requests: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        requests.append((url, headers))
        raise RuntimeError("403 Forbidden")

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server, get=fake_get)
    url = "https://sns-open-qc.xhscdn.com/professionalpc/test-token"

    prepared = ad_filter.prepare(url)

    assert prepared == "http://127.0.0.1:2323/raw?v=xhs-fallback-token"
    assert requests == [
        (
            url,
            {
                "Referer": "https://www.xiaohongshu.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "Range": "bytes=0-2047",
            },
        )
    ]
    assert server.calls == [
        (
            url,
            {
                "Referer": "https://www.xiaohongshu.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            },
        )
    ]


def test_local_hls_proxy_server_returns_404_for_missing_token() -> None:
    server = LocalHlsProxyServer()

    status, headers, body = server.handle_request("GET", "/m3u?v=missing")

    assert status == 404
    assert headers == []
    assert body == b"missing proxy session"


def test_local_hls_proxy_server_returns_decoded_dash_manifest_for_data_uri() -> None:
    server = LocalHlsProxyServer()
    mpd_url = server.create_dash_url("data:application/dash+xml;base64,PE1QRD48UGVyaW9kLz48L01QRD4=", {})

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body == b"<MPD><Period/></MPD>"


def test_local_hls_proxy_server_uses_mpd_suffix_for_dash_manifest_url() -> None:
    server = LocalHlsProxyServer()

    mpd_url = server.create_dash_url("data:application/dash+xml;base64,PE1QRD48L01QRD4=", {})

    assert mpd_url.startswith(f"http://{server.host}:{server.port}/dash/")
    assert mpd_url.endswith(".mpd")


def test_local_hls_proxy_server_escapes_bare_ampersands_in_dash_manifest() -> None:
    server = LocalHlsProxyServer()
    raw_xml = "<MPD><BaseURL>https://media.example/video.m4s?x=1&y=2</BaseURL></MPD>"
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body == (
        f"<MPD><BaseURL>http://127.0.0.1:2323/dash/asset/{token}/0.m4s</BaseURL></MPD>".encode("utf-8")
    )
    assert server._registry.get(token).dash_assets == ["https://media.example/video.m4s?x=1&y=2"]


def test_local_hls_proxy_server_does_not_double_escape_existing_entities_in_baseurl() -> None:
    server = LocalHlsProxyServer()
    raw_xml = "<MPD><BaseURL>https://media.example/video.m4s?x=1&amp;y=2</BaseURL></MPD>"
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body == (
        f"<MPD><BaseURL>http://127.0.0.1:2323/dash/asset/{token}/0.m4s</BaseURL></MPD>".encode("utf-8")
    )
    assert server._registry.get(token).dash_assets == ["https://media.example/video.m4s?x=1&y=2"]


def test_local_hls_proxy_server_escapes_entity_like_fragments_inside_baseurl() -> None:
    server = LocalHlsProxyServer()
    raw_xml = "<MPD><BaseURL>https://media.example/video.m4s?foo=1&abc=123&bar=2</BaseURL></MPD>"
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body == (
        f"<MPD><BaseURL>http://127.0.0.1:2323/dash/asset/{token}/0.m4s</BaseURL></MPD>".encode("utf-8")
    )
    assert server._registry.get(token).dash_assets == ["https://media.example/video.m4s?foo=1&abc=123&bar=2"]


def test_local_hls_proxy_server_rewrites_dash_baseurl_to_local_asset_proxy() -> None:
    server = LocalHlsProxyServer()
    raw_url = "https://media.example/video.m4s?foo=1&bar=2"
    raw_xml = f"<MPD><BaseURL>{raw_url}</BaseURL></MPD>"
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body == (
        f"<MPD><BaseURL>http://127.0.0.1:2323/dash/asset/{token}/0.m4s</BaseURL></MPD>".encode("utf-8")
    )
    assert server._registry.get(token).dash_assets == [raw_url]


def test_local_hls_proxy_server_keeps_only_first_video_and_audio_dash_representations() -> None:
    server = LocalHlsProxyServer()
    raw_xml = """
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet>
      <ContentComponent contentType="video"/>
      <Representation id="v1" bandwidth="300">
        <BaseURL>https://media.example/video-1.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="video"/>
      <Representation id="v2" bandwidth="200">
        <BaseURL>https://media.example/video-2.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="audio"/>
      <Representation id="a1" bandwidth="100">
        <BaseURL>https://media.example/audio-1.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="audio"/>
      <Representation id="a2" bandwidth="50">
        <BaseURL>https://media.example/audio-2.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
""".strip()
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    body_text = body.decode("utf-8")
    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert body_text.count("<AdaptationSet") == 2
    assert "video-2.m4s" not in body_text
    assert "audio-2.m4s" not in body_text
    assert f"/dash/asset/{token}/0.m4s" in body_text
    assert f"/dash/asset/{token}/1.m4s" in body_text
    assert server._registry.get(token).dash_assets == [
        "https://media.example/video-1.m4s",
        "https://media.example/audio-1.m4s",
    ]


def test_local_hls_proxy_server_defaults_dash_video_selection_to_highest_quality() -> None:
    server = LocalHlsProxyServer()
    raw_xml = """
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet>
      <ContentComponent contentType="video"/>
      <Representation id="v720" bandwidth="1200000" width="1280" height="720">
        <BaseURL>https://media.example/video-720.m4s</BaseURL>
      </Representation>
      <Representation id="v1080" bandwidth="2800000" width="1920" height="1080">
        <BaseURL>https://media.example/video-1080.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="audio"/>
      <Representation id="a1" bandwidth="128000">
        <BaseURL>https://media.example/audio-1.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
""".strip()
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    session = server._registry.get(token)
    assert session is not None
    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert session.selected_dash_video_id == "v1080"
    assert [representation.id for representation in session.dash_video_representations] == ["v720", "v1080"]
    assert [representation.height for representation in session.dash_video_representations] == [720, 1080]
    assert body.decode("utf-8").count("<Representation") == 2
    assert "video-1080.m4s" not in body.decode("utf-8")
    assert "video-720.m4s" not in body.decode("utf-8")
    assert session.dash_assets == [
        "https://media.example/video-1080.m4s",
        "https://media.example/audio-1.m4s",
    ]


def test_local_hls_proxy_server_rewrites_requested_dash_video_selection() -> None:
    server = LocalHlsProxyServer()
    raw_xml = """
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet>
      <ContentComponent contentType="video"/>
      <Representation id="v720" bandwidth="1200000" width="1280" height="720">
        <BaseURL>https://media.example/video-720.m4s</BaseURL>
      </Representation>
      <Representation id="v1080" bandwidth="2800000" width="1920" height="1080">
        <BaseURL>https://media.example/video-1080.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="audio"/>
      <Representation id="a1" bandwidth="128000">
        <BaseURL>https://media.example/audio-1.m4s</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
""".strip()
    payload = "data:application/dash+xml;base64," + __import__("base64").b64encode(raw_xml.encode("utf-8")).decode("ascii")
    mpd_url = server.create_dash_url(payload, {}, selected_video_id="v720")
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")

    status, headers, body = server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    session = server._registry.get(token)
    assert session is not None
    assert status == 200
    assert headers == [("Content-Type", "application/dash+xml")]
    assert session.selected_dash_video_id == "v720"
    assert body.decode("utf-8").count("<Representation") == 2
    assert session.dash_assets == [
        "https://media.example/video-720.m4s",
        "https://media.example/audio-1.m4s",
    ]


def test_local_hls_proxy_server_proxies_dash_asset_with_range_headers() -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self) -> None:
            self.content = b"abc"
            self.headers = {
                "Content-Type": "video/iso.segment",
                "Content-Range": "bytes 0-2/3",
                "Accept-Ranges": "bytes",
            }
            self.status_code = 206

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        requests.append((url, headers))
        return FakeResponse()

    server = LocalHlsProxyServer(get=fake_get)
    payload = "data:application/dash+xml;base64,PE1QRD48QmFzZVVSTD5odHRwczovL21lZGlhLmV4YW1wbGUvdmlkZW8ubTRzP2Zv bz0xJmJhcj0yPC9CYXNlVVJMPjwvTVBEPg==".replace(" ", "")
    mpd_url = server.create_dash_url(
        payload,
        {
            "Cookie": "SESSDATA=demo;bili_jct=demo2",
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")
    server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    status, headers, body = server.handle_request(
        "GET",
        f"/dash/asset/{token}/0.m4s",
        {"Range": "bytes=0-2"},
    )

    assert status == 206
    assert headers == [
        ("Content-Type", "video/iso.segment"),
        ("Content-Range", "bytes 0-2/3"),
        ("Accept-Ranges", "bytes"),
    ]
    assert body == b"abc"
    assert requests == [
        (
            "https://media.example/video.m4s?foo=1&bar=2",
            {
                "Cookie": "SESSDATA=demo;bili_jct=demo2",
                "Referer": "https://www.bilibili.com/",
                "User-Agent": "Mozilla/5.0",
                "Range": "bytes=0-2",
            },
        )
    ]


def test_local_hls_proxy_server_synthesizes_partial_content_when_origin_ignores_range() -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self) -> None:
            self.content = b"0123456789"
            self.headers = {
                "Content-Type": "video/iso.segment",
            }
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        requests.append((url, headers))
        return FakeResponse()

    server = LocalHlsProxyServer(get=fake_get)
    payload = "data:application/dash+xml;base64,PE1QRD48QmFzZVVSTD5odHRwczovL21lZGlhLmV4YW1wbGUvdmlkZW8ubTRzPC9CYXNlVVJMPjwvTVBEPg=="
    mpd_url = server.create_dash_url(payload, {"Referer": "https://www.bilibili.com/"})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")
    server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))

    status, headers, body = server.handle_request(
        "GET",
        f"/dash/asset/{token}/0.m4s",
        {"Range": "bytes=2-5"},
    )

    assert status == 206
    assert headers == [
        ("Content-Type", "video/iso.segment"),
        ("Content-Range", "bytes 2-5/10"),
        ("Accept-Ranges", "bytes"),
    ]
    assert body == b"2345"
    assert requests == [
        (
            "https://media.example/video.m4s",
            {
                "Referer": "https://www.bilibili.com/",
                "Range": "bytes=2-5",
            },
        )
    ]


def test_local_hls_proxy_server_streams_dash_asset_response_without_buffering_full_body() -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []

    class FakeStreamResponse:
        status_code = 200
        headers = {
            "Content-Type": "video/iso.segment",
            "Content-Length": "6",
        }

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self) -> bytes:
            yield b"abc"
            yield b"def"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_stream(method: str, url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        calls.append((method, url, headers))
        return FakeStreamResponse()

    class FakeHandler:
        def __init__(self) -> None:
            self.status_code: int | None = None
            self.headers: list[tuple[str, str]] = []
            self.wfile = BytesIO()
            self.ended = False

        def send_response(self, status_code: int) -> None:
            self.status_code = status_code

        def send_header(self, key: str, value: str) -> None:
            self.headers.append((key, value))

        def end_headers(self) -> None:
            self.ended = True

    server = LocalHlsProxyServer(stream=fake_stream)
    payload = "data:application/dash+xml;base64,PE1QRD48QmFzZVVSTD5odHRwczovL21lZGlhLmV4YW1wbGUvdmlkZW8ubTRzPC9CYXNlVVJMPjwvTVBEPg=="
    mpd_url = server.create_dash_url(payload, {"Referer": "https://www.bilibili.com/"})
    token = mpd_url.rsplit("/", 1)[-1].removesuffix(".mpd")
    server.handle_request("GET", mpd_url.removeprefix(f"http://{server.host}:{server.port}"))
    handler = FakeHandler()

    handled = server._stream_dash_asset_response(
        f"/dash/asset/{token}/0.m4s",
        {"Range": "bytes=0-5"},
        handler,
    )

    assert handled is True
    assert handler.status_code == 200
    assert handler.headers == [
        ("Content-Type", "video/iso.segment"),
        ("Content-Length", "6"),
    ]
    assert handler.ended is True
    assert handler.wfile.getvalue() == b"abcdef"
    assert calls == [
        (
            "GET",
            "https://media.example/video.m4s",
            {
                "Referer": "https://www.bilibili.com/",
                "Range": "bytes=0-5",
            },
        )
    ]


def test_local_hls_proxy_server_returns_repaired_bytes_for_direct_media_url() -> None:
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        return FakeResponse(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + b"\x00" * 32
            + b"IEND\xaeB`\x82"
            + b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + b"\x00" * 32
            + b"IEND\xaeB`\x82"
            + (b"\x47" + b"\x00" * 187) * 2
        )

    server = LocalHlsProxyServer(get=fake_get)
    media_url = server.create_media_url("https://media.example/path/disguised.png", {})
    token = media_url.rsplit("=", 1)[-1]

    status, headers, body = server.handle_request("GET", f"/raw?v={token}")

    assert status == 200
    assert headers == [("Content-Type", "video/MP2T")]
    assert body.startswith(b"\x47")


def test_local_hls_proxy_server_uses_default_xiaohongshu_headers_for_direct_media_url() -> None:
    seen_headers: list[dict[str, str]] = []

    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        seen_headers.append(headers)
        return FakeResponse((b"\x47" + b"\x00" * 187) * 2)

    server = LocalHlsProxyServer(get=fake_get)
    media_url = server.create_media_url("https://sns-open-qc.xhscdn.com/professionalpc/test-token", {})
    token = media_url.rsplit("=", 1)[-1]

    status, headers, body = server.handle_request("GET", f"/raw?v={token}")

    assert status == 200
    assert headers == [("Content-Type", "video/MP2T")]
    assert body.startswith(b"\x47")
    assert seen_headers == [
        {
            "Referer": "https://www.xiaohongshu.com/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        }
    ]


def test_local_hls_proxy_server_returns_502_when_playlist_fetch_fails() -> None:
    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        raise RuntimeError("origin down")

    server = LocalHlsProxyServer(get=fake_get)
    playlist_url = server.create_playlist_url("https://media.example/path/index.m3u8", {})
    token = playlist_url.rsplit("=", 1)[-1]

    status, headers, body = server.handle_request("GET", f"/m3u?v={token}")

    assert status == 502
    assert headers == []
    assert body == b"origin down"


def test_local_hls_proxy_server_deletes_session_when_playlist_returns_403() -> None:
    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        request = httpx.Request("GET", url)
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    server = LocalHlsProxyServer(get=fake_get)
    playlist_url = server.create_playlist_url("https://media.example/path/index.m3u8", {})
    token = playlist_url.rsplit("=", 1)[-1]

    status, headers, body = server.handle_request("GET", f"/m3u?v={token}")

    assert status == 502
    assert headers == []
    assert body == b"forbidden"
    assert server._registry.contains(token) is False


def test_local_hls_proxy_server_reuses_cached_playlist_when_origin_m3u8_becomes_403() -> None:
    requests: list[str] = []

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            return None

    playlist_text = """#EXTM3U
#EXTINF:5.0,
segment-0001.ts
"""
    origin_url = "https://media.example/path/index.m3u8"

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        requests.append(url)
        if len(requests) == 1:
            return FakeResponse(playlist_text)
        request = httpx.Request("GET", url)
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    server = LocalHlsProxyServer(get=fake_get)
    playlist_url = server.create_playlist_url(origin_url, {})
    token = playlist_url.rsplit("=", 1)[-1]

    first_status, first_headers, first_body = server.handle_request("GET", f"/m3u?v={token}")
    second_status, second_headers, second_body = server.handle_request("GET", f"/m3u?v={token}")

    expected_body = (
        "#EXTM3U\n#EXTINF:5.0,\nhttp://127.0.0.1:2323/seg?v="
        f"{token}&i=0\n"
    ).encode("utf-8")

    assert first_status == 200
    assert first_headers == [("Content-Type", "application/vnd.apple.mpegurl")]
    assert first_body == expected_body
    assert second_status == 200
    assert second_headers == [("Content-Type", "application/vnd.apple.mpegurl")]
    assert second_body == expected_body
    assert requests == [origin_url, origin_url]
    assert server._registry.contains(token) is True


def test_local_hls_proxy_server_returns_segment_for_v_query_param() -> None:
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool):
        return FakeResponse((b"\x47" + b"\x00" * 187) * 2)

    server = LocalHlsProxyServer(get=fake_get)
    playlist_url = server.create_playlist_url("https://media.example/path/index.m3u8", {})
    token = playlist_url.rsplit("=", 1)[-1]
    server._registry.get(token).segments = [
        PlaylistSegment(index=0, url="https://media.example/path/segment0.ts", duration=5.0)
    ]

    status, headers, body = server.handle_request("GET", f"/seg?v={token}&i=0")

    assert status == 200
    assert headers == [("Content-Type", "video/MP2T")]
    assert body.startswith(b"\x47")


def test_local_hls_proxy_server_falls_back_to_ephemeral_port_when_default_port_is_busy(monkeypatch) -> None:
    bind_attempts: list[tuple[str, int]] = []

    class FakeThreadingHTTPServer:
        def __init__(self, server_address: tuple[str, int], handler) -> None:
            del handler
            bind_attempts.append(server_address)
            if server_address[1] == 2323:
                raise OSError(errno.EADDRINUSE, "Address already in use")
            self.server_address = (server_address[0], 45123)

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    monkeypatch.setattr("atv_player.proxy.server.ThreadingHTTPServer", FakeThreadingHTTPServer)

    server = LocalHlsProxyServer()

    server.start()
    prepared = server.create_playlist_url("https://media.example/path/index.m3u8", {})
    server.close()

    assert bind_attempts == [("127.0.0.1", 2323), ("127.0.0.1", 0)]
    assert prepared.startswith("http://127.0.0.1:45123/m3u?v=")
