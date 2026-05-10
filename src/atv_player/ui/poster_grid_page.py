from __future__ import annotations

import threading
from collections.abc import Callable
from threading import BoundedSemaphore
from typing import cast

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.api import ApiError, UnauthorizedError
from atv_player.models import CategoryFilterOption
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.poster_loader import load_local_poster_image, load_remote_poster_image, normalize_poster_url


class _PosterGridSignals(QObject):
    categories_loaded = Signal(int, object)
    items_loaded = Signal(int, object, int)
    failed = Signal(str, int, str)
    unauthorized = Signal(int, str)
    poster_loaded = Signal(object, object)


class _FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = max(0, self.spacing())

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if line_height > 0 and next_x > effective_rect.right() + 1:
                x = effective_rect.x()
                y += line_height + spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x + spacing
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


class PosterGridPage(QWidget, AsyncGuardMixin):
    search_requested = Signal(str)
    open_requested = Signal(str)
    item_open_requested = Signal(object)
    folder_breadcrumb_requested = Signal(str, str, int)
    selected_category_changed = Signal(str)
    unauthorized = Signal()
    _CARD_WIDTH = 220
    _CARD_HEIGHT = 360
    _CARD_POSTER_SIZE = QSize(200, 285)
    _CARD_SPACING = 16
    _MIN_CARD_COLUMNS = 1
    _MAX_CARD_COLUMNS = 6
    _FILTER_PANEL_MAX_HEIGHT = 310

    def __init__(
        self,
        controller,
        click_action: str = "search",
        search_enabled: bool = False,
        folder_navigation_enabled: bool = False,
        initial_category_id: str = "",
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._click_action = click_action
        self._search_enabled = search_enabled
        self._folder_navigation_enabled = folder_navigation_enabled
        self._initial_category_id = initial_category_id
        self._initial_load_started = False
        self._search_mode = False
        self._search_keyword = ""
        self._external_results_active = False
        self._external_empty_message = "暂无内容"
        self._external_page_loader: Callable[[int], None] | None = None
        self._external_loading = False
        self._infer_page_size_from_items = bool(getattr(controller, "uses_result_length_for_pagination", False))
        self._search_row: QHBoxLayout | None = None
        self._search_controls_container: QWidget | None = None
        self.category_list = QListWidget()
        self.keyword_edit = QLineEdit()
        self.search_button = QPushButton("搜索")
        self.clear_button = QPushButton("清空")
        self.refresh_button = QPushButton("刷新")
        self.filter_toggle_button = QPushButton("筛选")
        self.filter_panel = QFrame()
        self.filter_panel_layout = QFormLayout(self.filter_panel)
        self.filter_scroll_area = QScrollArea()
        self.breadcrumb_bar = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_bar)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_layout.setSpacing(4)
        self.breadcrumb_buttons: list[QPushButton] = []
        self.status_label = QLabel("")
        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
        self.cards_widget = QWidget()
        self.cards_layout = QGridLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(self._CARD_SPACING)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setWidget(self.cards_widget)
        self.card_buttons: list[QToolButton] = []
        self._folder_breadcrumbs: list[dict[str, str]] = []
        self.filter_buttons: dict[str, list[QPushButton]] = {}
        self.categories = []
        self.items = []
        self.selected_category_id = ""
        self.current_page = 1
        self.page_size = 30
        self.total_items = 0
        self._estimated_page_size: int | None = None
        self._category_filter_state: dict[str, dict[str, str]] = {}
        self._current_card_columns = self._MIN_CARD_COLUMNS
        self._categories_request_id = 0
        self._items_request_id = 0
        self._poster_generation = 0
        self._poster_semaphore = BoundedSemaphore(value=6)
        self._signals = _PosterGridSignals()
        self._connect_async_signal(self._signals.categories_loaded, self._handle_categories_loaded)
        self._connect_async_signal(self._signals.items_loaded, self._handle_items_loaded)
        self._connect_async_signal(self._signals.failed, self._handle_failed)
        self._connect_async_signal(self._signals.unauthorized, self._handle_unauthorized)
        self._connect_async_signal(self._signals.poster_loaded, self._handle_poster_loaded)

        for button in (
            self.search_button,
            self.clear_button,
            self.refresh_button,
            self.filter_toggle_button,
            self.prev_page_button,
            self.next_page_button,
        ):
            self._set_button_cursor(button)

        self.category_list.setMinimumWidth(180)
        self.status_label.setWordWrap(True)
        self.breadcrumb_bar.setVisible(self._folder_navigation_enabled)
        self.filter_panel.hide()
        self.filter_scroll_area.setWidgetResizable(True)
        self.filter_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.filter_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filter_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filter_scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.filter_scroll_area.setWidget(self.filter_panel)
        self.filter_scroll_area.setMaximumHeight(self._FILTER_PANEL_MAX_HEIGHT)
        self.filter_scroll_area.hide()
        self.filter_toggle_button.hide()
        self._sync_category_list_visibility()

        right = QVBoxLayout()
        if self._search_enabled:
            search_row = QHBoxLayout()
            self._search_row = search_row
            search_row.addWidget(self.keyword_edit, 1)
            search_row.addWidget(self.search_button)
            search_row.addWidget(self.clear_button)
            search_row.addWidget(self.refresh_button)
            search_row.addWidget(self.filter_toggle_button)
            self._search_controls_container = QWidget()
            self._search_controls_container.setLayout(search_row)
            right.addWidget(self._search_controls_container)
        else:
            self.keyword_edit.hide()
            self.search_button.hide()
            self.clear_button.hide()
            self.refresh_button.hide()
            right.addWidget(self.filter_toggle_button)
        right.addWidget(self.filter_scroll_area)
        right.addWidget(self.breadcrumb_bar)
        right.addWidget(self.status_label)
        right.addWidget(self.cards_scroll, 1)
        paging = QHBoxLayout()
        paging.addStretch(1)
        paging.addWidget(self.prev_page_button)
        paging.addWidget(self.page_label)
        paging.addWidget(self.next_page_button)
        right.addLayout(paging)

        self.content_container = QWidget()
        self.content_container.setMaximumWidth(1800)
        self.content_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        content_layout = QHBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.category_list, 1)
        content_layout.addLayout(right, 4)

        layout = QHBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.content_container, 100)
        layout.addStretch(1)

        self.category_list.currentRowChanged.connect(self._handle_category_row_changed)
        self.prev_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.filter_toggle_button.clicked.connect(self._toggle_filters)
        if self._search_enabled:
            self.search_button.clicked.connect(self.search)
            self.clear_button.clicked.connect(self.clear_search)
            self.refresh_button.clicked.connect(self._refresh_current_view)
            self.keyword_edit.returnPressed.connect(self.search)
            self.keyword_edit.textChanged.connect(self._handle_keyword_text_changed)
            self._update_search_action_buttons()
            self._sync_search_controls_visibility()

    def _is_widget_alive(self) -> bool:
        return self._can_deliver_async_result()

    def ensure_loaded(self) -> None:
        if self._initial_load_started:
            return
        self._initial_load_started = True
        self.reload_categories()

    def reload_categories(self) -> None:
        self._categories_request_id += 1
        request_id = self._categories_request_id
        self.status_label.setText("加载分类中...")

        def run() -> None:
            try:
                categories = self.controller.load_categories()
            except UnauthorizedError:
                if self._is_widget_alive():
                    self._signals.unauthorized.emit(request_id, "categories")
                return
            except ApiError as exc:
                if self._is_widget_alive():
                    self._signals.failed.emit(str(exc), request_id, "categories")
                return
            if self._is_widget_alive():
                self._signals.categories_loaded.emit(request_id, categories)

        threading.Thread(target=run, daemon=True).start()

    def load_items(self, category_id: str, page: int) -> None:
        self._external_results_active = False
        self._sync_category_list_visibility()
        self._items_request_id += 1
        request_id = self._items_request_id
        active_filters = dict(self._category_filter_state.get(category_id, {}))
        self.status_label.setText("加载中...")

        def run() -> None:
            try:
                items, total = self.controller.load_items(category_id, page, filters=active_filters)
            except UnauthorizedError:
                if self._is_widget_alive():
                    self._signals.unauthorized.emit(request_id, "items")
                return
            except ApiError as exc:
                if self._is_widget_alive():
                    self._signals.failed.emit(str(exc), request_id, "items")
                return
            if self._is_widget_alive():
                self._signals.items_loaded.emit(request_id, items, total)

        threading.Thread(target=run, daemon=True).start()

    def _handle_categories_loaded(self, request_id: int, categories) -> None:
        if request_id != self._categories_request_id:
            return
        self.categories = list(categories)
        self.category_list.clear()
        for category in self.categories:
            self.category_list.addItem(category.type_name)
        if not self.categories:
            self.status_label.setText("暂无分类")
            self._update_pagination()
            return
        target_category_id = self.selected_category_id or self._initial_category_id
        target_row = next(
            (index for index, category in enumerate(self.categories) if category.type_id == target_category_id),
            0,
        )
        self.category_list.setCurrentRow(target_row)

    def _current_category(self):
        row = self.category_list.currentRow()
        if not (0 <= row < len(self.categories)):
            return None
        return self.categories[row]

    def _default_filter_state(self, category) -> dict[str, str]:
        return {}

    def _selected_filter_values(self) -> dict[str, str]:
        selected: dict[str, str] = {}
        for key, buttons in self.filter_buttons.items():
            checked = next((button for button in buttons if button.isChecked()), None)
            if checked is None:
                continue
            normalized = str(checked.property("filterValue") or "")
            if normalized:
                selected[key] = normalized
        return selected

    def _remember_current_filter_state(self) -> None:
        if not self.selected_category_id:
            return
        self._category_filter_state[self.selected_category_id] = self._selected_filter_values()

    def _rebuild_filter_panel(self) -> None:
        while self.filter_panel_layout.rowCount():
            self.filter_panel_layout.removeRow(0)
        self.filter_buttons = {}
        category = self._current_category()
        filters = list(getattr(category, "filters", [])) if category is not None else []
        if not filters:
            self.filter_toggle_button.hide()
            self.filter_scroll_area.hide()
            self.filter_panel.hide()
            return
        state = self._category_filter_state.setdefault(category.type_id, self._default_filter_state(category))
        for group in filters:
            if not group.options:
                continue
            selected_value = state.get(group.key, "")
            buttons_widget = self._build_filter_buttons(group.key, group.options, selected_value)
            self.filter_panel_layout.addRow(self._build_filter_group_label(group.name), buttons_widget)
        if not self.filter_buttons or self._search_mode:
            self.filter_toggle_button.setHidden(True)
            self.filter_scroll_area.hide()
            self.filter_panel.hide()
            return
        self._sync_filter_scroll_area_height()
        self.filter_toggle_button.show()
        self.filter_scroll_area.hide()
        self.filter_panel.hide()

    def _build_filter_buttons(self, key: str, options, selected_value: str) -> QWidget:
        container = QWidget(self.filter_panel)
        layout = _FlowLayout(container, spacing=8)
        merged_options = list(options)
        if not any(option.value == "" for option in merged_options) and not any(option.name == "全部" for option in merged_options):
            merged_options = [CategoryFilterOption(name="默认", value=""), *merged_options]
        if selected_value not in {option.value for option in merged_options}:
            selected_value = ""

        buttons: list[QPushButton] = []
        for option in merged_options:
            button = QPushButton(option.name, container)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            self._set_button_cursor(button)
            self._apply_filter_button_style(button)
            button.setProperty("filterKey", key)
            button.setProperty("filterValue", option.value)
            button.setChecked(option.value == selected_value)
            button.toggled.connect(self._handle_filter_button_toggled)
            layout.addWidget(button)
            buttons.append(button)

        self.filter_buttons[key] = buttons
        return container

    def _build_filter_group_label(self, name: str) -> QLabel:
        label = QLabel(name, self.filter_panel)
        font = label.font()
        font.setWeight(QFont.Weight.Bold)
        label.setFont(font)
        label.setStyleSheet("color: #0066cc;")
        return label

    def _toggle_filters(self) -> None:
        if not self.filter_buttons or self._search_mode:
            return
        is_hidden = self.filter_scroll_area.isHidden()
        self.filter_scroll_area.setVisible(is_hidden)
        self.filter_panel.setVisible(is_hidden)
        if is_hidden:
            self._sync_filter_scroll_area_height()

    def _sync_filter_scroll_area_height(self) -> None:
        if not self.filter_buttons:
            return
        self.filter_panel_layout.invalidate()
        self.filter_panel_layout.activate()
        width = max(1, self.filter_scroll_area.viewport().width(), self.filter_panel.width())
        if self.filter_panel_layout.hasHeightForWidth():
            content_height = self.filter_panel_layout.heightForWidth(width)
        else:
            content_height = self.filter_panel_layout.sizeHint().height()
        content_height = max(1, content_height)
        self.filter_scroll_area.setFixedHeight(min(content_height, self._FILTER_PANEL_MAX_HEIGHT))

    def _set_button_cursor(self, button: QPushButton | QToolButton) -> None:
        button.setCursor(Qt.CursorShape.PointingHandCursor)

    def _apply_filter_button_style(self, button: QPushButton) -> None:
        button.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                color: #1a1a1a;
                border: 1px solid #d0d0d0;
                border-radius: 14px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton:checked {
                background-color: #ffffff;
                color: #0066cc;
                border: 1px solid #0066cc;
            }
            QPushButton:checked:hover {
                color: #0080ff;
                border: 1px solid #0080ff;
            }
            """
        )

    def _update_search_action_buttons(self) -> None:
        if not self._search_enabled:
            return
        has_keyword = bool(self.keyword_edit.text().strip())
        self.search_button.setEnabled(has_keyword)
        self.clear_button.setEnabled(has_keyword)

    def _handle_keyword_text_changed(self) -> None:
        keyword = self.keyword_edit.text().strip()
        if not keyword and self._search_mode:
            self.clear_search()
            return
        self._update_search_action_buttons()

    def _handle_filter_button_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._handle_filter_changed()

    def _handle_filter_changed(self) -> None:
        if self._search_mode or not self.selected_category_id:
            return
        self._remember_current_filter_state()
        self.current_page = 1
        self.load_items(self.selected_category_id, self.current_page)

    def _handle_category_row_changed(self, row: int) -> None:
        if not (0 <= row < len(self.categories)):
            return
        if self.selected_category_id:
            self._remember_current_filter_state()
        category = self.categories[row]
        self.selected_category_id = category.type_id
        self.selected_category_changed.emit(self.selected_category_id)
        self._category_filter_state.setdefault(category.type_id, self._default_filter_state(category))
        self._rebuild_filter_panel()
        self.current_page = 1
        self.reset_folder_breadcrumbs_to_root()
        if self._search_mode:
            return
        self.load_items(self.selected_category_id, self.current_page)

    def _handle_items_loaded(self, request_id: int, items, total: int) -> None:
        if request_id != self._items_request_id:
            return
        self.show_items(items, total)

    def _handle_failed(self, message: str, request_id: int, request_kind: str) -> None:
        if request_kind == "categories" and request_id != self._categories_request_id:
            return
        if request_kind == "items" and request_id != self._items_request_id:
            return
        self.status_label.setText(message)
        self._update_pagination()

    def _handle_unauthorized(self, request_id: int, request_kind: str) -> None:
        if request_kind == "categories" and request_id != self._categories_request_id:
            return
        if request_kind == "items" and request_id != self._items_request_id:
            return
        self.unauthorized.emit()

    def _render_cards(self) -> None:
        self._poster_generation += 1
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is None:
                continue
            widget = cast(QWidget | None, item.widget())
            if widget is not None:
                widget.deleteLater()
        self.card_buttons = []
        for item in self.items:
            button = self._build_card_button(item)
            self.card_buttons.append(button)
            self._start_card_poster_load(button, item)
        self._relayout_cards()

    def _relayout_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is None:
                continue
            widget = cast(QWidget | None, item.widget())
            if widget is not None:
                self.cards_layout.removeWidget(widget)
        columns = self._column_count_for_width(self.cards_scroll.viewport().width())
        self._current_card_columns = columns
        for index, button in enumerate(self.card_buttons):
            self.cards_layout.addWidget(button, index // columns, index % columns)

    def _column_count_for_width(self, available_width: int) -> int:
        if available_width <= 0:
            return self._MIN_CARD_COLUMNS
        fit_columns = (available_width + self._CARD_SPACING) // (self._CARD_WIDTH + self._CARD_SPACING)
        fit_columns = max(self._MIN_CARD_COLUMNS, fit_columns)
        return min(fit_columns, self._MAX_CARD_COLUMNS)

    def _effective_page_size(self) -> int:
        return self._estimated_page_size or self.page_size

    def _total_pages(self) -> int:
        page_size = max(1, self._effective_page_size())
        return max(1, (self.total_items + page_size - 1) // page_size)

    def _update_page_size_estimate(self, item_count: int, total: int, page: int) -> None:
        if not self._infer_page_size_from_items:
            return
        if page <= 1:
            self._estimated_page_size = None
        if item_count <= 0 or total <= item_count:
            return
        if self._estimated_page_size is None:
            self._estimated_page_size = item_count
            return
        self._estimated_page_size = max(self._estimated_page_size, item_count)

    def _update_pagination(self) -> None:
        total_pages = self._total_pages()
        self.page_label.setText(f"第 {self.current_page} / {total_pages} 页")
        if self._external_results_active:
            pagination_enabled = self._external_page_loader is not None and not self._external_loading
            self.prev_page_button.setEnabled(pagination_enabled and self.current_page > 1)
            self.next_page_button.setEnabled(pagination_enabled and self.current_page < total_pages)
            return
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)

    def previous_page(self) -> None:
        if self._external_results_active:
            if self._external_page_loader is None or self._external_loading or self.current_page <= 1:
                return
            self._external_loading = True
            self.status_label.setText("搜索中...")
            self._update_pagination()
            self._external_page_loader(self.current_page - 1)
            return
        if self.current_page <= 1:
            return
        self.current_page -= 1
        if self._search_mode:
            self._search_items(self._search_keyword, self.current_page)
            return
        if not self.selected_category_id:
            return
        self.load_items(self.selected_category_id, self.current_page)

    def next_page(self) -> None:
        total_pages = self._total_pages()
        if self._external_results_active:
            if self._external_page_loader is None or self._external_loading or self.current_page >= total_pages:
                return
            self._external_loading = True
            self.status_label.setText("搜索中...")
            self._update_pagination()
            self._external_page_loader(self.current_page + 1)
            return
        if self.current_page >= total_pages:
            return
        self.current_page += 1
        if self._search_mode:
            self._search_items(self._search_keyword, self.current_page)
            return
        if not self.selected_category_id:
            return
        self.load_items(self.selected_category_id, self.current_page)

    def search(self) -> None:
        if not self._search_enabled:
            return
        keyword = self.keyword_edit.text().strip()
        if not keyword:
            return
        self._external_results_active = False
        self._external_page_loader = None
        self._external_loading = False
        self._sync_category_list_visibility()
        self._sync_search_controls_visibility()
        self._search_mode = True
        self._search_keyword = keyword
        self.current_page = 1
        self.filter_toggle_button.hide()
        self.filter_scroll_area.hide()
        self.filter_panel.hide()
        self._search_items(keyword, self.current_page)

    def clear_search(self) -> None:
        if not self._search_enabled:
            return
        self._external_results_active = False
        self._external_page_loader = None
        self._external_loading = False
        self._sync_category_list_visibility()
        self._sync_search_controls_visibility()
        self.keyword_edit.clear()
        self._search_mode = False
        self._search_keyword = ""
        self._update_search_action_buttons()
        self.current_page = 1
        self._rebuild_filter_panel()
        if self.selected_category_id:
            self.load_items(self.selected_category_id, self.current_page)

    def _refresh_current_view(self) -> None:
        if self._external_results_active:
            self.show_items(
                self.items,
                self.total_items,
                page=self.current_page,
                empty_message=self._external_empty_message,
            )
            return
        if self._search_mode and self._search_keyword:
            self._search_items(self._search_keyword, self.current_page)
        elif self.selected_category_id:
            self.load_items(self.selected_category_id, self.current_page)
        else:
            self.reload_categories()

    def _search_items(self, keyword: str, page: int) -> None:
        self._items_request_id += 1
        request_id = self._items_request_id
        self.status_label.setText("搜索中...")

        def run() -> None:
            try:
                items, total = self.controller.search_items(keyword, page, category_id=self.selected_category_id)
            except UnauthorizedError:
                if self._is_widget_alive():
                    self._signals.unauthorized.emit(request_id, "items")
                return
            except ApiError as exc:
                if self._is_widget_alive():
                    self._signals.failed.emit(str(exc), request_id, "items")
                return
            if self._is_widget_alive():
                self._signals.items_loaded.emit(request_id, items, total)

        threading.Thread(target=run, daemon=True).start()

    def show_items(
        self,
        items,
        total: int,
        page: int | None = None,
        empty_message: str = "当前分类暂无内容",
    ) -> None:
        self._items_request_id += 1
        if page is not None:
            self.current_page = page
        self.items = list(items)
        self.total_items = total
        self._update_page_size_estimate(len(self.items), total, self.current_page)
        self.status_label.setText("" if self.items else empty_message)
        self._render_cards()
        self._update_pagination()

    def show_external_results(
        self,
        items,
        total: int,
        page: int = 1,
        empty_message: str = "无搜索结果",
        page_loader: Callable[[int], None] | None = None,
    ) -> None:
        self._external_results_active = True
        self._external_empty_message = empty_message
        self._external_page_loader = page_loader
        self._external_loading = False
        self._sync_category_list_visibility()
        self._sync_search_controls_visibility()
        rendered_items = list(items)
        self.show_items(rendered_items, total, page=page, empty_message=empty_message)

    def clear_external_results(self) -> None:
        if not self._external_results_active:
            return
        self._external_results_active = False
        self._external_empty_message = "暂无内容"
        self._external_page_loader = None
        self._external_loading = False
        self._sync_category_list_visibility()
        self._sync_search_controls_visibility()
        if self.selected_category_id:
            self.current_page = 1
            self.load_items(self.selected_category_id, self.current_page)

    def _sync_category_list_visibility(self) -> None:
        self.category_list.setHidden(self._external_results_active)

    def _sync_search_controls_visibility(self) -> None:
        if self._search_controls_container is None:
            return
        self._search_controls_container.setHidden(self._external_results_active)

    def reset_folder_breadcrumbs_to_root(self) -> None:
        if not self._folder_navigation_enabled:
            return
        row = self.category_list.currentRow()
        if not (0 <= row < len(self.categories)):
            self._set_folder_breadcrumbs([])
            return
        category = self.categories[row]
        self._set_folder_breadcrumbs(
            [
                {"id": "", "label": "首页", "kind": "home"},
                {"id": category.type_id, "label": category.type_name, "kind": "category"},
            ]
        )

    def push_folder_breadcrumb(self, breadcrumb_id: str, label: str) -> None:
        if not self._folder_navigation_enabled:
            return
        breadcrumbs = list(self._folder_breadcrumbs)
        breadcrumbs.append({"id": breadcrumb_id, "label": label, "kind": "folder"})
        self._set_folder_breadcrumbs(breadcrumbs)

    def trim_folder_breadcrumbs(self, index: int) -> None:
        if not self._folder_navigation_enabled:
            return
        self._set_folder_breadcrumbs(self._folder_breadcrumbs[: index + 1])

    def _set_folder_breadcrumbs(self, breadcrumbs: list[dict[str, str]]) -> None:
        self._folder_breadcrumbs = list(breadcrumbs)
        self._render_folder_breadcrumbs()

    def _render_folder_breadcrumbs(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            if item is None:
                continue
            widget = cast(QWidget | None, item.widget())
            if widget is not None:
                widget.deleteLater()
        self.breadcrumb_buttons = []
        self.breadcrumb_bar.setVisible(self._folder_navigation_enabled and bool(self._folder_breadcrumbs))
        if not self._folder_navigation_enabled:
            return
        for index, breadcrumb in enumerate(self._folder_breadcrumbs):
            if index > 0:
                self.breadcrumb_layout.addWidget(QLabel("/"))
            button = QPushButton(breadcrumb["label"])
            self._set_button_cursor(button)
            button.setFlat(True)
            button.clicked.connect(
                lambda _checked=False, current_index=index: self._handle_folder_breadcrumb_clicked(current_index)
            )
            self.breadcrumb_buttons.append(button)
            self.breadcrumb_layout.addWidget(button)
        self.breadcrumb_layout.addStretch(1)

    def _handle_folder_breadcrumb_clicked(self, index: int) -> None:
        if not (0 <= index < len(self._folder_breadcrumbs)):
            return
        breadcrumb = self._folder_breadcrumbs[index]
        self.folder_breadcrumb_requested.emit(breadcrumb["id"], breadcrumb["kind"], index)

    def _build_card_button(self, item) -> QToolButton:
        text = item.vod_name if not item.vod_remarks else f"{item.vod_name}\n{item.vod_remarks}"
        button = QToolButton()
        button.setText(text)
        button.setFixedSize(self._CARD_WIDTH, self._CARD_HEIGHT)
        button.setToolTip(item.vod_name)
        button.setIconSize(self._CARD_POSTER_SIZE)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._set_button_cursor(button)
        button.setStyleSheet("padding: 10px;")
        button.clicked.connect(lambda _checked=False, current_item=item: self._handle_card_clicked(current_item))
        return button

    def _handle_card_clicked(self, item) -> None:
        if self._click_action == "open":
            self.item_open_requested.emit(item)
            self.open_requested.emit(item.vod_id)
            return
        self.search_requested.emit(item.vod_name)

    def _start_card_poster_load(self, button: QToolButton, item) -> None:
        poster_source = item.vod_pic or ""
        image_url = normalize_poster_url(poster_source)
        if not image_url:
            return

        gen = self._poster_generation

        def load() -> None:
            self._poster_semaphore.acquire()
            try:
                image = load_local_poster_image(poster_source, self._CARD_POSTER_SIZE)
                if image is None:
                    image = load_remote_poster_image(image_url, self._CARD_POSTER_SIZE)
                if image is not None and self._is_widget_alive() and gen == self._poster_generation:
                    self._signals.poster_loaded.emit(button, image)
            finally:
                self._poster_semaphore.release()

        threading.Thread(target=load, daemon=True).start()

    def _handle_poster_loaded(self, button: QToolButton, image) -> None:
        if button not in self.card_buttons:
            return
        pixmap = QPixmap.fromImage(image)
        button.setIcon(QIcon(pixmap))
        button.setIconSize(self._CARD_POSTER_SIZE)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._deactivate_async_guard()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.filter_buttons:
            self._sync_filter_scroll_area_height()
        if self.card_buttons:
            self._relayout_cards()
