# Spider Plugin `playerContent().cover` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let spider-plugin `playerContent().cover` replace only the player's video poster while leaving the detail poster and saved history poster unchanged.

**Architecture:** Add a session-only `video_cover_override` field on `PlayerSession`, and bind playback loaders so spider-plugin playback resolution can update that field without mutating `session.vod.vod_pic`. In `PlayerWindow`, split detail-poster rendering from video-poster rendering so the sidebar poster always follows `vod_pic`, while the video overlay prefers `video_cover_override`, then falls back to `vod_pic`, then the default video cover.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### File Structure

**Files and responsibilities:**

- `src/atv_player/models.py`
  Holds `OpenPlayerRequest`; widen the `playback_loader` callable type so request loaders may be either item-only or session-aware.

- `src/atv_player/controllers/player_controller.py`
  Owns `PlayerSession`, creates sessions, and reports history. This is where the new `video_cover_override` state should live and where session-aware playback loaders should be bound.

- `src/atv_player/plugins/controller.py`
  Resolves spider playback payloads. This is where `playerContent().cover` should update only the session video-poster override.

- `src/atv_player/ui/player_window.py`
  Renders the sidebar detail poster and the video overlay poster. This file needs the render split and separate remote-poster load targets.

- `tests/test_player_controller.py`
  Verifies session state creation, playback-loader binding, and history payload behavior.

- `tests/test_spider_plugin_controller.py`
  Verifies spider playback `cover` updates only the session video poster state.

- `tests/test_player_window_ui.py`
  Verifies video-poster override precedence, async refresh behavior, and detail-poster stability.

### Task 1: Add session-only video-poster override state and session-aware playback-loader binding

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `tests/test_player_controller.py`
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_controller_create_session_defaults_video_cover_override_to_empty() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="poster-detail")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=0)

    assert session.video_cover_override == ""


def test_player_controller_binds_session_aware_playback_loader_without_changing_history_poster() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-detail")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="/play/1")]

    def load_item(session, item: PlayItem) -> None:
        session.video_cover_override = "https://img.example/video-cover.jpg"
        item.url = "http://m/1.m3u8"
        return None

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        playback_loader=load_item,
        use_local_history=False,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=30,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        force_remote_report=True,
    )

    assert session.video_cover_override == "https://img.example/video-cover.jpg"
    assert session.vod.vod_pic == "poster-detail"
    assert api.saved_payloads[0]["vodPic"] == "poster-detail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_create_session_defaults_video_cover_override_to_empty tests/test_player_controller.py::test_player_controller_binds_session_aware_playback_loader_without_changing_history_poster -q`
Expected: FAIL with `AttributeError` for missing `video_cover_override`, or `TypeError` because `session.playback_loader(session.playlist[0])` cannot bind a two-argument loader.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class PlayerSession:
    vod: VodItem
    playlist: list[PlayItem]
    start_index: int
    start_position_seconds: int
    speed: float
    playlists: list[list[PlayItem]] = field(default_factory=list)
    playlist_index: int = 0
    opening_seconds: int = 0
    ending_seconds: int = 0
    detail_resolver: Callable[[PlayItem], VodItem | None] | None = None
    resolved_vod_by_id: dict[str, VodItem] = field(default_factory=dict)
    use_local_history: bool = True
    playback_loader: Callable[[PlayItem], PlaybackLoadResult | None] | None = None
    async_playback_loader: bool = False
    danmaku_controller: object | None = None
    playback_progress_reporter: Callable[[PlayItem, int, bool], None] | None = None
    playback_stopper: Callable[[PlayItem], None] | None = None
    playback_history_saver: Callable[[dict[str, object]], None] | None = None
    initial_log_message: str = ""
    is_placeholder: bool = False
    video_cover_override: str = ""
```

```python
def _bind_playback_loader(
    self,
    playback_loader: Callable[..., PlaybackLoadResult | None] | None,
    session: PlayerSession,
) -> Callable[[PlayItem], PlaybackLoadResult | None] | None:
    if playback_loader is None:
        return None
    parameters = list(inspect.signature(playback_loader).parameters.values())
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
    if has_varargs or len(positional) >= 2:
        return lambda item, playback_loader=playback_loader, session=session: playback_loader(session, item)
    return cast(Callable[[PlayItem], PlaybackLoadResult | None], playback_loader)
```

```python
session = PlayerSession(
    vod=vod,
    playlist=active_playlist,
    start_index=start_index,
    start_position_seconds=position_seconds,
    speed=speed,
    playlists=normalized_playlists,
    playlist_index=playlist_index,
    opening_seconds=int((history.opening if history else 0) / 1000),
    ending_seconds=int((history.ending if history else 0) / 1000),
    detail_resolver=detail_resolver,
    resolved_vod_by_id=dict(resolved_vod_by_id or {}),
    use_local_history=use_local_history,
    async_playback_loader=async_playback_loader,
    danmaku_controller=danmaku_controller,
    playback_progress_reporter=playback_progress_reporter,
    playback_stopper=playback_stopper,
    playback_history_saver=playback_history_saver,
    initial_log_message=initial_log_message,
    is_placeholder=is_placeholder,
)
session.playback_loader = self._bind_playback_loader(playback_loader, session)
return session
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_create_session_defaults_video_cover_override_to_empty tests/test_player_controller.py::test_player_controller_binds_session_aware_playback_loader_without_changing_history_poster -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat: add session video cover override state"
```

### Task 2: Update spider-plugin playback resolution to write only the session video-poster override

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.controllers.player_controller import PlayerController
```

```python
class _SessionApiClient:
    def get_history(self, key: str):
        return None

    def save_history(self, payload: dict) -> None:
        return None


def test_controller_updates_session_video_cover_override_from_player_content_cover() -> None:
    controller = SpiderPluginController(CoverPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("/detail/1")
    session = PlayerController(_SessionApiClient()).create_session(
        request.vod,
        request.playlist,
        request.clicked_index,
        playlists=request.playlists,
        playlist_index=request.playlist_index,
        playback_loader=request.playback_loader,
        async_playback_loader=request.async_playback_loader,
        use_local_history=False,
    )
    first = session.playlist[0]

    assert session.video_cover_override == ""
    assert request.vod.vod_pic == "poster-detail"
    assert session.playback_loader is not None

    session.playback_loader(first)

    assert session.video_cover_override == "https://img.example/resolved-cover.jpg"
    assert request.vod.vod_pic == "poster-detail"
    assert first.url == "https://stream.example/play/1.m3u8"


def test_controller_keeps_video_cover_override_empty_when_player_content_cover_is_blank() -> None:
    controller = SpiderPluginController(BlankCoverPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("/detail/1")
    session = PlayerController(_SessionApiClient()).create_session(
        request.vod,
        request.playlist,
        request.clicked_index,
        playlists=request.playlists,
        playlist_index=request.playlist_index,
        playback_loader=request.playback_loader,
        async_playback_loader=request.async_playback_loader,
        use_local_history=False,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])

    assert session.video_cover_override == ""
    assert request.vod.vod_pic == "poster-detail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_updates_session_video_cover_override_from_player_content_cover tests/test_spider_plugin_controller.py::test_controller_keeps_video_cover_override_empty_when_player_content_cover_is_blank -q`
Expected: FAIL because the spider playback loader still mutates `request.vod.vod_pic`, and `session.video_cover_override` either does not exist or remains empty.

- [ ] **Step 3: Write minimal implementation**

```python
from atv_player.controllers.player_controller import PlayerSession
```

```python
def _resolve_play_item(self, session: PlayerSession, item: PlayItem) -> PlaybackLoadResult | None:
    if item.url:
        if not item.danmaku_xml:
            self._maybe_resolve_danmaku(item, item.url)
        return
    item.external_subtitles = []
    item.playback_qualities = []
    item.selected_playback_quality_id = ""
    if not item.vod_id:
        return
    try:
        payload = self._spider.playerContent(item.play_source, item.vod_id, []) or {}
    except Exception as exc:
        logger.exception(
            "Spider plugin playback resolve failed plugin=%s source=%s",
            self._plugin_name,
            item.vod_id,
        )
        raise ValueError(str(exc)) from exc
    cover_source = str(payload.get("cover") or "").strip()
    if cover_source:
        session.video_cover_override = cover_source
```

```python
if _looks_like_drive_share_link(url):
    ...
    return PlaybackLoadResult(
        replacement_playlist=replacement,
        replacement_start_index=replacement_start_index,
    )
if parse_required:
    ...
    if cover_source:
        session.video_cover_override = cover_source
    self._maybe_resolve_danmaku(item, url)
    return None
...
item.external_subtitles = self._map_spider_external_subtitles(payload.get("subt"))
if cover_source:
    session.video_cover_override = cover_source
self._maybe_resolve_danmaku(item, url)
```

```python
def playback_loader(session: PlayerSession, item: PlayItem) -> PlaybackLoadResult | None:
    return self._resolve_play_item(session, item)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_updates_session_video_cover_override_from_player_content_cover tests/test_spider_plugin_controller.py::test_controller_keeps_video_cover_override_empty_when_player_content_cover_is_blank -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: map spider cover to session video override"
```

### Task 3: Split detail-poster and video-poster rendering in `PlayerWindow`

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_prefers_video_cover_override_before_session_poster_and_default_video_cover(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []
    video_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str) -> None:
        if target == "detail":
            detail_started.append(source)
        else:
            video_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/detail.jpg"),
        playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        video_cover_override="https://img.example/video.jpg",
    )
    window = PlayerWindow(
        FakePlayerController(),
        default_video_cover_loader=lambda: "https://img.example/fallback.jpg",
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert detail_started == ["https://img.example/detail.jpg"]
    assert video_started == ["https://img.example/video.jpg"]
```

```python
def test_player_window_refreshes_only_video_poster_after_async_playback_loader_updates_cover_override(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []
    video_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str) -> None:
        if target == "detail":
            detail_started.append(source)
        else:
            video_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers=None) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def audio_tracks(self) -> list[AudioTrack]:
            return []

        def supports_secondary_subtitle_ass_override(self) -> bool:
            return False

        def supports_subtitle_ass_override(self) -> bool:
            return False

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return track_id

        def supports_secondary_subtitle_position(self) -> bool:
            return False

        def position_seconds(self) -> int:
            return 0

    session = PlayerSession(
        vod=VodItem(vod_id="plugin-vod-1", vod_name="占位电影", vod_pic="https://img.example/detail.jpg"),
        playlist=[PlayItem(title="第1集", url="", vod_id="/play/1", play_source="备用线")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        async_playback_loader=True,
    )

    def playback_loader(current_session: PlayerSession, item: PlayItem) -> None:
        current_session.video_cover_override = "https://img.example/video.jpg"
        item.url = "http://m/1.m3u8"
        return None

    session.playback_loader = lambda item, session=session: playback_loader(session, item)

    window = PlayerWindow(FakePlayerController(), default_video_cover_loader=lambda: "")
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    qtbot.waitUntil(
        lambda: detail_started == ["https://img.example/detail.jpg"]
        and video_started == [
            "https://img.example/detail.jpg",
            "https://img.example/video.jpg",
        ]
    )
    assert session.vod.vod_pic == "https://img.example/detail.jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_prefers_video_cover_override_before_session_poster_and_default_video_cover tests/test_player_window_ui.py::test_player_window_refreshes_only_video_poster_after_async_playback_loader_updates_cover_override -q`
Expected: FAIL because `PlayerWindow` still renders one shared poster source through one shared async load path.

- [ ] **Step 3: Write minimal implementation**

```python
class _PosterLoadSignals(QObject):
    loaded = Signal(int, object)
```

```python
self._detail_poster_request_id = 0
self._video_poster_request_id = 0
self._poster_load_targets: dict[int, Callable[[QImage | None], None]] = {}
```

```python
def _preferred_detail_poster_source(self) -> str:
    if self.session is None:
        return ""
    return self.session.vod.vod_pic or ""


def _preferred_video_poster_source(self) -> str:
    if self.session is None:
        return ""
    if self.session.video_cover_override:
        return self.session.video_cover_override
    if self.session.vod.vod_pic:
        return self.session.vod.vod_pic
    return self._resolve_default_video_cover_source()
```

```python
def _start_poster_load(
    self,
    source: str,
    request_id: int,
    *,
    target: str,
    on_loaded: Callable[[QImage | None], None],
) -> None:
    image_url = normalize_poster_url(source)
    if not image_url:
        return
    self._poster_load_targets[request_id] = on_loaded

    def load() -> None:
        image = load_remote_poster_image(
            image_url,
            self._POSTER_SIZE,
            timeout=self._POSTER_REQUEST_TIMEOUT_SECONDS,
            get=httpx.get,
        )
        if self._is_window_alive():
            self._poster_load_signals.loaded.emit(request_id, image)

    threading.Thread(target=load, daemon=True).start()


def _handle_poster_load_finished(self, request_id: int, image: QImage | None) -> None:
    callback = self._poster_load_targets.pop(request_id, None)
    if callback is None:
        return
    callback(image)
```

```python
def _render_detail_poster(self) -> None:
    self._detail_poster_request_id += 1
    if self.session is None:
        self.poster_label.clear()
        self.poster_label.setText("")
        self.poster_label.setPixmap(QPixmap())
        return
    source = self._preferred_detail_poster_source()
    if not source:
        self.poster_label.clear()
        self.poster_label.setText("")
        self.poster_label.setPixmap(QPixmap())
        return
    pixmap = self._load_poster_pixmap(source)
    if not pixmap.isNull():
        self.poster_label.setText("")
        self.poster_label.setPixmap(pixmap)
        return
    self.poster_label.clear()
    self.poster_label.setText("")
    self.poster_label.setPixmap(QPixmap())
    request_id = self._detail_poster_request_id
    self._start_poster_load(
        source,
        request_id,
        target="detail",
        on_loaded=lambda image, request_id=request_id: self._apply_detail_poster_image(request_id, image),
    )
```

```python
def _render_video_poster(self) -> None:
    self._video_poster_request_id += 1
    self._video_surface_ready = False
    if self.session is None:
        self._clear_video_poster_overlay()
        return
    source = self._preferred_video_poster_source()
    if not source:
        self._clear_video_poster_overlay()
        return
    pixmap = self._load_poster_pixmap(source)
    if not pixmap.isNull():
        self._show_video_poster_overlay(pixmap)
        return
    self._clear_video_poster_overlay()
    request_id = self._video_poster_request_id
    self._start_poster_load(
        source,
        request_id,
        target="video",
        on_loaded=lambda image, request_id=request_id: self._apply_video_poster_image(request_id, image),
    )
```

```python
def _render_posters(self) -> None:
    self._render_detail_poster()
    self._render_video_poster()
```

```python
self._render_posters()
...
self._render_posters()
...
self._render_video_poster()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_prefers_video_cover_override_before_session_poster_and_default_video_cover tests/test_player_window_ui.py::test_player_window_refreshes_only_video_poster_after_async_playback_loader_updates_cover_override -q`
Expected: PASS

- [ ] **Step 5: Run focused regression tests**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_create_session_defaults_video_cover_override_to_empty tests/test_player_controller.py::test_player_controller_binds_session_aware_playback_loader_without_changing_history_poster tests/test_spider_plugin_controller.py::test_controller_updates_session_video_cover_override_from_player_content_cover tests/test_spider_plugin_controller.py::test_controller_keeps_video_cover_override_empty_when_player_content_cover_is_blank tests/test_player_window_ui.py::test_player_window_prefers_video_cover_override_before_session_poster_and_default_video_cover tests/test_player_window_ui.py::test_player_window_refreshes_only_video_poster_after_async_playback_loader_updates_cover_override tests/test_player_window_ui.py::test_player_window_prefers_session_poster_before_default_video_cover tests/test_player_window_ui.py::test_player_window_uses_default_video_cover_when_session_poster_is_empty -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py tests/test_spider_plugin_controller.py
git commit -m "feat: separate detail and video poster overrides"
```
