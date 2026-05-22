# yt-dlp Multi-Audio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose selectable `yt-dlp` audio candidates in the existing `音轨` UI, default to original English when available, and switch `yt-dlp` audio by re-resolving playback while preserving quality, position, and pause state.

**Architecture:** Keep `yt-dlp` audio selection as source-level state owned by `PlayItem` and resolved by `YtdlpPlaybackService`, not as an `mpv` embedded-track concern. Reuse the current quality-switch reload pattern so `player_window.py` remains the coordinator for state transitions while `mpv_widget.py` stays responsible only for real `mpv` track switching.

**Tech Stack:** Python, PySide6, dataclasses, pytest, `yt-dlp`, mpv

---

## File Structure

- Modify: `src/atv_player/models.py`
  Add a reusable `YtdlpAudioTrackOption` dataclass and extend `PlayItem` with explicit `yt-dlp` audio state.
- Modify: `src/atv_player/yt_dlp_service.py`
  Parse audio candidates from extractor payloads, select the default English/original track, extend cache keys, and carry audio-track data in `YtdlpResolveResult`.
- Modify: `src/atv_player/ui/main_window.py`
  Pass selected `yt-dlp` audio state into direct-parse and `yt-dlp` playback-loader resolution.
- Modify: `src/atv_player/plugins/controller.py`
  Pass selected `yt-dlp` audio state when hydrating spider/plugin items through `yt-dlp`.
- Modify: `src/atv_player/ui/player_window.py`
  Populate the existing `音轨` combo/menu from `PlayItem.audio_tracks` when present and reload the current item when a `yt-dlp` audio candidate is selected.
- Test: `tests/test_yt_dlp_service.py`
  Cover candidate extraction, default selection, cache behavior, and `PlayItem` hydration.
- Test: `tests/test_main_window_ui.py`
  Cover direct-parse playback loader forwarding of selected `yt-dlp` audio.
- Test: `tests/test_spider_plugin_controller.py`
  Cover spider/plugin hydration forwarding of selected `yt-dlp` audio.
- Test: `tests/test_player_window_ui.py`
  Cover UI population, `yt-dlp` audio switching, quality/audio preservation, and non-`yt-dlp` fallback behavior.

### Task 1: Add Explicit `yt-dlp` Audio Models

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/yt_dlp_service.py`
- Test: `tests/test_yt_dlp_service.py`

- [ ] **Step 1: Write the failing model-hydration tests**

```python
def test_apply_result_copies_ytdlp_audio_tracks_and_selected_audio_id(monkeypatch, service):
    info = _sample_info(
        formats=[
            {
                "format_id": "137",
                "url": "https://stream.test/video.mp4",
                "height": 1080,
                "vcodec": "avc1",
                "acodec": "none",
            },
            {
                "format_id": "140",
                "url": "https://stream.test/audio-en.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "language": "en",
                "language_preference": 10,
                "format_note": "original",
            },
            {
                "format_id": "140-dub",
                "url": "https://stream.test/audio-zh.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "language": "zh",
                "format_note": "dubbed",
            },
        ]
    )
    _stub_extract_info(monkeypatch, service, info)

    result = service.resolve("https://www.youtube.com/watch?v=test123")
    item = PlayItem(title="Episode", url="", original_url="", vod_id="video-1")
    service.apply_result(result, item=item, source_url="https://www.youtube.com/watch?v=test123")

    assert [track.id for track in item.audio_tracks] == ["ytdlp_audio_en_140", "ytdlp_audio_zh_140-dub"]
    assert item.selected_audio_track_id == "ytdlp_audio_en_140"
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_yt_dlp_service.py -k "copies_ytdlp_audio_tracks" -v`
Expected: FAIL because `PlayItem` and `YtdlpResolveResult` do not yet expose `audio_tracks` or `selected_audio_track_id`.

- [ ] **Step 3: Add the new dataclass and state fields**

```python
@dataclass(slots=True)
class YtdlpAudioTrackOption:
    id: str
    label: str
    lang: str = ""
    format_id: str = ""
    is_original: bool = False
    is_default: bool = False
    ytdl_format: str = ""


@dataclass(slots=True)
class PlayItem:
    title: str
    url: str
    original_title: str = ""
    original_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    audio_url: str = ""
    audio_tracks: list["YtdlpAudioTrackOption"] = field(default_factory=list)
    selected_audio_track_id: str = ""
    playback_qualities: list["VideoQualityOption"] = field(default_factory=list)
    selected_playback_quality_id: str = ""
    ytdl_format: str = ""
```

```python
@dataclass(frozen=True, slots=True)
class YtdlpResolveResult:
    url: str
    audio_url: str
    ytdl_format: str
    video_format_id: str
    audio_format_id: str
    audio_tracks: list[YtdlpAudioTrackOption]
    selected_audio_track_id: str
    subtitles: list[ExternalSubtitleOption]
    qualities: list[VideoQualityOption]
    selected_quality_id: str
```

- [ ] **Step 4: Update `apply_result()` so the new fields are hydrated**

```python
item.audio_tracks = list(result.audio_tracks)
item.selected_audio_track_id = str(result.selected_audio_track_id or "").strip()
if not item.selected_audio_track_id and item.audio_tracks:
    item.selected_audio_track_id = item.audio_tracks[0].id
```

- [ ] **Step 5: Re-run the targeted model test**

Run: `uv run pytest tests/test_yt_dlp_service.py -k "copies_ytdlp_audio_tracks" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/models.py src/atv_player/yt_dlp_service.py tests/test_yt_dlp_service.py
git commit -m "feat: add yt-dlp audio track state"
```

### Task 2: Parse Audio Candidates and Resolve the Default Track

**Files:**
- Modify: `src/atv_player/yt_dlp_service.py`
- Test: `tests/test_yt_dlp_service.py`

- [ ] **Step 1: Write the failing resolver tests for extraction, preference, and cache selection**

```python
def test_resolve_prefers_original_english_audio_track(monkeypatch, service):
    info = _sample_info(
        extractor="youtube",
        formats=[
            {"format_id": "137", "url": "https://stream.test/video.mp4", "height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"format_id": "140-zh", "url": "https://stream.test/audio-zh.m4a", "vcodec": "none", "acodec": "mp4a", "language": "zh", "format_note": "dubbed"},
            {"format_id": "140-en", "url": "https://stream.test/audio-en.m4a", "vcodec": "none", "acodec": "mp4a", "language": "en", "format_note": "original", "language_preference": 10},
        ],
    )
    _stub_extract_info(monkeypatch, service, info)

    result = service.resolve("https://www.youtube.com/watch?v=test123")

    assert [track.id for track in result.audio_tracks] == ["ytdlp_audio_en_140-en", "ytdlp_audio_zh_140-zh"]
    assert result.selected_audio_track_id == "ytdlp_audio_en_140-en"
    assert result.audio_format_id == "140-en"


def test_resolve_for_quality_preserves_requested_audio_track(monkeypatch, service):
    info = _sample_info(
        extractor="youtube",
        formats=[
            {"format_id": "22", "url": "https://stream.test/720-muxed.mp4", "height": 720, "vcodec": "avc1", "acodec": "mp4a"},
            {"format_id": "137", "url": "https://stream.test/1080-video.mp4", "height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"format_id": "140-en", "url": "https://stream.test/audio-en.m4a", "vcodec": "none", "acodec": "mp4a", "language": "en", "format_note": "original"},
            {"format_id": "140-zh", "url": "https://stream.test/audio-zh.m4a", "vcodec": "none", "acodec": "mp4a", "language": "zh", "format_note": "dubbed"},
        ],
    )
    _stub_extract_info(monkeypatch, service, info)

    result = service.resolve_for_quality(
        "https://www.youtube.com/watch?v=test123",
        "ytdlp_720",
        audio_track_id="ytdlp_audio_en_140-en",
    )

    assert result.selected_quality_id == "ytdlp_720"
    assert result.selected_audio_track_id == "ytdlp_audio_en_140-en"
```

```python
def test_resolve_cache_key_includes_selected_audio_track(monkeypatch, service):
    info = _sample_info(
        extractor="youtube",
        formats=[
            {"format_id": "137", "url": "https://stream.test/video.mp4", "height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"format_id": "140-en", "url": "https://stream.test/audio-en.m4a", "vcodec": "none", "acodec": "mp4a", "language": "en", "format_note": "original"},
            {"format_id": "140-zh", "url": "https://stream.test/audio-zh.m4a", "vcodec": "none", "acodec": "mp4a", "language": "zh", "format_note": "dubbed"},
        ],
    )
    calls = _stub_extract_info(monkeypatch, service, info)

    service.resolve("https://www.youtube.com/watch?v=test123", selected_audio_track_id="ytdlp_audio_en_140-en")
    service.resolve("https://www.youtube.com/watch?v=test123", selected_audio_track_id="ytdlp_audio_zh_140-zh")

    assert len(calls) == 2
```

- [ ] **Step 2: Run the targeted resolver tests**

Run: `uv run pytest tests/test_yt_dlp_service.py -k "original_english_audio_track or preserves_requested_audio_track or cache_key_includes_selected_audio_track" -v`
Expected: FAIL because the resolver cannot parse or select multiple audio candidates yet.

- [ ] **Step 3: Implement `yt-dlp` audio candidate parsing and default ranking**

```python
def _build_audio_track_options(info: dict) -> list[YtdlpAudioTrackOption]:
    candidates = _group_audio_candidates(info)
    options = [
        YtdlpAudioTrackOption(
            id=_audio_track_option_id(candidate),
            label=_audio_track_label(candidate),
            lang=_normalize_audio_lang(candidate),
            format_id=str(candidate.get("format_id") or ""),
            is_original=_audio_candidate_is_original(candidate),
            is_default=_audio_candidate_is_default(candidate),
            ytdl_format=_audio_track_selector(candidate),
        )
        for candidate in candidates
    ]
    return sorted(options, key=_audio_track_sort_key)


def _audio_track_sort_key(option: YtdlpAudioTrackOption) -> tuple[int, int, int, str]:
    return (
        0 if option.lang == "en" and option.is_original else 1,
        0 if option.lang == "en" else 1,
        0 if option.is_default else 1,
        option.label.casefold(),
    )
```

```python
def _resolve_selected_audio_track_id(
    audio_tracks: list[YtdlpAudioTrackOption],
    requested_audio_track_id: str,
) -> str:
    if requested_audio_track_id and any(track.id == requested_audio_track_id for track in audio_tracks):
        return requested_audio_track_id
    if audio_tracks:
        return audio_tracks[0].id
    return ""
```

- [ ] **Step 4: Extend resolver entry points and cache keys to include audio selection**

```python
def _cache_key(self, url: str, max_height: int | None, audio_track_id: str = "") -> str:
    quality_part = f"h={max_height}" if max_height and max_height > 0 else "h=any"
    audio_part = audio_track_id.strip() or "audio=auto"
    return f"{url.strip()}#{quality_part}#{audio_part}"


def resolve(
    self,
    url: str,
    log: object = None,
    *,
    max_height: int | None = None,
    selected_audio_track_id: str = "",
) -> YtdlpResolveResult:
    configured_default_height = self._configured_max_height() if max_height is None else None
    cache_height = max_height if max_height is not None else configured_default_height
    cached = self._get_cached_result(url, cache_height, selected_audio_track_id)
    if cached is not None:
        return cached
    info = self._extract_info_via_command(url, max_height, include_subtitles=True)
    return self._build_resolve_result(
        info,
        url=url,
        cache_height=cache_height,
        requested_audio_track_id=selected_audio_track_id,
    )


def resolve_for_quality(
    self,
    url: str,
    quality_id: str,
    log: object = None,
    *,
    audio_track_id: str = "",
) -> YtdlpResolveResult:
    return self.resolve(url, log=log, max_height=_quality_height_from_id(quality_id), selected_audio_track_id=audio_track_id)
```

- [ ] **Step 5: Use the selected audio candidate when composing the final stream pair**

```python
audio_tracks = _build_audio_track_options(info)
selected_audio_track_id = _resolve_selected_audio_track_id(audio_tracks, selected_audio_track_id)
selected_audio = _select_audio_format(info, audio_tracks, selected_audio_track_id, fallback=selected_audio)

result = YtdlpResolveResult(
    url=playback_url,
    audio_url=requested_audio_url,
    ytdl_format=ytdl_format,
    video_format_id=str((selected_video or {}).get("format_id") or ""),
    audio_format_id=str((selected_audio or {}).get("format_id") or ""),
    audio_tracks=audio_tracks,
    selected_audio_track_id=selected_audio_track_id,
    subtitles=subtitles,
    qualities=qualities,
    selected_quality_id=selected_quality_id,
)
```

- [ ] **Step 6: Run the full `yt-dlp` service suite**

Run: `uv run pytest tests/test_yt_dlp_service.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/yt_dlp_service.py tests/test_yt_dlp_service.py
git commit -m "feat: parse yt-dlp multi-audio candidates"
```

### Task 3: Plumb Selected Audio Through Playback Loaders

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing loader-plumbing tests**

```python
def test_direct_ytdlp_loader_passes_selected_audio_track_id(qtbot, monkeypatch):
    resolve_calls: list[tuple[str, str, str]] = []

    class FakeYtDlp:
        def is_available(self) -> bool:
            return True

        def resolve_for_quality(self, url: str, quality_id: str, log=None, *, audio_track_id: str = ""):
            del log
            resolve_calls.append((url, quality_id, audio_track_id))
            return type(
                "Result",
                (),
                {
                    "url": url,
                    "audio_url": "",
                    "ytdl_format": "299+140",
                    "headers": {},
                    "subtitles": [],
                    "qualities": [],
                    "selected_quality_id": quality_id,
                    "selected_audio_track_id": audio_track_id,
                    "audio_tracks": [],
                    "duration_seconds": 0,
                    "title": "Test Video",
                    "thumbnail": "",
                    "description": "",
                },
            )()

    service = FakeYtDlp()
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
    request = window._build_ytdlp_parse_request("https://www.youtube.com/watch?v=test123")
    session = type("Session", (), {"vod": request.vod})()
    item = request.playlist[0]
    item.selected_playback_quality_id = "ytdlp_1080"
    item.selected_audio_track_id = "ytdlp_audio_en_140"
    request.playback_loader(session, item)

    assert resolve_calls == [("https://www.youtube.com/watch?v=test123", "ytdlp_1080", "ytdlp_audio_en_140")]
```

```python
def test_controller_hydrates_ytdlp_item_with_selected_audio_track(monkeypatch):
    resolve_calls: list[tuple[str, str, str]] = []

    class FakeYtDlp:
        def is_available(self) -> bool:
            return True

        def can_resolve(self, url: str) -> bool:
            return "youtube.com" in url

        def resolve_for_quality(self, url: str, quality_id: str, log=None, *, audio_track_id: str = ""):
            del log
            resolve_calls.append((url, quality_id, audio_track_id))
            return type(
                "Result",
                (),
                {
                    "url": url,
                    "audio_url": "",
                    "ytdl_format": "298+140",
                    "headers": {},
                    "subtitles": [],
                    "qualities": [],
                    "selected_quality_id": quality_id,
                    "selected_audio_track_id": audio_track_id,
                    "audio_tracks": [],
                    "duration_seconds": 0,
                    "title": "Test Video",
                    "thumbnail": "",
                    "description": "",
                },
            )()

    service = FakeYtDlp()
    controller = SpiderPluginController(
        YoutubeDetailSpider(),
        plugin_name="YouTube插件",
        search_enabled=True,
        yt_dlp_service=service,
    )
    item = PlayItem(title="正片", url="", original_url="https://www.youtube.com/watch?v=test123", vod_id="yt")
    item.selected_playback_quality_id = "ytdlp_720"
    item.selected_audio_track_id = "ytdlp_audio_en_140"

    controller._maybe_hydrate_ytdlp_item(item, "https://www.youtube.com/watch?v=test123")

    assert resolve_calls == [("https://www.youtube.com/watch?v=test123", "ytdlp_720", "ytdlp_audio_en_140")]
```

- [ ] **Step 2: Run the targeted loader tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "selected_audio_track_id" -v`
Run: `uv run pytest tests/test_spider_plugin_controller.py -k "selected_audio_track" -v`
Expected: FAIL because current loader code only forwards selected quality.

- [ ] **Step 3: Thread selected audio through the main-window loaders**

```python
def resolve_with_ytdlp(current_item: PlayItem, source_url: str):
    yt_dlp = self._yt_dlp_service
    if yt_dlp is None or not yt_dlp.is_available():
        raise ValueError("yt-dlp 不可用")
    selected_quality_id = current_item.selected_playback_quality_id or ""
    selected_audio_track_id = current_item.selected_audio_track_id or ""
    if selected_quality_id.startswith("ytdlp_"):
        return yt_dlp.resolve_for_quality(
            source_url,
            selected_quality_id,
            audio_track_id=selected_audio_track_id,
        )
    return yt_dlp.resolve(source_url, max_height=None, selected_audio_track_id=selected_audio_track_id)
```

- [ ] **Step 4: Thread selected audio through spider/plugin hydration**

```python
selected_quality_id = item.selected_playback_quality_id or ""
selected_audio_track_id = item.selected_audio_track_id or ""
if selected_quality_id.startswith("ytdlp_"):
    result = yt_dlp.resolve_for_quality(candidate, selected_quality_id, audio_track_id=selected_audio_track_id)
else:
    result = yt_dlp.resolve(candidate, max_height=None, selected_audio_track_id=selected_audio_track_id)
```

- [ ] **Step 5: Re-run both loader suites**

Run: `uv run pytest tests/test_main_window_ui.py -k "selected_audio_track_id" -v`
Run: `uv run pytest tests/test_spider_plugin_controller.py -k "selected_audio_track" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/main_window.py src/atv_player/plugins/controller.py tests/test_main_window_ui.py tests/test_spider_plugin_controller.py
git commit -m "feat: plumb yt-dlp audio selection through loaders"
```

### Task 4: Reuse the Existing `音轨` UI for `yt-dlp` Audio Candidates

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing UI tests for population and switching**

```python
def test_player_window_populates_audio_combo_from_ytdlp_audio_tracks(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://www.youtube.com/watch?v=test123",
                original_url="https://www.youtube.com/watch?v=test123",
                audio_tracks=[
                    YtdlpAudioTrackOption(id="ytdlp_audio_en_140", label="English Original", lang="en", is_original=True),
                    YtdlpAudioTrackOption(id="ytdlp_audio_zh_141", label="中文配音", lang="zh"),
                ],
                selected_audio_track_id="ytdlp_audio_en_140",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)
    assert [window.audio_combo.itemText(i) for i in range(window.audio_combo.count())] == [
        "音轨",
        "English Original",
        "中文配音",
    ]
    assert window.audio_combo.currentText() == "English Original"
```

```python
def test_player_window_switches_ytdlp_audio_via_reload_preserving_quality_position_and_pause(qtbot) -> None:
    loader_calls: list[tuple[str, str]] = []

    def playback_loader(item: PlayItem) -> None:
        loader_calls.append((item.selected_playback_quality_id, item.selected_audio_track_id))
        item.url = "https://www.youtube.com/watch?v=test123"
        item.ytdl_format = "299+141" if item.selected_audio_track_id == "ytdlp_audio_zh_141" else "299+140"

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://www.youtube.com/watch?v=test123",
                original_url="https://www.youtube.com/watch?v=test123",
                audio_tracks=[
                    YtdlpAudioTrackOption(id="ytdlp_audio_en_140", label="English Original", lang="en", is_original=True),
                    YtdlpAudioTrackOption(id="ytdlp_audio_zh_141", label="中文配音", lang="zh"),
                ],
                selected_audio_track_id="ytdlp_audio_en_140",
                playback_qualities=[VideoQualityOption(id="ytdlp_1080", label="1080p", ytdl_format="299+140")],
                selected_playback_quality_id="ytdlp_1080",
                ytdl_format="299+140",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    session.playback_loader = playback_loader

    video = FakeVideo()
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = video
    window.open_session(session)
    session.playlist[0].selected_playback_quality_id = "ytdlp_1080"
    session.playlist[0].selected_audio_track_id = "ytdlp_audio_en_140"
    window.is_playing = False
    window.audio_combo.setCurrentIndex(2)

    assert loader_calls == [("ytdlp_1080", "ytdlp_audio_en_140"), ("ytdlp_1080", "ytdlp_audio_zh_141")]
    assert video.load_calls[-1] == ("https://www.youtube.com/watch?v=test123", True, 93, "299+141")
```

```python
def test_player_window_keeps_mpv_audio_track_behavior_for_non_ytdlp_items(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    fake_video = FakeVideo()
    window.video = fake_video
    window._audio_tracks = [
        AudioTrack(id=1, title="Original", lang="en", is_default=True, is_forced=False, label="Original"),
        AudioTrack(id=2, title="Dub", lang="zh", is_default=False, is_forced=False, label="Dub"),
    ]
    window._populate_audio_combo(window._audio_tracks)
    window.audio_combo.setCurrentIndex(2)
    assert fake_video.apply_audio_calls == [("track", 2)]
```

- [ ] **Step 2: Run the targeted player-window tests**

Run: `uv run pytest tests/test_player_window_ui.py -k "ytdlp_audio" -v`
Expected: FAIL because the combo currently only knows `mpv` `AudioTrack` entries and `_change_audio_selection()` always calls `apply_audio_mode()`.

- [ ] **Step 3: Add source-aware combo population for `yt-dlp` audio**

```python
def _current_item_ytdlp_audio_tracks(self) -> list[YtdlpAudioTrackOption]:
    if self.session is None or self.current_index < 0:
        return []
    item = self.session.playlist[self.current_index]
    return list(getattr(item, "audio_tracks", []) or [])


def _populate_audio_combo(self, tracks: list[AudioTrack]) -> None:
    ytdlp_tracks = self._current_item_ytdlp_audio_tracks()
    self.audio_combo.blockSignals(True)
    self.audio_combo.clear()
    self.audio_combo.addItem("音轨", ("auto", None))
    if ytdlp_tracks:
        selected_index = 0
        current_item = self.session.playlist[self.current_index]
        for index, track in enumerate(ytdlp_tracks, start=1):
            self.audio_combo.addItem(track.label, ("ytdlp", track.id))
            if track.id == current_item.selected_audio_track_id:
                selected_index = index
        self.audio_combo.setEnabled(len(ytdlp_tracks) > 1)
        self.audio_combo.setCurrentIndex(selected_index)
    elif len(tracks) > 1:
        for track in tracks:
            self.audio_combo.addItem(track.label, ("track", track.id))
        self.audio_combo.setEnabled(True)
        self.audio_combo.setCurrentIndex(0)
    else:
        self.audio_combo.setEnabled(False)
        self.audio_combo.setCurrentIndex(0)
    self.audio_combo.blockSignals(False)
```

- [ ] **Step 4: Route `yt-dlp` audio selection through reload instead of `mpv aid`**

```python
def _change_audio_selection(self, index: int) -> None:
    if index < 0 or self.session is None:
        return
    item_data = self.audio_combo.itemData(index)
    if item_data is None:
        return
    mode, track_id = item_data
    if mode == "ytdlp":
        self._change_ytdlp_audio_selection(str(track_id or ""))
        return
    if mode == "auto":
        self._audio_preference = AudioPreference()
        self.video.apply_audio_mode("auto")
        return
    track = next((track for track in self._audio_tracks if track.id == track_id), None)
    if track is None:
        return
    self._remember_audio_track_preference(track)
    self.video.apply_audio_mode("track", track_id=track_id)
```

```python
def _change_ytdlp_audio_selection(self, track_id: str) -> None:
    current_item = self.session.playlist[self.current_index]
    if not track_id or track_id == current_item.selected_audio_track_id or self.session.playback_loader is None:
        return
    previous_audio_track_id = current_item.selected_audio_track_id
    previous_url = current_item.url
    previous_audio_url = current_item.audio_url
    previous_ytdl_format = current_item.ytdl_format
    start_position_seconds = int(self.video.position_seconds() or 0)
    current_item.selected_audio_track_id = track_id
    try:
        self._play_item_at_index(
            self.current_index,
            start_position_seconds=start_position_seconds,
            pause=not self.is_playing,
            preserve_primary_external_subtitle_selection=True,
        )
    except Exception as exc:
        current_item.selected_audio_track_id = previous_audio_track_id
        current_item.url = previous_url
        current_item.audio_url = previous_audio_url
        current_item.ytdl_format = previous_ytdl_format
        self._refresh_audio_state()
        self._append_log(f"音轨切换失败: {exc}")
```

- [ ] **Step 5: Preserve audio on quality switches and quality on audio switches**

```python
if current_item.playback_qualities:
    previous_selected_quality_id = current_item.selected_playback_quality_id
    current_item.selected_playback_quality_id = target_quality_id
    # Do not clear selected_audio_track_id here; the loader/service re-resolves the combination.
    if not self._start_playback_prepare(
        previous_index=self.current_index,
        start_position_seconds=start_position_seconds,
        pause=not self.is_playing,
        previous_url=previous_url,
        previous_original_url=previous_original_url,
        previous_selected_playback_quality_id=previous_selected_quality_id,
    ):
        current_item.selected_playback_quality_id = previous_selected_quality_id
```

```python
def playback_loader(item: PlayItem) -> None:
    result = yt_dlp.resolve_for_quality(
        source_url,
        item.selected_playback_quality_id,
        audio_track_id=item.selected_audio_track_id,
    )
```

- [ ] **Step 6: Re-run the targeted player-window suite**

Run: `uv run pytest tests/test_player_window_ui.py -k "ytdlp_audio or switches_ytdlp_quality" -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add yt-dlp audio switching in player window"
```

### Task 5: Run Cross-Module Regression Checks

**Files:**
- Modify: none
- Test: `tests/test_yt_dlp_service.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the focused multi-audio regression set**

Run: `uv run pytest tests/test_yt_dlp_service.py tests/test_main_window_ui.py tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -k "ytdlp and (audio or quality)" -q`
Expected: PASS

- [ ] **Step 2: Run the broader player-window regression set that already covers `yt-dlp` quality switching**

Run: `uv run pytest tests/test_player_window_ui.py -k "switches_ytdlp_quality or audio_combo" -q`
Expected: PASS

- [ ] **Step 3: Verify there is no accidental `mpv_widget.py` behavior change**

Run: `uv run pytest tests/test_mpv_widget.py -k "ytdl_format" -q`
Expected: PASS because `mpv_widget.py` should remain responsible only for actual embedded tracks and `ytdl_format` loading.

- [ ] **Step 4: Inspect diff for source-boundary violations**

Run: `git diff -- src/atv_player/models.py src/atv_player/yt_dlp_service.py src/atv_player/ui/main_window.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py`
Expected: Only the planned files change; no `mpv_widget.py` edit unless a test forces a minimal compatibility tweak.

- [ ] **Step 5: Commit the final verified stack**

```bash
git add src/atv_player/models.py src/atv_player/yt_dlp_service.py src/atv_player/ui/main_window.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py tests/test_yt_dlp_service.py tests/test_main_window_ui.py tests/test_spider_plugin_controller.py tests/test_player_window_ui.py
git commit -m "feat: support yt-dlp multi-audio playback selection"
```
