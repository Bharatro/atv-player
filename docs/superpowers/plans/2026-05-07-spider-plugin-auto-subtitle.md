# Spider Plugin Auto Subtitle Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-enable a spider-plugin external subtitle only when the current media item has no embedded subtitle tracks, without overriding later user subtitle choices.

**Architecture:** Keep all changes inside the existing player subtitle state machine. Add a small amount of per-item auto-fallback state in `PlayerWindow`, trigger fallback from `_refresh_subtitle_state()` only when embedded tracks are absent and the primary preference is still `auto`, and suppress further auto-reapply once the user manually changes primary subtitle state through either the bottom combo box or the primary subtitle context menu.

**Tech Stack:** Python, PySide6, `pytest`, `uv`

---

### Task 1: Add failing player-window tests for spider subtitle auto-fallback

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_auto_loads_spider_subtitle_when_no_embedded_tracks(qtbot, monkeypatch) -> None:
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

    assert [select_for_secondary for _path, select_for_secondary in window.video.loaded_external_subtitles] == [False]
    assert window.video.subtitle_apply_calls == [("track", 91)]
    assert window.subtitle_combo.currentText() == "外挂字幕 [插件]"


def test_player_window_does_not_auto_load_spider_subtitle_when_embedded_tracks_exist(qtbot, monkeypatch) -> None:
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
            return [SubtitleTrack(id=11, title="", lang="zh", is_default=True, is_forced=False, label="中文 (默认)")]

        def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
            self.subtitle_apply_calls.append((mode, track_id))
            return 11 if mode == "auto" else track_id

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append((path, select_for_secondary))
            return 91

        def position_seconds(self) -> int:
            return 0

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("should not fetch spider subtitle when embedded tracks exist"),
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

    assert window.video.loaded_external_subtitles == []
    assert window.video.subtitle_apply_calls == [("auto", None)]
    assert window.subtitle_combo.currentText() == "字幕"


def test_player_window_does_not_auto_load_non_spider_external_subtitle_when_no_embedded_tracks(qtbot, monkeypatch) -> None:
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

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("should not auto-fetch non-spider subtitle"),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="bv1", vod_name="B站视频"),
        playlist=[
            PlayItem(
                title="第1话",
                url="http://m/1.m3u8",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="中文 [B站]",
                        lang="ai-zh",
                        url="http://sub/zh.srt",
                        format="application/x-subrip",
                        source="bilibili",
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

    assert window.video.loaded_external_subtitles == []
    assert window.video.subtitle_apply_calls == []
    assert window.subtitle_combo.currentText() == "字幕"


def test_player_window_does_not_reapply_auto_spider_subtitle_after_user_turns_subtitles_off(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[tuple[str, bool]] = []
            self.subtitle_apply_calls: list[tuple[str, int | None]] = []
            self.window = None

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

        def remove_subtitle_track(self, track_id: int | None) -> None:
            return None

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
    video = FakeVideo()
    video.window = window
    window.video = video

    window.open_session(session)
    window.video.subtitle_apply_calls.clear()
    window.video.loaded_external_subtitles.clear()

    window.subtitle_combo.setCurrentIndex(1)
    window.video_widget.subtitle_tracks_changed.emit()

    assert window.video.loaded_external_subtitles == []
    assert window.video.subtitle_apply_calls == [("off", None)]
    assert window.subtitle_combo.currentText() == "关闭字幕"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_auto_loads_spider_subtitle_when_no_embedded_tracks tests/test_player_window_ui.py::test_player_window_does_not_auto_load_spider_subtitle_when_embedded_tracks_exist tests/test_player_window_ui.py::test_player_window_does_not_auto_load_non_spider_external_subtitle_when_no_embedded_tracks tests/test_player_window_ui.py::test_player_window_does_not_reapply_auto_spider_subtitle_after_user_turns_subtitles_off -v`

Expected: `FAIL` because `PlayerWindow` currently never auto-loads spider subtitles when embedded tracks are absent, and it has no suppression state for later manual overrides.

- [ ] **Step 3: Commit the failing tests once they are in place locally**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover spider subtitle auto fallback"
```

Only do this commit if your workflow keeps red commits locally. If not, skip the commit and continue immediately to Task 2.

### Task 2: Implement spider subtitle auto-fallback in the player state machine

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add explicit per-item auto-fallback state**

Insert the following fields into `PlayerWindow.__init__()` alongside the existing subtitle state:

```python
        self._auto_spider_subtitle_suppressed = False
        self._auto_spider_subtitle_attempted_key: tuple[int, str] | None = None
```

Reset both fields at the start of `_load_current_item()` right after `self._clear_manual_subtitle_switch_refresh()`:

```python
        self._auto_spider_subtitle_suppressed = False
        self._auto_spider_subtitle_attempted_key = None
```

- [ ] **Step 2: Add helper methods for spider fallback eligibility and execution**

Add these methods near the current external subtitle helpers:

```python
    def _current_item_auto_spider_external_subtitles(self) -> list[ExternalSubtitleOption]:
        return [subtitle for subtitle in self._current_item_external_subtitles() if subtitle.source == "spider"]

    def _current_auto_spider_subtitle_attempt_key(self, subtitle: ExternalSubtitleOption) -> tuple[int, str]:
        current_item = self._current_play_item()
        return (id(current_item), subtitle.url)

    def _should_auto_apply_spider_subtitle(self) -> bool:
        if self._auto_spider_subtitle_suppressed:
            return False
        if self._subtitle_preference.mode != "auto":
            return False
        if self._subtitle_tracks:
            return False
        if self._primary_external_subtitle_track_id is not None and self._current_primary_external_subtitle() is not None:
            return False
        return bool(self._current_item_auto_spider_external_subtitles())

    def _auto_apply_spider_subtitle_if_needed(self) -> bool:
        if not self._should_auto_apply_spider_subtitle():
            return False
        subtitle = self._current_item_auto_spider_external_subtitles()[0]
        attempt_key = self._current_auto_spider_subtitle_attempt_key(subtitle)
        if self._auto_spider_subtitle_attempted_key == attempt_key:
            return False
        self._auto_spider_subtitle_attempted_key = attempt_key
        loaded_track_id, subtitle_path = self._load_external_subtitle(subtitle, secondary=False)
        self.video.apply_subtitle_mode("track", track_id=loaded_track_id)
        self._primary_external_subtitle_selection = ExternalSubtitleSelection(
            source=subtitle.source,
            option_url=subtitle.url,
        )
        self._primary_external_subtitle_track_id = loaded_track_id
        self._primary_external_subtitle_path = subtitle_path
        for index in range(self.subtitle_combo.count()):
            item_data = self.subtitle_combo.itemData(index)
            if (
                isinstance(item_data, tuple)
                and len(item_data) == 3
                and item_data[0] == "external"
                and getattr(item_data[2], "url", None) == subtitle.url
            ):
                self.subtitle_combo.blockSignals(True)
                try:
                    self.subtitle_combo.setCurrentIndex(index)
                finally:
                    self.subtitle_combo.blockSignals(False)
                break
        return True

    def _suppress_auto_spider_subtitle_for_current_item(self) -> None:
        self._auto_spider_subtitle_suppressed = True
```

- [ ] **Step 3: Trigger fallback from `_refresh_subtitle_state()` before the early return**

Replace the current early-return block:

```python
        if not self._subtitle_tracks:
            self._subtitle_preference = SubtitlePreference()
            return
```

with:

```python
        if not self._subtitle_tracks:
            try:
                if self._auto_apply_spider_subtitle_if_needed():
                    return
            except Exception as exc:
                self._append_log(f"字幕切换失败: {exc}")
                self._clear_primary_external_subtitle()
            self._subtitle_preference = SubtitlePreference()
            return
```

This is the only place where the player can reliably detect “no embedded subtitle tracks” during both initial playback and later mpv refreshes.

- [ ] **Step 4: Suppress future auto-reapply on manual primary subtitle changes**

At the start of `_change_subtitle_selection()`, after decoding `mode`, `track_id`, and `external_subtitle`, add:

```python
        self._suppress_auto_spider_subtitle_for_current_item()
```

Then preserve manual behavior exactly as-is for `auto`, `off`, `track`, and `external`.

Also suppress on right-click menu actions by adding the same call at the top of `_set_primary_subtitle_from_menu()`:

```python
        self._suppress_auto_spider_subtitle_for_current_item()
```

This keeps the context-menu path and bottom combo path consistent.

- [ ] **Step 5: Run the focused auto-fallback tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_auto_loads_spider_subtitle_when_no_embedded_tracks tests/test_player_window_ui.py::test_player_window_does_not_auto_load_spider_subtitle_when_embedded_tracks_exist tests/test_player_window_ui.py::test_player_window_does_not_auto_load_non_spider_external_subtitle_when_no_embedded_tracks tests/test_player_window_ui.py::test_player_window_does_not_reapply_auto_spider_subtitle_after_user_turns_subtitles_off -v`

Expected: `4 passed`

- [ ] **Step 6: Commit the implementation**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: auto load spider subtitles without embedded tracks"
```

### Task 3: Run subtitle regression coverage

**Files:**
- Modify: none
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the focused subtitle regression slice**

Run: `uv run pytest tests/test_player_window_ui.py -k "spider and subtitle or bilibili and subtitle or manual_subtitle_switch or secondary_subtitle" -v`

Expected: existing spider and Bilibili subtitle behavior still passes alongside the new auto-fallback tests.

- [ ] **Step 2: Run the full touched-module verification**

Run: `uv run pytest tests/test_player_window_ui.py -v`

Expected: `PASS` for the full player-window module, including existing subtitle, danmaku, and manual-switch tests.

- [ ] **Step 3: Commit only if Step 1 or Step 2 required follow-up edits**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "test: verify spider subtitle auto fallback"
```

Skip this commit if Task 2 already produced the final clean result without additional edits.
