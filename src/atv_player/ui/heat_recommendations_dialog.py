from __future__ import annotations

import threading
from collections.abc import Iterable

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)
from atv_player.ui.theme import current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class _HeatRecommendationSignals(QObject):
    poster_loaded = Signal(object, object)


class HeatRecommendationsDialog(ThemedDialogBase, AsyncGuardMixin):
    item_clicked = Signal(object)

    _POSTER_SIZE = QSize(128, 182)
    _CARD_WIDTH = 160
    _CARD_HEIGHT = 268
    _COLUMNS = 5
    _MAX_ITEMS = 30

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(title="大家在看", parent=parent, resizable=True)
        self._init_async_guard()
        self._poster_generation = 0
        self._poster_semaphore = threading.BoundedSemaphore(value=6)
        self._card_buttons: list[QToolButton] = []
        self._item_buttons: dict[str, QToolButton] = {}
        self._signals = _HeatRecommendationSignals()
        self._connect_async_signal(self._signals.poster_loaded, self._handle_poster_loaded)

        self.status_label = QLabel("", self)
        self.status_label.setObjectName("heatRecommendationsStatusLabel")

        self.cards_widget = QWidget(self)
        self.cards_layout = QGridLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(14)
        self.cards_layout.setVerticalSpacing(16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.cards_widget)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(12)
        layout.addWidget(self.status_label)
        layout.addWidget(scroll, 1)
        self._window_chrome_content_layout.addLayout(layout)
        self.resize(920, 720)
        self._apply_theme()

    def set_loading(self) -> None:
        self._poster_generation += 1
        self.status_label.setText("加载中...")
        self._clear_layout(self.cards_layout)
        self._card_buttons = []
        self._item_buttons = {}

    def set_items(self, items: Iterable[object]) -> None:
        self._poster_generation += 1
        self._clear_layout(self.cards_layout)
        self._card_buttons = []
        self._item_buttons = {}

        normalized_items: list[object] = []
        for item in list(items)[: self._MAX_ITEMS]:
            if str(getattr(item, "title", "") or "").strip():
                normalized_items.append(item)

        if not normalized_items:
            self.status_label.setText("暂无推荐")
            return

        self.status_label.setText("")
        for index, item in enumerate(normalized_items):
            button = self._create_card_button(item)
            row = index // self._COLUMNS
            column = index % self._COLUMNS
            self.cards_layout.addWidget(button, row, column)
            self._card_buttons.append(button)
            self._item_buttons[str(getattr(item, "title", "") or "").strip()] = button
            self._start_poster_load(button, item, self._poster_generation)
        self.cards_layout.setColumnStretch(self._COLUMNS, 1)

    def item_titles(self) -> list[str]:
        return list(self._item_buttons.keys())

    def item_button(self, title: str) -> QToolButton:
        return self._item_buttons[title]

    def _create_card_button(self, item: object) -> QToolButton:
        title = str(getattr(item, "title", "") or "").strip()
        heat_text = self._heat_text(item)
        button = QToolButton(self.cards_widget)
        button.setObjectName("heatRecommendationCardButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(self._POSTER_SIZE)
        button.setFixedSize(self._CARD_WIDTH, self._CARD_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setText(f"{title}\n{heat_text}" if heat_text else title)
        tooltip_parts = [title]
        if heat_text:
            tooltip_parts.append(heat_text)
        reason = str(getattr(item, "reason", "") or "").strip()
        if reason:
            tooltip_parts.append(reason)
        button.setToolTip("\n".join(tooltip_parts))
        button.clicked.connect(lambda _checked=False, current_item=item: self._handle_item_clicked(current_item))
        button.setStyleSheet(self._card_button_qss())
        return button

    @staticmethod
    def _heat_text(item: object) -> str:
        heat_score = _float_attr(item, "heat_score")
        if heat_score > 0:
            return f"热度 {heat_score:.0f}"
        return ""

    def _start_poster_load(self, button: QToolButton, item: object, generation: int) -> None:
        poster_source = str(getattr(item, "poster", "") or "").strip()
        image_url = normalize_poster_url(poster_source)
        if not image_url:
            return

        def load() -> None:
            self._poster_semaphore.acquire()
            try:
                image = load_local_poster_image(poster_source, self._POSTER_SIZE)
                if image is None:
                    image = load_remote_poster_image(image_url, self._POSTER_SIZE)
                if image is not None and generation == self._poster_generation and self._can_deliver_async_result():
                    self._signals.poster_loaded.emit(button, image)
            finally:
                self._poster_semaphore.release()

        threading.Thread(target=load, daemon=True).start()

    def _handle_poster_loaded(self, button: QToolButton, image) -> None:
        if button not in self._card_buttons:
            return
        button.setIcon(QIcon(QPixmap.fromImage(image)))
        button.setIconSize(self._POSTER_SIZE)

    def _handle_item_clicked(self, item: object) -> None:
        self.hide()
        self.item_clicked.emit(item)

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self.setStyleSheet(
            f"""
            QLabel#heatRecommendationsStatusLabel {{
                color: {tokens.text_secondary};
                font-size: 13px;
            }}
            """
        )
        for button in self._card_buttons:
            button.setStyleSheet(self._card_button_qss())

    @staticmethod
    def _card_button_qss() -> str:
        tokens = current_tokens()
        return f"""
        QToolButton#heatRecommendationCardButton {{
            text-align: left;
            color: {tokens.text_primary};
            background: {tokens.panel_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 8px;
            padding: 10px;
            font-size: 13px;
            font-weight: 600;
        }}
        QToolButton#heatRecommendationCardButton:hover {{
            background: {tokens.panel_alt_bg};
            border-color: {tokens.input_hover_border};
        }}
        """

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


def _float_attr(item: object, name: str) -> float:
    try:
        return float(getattr(item, name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
