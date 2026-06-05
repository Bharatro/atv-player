from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import DoubanCategory
from atv_player.ui.poster_grid_page import PosterGridPage
from atv_player.ui.theme import build_navigation_tabbar_qss, build_pill_button_qss, current_tokens


@dataclass(slots=True)
class SourceEntry:
    key: str
    title: str
    controller: object | None
    search_enabled: bool = True
    source_kind: str = "plugin"


class ClassicSourcePopup(QWidget):
    source_selected = Signal(str)
    COLUMN_COUNT = 4
    _SOURCE_KIND_LABELS = {
        "builtin": "内置源",
        "plugin": "插件源",
    }
    _SOURCE_KIND_ORDER = ("builtin", "plugin")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("classicSourcePopup")
        self._entries: list[SourceEntry] = []
        self._current_key = ""
        self.source_buttons: dict[str, QPushButton] = {}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._container = QFrame(self)
        self._container.setObjectName("classicSourcePopupContainer")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(16, 14, 16, 16)
        self._container_layout.setSpacing(12)

        title = QLabel("选择源", self._container)
        title.setObjectName("classicSourcePopupTitle")
        self._container_layout.addWidget(title)

        self._grid_widget = QWidget(self._container)
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setHorizontalSpacing(10)
        self._grid_layout.setVerticalSpacing(10)
        self._container_layout.addWidget(self._grid_widget)
        self._layout.addWidget(self._container)
        self._apply_theme()

    def set_sources(self, entries: list[SourceEntry], current_key: str) -> None:
        self._entries = list(entries)
        self._current_key = current_key
        self._render_sources()

    def source_button(self, key: str) -> QPushButton:
        return self.source_buttons[key]

    def show_at(self, global_pos, width: int) -> None:
        popup_width = max(width, self._preferred_popup_width())
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            popup_width = min(popup_width, max(360, available.width() - 32))
            x = global_pos.x()
            if x + popup_width > available.right():
                x = max(available.left(), available.right() - popup_width)
            global_pos.setX(x)
        self.setMinimumWidth(popup_width)
        self.setMaximumWidth(popup_width)
        self.adjustSize()
        self.move(global_pos)
        self.show()
        self.raise_()

    def _render_sources(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.source_buttons = {}
        grouped_entries = self._group_entries()
        show_sections = len([entries for entries in grouped_entries.values() if entries]) > 1
        row = 0
        for source_kind, entries in grouped_entries.items():
            if not entries:
                continue
            if show_sections:
                label = QLabel(self._SOURCE_KIND_LABELS.get(source_kind, "其他源"), self._grid_widget)
                label.setObjectName("classicSourcePopupSectionTitle")
                self._grid_layout.addWidget(label, row, 0, 1, self.COLUMN_COUNT)
                row += 1
            for index, entry in enumerate(entries):
                button = self._create_source_button(entry)
                self._grid_layout.addWidget(button, row + index // self.COLUMN_COUNT, index % self.COLUMN_COUNT)
                self.source_buttons[entry.key] = button
            row += (len(entries) + self.COLUMN_COUNT - 1) // self.COLUMN_COUNT
        for column in range(self.COLUMN_COUNT):
            self._grid_layout.setColumnStretch(column, 1)
        self.adjustSize()

    def _create_source_button(self, entry: SourceEntry) -> QPushButton:
        button = QPushButton(entry.title, self._grid_widget)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setCheckable(True)
        button.setChecked(entry.key == self._current_key)
        button.setProperty("selected", entry.key == self._current_key)
        button.setMinimumHeight(38)
        button.setFlat(True)
        button.setStyleSheet(self._source_button_qss())
        button.setMinimumWidth(self._preferred_column_width(button.fontMetrics()))
        button.setToolTip(entry.title)
        button.clicked.connect(lambda checked=False, key=entry.key: self._select_source(key))
        return button

    def _group_entries(self) -> dict[str, list[SourceEntry]]:
        grouped: dict[str, list[SourceEntry]] = {source_kind: [] for source_kind in self._SOURCE_KIND_ORDER}
        for entry in self._entries:
            source_kind = self._normalized_source_kind(entry)
            grouped.setdefault(source_kind, []).append(entry)
        return {
            source_kind: grouped[source_kind]
            for source_kind in (*self._SOURCE_KIND_ORDER, *grouped.keys())
            if source_kind in grouped and grouped[source_kind]
        }

    @staticmethod
    def _normalized_source_kind(entry: SourceEntry) -> str:
        source_kind = str(entry.source_kind or "").strip()
        if source_kind:
            return source_kind
        return "plugin" if entry.key.startswith("plugin:") else "builtin"

    def _preferred_column_width(self, metrics=None) -> int:
        if not self._entries:
            return 112
        metrics = metrics or self.fontMetrics()
        widest_title = max(metrics.horizontalAdvance(entry.title) for entry in self._entries)
        return max(112, widest_title + 56)

    def _preferred_popup_width(self) -> int:
        margins = self._container_layout.contentsMargins()
        horizontal_margins = margins.left() + margins.right()
        gaps = self._grid_layout.horizontalSpacing() * max(0, self.COLUMN_COUNT - 1)
        return horizontal_margins + gaps + self._preferred_column_width() * self.COLUMN_COUNT

    def _select_source(self, key: str) -> None:
        self.hide()
        self.source_selected.emit(key)

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self._container.setStyleSheet(
            f"""
            QFrame#classicSourcePopupContainer {{
                background: {tokens.window_bg};
                border: 1px solid {tokens.border_subtle};
                border-radius: 0;
                color: {tokens.text_primary};
            }}
            QLabel#classicSourcePopupTitle {{
                color: {tokens.text_secondary};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#classicSourcePopupSectionTitle {{
                color: {tokens.text_secondary};
                font-size: 12px;
                font-weight: 600;
                padding-top: 2px;
            }}
            """
        )
        for button in self.source_buttons.values():
            button.setStyleSheet(self._source_button_qss())

    @staticmethod
    def _source_button_qss() -> str:
        tokens = current_tokens()
        return f"""
        QPushButton {{
            text-align: center;
            color: {tokens.text_primary};
            background: transparent;
            border: 1px solid {tokens.border_subtle};
            padding: 7px 10px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {tokens.panel_alt_bg};
            border-color: {tokens.input_hover_border};
        }}
        QPushButton:checked {{
            background: {tokens.menu_selected_bg};
            border-color: {tokens.accent};
            color: {tokens.accent};
            font-weight: 600;
        }}
        """


class ClassicHomePage(QWidget):
    category_selected = Signal(str)
    source_changed = Signal(str)
    item_open_requested = Signal(object)
    folder_breadcrumb_requested = Signal(str, str, int)

    def __init__(
        self,
        source_entries: list[SourceEntry],
        initial_source_key: str = "",
        initial_category_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_entries = source_entries
        self._current_source_key = initial_source_key or (
            source_entries[0].key if source_entries else ""
        )
        self._initial_category_id = initial_category_id
        self._categories: list[DoubanCategory] = []
        self._selected_category_index = -1
        self._visible_category_indices: list[int] = []
        self._hidden_category_indices: list[int] = []
        self._refreshing_category_tabs = False
        self._app_event_filter_installed = False
        self._app_state_signal_connected = False

        self.source_button = QPushButton(self._current_source_title())
        self.source_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_button.setMinimumWidth(120)
        self.source_button.setMaximumWidth(180)
        self.source_button.setFixedWidth(160)
        self.source_button.setFixedHeight(36)
        self.source_button.setFlat(True)
        self.source_button.setStyleSheet(self._source_button_qss())
        self.source_button.clicked.connect(self._toggle_source_popup)
        self.source_popup = ClassicSourcePopup(self)
        self.source_popup.source_selected.connect(self._handle_source_selected)
        self._populate_source_popup()

        # Category tab bar
        self.category_tab_bar = QTabBar()
        self.category_tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.category_tab_bar.setDocumentMode(True)
        self.category_tab_bar.setExpanding(False)
        self.category_tab_bar.setDrawBase(False)
        self.category_tab_bar.setUsesScrollButtons(False)
        self.category_tab_bar.setStyleSheet(build_navigation_tabbar_qss(current_tokens()))
        self.category_tab_bar.currentChanged.connect(self._handle_category_changed)
        self.category_tab_bar.tabBarClicked.connect(self._handle_category_tab_clicked)
        self.category_more_button = QPushButton("更多")
        self.category_more_button.setCheckable(True)
        self.category_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.category_more_button.setFlat(True)
        self.category_more_button.hide()
        self.category_more_button.setStyleSheet(self._category_more_button_qss())
        self.category_more_button.clicked.connect(self._open_category_overflow_menu)
        self._category_tab_width_measure_bar = QTabBar(self)
        self._category_tab_width_measure_bar.setDocumentMode(True)
        self._category_tab_width_measure_bar.hide()
        self._category_overflow_menu: QMenu | None = None

        # Poster grid page for the active source
        initial_entry = self._current_entry()
        self.grid_page = PosterGridPage(
            initial_entry.controller if initial_entry and initial_entry.controller is not None else _FakeEmptyController(),
            click_action="open",
            search_enabled=bool(initial_entry.search_enabled) if initial_entry else False,
            initial_category_id=self._initial_category_id,
            category_layout="tabs",
            folder_navigation_enabled=self._entry_folder_navigation_enabled(initial_entry),
        )
        self.grid_page.item_open_requested.connect(self.item_open_requested.emit)
        self.grid_page.folder_breadcrumb_requested.connect(self.folder_breadcrumb_requested.emit)

        category_row = QHBoxLayout()
        category_row.setContentsMargins(0, 0, 0, 0)
        category_row.setSpacing(8)
        category_row.addWidget(self.category_tab_bar, 1)
        category_row.addWidget(self.category_more_button, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(category_row)
        layout.addWidget(self.grid_page, 1)

        # Load initial categories synchronously
        if initial_entry is not None:
            self._load_categories_from_controller(initial_entry.controller)

    def _current_entry(self) -> SourceEntry | None:
        for entry in self._source_entries:
            if entry.key == self._current_source_key:
                return entry
        return self._source_entries[0] if self._source_entries else None

    def set_source_entries(self, source_entries: list[SourceEntry], preferred_key: str = "") -> None:
        previous_key = self._current_source_key
        self._source_entries = source_entries
        keys = {entry.key for entry in source_entries}
        next_key = (
            preferred_key
            if preferred_key in keys
            else previous_key
            if previous_key in keys
            else (source_entries[0].key if source_entries else "")
        )
        self._current_source_key = next_key
        self._populate_source_popup()
        self._update_source_button_text()
        entry = self._current_entry()
        if entry is not None and (
            next_key != previous_key
            or getattr(self.grid_page, "controller", None) is not entry.controller
        ):
            self._replace_grid_page(entry)

    def _populate_source_popup(self) -> None:
        self.source_popup.set_sources(self._source_entries, self._current_source_key)

    def _handle_source_selected(self, key: str) -> None:
        self._remove_source_popup_event_filter()
        self.select_source_key(key)

    def select_source_key(self, key: str, *, emit: bool = True) -> None:
        if not key or key == self._current_source_key:
            return
        self._current_source_key = key
        self._populate_source_popup()
        self._update_source_button_text()
        entry = self._current_entry()
        if entry is None:
            return
        if entry.controller is not None:
            self._replace_grid_page(entry)
        if emit:
            self.source_changed.emit(key)

    def _toggle_source_popup(self) -> None:
        if self.source_popup.isVisible():
            self._hide_source_popup()
            return
        self._populate_source_popup()
        pos = self.source_button.mapToGlobal(self.source_button.rect().bottomLeft())
        self.source_popup.show_at(pos, self.source_button.width())
        self._install_source_popup_event_filter()

    def _hide_source_popup(self) -> None:
        self.source_popup.hide()
        self._remove_source_popup_event_filter()

    def _install_source_popup_event_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and not self._app_event_filter_installed:
            app.installEventFilter(self)
            self._app_event_filter_installed = True
        if app is not None and not self._app_state_signal_connected:
            app.applicationStateChanged.connect(self._handle_application_state_changed)
            self._app_state_signal_connected = True

    def _remove_source_popup_event_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and self._app_event_filter_installed:
            app.removeEventFilter(self)
            self._app_event_filter_installed = False
        if app is not None and self._app_state_signal_connected:
            app.applicationStateChanged.disconnect(self._handle_application_state_changed)
            self._app_state_signal_connected = False

    def _handle_application_state_changed(self, state) -> None:
        if state == Qt.ApplicationState.ApplicationInactive:
            self._hide_source_popup()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if (
            self.source_popup.isVisible()
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            global_pos = event.globalPosition().toPoint()
            if not self._source_popup_contains_global_pos(global_pos):
                self._hide_source_popup()
        if not isinstance(watched, QObject):
            return False
        return super().eventFilter(watched, event)

    def _source_popup_contains_global_pos(self, global_pos) -> bool:
        return (
            self.source_popup.geometry().contains(global_pos)
            or self.source_button.rect().contains(self.source_button.mapFromGlobal(global_pos))
        )

    def _current_source_title(self) -> str:
        entry = self._current_entry()
        return entry.title if entry is not None else "选择源"

    def _update_source_button_text(self) -> None:
        self.source_button.setText(self._current_source_title())

    @staticmethod
    def _source_button_qss() -> str:
        tokens = current_tokens()
        return f"""
        QPushButton {{
            color: {tokens.text_primary};
            background: {tokens.input_bg};
            border: 1px solid {tokens.input_border};
            border-radius: 18px;
            padding: 0 14px;
            text-align: left;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {tokens.panel_alt_bg};
            border-color: {tokens.input_hover_border};
        }}
        QPushButton:pressed {{
            border-color: {tokens.accent};
        }}
        """

    def _apply_theme(self) -> None:
        self.source_button.setStyleSheet(self._source_button_qss())
        self.category_tab_bar.setStyleSheet(build_navigation_tabbar_qss(current_tokens()))
        self.category_more_button.setStyleSheet(self._category_more_button_qss())
        self.source_popup._apply_theme()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._hide_source_popup()
        super().closeEvent(event)

    def _replace_grid_page(self, entry: SourceEntry) -> None:
        # Replace the grid page with a new one for the new source
        new_page = PosterGridPage(
            entry.controller if entry.controller is not None else _FakeEmptyController(),
            click_action="open",
            search_enabled=bool(entry.search_enabled),
            initial_category_id=self._initial_category_id,
            category_layout="tabs",
            folder_navigation_enabled=self._entry_folder_navigation_enabled(entry),
        )
        new_page.item_open_requested.connect(self.item_open_requested.emit)
        new_page.folder_breadcrumb_requested.connect(self.folder_breadcrumb_requested.emit)
        layout = self.layout()
        old_page = self.grid_page
        layout.replaceWidget(old_page, new_page)
        old_page.deleteLater()
        self.grid_page = new_page
        self._load_categories_from_controller(entry.controller)

    @staticmethod
    def _entry_folder_navigation_enabled(entry: SourceEntry | None) -> bool:
        if entry is None:
            return False
        return callable(getattr(entry.controller, "load_folder_items", None))

    def _handle_category_changed(self, index: int) -> None:
        if self._refreshing_category_tabs:
            return
        if not (0 <= index < len(self._visible_category_indices)):
            return
        self._select_category_index(self._visible_category_indices[index])

    def _handle_category_tab_clicked(self, index: int) -> None:
        if self._refreshing_category_tabs:
            return
        if not (0 <= index < len(self._visible_category_indices)):
            return
        self._select_category_index(self._visible_category_indices[index])

    def _select_category_index(self, index: int) -> None:
        if not (0 <= index < len(self._categories)):
            return
        category_id = self._categories[index].type_id
        if self._selected_category_index == index and self.grid_page.selected_category_id == category_id:
            return
        self._selected_category_index = index
        self._initial_category_id = category_id
        self.grid_page.selected_category_id = category_id
        self._refresh_category_tabs()
        self.category_selected.emit(category_id)
        self.grid_page.load_items(category_id, 1)

    def _category_tab_title_width(self, title: str) -> int:
        self._category_tab_width_measure_bar.setFont(self.category_tab_bar.font())
        index = self._category_tab_width_measure_bar.addTab(title)
        width = self._category_tab_width_measure_bar.tabSizeHint(index).width()
        self._category_tab_width_measure_bar.removeTab(index)
        return width

    def _category_more_button_width(self) -> int:
        return max(self.category_more_button.sizeHint().width(), 84)

    def _split_visible_and_hidden_category_indices(self) -> tuple[list[int], list[int]]:
        if not self._categories:
            return [], []
        button_spacing = 8
        total_width = self.category_tab_bar.width()
        if self.category_more_button.isVisible():
            total_width += self._category_more_button_width() + button_spacing
        if total_width <= 0:
            total_width = max(self.width(), 0)
        widths = [
            (index, self._category_tab_title_width(category.type_name))
            for index, category in enumerate(self._categories)
        ]
        available = total_width
        if sum(width for _index, width in widths) > available:
            available -= self._category_more_button_width() + button_spacing
        visible: list[int] = []
        hidden: list[int] = []
        used = 0
        for index, width in widths:
            if used + width <= available:
                visible.append(index)
                used += width
            else:
                hidden.append(index)
        return visible, hidden

    def _refresh_category_tabs(self) -> None:
        self._visible_category_indices, self._hidden_category_indices = self._split_visible_and_hidden_category_indices()
        selected_index = self._selected_category_index
        self._refreshing_category_tabs = True
        self.category_tab_bar.blockSignals(True)
        while self.category_tab_bar.count() > 0:
            self.category_tab_bar.removeTab(0)
        for category_index in self._visible_category_indices:
            self.category_tab_bar.addTab(self._categories[category_index].type_name)
        selected_visible_index = (
            self._visible_category_indices.index(selected_index)
            if selected_index in self._visible_category_indices
            else -1
        )
        self.category_tab_bar.setCurrentIndex(selected_visible_index)
        self.category_tab_bar.blockSignals(False)
        self._refreshing_category_tabs = False
        hidden_count = len(self._hidden_category_indices)
        self.category_more_button.setVisible(hidden_count > 0)
        self.category_more_button.setText(f"更多({hidden_count})" if hidden_count else "更多")
        hidden_selected = selected_index in self._hidden_category_indices
        self.category_more_button.setChecked(hidden_selected)
        self._set_dynamic_property(self.category_tab_bar, "hiddenTabActive", hidden_selected)
        if hidden_selected and 0 <= selected_index < len(self._categories):
            self.category_more_button.setToolTip(self._categories[selected_index].type_name)
        else:
            self.category_more_button.setToolTip("")

    def _open_category_overflow_menu(self) -> None:
        if not self._hidden_category_indices:
            self._refresh_category_tabs()
            return
        menu = QMenu(self.category_more_button)
        for category_index in self._hidden_category_indices:
            category = self._categories[category_index]
            action = QAction(category.type_name, menu)
            action.setCheckable(True)
            action.setChecked(category_index == self._selected_category_index)
            action.triggered.connect(
                lambda checked=False, index=category_index: self._select_category_index(index)
            )
            menu.addAction(action)
        menu.aboutToHide.connect(self._refresh_category_tabs)
        self._category_overflow_menu = menu
        self.category_more_button.setChecked(True)
        menu.popup(self.category_more_button.mapToGlobal(self.category_more_button.rect().bottomLeft()))

    @staticmethod
    def _category_more_button_qss() -> str:
        return build_pill_button_qss(current_tokens(), checked_accent=True, border_radius=12, horizontal_padding=8)

    @staticmethod
    def _set_dynamic_property(widget: QWidget, name: str, value: object) -> None:
        if widget.property(name) == value:
            return
        widget.setProperty(name, value)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _load_categories_from_controller(self, controller) -> None:
        if controller is None:
            self._categories = []
            self._selected_category_index = -1
            self.category_tab_bar.blockSignals(True)
            while self.category_tab_bar.count() > 0:
                self.category_tab_bar.removeTab(0)
            self.category_tab_bar.blockSignals(False)
            self._refresh_category_tabs()
            self.grid_page.show_items([], 0, page=1, empty_message="源加载中...")
            return
        try:
            categories = controller.load_categories()
        except Exception:
            categories = []
        self._categories = list(categories)
        if self._categories:
            target_index = next(
                (
                    index
                    for index, category in enumerate(self._categories)
                    if category.type_id == self._initial_category_id
                ),
                0,
            )
            self._selected_category_index = target_index
            self._refresh_category_tabs()
            self._select_category_index(target_index)
        else:
            self._selected_category_index = -1
            self._refresh_category_tabs()

    def current_source_key(self) -> str:
        return self._current_source_key

    def current_source_title(self) -> str:
        return self._current_source_title()

    def current_category_id(self) -> str:
        if not (0 <= self._selected_category_index < len(self._categories)):
            return ""
        return self._categories[self._selected_category_index].type_id

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_category_tabs()


class _FakeEmptyController:
    def load_categories(self):
        return []

    def load_items(self, category_id, page, filters=None):
        return [], 0
