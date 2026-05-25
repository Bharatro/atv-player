from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
)
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.theme import current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class FollowingEpisodePreviewDialog(ThemedDialogBase):
    def __init__(
        self, episode: FollowingEpisode, parent: QWidget | None = None
    ) -> None:
        title = _episode_title(episode)
        super().__init__(title=title, parent=parent, resizable=True)
        self.episode = episode

        layout = self.content_layout()
        self.still_label = QLabel("分集封面", self)
        self.still_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still_label.setFixedHeight(180)
        self.still_label.setStyleSheet(_image_placeholder_qss())
        self.title_label = QLabel(title, self)
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel(episode.air_date, self)
        self.overview_label = QLabel(episode.overview or "暂无剧情概要", self)
        self.overview_label.setWordWrap(True)

        layout.addWidget(self.still_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.overview_label)


class FollowingEpisodeCard(QPushButton):
    def __init__(
        self, episode: FollowingEpisode, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.episode = episode
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(240, 220)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.still_label = QLabel("分集封面", self)
        self.still_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still_label.setFixedSize(210, 92)
        self.still_label.setStyleSheet(_image_placeholder_qss())
        self.title_label = QLabel(_episode_title(episode), self)
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel(
            episode.air_date or f"第 {episode.episode_number} 集", self
        )
        self.overview_label = QLabel(episode.overview or "暂无剧情概要", self)
        self.overview_label.setWordWrap(True)

        layout.addWidget(self.still_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.overview_label, 1)
        self.setStyleSheet(_card_qss())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            FollowingEpisodePreviewDialog(self.episode, self).exec()
        super().mouseReleaseEvent(event)


class FollowingPersonCard(QFrame):
    def __init__(
        self, person: dict[str, object], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.person = person
        self.setMinimumSize(150, 180)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.avatar_label = QLabel("头像", self)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(96, 96)
        self.avatar_label.setStyleSheet(_image_placeholder_qss())
        self.name_label = QLabel(str(person.get("name") or ""), self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        role = (
            person.get("role")
            or person.get("character")
            or person.get("job")
            or person.get("known_for_department")
            or ""
        )
        self.role_label = QLabel(str(role), self)
        self.role_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.role_label.setWordWrap(True)

        layout.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.role_label)
        layout.addStretch(1)
        self.setStyleSheet(_frame_card_qss())


class FollowingDetailPage(QWidget, AsyncGuardMixin):
    back_requested = Signal()
    search_play_requested = Signal(int)
    unfollow_requested = Signal(int)

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self.current_following_id = 0
        self.current_view = None
        self.episode_widgets: list[FollowingEpisodeCard] = []
        self.cast_widgets: list[FollowingPersonCard] = []

        self.back_button = QPushButton("返回")
        self.backdrop_label = QLabel("海报背景")
        self.poster_label = QLabel("封面")
        self.title_label = QLabel()
        self.meta_label = QLabel()
        self.overview_label = QLabel()
        self.search_play_button = QPushButton("搜索播放")
        self.manual_check_button = QPushButton("手动检查")
        self.mark_latest_button = QPushButton("标记追到最新")
        self.unfollow_button = QPushButton("取消追更")
        self.season_tabs = QTabBar()

        self._episodes_container = QWidget()
        self._episodes_layout = QHBoxLayout(self._episodes_container)
        self._episodes_layout.setContentsMargins(0, 0, 0, 0)
        self._episodes_layout.setSpacing(12)
        self._cast_container = QWidget()
        self._cast_layout = QHBoxLayout(self._cast_container)
        self._cast_layout.setContentsMargins(0, 0, 0, 0)
        self._cast_layout.setSpacing(12)

        self._build_layout()
        self._connect_actions()
        self._apply_style()

    def load_record(self, following_id: int) -> None:
        self.current_following_id = int(following_id)
        self.current_view = self.controller.load_detail(self.current_following_id)
        self._render(self.current_view.record, self.current_view.snapshot)

    def _build_layout(self) -> None:
        self.backdrop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.backdrop_label.setMinimumHeight(140)
        self.backdrop_label.setStyleSheet(_image_placeholder_qss())
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(132, 186)
        self.poster_label.setStyleSheet(_image_placeholder_qss())
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("followingDetailTitle")
        self.meta_label.setWordWrap(True)
        self.overview_label.setWordWrap(True)
        self.overview_label.setMinimumHeight(64)

        action_row = QHBoxLayout()
        action_row.addWidget(self.back_button)
        action_row.addStretch(1)
        action_row.addWidget(self.search_play_button)
        action_row.addWidget(self.manual_check_button)
        action_row.addWidget(self.mark_latest_button)
        action_row.addWidget(self.unfollow_button)

        hero_info = QVBoxLayout()
        hero_info.addWidget(self.title_label)
        hero_info.addWidget(self.meta_label)
        hero_info.addWidget(self.overview_label)
        hero_info.addStretch(1)

        hero_row = QHBoxLayout()
        hero_row.addWidget(self.poster_label)
        hero_row.addLayout(hero_info, 1)

        self.episodes_scroll = QScrollArea()
        self.episodes_scroll.setWidgetResizable(True)
        self.episodes_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.episodes_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.episodes_scroll.setWidget(self._episodes_container)

        self.cast_scroll = QScrollArea()
        self.cast_scroll.setWidgetResizable(True)
        self.cast_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cast_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cast_scroll.setWidget(self._cast_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addLayout(action_row)
        layout.addWidget(self.backdrop_label)
        layout.addLayout(hero_row)
        layout.addWidget(QLabel("分集剧情", self))
        layout.addWidget(self.season_tabs)
        layout.addWidget(self.episodes_scroll, 1)
        layout.addWidget(QLabel("演职员", self))
        layout.addWidget(self.cast_scroll)

    def _connect_actions(self) -> None:
        self.back_button.clicked.connect(self.back_requested.emit)
        self.search_play_button.clicked.connect(self._emit_search_play)
        self.manual_check_button.clicked.connect(self._manual_check)
        self.mark_latest_button.clicked.connect(self._mark_watched_latest)
        self.unfollow_button.clicked.connect(self._emit_unfollow)

    def _render(
        self, record: FollowingRecord, snapshot: FollowingDetailSnapshot
    ) -> None:
        self.title_label.setText(record.title)
        self.meta_label.setText(_meta_text(record))
        self.overview_label.setText(snapshot.overview or "暂无简介")
        self.poster_label.setText("封面" if record.poster else "暂无封面")
        has_backdrop = bool(record.backdrop or snapshot.backdrops)
        backdrop_text = "海报背景" if has_backdrop else "暂无海报"
        self.backdrop_label.setText(backdrop_text)
        self._render_seasons(snapshot.episodes, record.season_number)
        self._render_episodes(snapshot.episodes)
        self._render_people(snapshot.cast, snapshot.crew)

    def _render_seasons(
        self, episodes: list[FollowingEpisode], fallback_season: int
    ) -> None:
        while self.season_tabs.count():
            self.season_tabs.removeTab(0)
        seasons = sorted(
            {episode.season_number for episode in episodes if episode.season_number > 0}
        )
        if not seasons and fallback_season > 0:
            seasons = [fallback_season]
        if not seasons:
            seasons = [1]
        for season in seasons:
            self.season_tabs.addTab(f"第 {season} 季")

    def _render_episodes(self, episodes: list[FollowingEpisode]) -> None:
        self.episode_widgets = []
        _clear_layout(self._episodes_layout)
        for episode in episodes:
            card = FollowingEpisodeCard(episode, self._episodes_container)
            self._episodes_layout.addWidget(card)
            self.episode_widgets.append(card)
        self._episodes_layout.addStretch(1)

    def _render_people(
        self, cast: list[dict[str, object]], crew: list[dict[str, object]]
    ) -> None:
        self.cast_widgets = []
        _clear_layout(self._cast_layout)
        for person in [*cast, *crew]:
            card = FollowingPersonCard(person, self._cast_container)
            self._cast_layout.addWidget(card)
            self.cast_widgets.append(card)
        self._cast_layout.addStretch(1)

    def _emit_search_play(self) -> None:
        self.search_play_requested.emit(self.current_following_id)

    def _emit_unfollow(self) -> None:
        self.unfollow_requested.emit(self.current_following_id)

    def _manual_check(self) -> None:
        if self.current_following_id <= 0:
            return
        self.controller.check_one(self.current_following_id)
        self.load_record(self.current_following_id)

    def _mark_watched_latest(self) -> None:
        if self.current_following_id <= 0:
            return
        self.controller.mark_watched_latest(self.current_following_id)
        self.load_record(self.current_following_id)

    def _apply_style(self) -> None:
        tokens = current_tokens()
        self.setStyleSheet(
            f"""
            QWidget {{
                color: {tokens.text_primary};
            }}
            QLabel#followingDetailTitle {{
                font-size: 26px;
                font-weight: 700;
            }}
            QPushButton {{
                border: 1px solid {tokens.border_subtle};
                border-radius: 12px;
                background: {tokens.button_bg};
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                border-color: {tokens.accent};
            }}
            QScrollArea {{
                border: 0;
                background: transparent;
            }}
            """
        )


def _clear_layout(layout: QHBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _episode_title(episode: FollowingEpisode) -> str:
    title = episode.title.strip() or "未命名"
    return f"{episode.episode_number}. {title}"


def _meta_text(record: FollowingRecord) -> str:
    episode_parts = []
    if record.current_episode > 0:
        episode_parts.append(f"看到 {record.current_episode}")
    if record.latest_episode > 0 and record.total_episodes > 0:
        episode_parts.append(f"最新 {record.latest_episode} / 总 {record.total_episodes}")
    elif record.latest_episode > 0:
        episode_parts.append(f"最新 {record.latest_episode}")
    elif record.total_episodes > 0:
        episode_parts.append(f"总 {record.total_episodes}")
    parts = [
        f"评分 {record.rating}" if record.rating else "",
        record.provider,
        *episode_parts,
        "有更新" if record.has_update else "暂无更新",
    ]
    return " · ".join(part for part in parts if part)


def _image_placeholder_qss() -> str:
    tokens = current_tokens()
    return (
        f"border: 1px solid {tokens.border_subtle};"
        "border-radius: 12px;"
        f"background: {tokens.panel_alt_bg};"
        f"color: {tokens.text_secondary};"
    )


def _card_qss() -> str:
    tokens = current_tokens()
    return (
        "QPushButton {"
        f"border: 1px solid {tokens.border_subtle};"
        "border-radius: 14px;"
        f"background: {tokens.panel_bg};"
        "text-align: left;"
        "}"
        "QPushButton:hover {"
        f"border-color: {tokens.accent};"
        "}"
    )


def _frame_card_qss() -> str:
    tokens = current_tokens()
    return (
        "QFrame {"
        f"border: 1px solid {tokens.border_subtle};"
        "border-radius: 14px;"
        f"background: {tokens.panel_bg};"
        "}"
    )
