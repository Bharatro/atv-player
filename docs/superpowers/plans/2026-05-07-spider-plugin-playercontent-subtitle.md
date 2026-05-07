# Spider Plugin `playerContent().subt` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow spider-plugin `playerContent()` to return `subt` and expose that subtitle as a manually selectable primary external subtitle without auto-enabling it.

**Architecture:** Reuse the existing `PlayItem.external_subtitles` path instead of inventing a new subtitle field. Normalize plugin `subt` inside `SpiderPluginController`, inject app `base_url` into that controller for `/path` resolution, then make `PlayerWindow` treat plugin subtitles as generic external subtitles while filtering them out of the secondary subtitle menu.

**Tech Stack:** Python, dataclasses, PySide6, `httpx`, `pytest`, `uv`

---

### Task 1: Map `playerContent().subt` into `PlayItem.external_subtitles`

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/plugins/controller.py`

- [ ] **Step 1: Write the failing controller tests**

```python
class SubtitlePayloadSpider(FakeSpider):
    def __init__(self, subt: str) -> None:
        self._subt = subt

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": f"https://stream.example{id}.m3u8",
            "header": {"Referer": "https://site.example"},
            "subt": self._subt,
        }


def test_controller_build_request_maps_absolute_subt_into_external_subtitles() -> None:
    controller = SpiderPluginController(
        SubtitlePayloadSpider("https://cdn.example/subtitles/episode-1.srt"),
        plugin_name="字幕插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlist[0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1.m3u8"
    assert [(sub.name, sub.url, sub.format, sub.source) for sub in first.external_subtitles] == [
        ("外挂字幕 [插件]", "https://cdn.example/subtitles/episode-1.srt", "application/x-subrip", "spider"),
    ]


def test_controller_build_request_resolves_relative_subt_against_base_url() -> None:
    controller = SpiderPluginController(
        SubtitlePayloadSpider("/files/subtitles/episode-1.ass"),
        plugin_name="字幕插件",
        search_enabled=True,
        base_url_loader=lambda: "http://127.0.0.1:4567",
    )

    request = controller.build_request("/detail/1")
    first = request.playlist[0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert [(sub.url, sub.format, sub.source) for sub in first.external_subtitles] == [
        ("http://127.0.0.1:4567/files/subtitles/episode-1.ass", "text/x-ass", "spider"),
    ]


def test_controller_build_request_ignores_blank_or_unsupported_subt_without_breaking_playback() -> None:
    controller = SpiderPluginController(
        SubtitlePayloadSpider("subtitle.srt"),
        plugin_name="字幕插件",
        search_enabled=True,
        base_url_loader=lambda: "http://127.0.0.1:4567",
    )

    request = controller.build_request("/detail/1")
    first = request.playlist[0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert first.url == "https://stream.example/play/1.m3u8"
    assert first.external_subtitles == []
```

- [ ] **Step 2: Run the controller tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_absolute_subt_into_external_subtitles tests/test_spider_plugin_controller.py::test_controller_build_request_resolves_relative_subt_against_base_url tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_blank_or_unsupported_subt_without_breaking_playback -v`

Expected: `FAIL` because `SpiderPluginController` does not accept `base_url_loader` and never populates `PlayItem.external_subtitles`.

- [ ] **Step 3: Write the minimal controller implementation**

```python
from urllib.parse import urljoin, urlparse

from atv_player.models import (
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    ExternalSubtitleOption,
    OpenPlayerRequest,
    PlayItem,
    PlaybackLoadResult,
    VodItem,
)


def _infer_external_subtitle_format(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".srt"):
        return "application/x-subrip"
    if path.endswith(".ass"):
        return "text/x-ass"
    if path.endswith(".ssa"):
        return "text/x-ssa"
    if path.endswith(".vtt"):
        return "text/vtt"
    return ""


class SpiderPluginController:
    def __init__(
        self,
        spider,
        plugin_name: str,
        search_enabled: bool,
        drive_detail_loader: Callable[[str], dict] | None = None,
        playback_history_loader: Callable[[str], object | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        playback_parser_service=None,
        preferred_parse_key_loader: Callable[[], str] | None = None,
        danmaku_service=None,
        danmaku_preference_store=None,
        base_url_loader: Callable[[], str] | None = None,
    ) -> None:
        ...
        self._base_url_loader = base_url_loader

    def _normalize_spider_subtitle_url(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.startswith(("http://", "https://")):
            return raw
        if not raw.startswith("/"):
            return ""
        base_url = "" if self._base_url_loader is None else str(self._base_url_loader() or "").strip()
        if not base_url:
            return ""
        return urljoin(f"{base_url.rstrip('/')}/", raw.lstrip("/"))

    def _map_spider_external_subtitles(self, payload: object) -> list[ExternalSubtitleOption]:
        url = self._normalize_spider_subtitle_url(payload)
        if not url:
            return []
        return [
            ExternalSubtitleOption(
                name="外挂字幕 [插件]",
                lang="",
                url=url,
                format=_infer_external_subtitle_format(url),
                source="spider",
            )
        ]

    def _resolve_play_item(self, item: PlayItem) -> PlaybackLoadResult | None:
        ...
        item.external_subtitles = []
        ...
        item.url = url
        item.headers = _normalize_headers(payload.get("header"))
        item.external_subtitles = self._map_spider_external_subtitles(payload.get("subt"))
        self._maybe_resolve_danmaku(item, url)
        ...
```

- [ ] **Step 4: Run the controller tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_absolute_subt_into_external_subtitles tests/test_spider_plugin_controller.py::test_controller_build_request_resolves_relative_subt_against_base_url tests/test_spider_plugin_controller.py::test_controller_build_request_ignores_blank_or_unsupported_subt_without_breaking_playback -v`

Expected: `3 passed`

- [ ] **Step 5: Commit the controller work**

```bash
git add tests/test_spider_plugin_controller.py src/atv_player/plugins/controller.py
git commit -m "feat: map spider plugin player subtitles"
```

### Task 2: Wire app `base_url` into spider plugin controllers

**Files:**
- Modify: `src/atv_player/plugins/__init__.py`
- Modify: `src/atv_player/app.py`

- [ ] **Step 1: Add the failing integration-oriented controller test**

```python
def test_controller_build_request_resolves_relative_subt_against_runtime_base_url() -> None:
    controller = SpiderPluginController(
        SubtitlePayloadSpider("/proxy/sub/episode-1.srt"),
        plugin_name="字幕插件",
        search_enabled=True,
        base_url_loader=lambda: "http://127.0.0.1:4567/",
    )

    request = controller.build_request("/detail/1")
    item = request.playlist[0]

    assert request.playback_loader is not None
    request.playback_loader(item)

    assert item.external_subtitles[0].url == "http://127.0.0.1:4567/proxy/sub/episode-1.srt"
```

This test should already exist from Task 1. Keep it as the guard while wiring production code.

- [ ] **Step 2: Run the test to verify production wiring is still missing**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_resolves_relative_subt_against_base_url -v`

Expected: `PASS` in the unit test, but note that production code still does not pass a loader into `SpiderPluginController`.

- [ ] **Step 3: Add the minimal wiring in plugin manager and app bootstrap**

```python
class SpiderPluginManager:
    def __init__(...):
        ...
        self._base_url_loader = None

    def load_enabled_plugins(self, drive_detail_loader=None) -> list[SpiderPluginDefinition]:
        ...
        controller = SpiderPluginController(
            loaded.spider,
            plugin_name=title,
            search_enabled=loaded.search_enabled,
            drive_detail_loader=drive_detail_loader,
            playback_parser_service=self._playback_parser_service,
            preferred_parse_key_loader=self._preferred_parse_key_loader,
            danmaku_service=self._danmaku_service,
            danmaku_preference_store=self._danmaku_preference_store,
            base_url_loader=self._base_url_loader,
            playback_history_loader=...,
            playback_history_saver=...,
        )
```

```python
class AppCoordinator(QObject):
    def __init__(self, repo: SettingsRepository) -> None:
        ...
        setattr(
            self._plugin_manager,
            "_base_url_loader",
            lambda: self.repo.load_config().base_url,
        )
```

- [ ] **Step 4: Run the focused controller regression**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_maps_absolute_subt_into_external_subtitles tests/test_spider_plugin_controller.py::test_controller_build_request_resolves_relative_subt_against_base_url -v`

Expected: `2 passed`

- [ ] **Step 5: Commit the wiring**

```bash
git add src/atv_player/plugins/__init__.py src/atv_player/app.py
git commit -m "feat: inject base url into spider plugin controllers"
```

### Task 3: Expose plugin subtitles only in the primary subtitle UI

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing player window tests**

```python
def test_player_window_lists_spider_external_subtitle_in_primary_combo(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return [SubtitleTrack(id=11, title="", lang="zh", is_default=True, is_forced=False, label="中文 (默认)")]

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return 11 if mode == "auto" else track_id

        def position_seconds(self) -> int:
            return 0

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
                        url="http://127.0.0.1:4567/sub/1.srt",
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
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    assert [window.subtitle_combo.itemText(index) for index in range(window.subtitle_combo.count())] == [
        "字幕",
        "关闭字幕",
        "中文 (默认)",
        "外挂字幕 [插件]",
    ]


def test_player_window_secondary_menu_excludes_spider_external_subtitles(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return [SubtitleTrack(id=11, title="", lang="zh", is_default=True, is_forced=False, label="中文 (默认)")]

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return track_id

        def apply_secondary_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return track_id

        def position_seconds(self) -> int:
            return 0

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
                        url="http://127.0.0.1:4567/sub/1.srt",
                        format="application/x-subrip",
                        source="spider",
                    ),
                    ExternalSubtitleOption(
                        name="English [B站]",
                        lang="ai-en",
                        url="http://sub/en.srt",
                        format="application/x-subrip",
                        source="bilibili",
                    ),
                ],
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
    menu = window._build_secondary_subtitle_menu(window)

    assert [action.text() for action in menu.actions()] == [
        "关闭次字幕",
        "中文 (默认)",
        "English [B站]",
    ]


def test_player_window_user_selection_loads_spider_subtitle_as_primary(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[tuple[str, bool]] = []
            self.subtitle_apply_calls: list[tuple[str, int | None]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            self.subtitle_apply_calls.append((mode, track_id))
            return track_id

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append((path, select_for_secondary))
            return 91

        def position_seconds(self) -> int:
            return 0

    class TextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda url, **kwargs: TextResponse("1\\n00:00:00,000 --> 00:00:01,000\\n你好\\n"),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="sp1", vod_name="插件视频"),
        playlist=[
            PlayItem(
                title="第1集",
                url="http://m/1.m3u8",
                headers={"Referer": "https://site.example"},
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="外挂字幕 [插件]",
                        lang="",
                        url="http://127.0.0.1:4567/sub/1.srt",
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
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)
    window.subtitle_combo.setCurrentIndex(2)

    assert [select_for_secondary for _path, select_for_secondary in window.video.loaded_external_subtitles] == [False]
    assert window.video.subtitle_apply_calls == [("track", 91)]
```

- [ ] **Step 2: Run the player tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_lists_spider_external_subtitle_in_primary_combo tests/test_player_window_ui.py::test_player_window_secondary_menu_excludes_spider_external_subtitles tests/test_player_window_ui.py::test_player_window_user_selection_loads_spider_subtitle_as_primary -v`

Expected: `FAIL` because there is no spider-specific primary-only filtering and helper names still assume Bilibili.

- [ ] **Step 3: Implement generic external subtitle helpers and secondary filtering**

```python
def _current_item_primary_external_subtitles(self) -> list[ExternalSubtitleOption]:
    return self._current_item_external_subtitles()


def _current_item_secondary_external_subtitles(self) -> list[ExternalSubtitleOption]:
    return [subtitle for subtitle in self._current_item_external_subtitles() if subtitle.source != "spider"]


def _load_external_subtitle(
    self,
    subtitle: ExternalSubtitleOption,
    *,
    secondary: bool,
) -> tuple[int | None, Path]:
    text = self._fetch_external_subtitle_text(subtitle)
    if not text.strip():
        raise ValueError("字幕内容为空")
    suffix = ".srt" if subtitle.format.endswith("subrip") else ".txt"
    subtitle_path = self._write_external_subtitle_file(text, suffix)
    track_id = self.video.load_external_subtitle(str(subtitle_path), select_for_secondary=secondary)
    return track_id, subtitle_path


def _build_primary_subtitle_options(self, tracks: list[SubtitleTrack]) -> list[UnifiedSubtitleOption]:
    options: list[UnifiedSubtitleOption] = []
    for track in tracks:
        options.append(UnifiedSubtitleOption(label=track.label, mode="track", track_id=track.id))
    for subtitle in self._current_item_primary_external_subtitles():
        options.append(
            UnifiedSubtitleOption(
                label=subtitle.name,
                mode="external",
                external_subtitle=subtitle,
            )
        )
    return options


def _build_secondary_subtitle_menu(self, parent: QWidget) -> QMenu:
    ...
    for subtitle in self._current_item_secondary_external_subtitles():
        action = menu.addAction(subtitle.name)
        ...
```

Also update the two existing call sites:

```python
loaded_track_id, subtitle_path = self._load_external_subtitle(external_subtitle, secondary=False)
...
loaded_track_id, subtitle_path = self._load_external_subtitle(subtitle, secondary=True)
```

- [ ] **Step 4: Run the focused player tests and a regression slice**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_lists_spider_external_subtitle_in_primary_combo tests/test_player_window_ui.py::test_player_window_secondary_menu_excludes_spider_external_subtitles tests/test_player_window_ui.py::test_player_window_user_selection_loads_spider_subtitle_as_primary tests/test_player_window_ui.py::test_player_window_lists_bilibili_external_subtitles_after_embedded_tracks tests/test_player_window_ui.py::test_player_window_context_menu_loads_bilibili_subtitle_as_secondary -v`

Expected: `5 passed`

- [ ] **Step 5: Commit the player work**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: limit spider external subtitles to primary slot"
```

### Task 4: Final verification

**Files:**
- Modify: none
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the focused end-to-end regression set**

Run: `uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -k "subt or subtitle" -v`

Expected: all targeted spider subtitle and existing external subtitle tests pass.

- [ ] **Step 2: Run the full touched-file test modules**

Run: `uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -v`

Expected: both modules pass without new failures.

- [ ] **Step 3: Commit if verification required follow-up edits**

```bash
git add src/atv_player/plugins/controller.py src/atv_player/plugins/__init__.py src/atv_player/app.py src/atv_player/ui/player_window.py tests/test_spider_plugin_controller.py tests/test_player_window_ui.py
git commit -m "test: verify spider plugin subtitle integration"
```

If no follow-up edits were needed after Task 3, skip this commit.
