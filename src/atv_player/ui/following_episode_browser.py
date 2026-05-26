from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from atv_player.following_models import (
    FollowingEpisode,
    FollowingEpisodeState,
    FollowingSeason,
    resolve_following_episode_state,
    resolve_progress_season,
)
from atv_player.time_utils import beijing_timezone
from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)
from atv_player.ui.theme import current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class EpisodeDisplayMode:
    COMPACT = "compact"
    POSTER = "poster"
    FULL = "full"


EPISODE_ROLE = Qt.ItemDataRole.UserRole
WATCHED_ROLE = Qt.ItemDataRole.UserRole + 1
DISPLAY_MODE_ROLE = Qt.ItemDataRole.UserRole + 2
AIR_DATE_ROLE = Qt.ItemDataRole.UserRole + 3
OVERVIEW_ROLE = Qt.ItemDataRole.UserRole + 4
STILL_ROLE = Qt.ItemDataRole.UserRole + 5
SPECIAL_ROLE = Qt.ItemDataRole.UserRole + 6
STATUS_ROLE = Qt.ItemDataRole.UserRole + 7
STATUS_TEXT_ROLE = Qt.ItemDataRole.UserRole + 8
BEIJING_TZ = beijing_timezone()


@dataclass(frozen=True, slots=True)
class EpisodeCardMetrics:
    item_height: int
    thumbnail_width: int
    thumbnail_height: int
    outer_margin_x: int
    outer_margin_y: int
    inner_spacing: int
    title_height: int
    meta_height: int
    overview_height: int
    badge_height: int
    badge_padding_x: int
    badge_padding_y: int
    corner_radius: int


@dataclass(frozen=True, slots=True)
class EpisodeSeasonGroup:
    season_number: int
    display_title: str
    episodes: list[FollowingEpisode]
    episode_count: int = 0
    overview: str = ""
    poster: str = ""
    air_date: str = ""


@dataclass(frozen=True, slots=True)
class EpisodeSeasonSummary:
    season_number: int
    title: str
    overview: str
    poster: str
    air_date: str
    episode_count: int


def build_episode_season_groups(
    episodes: list[FollowingEpisode],
    *,
    seasons: list[FollowingSeason] | None = None,
    fallback_season: int,
) -> list[EpisodeSeasonGroup]:
    grouped_episodes: dict[int, list[FollowingEpisode]] = {}
    default_season = fallback_season if fallback_season > 0 else 1
    for episode in episodes:
        season_number = episode.season_number if episode.season_number > 0 else default_season
        grouped_episodes.setdefault(season_number, []).append(episode)

    groups: list[EpisodeSeasonGroup] = []
    seen: set[int] = set()
    for season in sorted(seasons or [], key=lambda item: item.season_number):
        season_number = season.season_number if season.season_number > 0 else 0
        loaded_episodes = sorted(grouped_episodes.get(season_number, []), key=lambda item: item.episode_number)
        groups.append(
            EpisodeSeasonGroup(
                season_number=season_number,
                display_title=season.title.strip() or (f"第 {season_number} 季" if season_number > 0 else "特别篇"),
                episodes=loaded_episodes,
                episode_count=max(season.episode_count, len(loaded_episodes)),
                overview=season.overview,
                poster=season.poster,
                air_date=season.air_date,
            )
        )
        seen.add(season_number)

    for season_number, items in sorted(grouped_episodes.items()):
        if season_number in seen:
            continue
        groups.append(
            EpisodeSeasonGroup(
                season_number=season_number,
                display_title=f"第 {season_number} 季" if season_number > 0 else "特别篇",
                episodes=sorted(items, key=lambda item: item.episode_number),
                episode_count=len(items),
                overview="",
                poster="",
                air_date="",
            )
        )

    if not groups:
        groups.append(
            EpisodeSeasonGroup(
                season_number=default_season,
                display_title=f"第 {default_season} 季",
                episodes=[],
                episode_count=0,
                overview="",
                poster="",
                air_date="",
            )
        )
    return groups


def format_episode_title(episode: FollowingEpisode) -> str:
    title = episode.title.strip() or f"第 {episode.episode_number} 集"
    return f"{episode.episode_number}. {title}"


class SeasonListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups: list[EpisodeSeasonGroup] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._groups)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        group = self._groups[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{group.display_title} · {group.episode_count} 集"
        if role == Qt.ItemDataRole.UserRole:
            return group
        return None

    def set_groups(self, groups: list[EpisodeSeasonGroup]) -> None:
        self.beginResetModel()
        self._groups = list(groups)
        self.endResetModel()

    def group_at(self, row: int) -> EpisodeSeasonGroup | None:
        if row < 0 or row >= len(self._groups):
            return None
        return self._groups[row]


class EpisodeListModel(QAbstractListModel):
    def __init__(self, *, display_mode: str = EpisodeDisplayMode.POSTER, parent=None) -> None:
        super().__init__(parent)
        self._episodes: list[FollowingEpisode] = []
        self._current_episode = 0
        self._current_season_number = 0
        self._visible_season_number = 0
        self._latest_episode = 0
        self._latest_season_number = 0
        self._next_episode: FollowingEpisode | None = None
        self.display_mode = display_mode
        self._thumbnail_store: EpisodeThumbnailStore | None = None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._episodes)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        episode = self._episodes[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return format_episode_title(episode)
        if role == EPISODE_ROLE:
            return episode
        if role == WATCHED_ROLE:
            return self._episode_state(episode) == FollowingEpisodeState.WATCHED
        if role == DISPLAY_MODE_ROLE:
            return self.display_mode
        if role == AIR_DATE_ROLE:
            return episode.air_date or ""
        if role == OVERVIEW_ROLE:
            return episode.overview or ""
        if role == STILL_ROLE:
            return episode.still or ""
        if role == SPECIAL_ROLE:
            return bool(episode.is_special)
        if role == STATUS_ROLE:
            return self._episode_state(episode)
        if role == STATUS_TEXT_ROLE:
            return _episode_status_text(self._episode_state(episode))
        return None

    def set_episodes(
        self,
        episodes: list[FollowingEpisode],
        *,
        current_episode: int,
        current_season_number: int = 0,
        visible_season_number: int = 0,
        latest_episode: int = 0,
        latest_season_number: int = 0,
        next_episode: FollowingEpisode | None = None,
    ) -> None:
        self.beginResetModel()
        self._episodes = list(episodes)
        self._current_episode = max(0, int(current_episode))
        self._current_season_number = max(0, int(current_season_number))
        self._visible_season_number = max(0, int(visible_season_number))
        self._latest_episode = max(0, int(latest_episode))
        self._latest_season_number = max(0, int(latest_season_number))
        self._next_episode = next_episode or _nearest_future_episode(
            self._episodes,
            today=datetime.now(BEIJING_TZ).date(),
            visible_season_number=self._visible_season_number,
        )
        self.endResetModel()

    def set_display_mode(self, display_mode: str) -> None:
        if self.display_mode == display_mode:
            return
        self.display_mode = display_mode
        if self.rowCount() <= 0:
            return
        top = self.index(0, 0)
        bottom = self.index(self.rowCount() - 1, 0)
        self.dataChanged.emit(top, bottom)

    def row_for_episode_number(self, episode_number: int) -> int:
        normalized = max(0, int(episode_number))
        for row, episode in enumerate(self._episodes):
            if episode.episode_number == normalized:
                return row
        return -1

    def attach_thumbnail_store(self, store: "EpisodeThumbnailStore") -> None:
        self._thumbnail_store = store
        store.thumbnail_ready.connect(self._handle_thumbnail_ready)

    def _episode_state(self, episode: FollowingEpisode) -> str:
        return resolve_following_episode_state(
            episode=episode,
            current_season_number=self._current_season_number,
            current_episode=self._current_episode,
            latest_season_number=self._latest_season_number,
            latest_episode=self._latest_episode,
            visible_season_number=self._visible_season_number,
            next_episode=self._next_episode,
        )

    def _handle_thumbnail_ready(self, source: str) -> None:
        for row, episode in enumerate(self._episodes):
            if str(episode.still or "").strip() != source:
                continue
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])


class EpisodeThumbnailStore(QObject):
    thumbnail_ready = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cache: dict[str, QImage] = {}
        self._pending: set[str] = set()

    def image_for(self, source: str) -> QImage | None:
        return self._cache.get(str(source or "").strip())

    def request(self, source: str, *, target_size: QSize) -> None:
        key = str(source or "").strip()
        if not key or key in self._cache or key in self._pending:
            return
        image_url = normalize_poster_url(key)
        if not image_url:
            return
        self._pending.add(key)

        def load() -> None:
            image = load_local_poster_image(key, target_size)
            if image is None:
                image = load_remote_poster_image(image_url, target_size)
            if image is not None:
                self._handle_thumbnail_ready(key, image)
                return
            self._pending.discard(key)

        threading.Thread(target=load, daemon=True).start()

    def _handle_thumbnail_ready(self, source: str, image: QImage) -> None:
        key = str(source or "").strip()
        if not key:
            return
        self._pending.discard(key)
        self._cache[key] = image
        self.thumbnail_ready.emit(key)


class EpisodeItemDelegate(QStyledItemDelegate):
    def __init__(self, thumbnail_store: EpisodeThumbnailStore, parent=None) -> None:
        super().__init__(parent)
        self._thumbnail_store = thumbnail_store

    def sizeHint(self, option, index) -> QSize:
        del option
        metrics = _card_metrics_for_mode(str(index.data(DISPLAY_MODE_ROLE) or EpisodeDisplayMode.FULL))
        view = self.parent()
        grid_width = 0
        if isinstance(view, QListView):
            grid_width = max(0, view.gridSize().width())
        return QSize(max(1, grid_width), metrics.item_height)

    def paint(self, painter: QPainter, option, index) -> None:
        tokens = current_tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        background = QColor(tokens.panel_alt_bg if selected else tokens.panel_bg)
        state = str(index.data(STATUS_ROLE) or FollowingEpisodeState.PENDING)
        border = QColor(tokens.accent if selected else _episode_status_border_color(tokens, state))
        painter.setBrush(background)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, 12, 12)

        episode = index.data(EPISODE_ROLE)
        if episode is None:
            painter.restore()
            return
        mode = index.data(DISPLAY_MODE_ROLE) or EpisodeDisplayMode.POSTER
        metrics = _card_metrics_for_mode(str(mode))
        is_special = bool(index.data(SPECIAL_ROLE))
        title = format_episode_title(episode)
        status_text = str(index.data(STATUS_TEXT_ROLE) or "").strip()
        meta_text = _episode_meta_text(episode)
        overview = str(index.data(OVERVIEW_ROLE) or "").strip()
        still = str(index.data(STILL_ROLE) or "").strip()

        content_rect = rect.adjusted(
            metrics.outer_margin_x,
            metrics.outer_margin_y,
            -metrics.outer_margin_x,
            -metrics.outer_margin_y,
        )
        thumb_rect = QRect(
            content_rect.left(),
            content_rect.top(),
            metrics.thumbnail_width,
            metrics.thumbnail_height,
        )
        self._draw_thumbnail(painter, thumb_rect, still)
        text_rect = QRect(content_rect)
        text_rect.setLeft(thumb_rect.right() + metrics.inner_spacing)

        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(tokens.text_primary))
        title_line_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), metrics.title_height)
        badge_width = 0
        if status_text:
            badge_width = _status_badge_width(
                painter,
                status_text,
                padding_x=metrics.badge_padding_x,
            ) + 8
        painter.drawText(
            title_line_rect.adjusted(0, 0, -badge_width, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            title,
        )
        if status_text:
            badge_text_width = _status_badge_width(
                painter,
                status_text,
                padding_x=metrics.badge_padding_x,
            )
            badge_rect = QRect(
                title_line_rect.right() - badge_text_width,
                title_line_rect.top(),
                badge_text_width,
                metrics.badge_height,
            )
            _draw_status_badge(
                painter,
                badge_rect,
                status_text,
                state,
                radius=max(8, metrics.badge_height // 2),
            )

        meta_y = title_line_rect.bottom() + 6
        if is_special and "特别篇" not in meta_text:
            meta_text = " · ".join([part for part in (meta_text, "特别篇") if part])

        meta_font = painter.font()
        meta_font.setBold(False)
        painter.setFont(meta_font)
        painter.setPen(QColor(tokens.text_secondary))
        painter.drawText(
            QRect(text_rect.left(), meta_y, text_rect.width(), metrics.meta_height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            meta_text,
        )

        if overview:
            overview_rect = QRect(
                text_rect.left(),
                meta_y + metrics.meta_height + 4,
                text_rect.width(),
                metrics.overview_height,
            )
            painter.drawText(
                overview_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                overview,
            )

        painter.restore()

    def _draw_thumbnail(self, painter: QPainter, rect: QRect, source: str) -> None:
        tokens = current_tokens()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.panel_alt_bg))
        painter.drawRoundedRect(rect, 8, 8)
        image = self._thumbnail_store.image_for(source)
        if image is None:
            self._thumbnail_store.request(source, target_size=rect.size())
            painter.setPen(QColor(tokens.text_secondary))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "封面")
            return
        painter.drawImage(rect, image)


class FollowingEpisodeCard(QFrame):
    activated = Signal(object)

    def __init__(
        self,
        episode: FollowingEpisode,
        *,
        summary_columns: int,
        thumbnail_store: EpisodeThumbnailStore,
        status: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.episode = episode
        self.summary_columns = summary_columns
        self._thumbnail_store = thumbnail_store
        self._thumbnail_source = str(episode.still or "").strip()
        self.setObjectName("followingEpisodeCard")
        self.setProperty("episode_status", status)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(164 if summary_columns == 1 else 148 if summary_columns == 2 else 138)
        self.setStyleSheet(_episode_card_stylesheet(status))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.still_label = QLabel("封面", self)
        self.still_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still_label.setFixedSize(148 if summary_columns == 1 else 116, 84 if summary_columns == 1 else 68)
        self.still_label.setStyleSheet("border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.title_label = QLabel(format_episode_title(episode), self)
        self.title_label.setWordWrap(True)
        self.status_badge_label = QLabel(_episode_status_text(status), self)
        self.status_badge_label.setObjectName("followingEpisodeStatusBadge")
        self.status_badge_label.setProperty("episode_status", status)
        self.status_badge_label.setStyleSheet(_episode_status_badge_stylesheet(status))
        self.meta_label = QLabel(_episode_meta_text(episode), self)
        self.meta_label.setWordWrap(True)
        self.overview_label = QLabel(episode.overview or "", self)
        self.overview_label.setWordWrap(True)
        self.overview_label.setMaximumHeight(_overview_max_height(summary_columns))

        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.status_badge_label, 0, Qt.AlignmentFlag.AlignTop)
        text_layout.addLayout(title_row)
        text_layout.addWidget(self.meta_label)
        text_layout.addWidget(self.overview_label)
        text_layout.addStretch(1)

        layout.addWidget(self.still_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)

        self.refresh_thumbnail()

    def refresh_for_columns(self, columns: int) -> None:
        self.summary_columns = columns
        self.setMinimumHeight(164 if columns == 1 else 148 if columns == 2 else 138)
        self.still_label.setFixedSize(148 if columns == 1 else 116, 84 if columns == 1 else 68)
        self.overview_label.setMaximumHeight(_overview_max_height(columns))

    def refresh_thumbnail(self) -> None:
        if not self._thumbnail_source:
            return
        image = self._thumbnail_store.image_for(self._thumbnail_source)
        if image is None:
            self._thumbnail_store.request(self._thumbnail_source, target_size=self.still_label.size())
            return
        self.still_label.setText("")
        self.still_label.setPixmap(QPixmap.fromImage(image))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.episode)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SeasonPosterLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FollowingSeasonPosterPreviewDialog(ThemedDialogBase):
    _image_loaded = Signal(QLabel, object)

    def __init__(
        self, title: str, poster_source: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(title=title or "季封面", parent=parent, resizable=True)
        self._poster_source = poster_source

        layout = self.content_layout()
        self.poster_label = QLabel("季封面", self)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setMinimumSize(720, 1080)
        self.poster_label.setStyleSheet(_image_placeholder_qss())
        layout.addWidget(self.poster_label)

        self._image_loaded.connect(self._handle_image_loaded)
        self._load_poster()

    def _load_poster(self) -> None:
        image_url = normalize_poster_url(self._poster_source)
        if not image_url:
            self.poster_label.setText("暂无季封面")
            return
        target_size = self.poster_label.minimumSize()
        if target_size.isEmpty():
            target_size = QSize(480, 720)

        def load() -> None:
            image = load_local_poster_image(self._poster_source, target_size)
            if image is None:
                image = load_remote_poster_image(image_url, target_size)
            if image is not None:
                self._image_loaded.emit(self.poster_label, image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_image_loaded(self, label: QLabel, image) -> None:
        label.setText("")
        target_size = label.size()
        if target_size.isEmpty():
            target_size = label.minimumSize()
        pixmap = QPixmap.fromImage(image).scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(pixmap)


class FollowingEpisodeBrowser(QWidget):
    episode_activated = Signal(object)
    grid_columns_changed = Signal(int)
    season_changed = Signal(int)

    def __init__(self, *, initial_grid_columns: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._groups: list[EpisodeSeasonGroup] = []
        self._current_episode = 0
        self._current_season_number = 0
        self._latest_episode = 0
        self._latest_season_number = 0
        self._next_episode: FollowingEpisode | None = None
        self._current_group: EpisodeSeasonGroup | None = None
        self._current_season_summary = EpisodeSeasonSummary(0, "", "", "", "", 0)
        self._season_state: dict[int, tuple[int, int]] = {}
        self._season_change_in_progress = False
        self._grid_columns = self._normalize_grid_columns(initial_grid_columns)
        self.episode_cards: list[FollowingEpisodeCard] = []

        self.browser_frame = QFrame(self)
        self.browser_frame.setObjectName("followingEpisodeBrowser")

        self.season_list = QListView(self.browser_frame)
        self.season_list.setObjectName("followingEpisodeSeasonList")
        self.season_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.season_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.season_detail_panel = QFrame(self.browser_frame)
        self.season_detail_panel.setObjectName("followingEpisodeSeasonDetailPanel")
        self.season_detail_poster_label = SeasonPosterLabel("季封面", self.season_detail_panel)
        self.season_detail_title_label = QLabel("", self.season_detail_panel)
        self.season_detail_air_date_label = QLabel("", self.season_detail_panel)
        self.season_detail_episode_count_label = QLabel("", self.season_detail_panel)
        self.season_detail_overview_label = QLabel("", self.season_detail_panel)
        self.season_detail_poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.season_detail_poster_label.setMinimumSize(128, 182)
        self.season_detail_poster_label.setMaximumSize(128, 182)
        self.season_detail_title_label.setWordWrap(True)
        self.season_detail_air_date_label.setWordWrap(True)
        self.season_detail_episode_count_label.setWordWrap(True)
        self.season_detail_overview_label.setWordWrap(True)
        selectable_flags = Qt.TextInteractionFlag.TextSelectableByMouse
        self.season_detail_title_label.setTextInteractionFlags(selectable_flags)
        self.season_detail_air_date_label.setTextInteractionFlags(selectable_flags)
        self.season_detail_episode_count_label.setTextInteractionFlags(selectable_flags)
        self.season_detail_overview_label.setTextInteractionFlags(selectable_flags)
        self.season_detail_top_row = QWidget(self.season_detail_panel)
        self.season_detail_info_layout = QVBoxLayout()
        self.season_detail_info_layout.setContentsMargins(0, 0, 0, 0)
        self.season_detail_info_layout.setSpacing(6)
        self.season_detail_info_layout.addWidget(self.season_detail_title_label)
        self.season_detail_info_layout.addWidget(self.season_detail_episode_count_label)
        self.season_detail_info_layout.addWidget(self.season_detail_air_date_label)
        self.season_detail_info_layout.addStretch(1)

        season_detail_top_row_layout = QHBoxLayout(self.season_detail_top_row)
        season_detail_top_row_layout.setContentsMargins(0, 0, 0, 0)
        season_detail_top_row_layout.setSpacing(14)
        season_detail_top_row_layout.addWidget(
            self.season_detail_poster_label, 0, Qt.AlignmentFlag.AlignTop
        )
        season_detail_top_row_layout.addLayout(self.season_detail_info_layout, 1)
        self.season_detail_poster_label.clicked.connect(self._open_current_season_poster_preview)

        season_detail_layout = QVBoxLayout(self.season_detail_panel)
        season_detail_layout.setContentsMargins(10, 10, 10, 10)
        season_detail_layout.setSpacing(12)
        season_detail_layout.addWidget(self.season_detail_top_row)
        season_detail_layout.addWidget(self.season_detail_overview_label)
        season_detail_layout.addStretch(1)

        self.episode_list_panel = QFrame(self.browser_frame)
        self.episode_list_panel.setObjectName("followingEpisodeListPanel")
        self.grid_cycle_button = QPushButton("▮", self.episode_list_panel)
        self.grid_cycle_button.setObjectName("followingEpisodeGridCycleButton")
        self.grid_cycle_button.clicked.connect(self._cycle_grid_columns)

        self.episode_list = QListView(self.episode_list_panel)
        self.episode_list.setObjectName("followingEpisodeList")
        self.episode_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.episode_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.episode_list.setViewMode(QListView.ViewMode.IconMode)
        self.episode_list.setFlow(QListView.Flow.LeftToRight)
        self.episode_list.setWrapping(True)
        self.episode_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.episode_list.setMovement(QListView.Movement.Static)
        self.episode_list.setWordWrap(True)
        self.episode_list.setSpacing(10)
        self.episode_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.episode_list.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

        self.season_model = SeasonListModel(self)
        self.episode_model = EpisodeListModel(
            display_mode=EpisodeDisplayMode.FULL,
            parent=self,
        )
        self.thumbnail_store = EpisodeThumbnailStore(self)
        self.episode_model.attach_thumbnail_store(self.thumbnail_store)
        self.thumbnail_store.thumbnail_ready.connect(self._handle_card_thumbnail_ready)
        self.season_list.setModel(self.season_model)
        self.episode_list.setModel(self.episode_model)
        self.episode_list.setItemDelegate(EpisodeItemDelegate(self.thumbnail_store, self.episode_list))
        self.episode_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.episode_list.setHidden(False)
        self.episode_list.viewport().installEventFilter(self)

        self.episode_grid_container = QWidget(self.episode_list_panel)
        self.episode_grid_layout = QGridLayout(self.episode_grid_container)
        self.episode_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.episode_grid_layout.setHorizontalSpacing(10)
        self.episode_grid_layout.setVerticalSpacing(10)
        self.episode_grid_layout.setColumnStretch(0, 1)

        self.episode_scroll = QScrollArea(self.episode_list_panel)
        self.episode_scroll.setWidgetResizable(True)
        self.episode_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.episode_scroll.setWidget(self.episode_grid_container)
        self.episode_scroll.setHidden(True)

        episode_list_layout = QVBoxLayout(self.episode_list_panel)
        episode_list_layout.setContentsMargins(0, 0, 0, 0)
        episode_list_layout.setSpacing(8)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.grid_cycle_button)
        episode_list_layout.addLayout(toolbar_layout)
        episode_list_layout.addWidget(self.episode_scroll)
        episode_list_layout.addWidget(self.episode_list)

        frame_layout = QHBoxLayout(self.browser_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(12)
        frame_layout.addWidget(self.season_list, 2)
        frame_layout.addWidget(self.season_detail_panel, 3)
        frame_layout.addWidget(self.episode_list_panel, 6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.browser_frame)

        self.season_list.selectionModel().currentChanged.connect(
            self._handle_current_season_changed
        )
        self.episode_list.clicked.connect(self._handle_episode_activated)
        self.episode_list.activated.connect(self._handle_episode_activated)
        self.episode_list.doubleClicked.connect(self._handle_episode_activated)
        self._refresh_grid_cycle_button()

    def grid_columns(self) -> int:
        return self._grid_columns

    def display_mode(self) -> str:
        return self.episode_model.display_mode

    def set_grid_columns(self, columns: int) -> None:
        normalized = self._normalize_grid_columns(columns)
        if normalized == self._grid_columns:
            return
        self._grid_columns = normalized
        self._refresh_grid_cycle_button()
        self.episode_model.set_display_mode(_display_mode_for_grid_columns(normalized))
        self._apply_episode_grid_metrics()
        self.grid_columns_changed.emit(normalized)

    def current_season_summary(self) -> EpisodeSeasonSummary:
        return self._current_season_summary

    def set_content(
        self,
        *,
        groups: list[EpisodeSeasonGroup],
        current_episode: int,
        current_season_number: int = 0,
        selected_season_number: int = 0,
        latest_episode: int = 0,
        latest_season_number: int = 0,
        next_episode: FollowingEpisode | None = None,
    ) -> None:
        self._groups = list(groups)
        self._current_episode = max(0, int(current_episode))
        self._current_season_number = max(0, int(current_season_number))
        self._latest_episode = max(0, int(latest_episode))
        self._latest_season_number = max(0, int(latest_season_number))
        self._next_episode = next_episode
        self._season_state = {}
        self.season_model.set_groups(self._groups)
        self.episode_model.set_display_mode(_display_mode_for_grid_columns(self._grid_columns))
        if self._groups:
            initial_row = self._initial_season_row(selected_season_number)
            self._set_current_season_row(initial_row)
        else:
            self.episode_model.set_episodes(
                [],
                current_episode=self._current_episode,
                current_season_number=self._current_season_number,
                visible_season_number=0,
                latest_episode=self._latest_episode,
                latest_season_number=self._latest_season_number,
                next_episode=self._next_episode,
            )
            self._apply_episode_grid_metrics()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_episode_grid_metrics()

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.episode_list.viewport()
            and event is not None
            and event.type() in {QEvent.Type.Resize, QEvent.Type.Show}
        ):
            self._apply_episode_grid_metrics()
        return super().eventFilter(watched, event)

    def current_season_number(self) -> int:
        index = self.season_list.currentIndex()
        group = self.season_model.group_at(index.row()) if index.isValid() else None
        return group.season_number if group is not None else 0

    def _set_current_season_row(self, row: int) -> None:
        group = self.season_model.group_at(row)
        if group is None:
            self.episode_model.set_episodes(
                [],
                current_episode=self._current_episode,
                current_season_number=self._current_season_number,
                visible_season_number=0,
                latest_episode=self._latest_episode,
                latest_season_number=self._latest_season_number,
                next_episode=self._next_episode,
            )
            return
        index = self.season_model.index(row, 0)
        self._season_change_in_progress = True
        self.season_list.setCurrentIndex(index)
        self._season_change_in_progress = False
        self._apply_group(group, restore_state=True)

    def _handle_current_season_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if self._season_change_in_progress or not current.isValid():
            return
        self._remember_season_state(previous)
        group = self.season_model.group_at(current.row())
        if group is not None:
            self._apply_group(group, restore_state=True)
            self.season_changed.emit(group.season_number)

    def _handle_episode_activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        episode = self.episode_model.data(index, EPISODE_ROLE)
        if episode is not None:
            self.episode_activated.emit(episode)

    def _remember_season_state(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        group = self.season_model.group_at(index.row())
        if group is None:
            return
        self._season_state[group.season_number] = (
            self.episode_list.currentIndex().row(),
            self.episode_list.verticalScrollBar().value(),
        )

    def _apply_group(self, group: EpisodeSeasonGroup, *, restore_state: bool) -> None:
        self.episode_model.set_episodes(
            group.episodes,
            current_episode=self._current_episode,
            current_season_number=self._current_season_number,
            visible_season_number=group.season_number,
            latest_episode=self._latest_episode,
            latest_season_number=self._latest_season_number,
            next_episode=self._next_episode,
        )
        self._current_group = group
        self._current_season_summary = self._build_season_summary(group)
        self._refresh_season_detail_panel()
        self.episode_cards = []
        self._apply_episode_grid_metrics()
        if not group.episodes:
            return
        if restore_state and group.season_number in self._season_state:
            row, scroll_value = self._season_state[group.season_number]
            if row >= 0:
                self.episode_list.setCurrentIndex(self.episode_model.index(row, 0))
            self.episode_list.verticalScrollBar().setValue(max(0, scroll_value))
            return
        visible_season_number = resolve_progress_season(
            group.season_number,
            self._current_episode,
            fallback_season=group.season_number,
        )
        current_season_number = resolve_progress_season(
            self._current_season_number,
            self._current_episode,
            fallback_season=visible_season_number,
        )
        target_row = (
            self.episode_model.row_for_episode_number(self._current_episode)
            if visible_season_number == current_season_number
            else -1
        )
        if target_row < 0:
            target_row = 0
        target_index = self.episode_model.index(target_row, 0)
        self.episode_list.setCurrentIndex(target_index)
        self.episode_list.scrollTo(
            target_index,
            QListView.ScrollHint.PositionAtCenter,
        )

    def _initial_season_row(self, selected_season_number: int) -> int:
        if selected_season_number > 0:
            for row, group in enumerate(self._groups):
                if group.season_number == selected_season_number:
                    return row
        if self._current_season_number > 0:
            for row, group in enumerate(self._groups):
                if group.season_number == self._current_season_number:
                    return row
        if self._current_episode <= 0:
            return 0
        for row, group in enumerate(self._groups):
            for episode in group.episodes:
                if episode.episode_number == self._current_episode:
                    return row
        return 0

    @staticmethod
    def _normalize_grid_columns(columns: int) -> int:
        try:
            normalized = int(columns)
        except (TypeError, ValueError):
            return 1
        return normalized if normalized in {1, 2, 3} else 1

    def _apply_episode_grid_metrics(self) -> None:
        metrics = _card_metrics_for_columns(self._grid_columns)
        spacing = max(0, self.episode_list.spacing())
        viewport_width = max(1, self.episode_list.viewport().width() or self.episode_list.width() or 1)
        usable_width = max(1, viewport_width - spacing * max(0, self._grid_columns - 1))
        card_width = max(1, usable_width // self._grid_columns)
        self.episode_list.setGridSize(QSize(card_width, metrics.item_height))
        self.episode_list.doItemsLayout()

    def _cycle_grid_columns(self) -> None:
        self.set_grid_columns({1: 2, 2: 3, 3: 1}[self._grid_columns])

    def _build_season_summary(self, group: EpisodeSeasonGroup) -> EpisodeSeasonSummary:
        return EpisodeSeasonSummary(
            season_number=group.season_number,
            title=group.display_title,
            overview=str(group.overview or "").strip(),
            poster=str(group.poster or "").strip(),
            air_date=str(group.air_date or "").strip(),
            episode_count=max(0, int(group.episode_count or 0)),
        )

    def _rebuild_episode_cards(self, episodes: list[FollowingEpisode]) -> None:
        _clear_layout(self.episode_grid_layout)
        for column in range(self.episode_grid_layout.columnCount()):
            self.episode_grid_layout.setColumnStretch(column, 0)
        self.episode_cards = []
        if not episodes:
            return
        for index, episode in enumerate(episodes):
            status = self.status_for_episode(episode)
            card = FollowingEpisodeCard(
                episode,
                summary_columns=self._grid_columns,
                thumbnail_store=self.thumbnail_store,
                status=status,
                parent=self.episode_grid_container,
            )
            card.activated.connect(self.episode_activated.emit)
            row = index // self._grid_columns
            column = index % self._grid_columns
            self.episode_grid_layout.addWidget(card, row, column)
            self.episode_cards.append(card)
        for column in range(self._grid_columns):
            self.episode_grid_layout.setColumnStretch(column, 1)

    def _relayout_episode_cards(self) -> None:
        episodes = list(self._current_group.episodes) if self._current_group is not None else []
        self._rebuild_episode_cards(episodes)

    def _handle_card_thumbnail_ready(self, source: str) -> None:
        normalized = str(source or "").strip()
        if normalized == str(self._current_season_summary.poster or "").strip():
            self._refresh_season_detail_panel()

    def _refresh_grid_cycle_button(self) -> None:
        icon_text = {1: "▭", 2: "▮▮", 3: "▮▮▮"}[self._grid_columns]
        label = {1: "单列", 2: "双列", 3: "三列"}[self._grid_columns]
        self.grid_cycle_button.setText(icon_text)
        self.grid_cycle_button.setToolTip(label)

    def status_for_episode(self, episode: FollowingEpisode) -> str:
        visible_season_number = self._current_group.season_number if self._current_group is not None else 0
        return resolve_following_episode_state(
            episode=episode,
            current_season_number=self._current_season_number,
            current_episode=self._current_episode,
            latest_season_number=self._latest_season_number,
            latest_episode=self._latest_episode,
            visible_season_number=visible_season_number,
            next_episode=self._next_episode,
        )

    def status_text_for_episode(self, episode: FollowingEpisode) -> str:
        return _episode_status_text(self.status_for_episode(episode))

    def _refresh_season_detail_panel(self) -> None:
        summary = self._current_season_summary
        self.season_detail_title_label.setText(summary.title or "未命名季")
        self.season_detail_episode_count_label.setText(
            f"共 {summary.episode_count} 集" if summary.episode_count > 0 else ""
        )
        self.season_detail_air_date_label.setText(summary.air_date or "")
        self.season_detail_overview_label.setText(summary.overview or "暂无本季简介")
        self.season_detail_poster_label.setText("暂无季封面")
        self.season_detail_poster_label.setPixmap(QPixmap())
        self.season_detail_poster_label.setCursor(Qt.CursorShape.ArrowCursor)
        if summary.poster:
            image = self.thumbnail_store.image_for(summary.poster)
            self.season_detail_poster_label.setCursor(Qt.CursorShape.PointingHandCursor)
            if image is None:
                self.thumbnail_store.request(summary.poster, target_size=self.season_detail_poster_label.size())
                self.season_detail_poster_label.setText("季封面")
            else:
                self.season_detail_poster_label.setText("")
                self.season_detail_poster_label.setPixmap(QPixmap.fromImage(image))

    def _open_current_season_poster_preview(self) -> None:
        poster_source = str(self._current_season_summary.poster or "").strip()
        if not poster_source:
            return
        FollowingSeasonPosterPreviewDialog(
            self._current_season_summary.title or "季封面",
            poster_source,
            self,
        ).exec()


def _episode_meta_text(episode: FollowingEpisode) -> str:
    parts = []
    if episode.air_date:
        parts.append(episode.air_date)
    if episode.runtime > 0:
        parts.append(f"{episode.runtime}m")
    if episode.is_special:
        parts.append("特别篇")
    return " · ".join(parts)


def _episode_status_text(state: str) -> str:
    return {
        FollowingEpisodeState.WATCHED: "已看",
        FollowingEpisodeState.RELEASED: "已更新",
        FollowingEpisodeState.UPCOMING: "即将更新",
        FollowingEpisodeState.PENDING: "未更新",
    }.get(state, "未更新")


def _episode_air_date(value: str) -> datetime.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _nearest_future_episode(
    episodes: list[FollowingEpisode],
    *,
    today,
    visible_season_number: int,
) -> FollowingEpisode | None:
    candidates: list[tuple[datetime.date, int, FollowingEpisode]] = []
    for episode in episodes:
        air_date = _episode_air_date(episode.air_date)
        if air_date is None or air_date <= today:
            continue
        episode_season = resolve_progress_season(
            episode.season_number,
            episode.episode_number,
            fallback_season=visible_season_number,
        )
        candidates.append((air_date, episode_season, episode))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].episode_number))
    return candidates[0][2]


def _episode_status_colors(state: str) -> tuple[str, str, str]:
    return {
        FollowingEpisodeState.WATCHED: ("rgba(34,197,94,0.22)", "#dcfce7", "rgba(34,197,94,0.55)"),
        FollowingEpisodeState.RELEASED: ("rgba(56,189,248,0.22)", "#e0f2fe", "rgba(56,189,248,0.55)"),
        FollowingEpisodeState.UPCOMING: ("rgba(245,158,11,0.22)", "#fef3c7", "rgba(245,158,11,0.6)"),
        FollowingEpisodeState.PENDING: ("rgba(148,163,184,0.20)", "#e2e8f0", "rgba(148,163,184,0.35)"),
    }.get(state, ("rgba(148,163,184,0.20)", "#e2e8f0", "rgba(148,163,184,0.35)"))


def _episode_card_stylesheet(state: str) -> str:
    tokens = current_tokens()
    _badge_bg, _badge_fg, border = _episode_status_colors(state)
    return (
        f"QFrame#followingEpisodeCard {{"
        f"border: 1px solid {border};"
        f"border-radius: 14px;"
        f"background: {tokens.panel_bg};"
        "}"
    )


def _episode_status_badge_stylesheet(state: str) -> str:
    background, foreground, _border = _episode_status_colors(state)
    return (
        f"background: {background};"
        f"color: {foreground};"
        "border-radius: 10px;"
        "padding: 2px 8px;"
        "font-size: 11px;"
        "font-weight: 700;"
    )


def _episode_status_border_color(tokens, state: str) -> str:
    del tokens
    _badge_bg, _badge_fg, border = _episode_status_colors(state)
    return border


def _status_badge_width(painter: QPainter, text: str, *, padding_x: int = 8) -> int:
    return painter.fontMetrics().horizontalAdvance(text) + (padding_x * 2)


def _draw_status_badge(
    painter: QPainter,
    rect: QRect,
    text: str,
    state: str,
    *,
    radius: int = 10,
) -> None:
    background, foreground, _border = _episode_status_colors(state)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(background))
    painter.drawRoundedRect(rect, radius, radius)
    painter.setPen(QColor(foreground))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()


def _display_mode_for_grid_columns(columns: int) -> str:
    return {
        1: EpisodeDisplayMode.FULL,
        2: EpisodeDisplayMode.POSTER,
        3: EpisodeDisplayMode.COMPACT,
    }.get(columns, EpisodeDisplayMode.FULL)


def _card_metrics_for_columns(columns: int) -> EpisodeCardMetrics:
    return {
        1: EpisodeCardMetrics(164, 148, 84, 10, 10, 10, 42, 18, 54, 20, 8, 2, 12),
        2: EpisodeCardMetrics(148, 148, 84, 10, 10, 10, 38, 18, 38, 20, 8, 2, 12),
        3: EpisodeCardMetrics(138, 148, 84, 10, 10, 8, 34, 16, 34, 18, 6, 1, 10),
    }[columns]


def _card_metrics_for_mode(mode: str) -> EpisodeCardMetrics:
    return {
        EpisodeDisplayMode.FULL: _card_metrics_for_columns(1),
        EpisodeDisplayMode.POSTER: _card_metrics_for_columns(2),
        EpisodeDisplayMode.COMPACT: _card_metrics_for_columns(3),
    }.get(mode, _card_metrics_for_columns(1))


def _overview_max_height(columns: int) -> int:
    if columns == 1:
        return 96
    if columns == 2:
        return 60
    return 40


def _image_placeholder_qss() -> str:
    tokens = current_tokens()
    return (
        f"border: 1px solid {tokens.border_subtle};"
        "border-radius: 12px;"
        f"background: {tokens.panel_alt_bg};"
        f"color: {tokens.text_secondary};"
    )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)
