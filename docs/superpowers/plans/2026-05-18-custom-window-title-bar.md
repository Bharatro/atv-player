# Custom Window Title Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared custom title bar and frameless window chrome layer for all application-defined windows/dialogs, while keeping native Qt/system dialogs native and hiding the player title bar in fullscreen.

**Architecture:** Add a dedicated `window_chrome.py` module that provides a reusable `CustomTitleBar` plus separate base shells for `QMainWindow`, top-level `QWidget`, and `QDialog`. Then migrate windows in increasing complexity: a simple widget window and simple dialog first, followed by `MainWindow`, then `PlayerWindow` with fullscreen-specific behavior, and finally the remaining dialogs and dynamic `QDialog` creation sites.

**Tech Stack:** Python 3.13, PySide6, pytest, pytest-qt, existing `ThemeManager` / `theme.py` token system

---

## File Structure

- Create: `src/atv_player/ui/window_chrome.py`
  Responsibility: shared title bar widget, frameless chrome bases, drag/maximize/close plumbing, title-bar visibility toggling.
- Modify: `src/atv_player/ui/theme.py`
  Responsibility: add title-bar/window-chrome tokens and reusable stylesheet helpers consumed by the new chrome module.
- Modify: `src/atv_player/ui/login_window.py`
  Responsibility: migrate simple top-level `QWidget` window to `ThemedWidgetWindowBase`.
- Modify: `src/atv_player/ui/plugin_reorder_dialog.py`
  Responsibility: migrate a simple `QDialog` to `ThemedDialogBase` as the first dialog adoption point.
- Modify: `src/atv_player/ui/main_window.py`
  Responsibility: migrate `QMainWindow` to `ThemedMainWindowBase`; keep existing content tree intact inside the new central chrome container.
- Modify: `src/atv_player/ui/player_window.py`
  Responsibility: migrate the player to `ThemedWidgetWindowBase`, hide the title bar during fullscreen, and route runtime-created dialogs through the themed dialog base.
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `src/atv_player/ui/live_source_manager_dialog.py`
- Modify: `src/atv_player/ui/manual_live_source_dialog.py`
- Modify: `src/atv_player/ui/help_dialog.py`
  Responsibility: migrate all remaining custom dialog classes.
- Create: `tests/test_window_chrome.py`
  Responsibility: focused coverage for shared title-bar widget/base behavior.
- Modify: `tests/test_login_window_ui.py`
- Modify: `tests/test_plugin_reorder_dialog.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_plugin_manager_dialog.py`
- Modify: `tests/test_live_source_manager_dialog.py`
  Responsibility: regression tests proving each adopted window/dialog now exposes the shared custom title bar and still preserves existing behavior.

## Task 1: Build the Shared Chrome Layer and Theme Hooks

**Files:**
- Create: `src/atv_player/ui/window_chrome.py`
- Modify: `src/atv_player/ui/theme.py`
- Create: `tests/test_window_chrome.py`

- [ ] **Step 1: Write the failing shared-chrome tests**

```python
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel

from atv_player.ui.window_chrome import (
    CustomTitleBar,
    ThemedDialogBase,
    ThemedWidgetWindowBase,
)


class DemoWindow(ThemedWidgetWindowBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Window", allow_minimize=True, allow_maximize=True)
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


class DemoDialog(ThemedDialogBase):
    def __init__(self) -> None:
        super().__init__(title="Demo Dialog")
        self.content_layout().addWidget(QLabel("body", self.content_widget()))


def test_themed_widget_window_exposes_custom_title_bar_and_frameless_flag(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)

    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.title_bar().objectName() == "customTitleBar"
    assert window.title_bar().title_label.text() == "Demo Window"


def test_themed_dialog_hides_maximize_button_by_default(qtbot) -> None:
    dialog = DemoDialog()
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
    assert dialog.title_bar().minimize_button.isHidden() is True


def test_title_bar_visibility_toggle_hides_chrome_without_hiding_content(qtbot) -> None:
    window = DemoWindow()
    qtbot.addWidget(window)
    window.show()

    window.set_title_bar_visible(False)

    assert window.title_bar().isHidden() is True
    assert window.content_widget().isVisible() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.ui.window_chrome'`

- [ ] **Step 3: Write the minimal shared chrome implementation**

```python
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget


class CustomTitleBar(QWidget):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, allow_minimize: bool, allow_maximize: bool) -> None:
        super().__init__(parent)
        self.setObjectName("customTitleBar")
        self._drag_global_pos: QPoint | None = None
        self.title_label = QLabel("", self)
        self.title_label.setObjectName("customTitleBarLabel")
        self.minimize_button = QPushButton("—", self)
        self.maximize_button = QPushButton("□", self)
        self.close_button = QPushButton("✕", self)
        self.close_button.setObjectName("customTitleBarCloseButton")
        self.minimize_button.clicked.connect(self.minimize_requested.emit)
        self.maximize_button.clicked.connect(self.maximize_toggle_requested.emit)
        self.close_button.clicked.connect(self.close_requested.emit)
        self.minimize_button.setVisible(allow_minimize)
        self.maximize_button.setVisible(allow_maximize)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class _ThemedChromeMixin:
    def _init_chrome(self, title: str, *, allow_minimize: bool, allow_maximize: bool) -> None:
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._chrome_root = QWidget(self)
        self._chrome_root.setObjectName("windowChromeRoot")
        self._chrome_layout = QVBoxLayout(self._chrome_root)
        self._chrome_layout.setContentsMargins(1, 1, 1, 1)
        self._chrome_layout.setSpacing(0)
        self._title_bar = CustomTitleBar(
            self._chrome_root,
            allow_minimize=allow_minimize,
            allow_maximize=allow_maximize,
        )
        self._title_bar.set_title(title)
        self._chrome_layout.addWidget(self._title_bar)
        self._content_host = QWidget(self._chrome_root)
        self._content_host.setObjectName("windowChromeContent")
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._chrome_layout.addWidget(self._content_host, 1)
        self._title_bar.close_requested.connect(self.close)
        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.maximize_toggle_requested.connect(self._toggle_maximized)

    def title_bar(self) -> CustomTitleBar:
        return self._title_bar

    def content_widget(self) -> QWidget:
        return self._content_host

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_title_bar_visible(self, visible: bool) -> None:
        self._title_bar.setVisible(visible)

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()


class ThemedWidgetWindowBase(QWidget, _ThemedChromeMixin):
    def __init__(self, *, title: str, allow_minimize: bool, allow_maximize: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_chrome(title, allow_minimize=allow_minimize, allow_maximize=allow_maximize)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._chrome_root)


class ThemedDialogBase(QDialog, _ThemedChromeMixin):
    def __init__(self, *, title: str, parent: QWidget | None = None, allow_maximize: bool = False) -> None:
        super().__init__(parent)
        self._init_chrome(title, allow_minimize=False, allow_maximize=allow_maximize)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._chrome_root)
```

- [ ] **Step 4: Add theme tokens and stylesheet helper for the new chrome**

```python
@dataclass(frozen=True, slots=True)
class ThemeTokens:
    player_primary_button_icon: str
    titlebar_bg: str
    titlebar_border: str
    titlebar_text: str
    titlebar_button_bg: str
    titlebar_button_hover_bg: str
    titlebar_button_pressed_bg: str
    titlebar_button_close_hover_bg: str
    titlebar_button_close_pressed_bg: str
    window_chrome_bg: str
    window_chrome_border: str


def build_window_chrome_qss(tokens: ThemeTokens) -> str:
    return f"""
    QWidget#windowChromeRoot {{
        background: {tokens.window_chrome_bg};
        border: 1px solid {tokens.window_chrome_border};
        border-radius: 18px;
    }}
    QWidget#customTitleBar {{
        background: {tokens.titlebar_bg};
        border-bottom: 1px solid {tokens.titlebar_border};
        border-top-left-radius: 18px;
        border-top-right-radius: 18px;
    }}
    QLabel#customTitleBarLabel {{
        color: {tokens.titlebar_text};
        font-weight: 600;
    }}
    QWidget#windowChromeContent {{
        background: {tokens.window_chrome_bg};
        border-bottom-left-radius: 18px;
        border-bottom-right-radius: 18px;
    }}
    """
```

- [ ] **Step 5: Run tests and make them pass**

Run: `uv run pytest tests/test_window_chrome.py -v`
Expected: PASS for the new window chrome tests

- [ ] **Step 6: Commit the shared foundation**

```bash
git add src/atv_player/ui/window_chrome.py src/atv_player/ui/theme.py tests/test_window_chrome.py
git commit -m "feat: add themed window chrome foundation"
```

## Task 2: Adopt the Chrome in a Simple Window and Simple Dialog

**Files:**
- Modify: `src/atv_player/ui/login_window.py`
- Modify: `src/atv_player/ui/plugin_reorder_dialog.py`
- Modify: `tests/test_login_window_ui.py`
- Modify: `tests/test_plugin_reorder_dialog.py`

- [ ] **Step 1: Write the failing adoption tests**

```python
from PySide6.QtCore import Qt


def test_login_window_uses_custom_title_bar(qtbot) -> None:
    window = LoginWindow(FakeLoginController())
    qtbot.addWidget(window)

    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.title_bar().title_label.text() == "alist-tvbox 登录"


def test_plugin_reorder_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = PluginReorderDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert dialog.title_bar().title_label.text() == "调整插件顺序"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_login_window_ui.py tests/test_plugin_reorder_dialog.py -k "custom_title_bar" -v`
Expected: FAIL because `LoginWindow` and `PluginReorderDialog` do not expose `title_bar()`

- [ ] **Step 3: Migrate `LoginWindow` to `ThemedWidgetWindowBase`**

```python
from atv_player.ui.window_chrome import ThemedWidgetWindowBase


class LoginWindow(ThemedWidgetWindowBase, AsyncGuardMixin):
    def __init__(self, controller) -> None:
        super().__init__(title="alist-tvbox 登录", allow_minimize=True, allow_maximize=True)
        self._init_async_guard()
        self._controller = controller
        self._login_request_id = 0
        self.setWindowTitle("alist-tvbox 登录")
        self.resize(720, 520)
        layout = self.content_layout()
        layout.addStretch(1)
        layout.addLayout(centered_row)
        layout.addStretch(1)
```

- [ ] **Step 4: Migrate `PluginReorderDialog` to `ThemedDialogBase`**

```python
from atv_player.ui.window_chrome import ThemedDialogBase


class PluginReorderDialog(ThemedDialogBase):
    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(title="调整插件顺序", parent=parent)
        self.plugin_manager = plugin_manager
        self.resize(520, 460)
        layout = self.content_layout()
        layout.addWidget(self.plugin_list)
        layout.addLayout(controls)
        layout.addLayout(footer)
```

- [ ] **Step 5: Run the focused tests and the full file regressions**

Run: `uv run pytest tests/test_login_window_ui.py tests/test_plugin_reorder_dialog.py -v`
Expected: PASS, including existing async/login behavior and reorder flow

- [ ] **Step 6: Commit the first adoption slice**

```bash
git add src/atv_player/ui/login_window.py src/atv_player/ui/plugin_reorder_dialog.py tests/test_login_window_ui.py tests/test_plugin_reorder_dialog.py
git commit -m "feat: adopt custom title bar for login and reorder dialog"
```

## Task 3: Migrate `MainWindow` and Its Direct Dialog Entry Points

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `src/atv_player/ui/live_source_manager_dialog.py`
- Modify: `src/atv_player/ui/help_dialog.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_plugin_manager_dialog.py`
- Modify: `tests/test_live_source_manager_dialog.py`

- [ ] **Step 1: Write the failing main-window and dialog tests**

```python
class DummyHistoryController:
    def list_records(self):
        return []


def test_main_window_uses_custom_title_bar(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    assert window.title_bar().title_label.text() == "alist-tvbox Desktop Player"
    assert window.title_bar().maximize_button.isVisible() is True


def test_plugin_manager_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.title_bar().title_label.text() == "插件管理"


def test_live_source_manager_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = LiveSourceManagerDialog(FakeLiveSourceManager())
    qtbot.addWidget(dialog)

    assert dialog.title_bar().title_label.text() == "直播源管理"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py -k "custom_title_bar" -v`
Expected: FAIL because the window and dialogs still inherit the old top-level classes

- [ ] **Step 3: Introduce `ThemedMainWindowBase` and migrate `MainWindow`**

```python
class ThemedMainWindowBase(QMainWindow):
    def __init__(self, *, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._chrome_root = QWidget(self)
        self._chrome_layout = QVBoxLayout(self._chrome_root)
        self._title_bar = CustomTitleBar(self._chrome_root, allow_minimize=True, allow_maximize=True)
        self._title_bar.set_title(title)
        self._content_host = QWidget(self._chrome_root)
        self._content_layout = QVBoxLayout(self._content_host)
        self._chrome_layout.addWidget(self._title_bar)
        self._chrome_layout.addWidget(self._content_host, 1)
        super().setCentralWidget(self._chrome_root)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout


class MainWindow(ThemedMainWindowBase, AsyncGuardMixin):
    def __init__(self, browse_controller, history_controller, player_controller, config, save_config=None, apply_theme=None, **kwargs) -> None:
        super().__init__(title="alist-tvbox Desktop Player")
        self._init_async_guard()
        self._save_config = save_config or (lambda: None)
        self._apply_application_theme = apply_theme or (lambda: None)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(self.header_layout)
        container_layout.addWidget(self.global_search_status_label)
        container_layout.addWidget(self.nav_tabs)
        self.content_layout().addWidget(container)
```

- [ ] **Step 4: Migrate all directly-instantiated custom dialogs opened from `MainWindow`**

```python
class AdvancedSettingsDialog(ThemedDialogBase):
    def __init__(self, config: AppConfig, save_config: Callable[[], None], parent: QWidget | None = None, apply_theme: Callable[[], None] | None = None) -> None:
        super().__init__(title="高级设置", parent=parent)
        self._config = config
        self._save_config = save_config
        self._apply_application_theme = apply_theme
        layout = self.content_layout()
        layout.addWidget(self.settings_tabs)
        layout.addLayout(button_row)


class PluginManagerDialog(ThemedDialogBase, AsyncGuardMixin):
    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(title="插件管理", parent=parent, allow_maximize=True)
        self._init_async_guard()
        self.plugin_manager = plugin_manager


class LiveSourceManagerDialog(ThemedDialogBase):
    def __init__(self, manager, parent=None) -> None:
        super().__init__(title="直播源管理", parent=parent, allow_maximize=True)
        self.manager = manager
        self.resize(920, 520)
```

- [ ] **Step 5: Keep help-dialog behavior while migrating it to themed chrome**

```python
class ShortcutHelpDialog(ThemedDialogBase):
    def __init__(self, entries: Sequence[ShortcutEntry], parent: QWidget | None = None, *, system_info_rows: Sequence[tuple[str, str]] | None = None, diagnostics_text: str = "") -> None:
        super().__init__(title="帮助", parent=parent, allow_maximize=True)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        layout = self.content_layout()
        if system_info_rows is not None:
            layout.addWidget(QLabel("系统信息", self))
        layout.addWidget(self.shortcuts_table)
```

- [ ] **Step 6: Run the adopted test files**

Run: `uv run pytest tests/test_main_window_ui.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py -v`
Expected: PASS, with existing dialog-opening behavior still intact

- [ ] **Step 7: Commit the main-window slice**

```bash
git add src/atv_player/ui/window_chrome.py src/atv_player/ui/main_window.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/help_dialog.py tests/test_main_window_ui.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py
git commit -m "feat: adopt custom title bar for main window dialogs"
```

## Task 4: Migrate `PlayerWindow` and Hide Its Title Bar in Fullscreen

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window chrome tests**

```python
def test_player_window_uses_custom_title_bar(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.title_bar().title_label.text() == "alist-tvbox 播放器"


def test_player_window_hides_custom_title_bar_in_fullscreen(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()

    window.toggle_fullscreen()

    assert window.isFullScreen() is True
    assert window.title_bar().isHidden() is True


def test_player_window_restores_custom_title_bar_after_exiting_fullscreen(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.show()
    window.toggle_fullscreen()

    window.toggle_fullscreen()

    assert window.isFullScreen() is False
    assert window.title_bar().isVisible() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "custom_title_bar or hides_custom_title_bar_in_fullscreen or restores_custom_title_bar_after_exiting_fullscreen" -v`
Expected: FAIL because `PlayerWindow` still subclasses plain `QWidget`

- [ ] **Step 3: Migrate `PlayerWindow` to `ThemedWidgetWindowBase`**

```python
from atv_player.ui.window_chrome import ThemedDialogBase, ThemedWidgetWindowBase


class PlayerWindow(ThemedWidgetWindowBase, AsyncGuardMixin):
    def __init__(self, controller, config=None, save_config=None, m3u8_ad_filter=None, playback_parser_service=None, default_video_cover_loader=None) -> None:
        super().__init__(title=self._default_window_title(), allow_minimize=True, allow_maximize=True)
        self._init_async_guard()
        self.controller = controller
        self.config = config
        self._save_config = save_config or (lambda: None)
        layout = self.content_layout()
        layout.addWidget(self.main_splitter_host)

    def _refresh_window_title(self) -> None:
        title = self._active_playback_title() if self.session is not None else self._default_window_title()
        self.setWindowTitle(title)
        self.title_bar().set_title(title)
```

- [ ] **Step 4: Tie title-bar visibility to fullscreen state**

```python
def toggle_fullscreen(self) -> None:
    if self.isFullScreen():
        if self._was_maximized_before_fullscreen:
            self.showMaximized()
        else:
            self.showNormal()
        self._apply_visibility_state()
        return
    self._remember_sidebar_sizes()
    self._was_maximized_before_fullscreen = self.isMaximized()
    self.showFullScreen()
    self._apply_visibility_state()


def _apply_visibility_state(self) -> None:
    is_fullscreen = self.isFullScreen()
    self.set_title_bar_visible(not is_fullscreen)
    self.bottom_area.setHidden(is_fullscreen)
```

- [ ] **Step 5: Convert runtime-created player dialogs to the themed dialog base**

```python
class _PlayerFormDialog(ThemedDialogBase):
    def __init__(self, title: str, parent: QWidget) -> None:
        super().__init__(title=title, parent=parent, allow_maximize=True)
        self.resize(760, 480)


def _ensure_danmaku_settings_dialog(self) -> QDialog:
    if self._danmaku_settings_dialog is not None:
        return self._danmaku_settings_dialog
    dialog = _PlayerFormDialog("弹幕设置", self)
    layout = dialog.content_layout()
    layout.addLayout(line_count_row)
    layout.addLayout(render_row)
    layout.addLayout(position_row)
    self._danmaku_settings_dialog = dialog
    return dialog
```

- [ ] **Step 6: Run the player tests**

Run: `uv run pytest tests/test_player_window_ui.py -v`
Expected: PASS, including existing fullscreen/sidebar behavior plus the new title-bar visibility checks

- [ ] **Step 7: Commit the player slice**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add custom title bar to player window"
```

## Task 5: Migrate Remaining Dialogs and Close Coverage Gaps

**Files:**
- Modify: `src/atv_player/ui/manual_live_source_dialog.py`
- Modify: `tests/test_live_source_manager_dialog.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing remaining-dialog tests**

```python
def test_manual_live_source_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = ManualLiveSourceDialog(FakeLiveSourceManager(), 2)
    qtbot.addWidget(dialog)

    assert dialog.title_bar().title_label.text() == "管理频道"


def test_manual_entry_form_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = _ManualEntryFormDialog()
    qtbot.addWidget(dialog)

    assert dialog.title_bar().title_label.text() == "频道信息"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_live_source_manager_dialog.py -k "custom_title_bar" -v`
Expected: FAIL because `ManualLiveSourceDialog` and `_ManualEntryFormDialog` still inherit plain `QDialog`

- [ ] **Step 3: Migrate the remaining manual-live dialogs**

```python
from atv_player.ui.window_chrome import ThemedDialogBase


class _ManualEntryFormDialog(ThemedDialogBase):
    def __init__(self, *, group_name: str = "", channel_name: str = "", stream_url: str = "", logo_url: str = "", parent=None) -> None:
        super().__init__(title="频道信息", parent=parent)
        self.group_edit = QLineEdit(group_name, self)
        self.channel_edit = QLineEdit(channel_name, self)
        layout = self.content_layout()
        layout.addLayout(form)
        layout.addLayout(actions)


class ManualLiveSourceDialog(ThemedDialogBase):
    def __init__(self, manager, source_id: int, parent=None) -> None:
        super().__init__(title="管理频道", parent=parent, allow_maximize=True)
        self.manager = manager
        self.source_id = source_id
        layout = self.content_layout()
        layout.addLayout(actions)
        layout.addWidget(self.entry_table)
```

- [ ] **Step 4: Add a regression test proving native Qt dialogs are still native entry points**

```python
def test_live_source_manager_dialog_still_uses_qfiledialog_entry_point(qtbot, monkeypatch) -> None:
    manager = FakeLiveSourceManager()
    dialog = LiveSourceManagerDialog(manager)
    qtbot.addWidget(dialog)
    calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        "atv_player.ui.live_source_manager_dialog.QFileDialog.getOpenFileName",
        lambda *args: calls.append((args[1], args[2], args[3])) or ("/tmp/demo.m3u", ""),
    )

    dialog._add_local_source()

    assert calls == [("选择直播源文件", "", "Live Source Files (*.m3u *.m3u8 *.txt)")]
```

- [ ] **Step 5: Run the remaining regression files**

Run: `uv run pytest tests/test_live_source_manager_dialog.py tests/test_main_window_ui.py -v`
Expected: PASS, with themed custom dialogs and unchanged native dialog call paths

- [ ] **Step 6: Commit the final dialog coverage**

```bash
git add src/atv_player/ui/manual_live_source_dialog.py tests/test_live_source_manager_dialog.py tests/test_main_window_ui.py
git commit -m "feat: finish custom title bar dialog coverage"
```

## Task 6: Final Verification Pass

**Files:**
- Modify: `src/atv_player/ui/window_chrome.py`
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/ui/login_window.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `src/atv_player/ui/plugin_reorder_dialog.py`
- Modify: `src/atv_player/ui/live_source_manager_dialog.py`
- Modify: `src/atv_player/ui/manual_live_source_dialog.py`
- Modify: `src/atv_player/ui/help_dialog.py`
- Modify: `tests/test_window_chrome.py`
- Modify: `tests/test_login_window_ui.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_plugin_manager_dialog.py`
- Modify: `tests/test_plugin_reorder_dialog.py`
- Modify: `tests/test_live_source_manager_dialog.py`

- [ ] **Step 1: Run the full targeted test suite**

Run: `uv run pytest tests/test_window_chrome.py tests/test_login_window_ui.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_plugin_manager_dialog.py tests/test_plugin_reorder_dialog.py tests/test_live_source_manager_dialog.py -v`
Expected: PASS across all custom-window and dialog coverage

- [ ] **Step 2: Run a lightweight import/compile sanity check**

Run: `uv run python -m py_compile src/atv_player/ui/window_chrome.py src/atv_player/ui/theme.py src/atv_player/ui/login_window.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/plugin_reorder_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/manual_live_source_dialog.py src/atv_player/ui/help_dialog.py`
Expected: no output

- [ ] **Step 3: Commit any final polish fixes**

```bash
git add src/atv_player/ui/window_chrome.py src/atv_player/ui/theme.py src/atv_player/ui/login_window.py src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/plugin_reorder_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/manual_live_source_dialog.py src/atv_player/ui/help_dialog.py tests/test_window_chrome.py tests/test_login_window_ui.py tests/test_main_window_ui.py tests/test_player_window_ui.py tests/test_plugin_manager_dialog.py tests/test_plugin_reorder_dialog.py tests/test_live_source_manager_dialog.py
git commit -m "test: verify custom title bar rollout"
```

## Self-Review

- Spec coverage:
  - Shared custom title-bar foundation: Task 1
  - Theme token integration: Task 1
  - `LoginWindow`: Task 2
  - `MainWindow`: Task 3
  - `PlayerWindow` fullscreen title-bar hiding: Task 4
  - Static custom dialogs: Tasks 2, 3, and 5
  - Runtime-created player dialogs: Task 4
  - Native dialog exemptions: Task 5
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to task N” placeholders remain.
  - Every code-writing step includes concrete code blocks and exact file paths.
- Type consistency:
  - Shared API names are consistent across tasks: `CustomTitleBar`, `ThemedMainWindowBase`, `ThemedWidgetWindowBase`, `ThemedDialogBase`, `title_bar()`, `content_widget()`, `content_layout()`, `set_title_bar_visible()`.
