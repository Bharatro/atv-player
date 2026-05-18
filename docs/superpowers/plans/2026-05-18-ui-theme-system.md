# UI Theme System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persisted light/dark/follow-system theme system with a centralized `ThemeManager`, add an `外观` tab to `AdvancedSettingsDialog`, and apply the theme across top-level windows plus a mixed-mode `PlayerWindow` with a permanently dark immersive playback layer.

**Architecture:** Add a new `src/atv_player/ui/theme.py` module that resolves `theme_mode`, exposes theme tokens, and installs application-wide palette and stylesheet state. Persist `theme_mode` in `AppConfig` and `SettingsRepository`, wire a single refresh path through `app.py`, then migrate key UI surfaces to consume centralized tokens instead of hard-coded color literals. `PlayerWindow` follows the global theme for side panels and dialogs but keeps video overlays and controls on a dark token set.

**Tech Stack:** Python 3.14, PySide6 6.11, SQLite, `pytest`, `pytest-qt`

---

## File Map

- Modify `src/atv_player/models.py`
  Add persisted `theme_mode` to `AppConfig`.
- Modify `src/atv_player/storage.py`
  Add schema migration, normalization, and load/save support for `theme_mode`.
- Create `src/atv_player/ui/theme.py`
  Define theme constants, token dataclasses, system-theme resolution helpers, application stylesheet builders, and install/apply helpers.
- Modify `src/atv_player/app.py`
  Create and install `ThemeManager` during app startup, expose a single refresh path, and pass theme refresh callbacks into UI entry points.
- Modify `src/atv_player/ui/advanced_settings_dialog.py`
  Add the `外观` tab, theme-mode controls, and callback wiring for immediate apply after save.
- Modify `src/atv_player/ui/login_window.py`
  Apply shared container and form styling via theme helpers.
- Modify `src/atv_player/ui/main_window.py`
  Replace main-window hard-coded QSS constants with theme-generated strings and pass theme refresh callback into `AdvancedSettingsDialog`.
- Modify `src/atv_player/ui/history_page.py`
  Replace local hard-coded search/toggle styles with theme-driven helpers.
- Modify `src/atv_player/ui/poster_grid_page.py`
  Replace hard-coded filter/button/label colors with theme tokens.
- Modify `src/atv_player/ui/plugin_manager_dialog.py`
  Replace placeholder action styling and warning/panel styling with theme tokens.
- Modify `src/atv_player/ui/live_source_manager_dialog.py`
  Apply the same dialog token strategy as the plugin manager.
- Modify `src/atv_player/ui/player_window.py`
  Apply global theme tokens to side panels and keep immersive overlays on dark tokens.
- Modify `tests/test_storage.py`
  Cover `theme_mode` persistence and migration.
- Create `tests/test_theme.py`
  Cover `ThemeManager` resolution, fallback, token selection, and player immersive token behavior.
- Modify `tests/test_app.py`
  Cover app startup theme installation and refresh behavior.
- Modify `tests/test_main_window_ui.py`
  Cover the new `外观` tab and save/apply flow in `AdvancedSettingsDialog`.
- Modify `tests/test_player_window_ui.py`
  Cover mixed-mode player theme expectations.

### Task 1: Persist `theme_mode` In `AppConfig` And SQLite

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing persistence tests**

```python
def test_settings_repository_defaults_theme_mode_to_system(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    assert repo.load_config().theme_mode == "system"


def test_settings_repository_round_trip_persists_theme_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(theme_mode="dark")

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.theme_mode == "dark"


def test_settings_repository_normalizes_invalid_theme_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    repo.save_config(AppConfig(theme_mode="sepia"))

    assert repo.load_config().theme_mode == "system"
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -k theme_mode -q`

Expected: FAIL with `TypeError: AppConfig.__init__() got an unexpected keyword argument 'theme_mode'` or missing-column assertions.

- [ ] **Step 3: Add `theme_mode` to `AppConfig` and `SettingsRepository`**

```python
# src/atv_player/models.py
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    theme_mode: str = "system"
    metadata_enhancement_enabled: bool = True
    metadata_douban_cookie: str = ""
    metadata_tmdb_api_key: str = ""
    metadata_bangumi_access_token: str = ""
```

```python
# src/atv_player/storage.py
_VALID_THEME_MODES = {"light", "dark", "system"}


def _normalize_theme_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_THEME_MODES else "system"
```

```python
# src/atv_player/storage.py inside CREATE TABLE
theme_mode TEXT NOT NULL DEFAULT 'system',
```

```python
# src/atv_player/storage.py inside migration block
if "theme_mode" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN theme_mode TEXT NOT NULL DEFAULT 'system'"
    )
```

```python
# src/atv_player/storage.py inside INSERT default row / SELECT / UPDATE tuples
theme_mode,
metadata_enhancement_enabled,
episode_title_enhancement_enabled,
theme_mode=_normalize_theme_mode(theme_mode),
metadata_enhancement_enabled=bool(metadata_enhancement_enabled),
episode_title_enhancement_enabled=bool(episode_title_enhancement_enabled),
_normalize_theme_mode(config.theme_mode),
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -k theme_mode -q`

Expected: PASS with defaults, round-trip, and invalid-value normalization all green.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist ui theme mode"
```

### Task 2: Add `ThemeManager` Core Resolution And Application Installation

**Files:**
- Create: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_theme.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing theme-core tests**

```python
def test_theme_manager_resolves_system_mode_to_dark_when_style_hints_report_dark() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")

    assert manager.resolve_mode("system") == "dark"


def test_theme_manager_falls_back_to_light_when_system_theme_unknown() -> None:
    manager = ThemeManager(system_theme_getter=lambda: None)

    assert manager.resolve_mode("system") == "light"


def test_theme_manager_player_tokens_remain_dark_in_light_app_theme() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")

    app_tokens = manager.tokens_for("light")
    player_tokens = manager.player_tokens_for("light")

    assert app_tokens.window_bg != player_tokens.player_overlay_bg
    assert player_tokens.player_text_on_dark.startswith("#")


def test_build_application_installs_theme_manager_from_saved_config(monkeypatch, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    repo = SettingsRepository(tmp_path / "app.db")
    repo.save_config(AppConfig(theme_mode="dark"))

    monkeypatch.setattr(app_module, "QApplication", lambda args: app)
    monkeypatch.setattr(app_module, "SettingsRepository", lambda _path: repo)

    built_app, built_repo = app_module.build_application()

    assert built_repo is repo
    assert hasattr(built_app, "_theme_manager")
    assert built_app.property("resolved_theme") == "dark"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_theme.py tests/test_app.py -k "theme_manager or build_application_installs_theme_manager" -q`

Expected: FAIL because `ThemeManager` does not exist and `build_application()` does not install theme state.

- [ ] **Step 3: Create `ThemeManager` and app-level install helpers**

```python
# src/atv_player/ui/theme.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ThemeMode = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    window_bg: str
    panel_bg: str
    panel_alt_bg: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    input_bg: str
    input_border: str
    button_bg: str
    button_primary_bg: str
    button_primary_text: str
    player_overlay_bg: str
    player_controls_bg: str
    player_scrim: str
    player_text_on_dark: str


class ThemeManager:
    def __init__(self, system_theme_getter: Callable[[], str | None] | None = None) -> None:
        self._system_theme_getter = system_theme_getter or self._default_system_theme

    def resolve_mode(self, mode: str) -> ResolvedTheme:
        normalized = str(mode or "system").strip().lower()
        if normalized == "light":
            return "light"
        if normalized == "dark":
            return "dark"
        system_theme = self._system_theme_getter()
        return "dark" if system_theme == "dark" else "light"

    def tokens_for(self, theme: ResolvedTheme) -> ThemeTokens:
        if theme == "dark":
            return DARK_TOKENS
        return LIGHT_TOKENS

    def player_tokens_for(self, _theme: ResolvedTheme) -> ThemeTokens:
        return PLAYER_IMMERSIVE_TOKENS

    def build_palette(self, theme: ResolvedTheme) -> QPalette:
        tokens = self.tokens_for(theme)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens.window_bg))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.input_bg))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens.button_bg))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.button_primary_text))
        return palette

    def build_application_stylesheet(self, theme: ResolvedTheme) -> str:
        tokens = self.tokens_for(theme)
        return f"""
        QWidget {{
            background-color: {tokens.window_bg};
            color: {tokens.text_primary};
        }}
        QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QTextEdit {{
            background-color: {tokens.input_bg};
            border: 1px solid {tokens.input_border};
            border-radius: 12px;
        }}
        QPushButton {{
            background-color: {tokens.button_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 12px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            border-color: {tokens.accent_hover};
        }}
        """


def install_theme(app: QApplication, manager: ThemeManager, mode: str) -> str:
    resolved = manager.resolve_mode(mode)
    app.setPalette(manager.build_palette(resolved))
    app.setStyleSheet(manager.build_application_stylesheet(resolved))
    app.setProperty("resolved_theme", resolved)
    app.setProperty("theme_mode", mode)
    setattr(app, "_theme_manager", manager)
    return resolved
```

```python
# src/atv_player/app.py
from atv_player.ui.theme import ThemeManager, install_theme


def build_application() -> tuple[QApplication, SettingsRepository]:
    app = QApplication([])
    _install_button_pointing_hand_cursor(app)
    _install_main_thread_gc_workaround(app)
    app.setApplicationName("atv-player")
    if hasattr(app, "setApplicationVersion"):
        app.setApplicationVersion(resolve_app_version())
    app.setWindowIcon(load_icon(_app_icon_path()))
    data_dir = app_data_dir()
    repo = SettingsRepository(data_dir / "app.db")
    theme_manager = ThemeManager()
    install_theme(app, theme_manager, repo.load_config().theme_mode)
    purge_stale_poster_cache()
    threading.Thread(target=purge_stale_danmaku_cache, daemon=True).start()
    return app, repo
```

- [ ] **Step 4: Add a reusable app-level refresh helper and verify tests pass**

```python
# src/atv_player/app.py
def apply_saved_theme(app: QApplication, repo: SettingsRepository) -> str:
    manager = getattr(app, "_theme_manager", None)
    if manager is None:
        manager = ThemeManager()
        setattr(app, "_theme_manager", manager)
    return install_theme(app, manager, repo.load_config().theme_mode)
```

Run: `uv run pytest tests/test_theme.py tests/test_app.py -k "theme_manager or build_application_installs_theme_manager" -q`

Expected: PASS with both pure logic tests and application wiring tests green.

- [ ] **Step 5: Commit the theme-core slice**

```bash
git add tests/test_theme.py tests/test_app.py src/atv_player/ui/theme.py src/atv_player/app.py
git commit -m "feat: add application theme manager"
```

### Task 3: Add `外观` Tab And Immediate Apply Flow In `AdvancedSettingsDialog`

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing dialog tests**

```python
def test_advanced_settings_dialog_adds_appearance_tab_and_populates_theme_mode(qtbot) -> None:
    dialog = AdvancedSettingsDialog(AppConfig(theme_mode="dark"), save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.tabText(0) == "外观"
    assert dialog.settings_tabs.tabText(1) == "播放设置"
    assert dialog.theme_mode_combo.currentData() == "dark"


def test_advanced_settings_dialog_saves_theme_mode_and_calls_theme_refresh(qtbot) -> None:
    saved: list[str] = []
    refreshed: list[bool] = []
    config = AppConfig(theme_mode="system")
    dialog = AdvancedSettingsDialog(
        config,
        save_config=lambda: saved.append(config.theme_mode),
        apply_theme=lambda: refreshed.append(True),
    )
    qtbot.addWidget(dialog)

    dialog.theme_mode_combo.setCurrentIndex(dialog.theme_mode_combo.findData("light"))
    dialog.save_button.click()

    assert saved == ["light"]
    assert refreshed == [True]
    assert config.theme_mode == "light"
```

- [ ] **Step 2: Run the dialog tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "appearance_tab or theme_mode" -q`

Expected: FAIL because the dialog has no `外观` tab, no `theme_mode_combo`, and no theme-refresh callback path.

- [ ] **Step 3: Add `外观` tab controls and callback plumbing**

```python
# src/atv_player/ui/advanced_settings_dialog.py
class AdvancedSettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        save_config: Callable[[], None],
        parent: QWidget | None = None,
        apply_theme: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._save_config = save_config
        self._apply_theme = apply_theme
        self.appearance_tab = QWidget()
        self.theme_mode_combo = QComboBox()
        self.theme_mode_combo.addItem("浅色", "light")
        self.theme_mode_combo.addItem("深色", "dark")
        self.theme_mode_combo.addItem("跟随系统", "system")
        self.theme_hint_label = QLabel("跟随系统会在应用启动时读取当前系统浅深色；播放器播放区保持偏暗。")
        self.theme_hint_label.setWordWrap(True)
        self.theme_mode_combo.setCurrentIndex(
            max(0, self.theme_mode_combo.findData(config.theme_mode))
        )
        appearance_layout = QFormLayout()
        appearance_layout.addRow("界面主题", self.theme_mode_combo)
        appearance_layout.addRow("说明", self.theme_hint_label)
        self.appearance_tab.setLayout(appearance_layout)
        self.settings_tabs.addTab(self.appearance_tab, "外观")
        self.settings_tabs.addTab(self.playback_tab, "播放设置")
        self.settings_tabs.addTab(self.metadata_tab, "元数据")
        self.settings_tabs.addTab(self.network_proxy_tab, "网络代理")
```

```python
# src/atv_player/ui/advanced_settings_dialog.py inside _save()
self._config.theme_mode = str(self.theme_mode_combo.currentData() or "system")
self._save_config()
if self._apply_theme is not None:
    self._apply_theme()
self.accept()
```

```python
# src/atv_player/ui/main_window.py
class MainWindow(QMainWindow, AsyncGuardMixin):
    def __init__(
        self,
        browse_controller,
        history_controller,
        player_controller,
        config,
        save_config=None,
        apply_theme=None,
        douban_controller=None,
        telegram_controller=None,
        bilibili_controller=None,
        live_controller=None,
        live_source_manager=None,
        emby_controller=None,
        jellyfin_controller=None,
        feiniu_controller=None,
        pansou_controller=None,
        spider_plugins=None,
        plugin_loader_task=None,
        plugin_manager=None,
        drive_detail_loader=None,
        offline_download_detail_loader=None,
        direct_parse_detail_loader=None,
        direct_parse_danmaku_loader=None,
        direct_parse_playback_history_loader=None,
        direct_parse_playback_history_saver=None,
        default_video_cover_loader=None,
        global_search_hotkey_loader=None,
        global_search_suggestion_loader=None,
        show_bilibili_tab: bool = False,
        show_emby_tab: bool = True,
        show_jellyfin_tab: bool = True,
        show_feiniu_tab: bool = True,
        m3u8_ad_filter=None,
        playback_parser_service=None,
        yt_dlp_service=None,
        metadata_hydrator_factory=None,
        metadata_scrape_service_factory=None,
        episode_title_enhancer_factory=None,
        metadata_binding_repository=None,
    ) -> None:
        self._save_config = save_config or (lambda: None)
        self._apply_theme = apply_theme

    def _open_advanced_settings(self) -> None:
        dialog = AdvancedSettingsDialog(
            self.config,
            self._save_config,
            self,
            apply_theme=self._apply_theme,
        )
        dialog.exec()
```

```python
# src/atv_player/app.py
self.main_window = MainWindow(
    browse_controller=browse_controller,
    history_controller=history_controller,
    player_controller=player_controller,
    config=config,
    save_config=lambda: self.repo.save_config(config),
    douban_controller=douban_controller,
    telegram_controller=telegram_controller,
    bilibili_controller=bilibili_controller,
    live_controller=live_controller,
    live_source_manager=live_source_manager,
    emby_controller=emby_controller,
    jellyfin_controller=jellyfin_controller,
    feiniu_controller=feiniu_controller,
    pansou_controller=pansou_controller,
    spider_plugins=[],
    plugin_loader_task=plugin_loader_task,
    plugin_manager=self._plugin_manager,
    drive_detail_loader=drive_detail_loader,
    offline_download_detail_loader=offline_download_detail_loader,
    direct_parse_detail_loader=load_direct_parse_detail,
    apply_theme=lambda: apply_saved_theme(QApplication.instance(), self.repo),
)
```

- [ ] **Step 4: Run the dialog/app tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "appearance_tab or theme_mode" -q`

Expected: PASS with the new tab ordering, saved config, and immediate apply callback verified.

- [ ] **Step 5: Commit the settings-entry slice**

```bash
git add tests/test_main_window_ui.py tests/test_app.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/main_window.py src/atv_player/app.py
git commit -m "feat: add theme settings tab"
```

### Task 4: Migrate Top-Level Windows And Major Dialogs To Shared Theme Tokens

**Files:**
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/login_window.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/ui/history_page.py`
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `src/atv_player/ui/live_source_manager_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing UI-token migration tests**

```python
def test_history_page_search_styles_follow_resolved_dark_theme(qtbot) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    install_theme(app, manager, "dark")
    page = HistoryPage(controller=FakeHistoryController([]))
    qtbot.addWidget(page)

    assert "#d0d7de" not in page.search_edit.styleSheet()
    assert manager.tokens_for("dark").input_border in page.search_edit.styleSheet()


def test_advanced_settings_dialog_uses_appearance_tab_as_first_tab(qtbot) -> None:
    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert [dialog.settings_tabs.tabText(i) for i in range(dialog.settings_tabs.count())][:2] == ["外观", "播放设置"]
```

- [ ] **Step 2: Run the focused UI tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "history_page_search_styles_follow_resolved_dark_theme or appearance_tab_as_first_tab" -q`

Expected: FAIL because page-level styles still contain old hard-coded literals.

- [ ] **Step 3: Expand `theme.py` with page helper functions and replace the hardest-coded surfaces first**

```python
# src/atv_player/ui/theme.py
def current_theme_manager() -> ThemeManager | None:
    app = QApplication.instance()
    return getattr(app, "_theme_manager", None) if app is not None else None


def current_tokens() -> ThemeTokens:
    app = QApplication.instance()
    manager = current_theme_manager() or ThemeManager()
    resolved = str(app.property("resolved_theme") or "light") if app is not None else "light"
    return manager.tokens_for("dark" if resolved == "dark" else "light")


def build_pill_button_qss(tokens: ThemeTokens, *, checked_accent: bool = False) -> str:
    checked_block = ""
    if checked_accent:
        checked_block = f"""
        QPushButton:checked {{
            color: {tokens.accent};
            border: 1px solid {tokens.accent};
            background-color: {tokens.panel_bg};
        }}
        """
    return f"""
    QPushButton {{
        background-color: {tokens.button_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 14px;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        border-color: {tokens.accent_hover};
    }}
    {checked_block}
    """


def build_search_line_edit_qss(tokens: ThemeTokens) -> str:
    return f"""
    QLineEdit {{
        min-height: 30px;
        padding: 0 10px;
        border: 1px solid {tokens.input_border};
        border-radius: 15px;
        background: {tokens.input_bg};
        color: {tokens.text_primary};
    }}
    QLineEdit:focus {{
        border: 1px solid {tokens.accent};
    }}
    """
```

```python
# src/atv_player/ui/history_page.py
from atv_player.ui.theme import build_pill_button_qss, build_search_line_edit_qss, current_tokens

tokens = current_tokens()
self.search_edit.setStyleSheet(build_search_line_edit_qss(tokens))
self.continue_button.setStyleSheet(build_pill_button_qss(tokens, checked_accent=True))
```

```python
# src/atv_player/ui/plugin_manager_dialog.py
from atv_player.ui.theme import current_tokens

def _placeholder_action_style() -> str:
    tokens = current_tokens()
    return f"""
    QLabel {{
        border: 1px solid {tokens.border_subtle};
        padding: 4px 14px;
        background-color: {tokens.panel_alt_bg};
        color: {tokens.text_secondary};
    }}
    """
```

```python
# src/atv_player/ui/main_window.py
tokens = current_tokens()
self._container.setStyleSheet(build_main_container_qss(tokens))
self.hot_source_tab_bar.setStyleSheet(build_hot_tab_qss(tokens))
self.global_search_edit.setStyleSheet(build_global_search_qss(tokens))
```

- [ ] **Step 4: Extend the migration to login window, poster-grid filters, and the live/plugin manager dialogs, then run the tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog or history_page or poster_grid_page" -q`

Expected: PASS with no remaining assertions tied to old light-only literals; update brittle assertions to compare token-derived values where needed.

- [ ] **Step 5: Commit the shared-window migration slice**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/theme.py src/atv_player/ui/login_window.py src/atv_player/ui/main_window.py src/atv_player/ui/history_page.py src/atv_player/ui/poster_grid_page.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/live_source_manager_dialog.py
git commit -m "feat: theme top-level windows and dialogs"
```

### Task 5: Apply Mixed-Mode Theme Rules To `PlayerWindow`

**Files:**
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-theme tests**

```python
def test_player_window_details_panel_uses_global_light_theme_tokens(qtbot, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "light")
    install_theme(app, manager, "light")
    window = build_player_window(qtbot, monkeypatch)

    tokens = manager.tokens_for("light")
    assert tokens.panel_bg in window.details_panel.styleSheet()


def test_player_window_immersive_controls_remain_dark_in_light_theme(qtbot, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "light")
    install_theme(app, manager, "light")
    window = build_player_window(qtbot, monkeypatch)

    player_tokens = manager.player_tokens_for("light")
    assert player_tokens.player_controls_bg in window.controls_container.styleSheet()
```

- [ ] **Step 2: Run the focused player tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "global_light_theme_tokens or immersive_controls_remain_dark" -q`

Expected: FAIL because `PlayerWindow` does not yet expose themed details/control styles.

- [ ] **Step 3: Add explicit player-surface builders to `theme.py` and apply them in `PlayerWindow`**

```python
# src/atv_player/ui/theme.py
def build_player_panel_qss(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        background-color: {tokens.panel_bg};
        color: {tokens.text_primary};
    }}
    QPushButton {{
        background-color: {tokens.button_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 12px;
    }}
    """


def build_player_immersive_qss(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        background-color: {tokens.player_overlay_bg};
        color: {tokens.player_text_on_dark};
    }}
    QPushButton {{
        background-color: {tokens.player_controls_bg};
        color: {tokens.player_text_on_dark};
        border: 1px solid {tokens.player_scrim};
        border-radius: 12px;
    }}
    """
```

```python
# src/atv_player/ui/player_window.py
from atv_player.ui.theme import current_theme_manager

def _apply_theme(self) -> None:
    manager = current_theme_manager() or ThemeManager()
    app = QApplication.instance()
    resolved = str(app.property("resolved_theme") or "light") if app is not None else "light"
    tokens = manager.tokens_for("dark" if resolved == "dark" else "light")
    player_tokens = manager.player_tokens_for("dark" if resolved == "dark" else "light")
    self.details_panel.setStyleSheet(build_player_panel_qss(tokens))
    self.controls_container.setStyleSheet(build_player_immersive_qss(player_tokens))
    self._log_container.setStyleSheet(build_player_panel_qss(tokens))
```

```python
# src/atv_player/ui/player_window.py
def showEvent(self, event) -> None:
    self._apply_theme()
    super().showEvent(event)
```

- [ ] **Step 4: Run the focused player tests, then the broader player UI suite**

Run: `uv run pytest tests/test_player_window_ui.py -k "global_light_theme_tokens or immersive_controls_remain_dark" -q`

Expected: PASS with the details panel following global theme tokens while immersive controls remain dark.

Run: `uv run pytest tests/test_player_window_ui.py -q`

Expected: PASS with no regressions in existing player UI behavior.

- [ ] **Step 5: Commit the player-theme slice**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/theme.py src/atv_player/ui/player_window.py
git commit -m "feat: add mixed player theme support"
```

### Task 6: Final Verification And Cleanup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/theme.py`
- Modify: any touched UI files from prior tasks

- [ ] **Step 1: Run the consolidated targeted test matrix**

Run: `uv run pytest tests/test_storage.py tests/test_theme.py tests/test_app.py tests/test_main_window_ui.py tests/test_player_window_ui.py -q`

Expected: PASS with theme persistence, installation, dialog save flow, and mixed-mode player behavior all green.

- [ ] **Step 2: Manually scan for old hard-coded theme literals in migrated files**

Run: `rg -n "#d0d7de|#0066cc|#ffffff|#1a1a1a|#f6f8fa|#e7d8c8|#b06b3c" src/atv_player/ui/main_window.py src/atv_player/ui/history_page.py src/atv_player/ui/poster_grid_page.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/player_window.py`

Expected: No matches in migrated theme-sensitive surfaces except intentional non-theme usages such as user-selected danmaku color previews.

- [ ] **Step 3: Fix any residual literal leaks with token builders, then rerun the targeted matrix**

```python
# src/atv_player/ui/poster_grid_page.py example
tokens = current_tokens()
button.setStyleSheet(build_pill_button_qss(tokens))
label.setStyleSheet(f"color: {tokens.accent};")
```

Run: `uv run pytest tests/test_storage.py tests/test_theme.py tests/test_app.py tests/test_main_window_ui.py tests/test_player_window_ui.py -q`

Expected: PASS after any cleanup edits.

- [ ] **Step 4: Run the full suite before merge**

Run: `uv run pytest -q`

Expected: PASS for the full repository test suite.

- [ ] **Step 5: Commit the verification/cleanup slice**

```bash
git add tests/test_app.py tests/test_main_window_ui.py tests/test_player_window_ui.py src/atv_player/ui/theme.py src/atv_player/ui/main_window.py src/atv_player/ui/history_page.py src/atv_player/ui/poster_grid_page.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/player_window.py
git commit -m "test: verify ui theme system rollout"
```

## Self-Review

### Spec coverage

- `light | dark | system` persisted theme mode: covered by Task 1.
- Centralized `ThemeManager` plus startup `follow-system` resolution: covered by Task 2.
- `AdvancedSettingsDialog` `外观` tab and immediate apply behavior: covered by Task 3.
- Coverage across top-level windows and major dialogs: covered by Task 4.
- Mixed-mode `PlayerWindow` with dark immersive layer: covered by Task 5.
- Verification against regressions and literal leaks: covered by Task 6.

No spec requirement is left without an implementing task.

### Placeholder scan

- No `TODO` / `TBD` placeholders remain.
- Every code-changing step includes a concrete code snippet.
- Every test/run step includes the exact command and expected result.

### Type consistency

- Persisted field name is consistently `theme_mode`.
- Theme resolver type names are consistently `ThemeManager`, `ThemeTokens`, `ThemeMode`, and `ResolvedTheme`.
- The refresh path consistently uses `apply_saved_theme` and `apply_theme` callback naming.
- Player mixed-mode helpers consistently use `player_tokens_for` and player-surface builders.
