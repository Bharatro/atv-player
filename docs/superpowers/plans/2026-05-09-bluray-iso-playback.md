# Blu-ray ISO Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-version remote Blu-ray ISO playback by resolving a `.iso` URL into a proxied `BDMV/STREAM/*.m2ts` HTTP stream before handing playback to `mpv`.

**Architecture:** Add a focused Blu-ray ISO service that inspects remote ISO images through HTTP range reads and selects a default `m2ts` stream. Extend the local proxy to expose that selected internal stream as a range-capable HTTP endpoint, then wire the existing playback-preparation path to rewrite remote `.iso` URLs to that proxy URL and stop falling back to direct ISO playback on preparation failure.

**Tech Stack:** Python 3.12+, PySide6, `httpx`, `pycdlib`, existing `LocalHlsProxyServer`, `pytest`, `pytest-qt`

---

## File Structure

- Create: `src/atv_player/player/bluray_iso.py`
  Purpose: remote ISO detection, Blu-ray layout validation, default `m2ts` selection, remote range-backed ISO reads.
- Modify: `pyproject.toml`
  Purpose: add the ISO parsing dependency.
- Modify: `src/atv_player/proxy/session.py`
  Purpose: store ISO proxy session metadata.
- Modify: `src/atv_player/proxy/server.py`
  Purpose: create ISO-backed proxy URLs and serve embedded `m2ts` bytes with HTTP range support.
- Modify: `src/atv_player/player/m3u8_ad_filter.py`
  Purpose: expand playback preparation to include remote `.iso` URLs.
- Modify: `src/atv_player/ui/player_window.py`
  Purpose: treat ISO preparation as mandatory and avoid falling back to direct `.iso` playback after preparation failure.
- Create: `tests/test_bluray_iso.py`
  Purpose: cover ISO URL detection, Blu-ray layout validation, and default stream selection.
- Modify: `tests/test_hls_proxy_server.py`
  Purpose: cover ISO proxy URL creation and range serving.
- Modify: `tests/test_m3u8_ad_filter.py`
  Purpose: cover `.iso` preparation through the existing filter entry point.
- Modify: `tests/test_player_window_ui.py`
  Purpose: cover UI-level playback rewriting and failure behavior for ISO playback.

## Dependency Note

Use `pycdlib` for ISO parsing. This plan assumes `pycdlib` is added as a runtime dependency because its official docs support:

- opening an ISO from a file-like object via `open_fp()`
- reading files from an ISO in chunks via `open_file_from_iso()`
- UDF paths, which are required for Blu-ray layouts

## Task 1: Add Blu-ray ISO Core Service

**Files:**
- Modify: `pyproject.toml`
- Create: `src/atv_player/player/bluray_iso.py`
- Test: `tests/test_bluray_iso.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.player.bluray_iso import (
    BluRayIsoStream,
    BlurayIsoInspector,
    is_remote_iso_url,
    pick_main_feature_stream,
)


def test_is_remote_iso_url_accepts_http_iso_with_query() -> None:
    assert is_remote_iso_url("http://media.example/movie.iso?token=1") is True
    assert is_remote_iso_url("https://media.example/MOVIE.ISO") is True
    assert is_remote_iso_url("https://media.example/movie.mkv") is False
    assert is_remote_iso_url("/tmp/movie.iso") is False


def test_pick_main_feature_stream_prefers_largest_m2ts() -> None:
    streams = [
        BluRayIsoStream(path="/BDMV/STREAM/00001.m2ts", size=1048576),
        BluRayIsoStream(path="/BDMV/STREAM/00080.m2ts", size=8589934592),
        BluRayIsoStream(path="/BDMV/STREAM/00010.m2ts", size=2147483648),
    ]

    selected = pick_main_feature_stream(streams)

    assert selected.path == "/BDMV/STREAM/00080.m2ts"


def test_inspector_rejects_non_bluray_layout() -> None:
    inspector = BlurayIsoInspector(
        list_entries=lambda url, headers: [
            "/README.TXT",
            "/VIDEO_TS/VTS_01_1.VOB",
        ]
    )

    try:
        inspector.inspect("http://media.example/disc.iso", {})
    except ValueError as exc:
        assert str(exc) == "远程 ISO 不是受支持的 Blu-ray 目录结构"
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bluray_iso.py -v`

Expected: FAIL with `ModuleNotFoundError` or missing symbols from `atv_player.player.bluray_iso`

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class BluRayIsoStream:
    path: str
    size: int


def is_remote_iso_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = (parsed.path or "").lower()
    return path.endswith(".iso")


def pick_main_feature_stream(streams: list[BluRayIsoStream]) -> BluRayIsoStream:
    if not streams:
        raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
    return max(streams, key=lambda item: (item.size, item.path))


class BlurayIsoInspector:
    def __init__(self, list_entries: Callable[[str, dict[str, str]], list[str]]) -> None:
        self._list_entries = list_entries

    def inspect(self, url: str, headers: dict[str, str]) -> BluRayIsoStream:
        entries = [entry.upper() for entry in self._list_entries(url, headers)]
        if "/BDMV/INDEX.BDMV" not in entries:
            raise ValueError("远程 ISO 不是受支持的 Blu-ray 目录结构")
        stream_paths = [entry for entry in entries if entry.startswith("/BDMV/STREAM/") and entry.endswith(".M2TS")]
        streams = [BluRayIsoStream(path=path, size=0) for path in stream_paths]
        return pick_main_feature_stream(streams)
```

Then expand the same file in the same task to the real implementation:

```python
import io
import pycdlib
import httpx


class RemoteRangeReader(io.RawIOBase):
    ...


def list_iso_entries(url: str, headers: dict[str, str], *, get: Callable[..., httpx.Response] = httpx.get) -> list[str]:
    ...


def stat_iso_streams(url: str, headers: dict[str, str], *, get: Callable[..., httpx.Response] = httpx.get) -> list[BluRayIsoStream]:
    ...


def read_iso_stream_range(
    url: str,
    headers: dict[str, str],
    stream_path: str,
    start: int,
    end: int | None,
    *,
    get: Callable[..., httpx.Response] = httpx.get,
) -> tuple[bytes, int]:
    ...
```

Implementation requirements for the real code:

- add `pycdlib>=1.14.0` to runtime dependencies in `pyproject.toml`
- use UDF paths such as `"/BDMV/STREAM/00080.m2ts"`
- normalize returned paths to one canonical uppercase slash-separated form
- validate Blu-ray layout by requiring `"/BDMV/INDEX.BDMV"` plus at least one `"/BDMV/STREAM/*.M2TS"`
- keep error messages explicit and user-facing

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bluray_iso.py -v`

Expected: PASS for the new ISO unit tests

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/atv_player/player/bluray_iso.py tests/test_bluray_iso.py
git commit -m "feat: add bluray iso inspection service"
```

## Task 2: Extend the Local Proxy for ISO-backed Streams

**Files:**
- Modify: `src/atv_player/proxy/session.py`
- Modify: `src/atv_player/proxy/server.py`
- Test: `tests/test_hls_proxy_server.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.proxy.server import LocalHlsProxyServer


def test_local_hls_proxy_server_creates_iso_media_url() -> None:
    server = LocalHlsProxyServer()

    media_url = server.create_iso_media_url(
        "http://media.example/disc.iso",
        {"Referer": "https://site.example"},
        stream_path="/BDMV/STREAM/00080.m2ts",
        stream_size=4096,
    )

    assert media_url.startswith(f"http://{server.host}:{server.port}/iso/")
    assert media_url.endswith("/BDMV/STREAM/00080.m2ts")


def test_local_hls_proxy_server_serves_iso_stream_range() -> None:
    server = LocalHlsProxyServer()
    media_url = server.create_iso_media_url(
        "http://media.example/disc.iso",
        {},
        stream_path="/BDMV/STREAM/00080.m2ts",
        stream_size=10,
    )
    token = media_url.split("/iso/", 1)[1].split("/", 1)[0]

    server._read_iso_stream_range = lambda *args, **kwargs: (b"2345", 10)

    status, headers, body = server.handle_request(
        "GET",
        f"/iso/{token}/BDMV/STREAM/00080.m2ts",
        {"Range": "bytes=2-5"},
    )

    assert status == 206
    assert ("Content-Type", "video/MP2T") in headers
    assert ("Content-Range", "bytes 2-5/10") in headers
    assert ("Accept-Ranges", "bytes") in headers
    assert body == b"2345"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hls_proxy_server.py -k iso -v`

Expected: FAIL because `create_iso_media_url` and `/iso/...` handling do not exist yet

- [ ] **Step 3: Write minimal implementation**

Add ISO fields to `ProxySession`:

```python
@dataclass(slots=True)
class ProxySession:
    token: str
    playlist_url: str
    headers: dict[str, str]
    ...
    iso_stream_path: str = ""
    iso_stream_size: int = 0
```

Add ISO URL creation and request handling to `LocalHlsProxyServer`:

```python
def create_iso_media_url(
    self,
    url: str,
    headers: dict[str, str] | None = None,
    *,
    stream_path: str,
    stream_size: int,
) -> str:
    token = self._registry.create_session(url, normalize_media_request_headers(url, headers))
    session = self._registry.get(token)
    if session is not None:
        session.iso_stream_path = stream_path
        session.iso_stream_size = stream_size
    return f"http://{self.host}:{self.port}/iso/{quote(token)}{stream_path}"


def _iso_token_and_path(self, path: str) -> tuple[str, str]:
    prefix = "/iso/"
    token_and_path = path.removeprefix(prefix)
    token, _separator, inner_path = token_and_path.partition("/")
    return token, "/" + inner_path
```

Add serving logic:

```python
if parsed.path.startswith("/iso/"):
    token, stream_path = self._iso_token_and_path(parsed.path)
    session = self._registry.get(token)
    if session is None:
        return 404, [], b"missing proxy session"
    payload, total_size = self._read_iso_stream_range(
        session.playlist_url,
        session.headers,
        session.iso_stream_path or stream_path,
        request_headers or {},
    )
    ...
    return status, headers, payload
```

Implementation requirements for the real code:

- add a small `_read_iso_stream_range()` helper on `LocalHlsProxyServer` that delegates to `atv_player.player.bluray_iso.read_iso_stream_range`
- parse and honor `Range` headers
- return `206` with `Content-Range` and `Accept-Ranges` when a valid byte range is present
- return `200` for full-content requests
- use `video/MP2T` as the content type for proxied `m2ts`
- verify that the path tail matches the stored session path when practical, but prefer stored session metadata as the source of truth

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hls_proxy_server.py -k iso -v`

Expected: PASS for the new ISO proxy tests

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/proxy/session.py src/atv_player/proxy/server.py tests/test_hls_proxy_server.py
git commit -m "feat: add iso-backed local proxy playback"
```

## Task 3: Wire ISO Preparation into the Existing Playback Filter

**Files:**
- Modify: `src/atv_player/player/m3u8_ad_filter.py`
- Test: `tests/test_m3u8_ad_filter.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.player.m3u8_ad_filter import M3U8AdFilter


def test_m3u8_ad_filter_treats_remote_iso_as_proxy_candidate() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str], str, int]] = []

        def start(self) -> None:
            return None

        def create_iso_media_url(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            *,
            stream_path: str,
            stream_size: int,
        ) -> str:
            self.calls.append((url, dict(headers or {}), stream_path, stream_size))
            return "http://127.0.0.1:2323/iso/test/BDMV/STREAM/00080.m2ts"

        def close(self) -> None:
            return None

    class FakeInspector:
        def inspect(self, url: str, headers: dict[str, str]):
            return type("Result", (), {"path": "/BDMV/STREAM/00080.m2ts", "size": 123456789})()

    server = FakeServer()
    ad_filter = M3U8AdFilter(proxy_server=server, bluray_iso_inspector=FakeInspector())

    prepared = ad_filter.prepare("http://media.example/disc.iso", {"Referer": "https://site.example"})

    assert ad_filter.should_prepare("http://media.example/disc.iso") is True
    assert prepared == "http://127.0.0.1:2323/iso/test/BDMV/STREAM/00080.m2ts"
    assert server.calls == [
        (
            "http://media.example/disc.iso",
            {"Referer": "https://site.example"},
            "/BDMV/STREAM/00080.m2ts",
            123456789,
        )
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_m3u8_ad_filter.py -k iso -v`

Expected: FAIL because remote ISO detection and inspector injection do not exist yet

- [ ] **Step 3: Write minimal implementation**

Add ISO detection and inspector wiring:

```python
from atv_player.player.bluray_iso import BlurayIsoInspector, is_remote_iso_url


class M3U8AdFilter:
    def __init__(..., bluray_iso_inspector: BlurayIsoInspector | None = None) -> None:
        ...
        self._bluray_iso_inspector = bluray_iso_inspector or BlurayIsoInspector(...)

    def should_prepare(self, url: str) -> bool:
        if is_remote_iso_url(url):
            return True
        ...
```

Handle ISO in `prepare()` before the existing HLS/DASH/media branches:

```python
if is_remote_iso_url(url):
    self._proxy_server.start()
    normalized_headers = normalize_media_request_headers(url, headers)
    selected_stream = self._bluray_iso_inspector.inspect(url, normalized_headers)
    return self._proxy_server.create_iso_media_url(
        url,
        headers=normalized_headers,
        stream_path=selected_stream.path,
        stream_size=selected_stream.size,
    )
```

Implementation requirements for the real code:

- keep existing HLS/DASH behavior unchanged
- normalize headers before inspection so ISO range requests see the same request headers the proxy would use
- let ISO inspection failures raise through `prepare()`; `PlayerWindow` will decide how to present them

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_m3u8_ad_filter.py -k iso -v`

Expected: PASS for the new ISO filter test

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/m3u8_ad_filter.py tests/test_m3u8_ad_filter.py
git commit -m "feat: route remote iso playback through proxy"
```

## Task 4: Enforce ISO-specific Player Behavior and UI Logging

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_rewrites_remote_iso_to_local_proxy_url(qtbot) -> None:
    class FakeM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return url.endswith(".iso")

        def prepare(self, url: str, headers: dict[str, str] | None = None) -> str:
            return "http://127.0.0.1:2323/iso/test/BDMV/STREAM/00080.m2ts"

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[PlayItem(title="正片", url="http://media.example/disc.iso")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    video = RecordingVideo()
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=FakeM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = video

    window.open_session(session)

    qtbot.waitUntil(lambda: video.load_calls == [("http://127.0.0.1:2323/iso/test/BDMV/STREAM/00080.m2ts", 0)])


def test_player_window_does_not_fallback_to_direct_iso_on_prepare_failure(qtbot) -> None:
    class FailingM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return url.endswith(".iso")

        def prepare(self, url: str, headers: dict[str, str] | None = None) -> str:
            raise ValueError("远程 ISO 不是受支持的 Blu-ray 目录结构")

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[PlayItem(title="正片", url="http://media.example/disc.iso")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    video = RecordingVideo()
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=FailingM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = video

    window.open_session(session)
    qtbot.waitUntil(lambda: "远程 ISO 不是受支持的 Blu-ray 目录结构" in window.log_view.toPlainText())

    assert video.load_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k iso -v`

Expected: FAIL because the player currently falls back to the original URL after preparation failure

- [ ] **Step 3: Write minimal implementation**

Add a helper in `PlayerWindow`:

```python
from atv_player.player.bluray_iso import is_remote_iso_url


def _requires_prepared_media_url(self, url: str) -> bool:
    return is_remote_iso_url(url)
```

Use it in `_handle_playback_prepare_failed()`:

```python
def _handle_playback_prepare_failed(self, request_id: int, message: str) -> None:
    ...
    if self._requires_prepared_media_url(pending_prepare.source_url):
        self._append_log(f"播放失败: {message}")
        self._restore_current_index(pending_prepare.previous_index)
        return
    ...
```

Implementation requirements for the real code:

- keep the current fallback-to-original behavior for existing HLS/DASH/media cases
- only suppress fallback for ISO sources that require the proxy-prepared URL
- preserve the current logging style in the playback log panel

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k iso -v`

Expected: PASS for the ISO rewrite and no-fallback tests

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: stop direct playback fallback for iso errors"
```

## Task 5: Run the Focused Verification Suite

**Files:**
- Test: `tests/test_bluray_iso.py`
- Test: `tests/test_hls_proxy_server.py`
- Test: `tests/test_m3u8_ad_filter.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the new ISO unit tests**

Run: `uv run pytest tests/test_bluray_iso.py -v`

Expected: PASS

- [ ] **Step 2: Run the proxy and filter regression slice**

Run: `uv run pytest tests/test_hls_proxy_server.py tests/test_m3u8_ad_filter.py -v`

Expected: PASS

- [ ] **Step 3: Run the player-window regression slice**

Run: `uv run pytest tests/test_player_window_ui.py -k "proxy or iso" -v`

Expected: PASS

- [ ] **Step 4: Run one combined verification command**

Run: `uv run pytest tests/test_bluray_iso.py tests/test_hls_proxy_server.py tests/test_m3u8_ad_filter.py tests/test_player_window_ui.py -k "iso or proxy" -v`

Expected: PASS with the ISO-specific coverage plus nearby proxy/player regressions

- [ ] **Step 5: Commit**

```bash
git add tests/test_bluray_iso.py tests/test_hls_proxy_server.py tests/test_m3u8_ad_filter.py tests/test_player_window_ui.py
git commit -m "test: verify bluray iso playback flow"
```

## Self-Review

- Spec coverage: the plan covers Blu-ray-only inspection, proxy exposure, player integration, explicit failure logging, and focused tests. DVD ISO, menus, and playlist navigation remain out of scope, matching the spec.
- Placeholder scan: no `TODO`, `TBD`, or “handle appropriately” placeholders remain. Each task names exact files, concrete test targets, commands, and commit messages.
- Type consistency: the plan consistently uses `BlurayIsoInspector`, `BluRayIsoStream`, `is_remote_iso_url`, `create_iso_media_url`, and `read_iso_stream_range`. Those same names are referenced in all later tasks.
