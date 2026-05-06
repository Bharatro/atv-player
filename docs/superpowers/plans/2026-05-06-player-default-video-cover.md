# Player Default Video Cover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a poster overlay in the player whenever visible video is not available, preferring the current item's `vod_pic` and falling back to the backend `video_cover` setting.

**Architecture:** Add a small backend-setting accessor in `ApiClient`, thread that loader through `AppCoordinator` and `MainWindow`, and let `PlayerWindow` lazily cache the fallback URL. Replace the current progress-based overlay heuristic with explicit picture-state signals from `MpvWidget`, so the window can distinguish loading, visible-video, no-video, and playback-failure states.

**Tech Stack:** Python, PySide6, httpx, pytest, pytest-qt

---

### Task 1: Add backend access for the global `video_cover` setting

**Files:**
- Modify: `src/atv_player/api.py`
- Modify: `tests/test_api_client.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_api_client_gets_video_cover_setting() -> None:
    seen = {"path": "", "query": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"name": "video_cover", "value": "https://img.example/cover.jpg"})

    client = ApiClient(
        base_url="http://127.0.0.1:4567",
        token="auth-123",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_video_cover() == "https://img.example/cover.jpg"
    assert seen == {"path": "/api/settings/video_cover", "query": ""}


def test_api_client_get_video_cover_returns_empty_string_for_missing_value() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "video_cover", "value": None})

    client = ApiClient(
        base_url="http://127.0.0.1:4567",
        token="auth-123",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_video_cover() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_client.py::test_api_client_gets_video_cover_setting tests/test_api_client.py::test_api_client_get_video_cover_returns_empty_string_for_missing_value -q`
Expected: FAIL with `AttributeError: 'ApiClient' object has no attribute 'get_video_cover'`.

- [ ] **Step 3: Write minimal implementation**

```python
def get_video_cover(self) -> str:
    data = self._request("GET", "/api/settings/video_cover")
    if not isinstance(data, dict):
        return ""
    return str(data.get("value") or "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_client.py::test_api_client_gets_video_cover_setting tests/test_api_client.py::test_api_client_get_video_cover_returns_empty_string_for_missing_value -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/api.py tests/test_api_client.py
git commit -m "feat: add api client video cover setting lookup"
```

### Task 2: Wire the fallback-cover loader into `MainWindow` player creation

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_window_passes_default_video_cover_loader_to_player_window(qtbot, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            captured["loader"] = kwargs.get("default_video_cover_loader")
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)

    def load_video_cover() -> str:
        return "https://img.example/fallback.jpg"

    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        default_video_cover_loader=load_video_cover,
    )
    qtbot.addWidget(window)

    request = OpenPlayerRequest(
        vod=VodItem(vod_id="vod-1", vod_name="Movie"),
        playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
        clicked_index=0,
    )
    window.open_player(request)

    qtbot.waitUntil(lambda: "loader" in captured)
    assert captured["loader"] is load_video_cover
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main_window_ui.py::test_main_window_passes_default_video_cover_loader_to_player_window -q`
Expected: FAIL because `MainWindow.__init__()` does not accept `default_video_cover_loader`, or because `_apply_open_player()` does not forward it.

- [ ] **Step 3: Write minimal implementation**

```python
class MainWindow(QMainWindow, AsyncGuardMixin):
    def __init__(
        self,
        browse_controller,
        history_controller,
        player_controller,
        config,
        save_config=None,
        douban_controller=None,
        telegram_controller=None,
        bilibili_controller=None,
        live_controller=None,
        live_source_manager=None,
        emby_controller=None,
        jellyfin_controller=None,
        feiniu_controller=None,
        pansou_controller=None,
        spider_plugins=None,
        plugin_manager=None,
        drive_detail_loader=None,
        direct_parse_detail_loader=None,
        direct_parse_danmaku_loader=None,
        direct_parse_playback_history_loader=None,
        direct_parse_playback_history_saver=None,
        default_video_cover_loader=None,
        show_bilibili_tab: bool = False,
        show_emby_tab: bool = True,
        show_jellyfin_tab: bool = True,
        show_feiniu_tab: bool = True,
        m3u8_ad_filter=None,
        playback_parser_service=None,
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self._default_video_cover_loader = default_video_cover_loader

    def _apply_open_player(self, request, session, restore_paused_state: bool = False) -> None:
        if self.player_window is None:
            self.player_window = PlayerWindow(
                self.player_controller,
                self.config,
                self._save_config,
                m3u8_ad_filter=self._m3u8_ad_filter,
                playback_parser_service=self._playback_parser_service,
                default_video_cover_loader=self._default_video_cover_loader,
            )
```

```python
def _show_main(self):
    self.main_window = MainWindow(
        browse_controller=browse_controller,
        history_controller=history_controller,
        player_controller=player_controller,
        config=config,
        save_config=lambda: self.repo.save_config(config),
        douban_controller=douban_controller,
        telegram_controller=telegram_controller,
        bilibili_controller=bilibili_controller,
        live_controller=live_controller,
        live_source_manager=live_source_manager,
        emby_controller=emby_controller,
        jellyfin_controller=jellyfin_controller,
        feiniu_controller=feiniu_controller,
        pansou_controller=pansou_controller,
        spider_plugins=spider_plugins,
        plugin_manager=self._plugin_manager,
        drive_detail_loader=drive_detail_loader,
        direct_parse_detail_loader=load_direct_parse_detail,
        direct_parse_danmaku_loader=load_direct_parse_danmaku,
        direct_parse_playback_history_loader=None
        if self._playback_history_repository is None
        else lambda vod_id: self._playback_history_repository.get_history("direct_parse", vod_id),
        direct_parse_playback_history_saver=None
        if self._playback_history_repository is None
        else lambda vod_id, payload: self._playback_history_repository.save_history(
            "direct_parse",
            vod_id,
            payload,
            source_name="全局解析",
        ),
        default_video_cover_loader=getattr(self._api_client, "get_video_cover", None),
        show_bilibili_tab=bool(capabilities.get("bilibili")),
        show_emby_tab=bool(capabilities.get("emby")),
        show_jellyfin_tab=bool(capabilities.get("jellyfin")),
        show_feiniu_tab=bool(capabilities.get("feiniu")),
        m3u8_ad_filter=self._m3u8_ad_filter,
        playback_parser_service=self._playback_parser_service,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main_window_ui.py::test_main_window_passes_default_video_cover_loader_to_player_window -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: wire player video cover fallback loader"
```

### Task 3: Add `PlayerWindow` fallback poster resolution and lazy caching

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_prefers_session_poster_before_default_video_cover(qtbot, tmp_path) -> None:
    session_poster = tmp_path / "session.png"
    pixmap = QPixmap(24, 36)
    pixmap.fill(QColor("red"))
    assert pixmap.save(str(session_poster)) is True

    loader_calls: list[str] = []
    window = PlayerWindow(
        FakePlayerController(),
        default_video_cover_loader=lambda: loader_calls.append("called") or "https://img.example/fallback.jpg",
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic=str(session_poster)),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )

    assert loader_calls == []
    assert window.poster_label.pixmap() is not None
    assert window.poster_label.pixmap().isNull() is False


def test_player_window_uses_default_video_cover_when_session_poster_is_empty(qtbot, monkeypatch) -> None:
    started: list[str] = []

    def fake_start(self, source: str, request_id: int) -> None:
        started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    window = PlayerWindow(
        FakePlayerController(),
        default_video_cover_loader=lambda: "https://img.example/fallback.jpg",
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic=""),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )

    assert started == ["https://img.example/fallback.jpg"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_prefers_session_poster_before_default_video_cover tests/test_player_window_ui.py::test_player_window_uses_default_video_cover_when_session_poster_is_empty -q`
Expected: FAIL because `PlayerWindow` has no fallback-cover loader and `_render_poster()` only checks `session.vod.vod_pic`.

- [ ] **Step 3: Write minimal implementation**

```python
class PlayerWindow(QWidget, AsyncGuardMixin):
    def __init__(
        self,
        controller,
        config=None,
        save_config=None,
        m3u8_ad_filter=None,
        playback_parser_service=None,
        default_video_cover_loader=None,
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self._default_video_cover_loader = default_video_cover_loader
        self._default_video_cover_source: str | None = None

    def _resolve_default_video_cover_source(self) -> str:
        if self._default_video_cover_source is not None:
            return self._default_video_cover_source
        loader = self._default_video_cover_loader
        if not callable(loader):
            self._default_video_cover_source = ""
            return ""
        try:
            self._default_video_cover_source = str(loader() or "")
        except Exception:
            self._default_video_cover_source = ""
        return self._default_video_cover_source

    def _preferred_poster_source(self) -> str:
        if self.session is None:
            return ""
        if self.session.vod.vod_pic:
            return self.session.vod.vod_pic
        return self._resolve_default_video_cover_source()
```

```python
def _render_poster(self) -> None:
    self._poster_request_id += 1
    self._video_surface_ready = False
    source = self._preferred_poster_source()
    if not source:
        self._clear_poster()
        return
    pixmap = self._load_poster_pixmap(source)
    if not pixmap.isNull():
        self.poster_label.setText("")
        self.poster_label.setPixmap(pixmap)
        self._show_video_poster_overlay(pixmap)
        return
    self._clear_poster()
    self._start_poster_load(source, self._poster_request_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_prefers_session_poster_before_default_video_cover tests/test_player_window_ui.py::test_player_window_uses_default_video_cover_when_session_poster_is_empty -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player poster fallback source resolution"
```

### Task 4: Expose explicit picture-state signals from `MpvWidget`

**Files:**
- Modify: `src/atv_player/player/mpv_widget.py`
- Modify: `tests/test_mpv_widget.py`
- Test: `tests/test_mpv_widget.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mpv_widget_emits_loading_and_visible_picture_states(qtbot) -> None:
    widget = MpvWidget()
    qtbot.addWidget(widget)

    class FakePlayer:
        def __init__(self) -> None:
            self.pause = False
            self._track_list_observer = None
            self._video_out_observer = None

        def event_callback(self, *event_types):
            def register(callback):
                return callback
            return register

        def observe_property(self, name: str, handler) -> None:
            if name == "track-list":
                self._track_list_observer = handler
            elif name == "video-out-params":
                self._video_out_observer = handler

        def play(self, url: str) -> None:
            return None

    widget._player = FakePlayer()
    widget._register_player_events()
    states: list[str] = []
    widget.video_picture_state_changed.connect(states.append)

    widget.load("http://m/1.m3u8")
    widget._player._video_out_observer("video-out-params", {"w": 1920, "h": 1080})

    assert states == ["loading", "visible"]


def test_mpv_widget_emits_unavailable_picture_state_when_track_list_has_no_video(qtbot) -> None:
    widget = MpvWidget()
    qtbot.addWidget(widget)

    class FakePlayer:
        def __init__(self) -> None:
            self.pause = False
            self._track_list_observer = None
            self._video_out_observer = None

        def event_callback(self, *event_types):
            def register(callback):
                return callback
            return register

        def observe_property(self, name: str, handler) -> None:
            if name == "track-list":
                self._track_list_observer = handler
            elif name == "video-out-params":
                self._video_out_observer = handler

        def play(self, url: str) -> None:
            return None

    widget._player = FakePlayer()
    widget._register_player_events()
    states: list[str] = []
    widget.video_picture_state_changed.connect(states.append)

    widget.load("http://m/1.m3u8")
    widget._player._track_list_observer("track-list", [{"id": 2, "type": "audio"}])
    assert states[-1] == "unavailable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mpv_widget.py::test_mpv_widget_emits_loading_and_visible_picture_states tests/test_mpv_widget.py::test_mpv_widget_emits_unavailable_picture_state_when_track_list_has_no_video -q`
Expected: FAIL because `MpvWidget` does not expose a picture-state signal and does not observe `video-out-params`.

- [ ] **Step 3: Write minimal implementation**

```python
class MpvWidget(QWidget):
    video_picture_state_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._player: Any | None = None
        self._video_picture_state = "idle"

    def _set_video_picture_state(self, state: str) -> None:
        if self._video_picture_state == state:
            return
        self._video_picture_state = state
        self.video_picture_state_changed.emit(state)
```

```python
def _register_player_events(self) -> None:
    def handle_track_list(_property_name, tracks) -> None:
        self.subtitle_tracks_changed.emit()
        self.audio_tracks_changed.emit()
        normalized = tracks or []
        has_video_track = any(isinstance(track, dict) and track.get("type") == "video" for track in normalized)
        if not has_video_track:
            self._set_video_picture_state("unavailable")

    def handle_video_out_params(_property_name, params) -> None:
        if params:
            self._set_video_picture_state("visible")

    observe_property("track-list", handle_track_list)
    observe_property("video-out-params", handle_video_out_params)
```

```python
def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
    self._set_video_picture_state("loading")
    self._ensure_player()
    player = self._player
    if player is None:
        return
    header_fields = self._build_http_header_fields(headers)
    loadfile_options = self._loadfile_options(url)
    can_loadfile = hasattr(player, "loadfile")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mpv_widget.py::test_mpv_widget_emits_loading_and_visible_picture_states tests/test_mpv_widget.py::test_mpv_widget_emits_unavailable_picture_state_when_track_list_has_no_video -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/mpv_widget.py tests/test_mpv_widget.py
git commit -m "feat: add mpv video picture state signals"
```

### Task 5: Drive the player overlay from picture state and playback failure

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_hides_video_poster_overlay_after_visible_picture_signal(qtbot) -> None:
    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    image = QImage(24, 36, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/poster.jpg"),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )
    window._handle_poster_load_finished(window._poster_request_id, image)
    window._handle_video_picture_state_changed("loading")
    assert window.video_poster_overlay.isHidden() is False

    window._handle_video_picture_state_changed("visible")
    assert window.video_poster_overlay.isHidden() is True


def test_player_window_shows_video_poster_overlay_again_after_playback_failure(qtbot) -> None:
    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    image = QImage(24, 36, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/poster.jpg"),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )
    window._handle_poster_load_finished(window._poster_request_id, image)
    window._handle_video_picture_state_changed("visible")
    assert window.video_poster_overlay.isHidden() is True

    window._handle_playback_failed("播放失败: HTTP 403 Forbidden")
    assert window.video_poster_overlay.isHidden() is False
    assert "播放失败: HTTP 403 Forbidden" in window.log_view.toPlainText()


def test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable(qtbot) -> None:
    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    image = QImage(24, 36, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/poster.jpg"),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )
    window._handle_poster_load_finished(window._poster_request_id, image)
    window._handle_video_picture_state_changed("unavailable")
    assert window.video_poster_overlay.isHidden() is False
    assert "当前媒体没有可用视频画面，已显示封面" in window.log_view.toPlainText()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_video_poster_overlay_after_visible_picture_signal tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_again_after_playback_failure tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable -q`
Expected: FAIL because the overlay is still driven by `_sync_progress_slider()` and playback failure only appends logs.

- [ ] **Step 3: Write minimal implementation**

```python
class PlayerWindow(QWidget, AsyncGuardMixin):
    def __init__(
        self,
        controller,
        config=None,
        save_config=None,
        m3u8_ad_filter=None,
        playback_parser_service=None,
        default_video_cover_loader=None,
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self._video_picture_state = "idle"
        self.video_widget.video_picture_state_changed.connect(self._handle_video_picture_state_changed)
        self.video_widget.playback_failed.connect(self._handle_playback_failed)
```

```python
def _handle_video_picture_state_changed(self, state: str) -> None:
    self._video_picture_state = state
    if state == "visible":
        self._video_surface_ready = True
        self.video_poster_overlay.hide()
        return
    self._video_surface_ready = False
    pixmap = self.poster_label.pixmap()
    if pixmap is not None and not pixmap.isNull():
        self._show_video_poster_overlay(pixmap)
    if state == "unavailable":
        self._append_log("当前媒体没有可用视频画面，已显示封面")


def _handle_playback_failed(self, message: str) -> None:
    self._append_log(message)
    self._handle_video_picture_state_changed("unavailable")
```

```python
def open_session(self, session, start_paused: bool = False) -> None:
    self._invalidate_play_item_resolution()
    if not session.playlists:
        session.playlists = [session.playlist]
        session.playlist_index = 0
    self.session = session
    self._render_poster()
    self._render_metadata()
    self._reset_log()
    self._handle_video_picture_state_changed("loading")
```

```python
def _sync_progress_slider(self) -> None:
    if self._slider_dragging:
        return
    duration = self.video.duration_seconds() if hasattr(self.video, "duration_seconds") else 0
    position = self.video.position_seconds() or 0
    if (
        not self._auto_advance_locked
        and self.session is not None
        and self.current_index + 1 < len(self.session.playlist)
        and duration > self.opening_spin.value() + self.ending_spin.value()
        and position < duration
        and position + self.ending_spin.value() >= duration
    ):
        self._auto_advance_locked = True
        self.play_next()
        return
    self.progress.setMaximum(max(duration, 0))
    self.progress.setValue(max(min(position, self.progress.maximum()), 0))
    self.current_time_label.setText(self._format_time(position))
    self.duration_label.setText(self._format_time(duration))
```

Remove the old `if duration > 0 or position > 0: self._video_surface_ready = True; self.video_poster_overlay.hide()` block so progress no longer controls overlay visibility.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_video_poster_overlay_after_visible_picture_signal tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_again_after_playback_failure tests/test_player_window_ui.py::test_player_window_shows_video_poster_overlay_when_picture_becomes_unavailable -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: drive player poster overlay from picture state"
```

### Task 6: Run focused and broad verification for the full flow

**Files:**
- Modify: `tests/test_api_client.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_mpv_widget.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_api_client.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_mpv_widget.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run focused verification**

Run: `uv run pytest tests/test_api_client.py tests/test_main_window_ui.py tests/test_mpv_widget.py tests/test_player_window_ui.py -k "video_cover or poster_overlay or picture_state" -q`
Expected: PASS for the new regression coverage around fallback poster lookup and overlay state.

- [ ] **Step 2: Run broader verification**

Run: `uv run pytest tests/test_api_client.py tests/test_main_window_ui.py tests/test_mpv_widget.py tests/test_player_window_ui.py -q`
Expected: PASS, or a clearly documented unrelated pre-existing failure with exact output captured before stopping.

- [ ] **Step 3: Commit**

```bash
git add src/atv_player/api.py src/atv_player/app.py src/atv_player/player/mpv_widget.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py tests/test_api_client.py tests/test_main_window_ui.py tests/test_mpv_widget.py tests/test_player_window_ui.py docs/superpowers/specs/2026-05-06-player-default-video-cover-design.md docs/superpowers/plans/2026-05-06-player-default-video-cover.md
git commit -m "feat: show fallback poster when player has no video picture"
```

## Spec Coverage Check

- Backend `video_cover` access is covered by Task 1.
- Loader wiring and reuse of the existing player window are covered by Task 2.
- Poster priority and lazy fallback caching are covered by Task 3.
- Explicit picture-state signaling from `MpvWidget` is covered by Task 4.
- `loading`, `visible`, `no video`, and `playback failed` overlay behavior is covered by Task 5.
- Focused and broad regression verification is covered by Task 6.

## Placeholder Scan

- No `TODO`, `TBD`, or "similar to Task N" placeholders remain.
- Every code-changing task includes a concrete test command, implementation sketch, and commit command.
- The new public names used across tasks are consistent: `get_video_cover`, `default_video_cover_loader`, and `video_picture_state_changed`.

## Type Consistency Check

- `ApiClient.get_video_cover()` returns `str` in every task.
- `MainWindow` passes `default_video_cover_loader` through to `PlayerWindow` consistently.
- `MpvWidget` emits `video_picture_state_changed` with string states, and `PlayerWindow` consumes the same states without renaming.
