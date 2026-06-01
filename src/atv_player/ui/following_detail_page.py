from __future__ import annotations

import html
import re
import threading
from dataclasses import replace

import shiboken6
from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from atv_player.following_metadata import _resolve_effective_media_kind
from atv_player.following_models import (
    FollowingCompletionState,
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingEpisodeState,
    FollowingMetadataSourceSnapshot,
    FollowingPlaybackPlatformEntry,
    FollowingRatingEntry,
    FollowingRecord,
    FollowingSeason,
    format_progress_episode,
    progress_at_or_beyond,
    resolve_display_total_episodes,
    resolve_following_completion_state,
    resolve_new_episode_count,
    resolve_progress_season,
)
from atv_player.metadata.discovery import DiscoveryItem
from atv_player.models import AppConfig
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.external_links import external_link_html
from atv_player.ui.following_episode_browser import (
    FollowingEpisodeBrowser,
    build_episode_season_groups,
)
from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)
from atv_player.ui.theme import current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase

_SEASON_PROVIDER_ID_RE = re.compile(r":season:(\d+)$")


class FollowingEpisodePreviewDialog(ThemedDialogBase):
    _image_loaded = Signal(QLabel, object)

    def __init__(
        self,
        episode: FollowingEpisode,
        *,
        status_text: str = "",
        can_mark_watched: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        title = _episode_title(episode)
        super().__init__(title=title, parent=parent, resizable=True)
        self.episode = episode
        self.status_text = str(status_text or "").strip()
        self.mark_watched_requested = False

        layout = self.content_layout()
        self.still_label = QLabel("分集封面", self)
        self.still_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still_label.setFixedHeight(360)
        self.still_label.setMinimumWidth(640)
        self.still_label.setStyleSheet(_image_placeholder_qss())
        self.title_label = QLabel(title, self)
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel(_episode_preview_meta_text(episode, self.status_text), self)
        self.overview_label = QLabel(episode.overview or "暂无剧情概要", self)
        self.overview_label.setWordWrap(True)
        self.mark_watched_button = QPushButton("标记本集已看", self)
        self.mark_watched_button.setVisible(can_mark_watched)
        self.mark_watched_button.clicked.connect(self._mark_watched_and_accept)

        layout.addWidget(self.still_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.overview_label)
        layout.addWidget(self.mark_watched_button, 0, Qt.AlignmentFlag.AlignRight)

        self._image_loaded.connect(self._handle_image_loaded)
        self._load_still_image()

    def _load_still_image(self) -> None:
        image_url = normalize_poster_url(self.episode.still)
        if not image_url:
            self.still_label.setText("暂无分集封面")
            return
        target_size = self.still_label.minimumSize()
        if target_size.isEmpty():
            target_size = QSize(320, 180)

        def load() -> None:
            image = load_local_poster_image(self.episode.still, target_size)
            if image is None:
                image = load_remote_poster_image(image_url, target_size)
            if image is not None:
                self._image_loaded.emit(self.still_label, image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_image_loaded(self, label: QLabel, image) -> None:
        if not shiboken6.isValid(label):
            return
        label.setText("")
        label.setPixmap(QPixmap.fromImage(image))

    def _mark_watched_and_accept(self) -> None:
        self.mark_watched_requested = True
        self.accept()


class FollowingProgressDialog(ThemedDialogBase):
    def __init__(
        self,
        *,
        current_season_number: int,
        current_episode: int,
        latest_season_number: int,
        latest_episode: int,
        total_episodes: int,
        seasons: list[FollowingSeason],
        episodes: list[FollowingEpisode],
        selected_season_number: int = 0,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(title="设置追更进度", parent=parent)
        self._episodes = list(episodes)
        self._episode_counts = self._build_episode_counts(
            seasons=seasons,
            episodes=self._episodes,
            fallback_season=max(current_season_number, latest_season_number, 1),
        )
        initial_season_number = self._initial_season_number(
            selected_season_number=selected_season_number,
            current_season_number=current_season_number,
            latest_season_number=latest_season_number,
        )
        current_episode = self._normalize_progress_episode(
            season_number=initial_season_number,
            episode_number=current_episode if current_season_number == initial_season_number else 0,
            episodes=self._episodes,
            overflow_value=0,
        )
        self._global_latest_season_number = latest_season_number
        self._global_latest_episode = latest_episode
        self._latest_season_number = latest_season_number
        self._latest_episode = self._latest_episode_for_season(initial_season_number)
        self._mark_latest_season_number = self._latest_season_number
        self._mark_latest_episode = self._latest_episode
        self._total_episodes = resolve_display_total_episodes(
            total_episodes=self._total_episodes_for_season(
                initial_season_number,
                fallback_total=total_episodes,
            ),
            latest_episode=self._latest_episode,
            completion_state=FollowingCompletionState.COMPLETED,
        )
        self.accepted_season_number = initial_season_number
        self.accepted_episode = current_episode

        layout = self.content_layout()
        layout.setSpacing(14)

        self.info_label = QLabel("", self)
        layout.addWidget(self.info_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("第", self))
        self.season_spin = QSpinBox(self)
        self.season_spin.setRange(self._season_minimum(), self._season_maximum())
        self.season_spin.setValue(
            max(self._season_minimum(), initial_season_number or self._season_minimum())
        )
        if self._season_minimum() <= 0:
            self.season_spin.setSpecialValueText("特别篇")
        row.addWidget(self.season_spin)
        row.addWidget(QLabel("季", self))
        row.addWidget(QLabel("看到第", self))
        self.episode_spin = QSpinBox(self)
        self.episode_spin.setSpecialValueText("未看")
        row.addWidget(self.episode_spin)
        row.addWidget(QLabel("集", self))
        row.addStretch(1)
        layout.addLayout(row)

        self.mark_latest_button = QPushButton("", self)
        self.mark_latest_button.clicked.connect(self._set_to_latest)
        layout.addWidget(self.mark_latest_button)

        self.season_spin.valueChanged.connect(self._handle_season_changed)
        self._update_episode_range(initial_season_number, preferred_episode=current_episode)
        self._refresh_latest_controls()

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定", self)
        ok_btn.clicked.connect(self._accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _build_episode_counts(
        self,
        *,
        seasons: list[FollowingSeason],
        episodes: list[FollowingEpisode],
        fallback_season: int,
    ) -> dict[int, int]:
        groups = build_episode_season_groups(
            episodes,
            seasons=seasons,
            fallback_season=fallback_season,
        )
        counts = {group.season_number: group.episode_count for group in groups}
        return counts or {fallback_season or 1: 0}

    def _initial_season_number(
        self,
        *,
        selected_season_number: int,
        current_season_number: int,
        latest_season_number: int,
    ) -> int:
        for season_number in (selected_season_number, current_season_number, latest_season_number):
            normalized = max(0, int(season_number or 0))
            if normalized in self._episode_counts:
                return normalized
        return self._season_minimum()

    def _total_episodes_for_season(self, season_number: int, *, fallback_total: int) -> int:
        count = int(self._episode_counts.get(int(season_number), 0) or 0)
        return count if count > 0 else max(0, int(fallback_total or 0))

    def _latest_episode_for_season(self, season_number: int) -> int:
        normalized_season = max(0, int(season_number or 0))
        normalized_global_season = max(0, int(self._global_latest_season_number or 0))
        if normalized_season > 0 and normalized_global_season > 0 and normalized_season < normalized_global_season:
            return max(0, int(self._episode_counts.get(normalized_season, 0) or 0))
        if normalized_season != normalized_global_season:
            return 0
        return self._normalize_latest_episode(
            latest_season_number=normalized_season,
            latest_episode=self._global_latest_episode,
            episodes=self._episodes,
        )

    def _refresh_latest_controls(self) -> None:
        season_number = int(self.season_spin.value())
        self._latest_season_number = season_number
        self._latest_episode = self._latest_episode_for_season(season_number)
        self._mark_latest_season_number = season_number
        self._mark_latest_episode = self._latest_episode
        if self._mark_latest_episode <= 0:
            global_latest_season = max(0, int(self._global_latest_season_number or 0))
            global_latest_episode = self._latest_episode_for_season(global_latest_season)
            if global_latest_season > 0 and global_latest_episode > 0:
                self._mark_latest_season_number = global_latest_season
                self._mark_latest_episode = global_latest_episode
        self._total_episodes = resolve_display_total_episodes(
            total_episodes=self._total_episodes_for_season(season_number, fallback_total=0),
            latest_episode=self._latest_episode,
            completion_state=FollowingCompletionState.COMPLETED,
        )
        info_parts = []
        latest_text = format_progress_episode(
            "最新",
            season_number,
            self._latest_episode,
            fallback_season=season_number,
        )
        if latest_text and self._total_episodes > 0:
            info_parts.append(f"{latest_text} / 总 {self._total_episodes}")
        elif latest_text:
            info_parts.append(latest_text)
        elif self._total_episodes > 0:
            info_parts.append(f"总 {self._total_episodes}")
        self.info_label.setText("  ·  ".join(info_parts))
        self.info_label.setVisible(bool(info_parts))
        latest_pair_text = (
            "设为最新 "
            f"({format_progress_episode('', self._mark_latest_season_number, self._mark_latest_episode, fallback_season=self._mark_latest_season_number).strip()})"
            if self._mark_latest_episode > 0
            else ""
        )
        self.mark_latest_button.setText(latest_pair_text)
        self.mark_latest_button.setVisible(self._mark_latest_episode > 0)

    def _normalize_latest_episode(
        self,
        *,
        latest_season_number: int,
        latest_episode: int,
        episodes: list[FollowingEpisode],
    ) -> int:
        return self._normalize_progress_episode(
            season_number=latest_season_number,
            episode_number=latest_episode,
            episodes=episodes,
            overflow_value=None,
        )

    def _normalize_progress_episode(
        self,
        *,
        season_number: int,
        episode_number: int,
        episodes: list[FollowingEpisode],
        overflow_value: int | None,
    ) -> int:
        normalized_season = max(0, int(season_number or 0))
        normalized_episode = max(0, int(episode_number or 0))
        if normalized_season <= 0 or normalized_episode <= 0:
            return normalized_episode
        season_count = int(self._episode_counts.get(normalized_season, 0) or 0)
        if season_count <= 0:
            return normalized_episode
        local_numbers = [
            int(episode.episode_number or 0)
            for episode in episodes
            if int(episode.episode_number or 0) > 0
            and (
                int(episode.season_number or 0) or normalized_season
            ) == normalized_season
            and not episode.is_special
        ]
        if not local_numbers:
            return normalized_episode
        local_latest = max(local_numbers)
        if normalized_episode > local_latest and local_latest >= season_count:
            return local_latest if overflow_value is None else max(0, int(overflow_value))
        return normalized_episode

    def _season_minimum(self) -> int:
        return min(self._episode_counts) if self._episode_counts else 0

    def _season_maximum(self) -> int:
        return max(self._episode_counts) if self._episode_counts else 1

    def _episode_limit_for_season(self, season_number: int) -> int:
        count = int(self._episode_counts.get(int(season_number), 0) or 0)
        if int(season_number) == self._latest_season_number:
            count = max(count, self._latest_episode)
        return max(0, count)

    def _update_episode_range(self, season_number: int, *, preferred_episode: int | None = None) -> None:
        maximum = self._episode_limit_for_season(season_number)
        self.episode_spin.setRange(0, maximum or 9999)
        target_episode = max(0, int(preferred_episode if preferred_episode is not None else self.episode_spin.value() or 0))
        if maximum > 0:
            target_episode = min(target_episode, maximum)
        self.episode_spin.setValue(target_episode)

    def _handle_season_changed(self, value: int) -> None:
        self._update_episode_range(int(value))
        self._refresh_latest_controls()

    def _set_to_latest(self) -> None:
        season_number = self._mark_latest_season_number or self.season_spin.value()
        episode_number = self._mark_latest_episode
        self.season_spin.setValue(season_number)
        self.episode_spin.setValue(episode_number)

    def _accept(self) -> None:
        self.accepted_season_number = int(self.season_spin.value())
        self.accepted_episode = int(self.episode_spin.value())
        self.accept()


class MovieProgressDialog(ThemedDialogBase):
    def __init__(self, *, is_watched: bool, parent: QWidget | None = None) -> None:
        super().__init__(title="设置观影状态", parent=parent)
        self.accepted_episode = 0
        layout = self.content_layout()
        layout.setSpacing(14)
        btn_row = QHBoxLayout()
        self._unwatched_btn = QPushButton("未观看", self)
        self._watched_btn = QPushButton("已观看", self)
        if is_watched:
            self._watched_btn.setProperty("class", "accent")
        else:
            self._unwatched_btn.setProperty("class", "accent")
        self._unwatched_btn.clicked.connect(self._select_unwatched)
        self._watched_btn.clicked.connect(self._select_watched)
        btn_row.addWidget(self._unwatched_btn)
        btn_row.addWidget(self._watched_btn)
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_row.addStretch(1)
        ok_btn = QPushButton("确定", self)
        ok_btn.clicked.connect(self.accept)
        ok_row.addWidget(ok_btn)
        layout.addLayout(ok_row)

    def _select_unwatched(self) -> None:
        self.accepted_episode = 0
        self._unwatched_btn.setProperty("class", "accent")
        self._watched_btn.setProperty("class", "")
        self.accept()

    def _select_watched(self) -> None:
        self.accepted_episode = 1
        self._watched_btn.setProperty("class", "accent")
        self._unwatched_btn.setProperty("class", "")
        self.accept()


class FollowingPersonCard(QFrame):
    def __init__(
        self, person: dict[str, object], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.person = person
        self.setObjectName("personCard")
        self._person_url = _person_link(person)
        self.setMinimumSize(142, 248)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if self._person_url:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.avatar_label = QLabel(_person_avatar_initial(person), self)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(120, 180)
        self.avatar_label.setProperty("person_avatar", True)
        self.avatar_label.setObjectName("personAvatar")
        self.avatar_label.setStyleSheet(_person_avatar_fallback_qss())
        self.name_label = QLabel(str(person.get("name") or ""), self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("personName")
        self.name_label.setStyleSheet(_person_inner_label_qss())
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
        self.role_label.setObjectName("personRole")
        self.role_label.setStyleSheet(_person_inner_label_qss())
        self.role_label.setVisible(bool(str(role).strip()))

        layout.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.role_label)
        layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._person_url:
            QDesktopServices.openUrl(QUrl(self._person_url))
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FollowingRelatedRecommendationCard(QFrame):
    activated = Signal(object)
    context_menu_requested = Signal(object, object)

    def __init__(self, item: DiscoveryItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("followingRelatedRecommendationCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(148, 258)
        self.setMaximumWidth(176)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.poster_label = QLabel("海报", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(132, 188)
        self.poster_label.setStyleSheet(_image_placeholder_qss())
        self.title_label = QLabel(item.title or "未命名", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("relatedRecommendationTitle")
        meta_parts = [
            part
            for part in (
                item.year,
                "电影" if item.media_type == "movie" else "剧集",
                f"TMDB {item.rating}" if item.rating else "",
            )
            if str(part or "").strip()
        ]
        self.meta_label = QLabel(" · ".join(meta_parts), self)
        self.meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_label.setWordWrap(True)
        self.meta_label.setObjectName("relatedRecommendationMeta")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.item)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.context_menu_requested.emit(self.item, event.globalPos())
        event.accept()


class FollowingDetailPage(QWidget, AsyncGuardMixin):
    back_requested = Signal()
    continue_play_requested = Signal(int)
    search_play_requested = Signal(int)
    unfollow_requested = Signal(int)
    related_global_search_requested = Signal(str)
    image_loaded = Signal(object, object)
    check_finished = Signal(int, object, str)
    metadata_refresh_finished = Signal(int, object, str)
    season_detail_finished = Signal(int, int, object, str)
    related_recommendations_finished = Signal(int, int, object, str)

    def __init__(
        self,
        controller,
        *,
        config: AppConfig | None = None,
        save_config=None,
    ) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._config = config or AppConfig()
        self._save_config = save_config
        self.current_following_id = 0
        self.current_view = None
        self._selected_season_number = 0
        self._related_recommendation_request_id = 0
        self._pending_people: list[dict[str, object]] = []
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(1)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._render_next_batch)
        self.cast_widgets: list[FollowingPersonCard] = []

        self.back_button = QPushButton("返回")
        self.backdrop_label = QLabel("海报背景")
        self.poster_label = QLabel("封面")
        self.title_label = QLabel()
        self.meta_label = QLabel()
        self.rating_strip = QLabel()
        self.overview_label = QLabel()
        self.overview_label.setTextFormat(Qt.TextFormat.RichText)
        self.overview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.overview_label.setOpenExternalLinks(False)
        self.overview_label.linkActivated.connect(self._open_external_link)
        self.status_label = QLabel()
        self.continue_play_button = QPushButton("继续播放")
        self.search_play_button = QPushButton("搜索播放")
        self.manual_check_button = QPushButton("检查更新")
        self.refresh_metadata_button = QPushButton("更新元数据")
        self.set_progress_button = QPushButton("设置进度")
        self.unfollow_button = QPushButton("取消追更")
        self.poster_carousel_label = QLabel("海报轮播")
        self.poster_carousel_index = 0
        self.poster_carousel_sources: list[str] = []
        self.poster_carousel_timer = QTimer(self)
        self.poster_carousel_timer.setInterval(4500)
        self.episode_browser = FollowingEpisodeBrowser(
            initial_grid_columns=self._config.following_episode_grid_columns,
            parent=self,
        )
        self.metadata_source_bar = QWidget()
        self.metadata_source_layout = QHBoxLayout(self.metadata_source_bar)
        self.metadata_source_buttons: list[QPushButton] = []
        self.playback_platform_section = QFrame()
        self.playback_platform_layout = QVBoxLayout(self.playback_platform_section)
        self.playback_platform_buttons: list[QPushButton] = []
        self.playback_platform_widgets: list[QLabel] = []
        self._selected_metadata_source_key = "merged"
        self.related_recommendation_cards: list[FollowingRelatedRecommendationCard] = []
        self.related_recommendation_section = QFrame()
        self.related_recommendation_section.setObjectName("followingRelatedRecommendationSection")
        self.related_recommendation_status_label = QLabel()
        self.related_recommendation_scroll = QScrollArea()
        self._related_recommendation_container = QWidget()
        self._related_recommendation_layout = QHBoxLayout(self._related_recommendation_container)
        self._related_recommendation_layout.setContentsMargins(0, 0, 0, 0)
        self._related_recommendation_layout.setSpacing(12)

        self._cast_container = QWidget()
        self._cast_layout = QHBoxLayout(self._cast_container)
        self._cast_layout.setContentsMargins(0, 0, 0, 0)
        self._cast_layout.setSpacing(12)

        self._build_layout()
        self._connect_actions()
        self.poster_carousel_timer.timeout.connect(self._advance_poster_carousel)
        self._connect_async_signal(self.image_loaded, self._handle_image_loaded)
        self._connect_async_signal(self.check_finished, self._handle_check_finished)
        self._connect_async_signal(self.metadata_refresh_finished, self._handle_metadata_refresh_finished)
        self._connect_async_signal(self.season_detail_finished, self._handle_season_detail_finished)
        self._connect_async_signal(self.related_recommendations_finished, self._handle_related_recommendations_finished)
        self.episode_browser.episode_activated.connect(self._open_episode_preview)
        self.episode_browser.season_changed.connect(self._handle_season_changed)
        self.episode_browser.grid_columns_changed.connect(
            self._handle_episode_grid_columns_changed
        )
        self._apply_style()

    def load_record(self, following_id: int) -> None:
        self._batch_timer.stop()
        self._pending_people = []
        self.current_following_id = int(following_id)
        self.current_view = self._load_detail_view(self.current_following_id)
        self._selected_metadata_source_key = "merged"
        self._selected_season_number = self._initial_selected_season(
            self.current_view.record,
            self.current_view.snapshot,
        )
        self._render(self.current_view.record, self.current_view.snapshot)
        is_movie = str(getattr(self.current_view.record, "provider_id", "") or "").startswith("movie:")
        if self._snapshot_needs_refresh(self.current_view.snapshot):
            self.status_label.setText("详情暂无完整数据，可手动检查更新")
        elif not is_movie and self._should_load_selected_season():
            QTimer.singleShot(0, self._load_selected_season_if_needed)

    def _build_layout(self) -> None:
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setMinimumSize(260, 360)
        self.poster_label.setMaximumWidth(360)
        self.poster_label.setStyleSheet(_image_placeholder_qss())
        self.poster_carousel_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_carousel_label.setMinimumSize(720, 405)
        self.poster_carousel_label.setStyleSheet(_carousel_image_qss())
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("followingDetailTitle")
        self.meta_label.setWordWrap(True)
        self.rating_strip.setWordWrap(True)
        self.overview_label.setWordWrap(True)
        self.overview_label.setMinimumHeight(64)
        selectable_flags = (
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.title_label.setTextInteractionFlags(selectable_flags)
        self.meta_label.setTextInteractionFlags(selectable_flags)
        self.rating_strip.setTextInteractionFlags(selectable_flags)
        self.overview_label.setTextInteractionFlags(selectable_flags)
        self.metadata_source_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_source_layout.setSpacing(8)
        self.playback_platform_layout.setContentsMargins(0, 0, 0, 0)
        self.playback_platform_layout.setSpacing(8)

        action_row = QHBoxLayout()
        action_row.addWidget(self.back_button)
        action_row.addStretch(1)
        action_row.addWidget(self.continue_play_button)
        action_row.addWidget(self.search_play_button)
        action_row.addWidget(self.manual_check_button)
        action_row.addWidget(self.refresh_metadata_button)
        action_row.addWidget(self.set_progress_button)
        action_row.addWidget(self.unfollow_button)

        content = QWidget(self)

        self.metadata_panel = QFrame(content)
        self.metadata_panel.setObjectName("followingDetailMetadataPanel")
        metadata_layout = QVBoxLayout(self.metadata_panel)
        metadata_layout.setContentsMargins(18, 18, 18, 18)
        metadata_layout.setSpacing(12)
        metadata_layout.addLayout(action_row)
        metadata_layout.addWidget(self.status_label)
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.meta_label)
        metadata_layout.addWidget(self.rating_strip)
        metadata_layout.addWidget(self.metadata_source_bar)
        metadata_layout.addWidget(self.playback_platform_section)
        metadata_layout.addWidget(self.overview_label)
        metadata_layout.addStretch(1)

        self.poster_carousel_panel = QFrame(content)
        self.poster_carousel_panel.setObjectName("followingDetailPosterCarousel")
        poster_layout = QVBoxLayout(self.poster_carousel_panel)
        poster_layout.setContentsMargins(0, 0, 0, 0)
        poster_layout.setSpacing(0)
        poster_layout.addWidget(self.poster_carousel_label)

        self.top_section = QWidget(content)
        self.top_section.setObjectName("followingDetailTopSection")
        top_layout = QHBoxLayout(self.top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(18)
        top_layout.addWidget(self.metadata_panel, 3)
        top_layout.addWidget(self.poster_carousel_panel, 2)

        self.cast_scroll = QScrollArea()
        self.cast_scroll.setWidgetResizable(True)
        self.cast_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cast_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cast_scroll.setWidget(self._cast_container)
        self.cast_scroll.setMinimumHeight(270)
        self.cast_scroll.setMaximumHeight(300)

        self.related_recommendation_scroll.setWidgetResizable(True)
        self.related_recommendation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.related_recommendation_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.related_recommendation_scroll.setWidget(self._related_recommendation_container)
        self.related_recommendation_scroll.setMinimumHeight(286)
        self.related_recommendation_scroll.setMaximumHeight(308)

        related_section_layout = QVBoxLayout(self.related_recommendation_section)
        related_section_layout.setContentsMargins(14, 14, 14, 14)
        related_section_layout.setSpacing(10)
        related_section_layout.addWidget(QLabel("关联媒体推荐", self.related_recommendation_section))
        related_section_layout.addWidget(self.related_recommendation_status_label)
        related_section_layout.addWidget(self.related_recommendation_scroll)

        self.episodes_section = QFrame(content)
        self.episodes_section.setObjectName("followingDetailEpisodesSection")
        self.episodes_section.setMinimumHeight(480)
        episodes_section_layout = QVBoxLayout(self.episodes_section)
        episodes_section_layout.setContentsMargins(14, 14, 14, 14)
        episodes_section_layout.setSpacing(10)
        episodes_section_layout.addWidget(QLabel("分集详情", self.episodes_section))
        self.episode_browser.season_list.setMaximumWidth(180)
        self.episode_browser.browser_frame.layout().setStretch(0, 0)
        self.episode_browser.browser_frame.layout().setStretch(1, 1)
        episodes_section_layout.addWidget(self.episode_browser)

        self.cast_section = QFrame(content)
        self.cast_section.setObjectName("followingDetailCastSection")
        cast_section_layout = QVBoxLayout(self.cast_section)
        cast_section_layout.setContentsMargins(14, 14, 14, 14)
        cast_section_layout.setSpacing(10)
        cast_section_layout.addWidget(QLabel("演职员列表", self.cast_section))
        cast_section_layout.addWidget(self.cast_scroll)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(18)
        content_layout.addWidget(self.top_section)
        content_layout.addWidget(self.episodes_section)
        content_layout.addWidget(self.related_recommendation_section)
        content_layout.addWidget(self.cast_section)
        content_layout.addStretch(1)

        self.page_scroll = QScrollArea(self)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.page_scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.page_scroll)

    def _connect_actions(self) -> None:
        self.back_button.clicked.connect(self.back_requested.emit)
        self.continue_play_button.clicked.connect(self._emit_continue_play)
        self.search_play_button.clicked.connect(self._emit_search_play)
        self.manual_check_button.clicked.connect(self._manual_check)
        self.refresh_metadata_button.clicked.connect(self._refresh_metadata)
        self.set_progress_button.clicked.connect(self._open_progress_dialog)
        self.unfollow_button.clicked.connect(self._emit_unfollow)

    def _render(
        self, record: FollowingRecord, snapshot: FollowingDetailSnapshot
    ) -> None:
        display_record = _normalized_detail_progress_record(record, snapshot)
        self.status_label.setText("")
        has_binding = any(
            str(getattr(binding, "source_kind", "") or "").strip()
            and str(getattr(binding, "vod_id", "") or "").strip()
            for binding in list(record.source_bindings or [])
        )
        self.continue_play_button.setEnabled(has_binding)
        self.continue_play_button.setToolTip("从上次播放源继续" if has_binding else "暂无已绑定播放源，请先搜索播放")
        self.title_label.setText(display_record.title)
        self.meta_label.setText(_meta_text(display_record, snapshot))
        self._render_metadata_bundle(snapshot)
        self._render_poster_carousel(display_record, snapshot)
        groups = build_episode_season_groups(
            snapshot.episodes,
            seasons=snapshot.seasons,
            fallback_season=display_record.season_number,
        )
        latest_season_number = _detail_latest_season_number(display_record, snapshot)
        is_movie = str(getattr(record, "provider_id", "") or "").startswith("movie:")
        self.episode_browser.set_content(
            groups=groups,
            current_season_number=display_record.current_season_number,
            current_episode=display_record.current_episode,
            selected_season_number=self._selected_season_number,
            latest_episode=display_record.latest_episode,
            latest_season_number=latest_season_number,
            next_episode=snapshot.next_episode,
        )
        self.episodes_section.setVisible(not is_movie)
        self.cast_widgets = []
        _clear_layout(self._cast_layout)
        self._pending_people = [*snapshot.cast, *snapshot.crew]
        self._render_next_batch()
        self._start_related_recommendations_load()

    def _render_metadata_bundle(self, snapshot: FollowingDetailSnapshot) -> None:
        bundle = snapshot.metadata_bundle
        if bundle is None:
            self.rating_strip.setText("")
            self._render_source_buttons(["merged"], source_snapshots={})
            self._render_playback_platforms([])
            record = self.current_view.record if self.current_view is not None else None
            self.overview_label.setText(_format_detail_text(snapshot, record=record))
            return
        source_snapshots = dict(bundle.source_snapshots)
        current_key = (
            self._selected_metadata_source_key
            if self._selected_metadata_source_key in source_snapshots
            else bundle.default_source_key
        )
        current = bundle.merged_snapshot if current_key == "merged" else source_snapshots[current_key]
        self.rating_strip.setText(_rating_strip_text(bundle.merged_snapshot.ratings))
        self._render_source_buttons(bundle.available_source_keys, source_snapshots=source_snapshots)
        platforms = bundle.merged_snapshot.playback_platforms if current_key == "merged" else current.playback_platforms
        self._render_playback_platforms(platforms)
        record = self.current_view.record if self.current_view is not None else None
        if current_key == "merged":
            self.overview_label.setText(_format_merged_source_snapshot_text(bundle.merged_snapshot, record=record))
        else:
            self.overview_label.setText(_format_source_snapshot_text(current, record=record))

    def _render_source_buttons(
        self,
        source_keys: list[str],
        *,
        source_snapshots: dict[str, FollowingMetadataSourceSnapshot],
    ) -> None:
        _clear_layout(self.metadata_source_layout)
        self.metadata_source_buttons = []
        for source_key in source_keys:
            if source_key == "merged":
                label = "媒体信息"
            else:
                snapshot = source_snapshots.get(source_key)
                label = snapshot.provider_label if snapshot is not None else source_key
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
        if self.current_view is None:
            return
        self._render_metadata_bundle(self.current_view.snapshot)

    def _render_playback_platforms(self, platforms: list[FollowingPlaybackPlatformEntry]) -> None:
        _clear_layout(self.playback_platform_layout)
        self.playback_platform_buttons = []
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

    def _render_next_batch(self) -> None:
        batch = 20
        n = 0
        while self._pending_people and n < batch:
            person = self._pending_people.pop(0)
            card = FollowingPersonCard(person, self._cast_container)
            self._cast_layout.addWidget(card)
            self.cast_widgets.append(card)
            self._start_image_load(card.avatar_label, _person_avatar(person))
            n += 1
        if self._pending_people:
            self._batch_timer.start()
        else:
            self._cast_layout.addStretch(1)

    def _render_poster_carousel(
        self, record: FollowingRecord, snapshot: FollowingDetailSnapshot
    ) -> None:
        sources = _unique_sources(
            [
                *snapshot.backdrops,
                record.backdrop,
            ]
        )
        self.poster_carousel_sources = sources
        self.poster_carousel_index = 0
        self.poster_carousel_timer.stop()
        self.poster_carousel_label.setText("海报轮播" if sources else "暂无海报")
        if sources:
            self._start_image_load(self.poster_carousel_label, sources[0])
            if len(sources) > 1:
                self.poster_carousel_timer.start()

    def _advance_poster_carousel(self) -> None:
        if len(self.poster_carousel_sources) <= 1:
            self.poster_carousel_timer.stop()
            return
        self.poster_carousel_index = (self.poster_carousel_index + 1) % len(self.poster_carousel_sources)
        self._start_image_load(
            self.poster_carousel_label,
            self.poster_carousel_sources[self.poster_carousel_index],
        )

    def _emit_search_play(self) -> None:
        self.search_play_requested.emit(self.current_following_id)

    def _emit_continue_play(self) -> None:
        self.continue_play_requested.emit(self.current_following_id)

    def _emit_unfollow(self) -> None:
        self.unfollow_requested.emit(self.current_following_id)

    def _open_episode_preview(self, episode: FollowingEpisode) -> None:
        status = self.episode_browser.status_for_episode(episode)
        dialog = FollowingEpisodePreviewDialog(
            episode,
            status_text=self.episode_browser.status_text_for_episode(episode),
            can_mark_watched=status == FollowingEpisodeState.RELEASED,
            parent=self,
        )
        if dialog.exec() != 1 or not dialog.mark_watched_requested:
            return
        fallback_season = self.episode_browser.current_season_number()
        if fallback_season <= 0 and self.current_view is not None:
            fallback_season = self.current_view.record.season_number
        season_number = resolve_progress_season(
            episode.season_number,
            episode.episode_number,
            fallback_season=fallback_season,
        )
        self._save_following_progress(
            season_number=season_number,
            episode_number=episode.episode_number,
            message="已标记本集为已看",
        )

    def _handle_episode_grid_columns_changed(self, columns: int) -> None:
        normalized = int(columns)
        if self._config.following_episode_grid_columns == normalized:
            return
        self._config.following_episode_grid_columns = normalized
        if callable(self._save_config):
            self._save_config()

    def _handle_season_changed(self, season_number: int) -> None:
        normalized = int(season_number)
        if self.current_following_id <= 0:
            return
        if normalized == self._selected_season_number and self._current_snapshot_matches_selected_season():
            return
        self._selected_season_number = normalized
        self._request_season_load(normalized)

    def _manual_check(self) -> None:
        if self.current_following_id <= 0:
            return
        self._start_background_check("正在检查更新...")

    def _refresh_metadata(self) -> None:
        following_id = self.current_following_id
        if following_id <= 0 or not self.refresh_metadata_button.isEnabled():
            return
        self.status_label.setText("正在更新元数据...")
        self.refresh_metadata_button.setEnabled(False)

        def refresh() -> None:
            try:
                view = self.controller.refresh_metadata(following_id)
                error = ""
            except Exception as exc:
                view = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.metadata_refresh_finished.emit(following_id, view, error)

        threading.Thread(target=refresh, daemon=True).start()

    def _start_background_check(self, message: str) -> None:
        following_id = self.current_following_id
        if following_id <= 0 or not self.manual_check_button.isEnabled():
            return
        self.status_label.setText("正在检查更新...")
        self.manual_check_button.setEnabled(False)
        self.status_label.setText(message)

        def check() -> None:
            try:
                result = self.controller.check_one(following_id)
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.check_finished.emit(following_id, result, error)

        threading.Thread(target=check, daemon=True).start()

    def _handle_check_finished(self, following_id: int, result, error: str) -> None:
        if following_id != self.current_following_id:
            return
        self.manual_check_button.setEnabled(True)
        self.current_view = self._load_detail_view(following_id)
        self._render(self.current_view.record, self.current_view.snapshot)
        if error:
            self.status_label.setText(f"检查失败: {error}")
        elif result is not None and getattr(result, "checked", False) is False:
            self.status_label.setText(str(getattr(result, "error", "") or "检查失败"))
        else:
            self.status_label.setText("已完成检查更新")

    def _handle_metadata_refresh_finished(self, following_id: int, view, error: str) -> None:
        if following_id != self.current_following_id:
            return
        self.refresh_metadata_button.setEnabled(True)
        if error:
            self.status_label.setText(f"元数据更新失败: {error}")
            return
        self.current_view = view or self._load_detail_view(following_id)
        self._selected_season_number = self._initial_selected_season(
            self.current_view.record,
            self.current_view.snapshot,
        )
        self._render(self.current_view.record, self.current_view.snapshot)
        if self._should_load_selected_season():
            self.status_label.setText("正在加载当前季分集...")
            QTimer.singleShot(0, self._load_selected_season_if_needed)
            return
        self.status_label.setText("元数据已更新")

    def _handle_season_detail_finished(self, following_id: int, season_number: int, view, error: str) -> None:
        if following_id != self.current_following_id or season_number != self._selected_season_number:
            return
        if error:
            self.status_label.setText(f"分季加载失败: {error}")
            return
        self.current_view = view or self.controller.load_detail(following_id, refresh_if_empty=False)
        self._render(self.current_view.record, self.current_view.snapshot)
        self.status_label.setText("")

    def _open_progress_dialog(self) -> None:
        if self.current_following_id <= 0 or self.current_view is None:
            return
        record = _normalized_detail_progress_record(
            self.current_view.record,
            self.current_view.snapshot,
        )
        if _resolve_effective_media_kind(record, self.current_view.snapshot) == "movie":
            is_watched = record.current_episode > 0 or record.last_played_at > 0
            dialog = MovieProgressDialog(is_watched=is_watched, parent=self)
            if dialog.exec() != 1:
                return
            self._save_following_progress(
                season_number=0,
                episode_number=dialog.accepted_episode,
                message="已保存观影状态",
            )
            return
        current_season_number = resolve_progress_season(
            record.current_season_number,
            record.current_episode,
            fallback_season=record.season_number or self._selected_season_number,
        )
        latest_season_number = _detail_latest_season_number(record, self.current_view.snapshot)
        dialog = FollowingProgressDialog(
            current_season_number=current_season_number,
            current_episode=record.current_episode,
            latest_season_number=latest_season_number,
            latest_episode=record.latest_episode,
            total_episodes=record.total_episodes,
            seasons=list(self.current_view.snapshot.seasons or []),
            episodes=list(self.current_view.snapshot.episodes or []),
            selected_season_number=self._selected_season_number,
            parent=self,
        )
        if dialog.exec() != 1:
            return
        self._save_following_progress(
            season_number=dialog.accepted_season_number,
            episode_number=dialog.accepted_episode,
            message="已保存追更进度",
        )

    def _save_following_progress(
        self,
        *,
        season_number: int,
        episode_number: int,
        message: str,
    ) -> None:
        self.controller.record_playback_progress(
            self.current_following_id,
            current_season_number=season_number,
            current_episode=episode_number,
            position_seconds=0,
            allow_regression=True,
        )
        self.load_record(self.current_following_id)
        self.status_label.setText(message)

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

    def _start_related_recommendations_load(self) -> None:
        load_related = getattr(self.controller, "load_related_recommendations", None)
        self._related_recommendation_request_id += 1
        request_id = self._related_recommendation_request_id
        self._clear_related_recommendations()
        if self.current_following_id <= 0 or not callable(load_related):
            self.related_recommendation_section.hide()
            return
        following_id = self.current_following_id
        self.related_recommendation_section.show()
        self.related_recommendation_status_label.setText("正在加载关联推荐...")
        self.related_recommendation_status_label.show()
        self.related_recommendation_scroll.hide()

        def load() -> None:
            try:
                result = load_related(following_id)
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.related_recommendations_finished.emit(request_id, following_id, result, error)

        threading.Thread(target=load, daemon=True).start()

    def _handle_related_recommendations_finished(
        self,
        request_id: int,
        following_id: int,
        result,
        error: str,
    ) -> None:
        if request_id != self._related_recommendation_request_id or following_id != self.current_following_id:
            return
        self._clear_related_recommendations()
        self.related_recommendation_section.show()
        if error:
            self.related_recommendation_status_label.setText(f"关联推荐加载失败: {error}")
            self.related_recommendation_status_label.show()
            self.related_recommendation_scroll.hide()
            return
        items = list(getattr(result, "items", []) or [])
        if not items:
            self.related_recommendation_status_label.setText("暂无关联推荐")
            self.related_recommendation_status_label.show()
            self.related_recommendation_scroll.hide()
            return
        self.related_recommendation_status_label.hide()
        self.related_recommendation_scroll.show()
        for item in items:
            card = FollowingRelatedRecommendationCard(item, self._related_recommendation_container)
            card.activated.connect(self._handle_related_recommendation_activated)
            card.context_menu_requested.connect(self._open_related_recommendation_menu)
            self._related_recommendation_layout.addWidget(card)
            self.related_recommendation_cards.append(card)
            self._start_image_load(card.poster_label, item.poster)
        self._related_recommendation_layout.addStretch(1)

    def _clear_related_recommendations(self) -> None:
        self.related_recommendation_cards = []
        _clear_layout(self._related_recommendation_layout)

    def _handle_related_recommendation_activated(self, item: DiscoveryItem) -> None:
        keyword = str(item.title or "").strip()
        if keyword:
            self.related_global_search_requested.emit(keyword)

    def _open_related_recommendation_menu(self, item: DiscoveryItem, global_pos) -> None:
        menu = QMenu(self)
        search_action = menu.addAction("搜索资源")
        add_action = menu.addAction("加入追更")
        chosen = menu.exec(global_pos)
        if chosen == search_action:
            self._handle_related_recommendation_activated(item)
            return
        if chosen != add_action:
            return
        add_candidate = getattr(self.controller, "add_candidate", None)
        if not callable(add_candidate):
            self.status_label.setText("加入追更失败: 当前控制器不支持加入追更")
            return
        try:
            record = add_candidate(item)
        except Exception as exc:
            self.status_label.setText(f"加入追更失败: {exc}")
            return
        title = str(getattr(record, "title", "") or item.title or "").strip()
        self.status_label.setText(f"已加入追更: {title}" if title else "已加入追更")
        self._start_related_recommendations_load()

    def _snapshot_needs_refresh(self, snapshot: FollowingDetailSnapshot) -> bool:
        return not any(
            (
                snapshot.overview,
                snapshot.cast,
                snapshot.crew,
                snapshot.seasons,
                snapshot.episodes,
                snapshot.posters,
                snapshot.backdrops,
            )
        )

    def _initial_selected_season(
        self,
        record: FollowingRecord,
        snapshot: FollowingDetailSnapshot,
    ) -> int:
        season_numbers = {
            episode.season_number
            for episode in snapshot.episodes
            if episode.season_number > 0
        }
        if len(season_numbers) == 1:
            return next(iter(season_numbers))
        if record.season_number > 0:
            return record.season_number
        provider_id_season = _season_number_from_provider_id(record.provider_id)
        if provider_id_season > 0:
            return provider_id_season
        positive_summary_seasons = [season.season_number for season in snapshot.seasons if season.season_number > 0]
        if positive_summary_seasons:
            return positive_summary_seasons[0]
        if snapshot.seasons:
            return snapshot.seasons[0].season_number
        return 0

    def _current_snapshot_matches_selected_season(self) -> bool:
        if self._selected_season_number <= 0 or self.current_view is None:
            return False
        snapshot = self.current_view.snapshot
        if not snapshot.episodes:
            return False
        return any(
            (episode.season_number or self._selected_season_number) == self._selected_season_number
            for episode in snapshot.episodes
        )

    def _should_load_selected_season(self) -> bool:
        if self.current_view is None or self._selected_season_number <= 0:
            return False
        snapshot = self.current_view.snapshot
        if not snapshot.seasons:
            return False
        return not self._current_snapshot_matches_selected_season()

    def _load_selected_season_if_needed(self) -> None:
        if self._selected_season_number <= 0:
            return
        self._request_season_load(self._selected_season_number)

    def _request_season_load(self, season_number: int) -> None:
        load_detail_season = getattr(self.controller, "load_detail_season", None)
        if not callable(load_detail_season):
            return
        self.status_label.setText(f"正在加载第 {season_number} 季分集...")

        def load() -> None:
            try:
                view = load_detail_season(self.current_following_id, season_number=season_number)
                error = ""
            except Exception as exc:
                view = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.season_detail_finished.emit(self.current_following_id, season_number, view, error)

        threading.Thread(target=load, daemon=True).start()

    def _load_detail_view(self, following_id: int):
        try:
            return self.controller.load_detail(following_id, refresh_if_empty=False)
        except TypeError as exc:
            if "refresh_if_empty" not in str(exc):
                raise
            return self.controller.load_detail(following_id)

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
            QFrame#personCard {{
                border: 1px solid {tokens.border_subtle};
                border-radius: 14px;
                background: {tokens.panel_bg};
            }}
            QLabel#personAvatar {{
                border: 0;
                border-radius: 10px;
                background: {tokens.panel_alt_bg};
                color: {tokens.text_secondary};
                font-size: 24px;
                font-weight: 600;
            }}
            QLabel#personName, QLabel#personRole {{
                border: 0;
                border-radius: 0;
                background: transparent;
                color: {tokens.text_secondary};
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
            QPushButton:checked {{
                border-color: {tokens.accent};
                background: {tokens.panel_alt_bg};
            }}
            QSpinBox {{
                border: 1px solid {tokens.border_subtle};
                border-radius: 10px;
                background: {tokens.button_bg};
                color: {tokens.text_primary};
                padding: 6px 10px;
            }}
            QScrollArea {{
                border: 0;
                background: transparent;
            }}
            QLabel {{
                background: transparent;
            }}
            """
        )

def _clear_layout(layout: QHBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _episode_title(episode: FollowingEpisode) -> str:
    title = episode.title.strip() or "未命名"
    return f"{episode.episode_number}. {title}"


def _episode_preview_meta_text(episode: FollowingEpisode, status_text: str = "") -> str:
    parts = []
    if episode.air_date:
        parts.append(episode.air_date)
    if episode.runtime > 0:
        parts.append(f"{episode.runtime}m")
    if status_text:
        parts.append(status_text)
    return " · ".join(parts)


def _unique_sources(sources: list[str]) -> list[str]:
    result = []
    seen = set()
    for source in sources:
        normalized = str(source or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _season_number_from_provider_id(provider_id: object) -> int:
    match = _SEASON_PROVIDER_ID_RE.search(str(provider_id or "").strip())
    if match is None:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def _person_avatar(person: dict[str, object]) -> str:
    for key in ("avatar", "profile", "profile_url", "profile_path", "image", "photo"):
        value = str(person.get(key) or "").strip()
        if not value:
            continue
        if value.startswith("/"):
            return f"https://media.themoviedb.org/t/p/w300_and_h450_face{value}"
        return value
    return ""


def _person_link(person: dict[str, object]) -> str:
    for key in ("url", "link", "homepage"):
        value = str(person.get(key) or "").strip()
        if value:
            return value
    return ""


def _detail_latest_season_number(
    record: FollowingRecord,
    snapshot: FollowingDetailSnapshot | None = None,
) -> int:
    latest_episode = max(0, int(record.latest_episode or 0))
    base = resolve_progress_season(
        record.season_number,
        latest_episode,
        fallback_season=record.season_number,
    )
    current_season = max(0, int(record.current_season_number or 0))
    if current_season > base:
        base = current_season
    if snapshot is None:
        return base

    if base > 0 and latest_episode > 0:
        base_season_has_latest = any(
            (
                int(season.season_number or 0) == base
                and int(season.episode_count or 0) >= latest_episode
            )
            for season in snapshot.seasons
        )
        if base_season_has_latest and not (
            record.has_update and max(0, int(record.current_episode or 0)) <= 0
        ):
            if not (
                current_season == base
                and latest_episode <= max(0, int(record.current_episode or 0))
            ):
                return base

    exact_match_seasons = [
        int(episode.season_number)
        for episode in snapshot.episodes
        if int(episode.episode_number or 0) == latest_episode and int(episode.season_number or 0) > 0
    ]
    if (
        snapshot.next_episode is not None
        and int(snapshot.next_episode.episode_number or 0) == latest_episode
        and int(snapshot.next_episode.season_number or 0) > 0
    ):
        exact_match_seasons.append(int(snapshot.next_episode.season_number))
    if exact_match_seasons:
        exact_max = max(exact_match_seasons)
        if exact_max >= current_season:
            return exact_max

    if record.has_update and max(0, int(record.current_episode or 0)) <= 0:
        snapshot_seasons = [
            int(season.season_number)
            for season in snapshot.seasons
            if int(season.season_number or 0) > 0
        ]
        snapshot_seasons.extend(
            int(episode.season_number)
            for episode in snapshot.episodes
            if int(episode.season_number or 0) > 0
        )
        if snapshot.next_episode is not None and int(snapshot.next_episode.season_number or 0) > 0:
            snapshot_seasons.append(int(snapshot.next_episode.season_number))
        if latest_episode > 0 and snapshot_seasons:
            return max(max(snapshot_seasons), base)

    if base > 0 and latest_episode > 0:
        for season in snapshot.seasons:
            if (
                int(season.season_number or 0) == base
                and int(season.episode_count or 0) >= latest_episode
            ):
                return base

    snapshot_seasons = [int(season.season_number) for season in snapshot.seasons if int(season.season_number or 0) > 0]
    snapshot_seasons.extend(
        int(episode.season_number)
        for episode in snapshot.episodes
        if int(episode.season_number or 0) > 0
    )
    if snapshot.next_episode is not None and int(snapshot.next_episode.season_number or 0) > 0:
        snapshot_seasons.append(int(snapshot.next_episode.season_number))
    if latest_episode > 0 and snapshot_seasons:
        return max(max(snapshot_seasons), base)
    return base


def _display_total_episodes(
    record: FollowingRecord,
    snapshot: FollowingDetailSnapshot | None = None,
) -> int:
    completion_state = resolve_following_completion_state(
        episodes=snapshot.episodes if snapshot is not None else [],
        next_episode=snapshot.next_episode if snapshot is not None else None,
    )
    return resolve_display_total_episodes(
        total_episodes=record.total_episodes,
        latest_episode=record.latest_episode,
        completion_state=completion_state,
    )


def _normalize_loaded_season_episode(
    *,
    season_number: int,
    episode_number: int,
    total_episodes: int,
    seasons: list[FollowingSeason],
    episodes: list[FollowingEpisode],
    overflow_value: int | None,
) -> int:
    normalized_season = max(0, int(season_number or 0))
    normalized_episode = max(0, int(episode_number or 0))
    if normalized_season <= 0 or normalized_episode <= 0:
        return normalized_episode

    groups = build_episode_season_groups(
        episodes,
        seasons=seasons,
        fallback_season=normalized_season,
    )
    group = next(
        (item for item in groups if item.season_number == normalized_season),
        None,
    )
    if group is None or group.episode_count <= 0:
        return normalized_episode
    local_numbers = [
        int(episode.episode_number or 0)
        for episode in group.episodes
        if int(episode.episode_number or 0) > 0 and not episode.is_special
    ]
    if not local_numbers:
        return normalized_episode
    local_latest = max(local_numbers)
    if normalized_episode > local_latest and local_latest >= group.episode_count:
        if overflow_value is None:
            normalized_total = max(0, int(total_episodes or 0))
            if normalized_total > group.episode_count and normalized_episode <= normalized_total:
                return normalized_episode
        if overflow_value is None and any(
            int(episode.season_number or 0) == normalized_season
            and int(episode.episode_number or 0) > group.episode_count
            for episode in group.episodes
        ):
            return normalized_episode
        return local_latest if overflow_value is None else max(0, int(overflow_value))
    return normalized_episode


def _normalized_detail_progress_record(
    record: FollowingRecord,
    snapshot: FollowingDetailSnapshot | None,
) -> FollowingRecord:
    if snapshot is None:
        return record
    current_season_number = resolve_progress_season(
        record.current_season_number,
        record.current_episode,
        fallback_season=record.season_number,
    )
    latest_season_number = _detail_latest_season_number(record, snapshot)
    current_episode = _normalize_loaded_season_episode(
        season_number=current_season_number,
        episode_number=record.current_episode,
        total_episodes=record.total_episodes,
        seasons=list(snapshot.seasons or []),
        episodes=list(snapshot.episodes or []),
        overflow_value=0,
    )
    latest_episode = _normalize_loaded_season_episode(
        season_number=latest_season_number,
        episode_number=record.latest_episode,
        total_episodes=record.total_episodes,
        seasons=list(snapshot.seasons or []),
        episodes=list(snapshot.episodes or []),
        overflow_value=None,
    )
    if (
        current_season_number == record.current_season_number
        and current_episode == record.current_episode
        and latest_episode == record.latest_episode
    ):
        return record
    return replace(
        record,
        current_season_number=current_season_number,
        current_episode=current_episode,
        latest_episode=latest_episode,
    )


def _meta_text(record: FollowingRecord, snapshot: FollowingDetailSnapshot | None = None) -> str:
    if _resolve_effective_media_kind(record, snapshot) == "movie":
        parts = []
        if record.current_episode > 0 or record.last_played_at > 0:
            parts.append("已观看")
        else:
            parts.append("未观看")
        if record.has_update:
            parts.append("有更新")
        return " · ".join(parts)
    episode_parts = []
    completion_state = resolve_following_completion_state(
        episodes=snapshot.episodes if snapshot is not None else [],
        next_episode=snapshot.next_episode if snapshot is not None else None,
    )
    display_total = _display_total_episodes(record, snapshot)
    current_season_number = resolve_progress_season(
        record.current_season_number,
        record.current_episode,
        fallback_season=record.season_number,
    )
    latest_season_number = _detail_latest_season_number(record, snapshot)
    completed = False
    if (
        display_total > 0
        and completion_state == FollowingCompletionState.COMPLETED
        and record.latest_episode >= display_total
        and progress_at_or_beyond(
            current_season_number,
            record.current_episode,
            latest_season_number,
            display_total,
            current_fallback_season=record.season_number,
            latest_fallback_season=latest_season_number,
        )
    ):
        completed = True
        if latest_season_number > 0:
            episode_parts.extend(
                ["已看完", f"S{latest_season_number}共 {display_total} 集", "已完结"]
            )
        else:
            episode_parts.extend(["已看完", f"{display_total}集", "已完结"])
    else:
        current_text = format_progress_episode(
            "看到",
            current_season_number,
            record.current_episode,
            fallback_season=record.season_number,
        )
        if current_text:
            episode_parts.append(current_text)
    if completed:
        pass
    elif record.latest_episode > 0 and display_total > 0:
        latest_text = format_progress_episode(
            "最新",
            latest_season_number,
            record.latest_episode,
            fallback_season=record.season_number,
        )
        episode_parts.append(f"{latest_text} / 总 {display_total}")
    elif record.latest_episode > 0:
        episode_parts.append(
            format_progress_episode(
                "最新",
                latest_season_number,
                record.latest_episode,
                fallback_season=record.season_number,
            )
        )
    elif display_total > 0:
        episode_parts.append(f"总 {display_total}")
    parts = [
        *episode_parts,
        _detail_update_text(
            record,
            current_season_number=current_season_number,
            latest_season_number=latest_season_number,
            snapshot=snapshot,
        )
        if record.has_update
        else "",
    ]
    return " · ".join(part for part in parts if part)


def _detail_update_text(
    record: FollowingRecord,
    *,
    current_season_number: int,
    latest_season_number: int,
    snapshot: FollowingDetailSnapshot | None,
) -> str:
    count = resolve_new_episode_count(
        has_update=True,
        current_season_number=current_season_number,
        current_episode=record.current_episode,
        latest_season_number=latest_season_number,
        latest_episode=record.latest_episode,
        fallback_count=record.new_episode_count,
        total_episodes=record.total_episodes,
        seasons=snapshot.seasons if snapshot is not None else None,
        episodes=snapshot.episodes if snapshot is not None else None,
    )
    return f"有 {count} 集更新" if count > 0 else "有更新"


def _rating_strip_text(ratings: list[FollowingRatingEntry]) -> str:
    return "  ·  ".join(f"{item.label} {item.value}" for item in ratings if item.value)


def _format_source_snapshot_text(snapshot: FollowingMetadataSourceSnapshot, *, record: FollowingRecord | None = None) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if not value:
            continue
        parts.append(_metadata_field_html(label, value, record=record))
    overview = str(snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"{html.escape('简介:')}<br>{_metadata_value_html('简介', overview, record=record)}")
    return "<br>".join(parts) if parts else "暂无简介"


_MERGED_METADATA_LABEL_WHITELIST = {
    "类型",
    "年代",
    "地区",
    "语言",
    "导演",
    "编剧",
    "演员",
    "首播",
    "上映日期",
    "集数",
    "片长",
    "别名",
    "豆瓣ID",
    "IMDb ID",
    "TMDB ID",
}


def _format_merged_source_snapshot_text(snapshot: FollowingMetadataSourceSnapshot, *, record: FollowingRecord | None = None) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if label not in _MERGED_METADATA_LABEL_WHITELIST or not value:
            continue
        parts.append(_metadata_field_html(label, value, record=record))
    overview = str(snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"{html.escape('简介:')}<br>{_metadata_value_html('简介', overview, record=record)}")
    return "<br>".join(parts) if parts else "暂无简介"


def _playback_platform_text(entry: FollowingPlaybackPlatformEntry) -> str:
    parts = [entry.label]
    if entry.latest_episode > 0:
        parts.append(f"更新至第{entry.latest_episode}集")
    if entry.update_time_text:
        parts.append(entry.update_time_text)
    if entry.status_text:
        parts.append(entry.status_text)
    if entry.metric_value:
        metric_label = str(entry.metric_label or "").strip()
        parts.append(f"{metric_label} {entry.metric_value}".strip())
    return "  ·  ".join(part for part in parts if part)


def _playback_platforms_html(platforms: list[FollowingPlaybackPlatformEntry]) -> str:
    return "  ·  ".join(_playback_platform_entry_html(entry) for entry in platforms)


def _playback_platform_entry_html(entry: FollowingPlaybackPlatformEntry) -> str:
    label = str(entry.label or entry.provider or "").strip()
    label_html = external_link_html(entry.url, label) if entry.url else html.escape(label)
    parts = [label_html]
    if entry.latest_episode > 0:
        parts.append(html.escape(f"更新至第{entry.latest_episode}集"))
    if entry.update_time_text:
        parts.append(html.escape(entry.update_time_text))
    if entry.status_text:
        parts.append(html.escape(entry.status_text))
    if entry.metric_value:
        metric_label = str(entry.metric_label or "").strip()
        parts.append(html.escape(f"{metric_label} {entry.metric_value}".strip()))
    return " ".join(part for part in parts if part)


def _metadata_field_html(label: str, value: str, *, record: FollowingRecord | None = None) -> str:
    return f"{html.escape(label)}: {_metadata_value_html(label, value, record=record)}".rstrip()


def _metadata_value_html(label: str, value: str, *, record: FollowingRecord | None = None) -> str:
    url = _external_metadata_url(label, value, record=record)
    if url:
        return external_link_html(url, value)
    return html.escape(value).replace("\n", "<br>")


def _external_metadata_url(label: str, value: object, *, record: FollowingRecord | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    normalized_label = str(label or "").strip().lower()
    if normalized_label in {"豆瓣id", "dbid"}:
        return f"https://movie.douban.com/subject/{text}/"
    if normalized_label == "imdb id":
        return f"https://www.imdb.com/title/{text}"
    if normalized_label == "bangumi id":
        return f"https://bgm.tv/subject/{text}"
    if normalized_label == "tmdb id":
        media_type = "movie" if str(getattr(record, "media_kind", "") or "").strip().lower() == "movie" else "tv"
        provider_id = str(getattr(record, "provider_id", "") or "").strip()
        if provider_id.startswith("movie:"):
            media_type = "movie"
        return f"https://www.themoviedb.org/{media_type}/{text}"
    if normalized_label in {"bilibili id", "b站id", "season id"}:
        if re.match(r"^BV[0-9A-Za-z]+$", text):
            return f"https://www.bilibili.com/video/{text}"
        if text.isdigit():
            return f"https://www.bilibili.com/bangumi/play/ss{text}"
        ss_match = re.match(r"^ss(\d+)$", text, re.IGNORECASE)
        if ss_match is not None:
            return f"https://www.bilibili.com/bangumi/play/ss{ss_match.group(1)}"
    return ""


_DETAIL_SKIP_LABELS = {"更新时间", "更新状态"}


def _format_detail_text(snapshot: FollowingDetailSnapshot, *, record: FollowingRecord | None = None) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if label in _DETAIL_SKIP_LABELS or not value:
            continue
        parts.append(_metadata_field_html(label, value, record=record))
    overview = (snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"{html.escape('简介:')}<br>{_metadata_value_html('简介', overview, record=record)}")
    return "<br>".join(parts) if parts else "暂无简介"


def _image_placeholder_qss() -> str:
    tokens = current_tokens()
    return (
        f"border: 1px solid {tokens.border_subtle};"
        "border-radius: 12px;"
        f"background: {tokens.panel_alt_bg};"
        f"color: {tokens.text_secondary};"
    )


def _carousel_image_qss() -> str:
    tokens = current_tokens()
    return (
        "border: 0;"
        "border-radius: 12px;"
        "background: transparent;"
        f"color: {tokens.text_secondary};"
    )


def _person_inner_label_qss() -> str:
    tokens = current_tokens()
    return (
        "border: 0;"
        "border-radius: 0;"
        "background: transparent;"
        f"color: {tokens.text_secondary};"
    )


def _person_avatar_fallback_qss() -> str:
    tokens = current_tokens()
    return (
        "border: 0;"
        "border-radius: 10px;"
        f"background: {tokens.panel_alt_bg};"
        f"color: {tokens.text_secondary};"
        "font-size: 24px;"
        "font-weight: 600;"
    )


def _person_avatar_initial(person: dict[str, object]) -> str:
    name = str(person.get("name") or "").strip()
    if not name:
        return ""
    return name[:1].upper()
