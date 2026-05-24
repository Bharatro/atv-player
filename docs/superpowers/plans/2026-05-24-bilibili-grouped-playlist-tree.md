# Bilibili Grouped Playlist Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bilibili-only grouped playlist tree mode that renders Bilibili detail groups as expandable tree sections and plays items sequentially across all groups.

**Architecture:** Keep `BilibiliController` and `OpenPlayerRequest` semantics unchanged: Bilibili detail pages still open with grouped `request.playlists`. Implement the new behavior entirely in the player layer by persisting one global Bilibili setting, rendering either the existing `QListWidget` or a new `QTreeWidget`, and switching the active `session.playlist` between the current group playlist and a tree-flattened cross-group playlist when tree mode is enabled.

**Tech Stack:** Python 3.12, PySide6, sqlite3, pytest

---

## File Structure

- `src/atv_player/models.py`
  Responsibility: add the persisted Bilibili grouped-playlist-tree config field.
- `src/atv_player/storage.py`
  Responsibility: migrate, load, normalize, and save the new Bilibili tree-mode setting.
- `src/atv_player/ui/advanced_settings_dialog.py`
  Responsibility: expose the Bilibili tree-mode checkbox in playback settings and persist it through the existing save path.
- `src/atv_player/ui/player_window.py`
  Responsibility: add the Bilibili tree widget, render the correct playlist panel mode, map tree nodes to shared `PlayItem` objects, and switch the active session playlist to a cross-group flattened sequence while tree mode is active.
- `tests/test_storage.py`
  Responsibility: lock config persistence and migration defaults for the new setting.
- `tests/test_app.py`
  Responsibility: lock advanced-settings dialog save/restore behavior for the new checkbox.
- `tests/test_player_window_ui.py`
  Responsibility: lock tree rendering, tree clicks, cross-group `play_next()`, auto-advance, and tree-mode replacement-playlist remapping.

### Task 1: Persist The Bilibili Tree-Mode Setting

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing storage and dialog tests**

```python
def test_settings_repository_persists_bilibili_grouped_playlist_tree_enabled(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.bilibili_grouped_playlist_tree_enabled = True

    repo.save_config(config)
    loaded = SettingsRepository(tmp_path / "app.db").load_config()

    assert loaded.bilibili_grouped_playlist_tree_enabled is True


def test_settings_repository_defaults_missing_bilibili_grouped_playlist_tree_enabled_to_false(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                theme_mode TEXT NOT NULL DEFAULT 'system',
                logging_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                disabled_danmaku_provider_ids TEXT NOT NULL DEFAULT '[]',
                disabled_metadata_provider_ids TEXT NOT NULL DEFAULT '[]',
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                network_proxy_mode TEXT NOT NULL DEFAULT 'direct',
                network_proxy_url TEXT NOT NULL DEFAULT '',
                network_proxy_bypass_rules TEXT NOT NULL DEFAULT '[]',
                network_proxy_rules TEXT NOT NULL DEFAULT '[]',
                youtube_cookie_browser TEXT NOT NULL DEFAULT '',
                youtube_max_height INTEGER NOT NULL DEFAULT 1080,
                youtube_video_codec TEXT NOT NULL DEFAULT 'vp9',
                youtube_default_subtitle_lang TEXT NOT NULL DEFAULT '',
                youtube_default_audio_lang TEXT NOT NULL DEFAULT '',
                youtube_metadata_language TEXT NOT NULL DEFAULT '',
                youtube_region TEXT NOT NULL DEFAULT '',
                youtube_category_source_type TEXT NOT NULL DEFAULT 'builtin',
                youtube_category_source_value TEXT NOT NULL DEFAULT '',
                youtube_category_cache_json TEXT NOT NULL DEFAULT '',
                youtube_category_cache_refreshed_at INTEGER NOT NULL DEFAULT 0,
                youtube_category_cache_error TEXT NOT NULL DEFAULT '',
                mpv_cache_size_mb INTEGER NOT NULL DEFAULT 512,
                mpv_hwdec_mode TEXT NOT NULL DEFAULT 'auto-safe',
                mpv_network_timeout_seconds INTEGER NOT NULL DEFAULT 15,
                mpv_default_readahead_secs INTEGER NOT NULL DEFAULT 20,
                mpv_extra_options TEXT NOT NULL DEFAULT '',
                playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0,
                m3u_proxy_segment_prefetch_size INTEGER NOT NULL DEFAULT 2,
                last_path TEXT NOT NULL DEFAULT '/'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, theme_mode,
                logging_enabled, metadata_enhancement_enabled, episode_title_enhancement_enabled,
                disabled_danmaku_provider_ids, disabled_metadata_provider_ids,
                metadata_douban_cookie, metadata_tmdb_api_key, metadata_bangumi_access_token,
                network_proxy_mode, network_proxy_url, network_proxy_bypass_rules, network_proxy_rules,
                youtube_cookie_browser, youtube_max_height, youtube_video_codec,
                youtube_default_subtitle_lang, youtube_default_audio_lang, youtube_metadata_language,
                youtube_region, youtube_category_source_type, youtube_category_source_value,
                youtube_category_cache_json, youtube_category_cache_refreshed_at, youtube_category_cache_error,
                mpv_cache_size_mb, mpv_hwdec_mode, mpv_network_timeout_seconds,
                mpv_default_readahead_secs, mpv_extra_options,
                playback_auto_switch_source_on_failure, m3u_proxy_segment_prefetch_size, last_path
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', 'system',
                1, 1, 1, '[]', '[]', '', '', '', 'direct', '', '[]', '[]',
                '', 1080, 'vp9', '', '', '', '', 'builtin', '', '', 0, '',
                512, 'auto-safe', 15, 20, '', 0, 2, '/'
            )
            """
        )

    loaded = SettingsRepository(db_path).load_config()

    assert loaded.bilibili_grouped_playlist_tree_enabled is False
```

```python
def test_advanced_settings_dialog_saves_bilibili_grouped_playlist_tree_enabled(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig()
    save_calls: list[bool] = []
    dialog = AdvancedSettingsDialog(
        config,
        save_config=lambda: save_calls.append(config.bilibili_grouped_playlist_tree_enabled),
    )
    qtbot.addWidget(dialog)

    dialog.bilibili_grouped_playlist_tree_enabled_checkbox.setChecked(True)
    dialog._save()

    assert config.bilibili_grouped_playlist_tree_enabled is True
    assert save_calls == [True]


def test_advanced_settings_dialog_restores_bilibili_grouped_playlist_tree_enabled(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(
        AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(dialog)

    assert dialog.bilibili_grouped_playlist_tree_enabled_checkbox.isChecked() is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -k "bilibili_grouped_playlist_tree" tests/test_app.py -k "bilibili_grouped_playlist_tree" -v`

Expected: FAIL because `AppConfig`, `SettingsRepository`, and `AdvancedSettingsDialog` do not yet define `bilibili_grouped_playlist_tree_enabled`.

- [ ] **Step 3: Add the config field and storage normalization**

```python
@dataclass(slots=True)
class AppConfig:
    ...
    playback_auto_switch_source_on_failure: bool = False
    bilibili_grouped_playlist_tree_enabled: bool = False
    m3u_proxy_segment_prefetch_size: int = 2
    ...
```

```python
def _normalize_bilibili_grouped_playlist_tree_enabled(value: object) -> bool:
    return bool(value)
```

```python
CREATE TABLE IF NOT EXISTS app_config (
    ...
    playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0,
    bilibili_grouped_playlist_tree_enabled INTEGER NOT NULL DEFAULT 0,
    m3u_proxy_segment_prefetch_size INTEGER NOT NULL DEFAULT 2,
    ...
)
```

```python
if "bilibili_grouped_playlist_tree_enabled" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN bilibili_grouped_playlist_tree_enabled INTEGER NOT NULL DEFAULT 0"
    )
```

```python
SELECT
    ...
    playback_auto_switch_source_on_failure,
    bilibili_grouped_playlist_tree_enabled,
    m3u_proxy_segment_prefetch_size,
    ...
FROM app_config
WHERE id = 1
```

```python
return AppConfig(
    ...
    playback_auto_switch_source_on_failure=_normalize_playback_auto_switch_source_on_failure(
        playback_auto_switch_source_on_failure
    ),
    bilibili_grouped_playlist_tree_enabled=_normalize_bilibili_grouped_playlist_tree_enabled(
        bilibili_grouped_playlist_tree_enabled
    ),
    m3u_proxy_segment_prefetch_size=_normalize_m3u_proxy_segment_prefetch_size(
        m3u_proxy_segment_prefetch_size
    ),
    ...
)
```

```python
UPDATE app_config
SET
    ...
    playback_auto_switch_source_on_failure = ?,
    bilibili_grouped_playlist_tree_enabled = ?,
    m3u_proxy_segment_prefetch_size = ?,
    ...
WHERE id = 1
```

```python
(
    ...
    int(config.playback_auto_switch_source_on_failure),
    int(config.bilibili_grouped_playlist_tree_enabled),
    _normalize_m3u_proxy_segment_prefetch_size(config.m3u_proxy_segment_prefetch_size),
    ...
)
```

- [ ] **Step 4: Add the advanced-settings checkbox and save wiring**

```python
self.playback_auto_switch_source_on_failure_checkbox = QCheckBox("播放失败自动切换线路")
self.bilibili_grouped_playlist_tree_enabled_checkbox = QCheckBox("B站播放列表显示为分组树")
```

```python
self.bilibili_grouped_playlist_tree_enabled_checkbox.setChecked(
    config.bilibili_grouped_playlist_tree_enabled
)
```

```python
playback_layout = QFormLayout()
playback_layout.addRow(self.playback_auto_switch_source_on_failure_checkbox)
playback_layout.addRow(self.bilibili_grouped_playlist_tree_enabled_checkbox)
playback_layout.addRow("播放缓存大小（MB）", self.mpv_cache_size_edit)
...
```

```python
return (
    self.playback_auto_switch_source_on_failure_checkbox.isChecked(),
    self.bilibili_grouped_playlist_tree_enabled_checkbox.isChecked(),
    cache_size,
    str(self.mpv_hwdec_mode_combo.currentData() or "auto-safe"),
    timeout,
    readahead,
    prefetch_size,
    "\n".join(normalized_lines),
)
```

```python
(
    self._config.playback_auto_switch_source_on_failure,
    self._config.bilibili_grouped_playlist_tree_enabled,
    self._config.mpv_cache_size_mb,
    self._config.mpv_hwdec_mode,
    self._config.mpv_network_timeout_seconds,
    self._config.mpv_default_readahead_secs,
    self._config.m3u_proxy_segment_prefetch_size,
    self._config.mpv_extra_options,
) = playback_values
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -k "bilibili_grouped_playlist_tree" tests/test_app.py -k "bilibili_grouped_playlist_tree" -v`

Expected: PASS for the new storage and dialog tests, with no failures in the touched code paths.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py tests/test_storage.py tests/test_app.py
git commit -m "feat: persist bilibili grouped playlist tree setting"
```

### Task 2: Render The Bilibili Tree Playlist UI

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tree-rendering tests**

```python
def make_bilibili_grouped_session() -> PlayerSession:
    main_group = [PlayItem(title="正片", url="http://bili/main.mp4", vod_id="BV-main", play_source="BiliBili")]
    related_group = [
        PlayItem(title="相关1", url="http://bili/r1.mp4", vod_id="BV-r1", play_source="相关视频"),
        PlayItem(title="相关2", url="http://bili/r2.mp4", vod_id="BV-r2", play_source="相关视频"),
    ]
    up_group = [PlayItem(title="UP主1", url="http://bili/u1.mp4", vod_id="BV-u1", play_source="UP主视频")]
    return PlayerSession(
        vod=VodItem(vod_id="BV-main", vod_name="B站视频"),
        playlist=main_group,
        playlists=[main_group, related_group, up_group],
        playlist_index=0,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        source_kind="bilibili",
    )


def test_player_window_shows_bilibili_grouped_playlist_tree_when_enabled(qtbot) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    window.open_session(make_bilibili_grouped_session())

    assert window.playlist.isHidden() is True
    assert window.bilibili_playlist_tree.isHidden() is False
    assert window.playlist_group_combo.isHidden() is True
    assert window.bilibili_playlist_tree.topLevelItemCount() == 3
    assert window.bilibili_playlist_tree.topLevelItem(0).text(0) == "BiliBili"
    assert window.bilibili_playlist_tree.topLevelItem(1).text(0) == "相关视频"
    assert window.bilibili_playlist_tree.topLevelItem(2).text(0) == "UP主视频"


def test_player_window_keeps_plain_playlist_for_bilibili_when_tree_mode_disabled(qtbot) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=False),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    window.open_session(make_bilibili_grouped_session())

    assert window.playlist.isHidden() is False
    assert window.bilibili_playlist_tree.isHidden() is True
    assert window.playlist_group_combo.isHidden() is False


def test_player_window_ignores_bilibili_tree_mode_for_non_bilibili_sessions(qtbot) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    session = make_player_session(start_index=0)
    session.source_kind = "browse"
    window.open_session(session)

    assert window.playlist.isHidden() is False
    assert window.bilibili_playlist_tree.isHidden() is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_grouped_playlist_tree_when_enabled or plain_playlist_for_bilibili_when_tree_mode_disabled or ignores_bilibili_tree_mode_for_non_bilibili_sessions" -v`

Expected: FAIL because `PlayerWindow` does not yet define `bilibili_playlist_tree` or any Bilibili tree-mode rendering logic.

- [ ] **Step 3: Add the tree widget and render-mode helpers**

```python
self.playlist = QListWidget()
self.playlist.setSpacing(1)
...
self.bilibili_playlist_tree = QTreeWidget()
self.bilibili_playlist_tree.setHeaderHidden(True)
self.bilibili_playlist_tree.setIndentation(14)
self.bilibili_playlist_tree.setHidden(True)
self.bilibili_playlist_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
```

```python
self.bilibili_playlist_tree.itemClicked.connect(self._handle_bilibili_tree_item_clicked)
```

```python
sidebar_layout.addWidget(self.playlist)
sidebar_layout.addWidget(self.bilibili_playlist_tree)
```

```python
def _bilibili_grouped_playlist_tree_enabled(self) -> bool:
    return bool(
        self.config is not None
        and getattr(self.config, "bilibili_grouped_playlist_tree_enabled", False)
        and self.session is not None
        and str(getattr(self.session, "source_kind", "") or "").strip() == "bilibili"
        and len(self.session.playlists) > 1
    )


def _sync_playlist_panel_mode(self) -> None:
    tree_mode = self._bilibili_grouped_playlist_tree_enabled()
    self.playlist.setHidden(tree_mode)
    self.bilibili_playlist_tree.setHidden(not tree_mode)
    if tree_mode:
        self.playlist_group_combo.setHidden(True)
        self.playlist_source_combo.setHidden(True)
```

```python
def _render_playlist_panels(self) -> None:
    self._render_playlist_source_combos()
    self._render_playlist_title_tabs()
    self._render_playlist_items()
    self._render_bilibili_playlist_tree()
    self._sync_playlist_panel_mode()
```

- [ ] **Step 4: Render tree sections from `session.playlists`**

```python
def _render_bilibili_playlist_tree(self) -> None:
    self.bilibili_playlist_tree.clear()
    if self.session is None or not self._bilibili_grouped_playlist_tree_enabled():
        return
    for group_index, playlist in enumerate(self.session.playlists):
        if not playlist:
            continue
        group_item = QTreeWidgetItem([self._playlist_group_label(playlist, group_index)])
        group_item.setData(0, Qt.ItemDataRole.UserRole, ("group", group_index, -1))
        self.bilibili_playlist_tree.addTopLevelItem(group_item)
        group_item.setExpanded(True)
        for item_index, play_item in enumerate(playlist):
            leaf = QTreeWidgetItem([playlist_item_display_title(play_item, self.playlist_title_mode)])
            leaf.setData(0, Qt.ItemDataRole.UserRole, ("leaf", group_index, item_index))
            group_item.addChild(leaf)
```

```python
def _handle_bilibili_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
    payload = item.data(0, Qt.ItemDataRole.UserRole)
    if not isinstance(payload, tuple) or not payload or payload[0] != "leaf":
        item.setExpanded(not item.isExpanded())
        return
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_grouped_playlist_tree_when_enabled or plain_playlist_for_bilibili_when_tree_mode_disabled or ignores_bilibili_tree_mode_for_non_bilibili_sessions" -v`

Expected: PASS for the new render-mode tests, with the tree visible only for Bilibili sessions when the config is enabled.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: render bilibili grouped playlist tree"
```

### Task 3: Switch Playback To Cross-Group Tree Order

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing playback-order and replacement tests**

```python
def test_player_window_bilibili_tree_click_plays_leaf_item(qtbot) -> None:
    controller = RecordingPlayerController()
    window = PlayerWindow(
        controller,
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    window.open_session(make_bilibili_grouped_session())
    related_leaf = window.bilibili_playlist_tree.topLevelItem(1).child(1)

    window._handle_bilibili_tree_item_clicked(related_leaf, 0)

    assert window.session is not None
    assert window.session.playlist[window.current_index].title == "相关2"


def test_player_window_bilibili_tree_play_next_crosses_group_boundaries(qtbot) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    session = make_bilibili_grouped_session()
    session.playlist = session.playlists[1]
    session.playlist_index = 1
    session.start_index = 1
    window.open_session(session)

    window.play_next()

    assert window.session is not None
    assert window.session.playlist[window.current_index].title == "UP主1"


def test_player_window_bilibili_tree_auto_advance_crosses_group_boundaries(qtbot) -> None:
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    session = make_bilibili_grouped_session()
    session.playlist = session.playlists[0]
    session.playlist_index = 0
    session.start_index = 0
    window.open_session(session)

    window._handle_playback_finished()

    assert window.session is not None
    assert window.session.playlist[window.current_index].title == "相关1"


def test_player_window_bilibili_tree_rebuilds_flat_mapping_after_replacement(qtbot) -> None:
    main_group = [PlayItem(title="正片", url="", vod_id="BV-main", play_source="BiliBili")]
    related_group = [PlayItem(title="查看", url="", vod_id="BV-folder", play_source="相关视频")]
    session = PlayerSession(
        vod=VodItem(vod_id="BV-main", vod_name="B站视频"),
        playlist=related_group,
        playlists=[main_group, related_group],
        playlist_index=1,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        source_kind="bilibili",
        playback_loader=lambda item: PlaybackLoadResult(
            replacement_playlist=[
                PlayItem(title="相关A", url="http://m/a.mp4", vod_id="BV-a", play_source="相关视频"),
                PlayItem(title="相关B", url="http://m/b.mp4", vod_id="BV-b", play_source="相关视频"),
            ],
            replacement_start_index=1,
        ),
    )
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(bilibili_grouped_playlist_tree_enabled=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    window.open_session(session)

    assert window.session is not None
    assert [item.title for item in window.session.playlists[1]] == ["相关A", "相关B"]
    assert window.session.playlist[window.current_index].title == "相关B"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_tree_click_plays_leaf_item or bilibili_tree_play_next_crosses_group_boundaries or bilibili_tree_auto_advance_crosses_group_boundaries or bilibili_tree_rebuilds_flat_mapping_after_replacement" -v`

Expected: FAIL because tree clicks do not yet map to playable indexes and tree mode still uses the current group playlist instead of a flattened cross-group playlist.

- [ ] **Step 3: Add flat-tree playlist mapping helpers**

```python
def _build_bilibili_tree_flat_playlist(
    self,
) -> tuple[list[PlayItem], dict[int, int], dict[tuple[int, int], int]]:
    if self.session is None:
        return [], {}, {}
    flat_playlist: list[PlayItem] = []
    flat_index_by_item_id: dict[int, int] = {}
    flat_index_by_group_item: dict[tuple[int, int], int] = {}
    for group_index, playlist in enumerate(self.session.playlists):
        for item_index, play_item in enumerate(playlist):
            flat_index = len(flat_playlist)
            flat_playlist.append(play_item)
            flat_index_by_item_id[id(play_item)] = flat_index
            flat_index_by_group_item[(group_index, item_index)] = flat_index
    return flat_playlist, flat_index_by_item_id, flat_index_by_group_item
```

```python
def _activate_bilibili_tree_playlist(self) -> None:
    if self.session is None:
        return
    current_item = self.session.playlist[self.current_index] if 0 <= self.current_index < len(self.session.playlist) else None
    flat_playlist, flat_index_by_item_id, flat_index_by_group_item = self._build_bilibili_tree_flat_playlist()
    if not flat_playlist:
        return
    self._bilibili_tree_flat_index_by_item_id = flat_index_by_item_id
    self._bilibili_tree_flat_index_by_group_item = flat_index_by_group_item
    self._bilibili_tree_group_item_by_flat_index = {
        flat_index: group_item for group_item, flat_index in flat_index_by_group_item.items()
    }
    self.session.playlist = flat_playlist
    if current_item is None:
        self.current_index = 0
        return
    self.current_index = flat_index_by_item_id.get(id(current_item), 0)
```

```python
def _restore_bilibili_group_playlist(self) -> None:
    if self.session is None or not self.session.playlists:
        return
    group_index, item_index = self._bilibili_tree_group_item_by_flat_index.get(
        self.current_index,
        (self.session.playlist_index, 0),
    )
    self.session.playlist_index = max(0, min(group_index, len(self.session.playlists) - 1))
    self.session.playlist = self.session.playlists[self.session.playlist_index]
    self.current_index = max(0, min(item_index, len(self.session.playlist) - 1))
```

- [ ] **Step 4: Hook tree mode into `open_session()`, click playback, and replacements**

```python
def open_session(self, session, start_paused: bool = False) -> None:
    ...
    self.session = session
    self._bilibili_tree_flat_index_by_item_id = {}
    self._bilibili_tree_flat_index_by_group_item = {}
    self._bilibili_tree_group_item_by_flat_index = {}
    self.current_index = session.start_index
    if self._bilibili_grouped_playlist_tree_enabled():
        self._activate_bilibili_tree_playlist()
    self._render_playlist_panels()
    ...
```

```python
def _handle_bilibili_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
    payload = item.data(0, Qt.ItemDataRole.UserRole)
    if not isinstance(payload, tuple) or payload[0] != "leaf":
        item.setExpanded(not item.isExpanded())
        return
    if self.session is None:
        return
    flat_index = self._bilibili_tree_flat_index_by_group_item.get((payload[1], payload[2]))
    if flat_index is None or flat_index == self.current_index:
        return
    self.report_progress(force_remote_report=True)
    self._stop_current_playback()
    self._play_item_at_index(flat_index, preserve_primary_external_subtitle_selection=True)
```

```python
def _replace_playlist(self, replacement: list[PlayItem], replacement_start_index: int) -> None:
    ...
    if self._bilibili_grouped_playlist_tree_enabled():
        current_group_index, _ = self._bilibili_tree_group_item_by_flat_index.get(
            self.current_index,
            (self.session.playlist_index, 0),
        )
        self.session.playlists[current_group_index] = replacement
        self.session.playlist_index = current_group_index
        self._activate_bilibili_tree_playlist()
        self.current_index = self._bilibili_tree_flat_index_by_group_item.get(
            (current_group_index, replacement_start_index),
            self.current_index,
        )
        self._render_playlist_panels()
        return
    ...
```

- [ ] **Step 5: Refresh tree selection and visual state**

```python
def _sync_bilibili_tree_item_styles(self) -> None:
    if self.session is None or not self._bilibili_grouped_playlist_tree_enabled():
        return
    tokens = current_theme_manager().tokens_for(current_resolved_theme())
    for flat_index, (group_index, item_index) in self._bilibili_tree_group_item_by_flat_index.items():
        group_item = self.bilibili_playlist_tree.topLevelItem(group_index)
        if group_item is None or item_index >= group_item.childCount():
            continue
        leaf = group_item.child(item_index)
        font = leaf.font(0)
        if flat_index == self.current_index:
            leaf.setForeground(0, QBrush(QColor(tokens.accent)))
            font.setBold(True)
        elif flat_index < self.current_index:
            leaf.setForeground(0, QBrush(QColor(tokens.text_secondary)))
            font.setBold(False)
        else:
            leaf.setForeground(0, QBrush(QColor(tokens.text_primary)))
            font.setBold(False)
        leaf.setFont(0, font)
```

```python
def _render_bilibili_playlist_tree(self) -> None:
    ...
    self._sync_bilibili_tree_item_styles()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_tree_click_plays_leaf_item or bilibili_tree_play_next_crosses_group_boundaries or bilibili_tree_auto_advance_crosses_group_boundaries or bilibili_tree_rebuilds_flat_mapping_after_replacement" -v`

Expected: PASS for the tree-click, cross-group playback, and replacement-remapping tests.

- [ ] **Step 7: Run the broader player-window regression slice**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "route_replacement or play_next or bilibili_grouped_playlist_tree" -v`

Expected: PASS, including the pre-existing route replacement tests, proving that non-Bilibili playback and grouped leaf replacement behavior still work.

- [ ] **Step 8: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add bilibili grouped playlist tree playback"
```

## Self-Review Notes

- Spec coverage:
  - Global Bilibili-only setting: Task 1
  - Tree widget rendering and non-Bilibili fallback: Task 2
  - Leaf click playback, cross-group next/finish, and replacement remapping: Task 3
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to” references remain.
  - Every code-changing step contains explicit code snippets and exact commands.
- Type consistency:
  - The plan uses `bilibili_grouped_playlist_tree_enabled` consistently across `AppConfig`, storage, advanced settings, and player window helpers.
  - Tree-mode playback always pivots around existing `PlayerSession.playlists`, `PlayerSession.playlist`, and `current_index`.
