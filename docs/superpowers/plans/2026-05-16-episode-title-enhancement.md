# Episode Title Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral episode-title enhancement flow that can show `剧集标题` and `原始文件名` tabs above the player playlist, default to enhanced titles, and gate the feature behind a new advanced-settings switch.

**Architecture:** Keep title enhancement separate from metadata field merging. Persist only a global enable/disable switch in `AppConfig`, store both original and enhanced titles on `PlayItem`, and attach a dedicated asynchronous `episode_title_enhancer` callback to player requests/sessions. Start with TMDB as the first provider, but design the title model and helper layer so iqiyi/tencent/bilibili/plugin-native titles can reuse the same path without UI changes.

**Tech Stack:** Python 3.14, dataclasses, PySide6, pytest

---

## File Map

**Create:**
- `src/atv_player/episode_titles.py`
- `tests/test_episode_titles.py`

**Modify:**
- `src/atv_player/models.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/app.py`
- `src/atv_player/metadata/providers/tmdb_client.py`
- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_spider_plugin_controller.py`
- `tests/test_metadata_tmdb_client.py`
- `tests/test_app.py`

**Responsibilities:**
- `src/atv_player/episode_titles.py`
  - source-neutral helpers for storing original titles, applying enhanced titles with priority, deciding whether tabs should be shown, and formatting playlist labels for each tab
- `src/atv_player/models.py`
  - persistent config flag plus request/session/item fields
- `src/atv_player/controllers/player_controller.py`
  - carry the new enhancer callback from `OpenPlayerRequest` into `PlayerSession`
- `src/atv_player/ui/advanced_settings_dialog.py`
  - expose and save the new switch
- `src/atv_player/ui/player_window.py`
  - render the tab UI, run the enhancer asynchronously, and update active playlist labels without changing playback index
- `src/atv_player/plugins/controller.py`
  - seed `original_title` on all built/replacement `PlayItem`s and attach the enhancer factory to plugin detail requests
- `src/atv_player/app.py`
  - build the enhancer factory when the config switch and TMDB API key are enabled
- `src/atv_player/metadata/providers/tmdb_client.py`
  - fetch TMDB season detail data for episode-title enhancement

### Task 1: Add config, request/session, and item title fields

**Files:**
- Create: none
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing advanced-settings tests**

```python
def test_advanced_settings_dialog_loads_episode_title_enhancement_checkbox(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(
        metadata_enhancement_enabled=True,
        metadata_tmdb_api_key="tmdb-demo-key",
        episode_title_enhancement_enabled=True,
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.episode_title_enhancement_checkbox.isChecked() is True
    assert dialog.episode_title_enhancement_checkbox.isEnabled() is True


def test_advanced_settings_dialog_saves_episode_title_enhancement_checkbox(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved: list[AppConfig] = []
    config = AppConfig(metadata_enhancement_enabled=True)
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.episode_title_enhancement_checkbox.setChecked(True)
    dialog.save_button.click()

    assert saved[-1].episode_title_enhancement_enabled is True
```

- [ ] **Step 2: Run the focused settings tests and verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "episode_title_enhancement_checkbox" -q`

Expected: FAIL because `AppConfig` and `AdvancedSettingsDialog` do not yet define `episode_title_enhancement_enabled` or the checkbox widget.

- [ ] **Step 3: Add the config, item, request, and session fields**

```python
@dataclass(slots=True)
class AppConfig:
    metadata_enhancement_enabled: bool = True
    metadata_douban_cookie: str = ""
    metadata_tmdb_api_key: str = ""
    episode_title_enhancement_enabled: bool = False
```

```python
@dataclass(slots=True)
class PlayItem:
    title: str
    url: str
    original_title: str = ""
    episode_display_title: str = ""
    episode_title_source: str = ""
```

```python
metadata_hydrator: Callable[[object], VodItem | None] | None = None
episode_title_enhancer: Callable[[object], list[PlayItem] | None] | None = None
danmaku_controller: object | None = None
```

```python
metadata_hydrator: Callable[[object], VodItem | None] | None = None
metadata_hydrated: bool = False
episode_title_enhancer: Callable[[object], list[PlayItem] | None] | None = None
episode_titles_hydrated: bool = False
danmaku_controller: object | None = None
```

```python
session = PlayerSession(
    vod=vod,
    playlist=active_playlist,
    start_index=start_index,
    start_position_seconds=position_seconds,
    speed=speed,
    metadata_hydrator=metadata_hydrator,
    episode_title_enhancer=episode_title_enhancer,
    danmaku_controller=danmaku_controller,
)
```

- [ ] **Step 4: Add the advanced-settings checkbox and wire save/load**

```python
self.episode_title_enhancement_checkbox = QCheckBox("启用剧集标题增强")
self.episode_title_enhancement_checkbox.setChecked(config.episode_title_enhancement_enabled)
metadata_layout.addRow(self.episode_title_enhancement_checkbox)
self.episode_title_enhancement_checkbox.setEnabled(enabled)
self._config.episode_title_enhancement_enabled = self.episode_title_enhancement_checkbox.isChecked()
```

- [ ] **Step 5: Run the focused settings tests and verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "episode_title_enhancement_checkbox" -q`

Expected: PASS with 2 selected tests.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/models.py src/atv_player/controllers/player_controller.py src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add episode title enhancement config"
```

### Task 2: Add provider-neutral episode-title helper functions

**Files:**
- Create: `src/atv_player/episode_titles.py`
- Test: `tests/test_episode_titles.py`

- [ ] **Step 1: Write the failing helper tests**

```python
from atv_player.episode_titles import (
    apply_episode_title_map,
    playlist_has_title_variants,
    playlist_item_display_title,
    seed_original_titles,
)
from atv_player.models import PlayItem


def test_seed_original_titles_only_fills_missing_original_title() -> None:
    playlist = [
        PlayItem(title="原文件A.mkv", url="http://a"),
        PlayItem(title="原文件B.mkv", url="http://b", original_title="保留值"),
    ]

    seed_original_titles(playlist)

    assert playlist[0].original_title == "原文件A.mkv"
    assert playlist[1].original_title == "保留值"


def test_apply_episode_title_map_uses_higher_priority_source() -> None:
    playlist = [PlayItem(title="01.mkv", url="http://a", original_title="01.mkv")]
    seed_original_titles(playlist)

    apply_episode_title_map(
        playlist,
        {1: "第1集 原始站点标题"},
        source="tencent",
        source_priority=["plugin", "tencent", "tmdb"],
    )
    apply_episode_title_map(
        playlist,
        {1: "第1集 TMDB标题"},
        source="tmdb",
        source_priority=["plugin", "tencent", "tmdb"],
    )

    assert playlist[0].episode_display_title == "第1集 原始站点标题"
    assert playlist[0].episode_title_source == "tencent"


def test_playlist_has_title_variants_requires_different_original_and_enhanced_titles() -> None:
    playlist = [PlayItem(title="第1集", url="http://a", original_title="第1集", episode_display_title="第1集")]

    assert playlist_has_title_variants(playlist) is False

    playlist[0].episode_display_title = "第1集 星门初启"

    assert playlist_has_title_variants(playlist) is True


def test_playlist_item_display_title_switches_between_modes() -> None:
    item = PlayItem(
        title="第1集 星门初启",
        url="http://a",
        original_title="S01E01.mkv",
        episode_display_title="第1集 星门初启",
    )

    assert playlist_item_display_title(item, "episode") == "第1集 星门初启"
    assert playlist_item_display_title(item, "original") == "S01E01.mkv"
```

- [ ] **Step 2: Run the focused helper tests and verify they fail**

Run: `uv run pytest tests/test_episode_titles.py -q`

Expected: FAIL because `src/atv_player/episode_titles.py` does not exist yet.

- [ ] **Step 3: Implement the minimal helper module**

```python
from __future__ import annotations

import re

from atv_player.models import PlayItem


def normalize_episode_title_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def seed_original_titles(playlist: list[PlayItem]) -> list[PlayItem]:
    for item in playlist:
        if not item.original_title.strip():
            item.original_title = item.title.strip()
    return playlist


def _source_rank(source: str, source_priority: list[str]) -> int:
    return source_priority.index(source) if source in source_priority else len(source_priority) + 100


def apply_episode_title_map(
    playlist: list[PlayItem],
    titles_by_episode: dict[int, str],
    *,
    source: str,
    source_priority: list[str],
) -> list[PlayItem]:
    seed_original_titles(playlist)
    for index, item in enumerate(playlist, start=1):
        candidate = str(titles_by_episode.get(index) or "").strip()
        if not candidate:
            continue
        if normalize_episode_title_text(candidate) == normalize_episode_title_text(item.original_title):
            continue
        if item.episode_display_title and _source_rank(source, source_priority) > _source_rank(item.episode_title_source, source_priority):
            continue
        item.episode_display_title = candidate
        item.episode_title_source = source
    return playlist


def playlist_has_title_variants(playlist: list[PlayItem]) -> bool:
    return any(
        item.original_title.strip()
        and item.episode_display_title.strip()
        and normalize_episode_title_text(item.original_title) != normalize_episode_title_text(item.episode_display_title)
        for item in playlist
    )


def playlist_item_display_title(item: PlayItem, mode: str) -> str:
    if mode == "original":
        return item.original_title.strip() or item.title.strip()
    return item.episode_display_title.strip() or item.title.strip() or item.original_title.strip()
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run: `uv run pytest tests/test_episode_titles.py -q`

Expected: PASS with 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/episode_titles.py tests/test_episode_titles.py
git commit -m "feat: add episode title enhancement helpers"
```

### Task 3: Add the player-side title tabs and async title-enhancer flow

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window tests**

```python
def test_player_window_shows_episode_title_tabs_when_playlist_has_title_variants(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="示例剧集"),
        playlist=[
            PlayItem(
                title="第1集 星门初启",
                url="https://media.example/1.mp4",
                vod_id="ep1",
                original_title="S01E01.mkv",
                episode_display_title="第1集 星门初启",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = type("FakeVideo", (), {"load": lambda *args, **kwargs: None, "set_speed": lambda *args, **kwargs: None, "set_volume": lambda *args, **kwargs: None, "position_seconds": lambda *args, **kwargs: 0})()

    window.open_session(session)

    assert window.playlist_title_tabs.isHidden() is False
    assert window.playlist_title_tabs.tabText(0) == "剧集标题"
    assert window.playlist_title_tabs.tabText(1) == "原始文件名"
    assert window.playlist_title_tabs.currentIndex() == 0
    assert window.playlist.item(0).text() == "第1集 星门初启"


def test_player_window_switches_playlist_labels_without_changing_current_index(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="示例剧集"),
        playlist=[
            PlayItem(title="第1集 星门初启", url="https://media.example/1.mp4", vod_id="ep1", original_title="S01E01.mkv", episode_display_title="第1集 星门初启"),
            PlayItem(title="第2集 星火初燃", url="https://media.example/2.mp4", vod_id="ep2", original_title="S01E02.mkv", episode_display_title="第2集 星火初燃"),
        ],
        start_index=1,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = type("FakeVideo", (), {"load": lambda *args, **kwargs: None, "set_speed": lambda *args, **kwargs: None, "set_volume": lambda *args, **kwargs: None, "position_seconds": lambda *args, **kwargs: 0})()

    window.open_session(session)
    window.playlist_title_tabs.setCurrentIndex(1)

    assert window.current_index == 1
    assert window.playlist.currentRow() == 1
    assert window.playlist.item(0).text() == "S01E01.mkv"
    assert window.playlist.item(1).text() == "S01E02.mkv"


def test_player_window_async_episode_title_enhancer_updates_playlist_labels_late(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="示例剧集"),
        playlist=[PlayItem(title="S01E01.mkv", url="https://media.example/1.mp4", vod_id="ep1", original_title="S01E01.mkv")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        episode_title_enhancer=lambda current_session: [
            PlayItem(
                title=current_session.playlist[0].title,
                url=current_session.playlist[0].url,
                vod_id=current_session.playlist[0].vod_id,
                original_title="S01E01.mkv",
                episode_display_title="第1集 星门初启",
                episode_title_source="tmdb",
            )
        ],
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = type("FakeVideo", (), {"load": lambda *args, **kwargs: None, "set_speed": lambda *args, **kwargs: None, "set_volume": lambda *args, **kwargs: None, "position_seconds": lambda *args, **kwargs: 0})()

    window.open_session(session)

    qtbot.waitUntil(lambda: window.playlist_title_tabs.isHidden() is False, timeout=1000)
    assert window.playlist.item(0).text() == "第1集 星门初启"
    assert window.current_index == 0
```

- [ ] **Step 2: Run the focused player-window tests and verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "playlist_title_tabs or async_episode_title_enhancer" -q`

Expected: FAIL because `PlayerWindow` has no title-tab widget or enhancer flow.

- [ ] **Step 3: Add the tab UI, title-mode state, and async enhancer signals**

```python
self.playlist_title_mode = "episode"
self.playlist_title_tabs = QTabBar()
self.playlist_title_tabs.addTab("剧集标题")
self.playlist_title_tabs.addTab("原始文件名")
self.playlist_title_tabs.setHidden(True)
sidebar_layout.addWidget(self.playlist_title_tabs)
self.playlist_title_tabs.currentChanged.connect(self._change_playlist_title_mode)
```

```python
class _EpisodeTitleEnhancementSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)


def _change_playlist_title_mode(self, index: int) -> None:
    self.playlist_title_mode = "original" if index == 1 else "episode"
    self._render_playlist_items()


def _render_playlist_title_tabs(self) -> None:
    playlist = list(self.session.playlist if self.session is not None else [])
    visible = playlist_has_title_variants(playlist)
    self.playlist_title_tabs.setHidden(not visible)
    if visible:
        self.playlist_title_tabs.blockSignals(True)
        self.playlist_title_tabs.setCurrentIndex(0 if self.playlist_title_mode == "episode" else 1)
        self.playlist_title_tabs.blockSignals(False)
```

```python
def _render_playlist_items(self) -> None:
    self.playlist.clear()
    if self.session is None:
        return
    for item in self.session.playlist:
        self.playlist.addItem(playlist_item_display_title(item, self.playlist_title_mode))
    self.playlist.setCurrentRow(self.current_index)
```

```python
def _start_episode_title_enhancement(self) -> None:
    if self.session is None or self.session.episode_title_enhancer is None or self.session.episode_titles_hydrated:
        return
    self._episode_title_request_id += 1
    request_id = self._episode_title_request_id
    pending_session = self.session
    self._pending_episode_title_session = pending_session
    self.session.episode_titles_hydrated = True

    def run() -> None:
        try:
            playlist = pending_session.episode_title_enhancer(pending_session)
        except Exception as exc:
            self._episode_title_enhancement_signals.failed.emit(request_id, str(exc))
            return
        self._episode_title_enhancement_signals.succeeded.emit(request_id, playlist)

    threading.Thread(target=run, daemon=True).start()
```

```python
def _handle_episode_title_enhancement_succeeded(self, request_id: int, playlist: list[PlayItem] | None) -> None:
    if request_id != self._episode_title_request_id:
        return
    pending_session = self._pending_episode_title_session
    self._pending_episode_title_session = None
    if self.session is None or pending_session is None or self.session is not pending_session or playlist is None:
        return
    self.session.playlist = playlist
    if 0 <= self.session.playlist_index < len(self.session.playlists):
        self.session.playlists[self.session.playlist_index] = playlist
    self.playlist_title_mode = "episode"
    self._render_playlist_title_tabs()
    self._render_playlist_items()
```

- [ ] **Step 4: Call the new tab/enhancer hooks during session open and playlist replacement**

```python
def open_session(self, session, start_paused: bool = False) -> None:
    self.session = session
    self.current_index = session.start_index
    self.playlist_title_mode = "episode"
    self._render_playlist_title_tabs()
    self._render_playlist_items()
    self._start_episode_title_enhancement()
```

```python
def _replace_current_playlist(self, playlist: list[PlayItem], replacement: list[PlayItem], start_index: int) -> None:
    self.session.playlist = replacement
    self.session.playlists[self.session.playlist_index] = replacement
    self.current_index = start_index
    self.playlist_title_mode = "episode"
    self._render_playlist_title_tabs()
    self._render_playlist_items()
    self._start_episode_title_enhancement()
```

- [ ] **Step 5: Run the focused player-window tests and verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "playlist_title_tabs or async_episode_title_enhancer" -q`

Expected: PASS with the new title-tab tests.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player episode title tabs"
```

### Task 4: Wire plugin playlists, add TMDB season titles, and attach the first enhancer factory

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/metadata/providers/tmdb_client.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `tests/test_metadata_tmdb_client.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing TMDB client, plugin-controller, and app-wiring tests**

```python
def test_tmdb_client_get_tv_season_detail_requests_language_and_season() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"season_number": 1, "episodes": [{"episode_number": 1, "name": "星门初启"}]})

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    detail = client.get_tv_season_detail("42", 1)

    assert detail["episodes"][0]["name"] == "星门初启"
    assert seen["path"] == "/3/tv/42/season/1"
    assert seen["query"]["language"] == "zh-CN"
```

```python
def test_spider_plugin_request_seeds_original_titles_for_playlist_items() -> None:
    controller = SpiderPluginController(FakeSpider(), plugin_name="红果短剧", search_enabled=True)

    request = controller.build_request("/detail/1")

    assert [item.original_title for item in request.playlist] == ["第1集", "第2集"]
```

```python
def test_app_coordinator_builds_episode_title_enhancer_only_when_switch_and_tmdb_key_are_enabled(tmp_path, monkeypatch) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(
                metadata_enhancement_enabled=True,
                metadata_tmdb_api_key="tmdb-key",
                episode_title_enhancement_enabled=True,
            )

    coordinator = AppCoordinator(FakeRepo())
    factory = coordinator._build_episode_title_enhancer_factory(object())

    enhance = factory(source_kind="plugin", vod=VodItem(vod_id="v1", vod_name="深空彼岸"))

    assert callable(enhance)
```

- [ ] **Step 2: Run the focused wiring tests and verify they fail**

Run: `uv run pytest tests/test_metadata_tmdb_client.py tests/test_spider_plugin_controller.py tests/test_app.py -k "season_detail or original_titles_for_playlist_items or episode_title_enhancer_factory" -q`

Expected: FAIL because the TMDB season endpoint, seeded `original_title`, and enhancer factory do not exist.

- [ ] **Step 3: Seed original titles in all plugin-built and replacement playlists**

```python
from atv_player.episode_titles import seed_original_titles

if playlist:
    playlists.append(_mark_short_bare_numeric_playlist(seed_original_titles(playlist)))
return _mark_short_bare_numeric_playlist(seed_original_titles([
    PlayItem(
        title=item.title,
        url=item.url,
        media_title=resolved_media_title,
        path=item.path,
        index=index,
        size=item.size,
        vod_id=item.vod_id,
        headers=dict(item.headers),
        play_source=play_source,
        type_name=detail.type_name or item.type_name,
        category_name=resolved_category_name or item.category_name,
    )
    for index, item in enumerate(playlist)
    if item.url and not _looks_like_drive_share_link(item.url)
]))
```

- [ ] **Step 4: Add TMDB season-detail support and the episode-title enhancer factory**

```python
class TMDBClient:
    def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, Any]:
        return self._request(f"/tv/{tmdb_id}/season/{season_number}")
```

```python
def _build_episode_title_enhancer_factory(self, api_client: ApiClient):
    del api_client

    def factory(*, source_kind: str = "", source_key: str = "", vod=None, raw_detail=None, request=None):
        del source_key, raw_detail, request
        config = self.repo.load_config()
        if vod is None or source_kind != "plugin":
            return None
        if not config.episode_title_enhancement_enabled or not config.metadata_tmdb_api_key:
            return None
        client = TMDBClient(api_key=config.metadata_tmdb_api_key)

        def enhance(session) -> list[PlayItem] | None:
            playlist = [replace(item) for item in getattr(session, "playlist", [])]
            seed_original_titles(playlist)
            vod = getattr(session, "vod", None)
            year = str(getattr(vod, "vod_year", "") or "").strip()
            matches = client.search_tv(str(getattr(vod, "vod_name", "") or "").strip(), year=year)
            if not matches:
                return None
            season_detail = client.get_tv_season_detail(matches[0]["id"], 1)
            titles_by_episode = {
                int(item.get("episode_number") or 0): f"第{int(item.get('episode_number') or 0)}集 {str(item.get('name') or '').strip()}".strip()
                for item in season_detail.get("episodes") or []
                if int(item.get("episode_number") or 0) > 0 and str(item.get("name") or "").strip()
            }
            updated = apply_episode_title_map(
                playlist,
                titles_by_episode,
                source="tmdb",
                source_priority=["plugin", "iqiyi", "tencent", "bilibili", "tmdb"],
            )
            return updated if playlist_has_title_variants(updated) else None

        return enhance

    return factory
```

```python
request = controller.build_request("/detail/1")
assert request.episode_title_enhancer is not None
```

- [ ] **Step 5: Wire the enhancer factory into plugin requests**

```python
class SpiderPluginController:
    def __init__(
        self,
        spider,
        plugin_name: str,
        search_enabled: bool,
        drive_detail_loader: Callable[[str], dict] | None = None,
        offline_download_detail_loader: Callable[[str], dict] | None = None,
        playback_history_loader: Callable[[str], object | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        playback_parser_service=None,
        yt_dlp_service=None,
        preferred_parse_key_loader: Callable[[], str] | None = None,
        danmaku_service=None,
        danmaku_preference_store=None,
        base_url_loader: Callable[[], str] | None = None,
        metadata_hydrator_factory: Callable[..., object] | None = None,
        episode_title_enhancer_factory: Callable[..., object] | None = None,
    ) -> None:
        self._episode_title_enhancer_factory = episode_title_enhancer_factory
```

```python
episode_title_enhancer = None
if self._episode_title_enhancer_factory is not None:
    episode_title_enhancer = self._episode_title_enhancer_factory(
        source_kind="plugin",
        source_key=self._plugin_name,
        vod=detail,
        raw_detail=raw_detail,
    )

return OpenPlayerRequest(
    vod=detail,
    playlist=playlist,
    playlists=playlists,
    playlist_index=0,
    metadata_hydrator=metadata_hydrator,
    episode_title_enhancer=episode_title_enhancer,
    danmaku_controller=self if self._danmaku_enabled and self._danmaku_service is not None else None,
)
```

```python
metadata_hydrator_factory = self._build_metadata_hydrator_factory(self._api_client)
episode_title_enhancer_factory = self._build_episode_title_enhancer_factory(self._api_client)
setattr(self._plugin_manager, "_episode_title_enhancer_factory", episode_title_enhancer_factory)
```

- [ ] **Step 6: Run the focused wiring tests and verify they pass**

Run: `uv run pytest tests/test_metadata_tmdb_client.py tests/test_spider_plugin_controller.py tests/test_app.py -k "season_detail or original_titles_for_playlist_items or episode_title_enhancer_factory" -q`

Expected: PASS for the new focused tests.

- [ ] **Step 7: Run the end-to-end regression slice**

Run: `uv run pytest tests/test_episode_titles.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_spider_plugin_controller.py tests/test_metadata_tmdb_client.py tests/test_app.py -k "episode_title or playlist_title_tabs or season_detail or original_titles_for_playlist_items" -q`

Expected: PASS, confirming the new config switch, playlist plumbing, player tabs, and TMDB seed path work together.

- [ ] **Step 8: Commit**

```bash
git add src/atv_player/plugins/controller.py src/atv_player/app.py src/atv_player/metadata/providers/tmdb_client.py tests/test_spider_plugin_controller.py tests/test_metadata_tmdb_client.py tests/test_app.py
git commit -m "feat: wire tmdb episode title enhancement"
```

## Self-Review

- Spec coverage:
  - Advanced-settings switch: Task 1
  - `PlayItem` original/enhanced title model: Tasks 1 and 2
  - Right-side player tabs with default `剧集标题`: Task 3
  - Replacement-playlist recalculation and non-persistent tab state: Task 3
  - Provider-neutral priority logic: Task 2
  - First source implementation with TMDB: Task 4
- Placeholder scan:
  - No `TODO`/`TBD` markers remain in the actionable steps.
  - Every task includes exact files, tests, commands, and commit boundaries.
- Type consistency:
  - The plan consistently uses `episode_title_enhancement_enabled`, `original_title`, `episode_display_title`, `episode_title_source`, and `episode_title_enhancer`.
  - `OpenPlayerRequest` and `PlayerSession` use the same callback name.
