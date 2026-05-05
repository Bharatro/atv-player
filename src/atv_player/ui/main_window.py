from __future__ import annotations
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from atv_player.ui.browse_page import BrowsePage
from atv_player.models import HistoryRecord, OpenPlayerRequest, VodItem
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.help_dialog import ShortcutHelpDialog, show_shortcut_help_dialog
from atv_player.ui.icon_cache import load_icon
from atv_player.ui.poster_grid_page import PosterGridPage
from atv_player.ui.history_page import HistoryPage
from atv_player.ui.live_source_manager_dialog import LiveSourceManagerDialog
from atv_player.ui.plugin_manager_dialog import PluginManagerDialog
from atv_player.ui.player_window import PlayerWindow
from atv_player.ui.qt_compat import qbytearray_to_bytes, to_qbytearray


class _EmptyDoubanController:
    def load_categories(self):
        return []

    def load_items(self, category_id: str, page: int):
        return [], 0


class _EmptyTelegramController(_EmptyDoubanController):
    def build_request(self, vod_id: str):
        raise ValueError(f"没有可播放的项目: {vod_id}")


class _EmptyLiveController(_EmptyDoubanController):
    def build_request(self, vod_id: str):
        raise ValueError(f"没有可播放的项目: {vod_id}")

    def load_folder_items(self, vod_id: str):
        return [], 0


class _EmptyEmbyController(_EmptyDoubanController):
    def build_request(self, vod_id: str):
        raise ValueError(f"没有可播放的项目: {vod_id}")


class _EmptyJellyfinController(_EmptyDoubanController):
    def build_request(self, vod_id: str):
        raise ValueError(f"没有可播放的项目: {vod_id}")


class _EmptyFeiniuController(_EmptyDoubanController):
    def build_request(self, vod_id: str):
        raise ValueError(f"没有可播放的项目: {vod_id}")


def _plugin_value(definition: Any, key: str):
    if isinstance(definition, dict):
        return definition.get(key)
    return getattr(definition, key)


class _PluginController(Protocol):
    def load_categories(self): ...

    def load_items(self, category_id: str, page: int): ...

    def build_request(self, vod_id: str) -> OpenPlayerRequest: ...


class _AsyncRequestSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)


class _RestoreSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int)


class _SessionOpenSignals(QObject):
    succeeded = Signal(int, object, object, bool)
    failed = Signal(int, str, bool)


class _GlobalSearchSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)


@dataclass(slots=True)
class _MediaLoadResult:
    page: PosterGridPage
    items: list[Any]
    total: int
    empty_message: str
    push_breadcrumb: tuple[str, str] | None = None
    trim_breadcrumbs_to: int | None = None


@dataclass(slots=True)
class _TabDefinition:
    key: str
    title: str
    page: QWidget
    search_controller: Any | None = None
    global_search_only: bool = False


@dataclass(slots=True)
class _GlobalSearchResult:
    key: str
    title: str
    page: PosterGridPage
    items: list[Any]
    total: int


class MainWindow(QMainWindow, AsyncGuardMixin):
    logout_requested = Signal()
    _SEARCH_ICON_PATH = Path(__file__).resolve().parent.parent / "icons" / "search.svg"

    def __init__(
            self,
            browse_controller,
            history_controller,
            player_controller,
            config,
            save_config=None,
            douban_controller=None,
            telegram_controller=None,
            live_controller=None,
            live_source_manager=None,
            emby_controller=None,
            jellyfin_controller=None,
            feiniu_controller=None,
            pansou_controller=None,
            spider_plugins=None,
            plugin_manager=None,
            drive_detail_loader=None,
            show_emby_tab: bool = True,
            show_jellyfin_tab: bool = True,
            show_feiniu_tab: bool = True,
            m3u8_ad_filter=None,
            playback_parser_service=None,
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self._save_config = save_config or (lambda: None)
        self._m3u8_ad_filter = m3u8_ad_filter
        self._playback_parser_service = playback_parser_service
        self._plugin_definitions = list(spider_plugins or [])
        self._plugin_manager = plugin_manager
        self._drive_detail_loader = drive_detail_loader
        self._live_source_manager = live_source_manager
        self._plugin_pages: list[tuple[PosterGridPage, _PluginController, str]] = []
        self._static_tab_definitions: list[_TabDefinition] = []
        self._trailing_tab_definitions: list[_TabDefinition] = []
        self._plugin_tab_definitions: list[_TabDefinition] = []
        self.nav_tabs = QTabWidget()
        self.global_search_container = QWidget()
        self.global_search_edit = QLineEdit()
        self.global_search_button = QPushButton("搜索")
        self.global_search_clear_button = QPushButton("清空")
        self.global_search_status_label = QLabel("")
        self.plugin_manager_button = QPushButton("插件管理")
        self.live_source_manager_button = QPushButton("直播源管理")
        self.logout_button = QPushButton("退出登录")
        self.browse_page = BrowsePage(browse_controller, config=config, save_config=self._save_config)
        self.douban_page = PosterGridPage(douban_controller or _EmptyDoubanController())
        self.telegram_page = PosterGridPage(
            telegram_controller or _EmptyTelegramController(),
            click_action="open",
            search_enabled=True,
        )
        self.live_page = PosterGridPage(
            live_controller or _EmptyLiveController(),
            click_action="open",
            folder_navigation_enabled=True,
        )
        self.emby_page = None
        if show_emby_tab:
            self.emby_page = PosterGridPage(
                emby_controller or _EmptyEmbyController(),
                click_action="open",
                search_enabled=True,
                folder_navigation_enabled=True,
            )
        self.jellyfin_page = None
        if show_jellyfin_tab:
            self.jellyfin_page = PosterGridPage(
                jellyfin_controller or _EmptyJellyfinController(),
                click_action="open",
                search_enabled=True,
                folder_navigation_enabled=True,
            )
        self.feiniu_page = None
        if show_feiniu_tab:
            self.feiniu_page = PosterGridPage(
                feiniu_controller or _EmptyFeiniuController(),
                click_action="open",
                search_enabled=True,
                folder_navigation_enabled=True,
            )
        self.history_page = HistoryPage(history_controller)
        self.pansou_page = None
        if pansou_controller is not None:
            self.pansou_page = PosterGridPage(pansou_controller, click_action="open")
        self.browse_controller = browse_controller
        self.telegram_controller = telegram_controller or _EmptyTelegramController()
        self.live_controller = live_controller or _EmptyLiveController()
        self.emby_controller = emby_controller or _EmptyEmbyController()
        self.jellyfin_controller = jellyfin_controller or _EmptyJellyfinController()
        self.feiniu_controller = feiniu_controller or _EmptyFeiniuController()
        self.pansou_controller = pansou_controller
        self.player_controller = player_controller
        self.player_window: PlayerWindow | None = None
        self.help_dialog: ShortcutHelpDialog | None = None
        self.config = config
        self._open_request_id = 0
        self._media_request_id = 0
        self._restore_request_id = 0
        self._player_session_request_id = 0
        self._main_window_was_maximized_before_player = False
        self._open_request_signals = _AsyncRequestSignals()
        self._connect_async_signal(self._open_request_signals.succeeded, self._handle_open_request_succeeded)
        self._connect_async_signal(self._open_request_signals.failed, self._handle_open_request_failed)
        self._plugin_open_request_id = 0
        self._plugin_open_request_signals = _AsyncRequestSignals()
        self._connect_async_signal(
            self._plugin_open_request_signals.succeeded,
            self._handle_plugin_open_request_succeeded,
        )
        self._connect_async_signal(
            self._plugin_open_request_signals.failed,
            self._handle_plugin_open_request_failed,
        )
        self._pansou_resolve_request_id = 0
        self._pansou_resolve_request_signals = _AsyncRequestSignals()
        self._connect_async_signal(
            self._pansou_resolve_request_signals.succeeded,
            self._handle_pansou_resolve_succeeded,
        )
        self._connect_async_signal(
            self._pansou_resolve_request_signals.failed,
            self._handle_pansou_resolve_failed,
        )
        self._media_request_signals = _AsyncRequestSignals()
        self._connect_async_signal(self._media_request_signals.succeeded, self._handle_media_load_succeeded)
        self._connect_async_signal(self._media_request_signals.failed, self._handle_media_load_failed)
        self._restore_signals = _RestoreSignals()
        self._connect_async_signal(self._restore_signals.succeeded, self._handle_restore_succeeded)
        self._connect_async_signal(self._restore_signals.failed, self._handle_restore_failed)
        self._session_open_signals = _SessionOpenSignals()
        self._connect_async_signal(self._session_open_signals.succeeded, self._handle_session_open_succeeded)
        self._connect_async_signal(self._session_open_signals.failed, self._handle_session_open_failed)
        self._global_search_signals = _GlobalSearchSignals()
        self._connect_async_signal(self._global_search_signals.succeeded, self._handle_global_search_succeeded)
        self._connect_async_signal(self._global_search_signals.failed, self._handle_global_search_failed)
        self._global_search_request_id = 0
        self._global_search_pending_keys: set[str] = set()
        self._global_search_results: dict[str, _GlobalSearchResult] = {}
        self._global_search_active = False
        self._global_search_in_progress = False
        self._global_search_keyword = ""

        self.global_search_container.setFixedWidth(400)
        self.global_search_edit.setPlaceholderText("搜索")
        self.global_search_edit.setClearButtonEnabled(True)
        self.global_search_edit.setStyleSheet(
            """
            QLineEdit {
                min-height: 36px;
                padding: 0 12px;
                border: 1px solid #d0d7de;
                border-radius: 18px;
                background: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #409eff;
            }
            """
        )
        self.global_search_button.setText("")
        self.global_search_button.setIcon(load_icon(self._SEARCH_ICON_PATH))
        self.global_search_button.setFixedSize(36, 36)
        self.global_search_button.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #d0d7de;
                border-radius: 18px;
                background: #ffffff;
                padding: 0;
            }
            QPushButton:hover {
                background: #f3f4f6;
            }
            """
        )
        self.global_search_status_label.setWordWrap(True)
        self.global_search_clear_button.setEnabled(False)
        self.global_search_clear_button.hide()

        self._static_tab_definitions = [
            _TabDefinition("douban", "豆瓣电影", self.douban_page),
            _TabDefinition("telegram", "电报影视", self.telegram_page, self.telegram_controller),
            _TabDefinition("live", "网络直播", self.live_page),
        ]
        if self.emby_page is not None:
            self._static_tab_definitions.append(_TabDefinition("emby", "Emby", self.emby_page, self.emby_controller))
        if self.jellyfin_page is not None:
            self._static_tab_definitions.append(
                _TabDefinition("jellyfin", "Jellyfin", self.jellyfin_page, self.jellyfin_controller)
            )
        if self.feiniu_page is not None:
            self._static_tab_definitions.append(
                _TabDefinition("feiniu", "飞牛影视", self.feiniu_page, self.feiniu_controller)
            )
        if self.pansou_page is not None and self.pansou_controller is not None:
            self._static_tab_definitions.append(
                _TabDefinition(
                    "pansou",
                    "盘搜",
                    self.pansou_page,
                    self.pansou_controller,
                    global_search_only=True,
                )
            )
        self._trailing_tab_definitions = [
            _TabDefinition("browse", "文件浏览", self.browse_page),
            _TabDefinition("history", "播放记录", self.history_page),
        ]
        self._rebuild_spider_plugin_tabs()
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.plugin_manager_button.clicked.connect(self._open_plugin_manager)
        self.live_source_manager_button.clicked.connect(self._open_live_source_manager)
        self.global_search_button.clicked.connect(self._start_global_search)
        self.global_search_clear_button.clicked.connect(self._clear_global_search)
        self.global_search_edit.returnPressed.connect(self._start_global_search)
        self.global_search_edit.textChanged.connect(self._handle_global_search_text_changed)
        search_layout = QHBoxLayout(self.global_search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.global_search_edit, 1)
        search_layout.addWidget(self.global_search_button)
        self.header_layout = QHBoxLayout()
        self.header_layout.addStretch(1)
        self.header_layout.addWidget(self.global_search_container)
        self.header_layout.addStretch(1)
        self.header_layout.addWidget(self.plugin_manager_button)
        self.header_layout.addWidget(self.live_source_manager_button)
        self.header_layout.addWidget(self.logout_button)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(self.header_layout)
        container_layout.addWidget(self.global_search_status_label)
        container_layout.addWidget(self.nav_tabs)
        self.setCentralWidget(container)
        self.setWindowTitle("alist-tvbox Desktop Player")
        if self.config.main_window_geometry:
            self.restoreGeometry(to_qbytearray(self.config.main_window_geometry))

        self.nav_tabs.currentChanged.connect(self._handle_tab_changed)
        self.browse_page.open_requested.connect(self.open_player)
        self.history_page.open_detail_requested.connect(self.open_history_detail)
        self.douban_page.search_requested.connect(self._handle_douban_search_requested)
        self.telegram_page.open_requested.connect(self._handle_telegram_open_requested)
        self.live_page.item_open_requested.connect(self._handle_live_item_open_requested)
        self.live_page.folder_breadcrumb_requested.connect(
            lambda node_id, kind, index: self._handle_media_breadcrumb_requested(
                self.live_page,
                self.live_controller,
                node_id,
                kind,
                index,
            )
        )
        if self.emby_page is not None:
            emby_page = self.emby_page
            emby_page.item_open_requested.connect(self._handle_emby_item_open_requested)
            emby_page.folder_breadcrumb_requested.connect(
                lambda node_id, kind, index, page=emby_page: self._handle_media_breadcrumb_requested(
                    page,
                    self.emby_controller,
                    node_id,
                    kind,
                    index,
                )
            )
        if self.jellyfin_page is not None:
            jellyfin_page = self.jellyfin_page
            jellyfin_page.item_open_requested.connect(self._handle_jellyfin_item_open_requested)
            jellyfin_page.folder_breadcrumb_requested.connect(
                lambda node_id, kind, index, page=jellyfin_page: self._handle_media_breadcrumb_requested(
                    page,
                    self.jellyfin_controller,
                    node_id,
                    kind,
                    index,
                )
            )
        if self.feiniu_page is not None:
            feiniu_page = self.feiniu_page
            feiniu_page.item_open_requested.connect(self._handle_feiniu_item_open_requested)
            feiniu_page.folder_breadcrumb_requested.connect(
                lambda node_id, kind, index, page=feiniu_page: self._handle_media_breadcrumb_requested(
                    page,
                    self.feiniu_controller,
                    node_id,
                    kind,
                    index,
                )
            )
        if self.pansou_page is not None:
            self.pansou_page.item_open_requested.connect(self._handle_pansou_item_open_requested)

        self.douban_page.unauthorized.connect(self.logout_requested.emit)
        self.telegram_page.unauthorized.connect(self.logout_requested.emit)
        self.live_page.unauthorized.connect(self.logout_requested.emit)
        if self.emby_page is not None:
            self.emby_page.unauthorized.connect(self.logout_requested.emit)
        if self.jellyfin_page is not None:
            self.jellyfin_page.unauthorized.connect(self.logout_requested.emit)
        if self.feiniu_page is not None:
            self.feiniu_page.unauthorized.connect(self.logout_requested.emit)
        if self.pansou_page is not None:
            self.pansou_page.unauthorized.connect(self.logout_requested.emit)
        self.browse_page.unauthorized.connect(self.logout_requested.emit)
        self.history_page.unauthorized.connect(self.logout_requested.emit)
        self.quit_shortcut = QShortcut(QKeySequence.StandardKey.Quit, self)
        self.quit_shortcut.activated.connect(self._quit_application)
        self.player_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        self.player_shortcut.activated.connect(self.show_or_restore_player)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.show_or_restore_player)
        self.help_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        self.help_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.help_shortcut.activated.connect(self._show_shortcut_help)

        self._refresh_visible_tabs()
        self._sync_global_search_action_state()
        self._handle_tab_changed(self.nav_tabs.currentIndex())

    def show_browse_path(self, path: str) -> None:
        self.browse_page.load_path(path)
        self.nav_tabs.setCurrentWidget(self.browse_page)

    def _all_tab_definitions(self) -> list[_TabDefinition]:
        return [*self._static_tab_definitions, *self._plugin_tab_definitions, *self._trailing_tab_definitions]

    def _visible_tab_definitions(self) -> list[_TabDefinition]:
        if not self._global_search_active:
            return [
                definition
                for definition in self._all_tab_definitions()
                if not definition.global_search_only
            ]
        return [definition for definition in self._all_tab_definitions() if definition.key in self._global_search_results]

    def _global_search_title_overrides(self) -> dict[str, str]:
        return {
            key: f"{result.title}({result.total})"
            for key, result in self._global_search_results.items()
        }

    def _refresh_visible_tabs(self) -> None:
        current_widget = self.nav_tabs.currentWidget()
        definitions = self._visible_tab_definitions()
        title_overrides = self._global_search_title_overrides() if self._global_search_active else {}

        self.nav_tabs.blockSignals(True)
        self.nav_tabs.clear()
        for definition in definitions:
            self.nav_tabs.addTab(definition.page, title_overrides.get(definition.key, definition.title))
        self.nav_tabs.blockSignals(False)

        if current_widget is not None:
            current_index = self.nav_tabs.indexOf(current_widget)
            if current_index >= 0:
                self.nav_tabs.setCurrentIndex(current_index)
                return
        if self.nav_tabs.count() > 0:
            self.nav_tabs.setCurrentIndex(0)

    def _sync_global_search_action_state(self) -> None:
        has_keyword = bool(self.global_search_edit.text().strip())
        self.global_search_button.setEnabled(has_keyword)
        self.global_search_clear_button.setEnabled(self._global_search_active or has_keyword)

    def _handle_global_search_text_changed(self) -> None:
        if not self.global_search_edit.text().strip() and self._global_search_active:
            self._clear_global_search()
            return
        self._sync_global_search_action_state()

    def _handle_tab_changed(self, index: int) -> None:
        widget = self.nav_tabs.widget(index)
        if widget is None:
            return
        if self._global_search_active:
            return
        if widget is self.douban_page:
            self.douban_page.ensure_loaded()
            return
        if widget is self.telegram_page:
            self.telegram_page.ensure_loaded()
            return
        if widget is self.live_page:
            self.live_page.ensure_loaded()
            return
        if widget is self.emby_page and self.emby_page is not None:
            self.emby_page.ensure_loaded()
            return
        if widget is self.jellyfin_page and self.jellyfin_page is not None:
            self.jellyfin_page.ensure_loaded()
            return
        if widget is self.feiniu_page and self.feiniu_page is not None:
            self.feiniu_page.ensure_loaded()
            return
        for page, _controller, _plugin_id in self._plugin_pages:
            if widget is page:
                page.ensure_loaded()
                return
        if widget is self.browse_page:
            if hasattr(self.browse_controller, "load_folder"):
                self.browse_page.ensure_loaded(self.config.last_path or "/")
            return
        if widget is self.history_page:
            if hasattr(self.history_page.controller, "load_page"):
                self.history_page.ensure_loaded()

    def _handle_douban_search_requested(self, keyword: str) -> None:
        self.global_search_edit.setText(keyword)
        self._start_global_search()

    def _handle_telegram_item_open_requested(self, item) -> None:
        vod_id = item.vod_id
        self._start_open_request(lambda: self.telegram_controller.build_request(vod_id))

    def _handle_telegram_open_requested(self, vod_id: str) -> None:
        self._start_open_request(lambda: self.telegram_controller.build_request(vod_id))

    def _handle_live_item_open_requested(self, item) -> None:
        if getattr(item, "vod_tag", "") == "folder":
            self._open_media_folder(self.live_page, self.live_controller, item)
            return
        vod_id = item.vod_id
        self._start_open_request(lambda: self.live_controller.build_request(vod_id))

    def _handle_emby_item_open_requested(self, item) -> None:
        if getattr(item, "vod_tag", "") == "folder":
            if self.emby_page is not None:
                self._open_media_folder(self.emby_page, self.emby_controller, item)
            return
        vod_id = item.vod_id
        self._start_open_request(lambda: self.emby_controller.build_request(vod_id))

    def _handle_jellyfin_item_open_requested(self, item) -> None:
        if getattr(item, "vod_tag", "") == "folder":
            if self.jellyfin_page is not None:
                self._open_media_folder(self.jellyfin_page, self.jellyfin_controller, item)
            return
        vod_id = item.vod_id
        self._start_open_request(lambda: self.jellyfin_controller.build_request(vod_id))

    def _handle_feiniu_item_open_requested(self, item) -> None:
        if getattr(item, "vod_tag", "") == "folder":
            if self.feiniu_page is not None:
                self._open_media_folder(self.feiniu_page, self.feiniu_controller, item)
            return
        vod_id = item.vod_id
        self._start_open_request(lambda: self.feiniu_controller.build_request(vod_id))

    def _handle_pansou_item_open_requested(self, item) -> None:
        if self.pansou_controller is None:
            return
        self._pansou_resolve_request_id += 1
        request_id = self._pansou_resolve_request_id
        self.global_search_status_label.setText("打开中...")

        def run() -> None:
            try:
                path = self.pansou_controller.resolve_search_result(item)
            except Exception as exc:
                if self._is_window_alive():
                    self._pansou_resolve_request_signals.failed.emit(request_id, str(exc))
                return
            if self._is_window_alive():
                self._pansou_resolve_request_signals.succeeded.emit(request_id, path)

        threading.Thread(target=run, daemon=True).start()

    def _searchable_tab_definitions(self) -> list[_TabDefinition]:
        return [definition for definition in self._all_tab_definitions() if definition.search_controller is not None]

    def _start_global_search(self) -> None:
        keyword = self.global_search_edit.text().strip()
        if not keyword:
            return
        searchable = self._searchable_tab_definitions()
        if not searchable:
            self.global_search_status_label.setText("无可搜索来源")
            return
        self._global_search_request_id += 1
        request_id = self._global_search_request_id
        self._global_search_active = True
        self._global_search_in_progress = True
        self._global_search_keyword = keyword
        self._global_search_results = {}
        self._global_search_pending_keys = {definition.key for definition in searchable}
        self.global_search_status_label.setText("搜索中...")
        self._refresh_visible_tabs()
        self._sync_global_search_action_state()
        for definition in searchable:
            threading.Thread(
                target=self._run_global_search,
                args=(request_id, definition, keyword),
                daemon=True,
            ).start()

    def _run_global_search(self, request_id: int, definition: _TabDefinition, keyword: str) -> None:
        controller = definition.search_controller
        if controller is None:
            if self._is_window_alive():
                self._global_search_signals.failed.emit(request_id, definition.key)
            return
        try:
            items, total = controller.search_items(keyword, 1)
        except Exception:
            if self._is_window_alive():
                self._global_search_signals.failed.emit(request_id, definition.key)
            return
        if self._is_window_alive():
            self._global_search_signals.succeeded.emit(
                request_id,
                _GlobalSearchResult(
                    key=definition.key,
                    title=definition.title,
                    page=cast(PosterGridPage, definition.page),
                    items=list(items),
                    total=total,
                ),
            )

    def _handle_global_search_succeeded(self, request_id: int, result: _GlobalSearchResult) -> None:
        if request_id != self._global_search_request_id:
            return
        if result.items:
            result.page.show_external_results(result.items, result.total, page=1, empty_message="无搜索结果")
            self._global_search_results[result.key] = result
            self._refresh_visible_tabs()
        else:
            self._global_search_results.pop(result.key, None)
        self._finish_global_search_result(result.key)

    def _handle_global_search_failed(self, request_id: int, key: str) -> None:
        if request_id != self._global_search_request_id:
            return
        self._global_search_results.pop(key, None)
        self._refresh_visible_tabs()
        self._finish_global_search_result(key)

    def _finish_global_search_result(self, key: str) -> None:
        self._global_search_pending_keys.discard(key)
        if self._global_search_pending_keys:
            return
        self._global_search_in_progress = False
        if self.nav_tabs.count() > 0:
            self.global_search_status_label.setText("")
        else:
            self.global_search_status_label.setText("无搜索结果")
        self._sync_global_search_action_state()

    def _clear_global_search(self) -> None:
        if not self._global_search_active and not self.global_search_edit.text().strip():
            return
        if self._global_search_active:
            self._global_search_request_id += 1
        self._global_search_active = False
        self._global_search_in_progress = False
        self._global_search_keyword = ""
        self._global_search_results = {}
        self._global_search_pending_keys = set()
        self.global_search_edit.blockSignals(True)
        self.global_search_edit.clear()
        self.global_search_edit.blockSignals(False)
        self.global_search_status_label.setText("")
        for definition in self._all_tab_definitions():
            if isinstance(definition.page, PosterGridPage):
                definition.page.clear_external_results()
        self._refresh_visible_tabs()
        self._sync_global_search_action_state()

    def _rebuild_spider_plugin_tabs(self) -> None:
        for page, _controller, _plugin_id in self._plugin_pages:
            page.deleteLater()
        self._plugin_pages = []
        self._plugin_tab_definitions = []
        for definition in self._plugin_definitions:
            controller = cast(_PluginController, _plugin_value(definition, "controller"))
            plugin_id = str(_plugin_value(definition, "id") or "")
            title = str(_plugin_value(definition, "title") or "插件")
            page = PosterGridPage(
                controller,
                click_action="open",
                search_enabled=bool(_plugin_value(definition, "search_enabled")),
            )
            page.item_open_requested.connect(
                lambda item, controller=controller, plugin_id=plugin_id: self._open_spider_item(
                    controller,
                    plugin_id,
                    item,
                )
            )
            page.unauthorized.connect(self.logout_requested.emit)
            self._plugin_pages.append((page, controller, plugin_id))
            self._plugin_tab_definitions.append(
                _TabDefinition(f"plugin:{plugin_id}", title, page, controller)
            )
        self._refresh_visible_tabs()

    def _build_placeholder_player_request(
        self, item: Any, *, source_kind: str = "plugin", source_key: str = "",
    ) -> OpenPlayerRequest:
        placeholder_vod = VodItem(
            vod_id=getattr(item, "vod_id", ""),
            vod_name=getattr(item, "vod_name", ""),
            vod_pic=getattr(item, "vod_pic", ""),
            vod_remarks=getattr(item, "vod_remarks", ""),
            type_name=getattr(item, "type_name", ""),
            vod_content=getattr(item, "vod_content", ""),
            vod_year=getattr(item, "vod_year", ""),
            vod_area=getattr(item, "vod_area", ""),
            vod_lang=getattr(item, "vod_lang", ""),
            vod_director=getattr(item, "vod_director", ""),
            vod_actor=getattr(item, "vod_actor", ""),
        )
        return OpenPlayerRequest(
            vod=placeholder_vod,
            playlist=[],
            clicked_index=0,
            source_kind=source_kind,
            source_key=source_key,
            source_mode="detail",
            source_vod_id=placeholder_vod.vod_id,
            use_local_history=False,
            initial_log_message="正在加载详情...",
            is_placeholder=True,
        )

    def _open_spider_item(self, controller, plugin_id: str, item: Any) -> None:
        placeholder_request = self._build_placeholder_player_request(item, source_kind="plugin", source_key=plugin_id)
        self._open_player_immediately(placeholder_request)

        def build_request() -> OpenPlayerRequest:
            request = controller.build_request(getattr(item, "vod_id", ""))
            request.source_kind = "plugin"
            request.source_key = plugin_id
            return request

        self._start_plugin_open_request(build_request)

    def _open_plugin_manager(self) -> None:
        if self._plugin_manager is None:
            return
        self._close_help_dialog()
        dialog = PluginManagerDialog(self._plugin_manager, self)
        dialog.exec()
        load_enabled_plugins = getattr(self._plugin_manager, "load_enabled_plugins", None)
        if callable(load_enabled_plugins):
            try:
                loaded_plugins = load_enabled_plugins(drive_detail_loader=self._drive_detail_loader)
            except TypeError as exc:
                if "drive_detail_loader" not in str(exc):
                    raise
                loaded_plugins = load_enabled_plugins()
            if isinstance(loaded_plugins, Iterable):
                self._plugin_definitions = list(loaded_plugins)
            else:
                self._plugin_definitions = []
            self._rebuild_spider_plugin_tabs()

    def _open_live_source_manager(self) -> None:
        if self._live_source_manager is None:
            return
        self._close_help_dialog()
        dialog = LiveSourceManagerDialog(self._live_source_manager, self)
        dialog.exec()
        self.live_page.reload_categories()

    def _open_media_folder(self, page: PosterGridPage, controller: Any, item: Any) -> None:
        self._start_media_load(
            page,
            lambda: controller.load_folder_items(item.vod_id),
            empty_message="当前文件夹暂无内容",
            push_breadcrumb=(item.vod_id, item.vod_name),
        )

    def _handle_media_breadcrumb_requested(
        self,
        page: PosterGridPage,
        controller: Any,
        node_id: str,
        kind: str,
        index: int,
    ) -> None:
        if kind == "folder":
            self._start_media_load(
                page,
                lambda: controller.load_folder_items(node_id),
                empty_message="当前文件夹暂无内容",
                trim_breadcrumbs_to=index,
            )
            return
        category_id = page.selected_category_id
        if not category_id:
            return
        self._start_media_load(
            page,
            lambda: controller.load_items(category_id, 1),
            empty_message="当前分类暂无内容",
            trim_breadcrumbs_to=1,
        )

    def _find_plugin_controller(self, plugin_id: int):
        for definition in self._plugin_definitions:
            if _plugin_value(definition, "id") == plugin_id:
                return _plugin_value(definition, "controller")
        return None

    def open_history_detail(self, record: HistoryRecord) -> None:
        if record.source_kind == "spider_plugin":
            plugin_id = record.source_key or str(record.source_plugin_id or "")
            controller = self._plugin_controller_by_id(plugin_id)
            if controller is None:
                self.show_error(f"没有可播放的项目: {record.source_name or record.source_plugin_name or record.key}")
                return
            def build_request():
                request = controller.build_request(record.key)
                request.source_kind = "plugin"
                request.source_key = plugin_id
                if request.playback_history_loader is None:
                    request.playlist_index = record.playlist_index
                    request.clicked_index = record.episode
                return request

            self._start_open_request(build_request)
            return
        if record.source_kind == "emby":
            self._start_open_request(lambda: self.emby_controller.build_request(record.key))
            return
        if record.source_kind == "jellyfin":
            self._start_open_request(lambda: self.jellyfin_controller.build_request(record.key))
            return
        if record.source_kind == "feiniu":
            self._start_open_request(lambda: self.feiniu_controller.build_request(record.key))
            return
        self._start_open_request(lambda: self.browse_controller.build_request_from_detail(record.key))

    def _start_open_request(self, builder) -> int:
        self._open_request_id += 1
        request_id = self._open_request_id

        def run() -> None:
            try:
                request = builder()
            except Exception as exc:
                if self._is_window_alive():
                    self._open_request_signals.failed.emit(request_id, str(exc))
                return
            if self._is_window_alive():
                self._open_request_signals.succeeded.emit(request_id, request)

        threading.Thread(target=run, daemon=True).start()
        return request_id

    def _start_plugin_open_request(self, builder) -> int:
        self._plugin_open_request_id += 1
        request_id = self._plugin_open_request_id

        def run() -> None:
            try:
                request = builder()
            except Exception as exc:
                if self._is_window_alive():
                    self._plugin_open_request_signals.failed.emit(request_id, str(exc))
                return
            if self._is_window_alive():
                self._plugin_open_request_signals.succeeded.emit(request_id, request)

        threading.Thread(target=run, daemon=True).start()
        return request_id

    def _handle_open_request_succeeded(self, request_id: int, request: OpenPlayerRequest) -> None:
        if request_id != self._open_request_id:
            return
        self.open_player(request)

    def _handle_open_request_failed(self, request_id: int, message: str) -> None:
        if request_id != self._open_request_id:
            return
        if self.player_window is not None and getattr(self.player_window, "session", None) is not None:
            self._append_player_status_log(f"详情加载失败: {message}")
            return
        self.show_error(message)

    def _handle_plugin_open_request_succeeded(self, request_id: int, request: OpenPlayerRequest) -> None:
        if request_id != self._plugin_open_request_id:
            return
        self.open_player(request)

    def _handle_plugin_open_request_failed(self, request_id: int, message: str) -> None:
        if request_id != self._plugin_open_request_id:
            return
        self._append_player_status_log(f"详情加载失败: {message}")

    def _handle_pansou_resolve_succeeded(self, request_id: int, path: str) -> None:
        if request_id != self._pansou_resolve_request_id:
            return
        self._clear_global_search()
        self.show_browse_path(path)

    def _handle_pansou_resolve_failed(self, request_id: int, message: str) -> None:
        if request_id != self._pansou_resolve_request_id:
            return
        self.global_search_status_label.setText("")
        self.show_error(message)

    def _start_media_load(
        self,
        page: PosterGridPage,
        loader,
        *,
        empty_message: str,
        push_breadcrumb: tuple[str, str] | None = None,
        trim_breadcrumbs_to: int | None = None,
    ) -> int:
        self._media_request_id += 1
        request_id = self._media_request_id

        def run() -> None:
            try:
                items, total = loader()
            except Exception as exc:
                if self._is_window_alive():
                    self._media_request_signals.failed.emit(request_id, str(exc))
                return
            if self._is_window_alive():
                self._media_request_signals.succeeded.emit(
                    request_id,
                    _MediaLoadResult(
                        page=page,
                        items=list(items),
                        total=total,
                        empty_message=empty_message,
                        push_breadcrumb=push_breadcrumb,
                        trim_breadcrumbs_to=trim_breadcrumbs_to,
                    ),
                )

        threading.Thread(target=run, daemon=True).start()
        return request_id

    def _handle_media_load_succeeded(self, request_id: int, result: _MediaLoadResult) -> None:
        if request_id != self._media_request_id:
            return
        result.page.show_items(result.items, result.total, page=1, empty_message=result.empty_message)
        if result.push_breadcrumb is not None:
            breadcrumb_id, label = result.push_breadcrumb
            result.page.push_folder_breadcrumb(breadcrumb_id, label)
        if result.trim_breadcrumbs_to is not None:
            result.page.trim_folder_breadcrumbs(result.trim_breadcrumbs_to)

    def _handle_media_load_failed(self, request_id: int, message: str) -> None:
        if request_id != self._media_request_id:
            return
        self.show_error(message)

    def _is_window_alive(self) -> bool:
        return self._can_deliver_async_result()

    def _next_player_session_request_id(self) -> int:
        self._player_session_request_id += 1
        return self._player_session_request_id

    def _create_player_session(self, request):
        return self.player_controller.create_session(
            request.vod,
            request.playlist,
            request.clicked_index,
            playlists=request.playlists,
            playlist_index=request.playlist_index,
            detail_resolver=request.detail_resolver,
            resolved_vod_by_id=request.resolved_vod_by_id,
            use_local_history=request.use_local_history,
            restore_history=request.restore_history,
            playback_loader=request.playback_loader,
            async_playback_loader=request.async_playback_loader,
            danmaku_controller=request.danmaku_controller,
            playback_progress_reporter=request.playback_progress_reporter,
            playback_stopper=request.playback_stopper,
            playback_history_loader=request.playback_history_loader,
            playback_history_saver=request.playback_history_saver,
            initial_log_message=request.initial_log_message,
            is_placeholder=request.is_placeholder,
        )

    def _append_player_status_log(self, message: str) -> None:
        if not message:
            return
        if self.player_window is None:
            return
        append_status_log = getattr(self.player_window, "append_status_log", None)
        if callable(append_status_log):
            append_status_log(message)

    def _open_player_immediately(self, request, restore_paused_state: bool = False) -> None:
        try:
            session = self._create_player_session(request)
        except Exception as exc:
            self.show_error(str(exc))
            return
        self._next_player_session_request_id()
        self._apply_open_player(request, session, restore_paused_state=restore_paused_state)

    def _apply_open_player(self, request, session, restore_paused_state: bool = False) -> None:
        if self.player_window is None:
            try:
                self.player_window = PlayerWindow(
                    self.player_controller,
                    self.config,
                    self._save_config,
                    m3u8_ad_filter=self._m3u8_ad_filter,
                    playback_parser_service=self._playback_parser_service,
                )
            except TypeError as exc:
                if "m3u8_ad_filter" not in str(exc) and "playback_parser_service" not in str(exc):
                    raise
                self.player_window = PlayerWindow(
                    self.player_controller,
                    self.config,
                    self._save_config,
                )
            if hasattr(self.player_window, "closed_to_main"):
                self.player_window.closed_to_main.connect(self._show_main_again)
        self._close_help_dialog()
        self.config.last_active_window = "player"
        self.config.last_playback_source = request.source_kind
        self.config.last_playback_source_key = request.source_key
        self.config.last_playback_mode = request.source_mode
        self.config.last_playback_path = request.source_path
        self.config.last_playback_vod_id = request.source_vod_id
        self.config.last_playback_clicked_vod_id = request.source_clicked_vod_id
        start_paused = self.config.last_player_paused if restore_paused_state else False
        if not restore_paused_state:
            self.config.last_player_paused = False
        self._remember_main_window_state_for_player()
        self.config.main_window_geometry = qbytearray_to_bytes(self.saveGeometry())
        self._save_config()
        self.player_window.open_session(session, start_paused=start_paused)
        self.player_window.show()
        self.player_window.raise_()
        self.player_window.activateWindow()
        self.hide()

    def open_player(self, request, restore_paused_state: bool = False) -> None:
        request_id = self._next_player_session_request_id()

        def run() -> None:
            try:
                session = self._create_player_session(request)
            except Exception as exc:
                if self._is_window_alive():
                    self._session_open_signals.failed.emit(request_id, str(exc), restore_paused_state)
                return
            if not self._is_window_alive():
                return
            self._session_open_signals.succeeded.emit(request_id, request, session, restore_paused_state)

        threading.Thread(target=run, daemon=True).start()

    def _handle_session_open_succeeded(self, request_id: int, request, session, restore_paused_state: bool) -> None:
        if request_id != self._player_session_request_id:
            return
        self._apply_open_player(request, session, restore_paused_state=restore_paused_state)

    def _handle_session_open_failed(self, request_id: int, message: str, restore_paused_state: bool) -> None:
        if request_id != self._player_session_request_id:
            return
        if restore_paused_state:
            self.config.last_active_window = "main"
            self._save_config()
        self.show_error(message)

    def _show_main_again(self) -> None:
        if self.player_window is not None and getattr(self.player_window, "session", None) is None:
            self.player_window = None
        self.config.last_active_window = "main"
        self._save_config()
        self._restore_main_window_after_player()
        self.raise_()
        self.activateWindow()

    def _remember_main_window_state_for_player(self) -> None:
        self._main_window_was_maximized_before_player = self.isMaximized()

    def _restore_main_window_after_player(self) -> None:
        self._restore_saved_geometry()
        self.show()
        if self._main_window_was_maximized_before_player:
            self.showMaximized()
        self._refresh_main_window_layout()
        QTimer.singleShot(0, self._refresh_main_window_layout)

    def _restore_saved_geometry(self) -> None:
        geometry = self.config.main_window_geometry
        if not geometry:
            return
        self.restoreGeometry(to_qbytearray(geometry))

    def _refresh_main_window_layout(self) -> None:
        central_widget = self.centralWidget()
        if central_widget is None:
            return
        central_widget.updateGeometry()
        layout = central_widget.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()

    def show_or_restore_player(self) -> PlayerWindow | None:
        if self.player_window is not None and getattr(self.player_window, "session", None) is not None:
            self._close_help_dialog()
            self.config.last_active_window = "player"
            self._save_config()
            if hasattr(self.player_window, "resume_from_main"):
                self.player_window.resume_from_main()
            self.player_window.show()
            self.player_window.raise_()
            self.player_window.activateWindow()
            self.hide()
            return self.player_window
        self._start_restore_last_player()
        return None

    def restore_last_player(self) -> PlayerWindow | None:
        try:
            request = self._build_restore_request()
        except Exception:
            return None
        if request is None:
            return None
        self._next_player_session_request_id()
        session = self._create_player_session(request)
        self._apply_open_player(request, session, restore_paused_state=True)
        return self.player_window

    def _build_restore_request(self) -> OpenPlayerRequest | None:
        mode = self.config.last_playback_mode
        source = self.config.last_playback_source or "browse"
        if mode in {"detail", "custom"} and self.config.last_playback_vod_id:
            return self._build_detail_restore_request(source, self.config.last_playback_vod_id)
        if mode == "folder" and self.config.last_playback_path and self.config.last_playback_clicked_vod_id:
            clicked, items = self._find_restorable_folder_item(
                self.config.last_playback_path,
                self.config.last_playback_clicked_vod_id,
            )
            if clicked is None:
                return None
            return self.browse_controller.build_request_from_folder_item(clicked, items)
        return None

    def _start_restore_last_player(self) -> int:
        self._restore_request_id += 1
        request_id = self._restore_request_id

        def run() -> None:
            try:
                request = self._build_restore_request()
            except Exception:
                if self._is_window_alive():
                    self._restore_signals.failed.emit(request_id)
                return
            if self._is_window_alive():
                self._restore_signals.succeeded.emit(request_id, request)

        threading.Thread(target=run, daemon=True).start()
        return request_id

    def _handle_restore_succeeded(self, request_id: int, request: OpenPlayerRequest | None) -> None:
        if request_id != self._restore_request_id:
            return None
        if request is None:
            self.config.last_active_window = "main"
            self._save_config()
            return
        self.open_player(request, restore_paused_state=True)

    def _handle_restore_failed(self, request_id: int) -> None:
        if request_id != self._restore_request_id:
            return
        self.config.last_active_window = "main"
        self._save_config()

    def _build_detail_restore_request(self, source: str, vod_id: str):
        if source == "telegram":
            return self.telegram_controller.build_request(vod_id)
        if source == "live":
            return self.live_controller.build_request(vod_id)
        if source == "emby":
            return self.emby_controller.build_request(vod_id)
        if source == "jellyfin":
            return self.jellyfin_controller.build_request(vod_id)
        if source == "plugin":
            controller = self._plugin_controller_by_id(self.config.last_playback_source_key)
            if controller is None:
                raise ValueError("找不到已保存的插件来源")
            request = controller.build_request(vod_id)
            request.source_kind = "plugin"
            request.source_key = self.config.last_playback_source_key
            return request
        return self.browse_controller.build_request_from_detail(vod_id)

    def _plugin_controller_by_id(self, plugin_id: str) -> _PluginController | None:
        for _page, controller, current_plugin_id in self._plugin_pages:
            if current_plugin_id == plugin_id:
                return controller
        return None

    def _find_restorable_folder_item(
        self,
        path: str,
        clicked_vod_id: str,
        page_size: int = 50,
    ) -> tuple[Any | None, list[Any]]:
        page = 1
        total_pages = 1
        while page <= total_pages:
            items, total = self.browse_controller.load_folder(path, page=page, size=page_size)
            clicked = next((item for item in items if item.vod_id == clicked_vod_id), None)
            if clicked is not None:
                return clicked, items
            total_pages = max(1, (total + page_size - 1) // page_size)
            page += 1
        return None, []

    def show_error(self, message: str) -> None:
        QMessageBox.critical(self, "错误", message)

    def _show_shortcut_help(self) -> None:
        dialog = show_shortcut_help_dialog(
            self,
            context="main_window",
            existing_dialog=self.help_dialog,
            quit_sequence=self.quit_shortcut.key(),
        )
        if dialog is self.help_dialog:
            return
        self.help_dialog = dialog
        dialog.destroyed.connect(self._clear_help_dialog_reference)

    def _clear_help_dialog_reference(self, *_args) -> None:
        self.help_dialog = None

    def _close_help_dialog(self) -> None:
        dialog = self.help_dialog
        if dialog is None:
            return
        self.help_dialog = None
        dialog.close()

    def _quit_application(self) -> None:
        self.config.last_active_window = "main"
        self.config.main_window_geometry = qbytearray_to_bytes(self.saveGeometry())
        self._save_config()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F1:
            self._show_shortcut_help()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._deactivate_async_guard()
        self.config.main_window_geometry = qbytearray_to_bytes(self.saveGeometry())
        if self.isVisible():
            self.config.last_active_window = "main"
        self._save_config()
        super().closeEvent(event)
