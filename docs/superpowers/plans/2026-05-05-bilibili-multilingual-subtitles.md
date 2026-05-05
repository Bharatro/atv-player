# Bilibili Multilingual Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Bilibili `subs` entries show up in the existing subtitle controls as switchable primary and secondary subtitles without auto-enabling them.

**Architecture:** Keep Bilibili playback parsing in `BilibiliController` and keep subtitle orchestration in `PlayerWindow`. Model Bilibili subtitles as playback-time external subtitle options on `PlayItem`, merge them with embedded mpv tracks in the UI, and track slot-specific ownership so external subtitle cleanup never removes danmaku tracks by accident.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, httpx, python-mpv

---

## File Structure

- `src/atv_player/models.py`
  - Add small playback-time models for Bilibili external subtitle options and slot selections.
- `src/atv_player/controllers/bilibili_controller.py`
  - Parse backend `subs` payloads into normalized `PlayItem` subtitle options while preserving current URL/header/danmaku behavior.
- `src/atv_player/ui/player_window.py`
  - Merge embedded and Bilibili subtitle options into the existing subtitle UI, download/load external subtitle files on demand, and track primary/secondary slot ownership and cleanup.
- `tests/test_bilibili_controller.py`
  - Add deterministic tests for Bilibili `subs` parsing and filtering.
- `tests/test_player_window_ui.py`
  - Add deterministic tests for subtitle option population, manual Bilibili subtitle selection, cleanup, danmaku coexistence, and failure fallback.

### Task 1: Add Playback-Time Bilibili Subtitle Models And Controller Parsing

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/bilibili_controller.py`
- Modify: `tests/test_bilibili_controller.py`
- Test: `tests/test_bilibili_controller.py`

- [ ] **Step 1: Write the failing controller test**

Add this test after `test_load_playback_item_loads_direct_bilibili_danmaku_xml_from_payload()` in `tests/test_bilibili_controller.py`:

```python
def test_load_playback_item_maps_bilibili_subtitles_from_playback_payload() -> None:
    api = FakeApiClient()
    api.playback_payload = {
        "url": "http://127.0.0.1:2323/dash/demo.mpd",
        "header": {"Referer": "https://www.bilibili.com/video/BV1xx411c7mD"},
        "subs": [
            {"url": "", "name": "关闭", "lang": "", "format": "application/x-subrip"},
            {"url": "http://127.0.0.1:4567/subtitles?lang=zh", "name": "中文", "lang": "ai-zh", "format": "application/x-subrip"},
            {"url": "http://127.0.0.1:4567/subtitles?lang=en", "name": "English", "lang": "ai-en", "format": "application/x-subrip"},
        ],
    }
    controller = BilibiliController(api)
    item = PlayItem(title="视频", url="", vod_id="BV1xx411c7mD")

    controller.load_playback_item(item)

    assert item.url == "http://127.0.0.1:2323/dash/demo.mpd"
    assert [(sub.name, sub.lang, sub.url, sub.format) for sub in item.external_subtitles] == [
        ("中文 [B站]", "ai-zh", "http://127.0.0.1:4567/subtitles?lang=zh", "application/x-subrip"),
        ("English [B站]", "ai-en", "http://127.0.0.1:4567/subtitles?lang=en", "application/x-subrip"),
    ]
```

- [ ] **Step 2: Run the focused controller test to verify it fails**

Run:

```bash
uv run pytest tests/test_bilibili_controller.py::test_load_playback_item_maps_bilibili_subtitles_from_playback_payload -q
```

Expected: FAIL because `PlayItem` does not have `external_subtitles` and the controller does not parse `subs`.

- [ ] **Step 3: Add the playback-time subtitle models**

In `src/atv_player/models.py`, add these dataclasses above `PlayItem`:

```python
@dataclass(slots=True)
class ExternalSubtitleOption:
    name: str
    lang: str
    url: str
    format: str = ""
    source: str = ""


@dataclass(slots=True)
class ExternalSubtitleSelection:
    source: str
    option_url: str
```

Then add this field to `PlayItem` near the existing playback metadata:

```python
    external_subtitles: list[ExternalSubtitleOption] = field(default_factory=list)
```

- [ ] **Step 4: Implement Bilibili subtitle parsing**

In `src/atv_player/controllers/bilibili_controller.py`, extend the imports:

```python
from atv_player.models import (
    DoubanCategory,
    ExternalSubtitleOption,
    HistoryRecord,
    OpenPlayerRequest,
    PlayItem,
    VodItem,
)
```

Add these helpers above `load_playback_item()`:

```python
    def _normalize_bilibili_subtitle_name(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text in {"关闭", "关闭字幕", "off", "OFF"}:
            return ""
        return f"{text} [B站]"

    def _parse_bilibili_subtitles(self, payload: dict[str, object]) -> list[ExternalSubtitleOption]:
        raw_subs = payload.get("subs")
        if not isinstance(raw_subs, list):
            return []
        subtitles: list[ExternalSubtitleOption] = []
        for raw_sub in raw_subs:
            if not isinstance(raw_sub, dict):
                continue
            url = str(raw_sub.get("url") or "").strip()
            name = self._normalize_bilibili_subtitle_name(raw_sub.get("name"))
            if not url or not name:
                continue
            subtitles.append(
                ExternalSubtitleOption(
                    name=name,
                    lang=str(raw_sub.get("lang") or "").strip(),
                    url=url,
                    format=str(raw_sub.get("format") or "").strip(),
                    source="bilibili",
                )
            )
        return subtitles
```

In `load_playback_item()`, after `item.headers = ...`, add:

```python
        item.external_subtitles = self._parse_bilibili_subtitles(payload)
```

- [ ] **Step 5: Run the focused controller test to verify it passes**

Run:

```bash
uv run pytest tests/test_bilibili_controller.py::test_load_playback_item_maps_bilibili_subtitles_from_playback_payload -q
```

Expected: PASS with only valid Bilibili subtitle entries preserved.

- [ ] **Step 6: Run the full Bilibili controller suite**

Run:

```bash
uv run pytest tests/test_bilibili_controller.py -q
```

Expected: PASS with the new subtitle parsing and no regression to existing URL/header/danmaku behavior.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/models.py src/atv_player/controllers/bilibili_controller.py tests/test_bilibili_controller.py
git commit -m "feat: parse bilibili playback subtitles"
```

### Task 2: Expose Unified Embedded And Bilibili Subtitle Options In The Existing Subtitle UI

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing unified-option tests**

Add these tests after `test_player_window_disables_subtitle_selector_when_current_item_has_no_embedded_subtitles()` in `tests/test_player_window_ui.py`:

```python
def test_player_window_lists_bilibili_external_subtitles_after_embedded_tracks(qtbot) -> None:
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
        vod=VodItem(vod_id="BV1", vod_name="B站视频"),
        playlist=[
            PlayItem(
                title="第1话",
                url="http://m/1.m3u8",
                external_subtitles=[
                    ExternalSubtitleOption(name="中文 [B站]", lang="ai-zh", url="http://sub/zh.srt", format="application/x-subrip", source="bilibili"),
                    ExternalSubtitleOption(name="English [B站]", lang="ai-en", url="http://sub/en.srt", format="application/x-subrip", source="bilibili"),
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
        "中文 [B站]",
        "English [B站]",
    ]


def test_player_window_does_not_auto_load_bilibili_external_subtitles_on_open(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[str] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return None

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append(path)
            return 51

        def position_seconds(self) -> int:
            return 0

    monkeypatch.setattr(player_window_module.httpx, "get", lambda *args, **kwargs: pytest.fail("should not fetch subtitle"))
    session = PlayerSession(
        vod=VodItem(vod_id="BV1", vod_name="B站视频"),
        playlist=[PlayItem(title="第1话", url="http://m/1.m3u8", external_subtitles=[
            ExternalSubtitleOption(name="中文 [B站]", lang="ai-zh", url="http://sub/zh.srt", format="application/x-subrip", source="bilibili"),
        ])],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    assert window.video.loaded_external_subtitles == []
    assert window.subtitle_combo.currentText() == "字幕"
```

- [ ] **Step 2: Run the focused player window tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_lists_bilibili_external_subtitles_after_embedded_tracks \
  tests/test_player_window_ui.py::test_player_window_does_not_auto_load_bilibili_external_subtitles_on_open \
  -q
```

Expected: FAIL because `PlayerWindow` only renders embedded tracks today.

- [ ] **Step 3: Add unified subtitle option state**

In `src/atv_player/ui/player_window.py`, extend the model imports:

```python
from atv_player.models import (
    ExternalSubtitleOption,
    ExternalSubtitleSelection,
    PlayItem,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)
```

Add these dataclasses near `SubtitlePreference`:

```python
@dataclass(slots=True)
class UnifiedSubtitleOption:
    label: str
    mode: str
    track_id: int | None = None
    external_subtitle: ExternalSubtitleOption | None = None
```

Add these fields in `PlayerWindow.__init__` near the current subtitle state:

```python
        self._unified_primary_subtitle_options: list[UnifiedSubtitleOption] = []
        self._primary_external_subtitle_selection: ExternalSubtitleSelection | None = None
        self._secondary_external_subtitle_selection: ExternalSubtitleSelection | None = None
        self._primary_external_subtitle_track_id: int | None = None
        self._secondary_external_subtitle_track_id: int | None = None
        self._primary_external_subtitle_path: Path | None = None
        self._secondary_external_subtitle_path: Path | None = None
```

- [ ] **Step 4: Build the unified option list and wire the combo box**

In `PlayerWindow`, add these helpers near `_populate_subtitle_combo()`:

```python
    def _current_item_external_subtitles(self) -> list[ExternalSubtitleOption]:
        current_item = self._current_play_item()
        if current_item is None:
            return []
        return list(current_item.external_subtitles)

    def _build_primary_subtitle_options(self, tracks: list[SubtitleTrack]) -> list[UnifiedSubtitleOption]:
        options: list[UnifiedSubtitleOption] = []
        for track in tracks:
            options.append(UnifiedSubtitleOption(label=track.label, mode="track", track_id=track.id))
        for subtitle in self._current_item_external_subtitles():
            options.append(
                UnifiedSubtitleOption(
                    label=subtitle.name,
                    mode="external",
                    external_subtitle=subtitle,
                )
            )
        return options
```

Update `_populate_subtitle_combo()` to populate from `_unified_primary_subtitle_options`:

```python
    def _populate_subtitle_combo(self, tracks: list[SubtitleTrack]) -> None:
        self._unified_primary_subtitle_options = self._build_primary_subtitle_options(tracks)
        self.subtitle_combo.blockSignals(True)
        self.subtitle_combo.clear()
        self.subtitle_combo.addItem("字幕", ("auto", None))
        if self._unified_primary_subtitle_options:
            self.subtitle_combo.addItem("关闭字幕", ("off", None))
            for option in self._unified_primary_subtitle_options:
                self.subtitle_combo.addItem(option.label, (option.mode, option.track_id, option.external_subtitle))
        self.subtitle_combo.setEnabled(bool(self._unified_primary_subtitle_options))
        self.subtitle_combo.setCurrentIndex(0)
        self.subtitle_combo.blockSignals(False)
```

- [ ] **Step 5: Run the focused player window tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_lists_bilibili_external_subtitles_after_embedded_tracks \
  tests/test_player_window_ui.py::test_player_window_does_not_auto_load_bilibili_external_subtitles_on_open \
  -q
```

Expected: PASS with Bilibili subtitle labels visible and no subtitle fetch during initial playback.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: expose bilibili subtitle options in player ui"
```

### Task 3: Load Bilibili External Subtitles For Primary And Secondary Slots

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing selection tests**

Add these tests after `test_player_window_user_selection_applies_selected_subtitle_track()` in `tests/test_player_window_ui.py`:

```python
def test_player_window_user_selection_loads_bilibili_subtitle_as_primary(qtbot, monkeypatch, tmp_path) -> None:
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

    monkeypatch.setattr(player_window_module.httpx, "get", lambda url, **kwargs: TextResponse("1\n00:00:00,000 --> 00:00:01,000\n你好\n"))
    session = PlayerSession(
        vod=VodItem(vod_id="BV1", vod_name="B站视频"),
        playlist=[PlayItem(title="第1话", url="http://m/1.m3u8", headers={"Referer": "https://www.bilibili.com/"}, external_subtitles=[
            ExternalSubtitleOption(name="中文 [B站]", lang="ai-zh", url="http://sub/zh.srt", format="application/x-subrip", source="bilibili"),
        ])],
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


def test_player_window_context_menu_loads_bilibili_subtitle_as_secondary(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[tuple[str, bool]] = []
            self.secondary_subtitle_apply_calls: list[tuple[str, int | None]] = []

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return None

        def apply_secondary_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            self.secondary_subtitle_apply_calls.append((mode, track_id))
            return track_id

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append((path, select_for_secondary))
            return 101

        def position_seconds(self) -> int:
            return 0

    class TextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(player_window_module.httpx, "get", lambda url, **kwargs: TextResponse("1\n00:00:00,000 --> 00:00:01,000\nhello\n"))
    item = PlayItem(title="第1话", url="http://m/1.m3u8", headers={"Referer": "https://www.bilibili.com/"}, external_subtitles=[
        ExternalSubtitleOption(name="English [B站]", lang="ai-en", url="http://sub/en.srt", format="application/x-subrip", source="bilibili"),
    ])
    session = PlayerSession(vod=VodItem(vod_id="BV1", vod_name="B站视频"), playlist=[item], start_index=0, start_position_seconds=0, speed=1.0)
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)
    window._set_secondary_subtitle_from_menu("external", "http://sub/en.srt")

    assert [select_for_secondary for _path, select_for_secondary in window.video.loaded_external_subtitles] == [True]
    assert window.video.secondary_subtitle_apply_calls == [("track", 101)]
```

- [ ] **Step 2: Run the focused selection tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_user_selection_loads_bilibili_subtitle_as_primary \
  tests/test_player_window_ui.py::test_player_window_context_menu_loads_bilibili_subtitle_as_secondary \
  -q
```

Expected: FAIL because `PlayerWindow` cannot yet download and load Bilibili subtitle options.

- [ ] **Step 3: Implement external subtitle fetch/write/load helpers**

In `src/atv_player/ui/player_window.py`, add these helpers near the danmaku temp-file helpers:

```python
    def _write_external_subtitle_file(self, text: str, suffix: str) -> Path:
        temp_path = Path(Path.cwd(), f".atv-{time.time_ns()}{suffix}")
        temp_path.write_text(text, encoding="utf-8")
        return temp_path

    def _fetch_external_subtitle_text(self, subtitle: ExternalSubtitleOption) -> str:
        current_item = self._current_play_item()
        headers = {} if current_item is None else dict(current_item.headers)
        response = httpx.get(subtitle.url, headers=headers, timeout=10.0, follow_redirects=True)
        return str(getattr(response, "text", "") or "")

    def _load_bilibili_external_subtitle(
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
        if secondary:
            self._secondary_external_subtitle_path = subtitle_path
        else:
            self._primary_external_subtitle_path = subtitle_path
        return track_id, subtitle_path
```

- [ ] **Step 4: Route combo-box and context-menu selections through external subtitle loading**

Update `_change_subtitle_selection()` to handle tuple payloads with `mode == "external"`:

```python
        mode, track_id, external_subtitle = item_data
        if mode == "external" and external_subtitle is not None:
            loaded_track_id, _subtitle_path = self._load_bilibili_external_subtitle(external_subtitle, secondary=False)
            self._primary_external_subtitle_selection = ExternalSubtitleSelection(
                source=external_subtitle.source,
                option_url=external_subtitle.url,
            )
            self._primary_external_subtitle_track_id = loaded_track_id
            self.video.apply_subtitle_mode("track", track_id=loaded_track_id)
            return
```

Update `_build_secondary_subtitle_menu()` to append Bilibili subtitle actions:

```python
        for subtitle in self._current_item_external_subtitles():
            action = menu.addAction(subtitle.name)
            action.setCheckable(True)
            action.setChecked(
                self._secondary_external_subtitle_selection is not None
                and self._secondary_external_subtitle_selection.option_url == subtitle.url
            )
            action.triggered.connect(
                lambda _checked=False, subtitle_url=subtitle.url: self._set_secondary_subtitle_from_menu("external", subtitle_url)
            )
            group.addAction(action)
```

Update `_set_secondary_subtitle_from_menu()` to handle `"external"`:

```python
        if mode == "external":
            subtitle = next((item for item in self._current_item_external_subtitles() if item.url == track_id), None)
            if subtitle is None:
                return
            loaded_track_id, _subtitle_path = self._load_bilibili_external_subtitle(subtitle, secondary=True)
            self._secondary_external_subtitle_selection = ExternalSubtitleSelection(
                source=subtitle.source,
                option_url=subtitle.url,
            )
            self._secondary_external_subtitle_track_id = loaded_track_id
            self.video.apply_secondary_subtitle_mode("track", track_id=loaded_track_id)
            return
```

- [ ] **Step 5: Run the focused selection tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_user_selection_loads_bilibili_subtitle_as_primary \
  tests/test_player_window_ui.py::test_player_window_context_menu_loads_bilibili_subtitle_as_secondary \
  -q
```

Expected: PASS with primary and secondary Bilibili subtitle loading routed through `sub-add`.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: load bilibili subtitles into player slots"
```

### Task 4: Clean Up External Subtitle Tracks And Preserve Danmaku Isolation

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing cleanup and failure tests**

Add these tests after the new selection tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_unloads_primary_bilibili_subtitle_when_switching_to_off(qtbot) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.subtitle_apply_calls: list[tuple[str, int | None]] = []
            self.removed_track_ids: list[int] = []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            self.subtitle_apply_calls.append((mode, track_id))
            return None

        def remove_subtitle_track(self, track_id: int | None) -> None:
            if track_id is not None:
                self.removed_track_ids.append(track_id)

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window._primary_external_subtitle_track_id = 91

    window._change_subtitle_selection = PlayerWindow._change_subtitle_selection.__get__(window, PlayerWindow)
    window._primary_external_subtitle_selection = ExternalSubtitleSelection(source="bilibili", option_url="http://sub/zh.srt")
    window._clear_primary_external_subtitle()

    assert window.video.removed_track_ids == [91]


def test_player_window_clears_bilibili_subtitle_tracks_when_episode_changes_without_removing_danmaku(qtbot) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.removed_track_ids: list[int] = []

        def remove_subtitle_track(self, track_id: int | None) -> None:
            if track_id is not None:
                self.removed_track_ids.append(track_id)

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window._primary_external_subtitle_track_id = 91
    window._secondary_external_subtitle_track_id = 101
    window._danmaku_track_id = 77

    window._clear_external_subtitle_tracks()

    assert window.video.removed_track_ids == [91, 101]
    assert window._danmaku_track_id == 77


def test_player_window_logs_bilibili_subtitle_failure_without_interrupting_playback(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            return None

        def position_seconds(self) -> int:
            return 0

    monkeypatch.setattr(player_window_module.httpx, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    session = PlayerSession(
        vod=VodItem(vod_id="BV1", vod_name="B站视频"),
        playlist=[PlayItem(title="第1话", url="http://m/1.m3u8", external_subtitles=[
            ExternalSubtitleOption(name="中文 [B站]", lang="ai-zh", url="http://sub/zh.srt", format="application/x-subrip", source="bilibili"),
        ])],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)

    window.subtitle_combo.setCurrentIndex(2)

    assert "字幕切换失败: boom" in window.log_view.toPlainText()
```

- [ ] **Step 2: Run the focused cleanup tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_unloads_primary_bilibili_subtitle_when_switching_to_off \
  tests/test_player_window_ui.py::test_player_window_clears_bilibili_subtitle_tracks_when_episode_changes_without_removing_danmaku \
  tests/test_player_window_ui.py::test_player_window_logs_bilibili_subtitle_failure_without_interrupting_playback \
  -q
```

Expected: FAIL because the external subtitle cleanup helpers and failure fallback do not exist yet.

- [ ] **Step 3: Add explicit cleanup helpers**

In `src/atv_player/ui/player_window.py`, add these helpers near `_clear_active_danmaku()`:

```python
    def _clear_primary_external_subtitle(self) -> None:
        if self._primary_external_subtitle_track_id is not None and hasattr(self.video, "remove_subtitle_track"):
            self.video.remove_subtitle_track(self._primary_external_subtitle_track_id)
        self._primary_external_subtitle_track_id = None
        self._primary_external_subtitle_selection = None
        self._primary_external_subtitle_path = None

    def _clear_secondary_external_subtitle(self) -> None:
        if self._secondary_external_subtitle_track_id is not None and hasattr(self.video, "remove_subtitle_track"):
            self.video.remove_subtitle_track(self._secondary_external_subtitle_track_id)
        self._secondary_external_subtitle_track_id = None
        self._secondary_external_subtitle_selection = None
        self._secondary_external_subtitle_path = None

    def _clear_external_subtitle_tracks(self) -> None:
        self._clear_primary_external_subtitle()
        self._clear_secondary_external_subtitle()
```

Call `_clear_external_subtitle_tracks()` at the top of `_load_current_item()` after `_clear_active_danmaku()`.

Update `_change_subtitle_selection()`:

```python
        if mode == "auto":
            self._clear_primary_external_subtitle()
            self._subtitle_preference = SubtitlePreference()
            self._mark_manual_subtitle_switch_refresh()
            self.video.apply_subtitle_mode("auto")
            return
        if mode == "off":
            self._clear_primary_external_subtitle()
            self._subtitle_preference = SubtitlePreference(mode="off")
            self._mark_manual_subtitle_switch_refresh()
            self.video.apply_subtitle_mode("off")
            return
```

Update `_set_secondary_subtitle_from_menu()`:

```python
        if mode == "off":
            self._clear_secondary_external_subtitle()
            self._secondary_subtitle_preference = SecondarySubtitlePreference()
            self.video.apply_secondary_subtitle_mode("off")
            return
```

- [ ] **Step 4: Make external subtitle failures safe**

Wrap the external loading branch inside `_change_subtitle_selection()` and `_set_secondary_subtitle_from_menu()`:

```python
        try:
            loaded_track_id, _subtitle_path = self._load_bilibili_external_subtitle(external_subtitle, secondary=False)
        except Exception as exc:
            self._clear_primary_external_subtitle()
            self._append_log(f"字幕切换失败: {exc}")
            self.subtitle_combo.setCurrentIndex(0)
            return
```

and:

```python
        try:
            loaded_track_id, _subtitle_path = self._load_bilibili_external_subtitle(subtitle, secondary=True)
        except Exception as exc:
            self._clear_secondary_external_subtitle()
            self._append_log(f"次字幕切换失败: {exc}")
            return
```

- [ ] **Step 5: Run the focused cleanup tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_player_window_ui.py::test_player_window_unloads_primary_bilibili_subtitle_when_switching_to_off \
  tests/test_player_window_ui.py::test_player_window_clears_bilibili_subtitle_tracks_when_episode_changes_without_removing_danmaku \
  tests/test_player_window_ui.py::test_player_window_logs_bilibili_subtitle_failure_without_interrupting_playback \
  -q
```

Expected: PASS with slot-specific cleanup and failure fallback.

- [ ] **Step 6: Run the full targeted subtitle suites**

Run:

```bash
uv run pytest tests/test_bilibili_controller.py tests/test_player_window_ui.py -k "subtitle or bilibili" -q
```

Expected: PASS for the new Bilibili subtitle flow and existing subtitle-related behavior.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: clean up bilibili subtitle tracks safely"
```

## Self-Review

- Spec coverage:
  - `subs` parsing is covered by Task 1.
  - Unified subtitle UI with no auto-enable is covered by Task 2.
  - Primary and secondary Bilibili subtitle selection is covered by Task 3.
  - Slot-specific cleanup, episode changes, danmaku isolation, and safe fallback are covered by Task 4.
- Placeholder scan:
  - No `TODO`, `TBD`, “similar to”, or “write tests for the above” placeholders remain.
- Type consistency:
  - The plan consistently uses `ExternalSubtitleOption`, `ExternalSubtitleSelection`, `UnifiedSubtitleOption`, `_primary_external_subtitle_track_id`, `_secondary_external_subtitle_track_id`, `_clear_primary_external_subtitle()`, `_clear_secondary_external_subtitle()`, and `_clear_external_subtitle_tracks()`.
