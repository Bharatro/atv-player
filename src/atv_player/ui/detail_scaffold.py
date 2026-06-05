from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from atv_player.ui.theme import current_tokens


class MediaDetailScaffold:
    def __init__(
        self,
        owner: QWidget,
        *,
        action_row: QHBoxLayout,
        status_label: QLabel,
        title_label: QLabel,
        meta_label: QLabel,
        rating_label: QLabel,
        metadata_source_bar: QWidget | None,
        playback_platform_section: QWidget | None,
        overview_label: QLabel,
        extra_metadata_widgets: list[QWidget] | None = None,
        poster_carousel_label: QLabel,
        episode_widget: QWidget,
        related_status_label: QLabel | None,
        related_container: QWidget,
        cast_container: QWidget,
    ) -> None:
        self.owner = owner
        self.action_row = action_row
        self.status_label = status_label
        self.title_label = title_label
        self.meta_label = meta_label
        self.rating_label = rating_label
        self.metadata_source_bar = metadata_source_bar
        self.playback_platform_section = playback_platform_section
        self.overview_label = overview_label
        self.extra_metadata_widgets = list(extra_metadata_widgets or [])
        self.poster_carousel_label = poster_carousel_label
        self.episode_widget = episode_widget
        self.related_status_label = related_status_label
        self.related_container = related_container
        self.cast_container = cast_container

        self.metadata_panel: QFrame
        self.poster_carousel_panel: QFrame
        self.top_section: QWidget
        self.episodes_section: QFrame
        self.related_recommendation_section: QFrame
        self.cast_section: QFrame
        self.related_recommendation_scroll: QScrollArea
        self.cast_scroll: QScrollArea
        self.page_scroll: QScrollArea

        self.build()

    def build(self) -> None:
        owner = self.owner
        content = QWidget(owner)

        self.metadata_panel = QFrame(content)
        self.metadata_panel.setObjectName("followingDetailMetadataPanel")
        metadata_layout = QVBoxLayout(self.metadata_panel)
        metadata_layout.setContentsMargins(18, 18, 18, 18)
        metadata_layout.setSpacing(12)
        metadata_layout.addLayout(self.action_row)
        metadata_layout.addWidget(self.status_label)
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.meta_label)
        metadata_layout.addWidget(self.rating_label)
        if self.metadata_source_bar is not None:
            metadata_layout.addWidget(self.metadata_source_bar)
        if self.playback_platform_section is not None:
            metadata_layout.addWidget(self.playback_platform_section)
        metadata_layout.addWidget(self.overview_label)
        for widget in self.extra_metadata_widgets:
            metadata_layout.addWidget(widget)
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

        self.related_recommendation_scroll = QScrollArea()
        self.related_recommendation_scroll.setWidgetResizable(True)
        self.related_recommendation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.related_recommendation_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.related_recommendation_scroll.setWidget(self.related_container)
        self.related_recommendation_scroll.setMinimumHeight(286)
        self.related_recommendation_scroll.setMaximumHeight(308)

        self.related_recommendation_section = QFrame(content)
        self.related_recommendation_section.setObjectName("followingRelatedRecommendationSection")
        related_section_layout = QVBoxLayout(self.related_recommendation_section)
        related_section_layout.setContentsMargins(14, 14, 14, 14)
        related_section_layout.setSpacing(10)
        related_section_layout.addWidget(QLabel("关联媒体推荐", self.related_recommendation_section))
        if self.related_status_label is not None:
            related_section_layout.addWidget(self.related_status_label)
        related_section_layout.addWidget(self.related_recommendation_scroll)

        self.episodes_section = QFrame(content)
        self.episodes_section.setObjectName("followingDetailEpisodesSection")
        self.episodes_section.setMinimumHeight(480)
        episodes_section_layout = QVBoxLayout(self.episodes_section)
        episodes_section_layout.setContentsMargins(14, 14, 14, 14)
        episodes_section_layout.setSpacing(10)
        episodes_section_layout.addWidget(QLabel("分集详情", self.episodes_section))
        episodes_section_layout.addWidget(self.episode_widget)

        self.cast_scroll = QScrollArea()
        self.cast_scroll.setWidgetResizable(True)
        self.cast_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cast_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cast_scroll.setWidget(self.cast_container)
        self.cast_scroll.setMinimumHeight(270)
        self.cast_scroll.setMaximumHeight(300)

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

        self.page_scroll = QScrollArea(owner)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.page_scroll.setWidget(content)

        layout = QVBoxLayout(owner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.page_scroll)


def detail_scaffold_qss() -> str:
    tokens = current_tokens()
    return f"""
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
