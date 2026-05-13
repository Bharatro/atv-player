# yt-dlp Startup Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all `yt-dlp` playback opens show the player window immediately, resolve in-window asynchronously, and reuse short-lived cached results to shorten repeated startup.

**Architecture:** Keep the current `MainWindow -> OpenPlayerRequest -> PlayerSession -> PlayerWindow` flow, but stop doing synchronous `yt-dlp` extraction in `MainWindow`. Instead, create a placeholder `OpenPlayerRequest` whose `playback_loader` mutates the active session and play item after `yt-dlp` resolves, while `YtdlpPlaybackService` owns a small in-memory TTL cache for extracted results.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, threaded async loaders, existing `PlayerSession` binding behavior in `PlayerController`

---

## File Structure

- Modify: `src/atv_player/yt_dlp_service.py`
  - Responsibility: keep `yt-dlp` availability and domain detection logic, add a service-local TTL cache for `YtdlpResolveResult`, and keep `resolve()` as the single extraction entry point.
- Modify: `src/atv_player/ui/main_window.py`
  - Responsibility: replace synchronous `_build_ytdlp_parse_request()` behavior with a placeholder request plus a two-argument `playback_loader(session, item)` that hydrates session and item state after `yt-dlp` resolves.
- Modify: `src/atv_player/ui/player_window.py`
  - Responsibility: refresh window title and visible playlist rows after an async loader mutates the current item and `session.vod`.
- Modify: `tests/test_yt_dlp_service.py`
  - Responsibility: prove cache hit and cache expiry behavior without hitting the network.
- Modify: `tests/test_main_window_ui.py`
  - Responsibility: prove a YouTube URL now creates an async placeholder request and does not call the old synchronous `resolve_to_play_item()` path.
- Modify: `tests/test_player_window_ui.py`
  - Responsibility: prove async yt-dlp hydration refreshes the visible UI and does not let stale loader results overwrite the current selection.

## Task 1: Add TTL Caching To `YtdlpPlaybackService`

**Files:**
- Modify: `src/atv_player/yt_dlp_service.py`
- Test: `tests/test_yt_dlp_service.py`

- [ ] **Step 1: Write the failing cache-hit and cache-expiry tests**

```python
def test_resolve_uses_cached_result_before_ttl_expires(mock_ytdlp_module) -> None:
    from atv_player.yt_dlp_service import YtdlpPlaybackService

    info = _sample_info()
    extractor = MagicMock(return_value=info)
    mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
        return_value=MagicMock(extract_info=extractor)
    )
    mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

    clock = {"now": 100.0}
    service = YtdlpPlaybackService(ttl_seconds=300.0, now=lambda: clock["now"])

    first = service.resolve("https://www.youtube.com/watch?v=test123")
    second = service.resolve("https://www.youtube.com/watch?v=test123")

    assert first.url == "https://stream.test/direct.mp4"
    assert second.url == "https://stream.test/direct.mp4"
    assert extractor.call_count == 1


def test_resolve_re_extracts_after_cache_expiry(mock_ytdlp_module) -> None:
    from atv_player.yt_dlp_service import YtdlpPlaybackService

    info = _sample_info()
    extractor = MagicMock(return_value=info)
    mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
        return_value=MagicMock(extract_info=extractor)
    )
    mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

    clock = {"now": 100.0}
    service = YtdlpPlaybackService(ttl_seconds=5.0, now=lambda: clock["now"])

    service.resolve("https://www.youtube.com/watch?v=test123")
    clock["now"] = 110.0
    service.resolve("https://www.youtube.com/watch?v=test123")

    assert extractor.call_count == 2
```

- [ ] **Step 2: Run the focused yt-dlp tests and confirm the new cache tests fail**

Run: `uv run pytest tests/test_yt_dlp_service.py -k "cache or expiry" -v`

Expected: `FAIL` because `YtdlpPlaybackService.__init__()` does not yet accept `ttl_seconds` / `now`, and `resolve()` always calls `yt_dlp` extraction again.

- [ ] **Step 3: Implement the service-local TTL cache in `src/atv_player/yt_dlp_service.py`**

```python
from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(slots=True)
class _YtdlpCacheEntry:
    result: YtdlpResolveResult
    expires_at: float


class YtdlpPlaybackService:
    def __init__(
        self,
        ttl_seconds: float = 300.0,
        now: Callable[[], float] = monotonic,
    ) -> None:
        self._ytdlp_module: object | None = ...
        self._supported_domains: frozenset[str] | None = None
        self._ttl_seconds = float(ttl_seconds)
        self._now = now
        self._cache: dict[str, _YtdlpCacheEntry] = {}

    def _get_cached_result(self, url: str) -> YtdlpResolveResult | None:
        key = url.strip()
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._cache.pop(key, None)
            return None
        return entry.result

    def _store_cached_result(self, url: str, result: YtdlpResolveResult) -> None:
        key = url.strip()
        self._cache[key] = _YtdlpCacheEntry(
            result=result,
            expires_at=self._now() + self._ttl_seconds,
        )

    def resolve(self, url: str, log: object = None) -> YtdlpResolveResult:
        cached = self._get_cached_result(url)
        if cached is not None:
            if callable(log):
                log(f"yt-dlp 命中缓存 [{cached.extractor}]")
            return cached
        if not self.is_available():
            raise ValueError("yt-dlp 未安装")
        import yt_dlp

        ytdlp_opts: dict = {
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "extract_flat": False,
            "noplaylist": True,
        }

        if callable(log):
            log("yt-dlp 正在提取视频信息...")
        try:
            with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.GeoRestrictedError:
            raise ValueError("该内容受地区限制")
        except yt_dlp.utils.ExtractorError as exc:
            raise ValueError(f"无法获取视频: {exc}")
        except yt_dlp.utils.DownloadError as exc:
            raise ValueError(f"下载错误: {exc}")
        except Exception as exc:
            raise ValueError(f"yt-dlp 解析失败: {exc}")

        if info is None:
            raise ValueError("yt-dlp 未返回结果")

        direct_url = info.get("url", "")
        if not direct_url:
            formats = info.get("formats") or []
            for fmt in formats:
                if fmt.get("url"):
                    direct_url = fmt["url"]
                    break
        if not direct_url:
            raise ValueError("未获取到播放地址")

        http_headers = info.get("http_headers") or {}
        headers = {
            k: v for k, v in http_headers.items()
            if isinstance(k, str) and isinstance(v, str)
        }
        qualities = _build_quality_options(info)
        subtitles = _build_subtitle_options(info)
        result = YtdlpResolveResult(
            url=direct_url,
            title=info.get("title", ""),
            thumbnail=info.get("thumbnail", ""),
            description=info.get("description", ""),
            duration_seconds=int(info.get("duration") or 0),
            headers=headers,
            subtitles=subtitles,
            qualities=qualities,
            extractor=info.get("extractor", ""),
        )
        if callable(log):
            log(
                f"yt-dlp 提取完成 [{result.extractor}] 清晰度={len(result.qualities)} 字幕={len(result.subtitles)}"
            )
        self._store_cached_result(url, result)
        return result
```

- [ ] **Step 4: Run the focused yt-dlp tests and confirm they pass**

Run: `uv run pytest tests/test_yt_dlp_service.py -k "cache or expiry or resolve_to_play_item" -v`

Expected: `PASS` for the new cache tests and the existing `resolve_to_play_item` regression coverage.

- [ ] **Step 5: Commit the cache work**

```bash
git add tests/test_yt_dlp_service.py src/atv_player/yt_dlp_service.py
git commit -m "feat: cache yt-dlp resolve results"
```

## Task 2: Replace Synchronous yt-dlp Open Requests With Async Placeholders

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing main-window test for YouTube async placeholder requests**

```python
def test_main_window_global_search_treats_youtube_url_as_async_ytdlp_request(qtbot, monkeypatch) -> None:
    class FakeYtdlpService:
        def __init__(self) -> None:
            self.resolve_calls: list[str] = []

        def is_available(self) -> bool:
            return True

        def can_resolve(self, url: str) -> bool:
            return "youtube.com" in url

        def resolve(self, url: str):
            self.resolve_calls.append(url)
            return type(
                "Result",
                (),
                {
                    "url": "https://media.example/youtube.mp4",
                    "title": "Async Test Video",
                    "thumbnail": "https://img.example/poster.jpg",
                    "description": "async description",
                    "duration_seconds": 321,
                    "headers": {"Referer": "https://www.youtube.com/"},
                    "subtitles": [],
                    "qualities": [],
                    "extractor": "youtube",
                },
            )()

        def resolve_to_play_item(self, url: str):
            raise AssertionError("resolve_to_play_item should not be used")

    opened: list[OpenPlayerRequest] = []
    service = FakeYtdlpService()
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
        yt_dlp_service=service,
    )
    monkeypatch.setattr(window, "open_player", lambda request, restore_paused_state=False: opened.append(request))

    qtbot.addWidget(window)
    window.show()
    url = "https://www.youtube.com/watch?v=test123"
    window.global_search_edit.setText(url)
    window.global_search_button.click()

    qtbot.waitUntil(lambda: len(opened) == 1)

    request = opened[0]
    assert request.source_kind == "direct_parse"
    assert request.source_mode == "ytdlp"
    assert request.source_vod_id == url
    assert request.async_playback_loader is True
    assert request.playlist[0].url == ""
    assert request.playlist[0].original_url == url

    session = type("Session", (), {"vod": request.vod})()
    request.playback_loader(session, request.playlist[0])

    assert service.resolve_calls == [url]
    assert session.vod.vod_name == "Async Test Video"
    assert session.vod.vod_pic == "https://img.example/poster.jpg"
    assert session.vod.vod_content == "async description"
    assert request.playlist[0].url == "https://media.example/youtube.mp4"
    assert request.playlist[0].headers == {"Referer": "https://www.youtube.com/"}
```

- [ ] **Step 2: Run the focused main-window test and confirm it fails**

Run: `uv run pytest tests/test_main_window_ui.py -k "youtube_url_as_async_ytdlp_request" -v`

Expected: `FAIL` because `_build_ytdlp_parse_request()` still calls `resolve_to_play_item()` synchronously and returns a fully hydrated request instead of an async placeholder.

- [ ] **Step 3: Implement the placeholder request builder in `src/atv_player/ui/main_window.py`**

```python
def _apply_ytdlp_result_to_session(self, session, item: PlayItem, source_url: str, result) -> None:
    item.url = result.url
    item.original_url = source_url
    item.headers = dict(result.headers)
    item.playback_qualities = list(result.qualities)
    item.external_subtitles = list(result.subtitles)
    item.duration_seconds = result.duration_seconds
    item.media_title = result.title or item.media_title or source_url
    item.title = result.title or item.title or source_url
    if item.playback_qualities and not item.selected_playback_quality_id:
        item.selected_playback_quality_id = item.playback_qualities[0].id
    session.vod.vod_name = result.title or session.vod.vod_name or source_url
    session.vod.vod_pic = result.thumbnail
    session.vod.vod_content = result.description


def _build_ytdlp_parse_request(self, url: str) -> OpenPlayerRequest:
    if self._yt_dlp_service is None or not self._yt_dlp_service.is_available():
        raise ValueError("yt-dlp 不可用")
    history_loader, history_saver = self._direct_parse_history_hooks(url)

    def load_item(session, current_item: PlayItem):
        source_url = (current_item.original_url or current_item.vod_id or url).strip() or url
        result = self._yt_dlp_service.resolve(source_url)
        self._apply_ytdlp_result_to_session(session, current_item, source_url, result)
        return None

    item = PlayItem(
        title=url,
        url="",
        original_url=url,
        vod_id=url,
        media_title=url,
        parse_required=False,
    )
    return OpenPlayerRequest(
        vod=VodItem(vod_id=url, vod_name=url),
        playlist=[item],
        clicked_index=0,
        source_kind="direct_parse",
        source_mode="ytdlp",
        source_vod_id=url,
        use_local_history=False,
        playback_loader=load_item,
        async_playback_loader=True,
        playback_history_loader=history_loader,
        playback_history_saver=history_saver,
    )
```

- [ ] **Step 4: Run the focused main-window yt-dlp test and the nearby direct-open regressions**

Run: `uv run pytest tests/test_main_window_ui.py -k "youtube_url_as_async_ytdlp_request or non_drive_url_as_direct_parse or treats_drive_url_as_direct_detail_open" -v`

Expected: `PASS`, proving the YouTube path is now async while existing non-yt direct-open paths still work.

- [ ] **Step 5: Commit the main-window request rewrite**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/main_window.py
git commit -m "feat: open yt-dlp links with async placeholder sessions"
```

## Task 3: Refresh Player UI After Async yt-dlp Hydration

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window UI tests for async yt-dlp hydration**

```python
def test_player_window_async_loader_refreshes_title_metadata_and_playlist_after_hydration(qtbot, monkeypatch) -> None:
    poster_sources: list[tuple[str, str]] = []

    def fake_start(self, source: str, request_id: int, *, target: str, on_loaded=None) -> None:
        poster_sources.append((target, source))

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    class FakeVideo:
        def __init__(self) -> None:
            self.load_calls: list[tuple[str, bool, int, dict[str, str]]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
            self.load_calls.append((url, pause, start_seconds, headers or {}))

        def set_speed(self, value: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 0

    ready = threading.Event()
    session = PlayerSession(
        vod=VodItem(vod_id="https://www.youtube.com/watch?v=test123", vod_name="https://www.youtube.com/watch?v=test123"),
        playlist=[PlayItem(title="https://www.youtube.com/watch?v=test123", url="", original_url="https://www.youtube.com/watch?v=test123", vod_id="https://www.youtube.com/watch?v=test123")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        async_playback_loader=True,
    )

    def playback_loader(current_session: PlayerSession, item: PlayItem) -> None:
        assert ready.wait(timeout=1)
        current_session.vod.vod_name = "Hydrated Video"
        current_session.vod.vod_pic = "https://img.example/poster.jpg"
        current_session.vod.vod_content = "hydrated description"
        item.title = "Hydrated Video"
        item.media_title = "Hydrated Video"
        item.url = "https://media.example/youtube.mp4"
        item.headers = {"Referer": "https://www.youtube.com/"}
        item.external_subtitles = [
            ExternalSubtitleOption(
                name="English [yt-dlp]",
                lang="en",
                url="https://sub.example/en.vtt",
                format="vtt",
                source="ytdlp",
            )
        ]
        item.playback_qualities = [
            VideoQualityOption(
                id="720p",
                label="720P",
                url="https://media.example/youtube.mp4",
            )
        ]
        item.selected_playback_quality_id = "720p"

    session.playback_loader = playback_loader

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)

    assert "正在加载播放地址" in window.log_view.toPlainText()
    ready.set()

    qtbot.waitUntil(
        lambda: window.video.load_calls == [("https://media.example/youtube.mp4", False, 0, {"Referer": "https://www.youtube.com/"})]
    )
    assert "Hydrated Video" in window.windowTitle()
    assert window.playlist.item(0).text() == "Hydrated Video"
    assert "hydrated description" in window.metadata_view.toPlainText()
    assert window.video_quality_combo.currentData() == "720p"
    assert window.subtitle_combo.isEnabled() is True
    assert ("detail", "https://img.example/poster.jpg") in poster_sources


def test_player_window_ignores_stale_async_loader_result_after_switching_items(qtbot) -> None:
    ready = threading.Event()
    session = PlayerSession(
        vod=VodItem(vod_id="vod-1", vod_name="Placeholder"),
        playlist=[
            PlayItem(title="待解析", url="", vod_id="ep-1", original_url="https://www.youtube.com/watch?v=one"),
            PlayItem(title="第二集", url="https://media.example/two.mp4", vod_id="ep-2"),
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        async_playback_loader=True,
    )

    def playback_loader(current_session: PlayerSession, item: PlayItem) -> None:
        assert ready.wait(timeout=1)
        current_session.vod.vod_name = "旧结果"
        item.title = "旧结果"
        item.url = "https://media.example/stale.mp4"

    session.playback_loader = playback_loader

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(session)
    window.play_next()
    ready.set()

    qtbot.wait(100)
    assert window.current_index == 1
    assert window.playlist.item(1).text() == "第二集"
    assert "旧结果" not in window.windowTitle()
```

- [ ] **Step 2: Run the focused player-window tests and confirm they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "hydration or stale_async_loader_result" -v`

Expected: `FAIL` because `_handle_playback_loader_succeeded()` currently re-renders metadata and poster, but it does not refresh the window title or visible playlist row labels after the loader mutates the active item and `session.vod`.

- [ ] **Step 3: Update `src/atv_player/ui/player_window.py` to refresh visible UI after async loader success**

```python
def _handle_playback_loader_succeeded(self, request_id: int, load_result: PlaybackLoadResult | None) -> None:
    if request_id != self._playback_loader_request_id:
        return
    pending_loader = self._pending_playback_loader
    self._pending_playback_loader = None
    if pending_loader is None:
        return
    if self.session is None or self.current_index != pending_loader.index:
        return
    self._apply_playback_loader_result(load_result)
    self._render_playlist_items()
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()
    self._refresh_window_title()
    self._refresh_parse_combo_enabled_state()
    current_item = self.session.playlist[self.current_index]
    if not current_item.url:
        self._restore_or_keep_current_index_after_failure(pending_loader.previous_index)
        self._append_log(f"播放失败: 没有可用的播放地址: {current_item.title}")
        return
    try:
        if self._start_playback_prepare(
            previous_index=pending_loader.previous_index,
            start_position_seconds=pending_loader.start_position_seconds,
            pause=pending_loader.pause,
        ):
            return
        self._start_current_item_playback(
            start_position_seconds=pending_loader.start_position_seconds,
            pause=pending_loader.pause,
        )
    except Exception as exc:
        self._restore_or_keep_current_index_after_failure(pending_loader.previous_index)
        self._append_log(f"播放失败: {exc}")
```

- [ ] **Step 4: Re-run the focused player-window tests and nearby async-loader regressions**

Run: `uv run pytest tests/test_player_window_ui.py -k "async_session_loader or hydration or stale_async_loader_result" -v`

Expected: `PASS`, proving the existing async loader path still starts playback correctly and the yt-dlp-specific UI refresh behavior now works.

- [ ] **Step 5: Commit the player-window refresh changes**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: refresh player ui after async yt-dlp hydration"
```

## Task 4: Run The Focused Regression Sweep

**Files:**
- Test: `tests/test_yt_dlp_service.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the three focused suites together**

Run: `uv run pytest tests/test_yt_dlp_service.py tests/test_main_window_ui.py tests/test_player_window_ui.py -v`

Expected: `PASS` for yt-dlp service, main-window direct-open, and player-window async-loader coverage with no newly introduced thread-handling failures.

- [ ] **Step 2: Run a narrower smoke selection around first-playback optimizations**

Run: `uv run pytest tests/test_main_window_ui.py -k "direct_parse or youtube or drive_url" tests/test_player_window_ui.py -k "async_session_loader or startup or hydration" -v`

Expected: `PASS`, confirming the new async yt-dlp path coexists with the existing direct-parse and startup-state behaviors.

- [ ] **Step 3: Inspect the worktree before finishing**

Run: `git status --short`

Expected: only the intended source and test files from Tasks 1-3 are modified, with no stray debug changes.

- [ ] **Step 4: If the regression sweep required follow-up fixes, stage and commit them**

```bash
git add src/atv_player/yt_dlp_service.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py tests/test_yt_dlp_service.py tests/test_main_window_ui.py tests/test_player_window_ui.py
git commit -m "test: cover async yt-dlp startup flow"
```

If Step 1 and Step 2 both pass without additional edits, skip this commit because Tasks 1-3 already created the implementation commits.
