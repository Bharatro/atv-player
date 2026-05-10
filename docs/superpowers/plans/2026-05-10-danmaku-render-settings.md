# Danmaku Render Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `弹幕设置` dialog that persists global danmaku render settings and immediately regenerates the active danmaku ASS track when the user changes color, render mode, or position.

**Architecture:** Extend `AppConfig` and `SettingsRepository` with four new danmaku style fields, then thread those normalized settings into the danmaku ASS cache and renderer. Keep the current danmaku source flow intact, add a separate player dialog for style settings, and reuse the existing danmaku track ownership path so changing settings rebuilds the same ASS-backed subtitle track without replaying media.

**Tech Stack:** Python 3, PySide6, sqlite3, pytest, existing mpv widget integration, ASS subtitle generation in `src/atv_player/danmaku/subtitle.py`

---

## File Structure

- Modify: `src/atv_player/models.py`
  - Extend `AppConfig` with danmaku render mode, color mode, uniform color, and position preset defaults.
- Modify: `src/atv_player/storage.py`
  - Add schema migration, default insert values, load-time normalization, and save-time persistence for the new danmaku fields.
- Modify: `src/atv_player/danmaku/cache.py`
  - Expand ASS cache keys to include normalized render settings and bump cache version.
- Modify: `src/atv_player/danmaku/subtitle.py`
  - Replace static merged-cue-only rendering with a settings-aware ASS generator that supports `static`, `scroll_only`, and `mixed`.
- Modify: `src/atv_player/ui/player_window.py`
  - Add `弹幕设置` entry points, dialog state, config save handlers, and active danmaku regeneration logic.
- Modify: `tests/test_danmaku_subtitle.py`
  - Add renderer coverage for settings-aware danmaku output.
- Modify: `tests/test_player_window_ui.py`
  - Add UI, persistence, and immediate-refresh regression tests.
- Create: `tests/test_storage.py`
  - Add focused repository tests for new danmaku setting defaults and migrations.
- Modify: `tests/test_danmaku_cache.py`
  - Add cache-key regression tests for settings-sensitive ASS cache paths.

### Task 1: Persist Danmaku Render Settings

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from atv_player.models import AppConfig
from atv_player.storage import SettingsRepository


def test_settings_repository_loads_new_danmaku_render_defaults(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    config = repo.load_config()

    assert config.preferred_danmaku_render_mode == "static"
    assert config.preferred_danmaku_color_mode == "uniform"
    assert config.preferred_danmaku_uniform_color == "#FFFFFF"
    assert config.preferred_danmaku_position_preset == "top"


def test_settings_repository_persists_new_danmaku_render_settings(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.preferred_danmaku_render_mode = "mixed"
    config.preferred_danmaku_color_mode = "source"
    config.preferred_danmaku_uniform_color = "#00FF00"
    config.preferred_danmaku_position_preset = "mid_upper"

    repo.save_config(config)

    reloaded = repo.load_config()
    assert reloaded.preferred_danmaku_render_mode == "mixed"
    assert reloaded.preferred_danmaku_color_mode == "source"
    assert reloaded.preferred_danmaku_uniform_color == "#00FF00"
    assert reloaded.preferred_danmaku_position_preset == "mid_upper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL with `AttributeError` or constructor mismatch because `AppConfig` and `SettingsRepository` do not yet expose the four new fields.

- [ ] **Step 3: Extend `AppConfig` with the new global defaults**

```python
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    last_path: str = "/"
    last_active_window: str = "main"
    last_playback_source: str = "browse"
    last_playback_source_key: str = ""
    last_playback_mode: str = ""
    last_playback_path: str = ""
    last_playback_vod_id: str = ""
    last_playback_clicked_vod_id: str = ""
    last_player_paused: bool = False
    player_volume: int = 100
    player_muted: bool = False
    player_wide_mode: bool = False
    preferred_parse_key: str = ""
    preferred_danmaku_enabled: bool = True
    preferred_danmaku_line_count: int = 1
    preferred_danmaku_render_mode: str = "static"
    preferred_danmaku_color_mode: str = "uniform"
    preferred_danmaku_uniform_color: str = "#FFFFFF"
    preferred_danmaku_position_preset: str = "top"
    main_window_geometry: bytes | None = None
    player_window_geometry: bytes | None = None
    player_main_splitter_state: bytes | None = None
    browse_content_splitter_state: bytes | None = None
    last_selected_tab: str = "douban"
    last_selected_category_tab: str = ""
    last_selected_category_id: str = ""
```

- [ ] **Step 4: Add schema, load, save, and normalization support**

```python
_VALID_DANMAKU_RENDER_MODES = {"static", "scroll_only", "mixed"}
_VALID_DANMAKU_COLOR_MODES = {"uniform", "source"}
_VALID_DANMAKU_POSITION_PRESETS = {"top", "upper", "mid_upper", "bottom"}


def _normalize_danmaku_render_mode(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_RENDER_MODES else "static"


def _normalize_danmaku_color_mode(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_COLOR_MODES else "uniform"


def _normalize_danmaku_uniform_color(value: object) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 7 and text.startswith("#"):
        return text
    return "#FFFFFF"


def _normalize_danmaku_position_preset(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_POSITION_PRESETS else "top"
```

Add matching `ALTER TABLE` clauses, `INSERT` defaults, `SELECT` columns, `AppConfig(*values)` ordering, and `UPDATE` bindings so the new fields sit directly after `preferred_danmaku_line_count`.

- [ ] **Step 5: Run tests to verify the config path passes**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS with both repository tests green.

- [ ] **Step 6: Commit**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist danmaku render settings"
```

### Task 2: Make ASS Rendering And Cache Keys Settings-Aware

**Files:**
- Modify: `src/atv_player/danmaku/subtitle.py`
- Modify: `src/atv_player/danmaku/cache.py`
- Modify: `tests/test_danmaku_subtitle.py`
- Modify: `tests/test_danmaku_cache.py`

- [ ] **Step 1: Write failing renderer and cache tests**

```python
from atv_player.danmaku.cache import danmaku_ass_cache_path
from atv_player.danmaku.subtitle import render_danmaku_ass


def test_render_danmaku_ass_uses_uniform_color_and_scroll_mode() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,255">滚动蓝字</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FF0000",
        position_preset="upper",
    )

    assert "\\move(" in subtitle
    assert "\\c&H0000FF&" in subtitle
    assert "\\c&HFF0000&" not in subtitle


def test_render_danmaku_ass_preserves_source_top_and_bottom_in_mixed_mode() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,5,25,16777215">顶部</d>'
        '<d p="1.0,4,25,65280">底部</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=2,
        render_mode="mixed",
        color_mode="source",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "\\move(" not in subtitle.split("顶部", 1)[0]
    assert "顶部" in subtitle
    assert "底部" in subtitle


def test_danmaku_ass_cache_path_changes_when_render_settings_change() -> None:
    xml_text = '<?xml version="1.0" encoding="UTF-8"?><i><d p="0.0,1,25,16777215">一条</d></i>'

    first = danmaku_ass_cache_path(
        xml_text,
        1,
        render_mode="static",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
    )
    second = danmaku_ass_cache_path(
        xml_text,
        1,
        render_mode="mixed",
        color_mode="source",
        uniform_color="#00FF00",
        position_preset="bottom",
    )

    assert first != second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py -v`
Expected: FAIL because `render_danmaku_ass()` and `danmaku_ass_cache_path()` do not yet accept the new keyword arguments.

- [ ] **Step 3: Introduce normalized render settings and extend the cache key**

```python
_DANMAKU_ASS_CACHE_VERSION = "v2"


def danmaku_ass_cache_path(
    xml_text: str,
    line_count: int,
    *,
    render_mode: str,
    color_mode: str,
    uniform_color: str,
    position_preset: str,
) -> Path:
    digest = sha256(
        "\0".join(
            (
                _DANMAKU_ASS_CACHE_VERSION,
                str(max(1, min(int(line_count), 5))),
                render_mode,
                color_mode,
                uniform_color,
                position_preset,
                xml_text,
            )
        ).encode("utf-8")
    ).hexdigest()
    return danmaku_cache_dir() / f"{digest}.ass"
```

- [ ] **Step 4: Refactor `render_danmaku_ass()` to accept explicit settings and emit per-record ASS events**

```python
def render_danmaku_ass(
    xml_text: str,
    line_count: int = 1,
    duration_seconds: float = 4.0,
    *,
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = "#FFFFFF",
    position_preset: str = "top",
) -> str:
    normalized_line_count = max(1, min(int(line_count), 5))
    normalized_duration = max(1.0, float(duration_seconds))
    records = _parse_danmaku_xml(xml_text)
    if not records:
        return ""
    style = _DanmakuRenderStyle(
        render_mode=_normalize_render_mode(render_mode),
        color_mode=_normalize_color_mode(color_mode),
        uniform_color=_normalize_hex_color(uniform_color),
        position_preset=_normalize_position_preset(position_preset),
        line_count=normalized_line_count,
        duration_seconds=normalized_duration,
    )
    header = _build_ass_header(style)
    events = _build_ass_events(records, style)
    return "\n".join([header, *events, ""])
```

Keep `render_danmaku_srt()` untouched so unrelated subtitle tests do not change behavior.

- [ ] **Step 5: Thread the new settings through cache creation**

```python
def load_or_create_danmaku_ass_cache(
    xml_text: str,
    line_count: int,
    *,
    render_mode: str,
    color_mode: str,
    uniform_color: str,
    position_preset: str,
) -> Path | None:
    subtitle_text = render_danmaku_ass(
        xml_text,
        line_count=line_count,
        render_mode=render_mode,
        color_mode=color_mode,
        uniform_color=uniform_color,
        position_preset=position_preset,
    )
    if not subtitle_text:
        return None
    cache_path = danmaku_ass_cache_path(
        xml_text,
        line_count,
        render_mode=render_mode,
        color_mode=color_mode,
        uniform_color=uniform_color,
        position_preset=position_preset,
    )
    if not cache_path.exists():
        cache_path.write_text(subtitle_text, encoding="utf-8")
    return cache_path
```

- [ ] **Step 6: Run tests to verify the renderer and cache path pass**

Run: `uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py -v`
Expected: PASS with the new render-mode and cache-key assertions green.

- [ ] **Step 7: Commit**

```bash
git add tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py src/atv_player/danmaku/subtitle.py src/atv_player/danmaku/cache.py
git commit -m "feat: add configurable danmaku ass rendering"
```

### Task 3: Add The `弹幕设置` Dialog And Entry Points

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing UI entry-point and persistence tests**

```python
def test_player_window_exposes_danmaku_settings_button_next_to_danmaku_source(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.danmaku_settings_button.toolTip() == "弹幕设置"


def test_player_window_context_menu_exposes_danmaku_settings_action(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    menu = window._build_video_context_menu()
    assert any(action.text() == "弹幕设置" for action in menu.actions())


def test_player_window_saves_danmaku_render_mode_from_dialog(qtbot) -> None:
    saved = {"called": 0}
    config = AppConfig()
    window = PlayerWindow(
        FakePlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("called", saved["called"] + 1),
    )
    qtbot.addWidget(window)

    dialog = window._ensure_danmaku_settings_dialog()
    window._danmaku_render_mode_combo.setCurrentIndex(
        window._danmaku_render_mode_combo.findData("mixed")
    )

    assert config.preferred_danmaku_render_mode == "mixed"
    assert saved["called"] == 1
    assert dialog.windowTitle() == "弹幕设置"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "danmaku_settings or saves_danmaku_render_mode" -v`
Expected: FAIL because no `danmaku_settings_button`, dialog, or render-mode persistence handler exists.

- [ ] **Step 3: Add the new button, dialog references, and context-menu action**

```python
self.danmaku_settings_button = self._create_icon_button("danmaku.svg", "弹幕设置")
self.danmaku_settings_button.clicked.connect(self._open_danmaku_settings_dialog)
control_group_layout.addWidget(self.danmaku_settings_button)

self._danmaku_settings_dialog: QDialog | None = None
self._danmaku_render_mode_combo: QComboBox | None = None
self._danmaku_color_mode_combo: QComboBox | None = None
self._danmaku_uniform_color_edit: QLineEdit | None = None
self._danmaku_position_preset_combo: QComboBox | None = None
```

And in `_build_video_context_menu()`:

```python
menu.addMenu(self._build_danmaku_menu(menu))
menu.addAction("弹幕源", self._open_danmaku_source_dialog)
menu.addAction("弹幕设置", self._open_danmaku_settings_dialog)
menu.addAction("视频信息", self._toggle_video_info_from_menu)
```

- [ ] **Step 4: Build the dialog and save handlers**

```python
def _ensure_danmaku_settings_dialog(self) -> QDialog:
    if self._danmaku_settings_dialog is not None:
        return self._danmaku_settings_dialog
    dialog = QDialog(self)
    dialog.setWindowTitle("弹幕设置")
    layout = QVBoxLayout(dialog)
    self._danmaku_render_mode_combo = QComboBox(dialog)
    self._danmaku_render_mode_combo.addItem("静态", "static")
    self._danmaku_render_mode_combo.addItem("仅滚动", "scroll_only")
    self._danmaku_render_mode_combo.addItem("混合", "mixed")
    self._danmaku_color_mode_combo = QComboBox(dialog)
    self._danmaku_color_mode_combo.addItem("统一颜色", "uniform")
    self._danmaku_color_mode_combo.addItem("保留原色", "source")
    self._danmaku_uniform_color_edit = QLineEdit(dialog)
    self._danmaku_position_preset_combo = QComboBox(dialog)
    self._danmaku_position_preset_combo.addItem("顶部", "top")
    self._danmaku_position_preset_combo.addItem("顶部偏下", "upper")
    self._danmaku_position_preset_combo.addItem("中上", "mid_upper")
    self._danmaku_position_preset_combo.addItem("底部", "bottom")
    self._danmaku_render_mode_combo.currentIndexChanged.connect(self._change_danmaku_render_mode)
    self._danmaku_color_mode_combo.currentIndexChanged.connect(self._change_danmaku_color_mode)
    self._danmaku_uniform_color_edit.editingFinished.connect(self._change_danmaku_uniform_color)
    self._danmaku_position_preset_combo.currentIndexChanged.connect(self._change_danmaku_position_preset)
    self._danmaku_settings_dialog = dialog
    return dialog
```

- [ ] **Step 5: Implement normalization helpers and `恢复默认` behavior**

```python
def _preferred_danmaku_render_mode(self) -> str:
    if self.config is None:
        return "static"
    value = getattr(self.config, "preferred_danmaku_render_mode", "static")
    return value if value in {"static", "scroll_only", "mixed"} else "static"


def _restore_default_danmaku_render_settings(self) -> None:
    if self.config is None:
        return
    self.config.preferred_danmaku_render_mode = "static"
    self.config.preferred_danmaku_color_mode = "uniform"
    self.config.preferred_danmaku_uniform_color = "#FFFFFF"
    self.config.preferred_danmaku_position_preset = "top"
    self._save_config()
    self._refresh_danmaku_settings_dialog_controls()
    self._reload_active_danmaku_for_render_settings()
```

- [ ] **Step 6: Run the focused UI tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "danmaku_settings or saves_danmaku_render_mode" -v`
Expected: PASS with entry-point and immediate-save tests green.

- [ ] **Step 7: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: add danmaku settings dialog"
```

### Task 4: Regenerate The Active Danmaku Track Immediately

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing active-refresh tests**

```python
def test_player_window_reloads_active_danmaku_after_uniform_color_change(qtbot) -> None:
    saved = {"called": 0}

    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_danmaku_paths: list[str] = []
            self.removed_danmaku_track_ids: list[int] = []
            self._next_track_id = 70

        def load(self, url: str, pause: bool = False, start_seconds: int = 0) -> None:
            return None

        def set_speed(self, speed: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def subtitle_tracks(self) -> list[SubtitleTrack]:
            return []

        def audio_tracks(self) -> list[AudioTrack]:
            return []

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_danmaku_paths.append(path)
            track_id = self._next_track_id
            self._next_track_id += 1
            return track_id

        def remove_subtitle_track(self, track_id: int | None) -> None:
            if track_id is not None:
                self.removed_danmaku_track_ids.append(track_id)

        def supports_secondary_subtitle_position(self) -> bool:
            return False

        def position_seconds(self) -> int:
            return 0

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[PlayItem(title="第1集", url="http://m/1.m3u8", danmaku_xml='<?xml version="1.0" encoding="UTF-8"?><i><d p="0.0,1,25,16777215">第一条</d></i>')],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    config = AppConfig()
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: saved.__setitem__("called", saved["called"] + 1))
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)
    initial_count = len(window.video.loaded_danmaku_paths)

    window._save_danmaku_uniform_color("#00FF00")

    assert saved["called"] == 1
    assert len(window.video.loaded_danmaku_paths) == initial_count + 1
    assert window.video.removed_danmaku_track_ids == [70]


def test_player_window_saves_settings_without_enabling_danmaku_when_currently_off(qtbot) -> None:
    saved = {"called": 0}
    window = PlayerWindow(
        FakePlayerController(),
        config=AppConfig(preferred_danmaku_enabled=False),
        save_config=lambda: saved.__setitem__("called", saved["called"] + 1),
    )
    qtbot.addWidget(window)

    window._save_danmaku_render_mode("mixed")

    assert window.config.preferred_danmaku_enabled is False
    assert window.config.preferred_danmaku_render_mode == "mixed"
    assert saved["called"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "reloads_active_danmaku or without_enabling_danmaku" -v`
Expected: FAIL because there is no `reload_active_danmaku_for_render_settings()` path and no direct save helpers for the new settings.

- [ ] **Step 3: Thread render settings into ASS file creation and add direct save helpers**

```python
def _write_danmaku_subtitle_file(self, xml_text: str, line_count: int) -> Path | None:
    self._cleanup_danmaku_temp_file()
    temp_path = load_or_create_danmaku_ass_cache(
        xml_text,
        line_count,
        render_mode=self._preferred_danmaku_render_mode(),
        color_mode=self._preferred_danmaku_color_mode(),
        uniform_color=self._preferred_danmaku_uniform_color(),
        position_preset=self._preferred_danmaku_position_preset(),
    )
    if temp_path is None:
        return None
    self._danmaku_temp_path = temp_path
    return temp_path


def _save_danmaku_render_mode(self, value: str) -> None:
    if self.config is None:
        return
    normalized = value if value in {"static", "scroll_only", "mixed"} else "static"
    if self.config.preferred_danmaku_render_mode == normalized:
        return
    self.config.preferred_danmaku_render_mode = normalized
    self._save_config()
    self._reload_active_danmaku_for_render_settings()
```

Implement matching `_save_danmaku_color_mode()`, `_save_danmaku_uniform_color()`, and `_save_danmaku_position_preset()` helpers.

- [ ] **Step 4: Add a narrow active-danmaku reload path**

```python
def _reload_active_danmaku_for_render_settings(self) -> None:
    if not self._preferred_danmaku_enabled():
        return
    if not self._danmaku_active:
        return
    current_item = self._current_play_item()
    if current_item is None or not current_item.danmaku_xml:
        return
    try:
        self._enable_danmaku(self._preferred_danmaku_line_count())
    except Exception as exc:
        self._append_log(f"弹幕设置应用失败: {exc}")
```

This must reuse the existing `_enable_danmaku()` / `_clear_active_danmaku()` path so slot ownership, ASS override restoration, and mpv subtitle lifecycle keep their current behavior.

- [ ] **Step 5: Run focused player regression tests**

Run: `uv run pytest tests/test_player_window_ui.py -k "danmaku" -v`
Expected: PASS with existing danmaku combo tests still green and the new immediate-refresh tests added to the same file.

- [ ] **Step 6: Run the full focused regression set**

Run: `uv run pytest tests/test_storage.py tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py -v`
Expected: PASS with all new config, renderer, cache, and player-window behavior covered.

- [ ] **Step 7: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: reload danmaku when render settings change"
```
