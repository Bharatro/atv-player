from __future__ import annotations

import threading

import shiboken6
from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.controllers.media_detail_controller import (
    MediaDetailIdentity,
    MediaDetailRecommendation,
    MediaDetailView,
)
from atv_player.following_models import FollowingEpisode, FollowingSeason
from atv_player.metadata.discovery import DiscoveryItem
from atv_player.models import AppConfig
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.detail_scaffold import MediaDetailScaffold, detail_scaffold_qss
from atv_player.ui.following_detail_page import (
    FollowingEpisodePreviewDialog,
    FollowingPersonCard,
    FollowingRelatedRecommendationCard,
    _clear_layout,
    _carousel_image_qss,
    _format_merged_source_snapshot_text,
    _format_source_snapshot_text,
    _image_placeholder_qss,
    _playback_platforms_html,
    _person_inner_label_qss,
    _rating_strip_text,
    _unique_sources,
)
from atv_player.ui.following_episode_browser import (
    FollowingEpisodeBrowser,
    build_episode_season_groups,
)
from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)


class MediaDetailPage(AsyncGuardMixin, QWidget):
    back_requested = Signal()
    search_play_requested = Signal(object)
    add_following_requested = Signal(object)
    refresh_metadata_requested = Signal(object)
    related_open_requested = Signal(object)
    season_requested = Signal(object, int)
    image_loaded = Signal(QLabel, object)

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        save_config=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_async_guard()
        self._config = config or AppConfig()
        self._save_config = save_config
        self.current_view: MediaDetailView | None = None
        self._selected_season_number = 0
        self.person_cards: list[FollowingPersonCard] = []
        self.related_cards: list[FollowingRelatedRecommendationCard] = []
        self.metadata_source_buttons: list[QPushButton] = []
        self.playback_platform_widgets: list[QLabel] = []
        self._selected_metadata_source_key = "merged"

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
        self.metadata_source_bar = QWidget(self)
        self.metadata_source_layout = QHBoxLayout(self.metadata_source_bar)
        self.metadata_source_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_source_layout.setSpacing(8)
        self.playback_platform_section = QWidget(self)
        self.playback_platform_layout = QVBoxLayout(self.playback_platform_section)
        self.playback_platform_layout.setContentsMargins(0, 0, 0, 0)
        self.playback_platform_layout.setSpacing(8)

        self.episode_browser = FollowingEpisodeBrowser(
            initial_grid_columns=self._config.following_episode_grid_columns,
            parent=self,
        )
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
        self._selected_metadata_source_key = "merged"
        self.status_label.setText("")
        self.title_label.setText(view.title)
        meta_parts = [
            "电影" if view.media_type == "movie" else "剧集",
            view.release_date or view.year,
            " / ".join(view.genres),
        ]
        self.meta_label.setText(" · ".join(part for part in meta_parts if part))
        self._render_metadata_bundle(view)
        self._render_poster_carousel(view)
        self._render_episodes(view)
        self._render_people(view)
        self._render_related(view)

    def load_season_view(self, view: MediaDetailView, *, season_number: int) -> None:
        self.current_view = view
        self._selected_season_number = max(0, _int_value(season_number))
        self._render_episodes(view, selected_season_number=self._selected_season_number)
        self.status_label.setText("")

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
        self.poster_carousel_label.setStyleSheet(_carousel_image_qss())
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
        self.overview_label.setTextFormat(Qt.TextFormat.RichText)
        self.overview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.overview_label.setOpenExternalLinks(False)
        self.overview_label.linkActivated.connect(self._open_external_link)

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
            metadata_source_bar=self.metadata_source_bar,
            playback_platform_section=self.playback_platform_section,
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
        self._connect_async_signal(self.image_loaded, self._handle_image_loaded)
        self.episode_browser.episode_activated.connect(self._open_episode_preview)
        self.episode_browser.season_changed.connect(self._handle_season_changed)
        self.episode_browser.grid_columns_changed.connect(self._handle_episode_grid_columns_changed)

    def _emit_view(self, signal) -> None:
        if self.current_view is not None:
            signal.emit(self.current_view)

    def _render_poster_carousel(self, view: MediaDetailView) -> None:
        self.poster_carousel_label.clear()
        self.poster_carousel_label.setStyleSheet(_carousel_image_qss())
        sources = _unique_sources([view.backdrop_url, view.poster_url])
        self.poster_carousel_label.setText("海报轮播" if sources else "暂无海报")
        if sources:
            self._start_image_load(self.poster_carousel_label, sources[0])

    def _render_metadata_bundle(self, view: MediaDetailView) -> None:
        bundle = view.metadata_bundle
        if bundle is None:
            self.rating_strip.setText(f"TMDB {view.rating}" if view.rating else "")
            self._render_source_buttons(["merged"], source_snapshots={})
            self._render_playback_platforms([])
            self.overview_label.setText(view.overview or "暂无简介")
            return
        source_snapshots = dict(bundle.source_snapshots)
        current_key = (
            self._selected_metadata_source_key
            if self._selected_metadata_source_key in source_snapshots
            else bundle.default_source_key
        )
        self._selected_metadata_source_key = current_key
        current = bundle.merged_snapshot if current_key == "merged" else source_snapshots[current_key]
        self.rating_strip.setText(_rating_strip_text(bundle.merged_snapshot.ratings))
        self._render_source_buttons(bundle.available_source_keys, source_snapshots=source_snapshots)
        platforms = bundle.merged_snapshot.playback_platforms if current_key == "merged" else current.playback_platforms
        self._render_playback_platforms(platforms)
        record = _media_detail_record_for_links(view)
        if current_key == "merged":
            self.overview_label.setText(_format_merged_source_snapshot_text(bundle.merged_snapshot, record=record))
        else:
            self.overview_label.setText(_format_source_snapshot_text(current, record=record))

    def _render_source_buttons(self, source_keys: list[str], *, source_snapshots: dict[str, object]) -> None:
        _clear_layout(self.metadata_source_layout)
        self.metadata_source_buttons = []
        for source_key in source_keys:
            if source_key == "merged":
                label = "媒体信息"
            else:
                snapshot = source_snapshots.get(source_key)
                label = str(getattr(snapshot, "provider_label", "") or source_key)
            button = QPushButton(label, self.metadata_source_bar)
            button.setCheckable(True)
            button.setChecked(source_key == self._selected_metadata_source_key)
            button.clicked.connect(
                lambda _checked=False, target=source_key: self._handle_metadata_source_selected(target)
            )
            self.metadata_source_layout.addWidget(button)
            self.metadata_source_buttons.append(button)
        self.metadata_source_layout.addStretch(1)

    def _handle_metadata_source_selected(self, source_key: str) -> None:
        self._selected_metadata_source_key = str(source_key or "merged")
        if self.current_view is not None:
            self._render_metadata_bundle(self.current_view)

    def _render_playback_platforms(self, platforms: list[object]) -> None:
        _clear_layout(self.playback_platform_layout)
        self.playback_platform_widgets = []
        if not platforms:
            return
        label = QLabel(_playback_platforms_html(platforms), self.playback_platform_section)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._open_external_link)
        self.playback_platform_widgets.append(label)
        self.playback_platform_layout.addWidget(label)

    def _open_external_link(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(str(url or "")))

    def _render_episodes(self, view: MediaDetailView, *, selected_season_number: int | None = None) -> None:
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
        fallback_season = self._fallback_season_number(view, episodes)
        selected_season = selected_season_number if selected_season_number is not None else fallback_season
        self._selected_season_number = max(0, _int_value(selected_season))
        groups = build_episode_season_groups(episodes, seasons=seasons, fallback_season=fallback_season)
        self.episode_browser.set_content(
            groups=groups,
            current_season_number=0,
            current_episode=0,
            selected_season_number=self._selected_season_number,
            latest_episode=0,
            latest_season_number=fallback_season,
            next_episode=None,
        )
        self.episodes_section.setVisible(view.media_type != "movie")

    def _fallback_season_number(self, view: MediaDetailView, episodes: list[FollowingEpisode]) -> int:
        if episodes:
            return episodes[0].season_number or 1
        for season in view.seasons:
            if not isinstance(season, dict):
                continue
            season_number = _int_value(season.get("season_number"))
            if season_number > 0:
                return season_number
        return 1

    def _handle_season_changed(self, season_number: int) -> None:
        normalized = max(0, _int_value(season_number))
        if normalized <= 0 or self.current_view is None or self.current_view.media_type == "movie":
            return
        if normalized == self._selected_season_number and self._current_view_matches_season(normalized):
            return
        self._selected_season_number = normalized
        self.status_label.setText(f"正在加载第 {normalized} 季分集...")
        self.season_requested.emit(self.current_view, normalized)

    def _open_episode_preview(self, episode: FollowingEpisode) -> None:
        dialog = FollowingEpisodePreviewDialog(
            episode,
            status_text=self.episode_browser.status_text_for_episode(episode),
            can_mark_watched=False,
            parent=self,
        )
        dialog.exec()

    def _handle_episode_grid_columns_changed(self, columns: int) -> None:
        normalized = int(columns)
        if self._config.following_episode_grid_columns == normalized:
            return
        self._config.following_episode_grid_columns = normalized
        if callable(self._save_config):
            self._save_config()

    def _current_view_matches_season(self, season_number: int) -> bool:
        if self.current_view is None:
            return False
        return any(
            (episode.season_number or season_number) == season_number
            for episode in self.current_view.episodes
        )

    def _render_people(self, view: MediaDetailView) -> None:
        _clear_layout(self._cast_layout)
        self.person_cards = []
        for person in view.people:
            card = FollowingPersonCard(
                {
                    "name": person.name,
                    "role": person.role,
                    "avatar": person.profile_url,
                    "url": person.url,
                },
                self._cast_container,
            )
            self._cast_layout.addWidget(card)
            self.person_cards.append(card)
            self._start_image_load(card.avatar_label, person.profile_url)
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
            card.context_menu_requested.connect(
                lambda _item, global_pos, recommendation=item: self._open_related_recommendation_menu(
                    recommendation,
                    global_pos,
                )
            )
            self._related_recommendation_layout.addWidget(card)
            self.related_cards.append(card)
            self._start_image_load(card.poster_label, item.poster_url)
        self._related_recommendation_layout.addStretch(1)

    def _open_related_recommendation_menu(self, item: MediaDetailRecommendation, global_pos) -> None:
        menu = QMenu(self)
        search_action = menu.addAction("搜索资源")
        add_action = menu.addAction("加入追更")
        chosen = menu.exec(global_pos)
        if chosen == search_action:
            self._handle_related_recommendation_menu_action(item, "search")
        elif chosen == add_action:
            self._handle_related_recommendation_menu_action(item, "follow")

    def _handle_related_recommendation_menu_action(self, item: MediaDetailRecommendation, action: str) -> None:
        view = self._view_from_recommendation(item)
        if action == "search":
            self.search_play_requested.emit(view)
            return
        if action == "follow":
            self.add_following_requested.emit(view)

    def _view_from_recommendation(self, item: MediaDetailRecommendation) -> MediaDetailView:
        identity = MediaDetailIdentity(
            media_type=item.identity.media_type,
            tmdb_id=item.identity.tmdb_id,
            title=item.identity.title,
        )
        return MediaDetailView(
            identity=identity,
            title=identity.title,
            media_type=identity.media_type,
            year=item.year,
            poster_url=item.poster_url,
            rating=item.rating,
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(detail_scaffold_qss())

    def _start_image_load(self, label: QLabel, source: str) -> None:
        image_url = normalize_poster_url(source)
        if not image_url:
            return
        target_size = label.minimumSize()
        if target_size.isEmpty():
            target_size = QSize(max(1, label.width()), max(1, label.height()))

        def load() -> None:
            image = load_local_poster_image(source, target_size)
            if image is None:
                image = load_remote_poster_image(image_url, target_size)
            if image is not None and self._can_deliver_async_result():
                self.image_loaded.emit(label, image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_image_loaded(self, label: QLabel, image) -> None:
        if not shiboken6.isValid(label):
            return
        label.setText("")
        if label.property("person_avatar"):
            label.setStyleSheet(_person_inner_label_qss())
        label.setPixmap(QPixmap.fromImage(image))


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _media_detail_record_for_links(view: MediaDetailView):
    from atv_player.following_models import FollowingRecord

    return FollowingRecord(
        id=0,
        title=view.title,
        original_title=view.original_title,
        media_kind="movie" if view.media_type == "movie" else "live_action",
        provider="tmdb",
        provider_id=f"{view.media_type}:{view.identity.tmdb_id}",
    )
