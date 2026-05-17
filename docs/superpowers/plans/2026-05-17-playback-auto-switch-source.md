# Playback Auto Switch Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted `播放失败自动切换线路` playback setting, move the `播放设置` tab to the front of advanced settings, and automatically switch to the next source only when the current source fails during first open.

**Architecture:** Keep the existing `AppConfig -> SettingsRepository -> AdvancedSettingsDialog -> PlayerWindow` flow. Persist a single global boolean, expose it in the playback settings tab, then centralize first-open failure handling in `PlayerWindow` so all terminal startup failures can optionally reuse the existing `_switch_line_after_failure()` path without affecting post-start playback errors.

**Tech Stack:** Python 3, PySide6, SQLite settings storage, pytest-qt

---

## File Map

- Modify: `src/atv_player/models.py`
  Purpose: add the new persisted playback preference to `AppConfig`.
- Modify: `src/atv_player/storage.py`
  Purpose: migrate, normalize, load, and save the new boolean settings column.
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
  Purpose: move the playback tab to index 0 and expose the new checkbox inside the playback settings form.
- Modify: `src/atv_player/ui/player_window.py`
  Purpose: track auto-switched source attempts for the current open flow and route first-open failure exits through one helper.
- Modify: `tests/test_storage.py`
  Purpose: cover settings round-trip and migration default for the new flag.
- Modify: `tests/test_main_window_ui.py`
  Purpose: cover tab order plus reading/saving the new playback checkbox.
- Modify: `tests/test_player_window_ui.py`
  Purpose: cover auto-switch on startup failure, group rollover, exhaustion, disabled behavior, and no auto-switch after playback has already started.

### Task 1: Persist the New Playback Preference

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add these tests near the existing playback settings coverage in `tests/test_storage.py`:

```python
def test_settings_repository_round_trip_persists_playback_auto_switch_source_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        playback_auto_switch_source_on_failure=True,
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.playback_auto_switch_source_on_failure is True
    assert saved == config


def test_settings_repository_migrates_missing_playback_auto_switch_source_column(tmp_path: Path) -> None:
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
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO app_config (id, base_url, username, token, vod_token, last_path) VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')"
        )

    config = SettingsRepository(db_path).load_config()

    assert config.playback_auto_switch_source_on_failure is False
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -k "playback_auto_switch_source or playback_settings" -v`

Expected: FAIL because `AppConfig` and `SettingsRepository` do not yet define `playback_auto_switch_source_on_failure`.

- [ ] **Step 3: Add the model and storage support**

Update `src/atv_player/models.py` by inserting the new field alongside the other playback settings:

```python
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    metadata_enhancement_enabled: bool = True
    metadata_douban_cookie: str = ""
    metadata_tmdb_api_key: str = ""
    metadata_bangumi_access_token: str = ""
    network_proxy_mode: str = "direct"
    network_proxy_url: str = ""
    network_proxy_bypass_rules: list[str] = field(default_factory=_default_network_proxy_bypass_rules)
    youtube_cookie_browser: str = ""
    mpv_cache_size_mb: int = 512
    mpv_hwdec_mode: str = "auto-safe"
    mpv_network_timeout_seconds: int = 15
    mpv_default_readahead_secs: int = 20
    mpv_extra_options: str = ""
    playback_auto_switch_source_on_failure: bool = False
    episode_title_enhancement_enabled: bool = True
```

Update `src/atv_player/storage.py` in four places:

1. Add a normalizer:

```python
def _normalize_playback_auto_switch_source_on_failure(value: object) -> bool:
    return bool(value)
```

2. Add the column to the `CREATE TABLE` SQL and migration block:

```python
playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0,
```

```python
if "playback_auto_switch_source_on_failure" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0"
    )
```

3. Include it in `load_config()`:

```python
return AppConfig(
    ...
    mpv_default_readahead_secs=_normalize_mpv_default_readahead_secs(mpv_default_readahead_secs),
    mpv_extra_options=_normalize_mpv_extra_options(mpv_extra_options),
    playback_auto_switch_source_on_failure=_normalize_playback_auto_switch_source_on_failure(
        playback_auto_switch_source_on_failure
    ),
    last_path=last_path,
    ...
)
```

4. Include it in `save_config()`:

```python
UPDATE app_config
SET
    ...
    mpv_default_readahead_secs = ?,
    mpv_extra_options = ?,
    playback_auto_switch_source_on_failure = ?,
    last_path = ?,
    ...
```

```python
(
    ...
    _normalize_mpv_default_readahead_secs(config.mpv_default_readahead_secs),
    _normalize_mpv_extra_options(config.mpv_extra_options),
    int(config.playback_auto_switch_source_on_failure),
    config.last_path,
    ...
)
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -k "playback_auto_switch_source or playback_settings" -v`

Expected: PASS for the new flag tests and the existing playback settings tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist playback auto source switch setting"
```

### Task 2: Expose the Checkbox and Reorder the Advanced Settings Tabs

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing dialog tests**

Replace the existing tab-order assertion and extend the playback settings coverage in `tests/test_main_window_ui.py`:

```python
def test_advanced_settings_dialog_orders_tabs_with_playback_first(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.tabText(0) == "播放设置"
    assert dialog.settings_tabs.tabText(1) == "元数据"
    assert dialog.settings_tabs.tabText(2) == "网络代理"


def test_advanced_settings_dialog_adds_playback_tab_and_populates_existing_values(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(
        youtube_cookie_browser="firefox",
        mpv_cache_size_mb=1024,
        mpv_hwdec_mode="no",
        mpv_network_timeout_seconds=20,
        mpv_default_readahead_secs=35,
        mpv_extra_options="cache-pause-wait=9\nstream-buffer-size=8M",
        playback_auto_switch_source_on_failure=True,
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.tabText(0) == "播放设置"
    assert dialog.playback_auto_switch_source_on_failure_checkbox.isChecked() is True
    assert dialog.youtube_cookie_browser_combo.currentData() == "firefox"
```

```python
def test_advanced_settings_dialog_saves_trimmed_playback_settings(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved: list[AppConfig] = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.playback_auto_switch_source_on_failure_checkbox.setChecked(True)
    dialog.youtube_cookie_browser_combo.setCurrentIndex(dialog.youtube_cookie_browser_combo.findData("chrome"))
    dialog.mpv_cache_size_edit.setText(" 768 ")
    dialog.mpv_hwdec_mode_combo.setCurrentIndex(dialog.mpv_hwdec_mode_combo.findData("no"))
    dialog.mpv_network_timeout_edit.setText(" 22 ")
    dialog.mpv_default_readahead_edit.setText(" 40 ")
    dialog.mpv_extra_options_edit.setPlainText(" cache-pause-wait=8 \nstream-buffer-size=6M ")
    dialog._save()

    assert config.playback_auto_switch_source_on_failure is True
    assert config.youtube_cookie_browser == "chrome"
    assert config.mpv_cache_size_mb == 768
    assert len(saved) == 1
```

- [ ] **Step 2: Run the dialog tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog and (playback or tabs)" -v`

Expected: FAIL because the tab order is still `元数据 -> 网络代理 -> 播放设置` and there is no `playback_auto_switch_source_on_failure_checkbox`.

- [ ] **Step 3: Implement the dialog changes**

Update `src/atv_player/ui/advanced_settings_dialog.py`:

1. Add the checkbox in `__init__`:

```python
self.playback_auto_switch_source_on_failure_checkbox = QCheckBox("播放失败自动切换线路")
...
self.playback_auto_switch_source_on_failure_checkbox.setChecked(
    config.playback_auto_switch_source_on_failure
)
```

2. Put the checkbox at the top of the playback form:

```python
playback_layout = QFormLayout()
playback_layout.addRow(self.playback_auto_switch_source_on_failure_checkbox)
playback_layout.addRow("YouTube Cookie", self.youtube_cookie_browser_combo)
playback_layout.addRow("播放缓存大小（MB）", self.mpv_cache_size_edit)
...
```

3. Move the playback tab to the front:

```python
self.settings_tabs.addTab(self.playback_tab, "播放设置")
self.settings_tabs.addTab(self.metadata_tab, "元数据")
self.settings_tabs.addTab(self.network_proxy_tab, "网络代理")
```

4. Extend `_validated_playback_values()` to return the boolean:

```python
def _validated_playback_values(self) -> tuple[bool, str, int, str, int, int, str] | None:
    ...
    return (
        self.playback_auto_switch_source_on_failure_checkbox.isChecked(),
        browser,
        cache_size,
        str(self.mpv_hwdec_mode_combo.currentData() or "auto-safe"),
        timeout,
        readahead,
        "\n".join(normalized_lines),
    )
```

5. Save it in `_save()`:

```python
(
    self._config.playback_auto_switch_source_on_failure,
    self._config.youtube_cookie_browser,
    self._config.mpv_cache_size_mb,
    self._config.mpv_hwdec_mode,
    self._config.mpv_network_timeout_seconds,
    self._config.mpv_default_readahead_secs,
    self._config.mpv_extra_options,
) = playback_values
```

- [ ] **Step 4: Run the dialog tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog and (playback or tabs)" -v`

Expected: PASS for tab order, checkbox population, and playback settings save tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add playback auto source switch setting to dialog"
```

### Task 3: Add Auto-Switch Behavior for First-Open Source Failures

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player window tests**

Add focused tests near the existing grouped-source and failure coverage in `tests/test_player_window_ui.py`:

```python
def test_player_window_auto_switches_to_next_source_when_first_open_fails(qtbot) -> None:
    first = [PlayItem(title="第1集", url="", vod_id="line-1", play_source="线路1")]
    second = [PlayItem(title="第1集", url="http://line2/1.m3u8", play_source="线路2")]
    session = PlayerSession(
        vod=VodItem(vod_id="vod-1", vod_name="短剧"),
        playlist=first,
        playlists=[first, second],
        playlist_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="默认组",
                sources=[
                    PlaybackSource(label="线路1", playlist=first),
                    PlaybackSource(label="线路2", playlist=second),
                ],
            )
        ],
        source_group_index=0,
        source_index=0,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(playback_auto_switch_source_on_failure=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert window.session is not None
    assert window.session.source_index == 1
    assert window.video.load_calls[-1][0] == "http://line2/1.m3u8"
    assert "播放失败，自动切换线路" in window.log_view.toPlainText()
```

```python
def test_player_window_auto_switches_to_first_source_of_next_group_when_current_group_is_exhausted(qtbot) -> None:
    first = [PlayItem(title="第1集", url="", vod_id="line-1", play_source="组1线路1")]
    second = [PlayItem(title="第1集", url="http://group2/1.m3u8", play_source="组2线路1")]
    session = PlayerSession(
        vod=VodItem(vod_id="vod-2", vod_name="剧集"),
        playlist=first,
        playlists=[first, second],
        playlist_index=0,
        source_groups=[
            PlaybackSourceGroup(label="组1", sources=[PlaybackSource(label="组1线路1", playlist=first)]),
            PlaybackSourceGroup(label="组2", sources=[PlaybackSource(label="组2线路1", playlist=second)]),
        ],
        source_group_index=0,
        source_index=0,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(playback_auto_switch_source_on_failure=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert window.session is not None
    assert window.session.source_group_index == 1
    assert window.session.source_index == 0
    assert window.video.load_calls[-1][0] == "http://group2/1.m3u8"
```

```python
def test_player_window_stops_on_failed_startup_when_auto_switch_has_no_remaining_sources(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="vod-3", vod_name="单线路"),
        playlist=[PlayItem(title="第1集", url="", vod_id="line-1", play_source="线路1")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(playback_auto_switch_source_on_failure=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert window.session is not None
    assert window.session.source_index == 0
    assert window.video.load_calls == []
    assert window._startup_state.stage == PlaybackStartupStage.FAILED
```

```python
def test_player_window_does_not_auto_switch_when_playback_has_already_started(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="vod-4", vod_name="已开播"),
        playlist=[
            PlayItem(title="第1集", url="http://line1/1.m3u8", play_source="线路1"),
            PlayItem(title="第2集", url="http://line1/2.m3u8", play_source="线路1"),
        ],
        playlists=[
            [PlayItem(title="第1集", url="http://line1/1.m3u8", play_source="线路1")],
            [PlayItem(title="第1集", url="http://line2/1.m3u8", play_source="线路2")],
        ],
        playlist_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="默认组",
                sources=[
                    PlaybackSource(label="线路1", playlist=[PlayItem(title="第1集", url="http://line1/1.m3u8", play_source="线路1")]),
                    PlaybackSource(label="线路2", playlist=[PlayItem(title="第1集", url="http://line2/1.m3u8", play_source="线路2")]),
                ],
            )
        ],
        source_group_index=0,
        source_index=0,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(playback_auto_switch_source_on_failure=True),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    window._handle_video_picture_state_changed("visible")
    window._handle_playback_failed("播放失败: HTTP 403 Forbidden")

    assert window.session is not None
    assert window.session.source_index == 0
    assert "播放失败: HTTP 403 Forbidden" in window.log_view.toPlainText()
```

- [ ] **Step 2: Run the new player window tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "auto_switches_to_next_source or next_group_is_exhausted or no_remaining_sources or playback_has_already_started" -v`

Expected: FAIL because `PlayerWindow` does not yet have any startup-only auto-switch logic.

- [ ] **Step 3: Add startup-only auto-switch state and helper methods**

In `src/atv_player/ui/player_window.py`, add state in `__init__`:

```python
self._auto_switched_failure_sources: set[tuple[int, int]] = set()
```

Add the helper methods near the existing failure helpers:

```python
def _reset_auto_switched_failure_sources(self) -> None:
    self._auto_switched_failure_sources.clear()


def _current_source_attempt_key(self) -> tuple[int, int] | None:
    if self.session is None:
        return None
    return (self.session.source_group_index, self.session.source_index)


def _next_source_after_failure(self) -> tuple[int, int] | None:
    if self.session is None:
        return None
    source_groups = self._session_source_groups()
    if not source_groups:
        return None
    active_group = source_groups[self.session.source_group_index]
    if self.session.source_index + 1 < len(active_group.sources):
        return (self.session.source_group_index, self.session.source_index + 1)
    if self.session.source_group_index + 1 < len(source_groups):
        return (self.session.source_group_index + 1, 0)
    return None


def _should_auto_switch_source_after_failure(self) -> bool:
    return bool(getattr(self.config, "playback_auto_switch_source_on_failure", False))


def _try_auto_switch_source_after_failure(self) -> bool:
    if self.session is None or not self._should_auto_switch_source_after_failure():
        return False
    if self._startup_state.stage == PlaybackStartupStage.PLAYING:
        return False
    current_key = self._current_source_attempt_key()
    next_key = self._next_source_after_failure()
    if current_key is None or next_key is None:
        return False
    if current_key in self._auto_switched_failure_sources:
        return False
    self._auto_switched_failure_sources.add(current_key)
    self._append_log("播放失败，自动切换线路")
    self._switch_active_source(*next_key)
    return True
```

Update the existing manual helper to reuse the same next-source helper:

```python
def _switch_line_after_failure(self) -> None:
    next_source = self._next_source_after_failure()
    if next_source is None:
        return
    self._switch_active_source(*next_source)
```

Reset the state at the beginning of a new open flow and when manual control takes over:

```python
def open_session(self, session, start_paused: bool = False) -> None:
    self._reset_auto_switched_failure_sources()
    ...
```

```python
def _retry_failed_startup(self) -> None:
    self._reset_auto_switched_failure_sources()
    self._replay_current_item()
```

```python
def _switch_active_source(self, source_group_index: int, source_index: int) -> None:
    ...
    self._reset_auto_switched_failure_sources()
    ...
```

Clear the attempts once playback is actually considered started:

```python
def _handle_video_picture_state_changed(self, state: str) -> None:
    self._video_picture_state = state
    if state == "loading":
        self._set_startup_state(self._startup_coordinator.buffering())
    elif state in {"visible", "audio-cover"}:
        self._set_startup_state(self._startup_coordinator.playing())
        self._reset_auto_switched_failure_sources()
    ...
```

- [ ] **Step 4: Route terminal startup failures through the new helper**

Update each terminal first-open failure exit to try auto-switch before showing the failed startup state or restoring the previous index.

Use this pattern for direct `no url` failures:

```python
current_item = self.session.playlist[self.current_index]
if not current_item.url:
    if self._try_auto_switch_source_after_failure():
        return
    self._show_failed_startup_state(f"播放失败: 没有可用的播放地址: {current_item.title}")
    self._append_log(f"播放失败: 没有可用的播放地址: {current_item.title}")
    return
```

Apply the same pattern in:

- `_load_current_item()`
- `_handle_play_item_resolve_succeeded()` when `wait_for_load` resolves without a URL
- `_handle_play_item_resolve_failed()` in the `wait_for_load` branch
- `_handle_playback_loader_succeeded()` when the loader finishes without a URL
- `_handle_playback_loader_failed()`
- `_handle_playback_prepare_failed()` only in the terminal failure path that currently ends in `播放失败`
- `_handle_playback_failed()`

For `_handle_playback_failed()`, make the helper the first branch so mpv open failures can still auto-switch, while post-start errors remain on the current source because `_startup_state.stage` will already be `PLAYING`:

```python
def _handle_playback_failed(self, message: str) -> None:
    if self._try_auto_switch_source_after_failure():
        return
    self._show_failed_startup_state(message)
    self._append_log(message)
    self._video_surface_ready = False
    ...
```

When a terminal failure happens in a branch that currently restores the previous index, keep that restore path only when auto-switch does not fire.

- [ ] **Step 5: Run the targeted player window tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "auto_switches_to_next_source or next_group_is_exhausted or no_remaining_sources or playback_has_already_started" -v`

Expected: PASS for same-group switch, next-group rollover, exhaustion without looping, and no auto-switch after playback has already started.

- [ ] **Step 6: Run the broader player window regression slice**

Run: `uv run pytest tests/test_player_window_ui.py -k "switches_leaf_source or playback_failure or startup" -v`

Expected: PASS, proving the new helper does not break existing manual source switching, startup actions, or playback-failure log behavior.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: auto switch playback source on startup failure"
```

### Task 4: Final Cross-File Verification

**Files:**
- Verify: `src/atv_player/models.py`
- Verify: `src/atv_player/storage.py`
- Verify: `src/atv_player/ui/advanced_settings_dialog.py`
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_storage.py`
- Verify: `tests/test_main_window_ui.py`
- Verify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the full targeted suite**

Run: `uv run pytest tests/test_storage.py tests/test_main_window_ui.py tests/test_player_window_ui.py -k "playback_auto_switch_source or playback_settings or advanced_settings_dialog or startup or playback_failure or switches_leaf_source" -v`

Expected: PASS for the new storage, dialog, and player window coverage, plus nearby regressions.

- [ ] **Step 2: Inspect the diff**

Run: `git diff -- src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py tests/test_storage.py tests/test_main_window_ui.py tests/test_player_window_ui.py`

Expected: only the planned config, dialog, player-window, and test changes appear; no stray debug edits.

- [ ] **Step 3: Create the final implementation commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py tests/test_storage.py tests/test_main_window_ui.py tests/test_player_window_ui.py
git commit -m "feat: auto switch sources on startup playback failure"
```
