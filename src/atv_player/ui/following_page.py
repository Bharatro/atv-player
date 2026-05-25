from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
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
from atv_player.ui.theme import FlatComboBox, build_search_line_edit_qss, current_tokens


class FollowingCardButton(QPushButton):
    double_clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(230, 260)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setProperty("updated_hint", item.updated_hint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.poster_label = QLabel("封面", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(190, 120)
        self.poster_label.setStyleSheet("border-radius: 8px; background: rgba(255,255,255,0.08);")
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
        layout.addStretch(1)
        self._apply_style()

    def _apply_style(self) -> None:
        border = "#f2a67f" if self.item.updated_hint else "#d8cabc"
        self.setStyleSheet(
            "QPushButton {"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "background: rgba(255, 253, 250, 0.95);"
            "text-align: left;"
            "}"
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(int(self.item.record.id))
        super().mouseDoubleClickEvent(event)


class FollowingPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(int)

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

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.cards_scroll, 1)
        layout.addLayout(bottom_row)

        self.search_edit.returnPressed.connect(self._apply_search)
        self.only_updates_checkbox.toggled.connect(lambda _checked: self._apply_search())
        self.add_button.clicked.connect(self._open_add_dialog)
        self.check_updates_button.clicked.connect(self._check_updates)
        self.prev_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.page_size_combo.currentIndexChanged.connect(self._change_page_size)
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
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)

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

    def _total_pages(self) -> int:
        if self.total_items <= 0:
            return 1
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)

    def _update_pagination_controls(self) -> None:
        total_pages = self._total_pages()
        self.page_label.setText(f"第 {self.current_page} / {total_pages} 页")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)
