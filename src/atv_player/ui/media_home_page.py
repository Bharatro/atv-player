from __future__ import annotations

import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
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


@dataclass(slots=True)
class MediaHomeCard:
    title: str
    subtitle: str = ""
    poster: str = ""
    payload: object | None = None


@dataclass(slots=True)
class MediaHomeSections:
    current_playing: MediaHomeCard | None = None
    continue_watching: list[MediaHomeCard] | None = None
    following: list[MediaHomeCard] | None = None
    favorites: list[MediaHomeCard] | None = None


class _MediaHomeSignals(QObject):
    loaded = Signal(int, object)
    poster_loaded = Signal(object, object)


class MediaHomePage(QWidget, AsyncGuardMixin):
    current_play_requested = Signal()
    continue_requested = Signal(object)
    following_requested = Signal(int)
    favorite_requested = Signal(object)

    _POSTER_SIZE = QSize(118, 168)
    _CARD_WIDTH = 150
    _CARD_HEIGHT = 238
    _MAX_ROW_ITEMS = 12

    def __init__(self, loader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_async_guard()
        self._loader = loader
        self._request_id = 0
        self._poster_generation = 0
        self._poster_semaphore = threading.BoundedSemaphore(value=6)
        self._card_buttons: list[QToolButton] = []
        self.current_playing_button: QToolButton | None = None
        self.continue_buttons: list[QToolButton] = []
        self.following_buttons: list[QToolButton] = []
        self.favorite_buttons: list[QToolButton] = []

        self._signals = _MediaHomeSignals()
        self._connect_async_signal(self._signals.loaded, self._handle_loaded)
        self._connect_async_signal(
            self._signals.poster_loaded,
            self._handle_poster_loaded,
        )

        self.status_label = QLabel("")
        self.status_label.setObjectName("mediaHomeStatusLabel")

        self.content_container = QWidget()
        self.content_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(18)
        self.content_layout.addWidget(self.status_label)

        self.current_section = QWidget()
        current_layout = QVBoxLayout(self.current_section)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(10)
        current_layout.addWidget(self._section_title("当前播放"))
        self.current_container = QWidget()
        self.current_container_layout = QVBoxLayout(self.current_container)
        self.current_container_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(self.current_container)
        self.content_layout.addWidget(self.current_section)

        self.continue_row, self.continue_layout = self._create_card_row("继续观看")
        self.following_row, self.following_layout = self._create_card_row("追剧列表")
        self.favorites_row, self.favorites_layout = self._create_card_row("收藏列表")
        self.content_layout.addWidget(self.continue_row)
        self.content_layout.addWidget(self.following_row)
        self.content_layout.addWidget(self.favorites_row)
        self.content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.content_container)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll, 1)
        self._apply_theme()

    def refresh_content(self) -> None:
        self._request_id += 1
        request_id = self._request_id
        self.status_label.setText("加载中...")

        def run() -> None:
            try:
                sections = self._loader()
            except Exception:
                sections = MediaHomeSections()
            if self._can_deliver_async_result():
                self._signals.loaded.emit(request_id, sections)

        threading.Thread(target=run, daemon=True).start()

    def set_sections(self, sections: MediaHomeSections) -> None:
        self._poster_generation += 1
        self._card_buttons = []
        self.status_label.setText("")
        self._render_current_playing(sections.current_playing)
        self.continue_buttons = self._render_card_row(
            self.continue_layout,
            list(sections.continue_watching or [])[: self._MAX_ROW_ITEMS],
            self.continue_requested.emit,
        )
        self.following_buttons = self._render_card_row(
            self.following_layout,
            list(sections.following or [])[: self._MAX_ROW_ITEMS],
            lambda payload: self.following_requested.emit(int(payload)),
        )
        self.favorite_buttons = self._render_card_row(
            self.favorites_layout,
            list(sections.favorites or [])[: self._MAX_ROW_ITEMS],
            self.favorite_requested.emit,
        )
        has_any = bool(
            sections.current_playing
            or self.continue_buttons
            or self.following_buttons
            or self.favorite_buttons
        )
        if not has_any:
            self.status_label.setText("暂无媒体内容")

    def _handle_loaded(self, request_id: int, sections: object) -> None:
        if request_id != self._request_id:
            return
        self.set_sections(
            sections if isinstance(sections, MediaHomeSections) else MediaHomeSections()
        )

    def _render_current_playing(self, card: MediaHomeCard | None) -> None:
        self._clear_layout(self.current_container_layout)
        self.current_playing_button = None
        if card is None:
            empty = QLabel("没有正在播放的内容", self.current_container)
            empty.setObjectName("mediaHomeEmptyLabel")
            self.current_container_layout.addWidget(empty)
            return
        button = self._create_card_button(
            card,
            lambda _payload=None: self.current_play_requested.emit(),
        )
        self._card_buttons.append(button)
        self._start_poster_load(button, card, self._poster_generation)
        self.current_container_layout.addWidget(
            button,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        self.current_playing_button = button

    def _render_card_row(
        self,
        layout: QHBoxLayout,
        cards: list[MediaHomeCard],
        opener,
    ) -> list[QToolButton]:
        self._clear_layout(layout)
        buttons: list[QToolButton] = []
        if not cards:
            empty = QLabel("暂无内容")
            empty.setObjectName("mediaHomeEmptyLabel")
            layout.addWidget(empty)
            layout.addStretch(1)
            return buttons
        for card in cards:
            button = self._create_card_button(card, opener)
            layout.addWidget(button)
            buttons.append(button)
            self._card_buttons.append(button)
            self._start_poster_load(button, card, self._poster_generation)
        layout.addStretch(1)
        return buttons

    def _create_card_button(self, card: MediaHomeCard, opener) -> QToolButton:
        button = QToolButton()
        button.setObjectName("mediaHomeCardButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(self._POSTER_SIZE)
        button.setFixedSize(self._CARD_WIDTH, self._CARD_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setText(
            f"{card.title}\n{card.subtitle}" if card.subtitle else card.title
        )
        button.setToolTip(
            f"{card.title}\n{card.subtitle}" if card.subtitle else card.title
        )
        button.clicked.connect(
            lambda _checked=False, payload=card.payload: opener(payload)
        )
        button.setStyleSheet(self._card_button_qss())
        return button

    def _start_poster_load(
        self,
        button: QToolButton,
        card: MediaHomeCard,
        generation: int,
    ) -> None:
        poster_source = str(card.poster or "").strip()
        image_url = normalize_poster_url(poster_source)
        if not image_url:
            return

        def load() -> None:
            self._poster_semaphore.acquire()
            try:
                image = load_local_poster_image(poster_source, self._POSTER_SIZE)
                if image is None:
                    image = load_remote_poster_image(image_url, self._POSTER_SIZE)
                if (
                    image is not None
                    and generation == self._poster_generation
                    and self._can_deliver_async_result()
                ):
                    self._signals.poster_loaded.emit(button, image)
            finally:
                self._poster_semaphore.release()

        threading.Thread(target=load, daemon=True).start()

    def _handle_poster_loaded(self, button: QToolButton, image) -> None:
        if button not in self._card_buttons:
            return
        button.setIcon(QIcon(QPixmap.fromImage(image)))
        button.setIconSize(self._POSTER_SIZE)

    def _create_card_row(self, title: str) -> tuple[QWidget, QHBoxLayout]:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(10)
        section_layout.addWidget(self._section_title(title))
        row_scroll = QScrollArea()
        row_scroll.setWidgetResizable(True)
        row_scroll.setFrameShape(QFrame.Shape.NoFrame)
        row_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        row_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(14)
        row_scroll.setWidget(row_widget)
        row_scroll.setFixedHeight(self._CARD_HEIGHT + 18)
        section_layout.addWidget(row_scroll)
        return section, row_layout

    @staticmethod
    def _section_title(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("mediaHomeSectionTitle")
        return label

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self.setStyleSheet(
            f"""
            QLabel#mediaHomeSectionTitle {{
                color: {tokens.text_primary};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#mediaHomeStatusLabel,
            QLabel#mediaHomeEmptyLabel {{
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
        QToolButton#mediaHomeCardButton {{
            text-align: left;
            color: {tokens.text_primary};
            background: {tokens.panel_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 8px;
            padding: 10px;
            font-size: 13px;
            font-weight: 600;
        }}
        QToolButton#mediaHomeCardButton:hover {{
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
