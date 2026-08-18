"""智能广告过滤(ad_filter)策略、门控与集成测试。"""

from __future__ import annotations

from urllib.parse import urljoin

from atv_player.proxy.ad_filter import filter_segments, parse_media_playlist
from atv_player.proxy.m3u8 import rewrite_playlist
from atv_player.proxy.server import LocalHlsProxyServer
from atv_player.proxy.session import ProxySessionRegistry
from atv_player.storage import _normalize_m3u8_ad_filter_mode

PLAYLIST_URL = "https://cdn.example/v/index.m3u8"


def _alpha4(index: int) -> str:
    chars = []
    for _ in range(4):
        chars.append(chr(ord("a") + index % 26))
        index //= 26
    return "".join(reversed(chars))


def _media_content(uris: list[str], *, endlist: bool = True) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:6"]
    for uri in uris:
        if uri == "|":
            lines.append("#EXT-X-DISCONTINUITY")
            continue
        lines.append("#EXTINF:6.0,")
        lines.append(uri)
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def _numbered(count: int, start: int = 1) -> list[str]:
    return [f"hls-{i:04d}.ts" for i in range(start, start + count)]


def _plain_names(count: int, *, prefix: str = "blk") -> list[str]:
    # 无数字且定长的命名, 用于隔离测试分段统计策略
    return [f"{prefix}-{_alpha4(i)}bcdef.ts" for i in range(count)]


def _filter(content: str, mode: str = "smart"):
    parsed = parse_media_playlist(
        [line.strip() for line in content.splitlines() if line.strip()],
        lambda uri: urljoin(PLAYLIST_URL, uri),
    )
    result = filter_segments(parsed, mode, PLAYLIST_URL)
    kept_uris = [
        segment.uri_line
        for segment, keep in zip(parsed.segments, result.kept, strict=True)
        if keep
    ]
    return parsed, result, kept_uris


def test_digit_filter_drops_unnumbered_ad_run_with_strict_resume() -> None:
    uris = (
        _numbered(15)
        + ["staticad-one.ts", "staticad-two.ts", "staticad-three.ts"]
        + _numbered(15, start=16)
    )

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "digit"
    assert result.removed_count == 3
    assert "staticad-one.ts" not in kept_uris
    assert len(kept_uris) == 30


def test_digit_filter_drops_broken_number_ad_run() -> None:
    uris = (
        _numbered(15)
        + ["promo-9001.ts", "promo-9002.ts"]
        + _numbered(15, start=16)
    )

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "digit"
    assert result.removed_count == 2
    assert "promo-9001.ts" not in kept_uris


def test_digit_filter_keeps_playlist_with_numbering_restart() -> None:
    # 两段各自从 1 编号的拼接片源: 序号中断后不恢复, 必须整体放弃过滤
    uris = _numbered(20) + _numbered(20, start=1)

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert result.removed_count == 0
    assert len(kept_uris) == 40


def test_digit_filter_skips_small_playlist() -> None:
    _parsed, result, kept_uris = _filter(_media_content(_numbered(8)))

    assert result.strategy == "none"
    assert len(kept_uris) == 8


def test_length_filter_drops_deviant_name_runs() -> None:
    names = [f"hls-{_alpha4(i)}bcdef.ts" for i in range(40)]
    uris = names[:20] + ["ad.ts", "ad.ts"] + names[20:] + ["ad.ts"]

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "length"
    assert result.removed_count == 3
    assert "ad.ts" not in kept_uris
    assert len(kept_uris) == 40


def test_length_filter_skips_mixed_naming() -> None:
    uris = [f"hls-{_alpha4(i)}bcdef.ts" for i in range(30)] + [
        f"zz-{_alpha4(i)}xy.ts" for i in range(30, 50)
    ]

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert len(kept_uris) == 50


def test_stats_filter_drops_short_discontinuity_blocks() -> None:
    names = _plain_names(92)
    uris = (
        names[0:12] + ["|"]
        + names[12:22] + ["|"]
        + names[22:34] + ["|"]
        + names[34:44] + ["|"]
        + names[44:56] + ["|"]
        + names[56:68] + ["|"]
        + names[68:80] + ["|"]
        + names[80:92]
    )

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "stats"
    assert result.removed_count == 20
    assert names[12] not in kept_uris and names[21] not in kept_uris
    assert names[34] not in kept_uris and names[43] not in kept_uris
    assert names[0] in kept_uris and names[91] in kept_uris


def test_stats_filter_keeps_uniform_blocks() -> None:
    names = _plain_names(48)
    uris = (
        names[0:12] + ["|"] + names[12:24] + ["|"]
        + names[24:36] + ["|"] + names[36:48]
    )

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert len(kept_uris) == 48


def test_stats_filter_skips_when_too_few_blocks() -> None:
    names = _plain_names(24)
    uris = names[:12] + ["|"] + names[12:]

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert len(kept_uris) == 24


def test_stats_filter_never_drops_first_block() -> None:
    names = _plain_names(38)
    uris = (
        names[0:2] + ["|"] + names[2:14] + ["|"]
        + names[14:26] + ["|"] + names[26:38]
    )

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert result.removed_count == 0
    assert names[0] in kept_uris and names[1] in kept_uris


def test_stats_filter_aborts_when_drop_ratio_exceeds_limit() -> None:
    # 3 个内容块(10) + 7 个广告块(2), 删除占比 14/44 > 30%, 整体放弃
    names = _plain_names(44)
    sizes = [10, 2, 10, 2, 2, 10, 2, 2, 2, 2]
    uris: list[str] = []
    offset = 0
    for index, size in enumerate(sizes):
        if index:
            uris.append("|")
        uris.extend(names[offset : offset + size])
        offset += size

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert result.removed_count == 0
    assert len(kept_uris) == 44


def test_stats_filter_skips_key_rotation() -> None:
    def block(names: list[str], key_uri: str | None) -> list[str]:
        lines: list[str] = []
        if key_uri:
            lines.append(f'#EXT-X-KEY:METHOD=AES-128,URI="{key_uri}"')
        lines.extend(f"#EXTINF:6.0,\n{name}" for name in names)
        return lines

    content_lines = [
        "#EXTM3U",
        *block(_plain_names(12), "key-zero.key"),
        "#EXT-X-DISCONTINUITY",
        *block(_plain_names(2), "key-one.key"),
        "#EXT-X-DISCONTINUITY",
        *block(_plain_names(12), "key-two.key"),
        "#EXT-X-DISCONTINUITY",
        *block(_plain_names(12), None),
        "#EXT-X-DISCONTINUITY",
        *block(_plain_names(12), None),
        "#EXT-X-ENDLIST",
    ]

    _parsed, result, kept_uris = _filter("\n".join(content_lines) + "\n")

    assert result.strategy == "none"
    assert len(kept_uris) == 50


def test_live_playlist_only_uses_markers() -> None:
    uris = (
        _numbered(15)
        + ["staticad-one.ts"]
        + _numbered(15, start=16)
        + ["/adjump/tail.ts"]
    )

    _parsed, result, kept_uris = _filter(_media_content(uris, endlist=False))

    assert result.strategy == "markers"
    assert result.removed_count == 1
    assert "/adjump/tail.ts" not in kept_uris
    assert "staticad-one.ts" in kept_uris


def test_mode_off_keeps_everything() -> None:
    uris = (
        _numbered(15)
        + ["staticad-one.ts", "/adjump/tail.ts"]
        + _numbered(15, start=16)
    )

    _parsed, result, kept_uris = _filter(_media_content(uris), mode="off")

    assert result.strategy == "none"
    assert result.removed_count == 0
    assert "/adjump/tail.ts" in kept_uris
    assert len(kept_uris) == 32


def test_never_empties_playlist_when_markers_hit_all_segments() -> None:
    uris = [f"/adjump/seg-{i:02d}.ts" for i in range(20)]

    _parsed, result, kept_uris = _filter(_media_content(uris))

    assert result.strategy == "none"
    assert len(kept_uris) == 20


def test_parse_media_playlist_splits_header_segments_and_trailing() -> None:
    content = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:6",
            '#EXT-X-KEY:METHOD=AES-128,URI="enc.key"',
            '#EXT-X-MAP:URI="init.mp4"',
            "#EXTINF:5.0,",
            "seg-a.ts",
            "#EXTINF:5.5,title",
            "seg-b.ts",
            "#EXT-X-DISCONTINUITY",
            "#EXT-X-BYTERANGE:1000@0",
            "#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:00Z",
            "#EXTINF:5.0,",
            "seg-c.ts",
            "#EXT-X-ENDLIST",
        ]
    ) + "\n"

    parsed = parse_media_playlist(
        [line.strip() for line in content.splitlines() if line.strip()],
        lambda uri: urljoin(PLAYLIST_URL, uri),
    )

    assert parsed.header_lines == [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:6",
    ]
    assert parsed.is_vod is True
    assert parsed.has_key_tags is True
    assert parsed.trailing_lines == ["#EXT-X-ENDLIST"]
    assert [segment.uri_line for segment in parsed.segments] == [
        "seg-a.ts",
        "seg-b.ts",
        "seg-c.ts",
    ]
    first, second, third = parsed.segments
    assert first.tags == [
        '#EXT-X-KEY:METHOD=AES-128,URI="enc.key"',
        '#EXT-X-MAP:URI="init.mp4"',
    ]
    assert first.extinf_line == "#EXTINF:5.0,"
    assert first.duration == 5.0
    assert first.block_index == 0
    assert first.absolute_url == "https://cdn.example/v/seg-a.ts"
    assert second.duration == 5.5
    assert second.block_index == 0
    assert third.block_index == 1
    assert third.tags == [
        "#EXT-X-BYTERANGE:1000@0",
        "#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:00Z",
    ]


def _digit_ad_playlist() -> str:
    uris = (
        _numbered(15)
        + ["|"]
        + ["adbanner-9001.ts", "adbanner-9002.ts", "adbanner-9003.ts"]
        + ["|"]
        + _numbered(15, start=16)
    )
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:6"]
    for uri in uris:
        if uri == "|":
            lines.append("#EXT-X-DISCONTINUITY")
            continue
        duration = "1.0" if uri.startswith("adbanner") else "6.0"
        lines.append(f"#EXTINF:{duration},")
        lines.append(uri)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def test_rewrite_playlist_smart_mode_drops_ads_and_collapses_discontinuity() -> None:
    registry = ProxySessionRegistry()
    token = registry.create_session(PLAYLIST_URL, {})

    rewritten = rewrite_playlist(
        token=token,
        playlist_url=PLAYLIST_URL,
        content=_digit_ad_playlist(),
        session_registry=registry,
        proxy_base_url="http://127.0.0.1:2323",
        ad_filter_mode="smart",
    )

    assert "adbanner-9001.ts" not in rewritten.text
    assert rewritten.text.count("#EXT-X-DISCONTINUITY") == 1
    assert rewritten.text.count("#EXTINF:") == 30
    assert "#EXTINF:1.0," not in rewritten.text
    session = registry.get(token)
    assert session is not None
    assert len(session.segments) == 30
    assert [segment.index for segment in session.segments] == list(range(30))
    assert session.segments[0].url == "https://cdn.example/v/hls-0001.ts"
    assert session.segments[15].url == "https://cdn.example/v/hls-0016.ts"
    assert session.media_encrypted is False


def test_rewrite_playlist_default_mode_keeps_smart_only_ads() -> None:
    registry = ProxySessionRegistry()
    token = registry.create_session(PLAYLIST_URL, {})

    rewrite_playlist(
        token=token,
        playlist_url=PLAYLIST_URL,
        content=_digit_ad_playlist(),
        session_registry=registry,
        proxy_base_url="http://127.0.0.1:2323",
    )

    session = registry.get(token)
    assert session is not None
    assert len(session.segments) == 33


def test_rewrite_playlist_marks_encrypted_session_and_rewrites_key_uri() -> None:
    registry = ProxySessionRegistry()
    token = registry.create_session(PLAYLIST_URL, {})
    content = (
        "#EXTM3U\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="enc.key"\n'
        "#EXTINF:5.0,\n"
        "seg-a.ts\n"
        "#EXT-X-ENDLIST\n"
    )

    rewritten = rewrite_playlist(
        token=token,
        playlist_url=PLAYLIST_URL,
        content=content,
        session_registry=registry,
        proxy_base_url="http://127.0.0.1:2323",
        ad_filter_mode="smart",
    )

    assert 'URI="http://127.0.0.1:2323/asset?v=' in rewritten.text
    session = registry.get(token)
    assert session is not None
    assert session.media_encrypted is True


def test_local_hls_proxy_server_propagates_ad_filter_mode() -> None:
    class FakeResponse:
        text = _digit_ad_playlist()

        def raise_for_status(self) -> None:
            return None

    def fake_get(
        url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool
    ):
        return FakeResponse()

    server = LocalHlsProxyServer(get=fake_get, ad_filter_mode="smart")
    playlist_url = server.create_playlist_url(PLAYLIST_URL, {})
    path = playlist_url.removeprefix(f"http://{server.host}:{server.port}")

    _status, _headers, smart_body = server.handle_request("GET", path)
    assert smart_body.count(b"/seg?v=") == 30

    server.set_ad_filter_mode("markers")
    _status, _headers, markers_body = server.handle_request("GET", path)
    assert markers_body.count(b"/seg?v=") == 33


def test_normalize_m3u8_ad_filter_mode() -> None:
    assert _normalize_m3u8_ad_filter_mode("markers") == "markers"
    assert _normalize_m3u8_ad_filter_mode("OFF") == "off"
    assert _normalize_m3u8_ad_filter_mode(" Smart ") == "smart"
    assert _normalize_m3u8_ad_filter_mode("bogus") == "smart"
    assert _normalize_m3u8_ad_filter_mode(None) == "smart"
    assert _normalize_m3u8_ad_filter_mode("") == "smart"
