# yt-dlp Detail Writeback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `yt-dlp` playback entry overwrite the current session's video detail metadata with the resolved title, poster, description, and runtime playback fields.

**Architecture:** Add one shared `YtdlpPlaybackService.apply_result()` helper that mutates an existing `VodItem` and `PlayItem` from a `YtdlpResolveResult`. Then switch `MainWindow` and `SpiderPluginController` to call that helper instead of maintaining their own field-by-field writeback logic, with tests covering direct `yt-dlp`, parser fallback, and plugin playback.

**Tech Stack:** Python 3, PySide6 UI/controller layer, dataclass models, `pytest`

---

## File Structure

- Modify: `src/atv_player/yt_dlp_service.py`
  Responsibility: define the shared `yt-dlp` result writeback helper and reuse it from `resolve_to_play_item()`.
- Modify: `src/atv_player/ui/main_window.py`
  Responsibility: route both `ytdlp` async loading and parser-fallback-to-`yt-dlp` through the shared helper.
- Modify: `src/atv_player/plugins/controller.py`
  Responsibility: pass the current session `VodItem` into `yt-dlp` hydration so plugin playback updates visible detail metadata.
- Modify: `tests/test_yt_dlp_service.py`
  Responsibility: lock down overwrite semantics for `VodItem` and `PlayItem`.
- Modify: `tests/test_main_window_ui.py`
  Responsibility: verify both `MainWindow` `yt-dlp` paths apply metadata back to the session detail object.
- Modify: `tests/test_spider_plugin_controller.py`
  Responsibility: verify plugin playback updates `session.vod` when the resolved URL is a YouTube link.

### Task 1: Add Shared `yt-dlp` Writeback Helper

**Files:**
- Modify: `tests/test_yt_dlp_service.py`
- Modify: `src/atv_player/yt_dlp_service.py`

- [ ] **Step 1: Write the failing service test**

Add this test near the existing `resolve_to_play_item()` assertions in `tests/test_yt_dlp_service.py`:

```python
    def test_apply_result_overwrites_vod_and_play_item(self, monkeypatch, service):
        info = _sample_info(
            title="Resolved Title",
            thumbnail="https://img.test/resolved.jpg",
            description="",
            duration=321,
        )
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")
        vod = VodItem(
            vod_id="detail-1",
            vod_name="Original Title",
            vod_pic="https://img.test/original.jpg",
            vod_content="original description",
        )
        item = PlayItem(
            title="Original Episode",
            url="",
            original_url="",
            vod_id="detail-1",
            media_title="Original Media",
            duration_seconds=12,
            selected_playback_quality_id="",
        )

        service.apply_result(
            result,
            vod=vod,
            item=item,
            source_url="https://www.youtube.com/watch?v=test123",
        )

        assert vod.vod_id == "detail-1"
        assert vod.vod_name == "Resolved Title"
        assert vod.vod_pic == "https://img.test/resolved.jpg"
        assert vod.vod_content == ""
        assert item.url == "https://www.youtube.com/watch?v=test123"
        assert item.original_url == "https://www.youtube.com/watch?v=test123"
        assert item.title == "Resolved Title"
        assert item.media_title == "Resolved Title"
        assert item.duration_seconds == 321
        assert item.selected_playback_quality_id == "ytdlp_1080"
        assert len(item.playback_qualities) == 3
        assert len(item.external_subtitles) == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_yt_dlp_service.py -k "apply_result_overwrites_vod_and_play_item" -v
```

Expected: FAIL with `AttributeError: 'YtdlpPlaybackService' object has no attribute 'apply_result'`

- [ ] **Step 3: Implement the shared helper in `YtdlpPlaybackService`**

Add this method in `src/atv_player/yt_dlp_service.py` inside `class YtdlpPlaybackService`, below `resolve_for_quality()`:

```python
    def apply_result(
        self,
        result: YtdlpResolveResult,
        *,
        vod: VodItem | None = None,
        item: PlayItem | None = None,
        source_url: str = "",
    ) -> None:
        resolved_source_url = (
            str(source_url or "")
            or (item.original_url if item is not None else "")
            or (item.vod_id if item is not None else "")
            or result.url
        )
        resolved_title = str(result.title or "").strip() or resolved_source_url

        if vod is not None:
            vod.vod_name = resolved_title
            vod.vod_pic = str(result.thumbnail or "")
            vod.vod_content = str(result.description or "")

        if item is None:
            return

        item.url = str(result.url or "")
        item.original_url = resolved_source_url
        item.headers = dict(result.headers)
        item.audio_url = str(result.audio_url or "")
        item.ytdl_format = str(result.ytdl_format or "")
        item.playback_qualities = list(result.qualities)
        item.external_subtitles = list(result.subtitles)
        item.duration_seconds = int(result.duration_seconds or 0)
        item.title = resolved_title
        item.media_title = resolved_title

        resolved_quality_id = str(result.selected_quality_id or "").strip()
        if resolved_quality_id:
            item.selected_playback_quality_id = resolved_quality_id
        elif item.playback_qualities:
            item.selected_playback_quality_id = item.playback_qualities[0].id
        else:
            item.selected_playback_quality_id = ""
```

- [ ] **Step 4: Reuse the helper from `resolve_to_play_item()`**

Replace the body of `resolve_to_play_item()` in `src/atv_player/yt_dlp_service.py` with:

```python
    def resolve_to_play_item(
        self,
        url: str,
        *,
        max_height: int | None = None,
    ) -> tuple[VodItem, PlayItem]:
        result = self.resolve(url, max_height=max_height)
        vod = VodItem(vod_id=url, vod_name=url)
        item = PlayItem(
            title=url,
            url="",
            original_url=url,
            vod_id=url,
            media_title=url,
        )
        self.apply_result(result, vod=vod, item=item, source_url=url)
        return vod, item
```

- [ ] **Step 5: Run the focused service tests**

Run:

```bash
uv run pytest tests/test_yt_dlp_service.py -k "apply_result_overwrites_vod_and_play_item or test_success" -v
```

Expected: PASS for the new overwrite test and the existing `resolve_to_play_item()` success regression

- [ ] **Step 6: Commit the service-layer change**

Run:

```bash
git add tests/test_yt_dlp_service.py src/atv_player/yt_dlp_service.py
git commit -m "feat: add shared yt-dlp writeback helper"
```

### Task 2: Route Both `MainWindow` `yt-dlp` Paths Through the Helper

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `src/atv_player/ui/main_window.py`

- [ ] **Step 1: Write the failing parser-fallback test**

Add this test near the existing `yt-dlp` loader tests in `tests/test_main_window_ui.py`:

```python
def test_main_window_direct_parse_fallback_to_ytdlp_overwrites_session_metadata(qtbot) -> None:
    class FailingParserService:
        def resolve(self, flag: str, url: str, preferred_key: str = ""):
            raise ValueError("parser failed")

    class FakeYtdlpService:
        def is_available(self) -> bool:
            return True

        def resolve(self, url: str, *, max_height: int | None = None):
            return type(
                "Result",
                (),
                {
                    "url": "https://www.youtube.com/watch?v=test123",
                    "title": "Fallback Video",
                    "thumbnail": "https://img.example/fallback.jpg",
                    "description": "fallback description",
                    "duration_seconds": 654,
                    "headers": {"Referer": "https://www.youtube.com/"},
                    "subtitles": [],
                    "qualities": [],
                    "audio_url": "",
                    "ytdl_format": "299+140",
                    "extractor": "youtube",
                    "selected_quality_id": "ytdlp_1080",
                },
            )()

        def resolve_for_quality(self, url: str, quality_id: str):
            return self.resolve(url)

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
        config=AppConfig(preferred_parse_key="jx1"),
        plugin_manager=FakePluginManager(),
        playback_parser_service=FailingParserService(),
        yt_dlp_service=FakeYtdlpService(),
    )

    qtbot.addWidget(window)

    request = window._build_direct_parse_request("https://www.youtube.com/watch?v=test123")
    session = type("Session", (), {"vod": request.vod})()
    item = request.playlist[0]

    request.playback_loader(session, item)

    assert session.vod.vod_name == "Fallback Video"
    assert session.vod.vod_pic == "https://img.example/fallback.jpg"
    assert session.vod.vod_content == "fallback description"
    assert item.url == "https://www.youtube.com/watch?v=test123"
    assert item.headers == {"Referer": "https://www.youtube.com/"}
    assert item.selected_playback_quality_id == "ytdlp_1080"
    assert item.ytdl_format == "299+140"
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "fallback_to_ytdlp_overwrites_session_metadata" -v
```

Expected: FAIL with a `TypeError` because the loader only accepts one positional argument, or FAIL because `session.vod` never updates

- [ ] **Step 3: Update `_build_direct_parse_request()` and `_build_ytdlp_parse_request()`**

In `src/atv_player/ui/main_window.py`, replace the direct-parse loader with a wrapper that accepts either `(item)` or `(session, item)` and uses `apply_result()` in the fallback branch:

```python
        def load_item(
            session_or_item,
            item: PlayItem | None = None,
        ):
            session = session_or_item if item is not None else None
            current_item = item or session_or_item
            source_url = (current_item.original_url or current_item.vod_id or url).strip() or url
            try:
                result = self._playback_parser_service.resolve(
                    "",
                    source_url,
                    preferred_key=getattr(self.config, "preferred_parse_key", ""),
                )
                current_item.url = result.url
                current_item.original_url = source_url
                current_item.headers = dict(result.headers)
            except ValueError:
                yt_result = resolve_with_ytdlp(current_item, source_url)
                self._yt_dlp_service.apply_result(
                    yt_result,
                    vod=None if session is None else session.vod,
                    item=current_item,
                    source_url=source_url,
                )
            current_item.parse_required = True
            if danmaku_controller is not None:
                danmaku_controller.maybe_resolve(current_item)
            return None
```

In the `ytdlp` async loader in the same file, replace the manual field assignments with:

```python
            self._yt_dlp_service.apply_result(
                result,
                vod=session.vod,
                item=current_item,
                source_url=source_url,
            )
```

- [ ] **Step 4: Run the focused `MainWindow` regression tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "fallback_to_ytdlp_overwrites_session_metadata or treats_youtube_url_as_async_ytdlp_request or ytdlp_loader_resolves_selected_quality_on_reload or treats_non_drive_url_as_direct_parse" -v
```

Expected: PASS for the new fallback coverage, existing async `yt-dlp` coverage, selected-quality reload coverage, and the one-argument direct-parse regression

- [ ] **Step 5: Commit the `MainWindow` change**

Run:

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/main_window.py
git commit -m "refactor: unify main window yt-dlp writeback"
```

### Task 3: Sync Plugin `yt-dlp` Hydration Back Into `session.vod`

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/plugins/controller.py`

- [ ] **Step 1: Write the failing plugin session-detail test**

Add this test near the existing YouTube plugin hydration tests in `tests/test_spider_plugin_controller.py`:

```python
def test_controller_playback_loader_overwrites_session_vod_with_ytdlp_metadata() -> None:
    class FakeYtdlpService:
        def is_available(self) -> bool:
            return True

        def can_resolve(self, url: str) -> bool:
            return "youtube.com" in url

        def resolve(self, url: str, *, max_height: int | None = None):
            return type(
                "Result",
                (),
                {
                    "url": url,
                    "audio_url": "",
                    "headers": {"Referer": "https://www.youtube.com/"},
                    "subtitles": [],
                    "qualities": [],
                    "ytdl_format": "bestvideo+bestaudio/best",
                    "selected_quality_id": "ytdlp_2160",
                    "title": "Resolved YouTube Title",
                    "thumbnail": "https://img.example/youtube.jpg",
                    "description": "resolved plugin description",
                    "duration_seconds": 777,
                },
            )()

    controller = SpiderPluginController(
        YoutubeDetailSpider(),
        plugin_name="YouTube插件",
        search_enabled=True,
        yt_dlp_service=FakeYtdlpService(),
    )

    request = controller.build_request("/detail/youtube")
    first = request.playlists[0][0]
    session = type(
        "Session",
        (),
        {
            "vod": request.vod,
            "playlist": request.playlist,
            "video_cover_override": "",
        },
    )()

    assert request.playback_loader is not None
    request.playback_loader(session, first)

    assert session.vod.vod_name == "Resolved YouTube Title"
    assert session.vod.vod_pic == "https://img.example/youtube.jpg"
    assert session.vod.vod_content == "resolved plugin description"
    assert first.title == "Resolved YouTube Title"
    assert first.media_title == "Resolved YouTube Title"
    assert first.duration_seconds == 777
```

- [ ] **Step 2: Run the new plugin test to verify it fails**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "overwrites_session_vod_with_ytdlp_metadata" -v
```

Expected: FAIL because `session.vod` keeps the original plugin detail instead of the resolved YouTube metadata

- [ ] **Step 3: Thread `vod` through plugin hydration and call the shared helper**

In `src/atv_player/plugins/controller.py`, update the two call sites inside `_resolve_play_item()`:

```python
        if item.url:
            self._maybe_hydrate_ytdlp_item(item, item.url, vod=session.vod)
            session.video_cover_override = item.video_cover_override
            if not item.danmaku_xml:
                self._maybe_resolve_danmaku(item, item.url, current_playlist)
            return
```

and:

```python
        if not self._maybe_hydrate_ytdlp_item(item, url, vod=session.vod):
            item.playback_qualities, item.selected_playback_quality_id = _map_spider_playback_qualities(
                payload.get("qualities"),
                url,
            )
```

Then change `_maybe_hydrate_ytdlp_item()` to accept `vod` and reuse the service helper:

```python
    def _maybe_hydrate_ytdlp_item(
        self,
        item: PlayItem,
        source_url: str,
        *,
        vod: VodItem | None = None,
    ) -> bool:
        yt_dlp = self._yt_dlp_service
        if yt_dlp is None or not yt_dlp.is_available():
            return False
        candidate = str(source_url or "").strip()
        if not candidate or not yt_dlp.can_resolve(candidate):
            return False
        selected_quality_id = item.selected_playback_quality_id or ""
        if selected_quality_id.startswith("ytdlp_"):
            result = yt_dlp.resolve_for_quality(candidate, selected_quality_id)
        else:
            result = yt_dlp.resolve(candidate, max_height=None)
        yt_dlp.apply_result(result, vod=vod, item=item, source_url=candidate)
        return True
```

- [ ] **Step 4: Run the focused plugin regressions**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "hydrates_prefilled_youtube_url_via_ytdlp or resolves_playercontent_youtube_url_via_ytdlp or overwrites_session_vod_with_ytdlp_metadata" -v
```

Expected: PASS for both existing YouTube hydration tests and the new session-detail writeback test

- [ ] **Step 5: Commit the plugin change**

Run:

```bash
git add tests/test_spider_plugin_controller.py src/atv_player/plugins/controller.py
git commit -m "feat: sync plugin yt-dlp metadata into session"
```

## Self-Review

- Spec coverage:
  - Shared helper and unified overwrite rules: Task 1
  - `MainWindow` direct `yt-dlp` and parser fallback alignment: Task 2
  - Plugin playback detail writeback: Task 3
  - No expansion into unstable `vod_year`/`vod_actor` fields: preserved by Task 1 helper scope
- Placeholder scan:
  - No `TODO`/`TBD`
  - Every code-changing step includes concrete code
  - Every test step includes an exact command and expected failure/pass signal
- Type consistency:
  - Helper name is consistently `apply_result`
  - Main window and plugin code both call `apply_result(..., vod=..., item=..., source_url=...)`
  - Plugin signature consistently uses `_maybe_hydrate_ytdlp_item(..., vod=...)`
