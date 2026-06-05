from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import VodItem
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)
from atv_player.ui.theme import (
    build_pill_button_qss,
    build_search_line_edit_qss,
    current_tokens,
)


class _SimplifiedHomeSignals(QObject):
    hotwords_loaded = Signal(int, object)
    recommendations_loaded = Signal(int, object)
    poster_loaded = Signal(object, object)


class SimplifiedHomePage(QWidget, AsyncGuardMixin):
    search_requested = Signal(str)

    _MAX_HOTWORDS = 18
    _MAX_RECOMMENDATIONS = 18
    _CARD_MIN_WIDTH = 142
    _CARD_HEIGHT = 248
    _CARD_POSTER_SIZE = QSize(118, 168)

    def __init__(
        self,
        *,
        hotword_loader: Callable[[], list[dict[str, str]]] | None = None,
        recommendation_loader: Callable[[], list[VodItem]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_async_guard()
        self._hotword_loader = hotword_loader
        self._recommendation_loader = recommendation_loader
        self._hotwords_request_id = 0
        self._recommendations_request_id = 0
        self._hotwords: list[dict[str, str]] = []
        self._recommendations: list[VodItem] = []
        self.hotword_buttons: list[QPushButton] = []
        self.recommendation_buttons: list[QToolButton] = []
        self._recommendation_columns = 0
        self._poster_generation = 0
        self._poster_semaphore = threading.BoundedSemaphore(value=6)

        self._signals = _SimplifiedHomeSignals()
        self._connect_async_signal(
            self._signals.hotwords_loaded,
            self._handle_hotwords_loaded,
        )
        self._connect_async_signal(
            self._signals.recommendations_loaded,
            self._handle_recommendations_loaded,
        )
        self._connect_async_signal(
            self._signals.poster_loaded,
            self._handle_poster_loaded,
        )

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("simplifiedSearchEdit")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("搜索影片、剧集或资源链接")
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("simplifiedSearchButton")
        self.search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_button.setEnabled(False)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(10)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)

        self.hotwords_title = QLabel("热搜词")
        self.hotwords_title.setObjectName("simplifiedSectionTitle")
        self.hotwords_status_label = QLabel("")
        self.hotwords_status_label.setObjectName("simplifiedMutedLabel")
        self.hotwords_grid = QGridLayout()
        self.hotwords_grid.setContentsMargins(0, 0, 0, 0)
        self.hotwords_grid.setHorizontalSpacing(8)
        self.hotwords_grid.setVerticalSpacing(8)

        self.recommendations_title = QLabel("热门推荐")
        self.recommendations_title.setObjectName("simplifiedSectionTitle")
        self.recommendations_status_label = QLabel("")
        self.recommendations_status_label.setObjectName("simplifiedMutedLabel")
        self.recommendations_widget = QWidget()
        self.recommendations_grid = QGridLayout(self.recommendations_widget)
        self.recommendations_grid.setContentsMargins(0, 0, 0, 0)
        self.recommendations_grid.setHorizontalSpacing(14)
        self.recommendations_grid.setVerticalSpacing(14)
        self.recommendations_scroll = QScrollArea()
        self.recommendations_scroll.setWidgetResizable(True)
        self.recommendations_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recommendations_scroll.setWidget(self.recommendations_widget)

        self.content_container = QWidget()
        self.content_container.setMaximumWidth(1120)
        self.content_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(28, 44, 28, 28)
        content_layout.setSpacing(18)
        content_layout.addLayout(search_row)
        content_layout.addSpacing(8)
        content_layout.addWidget(self.hotwords_title)
        content_layout.addWidget(self.hotwords_status_label)
        content_layout.addLayout(self.hotwords_grid)
        content_layout.addSpacing(14)
        content_layout.addWidget(self.recommendations_title)
        content_layout.addWidget(self.recommendations_status_label)
        content_layout.addWidget(self.recommendations_scroll, 1)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)
        outer_layout.addWidget(self.content_container, 100)
        outer_layout.addStretch(1)

        self.search_edit.textChanged.connect(self._sync_search_button)
        self.search_edit.returnPressed.connect(self._submit_search)
        self.search_button.clicked.connect(self._submit_search)
        self._apply_theme()

    def refresh_content(self) -> None:
        self.refresh_hotwords()
        self.refresh_recommendations()

    def refresh_hotwords(self) -> None:
        self._hotwords_request_id += 1
        request_id = self._hotwords_request_id
        self.hotwords_status_label.setText("加载中...")
        loader = self._hotword_loader
        if loader is None:
            self.set_hotwords([])
            return

        def run() -> None:
            try:
                items = loader()
            except Exception:
                items = []
            if self._can_deliver_async_result():
                self._signals.hotwords_loaded.emit(request_id, items)

        threading.Thread(target=run, daemon=True).start()

    def refresh_recommendations(self) -> None:
        self._recommendations_request_id += 1
        request_id = self._recommendations_request_id
        self.recommendations_status_label.setText("加载中...")
        loader = self._recommendation_loader
        if loader is None:
            self.set_recommendations([])
            return

        def run() -> None:
            try:
                items = loader()
            except Exception:
                items = []
            if self._can_deliver_async_result():
                self._signals.recommendations_loaded.emit(request_id, items)

        threading.Thread(target=run, daemon=True).start()

    def set_hotwords(self, hotwords: list[dict[str, str]]) -> None:
        normalized: list[dict[str, str]] = []
        for item in hotwords:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            query = str(item.get("query") or title).strip()
            if title and query:
                normalized.append({"title": title, "query": query})
        self._hotwords = normalized[: self._MAX_HOTWORDS]
        self._render_hotwords()

    def set_recommendations(self, recommendations: list[VodItem]) -> None:
        self._recommendations = list(recommendations)[: self._MAX_RECOMMENDATIONS]
        self._render_recommendations()

    def _handle_hotwords_loaded(self, request_id: int, items: object) -> None:
        if request_id != self._hotwords_request_id:
            return
        self.set_hotwords(items if isinstance(items, list) else [])

    def _handle_recommendations_loaded(self, request_id: int, items: object) -> None:
        if request_id != self._recommendations_request_id:
            return
        self.set_recommendations(items if isinstance(items, list) else [])

    def _render_hotwords(self) -> None:
        self._clear_grid(self.hotwords_grid)
        self.hotword_buttons = []
        if not self._hotwords:
            self.hotwords_status_label.setText("暂无热搜词")
            return
        self.hotwords_status_label.setText("")
        for index, item in enumerate(self._hotwords):
            button = QPushButton(item["title"])
            button.setObjectName("simplifiedHotwordButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(32)
            button.setToolTip(item["title"])
            button.setStyleSheet(self._hotword_button_qss())
            button.clicked.connect(
                lambda checked=False, query=item["query"]: self._submit_keyword(query)
            )
            self.hotwords_grid.addWidget(button, index // 6, index % 6)
            self.hotword_buttons.append(button)
        for column in range(6):
            self.hotwords_grid.setColumnStretch(column, 1)

    def _render_recommendations(self) -> None:
        self._poster_generation += 1
        self._clear_grid(self.recommendations_grid)
        self.recommendation_buttons = []
        if not self._recommendations:
            self.recommendations_status_label.setText("暂无热门推荐")
            return
        self.recommendations_status_label.setText("")
        columns = self._recommendation_column_count()
        self._recommendation_columns = columns
        for index, item in enumerate(self._recommendations):
            button = self._create_recommendation_button(item)
            self._start_recommendation_poster_load(
                button,
                item,
                self._poster_generation,
            )
            self.recommendations_grid.addWidget(
                button,
                index // columns,
                index % columns,
            )
            self.recommendation_buttons.append(button)
        for column in range(columns):
            self.recommendations_grid.setColumnStretch(column, 1)

    def _create_recommendation_button(self, item: VodItem) -> QToolButton:
        title = str(getattr(item, "vod_name", "") or "").strip()
        remark = str(getattr(item, "vod_remarks", "") or "").strip()
        button = QToolButton()
        button.setObjectName("simplifiedRecommendationButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(self._CARD_POSTER_SIZE)
        button.setMinimumSize(self._CARD_MIN_WIDTH, self._CARD_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setText(f"{title}\n{remark}" if remark else title)
        button.setToolTip(title)
        button.setStyleSheet(self._recommendation_button_qss())
        button.clicked.connect(
            lambda checked=False, keyword=title: self._submit_keyword(keyword)
        )
        return button

    def _start_recommendation_poster_load(
        self,
        button: QToolButton,
        item: VodItem,
        generation: int,
    ) -> None:
        poster_source = str(getattr(item, "vod_pic", "") or "").strip()
        image_url = normalize_poster_url(poster_source)
        if not image_url:
            return

        def load() -> None:
            self._poster_semaphore.acquire()
            try:
                image = load_local_poster_image(poster_source, self._CARD_POSTER_SIZE)
                if image is None:
                    image = load_remote_poster_image(image_url, self._CARD_POSTER_SIZE)
                if (
                    image is not None
                    and self._can_deliver_async_result()
                    and generation == self._poster_generation
                ):
                    self._signals.poster_loaded.emit(button, image)
            finally:
                self._poster_semaphore.release()

        threading.Thread(target=load, daemon=True).start()

    def _handle_poster_loaded(self, button: QToolButton, image) -> None:
        if button not in self.recommendation_buttons:
            return
        pixmap = QPixmap.fromImage(image)
        button.setIcon(QIcon(pixmap))
        button.setIconSize(self._CARD_POSTER_SIZE)

    def _recommendation_column_count(self) -> int:
        width = max(
            self.recommendations_scroll.viewport().width(),
            self.content_container.width(),
        )
        return max(2, min(6, width // (self._CARD_MIN_WIDTH + 14)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = self._recommendation_column_count()
        if self._recommendations and columns != self._recommendation_columns:
            self._render_recommendations()

    def _submit_search(self) -> None:
        self._submit_keyword(self.search_edit.text())

    def _submit_keyword(self, keyword: str) -> None:
        normalized = str(keyword or "").strip()
        if not normalized:
            return
        self.search_edit.setText(normalized)
        self.search_requested.emit(normalized)

    def _sync_search_button(self) -> None:
        self.search_button.setEnabled(bool(self.search_edit.text().strip()))

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self.search_edit.setStyleSheet(
            build_search_line_edit_qss(tokens, border_radius=22, min_height=44)
        )
        self.search_button.setStyleSheet(
            f"""
            QPushButton#simplifiedSearchButton {{
                min-width: 82px;
                min-height: 44px;
                border-radius: 22px;
                padding: 0 18px;
                background: {tokens.button_primary_bg};
                color: {tokens.button_primary_text};
                border: 1px solid {tokens.button_primary_bg};
                font-weight: 600;
            }}
            QPushButton#simplifiedSearchButton:hover {{
                background: {tokens.accent_hover};
                border-color: {tokens.accent_hover};
            }}
            QPushButton#simplifiedSearchButton:disabled {{
                background: {tokens.button_disabled_bg};
                border-color: {tokens.button_disabled_border};
                color: {tokens.button_disabled_text};
            }}
            """
        )
        self.setStyleSheet(
            f"""
            QLabel#simplifiedSectionTitle {{
                color: {tokens.text_primary};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#simplifiedMutedLabel {{
                color: {tokens.text_secondary};
                font-size: 13px;
            }}
            """
        )
        for button in self.hotword_buttons:
            button.setStyleSheet(self._hotword_button_qss())
        for button in self.recommendation_buttons:
            button.setStyleSheet(self._recommendation_button_qss())

    @staticmethod
    def _hotword_button_qss() -> str:
        return build_pill_button_qss(
            current_tokens(),
            border_radius=16,
            horizontal_padding=12,
        )

    @staticmethod
    def _recommendation_button_qss() -> str:
        tokens = current_tokens()
        return f"""
        QToolButton#simplifiedRecommendationButton {{
            text-align: left;
            color: {tokens.text_primary};
            background: {tokens.panel_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 8px;
            padding: 14px;
            font-size: 14px;
            font-weight: 600;
        }}
        QToolButton#simplifiedRecommendationButton:hover {{
            background: {tokens.panel_alt_bg};
            border-color: {tokens.input_hover_border};
        }}
        """

    @staticmethod
    def _clear_grid(grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
