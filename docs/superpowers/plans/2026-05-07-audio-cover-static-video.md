# Audio Cover Static Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make audio-only media automatically render a cover-backed static video surface so mpv subtitles remain visible, while preserving spider local subtitle paths and existing subtitle selection behavior.

**Architecture:** Keep subtitle rendering inside mpv. Extend `MpvWidget` with a small audio-cover-aware loading path, let `PlayerWindow` decide when to use it and when to keep Qt poster overlays hidden, and preserve spider local subtitle paths so `subt="/tmp/..."` reaches the player unchanged.

**Tech Stack:** PySide6, python-mpv/mpv, pytest, pytest-qt, existing spider plugin controller/player window code

---

## File Structure

- Modify: `src/atv_player/player/mpv_widget.py`
  - Add the minimal mpv loading surface for audio-only media with a poster-backed visual target.
  - Keep the existing subtitle/audio API stable for `PlayerWindow`.
- Modify: `src/atv_player/ui/player_window.py`
  - Decide whether the current item should request audio-cover mode.
  - Reuse the existing poster/default-cover pipeline.
  - Prevent the Qt poster overlay from hiding active subtitles in audio-only mode.
- Modify: `src/atv_player/plugins/controller.py`
  - Keep real local subtitle paths returned by spider plugins unchanged.
- Modify: `tests/test_mpv_widget.py`
  - Cover mpv configuration and audio-cover loading entry points.
- Modify: `tests/test_player_window_ui.py`
  - Cover audio-only cover behavior, subtitle visibility, local subtitle loading, and regressions.
- Modify: `tests/test_spider_plugin_controller.py`
  - Cover local absolute spider subtitle path preservation.

### Task 1: Preserve Local Spider Subtitle Paths

**Files:**
- Modify: `tests/test_spider_plugin_controller.py:456-490`
- Modify: `tests/test_player_window_ui.py:5472-5505`
- Modify: `src/atv_player/plugins/controller.py:321-335`
- Modify: `src/atv_player/ui/player_window.py:3521-3542`

- [ ] **Step 1: Write the failing controller and player tests**

```python
def test_controller_build_request_keeps_local_absolute_subt_path(tmp_path) -> None:
    subtitle_path = tmp_path / "episode-1.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    controller = SpiderPluginController(
        SubtitlePayloadSpider(str(subtitle_path)),
        plugin_name="字幕插件",
        search_enabled=True,
        base_url_loader=lambda: "http://127.0.0.1:4567",
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]
    request.playback_loader(first)

    assert [(sub.url, sub.format, sub.source) for sub in first.external_subtitles] == [
        (str(subtitle_path), "application/x-subrip", "spider"),
    ]


def test_player_window_auto_loads_spider_subtitle_from_local_path(qtbot, monkeypatch, tmp_path) -> None:
    subtitle_path = tmp_path / "plugin.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")
    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("should not fetch local spider subtitle via http"),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="sp1", vod_name="插件视频"),
        playlist=[
            PlayItem(
                title="第1集",
                url="http://m/1.m3u8",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="外挂字幕 [插件]",
                        lang="",
                        url=str(subtitle_path),
                        format="application/x-subrip",
                        source="spider",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_keeps_local_absolute_subt_path tests/test_player_window_ui.py::test_player_window_auto_loads_spider_subtitle_from_local_path -v`

Expected: FAIL because the controller rewrites `/tmp/...` into a base-URL-relative HTTP path and the player still tries `httpx.get()` for local subtitle files.

- [ ] **Step 3: Write the minimal implementation**

```python
def _normalize_spider_subtitle_url(self, value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    local_path = Path(raw)
    if local_path.is_absolute() and local_path.exists():
        return raw
    if not raw.startswith("/"):
        return ""
    base_url = "" if self._base_url_loader is None else str(self._base_url_loader() or "").strip()
    if not base_url:
        return ""
    return urljoin(f"{base_url.rstrip('/')}/", raw.lstrip("/"))


def _fetch_external_subtitle_text(self, subtitle: ExternalSubtitleOption) -> str:
    subtitle_path = Path(subtitle.url)
    if subtitle_path.is_absolute() and subtitle_path.exists():
        return subtitle_path.read_text(encoding="utf-8")
    current_item = self._current_play_item()
    headers = {} if current_item is None else dict(current_item.headers)
    response = httpx.get(subtitle.url, headers=headers, timeout=10.0, follow_redirects=True)
    return str(getattr(response, "text", "") or "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_keeps_local_absolute_subt_path tests/test_player_window_ui.py::test_player_window_auto_loads_spider_subtitle_from_local_path -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_spider_plugin_controller.py tests/test_player_window_ui.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py
git commit -m "fix: preserve local spider subtitle paths"
```

### Task 2: Add mpv Audio-Cover Primitives

**Files:**
- Modify: `tests/test_mpv_widget.py:390-415`
- Modify: `src/atv_player/player/mpv_widget.py:84-127`
- Modify: `src/atv_player/player/mpv_widget.py:317-355`

- [ ] **Step 1: Write the failing mpv tests**

```python
def test_mpv_widget_disables_mpv_keyboard_bindings_for_embedded_player(qtbot, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMPV:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    widget = MpvWidget()
    qtbot.addWidget(widget)
    monkeypatch.setitem(sys.modules, "mpv", types.SimpleNamespace(MPV=FakeMPV))

    widget._create_player()

    assert captured["force_window"] == "yes"


def test_mpv_widget_load_accepts_audio_cover_image_path(qtbot) -> None:
    class FakePlayer:
        def __init__(self) -> None:
            self.pause = False

        def loadfile(self, url: str, **kwargs) -> None:
            return None

    widget = MpvWidget()
    qtbot.addWidget(widget)
    widget._player = FakePlayer()
    seen_calls: list[tuple[str, str, int]] = []
    widget._load_audio_with_cover = (
        lambda player, url, poster_image_path, start_seconds: seen_calls.append(
            (url, poster_image_path, start_seconds)
        )
    )

    widget.load("http://m/1.mp3", headers={}, poster_image_path="/tmp/cover.jpg", start_seconds=5)

    assert seen_calls == [("http://m/1.mp3", "/tmp/cover.jpg", 5)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mpv_widget.py::test_mpv_widget_disables_mpv_keyboard_bindings_for_embedded_player tests/test_mpv_widget.py::test_mpv_widget_load_accepts_audio_cover_image_path -v`

Expected: FAIL because `force_window` is missing and `load()` has no poster-image-aware path yet.

- [ ] **Step 3: Write the minimal implementation**

```python
def _create_player(self):
    import mpv

    common = dict(
        wid=str(int(self.winId())),
        hwdec="auto-safe",
        force_window="yes",
        audio_spdif="no",
        ad="ffmpeg",
        input_default_bindings=False,
        input_vo_keyboard=False,
        cache=True,
        cache_pause_initial=True,
        cache_pause_wait=3,
        demuxer_max_bytes="512M",
        demuxer_max_back_bytes="128M",
        demuxer_readahead_secs=20,
        stream_buffer_size="4M",
        network_timeout=15,
    )


def load(
    self,
    url: str,
    pause: bool = False,
    start_seconds: int = 0,
    headers: dict[str, str] | None = None,
    poster_image_path: str | None = None,
) -> None:
    self._set_video_picture_state("loading")
    self._ensure_player()
    player = self._player
    if player is None:
        return
    header_fields = self._build_http_header_fields(headers)
    self._apply_http_header_fields(player, header_fields)
    if poster_image_path:
        self._load_audio_with_cover(player, url, poster_image_path, start_seconds)
    elif start_seconds > 0 and hasattr(player, "loadfile"):
        player.loadfile(url, start=str(start_seconds), **self._loadfile_options(url))
    elif (header_fields or self._loadfile_options(url)) and hasattr(player, "loadfile"):
        player.loadfile(url, **self._loadfile_options(url))
    else:
        player.play(url)
    player.pause = pause


def _load_audio_with_cover(self, player: Any, url: str, poster_image_path: str, start_seconds: int) -> None:
    load_kwargs: dict[str, str] = {}
    if start_seconds > 0:
        load_kwargs["start"] = str(start_seconds)
    load_kwargs.update(self._loadfile_options(url))
    player.loadfile(url, **load_kwargs)
    self._set_player_property("image-display-duration", "inf")
    self._set_player_property("keep-open", "yes")
    self._player.command("video-add", poster_image_path, "auto")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mpv_widget.py::test_mpv_widget_disables_mpv_keyboard_bindings_for_embedded_player tests/test_mpv_widget.py::test_mpv_widget_load_accepts_audio_cover_image_path -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_mpv_widget.py src/atv_player/player/mpv_widget.py
git commit -m "feat: add mpv audio cover loading path"
```

### Task 3: Coordinate Audio-Only Cover Mode in PlayerWindow

**Files:**
- Modify: `tests/test_player_window_ui.py:1711-1770`
- Modify: `src/atv_player/ui/player_window.py:974-997`
- Modify: `src/atv_player/ui/player_window.py:1195-1234`

- [ ] **Step 1: Write the failing player-window tests**

```python
def test_player_window_hides_video_poster_overlay_when_picture_is_unavailable_but_primary_subtitle_is_active(qtbot) -> None:
    image = QImage(24, 36, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    session = PlayerSession(
        vod=VodItem(vod_id="sp1", vod_name="插件视频", vod_pic="https://img.example/poster.jpg"),
        playlist=[
            PlayItem(
                title="第1集",
                url="http://m/1.mp3",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="外挂字幕 [插件]",
                        lang="",
                        url="http://sub/1.srt",
                        format="application/x-subrip",
                        source="spider",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(session)
    window._primary_external_subtitle_selection = ExternalSubtitleSelection(source="spider", option_url="http://sub/1.srt")
    window._primary_external_subtitle_track_id = 91
    window._handle_poster_load_finished(window._poster_request_id, image)
    window._handle_video_picture_state_changed("unavailable")

    assert window.video_poster_overlay.isHidden() is True


def test_player_window_passes_preferred_poster_into_audio_only_load(qtbot) -> None:
    seen_calls: list[tuple[str, str | None]] = []

    class FakeVideo(RecordingVideo):
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers=None, poster_image_path=None) -> None:
            seen_calls.append((url, poster_image_path))

    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "/tmp/default-cover.png")
    qtbot.addWidget(window)
    window.video = FakeVideo()


def test_player_window_uses_default_cover_for_audio_only_load_when_vod_pic_is_missing(qtbot) -> None:
    seen_calls: list[tuple[str, str | None]] = []

    class FakeVideo(RecordingVideo):
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers=None, poster_image_path=None) -> None:
            seen_calls.append((url, poster_image_path))

    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "/tmp/default-cover.png")
    qtbot.addWidget(window)
    window.video = FakeVideo()

    assert seen_calls[-1][1] == "/tmp/default-cover.png"


def test_player_window_does_not_pass_poster_image_into_normal_video_load(qtbot) -> None:
    seen_calls: list[tuple[str, str | None]] = []

    class FakeVideo(RecordingVideo):
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers=None, poster_image_path=None) -> None:
            seen_calls.append((url, poster_image_path))

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return [SubtitleTrack(id=11, title="", lang="zh", is_default=True, is_forced=False, label="中文 (默认)")]

        def audio_tracks(self) -> list[AudioTrack]:
            return [AudioTrack(id=21, title="", lang="cmn", is_default=True, is_forced=False, label="普通话")]

    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "/tmp/default-cover.png")
    qtbot.addWidget(window)
    window.video = FakeVideo()

    assert seen_calls[-1][1] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_video_poster_overlay_when_picture_is_unavailable_but_primary_subtitle_is_active tests/test_player_window_ui.py::test_player_window_passes_preferred_poster_into_audio_only_load tests/test_player_window_ui.py::test_player_window_uses_default_cover_for_audio_only_load_when_vod_pic_is_missing tests/test_player_window_ui.py::test_player_window_does_not_pass_poster_image_into_normal_video_load -v`

Expected: FAIL because `PlayerWindow` neither passes a poster path into the audio-only load call nor suppresses the Qt overlay when subtitles are active on audio-only playback, and it has no explicit branch keeping normal video loads out of audio-cover mode.

- [ ] **Step 3: Write the minimal implementation**

```python
def _poster_image_path_for_audio_cover(self) -> str | None:
    current_item = self._current_play_item()
    if current_item is None:
        return None
    if not current_item.url.lower().endswith((".mp3", ".flac", ".aac", ".m4a", ".ogg", ".wav")):
        return None
    poster_source = self._preferred_poster_source()
    if not poster_source:
        return None
    poster_path = Path(poster_source)
    if poster_path.is_file():
        return str(poster_path)
    return self._cached_audio_cover_path(poster_source)


def _cached_audio_cover_path(self, source: str) -> str | None:
    image = load_remote_poster_image(
        normalize_poster_url(source),
        self._POSTER_SIZE,
        timeout=self._POSTER_REQUEST_TIMEOUT_SECONDS,
        get=httpx.get,
    )
    if image is None or image.isNull():
        return None
    target = Path(tempfile.NamedTemporaryFile(suffix=".png", delete=False).name)
    image.save(str(target))
    return str(target)


def _start_current_item_playback(self, start_position_seconds: int = 0, pause: bool = False) -> None:
    if self.session is None:
        return
    current_item = self.session.playlist[self.current_index]
    poster_path = self._poster_image_path_for_audio_cover()
    self._video_load(
        current_item.url,
        pause=pause,
        start_seconds=effective_start_seconds,
        headers=current_item.headers,
        poster_image_path=poster_path,
    )


def _handle_video_picture_state_changed(self, state: str) -> None:
    self._video_picture_state = state
    if state == "visible":
        self._video_surface_ready = True
        self.video_poster_overlay.hide()
        return
    self._video_surface_ready = False
    if state == "unavailable" and self._has_active_primary_external_subtitle():
        self.video_poster_overlay.hide()
        return
    pixmap = self.poster_label.pixmap()
    if pixmap is not None and not pixmap.isNull():
        self._show_video_poster_overlay(pixmap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_video_poster_overlay_when_picture_is_unavailable_but_primary_subtitle_is_active tests/test_player_window_ui.py::test_player_window_passes_preferred_poster_into_audio_only_load tests/test_player_window_ui.py::test_player_window_uses_default_cover_for_audio_only_load_when_vod_pic_is_missing tests/test_player_window_ui.py::test_player_window_does_not_pass_poster_image_into_normal_video_load -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: route audio-only playback through cover mode"
```

### Task 4: Regressions and Verification

**Files:**
- Test: `tests/test_mpv_widget.py`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run focused subtitle and audio-cover regressions**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "subt or subtitle" -v`

Expected: PASS for absolute, relative, and local spider subtitle path mapping.

- [ ] **Step 2: Run focused player-window regressions**

Run: `uv run pytest tests/test_player_window_ui.py -k "subtitle and (spider or bilibili or external or manual_subtitle_switch or secondary_subtitle or local_path)" -v`

Expected: PASS for spider auto subtitle, local subtitle files, and manual subtitle switching.

- [ ] **Step 3: Run touched-module full verification**

Run: `uv run pytest tests/test_mpv_widget.py -v`

Expected: PASS

Run: `uv run pytest tests/test_spider_plugin_controller.py -v`

Expected: PASS

Run: `uv run pytest tests/test_player_window_ui.py -v`

Expected: PASS

- [ ] **Step 4: Review git diff before completion**

Run: `git diff -- src/atv_player/player/mpv_widget.py src/atv_player/ui/player_window.py src/atv_player/plugins/controller.py tests/test_mpv_widget.py tests/test_player_window_ui.py tests/test_spider_plugin_controller.py`

Expected: Only audio-cover/static-video and local spider subtitle path changes are present.

- [ ] **Step 5: Commit the final verification checkpoint**

```bash
git add src/atv_player/player/mpv_widget.py src/atv_player/ui/player_window.py src/atv_player/plugins/controller.py tests/test_mpv_widget.py tests/test_player_window_ui.py tests/test_spider_plugin_controller.py
git commit -m "test: verify audio cover static video regressions"
```
