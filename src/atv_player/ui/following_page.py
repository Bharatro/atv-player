# ruff: noqa: E501
from __future__ import annotations

import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.following_search_dialog import FollowingSearchDialog
from atv_player.ui.poster_grid_page import _FlowLayout
from atv_player.ui.poster_loader import load_local_poster_image, load_remote_poster_image, normalize_poster_url
from atv_player.ui.theme import FlatComboBox, build_search_line_edit_qss, current_tokens


class FollowingCardButton(QPushButton):
    double_clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(220, 320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setProperty("updated_hint", item.updated_hint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.poster_label = QLabel("封面", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(196, 220)
        layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QLabel(item.display_title, self)
        self.title_label.setWordWrap(True)
        self.progress_label = QLabel(item.progress_text, self)
        self.update_label = QLabel(item.update_text, self)
        self.error_label = QLabel(item.error_text, self)
        self.error_label.setVisible(bool(item.error_text))
        for label in (self.title_label, self.progress_label, self.update_label, self.error_label):
            label.setWordWrap(True)
            layout.addWidget(label)
        self._apply_label_styles()
        self._apply_style()

    def _apply_style(self) -> None:
        tokens = current_tokens()
        border = tokens.accent_hover if self.item.updated_hint else tokens.border_subtle
        self.setStyleSheet(
            "QPushButton {"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            f"background: {tokens.panel_bg};"
            "text-align: left;"
            "}"
        )

    def _apply_label_styles(self) -> None:
        tokens = current_tokens()
        self.poster_label.setStyleSheet(
            "border: none;"
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )
        self.title_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_primary};"
            "font-weight: 700;"
        )
        self.progress_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )
        self.update_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.accent_hover if self.item.updated_hint else tokens.text_secondary};"
            "font-weight: 700;"
        )
        self.error_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.accent};"
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(int(self.item.record.id))
        super().mouseDoubleClickEvent(event)


class FollowingPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(int)
    poster_loaded = Signal(object, object)

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._initial_load_started = False
        self.current_page = 1
        self.page_size = 20
        self.total_items = 0
        self.records = []
        self.card_widgets: list[FollowingCardButton] = []

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索追更...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(build_search_line_edit_qss(current_tokens()))
        self.add_button = QPushButton("添加追更")
        self.check_updates_button = QPushButton("检查更新")
        self.only_updates_checkbox = QCheckBox("只看有更新")
        self.status_label = QLabel("没有追更记录")
        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
        self.page_size_combo = FlatComboBox()
        for size in ("20", "30", "50", "100"):
            self.page_size_combo.addItem(size, int(size))

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(self.only_updates_checkbox)
        top_row.addWidget(self.add_button)
        top_row.addWidget(self.check_updates_button)

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
        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.cards_scroll, 1)
        content_layout.addLayout(bottom_row)

        layout = QHBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(content_container, 100)
        layout.addStretch(1)

        self.search_edit.returnPressed.connect(self._apply_search)
        self.only_updates_checkbox.toggled.connect(lambda _checked: self._apply_search())
        self.add_button.clicked.connect(self._open_add_dialog)
        self.check_updates_button.clicked.connect(self._check_updates)
        self.prev_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.page_size_combo.currentIndexChanged.connect(self._change_page_size)
        self._connect_async_signal(self.poster_loaded, self._handle_poster_loaded)
        self._apply_status_style()
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
            only_updates=self.only_updates_checkbox.isChecked(),
        )
        self.total_items = total
        self._render_cards(records)
        self._update_status_label()
        self._update_pagination_controls()

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

    def _render_cards(self, items) -> None:
        self.records = list(items)
        self.card_widgets = []
        while self.cards_layout.count():
            layout_item = self.cards_layout.takeAt(0)
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()
        for item in self.records:
            card = FollowingCardButton(item, self.cards_container)
            card.double_clicked.connect(self.open_detail_requested.emit)
            card.clicked.connect(
                lambda _checked=False, current_id=item.record.id: self.open_detail_requested.emit(int(current_id))
            )
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)
            self._start_card_poster_load(card)

    def _start_card_poster_load(self, card: FollowingCardButton) -> None:
        poster_source = card.item.record.poster or ""
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

    def _handle_poster_loaded(self, card: FollowingCardButton, image) -> None:
        if card not in self.card_widgets:
            return
        card.poster_label.setText("")
        card.poster_label.setPixmap(QPixmap.fromImage(image))

    def _apply_search(self) -> None:
        self.current_page = 1
        self.load_page()

    def _change_page_size(self) -> None:
        page_size = self.page_size_combo.currentData()
        if page_size is None:
            return
        self.page_size = int(page_size)
        self.current_page = 1
        self.load_page()

    def _open_add_dialog(self) -> None:
        dialog = FollowingSearchDialog(self.controller, self)
        dialog.candidate_selected.connect(lambda _candidate: self.load_page())
        dialog.exec()

    def _check_updates(self) -> None:
        self.controller.check_all_due()
        self.load_page()
        self._update_status_label(prefix="已检查更新")

    def _apply_status_style(self) -> None:
        tokens = current_tokens()
        self.status_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )

    def _update_status_label(self, *, prefix: str = "") -> None:
        if self.total_items <= 0:
            message = "没有有更新的追更" if self.only_updates_checkbox.isChecked() else "没有追更记录"
        else:
            visible_count = len(self.records)
            updated_count = sum(
                1
                for item in self.records
                if bool(getattr(item, "updated_hint", False) or getattr(item.record, "has_update", False))
            )
            message = f"共 {self.total_items} 条，当前显示 {visible_count} 条，{updated_count} 条有更新"
        if prefix:
            message = f"{prefix} · {message}"
        self.status_label.setText(message)

    def _total_pages(self) -> int:
        if self.total_items <= 0:
            return 1
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)

    def _update_pagination_controls(self) -> None:
        total_pages = self._total_pages()
        self.page_label.setText(f"第 {self.current_page} / {total_pages} 页")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)
