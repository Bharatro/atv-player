from __future__ import annotations

import base64
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import errno
import logging
import re
import threading
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx

from atv_player.proxy.m3u8 import rewrite_playlist
from atv_player.proxy.segment import SegmentProxy
from atv_player.proxy.session import ProxySession, ProxySessionRegistry
from atv_player.request_headers import normalize_media_request_headers

logger = logging.getLogger(__name__)


def _is_dash_data_uri(url: str) -> bool:
    return url.startswith("data:application/dash+xml;base64,")


def _decode_dash_manifest(url: str) -> bytes:
    if not _is_dash_data_uri(url):
        raise ValueError("unsupported dash manifest url")
    _prefix, _separator, payload = url.partition(",")
    cleaned = "".join(payload.split())
    return base64.b64decode(cleaned)


_BASE_URL_RE = re.compile(r"(<BaseURL>)(.*?)(</BaseURL>)", re.DOTALL)
_XML_QUOTE_ESCAPES = {'"': "&quot;", "'": "&apos;"}


def _sanitize_dash_manifest(payload: bytes) -> bytes:
    text = payload.decode("utf-8")

    def replace_base_url(match: re.Match[str]) -> str:
        raw_url = match.group(2)
        normalized_url = escape(
            unescape(raw_url),
            _XML_QUOTE_ESCAPES,
        )
        return f"{match.group(1)}{normalized_url}{match.group(3)}"

    return _BASE_URL_RE.sub(replace_base_url, text).encode("utf-8")


def _rewrite_dash_manifest(payload: bytes, session: ProxySession, proxy_base_url: str) -> bytes:
    root = ET.fromstring(payload)
    session.dash_assets = []
    namespace_match = re.match(r"\{([^}]+)\}", root.tag)
    namespace = namespace_match.group(1) if namespace_match else ""
    prefix = f"{{{namespace}}}" if namespace else ""

    def child_elements(parent: ET.Element, local_name: str) -> list[ET.Element]:
        return [child for child in parent if child.tag == f"{prefix}{local_name}"]

    def adaptation_content_type(adaptation_set: ET.Element) -> str:
        content_type = str(adaptation_set.attrib.get("contentType") or "").strip().lower()
        if content_type:
            return content_type
        for component in child_elements(adaptation_set, "ContentComponent"):
            content_type = str(component.attrib.get("contentType") or "").strip().lower()
            if content_type:
                return content_type
        representation = next(iter(child_elements(adaptation_set, "Representation")), None)
        if representation is None:
            return ""
        mime_type = str(representation.attrib.get("mimeType") or "").strip().lower()
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        return ""

    periods = [element for element in root.iter() if element.tag == f"{prefix}Period"]
    for period in periods:
        kept_video = False
        kept_audio = False
        for adaptation_set in list(child_elements(period, "AdaptationSet")):
            content_type = adaptation_content_type(adaptation_set)
            if content_type == "video":
                if kept_video:
                    period.remove(adaptation_set)
                    continue
                kept_video = True
            elif content_type == "audio":
                if kept_audio:
                    period.remove(adaptation_set)
                    continue
                kept_audio = True
            representations = child_elements(adaptation_set, "Representation")
            for extra_representation in representations[1:]:
                adaptation_set.remove(extra_representation)

    for base_url in [element for element in root.iter() if element.tag == f"{prefix}BaseURL"]:
        raw_url = unescape((base_url.text or "").strip())
        asset_index = len(session.dash_assets)
        session.dash_assets.append(raw_url)
        base_url.text = f"{proxy_base_url}/dash/asset/{quote(session.token)}/{asset_index}.m4s"

    if namespace:
        ET.register_namespace("", namespace)
    return ET.tostring(root, encoding="utf-8").replace(b" />", b"/>")


def _parse_byte_range_header(range_header: str) -> tuple[int, int | None] | None:
    match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header.strip())
    if match is None:
        return None
    start = int(match.group(1))
    end_text = match.group(2)
    end = int(end_text) if end_text else None
    return start, end


def _slice_payload_for_byte_range(payload: bytes, range_header: str) -> tuple[bytes, str] | None:
    parsed = _parse_byte_range_header(range_header)
    if parsed is None:
        return None
    start, end = parsed
    if start >= len(payload):
        return b"", f"bytes */{len(payload)}"
    inclusive_end = len(payload) - 1 if end is None else min(end, len(payload) - 1)
    if inclusive_end < start:
        return None
    sliced = payload[start : inclusive_end + 1]
    return sliced, f"bytes {start}-{inclusive_end}/{len(payload)}"


def _default_stream(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    follow_redirects: bool,
) -> Any:
    return httpx.stream(
        method,
        url,
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
    )


class LocalHlsProxyServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 2323, get=httpx.get, stream=_default_stream) -> None:
        self.host = host
        self.port = port
        self._preferred_port = port
        self._get = get
        self._stream = stream
        self._registry = ProxySessionRegistry()
        self._segment_proxy = SegmentProxy(self._registry, get=get)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._server = ThreadingHTTPServer((self.host, self._preferred_port), self._handler_type())
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or self._preferred_port == 0:
                raise
            logger.warning(
                "Local HLS proxy port busy, fallback to ephemeral port host=%s port=%s",
                self.host,
                self._preferred_port,
            )
            self._server = ThreadingHTTPServer((self.host, 0), self._handler_type())
        self.port = int(self._server.server_address[1])
        self._server.proxy_server = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self.port = self._preferred_port

    def create_playlist_url(self, url: str, headers: dict[str, str] | None = None) -> str:
        token = self._registry.create_session(url, normalize_media_request_headers(url, headers))
        return f"http://{self.host}:{self.port}/m3u?v={quote(token)}"

    def create_media_url(self, url: str, headers: dict[str, str] | None = None) -> str:
        token = self._registry.create_session(url, normalize_media_request_headers(url, headers))
        return f"http://{self.host}:{self.port}/raw?v={quote(token)}"

    def create_dash_url(self, url: str, headers: dict[str, str] | None = None) -> str:
        token = self._registry.create_session(url, normalize_media_request_headers(url, headers))
        return f"http://{self.host}:{self.port}/dash/{quote(token)}.mpd"

    @staticmethod
    def _query_token(query: dict[str, list[str]]) -> str:
        values = query.get("token") or query.get("v")
        if not values:
            raise KeyError("token")
        return values[0]

    @staticmethod
    def _path_token(path: str) -> str:
        if not path.startswith("/dash/") or not path.endswith(".mpd"):
            raise KeyError("token")
        token = path.removeprefix("/dash/").removesuffix(".mpd")
        if not token:
            raise KeyError("token")
        return token

    @staticmethod
    def _dash_asset_path(path: str) -> tuple[str, int]:
        prefix = "/dash/asset/"
        if not path.startswith(prefix) or not path.endswith(".m4s"):
            raise KeyError("token")
        asset_path = path.removeprefix(prefix)
        token, _separator, index_part = asset_path.partition("/")
        if not token or not index_part:
            raise KeyError("token")
        return token, int(index_part.removesuffix(".m4s"))

    def _proxy_dash_asset(
        self,
        token: str,
        asset_index: int,
        request_headers: dict[str, str] | None = None,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        session = self._registry.get(token)
        if session is None:
            return 404, [], b"missing proxy session"
        if asset_index < 0 or asset_index >= len(session.dash_assets):
            return 404, [], b"missing dash asset"
        upstream_headers = dict(session.headers)
        range_header = (request_headers or {}).get("Range") or (request_headers or {}).get("range")
        if range_header:
            upstream_headers["Range"] = range_header
        response = self._get(
            session.dash_assets[asset_index],
            headers=upstream_headers,
            timeout=10.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        status_code = int(getattr(response, "status_code", 200) or 200)
        body = bytes(response.content)
        content_range = response.headers.get("Content-Range")
        if range_header and status_code == 200 and not content_range:
            sliced = _slice_payload_for_byte_range(body, range_header)
            if sliced is not None:
                body, content_range = sliced
                status_code = 206
        headers: list[tuple[str, str]] = []
        content_type = response.headers.get("Content-Type")
        if content_type:
            headers.append(("Content-Type", content_type))
        if content_range:
            headers.append(("Content-Range", content_range))
        accept_ranges = response.headers.get("Accept-Ranges")
        if accept_ranges:
            headers.append(("Accept-Ranges", accept_ranges))
        elif range_header or status_code == 206:
            headers.append(("Accept-Ranges", "bytes"))
        return status_code, headers, body

    def _stream_dash_asset_response(
        self,
        path: str,
        request_headers: dict[str, str],
        handler: BaseHTTPRequestHandler,
    ) -> bool:
        if not (path.startswith("/dash/asset/") and path.endswith(".m4s")):
            return False
        token, asset_index = self._dash_asset_path(urlparse(path).path)
        session = self._registry.get(token)
        if session is None:
            payload = b"missing proxy session"
            handler.send_response(404)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
            return True
        if asset_index < 0 or asset_index >= len(session.dash_assets):
            payload = b"missing dash asset"
            handler.send_response(404)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
            return True
        upstream_headers = dict(session.headers)
        range_header = request_headers.get("Range") or request_headers.get("range")
        if range_header:
            upstream_headers["Range"] = range_header
        with self._stream(
            "GET",
            session.dash_assets[asset_index],
            headers=upstream_headers,
            timeout=10.0,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            handler.send_response(int(getattr(response, "status_code", 200) or 200))
            for header_name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                header_value = response.headers.get(header_name)
                if header_value:
                    handler.send_header(header_name, header_value)
            handler.end_headers()
            for chunk in response.iter_bytes():
                if chunk:
                    handler.wfile.write(chunk)
        return True

    def handle_request(
        self,
        method: str,
        path: str,
        request_headers: dict[str, str] | None = None,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        parsed = urlparse(path)
        query = parse_qs(parsed.query)
        try:
            if method != "GET":
                return 405, [], b"method not allowed"
            if parsed.path == "/m3u":
                token = self._query_token(query)
                session = self._registry.get(token)
                if session is None:
                    return 404, [], b"missing proxy session"
                try:
                    response = self._get(
                        session.playlist_url,
                        headers=session.headers,
                        timeout=10.0,
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response is not None and exc.response.status_code == 403:
                        if session.cached_playlist_text is not None:
                            return (
                                200,
                                [("Content-Type", "application/vnd.apple.mpegurl")],
                                session.cached_playlist_text.encode("utf-8"),
                            )
                        self._registry.delete(token)
                    raise
                rewritten = rewrite_playlist(
                    token=token,
                    playlist_url=session.playlist_url,
                    content=response.text,
                    session_registry=self._registry,
                    proxy_base_url=f"http://{self.host}:{self.port}",
                )
                session.cached_playlist_text = rewritten.text
                return 200, [("Content-Type", "application/vnd.apple.mpegurl")], rewritten.text.encode("utf-8")
            if parsed.path == "/seg":
                token = self._query_token(query)
                session = self._registry.get(token)
                if session is None:
                    return 404, [], b"missing proxy session"
                index = int(query["i"][0])
                payload = self._segment_proxy.fetch_segment(token, index)
                return 200, [("Content-Type", "video/MP2T")], payload
            if parsed.path == "/asset":
                token = self._query_token(query)
                session = self._registry.get(token)
                if session is None:
                    return 404, [], b"missing proxy session"
                asset_url = query["url"][0]
                payload = self._segment_proxy.fetch_asset(token, asset_url)
                return 200, [], payload
            if parsed.path == "/raw":
                token = self._query_token(query)
                session = self._registry.get(token)
                if session is None:
                    return 404, [], b"missing proxy session"
                payload = self._segment_proxy.fetch_media(token)
                return 200, [("Content-Type", "video/MP2T")], payload
            if parsed.path.startswith("/dash/asset/") and parsed.path.endswith(".m4s"):
                token, asset_index = self._dash_asset_path(parsed.path)
                return self._proxy_dash_asset(token, asset_index, request_headers=request_headers)
            if parsed.path == "/mpd" or (parsed.path.startswith("/dash/") and parsed.path.endswith(".mpd")):
                token = self._path_token(parsed.path) if parsed.path != "/mpd" else self._query_token(query)
                session = self._registry.get(token)
                if session is None:
                    return 404, [], b"missing proxy session"
                proxy_base_url = f"http://{self.host}:{self.port}"
                payload = _rewrite_dash_manifest(
                    _sanitize_dash_manifest(_decode_dash_manifest(session.playlist_url)),
                    session,
                    proxy_base_url,
                )
                return 200, [("Content-Type", "application/dash+xml")], payload
        except Exception as exc:
            return 502, [], str(exc).encode("utf-8")
        return 404, [], b"not found"

    def _handler_type(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                try:
                    if parent._stream_dash_asset_response(self.path, dict(self.headers.items()), self):
                        return
                except Exception as exc:
                    payload = str(exc).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                status, headers, payload = parent.handle_request("GET", self.path, dict(self.headers.items()))
                self.send_response(status)
                for key, value in headers:
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args) -> None:
                return None

        return Handler
