from __future__ import annotations

from datetime import datetime
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import FavoriteCardItem, FavoriteRecord
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.poster_grid_page import _FlowLayout
from atv_player.ui.poster_loader import load_local_poster_image, load_remote_poster_image, normalize_poster_url
from atv_player.ui.theme import FlatComboBox, build_search_line_edit_qss, current_tokens


class FavoriteCardButton(QPushButton):
    double_clicked = Signal(object)

    def __init__(self, item: FavoriteCardItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCheckable(True)
        self.setProperty("title_changed", item.updated_hint)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(220, 320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.poster_label = QLabel("封面", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(196, 220)
        layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignHCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        self.title_label = QLabel(item.display_title, self)
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label, 1)
        self.updated_icon = QLabel("●", self)
        self.updated_icon.setVisible(item.updated_hint)
        self.updated_icon.setStyleSheet("color: #ff9b6a;")
        title_row.addWidget(self.updated_icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        self.source_label = QLabel(item.source_label, self)
        self.secondary_label = QLabel(item.secondary_text, self)
        self.secondary_label.setWordWrap(True)
        self.secondary_label.setVisible(bool(item.secondary_text))
        self.time_label = QLabel(self._format_time(item.record.created_at), self)
        for label in (self.source_label, self.secondary_label, self.time_label):
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)
        self._apply_label_styles()
        self._apply_state_style()
        self.toggled.connect(lambda _checked: self._apply_state_style())

    def _format_time(self, timestamp: int) -> str:
        if timestamp <= 0:
            return ""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def _apply_state_style(self) -> None:
        tokens = current_tokens()
        border_color = tokens.border_subtle
        if self.property("title_changed"):
            border_color = tokens.accent_hover
        if self.isChecked():
            border_color = tokens.accent
        self.setStyleSheet(
            "QPushButton {"
            f"border: 1px solid {border_color};"
            "border-radius: 16px;"
            f"background: {tokens.panel_bg};"
            "text-align: left;"
            "}"
        )

    def _apply_label_styles(self) -> None:
        tokens = current_tokens()
        self.poster_label.setStyleSheet(
            "border: none;"
            "border-radius: 12px;"
            f"background: {tokens.panel_alt_bg};"
            f"color: {tokens.text_secondary};"
        )
        self.title_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_primary};"
            "font-weight: 700;"
        )
        for label in (self.source_label, self.secondary_label, self.time_label):
            label.setStyleSheet(
                "background: transparent;"
                f"color: {tokens.text_secondary};"
            )
        self.updated_icon.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.accent_hover};"
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.item.record)
        super().mouseDoubleClickEvent(event)


class FavoritesPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(object)
    poster_loaded = Signal(object, object)
    unauthorized = Signal()

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._initial_load_started = False
        self.current_page = 1
        self.page_size = 20
        self.total_items = 0
        self.records: list[FavoriteCardItem] = []
        self.card_widgets: list[FavoriteCardButton] = []

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(build_search_line_edit_qss(current_tokens()))
        self.refresh_button = QPushButton("刷新")
        self.delete_button = QPushButton("删除选中")
        self.clear_button = QPushButton("清空当前结果")
        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
        self.page_size_combo = FlatComboBox()
        for size in ("20", "30", "50", "100"):
            self.page_size_combo.addItem(size, int(size))

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(self.refresh_button)
        top_row.addWidget(self.delete_button)
        top_row.addWidget(self.clear_button)

        self.cards_container = QWidget()
        self.cards_layout = _FlowLayout(self.cards_container, spacing=16)
        self.cards_container.setLayout(self.cards_layout)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setWidget(self.cards_container)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.prev_page_button)
        bottom_row.addWidget(self.page_label)
        bottom_row.addWidget(self.next_page_button)
        bottom_row.addWidget(self.page_size_combo)

        content_container = QWidget()
        content_container.setMaximumWidth(1800)
        content_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(top_row)
        content_layout.addWidget(self.cards_scroll, 1)
        content_layout.addLayout(bottom_row)

        layout = QHBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(content_container, 100)
        layout.addStretch(1)

        self.refresh_button.clicked.connect(self.load_page)
        self.delete_button.clicked.connect(self.delete_selected)
        self.clear_button.clicked.connect(self.clear_current_results)
        self.prev_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.search_edit.returnPressed.connect(self._apply_search)
        self.page_size_combo.currentIndexChanged.connect(self._change_page_size)
        self._connect_async_signal(self.poster_loaded, self._handle_poster_loaded)
        self._sync_action_state()
        self._update_pagination_controls()

    def ensure_loaded(self) -> None:
        if self._initial_load_started:
            return
        self._initial_load_started = True
        self.load_page()

    def load_page(self) -> None:
        self._initial_load_started = True
        records, total = self.controller.load_page(
            page=self.current_page,
            size=self.page_size,
            keyword=self.search_edit.text().strip(),
        )
        self.total_items = total
        self._render_cards(records)
        self._update_pagination_controls()

    def _render_cards(self, items: list[FavoriteCardItem]) -> None:
        self.records = list(items)
        self.card_widgets = []
        while self.cards_layout.count():
            layout_item = self.cards_layout.takeAt(0)
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()
        for favorite in items:
            card = FavoriteCardButton(favorite, self.cards_container)
            card.clicked.connect(self._sync_action_state)
            card.clicked.connect(
                lambda _checked=False, current=favorite.record: self.open_detail_requested.emit(current)
            )
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)
            self._start_card_poster_load(card)
        self._sync_action_state()

    def _start_card_poster_load(self, card: FavoriteCardButton) -> None:
        poster_source = card.item.record.vod_pic or ""
        image_url = normalize_poster_url(poster_source)
        if not image_url:
            return
        target_size = QSize(card.poster_label.width(), card.poster_label.height())

        def load() -> None:
            image = load_local_poster_image(poster_source, target_size)
            if image is None:
                image = load_remote_poster_image(image_url, target_size)
            if image is not None and self._can_deliver_async_result():
                self.poster_loaded.emit(card, image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_poster_loaded(self, card: FavoriteCardButton, image) -> None:
        if card not in self.card_widgets:
            return
        card.poster_label.setText("")
        card.poster_label.setPixmap(QPixmap.fromImage(image))

    def _selected_records(self) -> list[FavoriteRecord]:
        return [card.item.record for card in self.card_widgets if card.isChecked()]

    def _confirm_delete_selected(self, count: int) -> bool:
        return (
            QMessageBox.question(
                self,
                "删除收藏",
                f"是否删除选中的 {count} 项收藏？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _confirm_clear_current_results(self, count: int) -> bool:
        return (
            QMessageBox.question(
                self,
                "清空收藏",
                f"是否删除当前结果中的 {count} 项收藏？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def delete_selected(self) -> None:
        records = self._selected_records()
        if not records or not self._confirm_delete_selected(len(records)):
            return
        self.controller.remove_favorite(records)
        self._reload_after_mutation()

    def clear_current_results(self) -> None:
        if not self.records or not self._confirm_clear_current_results(len(self.records)):
            return
        self.controller.clear_filtered(keyword=self.search_edit.text().strip())
        self.current_page = 1
        self.load_page()

    def _reload_after_mutation(self) -> None:
        if len(self.records) == len(self._selected_records()) and self.current_page > 1:
            self.current_page -= 1
        self.load_page()

    def _apply_search(self) -> None:
        self.current_page = 1
        self.load_page()

    def _change_page_size(self) -> None:
        page_size = self.page_size_combo.currentData()
        if page_size is None:
            return
        page_size = int(page_size)
        if page_size == self.page_size:
            return
        self.page_size = page_size
        self.current_page = 1
        self.load_page()

    def previous_page(self) -> None:
        if self.current_page <= 1:
            return
        self.current_page -= 1
        self.load_page()

    def next_page(self) -> None:
        if self.current_page >= self._total_pages():
            return
        self.current_page += 1
        self.load_page()

    def _total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)

    def _update_pagination_controls(self) -> None:
        total_pages = self._total_pages()
        self.page_label.setText(f"第 {self.current_page} / {total_pages} 页")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)

    def _sync_action_state(self) -> None:
        has_selection = any(card.isChecked() for card in self.card_widgets)
        self.delete_button.setEnabled(has_selection)
        self.clear_button.setEnabled(bool(self.records))
