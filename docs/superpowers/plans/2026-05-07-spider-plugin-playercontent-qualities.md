# Spider Plugin `playerContent().qualities` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let spider-plugin `playerContent()` return `qualities` so one episode can expose multiple direct playback URLs in the existing player quality selector.

**Architecture:** Extend `PlayItem` and `VideoQualityOption` with just enough state to carry spider-provided quality URLs, normalize those URLs inside `SpiderPluginController`, then teach `PlayerWindow` to treat the existing quality combo/menu as a two-source control: spider URL qualities first, DASH qualities second. Preserve the current lazy playback-loader flow, and add explicit rollback for failed spider quality switches so a bad quality URL does not interrupt the already-playing stream.

**Tech Stack:** Python, dataclasses, PySide6, `pytest`, `uv`

---

## File Map

- `src/atv_player/models.py`
  Responsibility: add persistent in-memory fields for spider quality options on `PlayItem` and store a per-option URL on `VideoQualityOption`.
- `src/atv_player/plugins/controller.py`
  Responsibility: normalize `playerContent().qualities`, ignore malformed entries, and attach selected spider quality metadata to `PlayItem`.
- `src/atv_player/ui/player_window.py`
  Responsibility: surface spider quality options in the existing quality UI, switch URLs while preserving playback state, and roll back failed switches.
- `tests/test_spider_plugin_controller.py`
  Responsibility: lock down `qualities` parsing and selection rules at the plugin-controller boundary.
- `tests/test_player_window_ui.py`
  Responsibility: lock down combo/menu display, successful switching, source-priority, and rollback behavior.

### Task 1: Normalize `playerContent().qualities` into `PlayItem`

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/plugins/controller.py`

- [ ] **Step 1: Write the failing controller tests**

```python
from atv_player.models import CategoryFilter, CategoryFilterOption, PlayItem, VideoQualityOption


class QualityPayloadSpider(FakeSpider):
    def __init__(self, url: str, qualities: object) -> None:
        self._url = url
        self._qualities = qualities

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": self._url,
            "header": {"Referer": "https://site.example"},
            "qualities": self._qualities,
        }


def test_controller_build_request_maps_spider_qualities_matching_top_level_url() -> None:
    controller = SpiderPluginController(
        QualityPayloadSpider(
            "https://stream.example/play/1-1080.m3u8",
            [
                {"id": "1080p", "label": "1080P", "url": "https://stream.example/play/1-1080.m3u8"},
                {"id": "720p", "label": "720P", "url": "https://stream.example/play/1-720.m3u8"},
            ],
        ),
        plugin_name="清晰度插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1-1080.m3u8"
    assert [(quality.id, quality.label, quality.url) for quality in first.playback_qualities] == [
        ("1080p", "1080P", "https://stream.example/play/1-1080.m3u8"),
        ("720p", "720P", "https://stream.example/play/1-720.m3u8"),
    ]
    assert first.selected_playback_quality_id == "1080p"


def test_controller_build_request_falls_back_to_first_valid_spider_quality() -> None:
    controller = SpiderPluginController(
        QualityPayloadSpider(
            "https://stream.example/play/1-default.m3u8",
            [
                {"id": "720p", "label": "720P", "url": "https://stream.example/play/1-720.m3u8"},
                {"id": "480p", "label": "480P", "url": "https://stream.example/play/1-480.m3u8"},
            ],
        ),
        plugin_name="清晰度插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1-default.m3u8"
    assert [quality.id for quality in first.playback_qualities] == ["720p", "480p"]
    assert first.selected_playback_quality_id == "720p"


def test_controller_build_request_ignores_malformed_spider_quality_entries() -> None:
    controller = SpiderPluginController(
        QualityPayloadSpider(
            "https://stream.example/play/1-1080.m3u8",
            [
                {"id": "", "label": "无效", "url": "https://stream.example/play/invalid.m3u8"},
                {"id": "bad-html", "label": "页面地址", "url": "https://example.com/watch/1.html"},
                {"id": "720p", "label": "720P", "url": "https://stream.example/play/1-720.m3u8"},
            ],
        ),
        plugin_name="清晰度插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1-1080.m3u8"
    assert [(quality.id, quality.label, quality.url) for quality in first.playback_qualities] == [
        ("720p", "720P", "https://stream.example/play/1-720.m3u8"),
    ]
    assert first.selected_playback_quality_id == "720p"
```

- [ ] **Step 2: Run the controller tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_spider_qualities_matching_top_level_url tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_first_valid_spider_quality tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_malformed_spider_quality_entries -v`

Expected: `FAIL` because `PlayItem` has no `playback_qualities` or `selected_playback_quality_id`, `VideoQualityOption` has no `url`, and `SpiderPluginController` ignores `payload["qualities"]`.

- [ ] **Step 3: Write the minimal model and controller implementation**

```python
@dataclass(slots=True)
class VideoQualityOption:
    id: str
    label: str
    url: str = ""
    width: int = 0
    height: int = 0
    bandwidth: int = 0
    codecs: str = ""


@dataclass(slots=True)
class PlayItem:
    headers: dict[str, str] = field(default_factory=dict)
    external_subtitles: list[ExternalSubtitleOption] = field(default_factory=list)
    playback_qualities: list[VideoQualityOption] = field(default_factory=list)
    selected_playback_quality_id: str = ""
    dash_video_id: str = ""
```

```python
from atv_player.models import (
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    ExternalSubtitleOption,
    OpenPlayerRequest,
    PlayItem,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)


class SpiderPluginController:
    def _map_spider_playback_qualities(
        self,
        payload: object,
        selected_url: str,
    ) -> tuple[list[VideoQualityOption], str]:
        if not isinstance(payload, list):
            return [], ""
        qualities: list[VideoQualityOption] = []
        selected_quality_id = ""
        for raw_quality in payload:
            if not isinstance(raw_quality, Mapping):
                continue
            quality_id = str(raw_quality.get("id") or "").strip()
            label = str(raw_quality.get("label") or "").strip()
            quality_url = str(raw_quality.get("url") or "").strip()
            if not quality_id or not label or not _looks_like_media_url(quality_url):
                continue
            qualities.append(VideoQualityOption(id=quality_id, label=label, url=quality_url))
            if not selected_quality_id and quality_url == selected_url:
                selected_quality_id = quality_id
        if not qualities:
            return [], ""
        return qualities, selected_quality_id or qualities[0].id
```

```python
item.external_subtitles = []
item.playback_qualities = []
item.selected_playback_quality_id = ""
```

```python
if not _looks_like_media_url(url):
    raise ValueError("插件未返回可播放地址")
item.url = url
item.headers = _normalize_headers(payload.get("header"))
item.playback_qualities, item.selected_playback_quality_id = self._map_spider_playback_qualities(
    payload.get("qualities"),
    url,
)
item.external_subtitles = self._map_spider_external_subtitles(payload.get("subt"))
self._maybe_resolve_danmaku(item, url)
logger.info(
    "Spider plugin resolved playback url plugin=%s source=%s play_source=%s",
    self._plugin_name,
    item.vod_id,
    item.play_source,
)
```

- [ ] **Step 4: Run the controller tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_spider_qualities_matching_top_level_url tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_first_valid_spider_quality tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_malformed_spider_quality_entries -v`

Expected: `3 passed`

- [ ] **Step 5: Commit the controller contract**

```bash
git add tests/test_spider_plugin_controller.py src/atv_player/models.py src/atv_player/plugins/controller.py
git commit -m "feat: map spider playback qualities"
```

### Task 2: Surface spider quality options in the existing player UI

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing player UI tests for display and successful switching**

```python
def test_player_window_populates_spider_video_quality_options(qtbot) -> None:
    class PassThroughM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return False

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://media.example/video-1080.m3u8",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.m3u8"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.m3u8"),
                ],
                selected_playback_quality_id="1080p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=PassThroughM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert [window.video_quality_combo.itemData(index) for index in range(window.video_quality_combo.count())] == [
        "1080p",
        "720p",
    ]
    assert window.video_quality_combo.currentData() == "1080p"
    assert window.video_quality_combo.isEnabled() is True


def test_player_window_switches_spider_video_quality_with_position_and_pause_preserved(qtbot) -> None:
    class PassThroughM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return False

    class FakeVideo:
        def __init__(self) -> None:
            self.load_calls: list[tuple[str, bool, int]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            self.load_calls.append((url, pause, start_seconds))

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 93

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://media.example/video-1080.m3u8",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.m3u8"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.m3u8"),
                ],
                selected_playback_quality_id="1080p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=PassThroughM3U8AdFilter())
    qtbot.addWidget(window)
    video = FakeVideo()
    window.video = video

    window.open_session(session)
    assert video.load_calls == [("https://media.example/video-1080.m3u8", False, 0)]

    window.is_playing = False
    window.video_quality_combo.setCurrentIndex(1)

    qtbot.waitUntil(lambda: len(video.load_calls) == 2)
    assert video.load_calls[-1] == ("https://media.example/video-720.m3u8", True, 93)
    assert session.playlist[0].selected_playback_quality_id == "720p"


def test_player_window_builds_video_context_menu_with_spider_quality_submenu(qtbot) -> None:
    class PassThroughM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return False

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://media.example/video-1080.m3u8",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.m3u8"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.m3u8"),
                ],
                selected_playback_quality_id="1080p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=PassThroughM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    menu = window._build_video_context_menu()

    assert "清晰度" in [action.text() for action in menu.actions()]
    assert [action.text() for action in _submenu_actions(menu, "清晰度")] == ["1080P", "720P"]
```

- [ ] **Step 2: Run the player UI tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_populates_spider_video_quality_options tests/test_player_window_ui.py::test_player_window_switches_spider_video_quality_with_position_and_pause_preserved tests/test_player_window_ui.py::test_player_window_builds_video_context_menu_with_spider_quality_submenu -v`

Expected: `FAIL` because `_refresh_video_quality_state()` only knows how to read DASH qualities, and `_change_video_quality_selection()` returns early for non-DASH URLs.

- [ ] **Step 3: Implement spider-quality display and successful switching**

```python
@dataclass(slots=True)
class _PendingPlaybackPrepare:
    index: int
    previous_index: int
    start_position_seconds: int
    pause: bool
    source_url: str
    requested_dash_video_id: str = ""
    previous_dash_video_id: str = ""
    previous_url: str = ""
    previous_original_url: str = ""
    previous_selected_playback_quality_id: str = ""
```

```python
self._refresh_subtitle_state()
self._refresh_audio_state()
self._refresh_video_quality_state()
self._configure_danmaku_for_current_item()
```

```python
def _refresh_video_quality_state(self, prepared_url: str | None = None) -> None:
    current_item = self._current_play_item()
    if current_item is None:
        self._video_quality_options = []
        self._reset_video_quality_combo()
        return
    if current_item.playback_qualities:
        self._video_quality_options = list(current_item.playback_qualities)
        selected_quality_id = current_item.selected_playback_quality_id or current_item.playback_qualities[0].id
        current_item.selected_playback_quality_id = selected_quality_id
        self._populate_video_quality_combo(self._video_quality_options, selected_quality_id)
        return
    source_url = current_item.original_url or current_item.url
    if not source_url.startswith(self._DASH_DATA_URI_PREFIX):
        self._video_quality_options = []
        self._reset_video_quality_combo()
        return
    qualities_getter = getattr(self._m3u8_ad_filter, "dash_video_qualities", None)
    selected_getter = getattr(self._m3u8_ad_filter, "selected_dash_video_quality", None)
    if not callable(qualities_getter) or not callable(selected_getter):
        self._video_quality_options = []
        self._reset_video_quality_combo()
        return
    target_url = prepared_url or current_item.url
    self._video_quality_options = list(qualities_getter(target_url))
    selected_quality_id = selected_getter(target_url) or current_item.dash_video_id or None
    if selected_quality_id is not None:
        current_item.dash_video_id = selected_quality_id
    self._populate_video_quality_combo(self._video_quality_options, selected_quality_id)
```

```python
def _change_video_quality_selection(self, index: int) -> None:
    if index < 0 or self.session is None:
        return
    current_item = self.session.playlist[self.current_index]
    target_quality_id = self.video_quality_combo.itemData(index)
    if not isinstance(target_quality_id, str) or not target_quality_id:
        return
    if current_item.playback_qualities:
        if target_quality_id == current_item.selected_playback_quality_id:
            return
        selected_quality = next(
            (quality for quality in current_item.playback_qualities if quality.id == target_quality_id and quality.url),
            None,
        )
        if selected_quality is None:
            return
        try:
            start_position_seconds = int(self.video.position_seconds() or 0)
        except Exception:
            start_position_seconds = 0
        previous_url = current_item.url
        previous_original_url = current_item.original_url
        previous_selected_quality_id = current_item.selected_playback_quality_id
        current_item.url = selected_quality.url
        current_item.original_url = selected_quality.url
        current_item.selected_playback_quality_id = target_quality_id
        if self._start_playback_prepare(
            previous_index=self.current_index,
            start_position_seconds=start_position_seconds,
            pause=not self.is_playing,
            previous_url=previous_url,
            previous_original_url=previous_original_url,
            previous_selected_playback_quality_id=previous_selected_quality_id,
        ):
            return
        try:
            self._start_current_item_playback(
                start_position_seconds=start_position_seconds,
                pause=not self.is_playing,
            )
        except Exception as exc:
            current_item.url = previous_url
            current_item.original_url = previous_original_url
            current_item.selected_playback_quality_id = previous_selected_quality_id
            self._refresh_video_quality_state()
            self._append_log(f"清晰度切换失败: {exc}")
        return
    if target_quality_id == current_item.dash_video_id:
        return
    source_url = current_item.original_url or current_item.url
    if not source_url.startswith(self._DASH_DATA_URI_PREFIX):
        return
```

```python
def _start_playback_prepare(
    self,
    *,
    previous_index: int,
    start_position_seconds: int,
    pause: bool,
    dash_video_id: str | None = None,
    previous_url: str = "",
    previous_original_url: str = "",
    previous_selected_playback_quality_id: str = "",
) -> bool:
    if self.session is None:
        return False
    current_item = self.session.playlist[self.current_index]
    source_url = self._playback_prepare_source_url(current_item)
    if source_url.startswith(self._DASH_DATA_URI_PREFIX) and not current_item.original_url:
        current_item.original_url = source_url
    should_prepare = getattr(self._m3u8_ad_filter, "should_prepare", None)
    if callable(should_prepare):
        if not should_prepare(source_url):
            return False
    elif ".m3u8" not in source_url.lower():
        return False
    self._playback_prepare_request_id += 1
    request_id = self._playback_prepare_request_id
    requested_dash_video_id = dash_video_id if dash_video_id is not None else current_item.dash_video_id
    self._pending_playback_prepare = _PendingPlaybackPrepare(
        index=self.current_index,
        previous_index=previous_index,
        start_position_seconds=start_position_seconds,
        pause=pause,
        source_url=source_url,
        requested_dash_video_id=requested_dash_video_id,
        previous_dash_video_id=current_item.dash_video_id,
        previous_url=previous_url,
        previous_original_url=previous_original_url,
        previous_selected_playback_quality_id=previous_selected_playback_quality_id,
    )
```

- [ ] **Step 4: Run the player UI tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_populates_spider_video_quality_options tests/test_player_window_ui.py::test_player_window_switches_spider_video_quality_with_position_and_pause_preserved tests/test_player_window_ui.py::test_player_window_builds_video_context_menu_with_spider_quality_submenu -v`

Expected: `3 passed`

- [ ] **Step 5: Commit the player UI success path**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: add spider quality switching"
```

### Task 3: Roll back failed spider quality switches and protect DASH behavior

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing rollback and priority tests**

```python
def test_player_window_restores_previous_spider_quality_after_prepare_failure(qtbot) -> None:
    class FlakyM3U8AdFilter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def should_prepare(self, url: str) -> bool:
            return url.endswith(".m3u8")

        def prepare(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            dash_video_id: str | None = None,
        ) -> str:
            self.calls.append((url, dash_video_id))
            if len(self.calls) == 1:
                return "http://127.0.0.1:2323/m3u?v=spider-1080"
            raise RuntimeError("proxy busy")

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://media.example/video-1080.m3u8",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.m3u8"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.m3u8"),
                ],
                selected_playback_quality_id="1080p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=FlakyM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    qtbot.waitUntil(lambda: window.video.load_calls == [("http://127.0.0.1:2323/m3u?v=spider-1080", 0)])

    item = session.playlist[0]
    assert item.original_url == "https://media.example/video-1080.m3u8"

    window.video_quality_combo.setCurrentIndex(1)

    qtbot.waitUntil(lambda: "清晰度切换失败: proxy busy" in window.log_view.toPlainText())
    assert item.url == "http://127.0.0.1:2323/m3u?v=spider-1080"
    assert item.original_url == "https://media.example/video-1080.m3u8"
    assert item.selected_playback_quality_id == "1080p"
    assert window.video.load_calls == [("http://127.0.0.1:2323/m3u?v=spider-1080", 0)]


def test_player_window_restores_previous_spider_quality_after_direct_load_failure(qtbot) -> None:
    class PassThroughM3U8AdFilter:
        def should_prepare(self, url: str) -> bool:
            return False

    class FlakyVideo:
        def __init__(self) -> None:
            self.load_calls: list[tuple[str, bool, int]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            self.load_calls.append((url, pause, start_seconds))
            if len(self.load_calls) == 2:
                raise RuntimeError("device busy")

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 41

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="https://media.example/video-1080.mp4",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.mp4"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.mp4"),
                ],
                selected_playback_quality_id="1080p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=PassThroughM3U8AdFilter())
    qtbot.addWidget(window)
    video = FlakyVideo()
    window.video = video

    window.open_session(session)
    assert video.load_calls == [("https://media.example/video-1080.mp4", False, 0)]

    window.video_quality_combo.setCurrentIndex(1)

    qtbot.waitUntil(lambda: "清晰度切换失败: device busy" in window.log_view.toPlainText())
    assert session.playlist[0].url == "https://media.example/video-1080.mp4"
    assert session.playlist[0].selected_playback_quality_id == "1080p"


def test_player_window_prefers_spider_quality_options_over_dash_quality_options(qtbot) -> None:
    class FakeM3U8AdFilter:
        def dash_video_qualities(self, prepared_url: str) -> list[VideoQualityOption]:
            return [
                VideoQualityOption(id="v1080", label="1080P AVC 2.8 Mbps"),
                VideoQualityOption(id="v720", label="720P AVC 1.2 Mbps"),
            ]

        def selected_dash_video_quality(self, prepared_url: str) -> str | None:
            return "v1080"

    window = PlayerWindow(FakePlayerController(), m3u8_ad_filter=FakeM3U8AdFilter())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[
            PlayItem(
                title="正片",
                url="http://127.0.0.1:2323/dash/v1080.mpd",
                original_url="data:application/dash+xml;base64,PE1QRD48L01QRD4=",
                playback_qualities=[
                    VideoQualityOption(id="1080p", label="1080P", url="https://media.example/video-1080.m3u8"),
                    VideoQualityOption(id="720p", label="720P", url="https://media.example/video-720.m3u8"),
                ],
                selected_playback_quality_id="720p",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window.current_index = 0

    window._refresh_video_quality_state("http://127.0.0.1:2323/dash/v1080.mpd")

    assert [window.video_quality_combo.itemData(index) for index in range(window.video_quality_combo.count())] == [
        "1080p",
        "720p",
    ]
    assert window.video_quality_combo.currentData() == "720p"
```

- [ ] **Step 2: Run the rollback and regression tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_prepare_failure tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_direct_load_failure tests/test_player_window_ui.py::test_player_window_prefers_spider_quality_options_over_dash_quality_options tests/test_player_window_ui.py::test_player_window_populates_dash_video_quality_options_after_prepare tests/test_player_window_ui.py::test_player_window_switches_dash_video_quality_with_position_and_pause_preserved -v`

Expected: `FAIL` because prepare failure currently logs `播放代理失败，继续播放原地址: proxy busy` and restarts playback instead of restoring the previous spider state, direct non-DASH switching has no rollback path, and `_refresh_video_quality_state()` always chooses DASH over spider qualities when a DASH source URL exists.

- [ ] **Step 3: Implement rollback for failed spider quality switches**

```python
def _restore_failed_spider_quality_switch(
    self,
    item: PlayItem,
    pending_prepare: _PendingPlaybackPrepare | None = None,
) -> bool:
    if pending_prepare is None or not pending_prepare.previous_url:
        return False
    item.url = pending_prepare.previous_url
    item.original_url = pending_prepare.previous_original_url
    item.selected_playback_quality_id = pending_prepare.previous_selected_playback_quality_id
    self._refresh_video_quality_state()
    return True


def _handle_playback_prepare_failed(self, request_id: int, message: str) -> None:
    if request_id != self._playback_prepare_request_id:
        return
    pending_prepare = self._pending_playback_prepare
    self._pending_playback_prepare = None
    if pending_prepare is None:
        return
    if self.session is None or self.current_index != pending_prepare.index:
        return
    current_item = self.session.playlist[self.current_index]
    if self._restore_failed_spider_quality_switch(current_item, pending_prepare):
        self._append_log(f"清晰度切换失败: {message}")
        return
    current_item.dash_video_id = pending_prepare.previous_dash_video_id
    self._refresh_video_quality_state(current_item.url)
    self._append_log(f"播放代理失败，继续播放原地址: {message}")
    try:
        self._start_current_item_playback(
            start_position_seconds=pending_prepare.start_position_seconds,
            pause=pending_prepare.pause,
        )
    except Exception as exc:
        self._restore_current_index(pending_prepare.previous_index)
        self._append_log(f"播放失败: {exc}")
```

```python
def _change_video_quality_selection(self, index: int) -> None:
    if index < 0 or self.session is None:
        return
    current_item = self.session.playlist[self.current_index]
    target_quality_id = self.video_quality_combo.itemData(index)
    if not isinstance(target_quality_id, str) or not target_quality_id:
        return
    if current_item.playback_qualities:
        if target_quality_id == current_item.selected_playback_quality_id:
            return
        selected_quality = next(
            (quality for quality in current_item.playback_qualities if quality.id == target_quality_id and quality.url),
            None,
        )
        if selected_quality is None:
            return
        try:
            start_position_seconds = int(self.video.position_seconds() or 0)
        except Exception:
            start_position_seconds = 0
        previous_url = current_item.url
        previous_original_url = current_item.original_url
        previous_selected_quality_id = current_item.selected_playback_quality_id
        current_item.url = selected_quality.url
        current_item.original_url = selected_quality.url
        current_item.selected_playback_quality_id = target_quality_id
        if self._start_playback_prepare(
            previous_index=self.current_index,
            start_position_seconds=start_position_seconds,
            pause=not self.is_playing,
            previous_url=previous_url,
            previous_original_url=previous_original_url,
            previous_selected_playback_quality_id=previous_selected_quality_id,
        ):
            return
        try:
            self._start_current_item_playback(
                start_position_seconds=start_position_seconds,
                pause=not self.is_playing,
            )
        except Exception as exc:
            current_item.url = previous_url
            current_item.original_url = previous_original_url
            current_item.selected_playback_quality_id = previous_selected_quality_id
            self._refresh_video_quality_state()
            self._append_log(f"清晰度切换失败: {exc}")
        return
    if target_quality_id == current_item.dash_video_id:
        return
```

- [ ] **Step 4: Run the rollback and regression tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_prepare_failure tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_direct_load_failure tests/test_player_window_ui.py::test_player_window_prefers_spider_quality_options_over_dash_quality_options tests/test_player_window_ui.py::test_player_window_populates_dash_video_quality_options_after_prepare tests/test_player_window_ui.py::test_player_window_switches_dash_video_quality_with_position_and_pause_preserved -v`

Expected: `5 passed`

- [ ] **Step 5: Run the focused quality regression suite**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_spider_qualities_matching_top_level_url tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_first_valid_spider_quality tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_malformed_spider_quality_entries tests/test_player_window_ui.py::test_player_window_populates_spider_video_quality_options tests/test_player_window_ui.py::test_player_window_switches_spider_video_quality_with_position_and_pause_preserved tests/test_player_window_ui.py::test_player_window_builds_video_context_menu_with_spider_quality_submenu tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_prepare_failure tests/test_player_window_ui.py::test_player_window_restores_previous_spider_quality_after_direct_load_failure tests/test_player_window_ui.py::test_player_window_prefers_spider_quality_options_over_dash_quality_options tests/test_player_window_ui.py::test_player_window_populates_dash_video_quality_options_after_prepare tests/test_player_window_ui.py::test_player_window_switches_dash_video_quality_with_position_and_pause_preserved -v`

Expected: all listed tests `PASSED`

- [ ] **Step 6: Commit the rollback and regression work**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "fix: rollback failed spider quality switches"
```
