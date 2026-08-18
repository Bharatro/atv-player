from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote, urljoin, urlparse, urlunparse

from atv_player.proxy.ad_filter import (
    MODE_MARKERS,
    filter_segments,
    parse_media_playlist,
)
from atv_player.proxy.session import PlaylistSegment, ProxySessionRegistry

_URI_ATTR_RE = re.compile(r'URI="([^"]+)"')


@dataclass(slots=True, frozen=True)
class RewrittenPlaylist:
    text: str
    is_master: bool


def rewrite_playlist(
    *,
    token: str,
    playlist_url: str,
    content: str,
    session_registry: ProxySessionRegistry,
    proxy_base_url: str,
    ad_filter_mode: str = MODE_MARKERS,
) -> RewrittenPlaylist:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    session = session_registry.get(token)
    if session is None:
        return RewrittenPlaylist(text="", is_master=False)
    new_segments: list[PlaylistSegment] = []
    if any(line.startswith("#EXT-X-STREAM-INF") for line in lines):
        output: list[str] = []
        for line in lines:
            if line.startswith("#"):
                output.append(line)
                continue
            child_url = _resolve_playlist_uri(playlist_url, line)
            child_token = session_registry.create_session(child_url, session.headers)
            output.append(f"{proxy_base_url}/m3u/{quote(child_token, safe='')}")
        return RewrittenPlaylist(text="\n".join(output) + "\n", is_master=True)

    parsed = parse_media_playlist(
        lines, lambda uri: _resolve_playlist_uri(playlist_url, uri)
    )
    # AES-128(等)加密播放列表: 分片是密文, 不能交给 stripper 做 TS 同步"修复"
    # (会在密文里误判 0x47 同步字节并截断, 破坏 16 字节对齐导致解密失败)。
    session.media_encrypted = parsed.has_key_tags
    result = filter_segments(parsed, ad_filter_mode, playlist_url)

    output = [
        _rewrite_tag_uris(line, token, playlist_url, proxy_base_url)
        for line in parsed.header_lines
    ]
    segment_index = 0
    previous_block: int | None = None
    for segment, keep in zip(parsed.segments, result.kept, strict=True):
        if not keep:
            continue
        # 按分块变化重建 DISCONTINUITY: 被清空的广告块边界自动坍缩, 首尾不输出
        if previous_block is not None and segment.block_index != previous_block:
            output.append("#EXT-X-DISCONTINUITY")
        previous_block = segment.block_index
        output.extend(
            _rewrite_tag_uris(tag, token, playlist_url, proxy_base_url)
            for tag in segment.tags
        )
        if segment.extinf_line is not None:
            output.append(segment.extinf_line)
        new_segments.append(
            PlaylistSegment(
                index=segment_index,
                url=segment.absolute_url,
                duration=segment.duration,
            )
        )
        output.append(f"{proxy_base_url}/seg?v={quote(token)}&i={segment_index}")
        segment_index += 1
    output.extend(
        _rewrite_tag_uris(line, token, playlist_url, proxy_base_url)
        for line in parsed.trailing_lines
    )
    session.segments = new_segments
    return RewrittenPlaylist(text="\n".join(output) + "\n", is_master=False)


def _rewrite_tag_uris(line: str, token: str, playlist_url: str, proxy_base_url: str) -> str:
    def repl(match: re.Match[str]) -> str:
        absolute_url = _resolve_playlist_uri(playlist_url, match.group(1))
        return f'URI="{proxy_base_url}/asset?v={quote(token)}&url={quote(absolute_url, safe="")}"'

    return _URI_ATTR_RE.sub(repl, line)


def _resolve_playlist_uri(playlist_url: str, uri: str) -> str:
    absolute_url = urljoin(playlist_url, uri)
    parent = urlparse(playlist_url)
    parsed_uri = urlparse(uri)
    resolved = urlparse(absolute_url)
    if (
        parent.query
        and not parsed_uri.scheme
        and not parsed_uri.netloc
        and not resolved.query
    ):
        resolved = resolved._replace(query=parent.query)
        return urlunparse(resolved)
    return absolute_url
