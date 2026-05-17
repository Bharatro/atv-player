# Mini Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-player Mini Player mode that switches the existing `PlayerWindow` into a frameless always-on-top floating window with a hover-only compact control bar, double-click restore, and separate geometry persistence.

**Architecture:** Keep Mini Player fully inside `PlayerWindow` rather than creating a second playback window. Add one new persisted geometry field in `AppConfig` and `SettingsRepository`, then layer Mini Player state, window-flag switching, and hover overlay controls on top of the existing video stack and visibility logic. Reuse current playback/session machinery so entering Mini Player never rebuilds playback state.

**Tech Stack:** Python, PySide6, SQLite, pytest, pytest-qt

---

## File Structure

### Existing files to modify

- `src/atv_player/models.py`
  Responsibility: `AppConfig` shape, including the new persisted `mini_player_geometry` field.

- `src/atv_player/storage.py`
  Responsibility: SQLite schema, migration, load/save round-trip for `mini_player_geometry`.

- `src/atv_player/ui/player_window.py`
  Responsibility: Mini Player state, button wiring, window flag transitions, geometry persistence split, hover overlay controls, fullscreen/wide/escape/double-click interaction rules.

- `tests/test_storage.py`
  Responsibility: storage round-trip and migration coverage for the new config field.

- `tests/test_player_window_ui.py`
  Responsibility: UI behavior coverage for Mini Player mode switching, geometry persistence, hover overlay visibility, and interaction rules.

### Design constraints for implementation

- Do not introduce a second player window or move Mini Player responsibility into `MainWindow`.
- Do not persist “start application in Mini Player”.
- Do not reuse `bottom_area` as the Mini Player overlay. Add a dedicated overlay inside `self.video_stack`.
- Keep method naming consistent across tasks:
  - `_is_mini_player`
  - `toggle_mini_player()`
  - `enter_mini_player()`
  - `exit_mini_player()`
  - `_apply_mini_player_window_flags()`
  - `_persist_geometry()`
  - `_restore_window_geometry()`
  - `_update_mini_player_overlay_visibility()`

---

### Task 1: Persist Mini Player Geometry In Config And Storage

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add these tests near the existing player geometry storage coverage in `tests/test_storage.py`:

```python
def test_settings_repository_round_trip_persists_mini_player_geometry(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        player_window_geometry=b"player-geometry",
        mini_player_geometry=b"mini-geometry",
        player_main_splitter_state=b"split-main",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.player_window_geometry == b"player-geometry"
    assert saved.mini_player_geometry == b"mini-geometry"
    assert saved.player_main_splitter_state == b"split-main"
    assert saved == config


def test_settings_repository_migrates_missing_mini_player_geometry_column(tmp_path: Path) -> None:
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
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]',
                global_search_hot_source TEXT NOT NULL DEFAULT '360'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token,
                metadata_enhancement_enabled, episode_title_enhancement_enabled,
                metadata_douban_cookie, metadata_tmdb_api_key, metadata_bangumi_access_token,
                last_path, last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id, last_playback_clicked_vod_id,
                last_player_paused, player_volume, player_muted, player_wide_mode, player_log_visible,
                preferred_parse_key, preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode, preferred_danmaku_uniform_color,
                preferred_danmaku_position_preset, preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history, global_search_hot_source
            )
            VALUES (
                1, 'http://127.0.0.1:4567', 'alice', '', '',
                1, 1, '', '', '',
                '/', 'main', 'browse', '', '', '', '', '',
                0, 100, 0, 0, 1,
                '', 1, 1, 'static', 'source', '#FFFFFF',
                'top', 1.0, 32,
                NULL, 'player-geometry', 'split-main',
                NULL, 'douban', '', '', '[]', '360'
            )
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.player_window_geometry == b"player-geometry"
    assert saved.player_main_splitter_state == b"split-main"
    assert saved.mini_player_geometry is None
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_storage.py::test_settings_repository_round_trip_persists_mini_player_geometry tests/test_storage.py::test_settings_repository_migrates_missing_mini_player_geometry_column -v
```

Expected:
- `FAIL` because `AppConfig` does not accept `mini_player_geometry`
- or `FAIL` because `SettingsRepository` does not load/save that column

- [ ] **Step 3: Write the minimal storage implementation**

Update `src/atv_player/models.py` and `src/atv_player/storage.py` with these concrete changes:

```python
# src/atv_player/models.py
@dataclass(slots=True)
class AppConfig:
    ...
    main_window_geometry: bytes | None = None
    player_window_geometry: bytes | None = None
    mini_player_geometry: bytes | None = None
    player_main_splitter_state: bytes | None = None
    ...
```

```python
# src/atv_player/storage.py - schema and migration
CREATE TABLE IF NOT EXISTS app_config (
    ...
    main_window_geometry BLOB,
    player_window_geometry BLOB,
    mini_player_geometry BLOB,
    player_main_splitter_state BLOB,
    ...
)

if "mini_player_geometry" not in columns:
    conn.execute("ALTER TABLE app_config ADD COLUMN mini_player_geometry BLOB")
```

```python
# src/atv_player/storage.py - load/save paths
SELECT
    ...
    main_window_geometry,
    player_window_geometry,
    mini_player_geometry,
    player_main_splitter_state,
    ...

return AppConfig(
    ...
    main_window_geometry=main_window_geometry,
    player_window_geometry=player_window_geometry,
    mini_player_geometry=mini_player_geometry,
    player_main_splitter_state=player_main_splitter_state,
    ...
)
```

```python
# src/atv_player/storage.py - update statement/value tuple
SET
    ...
    main_window_geometry = ?,
    player_window_geometry = ?,
    mini_player_geometry = ?,
    player_main_splitter_state = ?,
    ...

(
    ...
    config.main_window_geometry,
    config.player_window_geometry,
    config.mini_player_geometry,
    config.player_main_splitter_state,
    ...
)
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_storage.py::test_settings_repository_round_trip_persists_mini_player_geometry tests/test_storage.py::test_settings_repository_migrates_missing_mini_player_geometry_column -v
```

Expected:
- both tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist mini player geometry"
```

---

### Task 2: Add Mini Player Mode State, Button, And Geometry Switching

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing Mini Player mode tests**

Add these tests near the existing fullscreen/wide-mode coverage in `tests/test_player_window_ui.py`:

```python
def test_player_window_enters_mini_player_with_frameless_topmost_flags(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    window.toggle_mini_player()

    flags = window.windowFlags()
    assert window._is_mini_player is True
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert bool(flags & Qt.WindowType.FramelessWindowHint)
    assert window.bottom_area.isHidden() is True
    assert window.sidebar_container.isHidden() is True


def test_player_window_exits_mini_player_and_restores_normal_visibility(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    window.toggle_mini_player()
    window.toggle_mini_player()

    flags = window.windowFlags()
    assert window._is_mini_player is False
    assert not bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert not bool(flags & Qt.WindowType.FramelessWindowHint)
    assert window.bottom_area.isHidden() is False
    assert window.sidebar_container.isHidden() is False


def test_player_window_persists_mini_player_geometry_separately(qtbot) -> None:
    config = AppConfig()
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(window)
    window.show()
    window.setGeometry(100, 120, 1280, 800)

    window.enter_mini_player()
    window.setGeometry(240, 260, 480, 270)
    window._persist_geometry()

    assert config.player_window_geometry != config.mini_player_geometry
    assert config.mini_player_geometry is not None

    restored = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(restored)
    restored.show()
    restored.enter_mini_player()

    assert restored.geometry().width() == 480
    assert restored.geometry().height() == 270
```

- [ ] **Step 2: Run the mode-switch tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_enters_mini_player_with_frameless_topmost_flags tests/test_player_window_ui.py::test_player_window_exits_mini_player_and_restores_normal_visibility tests/test_player_window_ui.py::test_player_window_persists_mini_player_geometry_separately -v
```

Expected:
- `FAIL` because `toggle_mini_player()` and `_is_mini_player` do not exist
- or `FAIL` because `_persist_geometry()` still writes only `player_window_geometry`

- [ ] **Step 3: Write the minimal PlayerWindow mode implementation**

Add concrete state and button wiring in `src/atv_player/ui/player_window.py`:

```python
# __init__ state
self._is_mini_player = False
self._pre_mini_player_geometry: bytes | None = None
self.mini_player_button = self._create_icon_button("maximize.svg", "Mini Player")
self.mini_player_button.setCheckable(True)
```

Insert the button into the existing main control row between `refresh_button` and `wide_button`:

```python
control_group_layout.addWidget(self.refresh_button)
control_group_layout.addWidget(self.mini_player_button)
control_group_layout.addWidget(self.wide_button)
```

Wire the button:

```python
self.mini_player_button.clicked.connect(self.toggle_mini_player)
```

Split geometry persistence:

```python
def _restore_window_geometry(self, geometry_bytes: bytes | None) -> None:
    if not geometry_bytes:
        return
    self.restoreGeometry(to_qbytearray(geometry_bytes))


def _persist_geometry(self) -> None:
    if self.config is None:
        return
    geometry = qbytearray_to_bytes(self.saveGeometry())
    if self._is_mini_player:
        self.config.mini_player_geometry = geometry
    else:
        self.config.player_window_geometry = geometry
    self.config.player_main_splitter_state = self._main_splitter_state_for_persistence()
    self._save_config()
```

Add the Mini Player entry points:

```python
def toggle_mini_player(self) -> None:
    if self._is_mini_player:
        self.exit_mini_player()
    else:
        self.enter_mini_player()


def enter_mini_player(self) -> None:
    if self._is_mini_player:
        return
    if self.isFullScreen():
        self.toggle_fullscreen()
    if self.wide_button.isChecked():
        self.wide_button.setChecked(False)
        self._toggle_wide_mode()
    self._pre_mini_player_geometry = qbytearray_to_bytes(self.saveGeometry())
    self._is_mini_player = True
    self.mini_player_button.setChecked(True)
    self._apply_mini_player_window_flags(True)
    self._restore_window_geometry(getattr(self.config, "mini_player_geometry", None))
    self._apply_visibility_state()


def exit_mini_player(self) -> None:
    if not self._is_mini_player:
        return
    self._is_mini_player = False
    self.mini_player_button.setChecked(False)
    self._apply_mini_player_window_flags(False)
    if self._pre_mini_player_geometry:
        self._restore_window_geometry(self._pre_mini_player_geometry)
    else:
        self._restore_window_geometry(getattr(self.config, "player_window_geometry", None))
    self._apply_visibility_state()


def _apply_mini_player_window_flags(self, enabled: bool) -> None:
    flags = self.windowFlags() | Qt.WindowType.Window
    flags &= ~Qt.WindowType.WindowStaysOnTopHint
    flags &= ~Qt.WindowType.FramelessWindowHint
    if enabled:
        flags |= Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
    self.setWindowFlags(flags)
    self.show()
```

Make startup geometry restoration use the helper:

```python
if self.config and self.config.player_window_geometry:
    self._restore_window_geometry(self.config.player_window_geometry)
    self._sidebar_sizes = self.main_splitter.sizes()
```

Update visibility rules:

```python
def _apply_visibility_state(self) -> None:
    is_fullscreen = self.isFullScreen()
    is_mini_player = self._is_mini_player
    sidebar_hidden = is_fullscreen or self.wide_button.isChecked() or is_mini_player
    metadata_visible = self.toggle_details_button.isChecked()
    log_visible = self.toggle_log_button.isChecked()
    self._update_log_section_host_layout()
    self.bottom_area.setHidden(is_fullscreen or is_mini_player)
    self.sidebar_actions_widget.setHidden(is_fullscreen or is_mini_player)
    self.sidebar_container.setHidden(sidebar_hidden)
    self.playlist.setHidden(is_mini_player or not self._playlist_panel_visible())
    self._render_playlist_title_tabs()
    self.details.setHidden(is_mini_player or is_fullscreen or not metadata_visible)
    self.metadata_section.setHidden(is_mini_player or is_fullscreen or not metadata_visible)
    self.log_section.setHidden(is_mini_player or is_fullscreen or not log_visible)
    self._update_log_section_max_height()
```

- [ ] **Step 4: Run the mode-switch tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_enters_mini_player_with_frameless_topmost_flags tests/test_player_window_ui.py::test_player_window_exits_mini_player_and_restores_normal_visibility tests/test_player_window_ui.py::test_player_window_persists_mini_player_geometry_separately -v
```

Expected:
- all three tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: add player mini mode state"
```

---

### Task 3: Add Hover Overlay Controls And Mini Player Interaction Rules

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing overlay and interaction tests**

Add these tests in `tests/test_player_window_ui.py` near other video-surface interaction tests:

```python
def test_player_window_mini_player_hover_shows_and_hides_overlay(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    window.enter_mini_player()

    assert window.mini_controls_overlay.isHidden() is True

    enter_event = QEvent(QEvent.Type.Enter)
    window.eventFilter(window.video_widget, enter_event)
    assert window.mini_controls_overlay.isHidden() is False

    leave_event = QEvent(QEvent.Type.Leave)
    window.eventFilter(window.video_widget, leave_event)
    assert window.mini_controls_overlay.isHidden() is True


def test_player_window_mini_player_double_click_restores_normal_mode(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    window.enter_mini_player()

    window.video_widget.double_clicked.emit()

    assert window._is_mini_player is False
    assert window.isFullScreen() is False


def test_player_window_escape_exits_mini_player_before_returning_to_main(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    window.enter_mini_player()

    returned = {"count": 0}
    monkeypatch.setattr(window, "_return_to_main", lambda: returned.__setitem__("count", returned["count"] + 1))

    window._handle_escape()

    assert window._is_mini_player is False
    assert returned["count"] == 0


def test_player_window_mini_player_disables_fullscreen_shortcut_behavior(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    window.enter_mini_player()

    window.toggle_fullscreen()

    assert window._is_mini_player is False
    assert window.isFullScreen() is False
```

- [ ] **Step 2: Run the overlay and interaction tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_mini_player_hover_shows_and_hides_overlay tests/test_player_window_ui.py::test_player_window_mini_player_double_click_restores_normal_mode tests/test_player_window_ui.py::test_player_window_escape_exits_mini_player_before_returning_to_main tests/test_player_window_ui.py::test_player_window_mini_player_disables_fullscreen_shortcut_behavior -v
```

Expected:
- `FAIL` because `mini_controls_overlay` does not exist
- or `FAIL` because double-click and escape still route to fullscreen / return-to-main behavior

- [ ] **Step 3: Write the minimal overlay and interaction implementation**

Build a dedicated overlay on top of `self.video_stack`:

```python
# __init__ after self.video_stack_layout setup
self.mini_controls_overlay = QWidget(self.video_stack)
self.mini_controls_overlay.hide()
self.mini_controls_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
self.mini_controls_overlay_layout = QHBoxLayout(self.mini_controls_overlay)
self.mini_controls_overlay_layout.setContentsMargins(12, 8, 12, 8)
self.mini_controls_overlay_layout.setSpacing(6)

self.mini_prev_button = self._create_icon_button("previous.svg", "上一集", "PgUp")
self.mini_play_button = self._create_icon_button("play.svg", "播放/暂停", "Space")
self.mini_next_button = self._create_icon_button("next.svg", "下一集", "PgDn")
self.mini_progress = ClickableSlider(Qt.Orientation.Horizontal)
self.mini_progress.setRange(0, 0)
self.mini_progress.setFixedWidth(220)
self.mini_restore_button = QPushButton("恢复")
self.mini_close_button = QPushButton("关闭")

self.mini_controls_overlay_layout.addWidget(self.mini_prev_button)
self.mini_controls_overlay_layout.addWidget(self.mini_play_button)
self.mini_controls_overlay_layout.addWidget(self.mini_next_button)
self.mini_controls_overlay_layout.addWidget(self.mini_progress)
self.mini_controls_overlay_layout.addWidget(self.mini_restore_button)
self.mini_controls_overlay_layout.addWidget(self.mini_close_button)

self.video_stack_layout.addWidget(self.mini_controls_overlay)
```

Wire the overlay buttons to the existing playback methods:

```python
self.mini_prev_button.clicked.connect(self.play_previous)
self.mini_play_button.clicked.connect(self.toggle_playback)
self.mini_next_button.clicked.connect(self.play_next)
self.mini_progress.clicked_value.connect(self._seek_to_position)
self.mini_progress.sliderPressed.connect(self._handle_slider_pressed)
self.mini_progress.sliderReleased.connect(self._seek_from_mini_slider)
self.mini_restore_button.clicked.connect(self.exit_mini_player)
self.mini_close_button.clicked.connect(self.close)
```

Keep overlay icons and progress in sync with existing state:

```python
def _seek_from_mini_slider(self) -> None:
    self._slider_dragging = False
    self._seek_to_position(self.mini_progress.value())


def _update_play_button_icon(self) -> None:
    icon_name = "pause.svg" if self.is_playing else "play.svg"
    self.play_button.setIcon(load_icon(self._icons_dir / icon_name))
    if hasattr(self, "mini_play_button"):
        self.mini_play_button.setIcon(load_icon(self._icons_dir / icon_name))


def _sync_progress_slider(self) -> None:
    if self._slider_dragging:
        return
    duration = self.video.duration_seconds() if hasattr(self.video, "duration_seconds") else 0
    position = self.video.position_seconds() or 0
    ...
    self.progress.setMaximum(max(duration, 0))
    self.progress.setValue(max(min(position, self.progress.maximum()), 0))
    if hasattr(self, "mini_progress"):
        self.mini_progress.setMaximum(max(duration, 0))
        self.mini_progress.setValue(max(min(position, self.mini_progress.maximum()), 0))
```

Handle overlay visibility and interactions:

```python
def _update_mini_player_overlay_visibility(self, visible: bool) -> None:
    if not self._is_mini_player:
        self.mini_controls_overlay.hide()
        return
    self.mini_controls_overlay.setVisible(visible)


def toggle_fullscreen(self) -> None:
    if self._is_mini_player:
        self.exit_mini_player()
        return
    ...


def _handle_escape(self) -> None:
    if self._dismiss_escape_dialog():
        return
    if self._is_mini_player:
        self.exit_mini_player()
        return
    if self.isFullScreen():
        self.toggle_fullscreen()
        return
    self._return_to_main()
```

Redirect double-click in `__init__`:

```python
self.video_widget.double_clicked.connect(self._handle_video_double_click)
```

```python
def _handle_video_double_click(self) -> None:
    if self._is_mini_player:
        self.exit_mini_player()
        return
    self.toggle_fullscreen()
```

Update `eventFilter()`:

```python
if isinstance(watched, QWidget) and watched in self._video_surface_widgets():
    if event.type() == QEvent.Type.Enter:
        self._video_pointer_inside = True
        self._handle_video_mouse_activity()
        self._update_mini_player_overlay_visibility(True)
    elif event.type() == QEvent.Type.MouseMove:
        self._video_pointer_inside = True
        self._handle_video_mouse_activity()
        self._update_mini_player_overlay_visibility(True)
    ...
    elif event.type() == QEvent.Type.Leave:
        self._handle_video_leave()
        self._update_mini_player_overlay_visibility(False)
```

When entering/exiting Mini Player, force overlay state reset:

```python
def enter_mini_player(self) -> None:
    ...
    self._update_mini_player_overlay_visibility(False)


def exit_mini_player(self) -> None:
    ...
    self._update_mini_player_overlay_visibility(False)
```

- [ ] **Step 4: Run the overlay and interaction tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_mini_player_hover_shows_and_hides_overlay tests/test_player_window_ui.py::test_player_window_mini_player_double_click_restores_normal_mode tests/test_player_window_ui.py::test_player_window_escape_exits_mini_player_before_returning_to_main tests/test_player_window_ui.py::test_player_window_mini_player_disables_fullscreen_shortcut_behavior -v
```

Expected:
- all four tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: add mini player overlay controls"
```

---

### Task 4: Run Focused Regression Coverage For Mini Player And Existing Player Modes

**Files:**
- Test only: `tests/test_player_window_ui.py`
- Test only: `tests/test_storage.py`

- [ ] **Step 1: Run the focused Mini Player and surrounding regression suite**

Run:

```bash
uv run pytest tests/test_storage.py -k "mini_player_geometry or player_window_geometry" tests/test_player_window_ui.py -k "mini_player or wide_mode or fullscreen or geometry" -v
```

Expected:
- all targeted tests `PASS`
- no regression in existing wide-mode/fullscreen/geometry coverage

- [ ] **Step 2: If any existing fullscreen or wide-mode test fails, fix PlayerWindow state interactions before broadening scope**

Use these constraints while fixing:

```python
# Keep these invariants true
assert not (self._is_mini_player and self.isFullScreen())
assert not (self._is_mini_player and self.wide_button.isChecked())
assert self.bottom_area.isHidden() == (self.isFullScreen() or self._is_mini_player)
```

Typical minimal fix points:

```python
def enter_mini_player(self) -> None:
    if self.isFullScreen():
        self.toggle_fullscreen()
    if self.wide_button.isChecked():
        self.wide_button.setChecked(False)
        self._toggle_wide_mode()
    ...
```

```python
def _should_dock_log_to_sidebar_bottom(self) -> bool:
    return (
        not self._is_mini_player
        and not self.isFullScreen()
        and not self.wide_button.isChecked()
        and not self.toggle_details_button.isChecked()
        and self.toggle_log_button.isChecked()
    )
```

- [ ] **Step 3: Re-run the same regression command to verify the fixes**

Run:

```bash
uv run pytest tests/test_storage.py -k "mini_player_geometry or player_window_geometry" tests/test_player_window_ui.py -k "mini_player or wide_mode or fullscreen or geometry" -v
```

Expected:
- all targeted tests `PASS`

- [ ] **Step 4: Commit**

```bash
git add tests/test_storage.py tests/test_player_window_ui.py src/atv_player/ui/player_window.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "test: verify mini player regressions"
```

---

## Self-Review

### Spec coverage

- In-player entry via dedicated button: covered by Task 2.
- Frameless always-on-top state: covered by Task 2.
- Separate Mini Player geometry persistence: covered by Tasks 1 and 2.
- Hover-only compact overlay controls: covered by Task 3.
- Double-click restore and `Esc` exits Mini Player first: covered by Task 3.
- Fullscreen/wide mutual exclusion and regression coverage: covered by Task 4.

No spec section is currently uncovered.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Each task includes explicit file paths, test names, commands, and concrete code blocks.
- No task relies on “similar to previous task” shorthand.

### Type consistency

- Persisted config field name is consistently `mini_player_geometry`.
- Mini Player state flag is consistently `_is_mini_player`.
- Entry points are consistently `toggle_mini_player()`, `enter_mini_player()`, and `exit_mini_player()`.
- Overlay visibility helper is consistently `_update_mini_player_overlay_visibility()`.
