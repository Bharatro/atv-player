# First Playback Optimization Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first phase of startup UX improvements for playback: explicit startup states, built-in parser result caching, and failure recovery actions in the player window.

**Architecture:** Keep the existing `controller -> request -> player window` flow intact and add two narrow support modules under `src/atv_player/player/`: one for startup state modeling and one for parser-result caching. Integrate those modules into `BuiltInPlaybackParserService` and `PlayerWindow` without moving playback ownership out of the existing UI layer.

**Tech Stack:** Python 3.12+, PySide6, pytest, pytest-qt, existing `atv_player` player/parsing modules

---

## File Structure

- Create: `src/atv_player/player/startup.py`
  - Own the startup stages, failure action model, and a small coordinator that returns immutable state payloads for the UI.
- Create: `src/atv_player/player/resolve_cache.py`
  - Own the short-lived cache for built-in parser results with a TTL-based in-memory implementation.
- Modify: `src/atv_player/playback_parsers.py`
  - Inject the resolve cache into `BuiltInPlaybackParserService` and reuse cached built-in parser results before issuing network requests.
- Modify: `src/atv_player/ui/player_window.py`
  - Add startup status UI, drive startup-state transitions from the existing async loading/prepare hooks, and expose retry / switch-line / switch-parser actions after failures.
- Create: `tests/test_playback_startup.py`
  - Unit-test the startup coordinator in isolation.
- Modify: `tests/test_playback_parsers.py`
  - Add cache-hit and cache-expiry coverage for built-in parser resolution.
- Modify: `tests/test_player_window_ui.py`
  - Add UI tests for startup-state rendering and failure action visibility/click behavior.

### Task 1: Startup State Domain Module

**Files:**
- Create: `src/atv_player/player/startup.py`
- Test: `tests/test_playback_startup.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.player.startup import (
    PlaybackFailureAction,
    PlaybackStartupCoordinator,
    PlaybackStartupStage,
)


def test_startup_coordinator_builds_progressive_states() -> None:
    coordinator = PlaybackStartupCoordinator()

    assert coordinator.preparing().stage is PlaybackStartupStage.PREPARING
    assert coordinator.preparing().message == "正在准备播放项"
    assert coordinator.resolving().stage is PlaybackStartupStage.RESOLVING
    assert coordinator.connecting().stage is PlaybackStartupStage.CONNECTING
    assert coordinator.buffering().stage is PlaybackStartupStage.BUFFERING
    assert coordinator.playing().stage is PlaybackStartupStage.PLAYING
    assert coordinator.playing().actions == ()


def test_startup_coordinator_builds_failure_actions_for_parse_item_with_multiple_lines() -> None:
    coordinator = PlaybackStartupCoordinator()

    state = coordinator.failed(
        message="当前线路响应超时",
        parse_required=True,
        has_multiple_sources=True,
    )

    assert state.stage is PlaybackStartupStage.FAILED
    assert state.message == "当前线路响应超时"
    assert state.actions == (
        PlaybackFailureAction(key="retry", label="重试"),
        PlaybackFailureAction(key="switch_line", label="换线路"),
        PlaybackFailureAction(key="switch_parser", label="换解析器"),
    )


def test_startup_coordinator_omits_unavailable_failure_actions() -> None:
    coordinator = PlaybackStartupCoordinator()

    state = coordinator.failed(
        message="解析器未返回可播放地址",
        parse_required=False,
        has_multiple_sources=False,
    )

    assert state.actions == (
        PlaybackFailureAction(key="retry", label="重试"),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_playback_startup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.player.startup'`

- [ ] **Step 3: Write the minimal startup state implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlaybackStartupStage(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    RESOLVING = "resolving"
    CONNECTING = "connecting"
    BUFFERING = "buffering"
    PLAYING = "playing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlaybackFailureAction:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class PlaybackStartupState:
    stage: PlaybackStartupStage
    message: str = ""
    actions: tuple[PlaybackFailureAction, ...] = ()


class PlaybackStartupCoordinator:
    def idle(self) -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.IDLE)

    def preparing(self, message: str = "正在准备播放项") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.PREPARING, message=message)

    def resolving(self, message: str = "正在解析播放地址") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.RESOLVING, message=message)

    def connecting(self, message: str = "正在连接视频源") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.CONNECTING, message=message)

    def buffering(self, message: str = "正在等待首帧") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.BUFFERING, message=message)

    def playing(self, message: str = "播放中") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.PLAYING, message=message)

    def failed(
        self,
        *,
        message: str,
        parse_required: bool,
        has_multiple_sources: bool,
    ) -> PlaybackStartupState:
        actions = [PlaybackFailureAction(key="retry", label="重试")]
        if has_multiple_sources:
            actions.append(PlaybackFailureAction(key="switch_line", label="换线路"))
        if parse_required:
            actions.append(PlaybackFailureAction(key="switch_parser", label="换解析器"))
        return PlaybackStartupState(
            stage=PlaybackStartupStage.FAILED,
            message=message,
            actions=tuple(actions),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_playback_startup.py -v`
Expected: PASS with `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_playback_startup.py src/atv_player/player/startup.py
git commit -m "feat: add playback startup state coordinator"
```

### Task 2: Built-in Parser Result Cache

**Files:**
- Create: `src/atv_player/player/resolve_cache.py`
- Modify: `src/atv_player/playback_parsers.py`
- Test: `tests/test_playback_parsers.py`

- [ ] **Step 1: Write the failing tests**

```python
from atv_player.playback_parsers import BuiltInPlaybackParserService
from atv_player.player.resolve_cache import PlaybackResolveCache


def test_parser_service_reuses_cached_result_for_same_parser() -> None:
    calls: list[str] = []

    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        calls.append(url)
        return httpx.Response(
            200,
            json={
                "parse": 0,
                "jx": 0,
                "url": "https://media.example/real.m3u8",
                "header": {"Referer": "https://site.example"},
            },
        )

    cache = PlaybackResolveCache(ttl_seconds=300.0, now=lambda: 100.0)
    service = BuiltInPlaybackParserService(get=fake_get, resolve_cache=cache)

    first = service.resolve("qq", "https://site.example/play?id=2", preferred_key="fish")
    second = service.resolve("qq", "https://site.example/play?id=2", preferred_key="fish")

    assert first.url == "https://media.example/real.m3u8"
    assert second.url == "https://media.example/real.m3u8"
    assert second.headers == {"Referer": "https://site.example"}
    assert calls == ["https://kalbim.xatut.top/kalbim2025/781718/play/video_player.php"]


def test_parser_service_re_resolves_after_cache_expiry() -> None:
    calls: list[str] = []
    clock = {"now": 100.0}

    def fake_get(url: str, params: dict[str, str], headers: dict[str, str], timeout: float, follow_redirects: bool):
        calls.append(url)
        return httpx.Response(
            200,
            json={
                "parse": 0,
                "jx": 0,
                "url": "https://media.example/real.m3u8",
            },
        )

    cache = PlaybackResolveCache(ttl_seconds=5.0, now=lambda: clock["now"])
    service = BuiltInPlaybackParserService(get=fake_get, resolve_cache=cache)

    service.resolve("qq", "https://site.example/play?id=5", preferred_key="fish")
    clock["now"] = 110.0
    service.resolve("qq", "https://site.example/play?id=5", preferred_key="fish")

    assert calls == [
        "https://kalbim.xatut.top/kalbim2025/781718/play/video_player.php",
        "https://kalbim.xatut.top/kalbim2025/781718/play/video_player.php",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_playback_parsers.py -k "reuses_cached_result or re_resolves_after_cache_expiry" -v`
Expected: FAIL with `ModuleNotFoundError` for `atv_player.player.resolve_cache` or `TypeError` because `BuiltInPlaybackParserService` does not accept `resolve_cache`

- [ ] **Step 3: Write the cache module and integrate it into the parser service**

```python
# src/atv_player/player/resolve_cache.py
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class ResolveCacheValue:
    url: str
    headers: dict[str, str]


@dataclass(slots=True)
class _ResolveCacheEntry:
    value: ResolveCacheValue
    expires_at: float


class PlaybackResolveCache:
    def __init__(self, ttl_seconds: float = 300.0, now: Callable[[], float] = monotonic) -> None:
        self._ttl_seconds = float(ttl_seconds)
        self._now = now
        self._entries: dict[tuple[str, str, str], _ResolveCacheEntry] = {}

    def _key(self, *, flag: str, url: str, parser_key: str) -> tuple[str, str, str]:
        return (flag.strip(), url.strip(), parser_key.strip())

    def get(self, *, flag: str, url: str, parser_key: str) -> ResolveCacheValue | None:
        key = self._key(flag=flag, url=url, parser_key=parser_key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._entries.pop(key, None)
            return None
        return entry.value

    def put(self, *, flag: str, url: str, parser_key: str, value: ResolveCacheValue) -> None:
        key = self._key(flag=flag, url=url, parser_key=parser_key)
        self._entries[key] = _ResolveCacheEntry(
            value=value,
            expires_at=self._now() + self._ttl_seconds,
        )
```

```python
# src/atv_player/playback_parsers.py
from atv_player.player.resolve_cache import PlaybackResolveCache, ResolveCacheValue


class BuiltInPlaybackParserService:
    def resolve(self, flag: str, url: str, preferred_key: str = "") -> BuiltInPlaybackParserResult:
        if not url.strip():
            raise ValueError("解析失败: 缺少待解析地址")
        errors: list[str] = []
        for parser in self._ordered_parsers(url, preferred_key):
            cached = self._resolve_cache.get(flag=flag, url=url, parser_key=parser.key)
            if cached is not None:
                return BuiltInPlaybackParserResult(
                    parser_key=parser.key,
                    parser_label=parser.label,
                    url=cached.url,
                    headers=dict(cached.headers),
                )
            try:
                result = self._resolve_with_parser(parser, flag, url)
            except Exception as exc:
                errors.append(f"{parser.key}: {exc}")
                continue
            self._resolve_cache.put(
                flag=flag,
                url=url,
                parser_key=parser.key,
                value=ResolveCacheValue(
                    url=result.url,
                    headers=dict(result.headers),
                ),
            )
            return result
        raise ValueError(f"解析失败: {'; '.join(errors)}")
```

```diff
diff --git a/src/atv_player/playback_parsers.py b/src/atv_player/playback_parsers.py
@@
-from Crypto.Cipher import AES
-from Crypto.Util.Padding import unpad
+from Crypto.Cipher import AES
+from Crypto.Util.Padding import unpad
+
+from atv_player.player.resolve_cache import PlaybackResolveCache, ResolveCacheValue
@@
-    def __init__(
-        self,
-        get: Callable[..., httpx.Response] = httpx.get,
-        post: Callable[..., httpx.Response] = httpx.post,
-    ) -> None:
+    def __init__(
+        self,
+        get: Callable[..., httpx.Response] = httpx.get,
+        post: Callable[..., httpx.Response] = httpx.post,
+        resolve_cache: PlaybackResolveCache | None = None,
+    ) -> None:
         self._get = get
         self._post = post
+        self._resolve_cache = resolve_cache or PlaybackResolveCache()
         self._parsers = [
             BuiltInPlaybackParser(
                 key="xm",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_playback_parsers.py -k "reuses_cached_result or re_resolves_after_cache_expiry" -v`
Expected: PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_playback_parsers.py src/atv_player/player/resolve_cache.py src/atv_player/playback_parsers.py
git commit -m "feat: cache built-in parser results"
```

### Task 3: Player Startup Status UI And Failure Actions

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing UI tests**

```python
def test_player_window_renders_failed_startup_actions_for_parse_item_with_multiple_lines(qtbot) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), playback_parser_service=FakeParserService())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(vod_id="vod-1", vod_name="测试剧"),
        playlist=[PlayItem(title="第1集", url="https://stream.example/1.m3u8", parse_required=True)],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        source_groups=[
            PlaybackSourceGroup(
                label="默认",
                sources=[
                    PlaybackSource(label="线路1", playlist=[PlayItem(title="第1集", url="https://stream.example/1.m3u8", parse_required=True)]),
                    PlaybackSource(label="线路2", playlist=[PlayItem(title="第1集", url="https://backup.example/1.m3u8", parse_required=True)]),
                ],
            )
        ],
    )

    window.open_session(session)
    window._show_failed_startup_state("当前线路响应超时")

    assert window.playback_startup_status_label.text() == "当前线路响应超时"
    assert window.playback_retry_button.isVisible() is True
    assert window.playback_switch_line_button.isVisible() is True
    assert window.playback_switch_parser_button.isVisible() is True


def test_player_window_retry_action_replays_current_item(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), playback_parser_service=FakeParserService())
    qtbot.addWidget(window)

    replay_calls: list[str] = []
    monkeypatch.setattr(window, "_replay_current_item", lambda: replay_calls.append("replayed"))

    window._show_failed_startup_state("解析器未返回可播放地址")
    window.playback_retry_button.click()

    assert replay_calls == ["replayed"]


def test_player_window_hides_failure_actions_when_video_becomes_visible(qtbot) -> None:
    window = PlayerWindow(FakePlayerController(), config=AppConfig(), playback_parser_service=FakeParserService())
    qtbot.addWidget(window)

    window._show_failed_startup_state("播放失败")
    assert window.playback_retry_button.isVisible() is True

    window._handle_video_picture_state_changed("visible")

    assert window.playback_startup_status_label.text() == "播放中"
    assert window.playback_retry_button.isVisible() is False
    assert window.playback_switch_line_button.isVisible() is False
    assert window.playback_switch_parser_button.isVisible() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "failed_startup_actions or retry_action_replays_current_item or hides_failure_actions_when_video_becomes_visible" -v`
Expected: FAIL with `AttributeError` because `PlayerWindow` does not expose `playback_startup_status_label`, `playback_retry_button`, or `_show_failed_startup_state`

- [ ] **Step 3: Add startup status UI and wire it into existing playback hooks**

```python
# src/atv_player/ui/player_window.py
from atv_player.player.startup import (
    PlaybackStartupCoordinator,
    PlaybackStartupStage,
    PlaybackStartupState,
)


class PlayerWindow(QWidget, AsyncGuardMixin):
    def __init__(self, controller, *, config=None, playback_parser_service=None, **kwargs) -> None:
        super().__init__()
        self.controller = controller
        self.config = config
        self._playback_parser_service = playback_parser_service
        self._startup_coordinator = PlaybackStartupCoordinator()
        self._startup_state = self._startup_coordinator.idle()

        self.playback_startup_widget = QWidget(self)
        self.playback_startup_widget.setObjectName("playbackStartupWidget")
        self.playback_startup_status_label = QLabel("")
        self.playback_retry_button = QPushButton("重试", self.playback_startup_widget)
        self.playback_switch_line_button = QPushButton("换线路", self.playback_startup_widget)
        self.playback_switch_parser_button = QPushButton("换解析器", self.playback_startup_widget)

        startup_layout = QHBoxLayout(self.playback_startup_widget)
        startup_layout.setContentsMargins(0, 0, 0, 0)
        startup_layout.addWidget(self.playback_startup_status_label, 1)
        startup_layout.addWidget(self.playback_retry_button)
        startup_layout.addWidget(self.playback_switch_line_button)
        startup_layout.addWidget(self.playback_switch_parser_button)

        self.playback_retry_button.clicked.connect(self._retry_failed_startup)
        self.playback_switch_line_button.clicked.connect(self._switch_line_after_failure)
        self.playback_switch_parser_button.clicked.connect(self._switch_parser_after_failure)
        self.playback_startup_widget.hide()

        # add the widget just above the playback log section in the existing sidebar layout

    def _set_startup_state(self, state: PlaybackStartupState) -> None:
        self._startup_state = state
        self.playback_startup_status_label.setText(state.message)
        action_keys = {action.key for action in state.actions}
        self.playback_retry_button.setVisible("retry" in action_keys)
        self.playback_switch_line_button.setVisible("switch_line" in action_keys)
        self.playback_switch_parser_button.setVisible("switch_parser" in action_keys)
        self.playback_startup_widget.setHidden(state.stage is PlaybackStartupStage.IDLE)

    def _has_multiple_playback_sources(self) -> bool:
        if self.session is None:
            return False
        source_groups = self._session_source_groups()
        return sum(len(group.sources) for group in source_groups) > 1

    def _show_failed_startup_state(self, message: str) -> None:
        self._set_startup_state(
            self._startup_coordinator.failed(
                message=message,
                parse_required=self._current_item_requires_parse(),
                has_multiple_sources=self._has_multiple_playback_sources(),
            )
        )

    def _retry_failed_startup(self) -> None:
        self._replay_current_item()

    def _switch_line_after_failure(self) -> None:
        if self.session is None:
            return
        source_groups = self._session_source_groups()
        current_group = source_groups[self.session.source_group_index]
        if self.session.source_index + 1 < len(current_group.sources):
            self._switch_active_source(self.session.source_group_index, self.session.source_index + 1)
            return
        if self.session.source_group_index + 1 < len(source_groups):
            self._switch_active_source(self.session.source_group_index + 1, 0)

    def _switch_parser_after_failure(self) -> None:
        if not self._current_item_requires_parse():
            return
        if self.parse_combo.count() <= 2:
            return
        current_index = max(1, self.parse_combo.currentIndex())
        next_index = current_index + 1
        if next_index >= self.parse_combo.count():
            next_index = 1
        if next_index == current_index:
            return
        self.parse_combo.setCurrentIndex(next_index)

    def _handle_play_item_resolve_failed(self, request_id: int, message: str) -> None:
        if request_id != self._play_item_request_id:
            return
        pending_load = self._pending_play_item_load
        self._pending_play_item_load = None
        if pending_load is not None and pending_load.wait_for_load:
            self._show_failed_startup_state(f"播放失败: {message}")
            self._restore_current_index(pending_load.previous_index)
            self._append_log(f"播放失败: {message}")
            return
        self._append_log(f"详情加载失败: {message}")

    def _handle_playback_loader_failed(self, request_id: int, message: str) -> None:
        if request_id != self._playback_loader_request_id:
            return
        pending_loader = self._pending_playback_loader
        self._pending_playback_loader = None
        if pending_loader is None:
            return
        self._show_failed_startup_state(f"播放失败: {message}")
        self._restore_or_keep_current_index_after_failure(pending_loader.previous_index)
        self._append_log(f"播放失败: {message}")

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
        self._show_failed_startup_state(f"播放失败: {message}")
```

```diff
diff --git a/src/atv_player/ui/player_window.py b/src/atv_player/ui/player_window.py
@@
-from atv_player.player.m3u8_ad_filter import M3U8AdFilter
+from atv_player.player.m3u8_ad_filter import M3U8AdFilter
+from atv_player.player.startup import PlaybackStartupCoordinator, PlaybackStartupStage, PlaybackStartupState
@@
         self._playback_parser_service = playback_parser_service
+        self._startup_coordinator = PlaybackStartupCoordinator()
+        self._startup_state = self._startup_coordinator.idle()
@@
         self.log_view = QTextEdit()
+        self.playback_startup_widget = QWidget(self)
+        self.playback_startup_widget.setObjectName("playbackStartupWidget")
+        self.playback_startup_status_label = QLabel("")
+        self.playback_retry_button = QPushButton("重试", self.playback_startup_widget)
+        self.playback_switch_line_button = QPushButton("换线路", self.playback_startup_widget)
+        self.playback_switch_parser_button = QPushButton("换解析器", self.playback_startup_widget)
+        startup_layout = QHBoxLayout(self.playback_startup_widget)
+        startup_layout.setContentsMargins(0, 0, 0, 0)
+        startup_layout.addWidget(self.playback_startup_status_label, 1)
+        startup_layout.addWidget(self.playback_retry_button)
+        startup_layout.addWidget(self.playback_switch_line_button)
+        startup_layout.addWidget(self.playback_switch_parser_button)
+        self.playback_startup_widget.hide()
@@
-        sidebar_layout.addWidget(self.log_container)
+        sidebar_layout.addWidget(self.playback_startup_widget)
+        sidebar_layout.addWidget(self.log_container)
@@
+        self.playback_retry_button.clicked.connect(self._retry_failed_startup)
+        self.playback_switch_line_button.clicked.connect(self._switch_line_after_failure)
+        self.playback_switch_parser_button.clicked.connect(self._switch_parser_after_failure)
@@
+    def _set_startup_state(self, state: PlaybackStartupState) -> None:
+        self._startup_state = state
+        self.playback_startup_status_label.setText(state.message)
+        action_keys = {action.key for action in state.actions}
+        self.playback_retry_button.setVisible("retry" in action_keys)
+        self.playback_switch_line_button.setVisible("switch_line" in action_keys)
+        self.playback_switch_parser_button.setVisible("switch_parser" in action_keys)
+        self.playback_startup_widget.setHidden(state.stage is PlaybackStartupStage.IDLE)
+
+    def _has_multiple_playback_sources(self) -> bool:
+        if self.session is None:
+            return False
+        return sum(len(group.sources) for group in self._session_source_groups()) > 1
+
+    def _show_failed_startup_state(self, message: str) -> None:
+        self._set_startup_state(
+            self._startup_coordinator.failed(
+                message=message,
+                parse_required=self._current_item_requires_parse(),
+                has_multiple_sources=self._has_multiple_playback_sources(),
+            )
+        )
+
+    def _retry_failed_startup(self) -> None:
+        self._replay_current_item()
+
+    def _switch_line_after_failure(self) -> None:
+        if self.session is None:
+            return
+        source_groups = self._session_source_groups()
+        active_group = source_groups[self.session.source_group_index]
+        if self.session.source_index + 1 < len(active_group.sources):
+            self._switch_active_source(self.session.source_group_index, self.session.source_index + 1)
+            return
+        if self.session.source_group_index + 1 < len(source_groups):
+            self._switch_active_source(self.session.source_group_index + 1, 0)
+
+    def _switch_parser_after_failure(self) -> None:
+        if not self._current_item_requires_parse():
+            return
+        if self.parse_combo.count() <= 2:
+            return
+        current_index = max(1, self.parse_combo.currentIndex())
+        next_index = current_index + 1
+        if next_index >= self.parse_combo.count():
+            next_index = 1
+        if next_index == current_index:
+            return
+        self.parse_combo.setCurrentIndex(next_index)
@@
     def _load_current_item(
         self,
         start_position_seconds: int = 0,
         pause: bool = False,
         *,
         previous_index: int | None = None,
         preserve_primary_external_subtitle_selection: bool = False,
     ) -> None:
         if self.session is None:
             return
+        self._set_startup_state(self._startup_coordinator.preparing())
         self._invalidate_play_item_resolution()
@@
     def _start_playback_loader(
         self,
         *,
         previous_index: int,
         start_position_seconds: int,
         pause: bool,
     ) -> None:
         if self.session is None or self.session.playback_loader is None:
             return
+        self._set_startup_state(self._startup_coordinator.resolving())
         current_item = self.session.playlist[self.current_index]
@@
     def _start_play_item_resolution(
         self,
         *,
         previous_index: int,
         start_position_seconds: int,
         pause: bool,
         wait_for_load: bool,
     ) -> None:
         if self.session is None:
             return
+        self._set_startup_state(self._startup_coordinator.resolving())
         session = self.session
@@
     def _start_current_item_playback(self, start_position_seconds: int = 0, pause: bool = False) -> None:
         if self.session is None:
             return
+        self._set_startup_state(self._startup_coordinator.connecting())
         current_item = self.session.playlist[self.current_index]
@@
     def _handle_video_picture_state_changed(self, state: str) -> None:
         self._video_picture_state = state
+        if state == "loading":
+            self._set_startup_state(self._startup_coordinator.buffering())
+        elif state in {"visible", "audio-cover"}:
+            self._set_startup_state(self._startup_coordinator.playing())
         if state in {"visible", "audio-cover"}:
             self._video_surface_ready = True
             self.video_poster_overlay.hide()
             return
@@
     def _handle_playback_failed(self, message: str) -> None:
+        self._show_failed_startup_state(message)
         self._append_log(message)
         self._video_surface_ready = False
@@
     def _handle_play_item_resolve_failed(self, request_id: int, message: str) -> None:
         if request_id != self._play_item_request_id:
             return
         pending_load = self._pending_play_item_load
         self._pending_play_item_load = None
         if pending_load is not None and pending_load.wait_for_load:
+            self._show_failed_startup_state(f"播放失败: {message}")
             self._restore_current_index(pending_load.previous_index)
             self._append_log(f"播放失败: {message}")
             return
@@
     def _handle_playback_loader_failed(self, request_id: int, message: str) -> None:
         if request_id != self._playback_loader_request_id:
             return
         pending_loader = self._pending_playback_loader
         self._pending_playback_loader = None
         if pending_loader is None:
             return
+        self._show_failed_startup_state(f"播放失败: {message}")
         self._restore_or_keep_current_index_after_failure(pending_loader.previous_index)
         self._append_log(f"播放失败: {message}")
@@
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
+        self._show_failed_startup_state(f"播放失败: {message}")
         if self._requires_prepared_media_url(pending_prepare.source_url):
             self._append_log(f"播放失败: {message}")
             self._restore_current_index(pending_prepare.previous_index)
             return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k "failed_startup_actions or retry_action_replays_current_item or hides_failure_actions_when_video_becomes_visible" -v`
Expected: PASS with `3 passed`

- [ ] **Step 5: Run the focused regression suite**

Run: `uv run pytest tests/test_playback_startup.py tests/test_playback_parsers.py tests/test_player_window_ui.py -k "startup or cached_result or cache_expiry or failed_startup_actions or retry_action_replays_current_item or hides_failure_actions_when_video_becomes_visible" -v`
Expected: PASS with all selected tests green and `0 failed`

- [ ] **Step 6: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: surface playback startup status and recovery actions"
```

## Self-Review

### Spec coverage

- Startup stage visibility: covered by Task 1 state model and Task 3 UI integration.
- Short-term built-in parser caching: covered by Task 2.
- Failure recovery actions: covered by Task 1 action model and Task 3 action buttons/handlers.
- Phase 1 scope only: this plan intentionally excludes prewarm, automatic fallback, and next-episode prefetch.

No spec gaps remain for phase 1.

### Placeholder scan

- Checked for `TODO`, `TBD`, vague “handle edge cases”, and unspecified test commands.
- All steps include exact file paths, test code, commands, and commit messages.

### Type consistency

- Startup state types are consistently named `PlaybackStartupStage`, `PlaybackStartupState`, `PlaybackFailureAction`, and `PlaybackStartupCoordinator`.
- Failure action keys are consistently `retry`, `switch_line`, and `switch_parser`.
- Cache types are consistently `PlaybackResolveCache` and `ResolveCacheValue`.
