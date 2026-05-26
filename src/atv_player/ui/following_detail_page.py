from __future__ import annotations

import shiboken6
import re
import threading

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from atv_player.following_models import (
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
    resolve_progress_season,
)
from atv_player.models import AppConfig
from atv_player.ui.following_episode_browser import (
    FollowingEpisodeBrowser,
    build_episode_season_groups,
)
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.poster_loader import load_local_poster_image, load_remote_poster_image, normalize_poster_url
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
        parent: QWidget | None = None
    ) -> None:
        super().__init__(title="设置追更进度", parent=parent)
        self._episode_counts = self._build_episode_counts(
            seasons=seasons,
            episodes=episodes,
            fallback_season=max(current_season_number, latest_season_number, 1),
        )
        self._latest_season_number = latest_season_number
        self._latest_episode = latest_episode
        self._total_episodes = total_episodes
        self.accepted_season_number = current_season_number
        self.accepted_episode = current_episode

        layout = self.content_layout()
        layout.setSpacing(14)

        info_parts = []
        latest_text = format_progress_episode(
            "最新",
            latest_season_number,
            latest_episode,
            fallback_season=latest_season_number,
        )
        if latest_text and total_episodes > 0:
            info_parts.append(f"{latest_text} / 总 {total_episodes}")
        elif latest_text:
            info_parts.append(latest_text)
        elif total_episodes > 0:
            info_parts.append(f"总 {total_episodes}")
        if info_parts:
            info_label = QLabel("  ·  ".join(info_parts), self)
            layout.addWidget(info_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("第", self))
        self.season_spin = QSpinBox(self)
        self.season_spin.setRange(self._season_minimum(), self._season_maximum())
        self.season_spin.setValue(max(self._season_minimum(), current_season_number or self._season_minimum()))
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

        self.season_spin.valueChanged.connect(self._handle_season_changed)
        self._update_episode_range(current_season_number, preferred_episode=current_episode)

        latest_pair_text = (
            "设为最新 "
            f"({format_progress_episode('', latest_season_number, latest_episode, fallback_season=latest_season_number).strip()})"
            if latest_episode > 0
            else ""
        )

        if latest_episode > 0:
            mark_btn = QPushButton(latest_pair_text, self)
            mark_btn.clicked.connect(self._set_to_latest)
            layout.addWidget(mark_btn)

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

    def _set_to_latest(self) -> None:
        self.season_spin.setValue(self._latest_season_number or self.season_spin.value())
        self.episode_spin.setValue(self._latest_episode)

    def _accept(self) -> None:
        self.accepted_season_number = int(self.season_spin.value())
        self.accepted_episode = int(self.episode_spin.value())
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


class FollowingDetailPage(QWidget, AsyncGuardMixin):
    back_requested = Signal()
    search_play_requested = Signal(int)
    unfollow_requested = Signal(int)
    image_loaded = Signal(object, object)
    check_finished = Signal(int, object, str)
    metadata_refresh_finished = Signal(int, object, str)
    season_detail_finished = Signal(int, int, object, str)

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
        self.status_label = QLabel()
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
        if self._snapshot_needs_refresh(self.current_view.snapshot):
            self.status_label.setText("详情暂无完整数据，可手动检查更新")
        elif self._should_load_selected_season():
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
        self.cast_scroll.setMinimumHeight(248)
        self.cast_scroll.setMaximumHeight(296)

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
        self.search_play_button.clicked.connect(self._emit_search_play)
        self.manual_check_button.clicked.connect(self._manual_check)
        self.refresh_metadata_button.clicked.connect(self._refresh_metadata)
        self.set_progress_button.clicked.connect(self._open_progress_dialog)
        self.unfollow_button.clicked.connect(self._emit_unfollow)

    def _render(
        self, record: FollowingRecord, snapshot: FollowingDetailSnapshot
    ) -> None:
        self.status_label.setText("")
        self.title_label.setText(record.title)
        self.meta_label.setText(_meta_text(record, snapshot))
        self._render_metadata_bundle(snapshot)
        self._render_poster_carousel(record, snapshot)
        groups = build_episode_season_groups(
            snapshot.episodes,
            seasons=snapshot.seasons,
            fallback_season=record.season_number,
        )
        latest_season_number = _detail_latest_season_number(record, snapshot)
        self.episode_browser.set_content(
            groups=groups,
            current_season_number=record.current_season_number,
            current_episode=record.current_episode,
            selected_season_number=self._selected_season_number,
            latest_episode=record.latest_episode,
            latest_season_number=latest_season_number,
            next_episode=snapshot.next_episode,
        )
        self.cast_widgets = []
        _clear_layout(self._cast_layout)
        self._pending_people = [*snapshot.cast, *snapshot.crew]
        self._render_next_batch()

    def _render_metadata_bundle(self, snapshot: FollowingDetailSnapshot) -> None:
        bundle = snapshot.metadata_bundle
        if bundle is None:
            self.rating_strip.setText("")
            self._render_source_buttons(["merged"], source_snapshots={})
            self._render_playback_platforms([])
            self.overview_label.setText(_format_detail_text(snapshot))
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
        if current_key == "merged":
            self.overview_label.setText(_format_merged_source_snapshot_text(bundle.merged_snapshot))
        else:
            self.overview_label.setText(_format_source_snapshot_text(current))

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
        for entry in platforms:
            row = QWidget(self.playback_platform_section)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            label = QLabel(_playback_platform_text(entry), row)
            label.setWordWrap(True)
            row_layout.addWidget(label, 1)
            self.playback_platform_widgets.append(label)
            if entry.url:
                button = QPushButton("打开链接", row)
                button.clicked.connect(
                    lambda _checked=False, url=entry.url: QDesktopServices.openUrl(QUrl(url))
                )
                row_layout.addWidget(button)
                self.playback_platform_buttons.append(button)
            self.playback_platform_layout.addWidget(row)

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
        record = self.current_view.record
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
    if snapshot is None:
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
        return max(exact_match_seasons)

    snapshot_seasons = [int(season.season_number) for season in snapshot.seasons if int(season.season_number or 0) > 0]
    snapshot_seasons.extend(
        int(episode.season_number)
        for episode in snapshot.episodes
        if int(episode.season_number or 0) > 0
    )
    if snapshot.next_episode is not None and int(snapshot.next_episode.season_number or 0) > 0:
        snapshot_seasons.append(int(snapshot.next_episode.season_number))
    if (
        latest_episode > 0
        and int(record.total_episodes or 0) > 0
        and latest_episode >= int(record.total_episodes or 0)
        and snapshot_seasons
    ):
        return max(snapshot_seasons)
    return base


def _meta_text(record: FollowingRecord, snapshot: FollowingDetailSnapshot | None = None) -> str:
    episode_parts = []
    current_season_number = resolve_progress_season(
        record.current_season_number,
        record.current_episode,
        fallback_season=record.season_number,
    )
    latest_season_number = _detail_latest_season_number(record, snapshot)
    completed = False
    if (
        record.total_episodes > 0
        and record.latest_episode >= record.total_episodes
        and progress_at_or_beyond(
            current_season_number,
            record.current_episode,
            latest_season_number,
            record.total_episodes,
            current_fallback_season=record.season_number,
            latest_fallback_season=latest_season_number,
        )
    ):
        completed = True
        if latest_season_number > 0:
            episode_parts.extend(["已看完", f"S{latest_season_number}共 {record.total_episodes} 集", "已完结"])
        else:
            episode_parts.extend(["已看完", f"{record.total_episodes}集", "已完结"])
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
    elif record.latest_episode > 0 and record.total_episodes > 0:
        latest_text = format_progress_episode(
            "最新",
            latest_season_number,
            record.latest_episode,
            fallback_season=record.season_number,
        )
        episode_parts.append(f"{latest_text} / 总 {record.total_episodes}")
    elif record.latest_episode > 0:
        episode_parts.append(
            format_progress_episode(
                "最新",
                latest_season_number,
                record.latest_episode,
                fallback_season=record.season_number,
            )
        )
    elif record.total_episodes > 0:
        episode_parts.append(f"总 {record.total_episodes}")
    parts = [
        *episode_parts,
        "有更新" if record.has_update else "",
    ]
    return " · ".join(part for part in parts if part)


def _rating_strip_text(ratings: list[FollowingRatingEntry]) -> str:
    return "  ·  ".join(f"{item.label} {item.value}" for item in ratings if item.value)


def _format_source_snapshot_text(snapshot: FollowingMetadataSourceSnapshot) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if not value:
            continue
        parts.append(f"{label}: {value}")
    overview = str(snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"简介:\n{overview}")
    return "\n".join(parts) if parts else "暂无简介"


_MERGED_METADATA_LABEL_WHITELIST = {
    "类型",
    "年代",
    "地区",
    "语言",
    "导演",
    "演员",
    "别名",
    "豆瓣ID",
    "IMDb ID",
    "TMDB ID",
}


def _format_merged_source_snapshot_text(snapshot: FollowingMetadataSourceSnapshot) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if label not in _MERGED_METADATA_LABEL_WHITELIST or not value:
            continue
        parts.append(f"{label}: {value}")
    overview = str(snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"简介:\n{overview}")
    return "\n".join(parts) if parts else "暂无简介"


def _playback_platform_text(entry: FollowingPlaybackPlatformEntry) -> str:
    parts = [entry.label]
    if entry.latest_episode > 0:
        parts.append(f"更新至第{entry.latest_episode}集")
    if entry.update_time_text:
        parts.append(entry.update_time_text)
    if entry.status_text:
        parts.append(entry.status_text)
    return "  ·  ".join(part for part in parts if part)


_DETAIL_SKIP_LABELS = {"更新时间", "更新状态"}


def _format_detail_text(snapshot: FollowingDetailSnapshot) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if label in _DETAIL_SKIP_LABELS or not value:
            continue
        parts.append(f"{label}: {value}")
    overview = (snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"简介:\n{overview}")
    return "\n".join(parts) if parts else "暂无简介"


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
