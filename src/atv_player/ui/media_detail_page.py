from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from atv_player.controllers.media_detail_controller import (
    MediaDetailView,
)
from atv_player.following_models import FollowingEpisode, FollowingSeason
from atv_player.metadata.discovery import DiscoveryItem
from atv_player.ui.detail_scaffold import MediaDetailScaffold, detail_scaffold_qss
from atv_player.ui.following_detail_page import (
    FollowingPersonCard,
    FollowingRelatedRecommendationCard,
    _clear_layout,
    _image_placeholder_qss,
)
from atv_player.ui.following_episode_browser import (
    FollowingEpisodeBrowser,
    build_episode_season_groups,
)


class MediaDetailPage(QWidget):
    back_requested = Signal()
    search_play_requested = Signal(object)
    add_following_requested = Signal(object)
    refresh_metadata_requested = Signal(object)
    related_open_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_view: MediaDetailView | None = None
        self.person_cards: list[FollowingPersonCard] = []
        self.related_cards: list[FollowingRelatedRecommendationCard] = []

        self.back_button = QPushButton("返回", self)
        self.search_play_button = QPushButton("搜索播放", self)
        self.add_following_button = QPushButton("加入追更", self)
        self.refresh_metadata_button = QPushButton("更新元数据", self)
        self.status_label = QLabel("", self)
        self.title_label = QLabel("", self)
        self.meta_label = QLabel("", self)
        self.rating_strip = QLabel("", self)
        self.overview_label = QLabel("", self)
        self.poster_carousel_label = QLabel("海报轮播", self)
        self.related_recommendation_status_label = QLabel("", self)

        self.episode_browser = FollowingEpisodeBrowser(initial_grid_columns=1, parent=self)
        self._cast_container = QWidget(self)
        self._cast_layout = QHBoxLayout(self._cast_container)
        self._cast_layout.setContentsMargins(0, 0, 0, 0)
        self._cast_layout.setSpacing(12)
        self._related_recommendation_container = QWidget(self)
        self._related_recommendation_layout = QHBoxLayout(self._related_recommendation_container)
        self._related_recommendation_layout.setContentsMargins(0, 0, 0, 0)
        self._related_recommendation_layout.setSpacing(12)

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
        self.rating_strip.setText(f"TMDB {view.rating}" if view.rating else "")
        self.overview_label.setText(view.overview or "暂无简介")
        self.poster_carousel_label.setText("海报轮播" if view.backdrop_url or view.poster_url else "暂无海报")
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

        self.poster_carousel_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_carousel_label.setMinimumSize(720, 405)
        self.poster_carousel_label.setStyleSheet(_image_placeholder_qss())
        self.title_label.setObjectName("followingDetailTitle")
        self.title_label.setWordWrap(True)
        self.meta_label.setWordWrap(True)
        self.rating_strip.setWordWrap(True)
        self.overview_label.setWordWrap(True)
        self.overview_label.setMinimumHeight(64)
        selectable_flags = Qt.TextInteractionFlag.TextSelectableByMouse
        self.title_label.setTextInteractionFlags(selectable_flags)
        self.meta_label.setTextInteractionFlags(selectable_flags)
        self.rating_strip.setTextInteractionFlags(selectable_flags)
        self.overview_label.setTextInteractionFlags(selectable_flags)

        action_row = QHBoxLayout()
        action_row.addWidget(self.back_button)
        action_row.addStretch(1)
        action_row.addWidget(self.search_play_button)
        action_row.addWidget(self.add_following_button)
        action_row.addWidget(self.refresh_metadata_button)

        self.episode_browser.season_list.setMaximumWidth(180)
        self.episode_browser.browser_frame.layout().setStretch(0, 0)
        self.episode_browser.browser_frame.layout().setStretch(1, 1)

        self.detail_scaffold = MediaDetailScaffold(
            self,
            action_row=action_row,
            status_label=self.status_label,
            title_label=self.title_label,
            meta_label=self.meta_label,
            rating_label=self.rating_strip,
            metadata_source_bar=None,
            playback_platform_section=None,
            overview_label=self.overview_label,
            extra_metadata_widgets=[],
            poster_carousel_label=self.poster_carousel_label,
            episode_widget=self.episode_browser,
            related_status_label=self.related_recommendation_status_label,
            related_container=self._related_recommendation_container,
            cast_container=self._cast_container,
        )
        self.metadata_panel = self.detail_scaffold.metadata_panel
        self.poster_carousel_panel = self.detail_scaffold.poster_carousel_panel
        self.top_section = self.detail_scaffold.top_section
        self.cast_scroll = self.detail_scaffold.cast_scroll
        self.related_recommendation_scroll = self.detail_scaffold.related_recommendation_scroll
        self.related_recommendation_section = self.detail_scaffold.related_recommendation_section
        self.episodes_section = self.detail_scaffold.episodes_section
        self.cast_section = self.detail_scaffold.cast_section
        self.page_scroll = self.detail_scaffold.page_scroll

    def _connect_actions(self) -> None:
        self.back_button.clicked.connect(self.back_requested.emit)
        self.search_play_button.clicked.connect(lambda: self._emit_view(self.search_play_requested))
        self.add_following_button.clicked.connect(lambda: self._emit_view(self.add_following_requested))
        self.refresh_metadata_button.clicked.connect(lambda: self._emit_view(self.refresh_metadata_requested))

    def _emit_view(self, signal) -> None:
        if self.current_view is not None:
            signal.emit(self.current_view)

    def _render_episodes(self, view: MediaDetailView) -> None:
        episodes = [
            FollowingEpisode(
                season_number=episode.season_number,
                episode_number=episode.episode_number,
                title=episode.title,
                air_date=episode.air_date,
                overview=episode.overview,
                still=episode.still_url,
            )
            for episode in view.episodes
        ]
        seasons = [
            FollowingSeason(
                season_number=_int_value(season.get("season_number")),
                title=str(season.get("name") or season.get("title") or "").strip(),
                overview=str(season.get("overview") or "").strip(),
                poster=str(season.get("poster_url") or season.get("poster_path") or "").strip(),
                air_date=str(season.get("air_date") or "").strip(),
                episode_count=_int_value(season.get("episode_count")),
                is_special=_int_value(season.get("season_number")) <= 0,
            )
            for season in view.seasons
            if isinstance(season, dict)
        ]
        fallback_season = episodes[0].season_number if episodes else 1
        groups = build_episode_season_groups(episodes, seasons=seasons, fallback_season=fallback_season)
        self.episode_browser.set_content(
            groups=groups,
            current_season_number=0,
            current_episode=0,
            selected_season_number=fallback_season,
            latest_episode=0,
            latest_season_number=fallback_season,
            next_episode=None,
        )
        self.episodes_section.setVisible(view.media_type != "movie")

    def _render_people(self, view: MediaDetailView) -> None:
        _clear_layout(self._cast_layout)
        self.person_cards = []
        for person in view.people:
            card = FollowingPersonCard(
                {
                    "name": person.name,
                    "role": person.role,
                    "avatar": person.profile_url,
                },
                self._cast_container,
            )
            self._cast_layout.addWidget(card)
            self.person_cards.append(card)
        self._cast_layout.addStretch(1)

    def _render_related(self, view: MediaDetailView) -> None:
        _clear_layout(self._related_recommendation_layout)
        self.related_cards = []
        if not view.related:
            self.related_recommendation_status_label.setText("暂无关联推荐")
            self.related_recommendation_scroll.hide()
            return
        self.related_recommendation_status_label.setText("")
        self.related_recommendation_scroll.show()
        for item in view.related:
            discovery_item = DiscoveryItem(
                provider="tmdb",
                provider_id=f"{item.identity.media_type}:{item.identity.tmdb_id}",
                tmdb_id=item.identity.tmdb_id,
                media_type=item.identity.media_type,
                title=item.identity.title,
                year=item.year,
                poster=item.poster_url,
                rating=item.rating,
            )
            card = FollowingRelatedRecommendationCard(discovery_item, self._related_recommendation_container)
            card.activated.connect(
                lambda _item, identity=item.identity: self.related_open_requested.emit(identity)
            )
            self._related_recommendation_layout.addWidget(card)
            self.related_cards.append(card)
        self._related_recommendation_layout.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(detail_scaffold_qss())


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
