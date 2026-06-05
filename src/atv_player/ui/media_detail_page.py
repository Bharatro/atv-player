from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.controllers.media_detail_controller import (
    MediaDetailIdentity,
    MediaDetailView,
)
from atv_player.ui.theme import current_tokens


class MediaDetailPage(QWidget):
    back_requested = Signal()
    search_play_requested = Signal(object)
    add_following_requested = Signal(object)
    refresh_metadata_requested = Signal(object)
    related_open_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_view: MediaDetailView | None = None
        self.episode_buttons: list[QToolButton] = []
        self.person_labels: list[QLabel] = []
        self.related_buttons: list[QToolButton] = []

        self.back_button = QPushButton("返回", self)
        self.search_play_button = QPushButton("搜索播放", self)
        self.add_following_button = QPushButton("加入追更", self)
        self.refresh_metadata_button = QPushButton("更新元数据", self)
        self.status_label = QLabel("", self)
        self.title_label = QLabel("", self)
        self.meta_label = QLabel("", self)
        self.rating_label = QLabel("", self)
        self.overview_label = QLabel("", self)
        self.poster_label = QLabel("封面", self)
        self.backdrop_label = QLabel("背景", self)

        self.episodes_section = QFrame(self)
        self.episodes_layout = QVBoxLayout(self.episodes_section)
        self.people_section = QFrame(self)
        self.people_layout = QHBoxLayout()
        self.related_section = QFrame(self)
        self.related_layout = QHBoxLayout()

        self._build_layout()
        self._connect_actions()
        self._apply_style()

    def load_view(self, view: MediaDetailView) -> None:
        self.current_view = view
        self.status_label.setText("")
        self.title_label.setText(view.title)
        meta_parts = [
            "电影" if view.media_type == "movie" else "剧集",
            view.release_date or view.year,
            " / ".join(view.genres),
        ]
        self.meta_label.setText(" · ".join(part for part in meta_parts if part))
        self.rating_label.setText(f"TMDB {view.rating}" if view.rating else "")
        self.overview_label.setText(view.overview or "暂无简介")
        self.poster_label.setText("封面" if not view.poster_url else "")
        self.backdrop_label.setText("背景" if not view.backdrop_url else "")
        self._render_episodes(view)
        self._render_people(view)
        self._render_related(view)

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))

    def _build_layout(self) -> None:
        for button in (
            self.back_button,
            self.search_play_button,
            self.add_following_button,
            self.refresh_metadata_button,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.title_label.setObjectName("mediaDetailTitle")
        self.title_label.setWordWrap(True)
        self.meta_label.setWordWrap(True)
        self.rating_label.setWordWrap(True)
        self.overview_label.setWordWrap(True)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setMinimumSize(180, 260)
        self.backdrop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.backdrop_label.setMinimumHeight(220)

        action_row = QHBoxLayout()
        action_row.addWidget(self.back_button)
        action_row.addStretch(1)
        action_row.addWidget(self.search_play_button)
        action_row.addWidget(self.add_following_button)
        action_row.addWidget(self.refresh_metadata_button)

        metadata_panel = QFrame(self)
        metadata_panel.setObjectName("mediaDetailMetadataPanel")
        metadata_layout = QVBoxLayout(metadata_panel)
        metadata_layout.setContentsMargins(18, 18, 18, 18)
        metadata_layout.setSpacing(10)
        metadata_layout.addLayout(action_row)
        metadata_layout.addWidget(self.status_label)
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.meta_label)
        metadata_layout.addWidget(self.rating_label)
        metadata_layout.addWidget(self.overview_label, 1)

        top_row = QHBoxLayout()
        top_row.setSpacing(18)
        top_row.addWidget(metadata_panel, 3)
        top_row.addWidget(self.backdrop_label, 2)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(18)
        content_layout.addLayout(top_row)
        content_layout.addWidget(self._section_title("分集"))
        self.episodes_layout.setContentsMargins(14, 14, 14, 14)
        self.episodes_layout.setSpacing(8)
        content_layout.addWidget(self.episodes_section)
        content_layout.addWidget(self._section_title("演职员"))
        people_scroll = QScrollArea(self)
        people_scroll.setWidgetResizable(True)
        people_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        people_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        people_container = QWidget(self)
        people_container.setLayout(self.people_layout)
        self.people_layout.setContentsMargins(0, 0, 0, 0)
        self.people_layout.setSpacing(10)
        people_scroll.setWidget(people_container)
        people_scroll.setMinimumHeight(110)
        content_layout.addWidget(people_scroll)
        content_layout.addWidget(self._section_title("关联推荐"))
        related_scroll = QScrollArea(self)
        related_scroll.setWidgetResizable(True)
        related_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        related_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        related_container = QWidget(self)
        related_container.setLayout(self.related_layout)
        self.related_layout.setContentsMargins(0, 0, 0, 0)
        self.related_layout.setSpacing(10)
        related_scroll.setWidget(related_container)
        related_scroll.setMinimumHeight(170)
        content_layout.addWidget(related_scroll)
        content_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _connect_actions(self) -> None:
        self.back_button.clicked.connect(self.back_requested.emit)
        self.search_play_button.clicked.connect(lambda: self._emit_view(self.search_play_requested))
        self.add_following_button.clicked.connect(lambda: self._emit_view(self.add_following_requested))
        self.refresh_metadata_button.clicked.connect(lambda: self._emit_view(self.refresh_metadata_requested))

    def _emit_view(self, signal) -> None:
        if self.current_view is not None:
            signal.emit(self.current_view)

    def _render_episodes(self, view: MediaDetailView) -> None:
        self._clear_layout(self.episodes_layout)
        self.episode_buttons = []
        if not view.episodes:
            label = QLabel("暂无分集信息", self.episodes_section)
            self.episodes_layout.addWidget(label)
            return
        for episode in view.episodes:
            button = QToolButton(self.episodes_section)
            button.setText(
                f"{episode.display_title}\n{episode.air_date}" if episode.air_date else episode.display_title
            )
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.episode_buttons.append(button)
            self.episodes_layout.addWidget(button)
        self.episodes_layout.addStretch(1)

    def _render_people(self, view: MediaDetailView) -> None:
        self._clear_layout(self.people_layout)
        self.person_labels = []
        if not view.people:
            label = QLabel("暂无演职员信息", self)
            self.person_labels.append(label)
            self.people_layout.addWidget(label)
            return
        for person in view.people:
            label = QLabel(f"{person.name}\n{person.role}" if person.role else person.name, self)
            label.setObjectName("mediaDetailPersonLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            label.setWordWrap(True)
            label.setFixedWidth(150)
            self.person_labels.append(label)
            self.people_layout.addWidget(label)
        self.people_layout.addStretch(1)

    def _render_related(self, view: MediaDetailView) -> None:
        self._clear_layout(self.related_layout)
        self.related_buttons = []
        if not view.related:
            label = QLabel("暂无关联推荐", self)
            self.related_layout.addWidget(label)
            return
        for item in view.related:
            button = QToolButton(self)
            details = " · ".join(part for part in (item.year, item.rating) if part)
            button.setText(f"{item.identity.title}\n{details}" if details else item.identity.title)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setFixedSize(150, 120)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, identity=item.identity: self.related_open_requested.emit(identity)
            )
            self.related_buttons.append(button)
            self.related_layout.addWidget(button)
        self.related_layout.addStretch(1)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("mediaDetailSectionTitle")
        return label

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _apply_style(self) -> None:
        tokens = current_tokens()
        self.setStyleSheet(
            f"""
            QLabel#mediaDetailTitle {{
                color: {tokens.text_primary};
                font-size: 26px;
                font-weight: 700;
            }}
            QLabel#mediaDetailSectionTitle {{
                color: {tokens.text_primary};
                font-size: 18px;
                font-weight: 600;
            }}
            QLabel#mediaDetailPersonLabel {{
                color: {tokens.text_primary};
                background: {tokens.panel_bg};
                border: 1px solid {tokens.border_subtle};
                border-radius: 8px;
                padding: 10px;
            }}
            QFrame#mediaDetailMetadataPanel,
            QFrame#mediaDetailEpisodesSection {{
                background: {tokens.panel_bg};
                border: 1px solid {tokens.border_subtle};
                border-radius: 8px;
            }}
            """
        )
