from __future__ import annotations

import threading

import shiboken6
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from atv_player.ui.poster_loader import (
    load_local_poster_image,
    load_remote_poster_image,
    normalize_poster_url,
)
from atv_player.ui.theme import current_tokens


def following_search_candidate_media_type(candidate) -> str:
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    if provider_id.startswith("tv:"):
        return "电视"
    if provider_id.startswith("movie:"):
        return "电影"
    return ""


class FollowingSearchResultCard(QFrame):
    image_loaded = Signal(object)

    def __init__(self, candidate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self._selected = False
        self._overview_full_text = self._overview_text()
        self.poster_label = QLabel("封面", self)
        self.title_label = QLabel(str(getattr(candidate, "title", "") or "未命名条目"), self)
        self.rating_label = QLabel(self._rating_text(), self)
        self.meta_label = QLabel(self._meta_text(), self)
        self.overview_label = QLabel(self._overview_full_text, self)
        self._build_ui()
        self.image_loaded.connect(self._handle_image_loaded)
        self._start_poster_load()

    def _build_ui(self) -> None:
        tokens = current_tokens()
        self.setObjectName("followingSearchResultCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"""
            QFrame#followingSearchResultCard {{
                background: {tokens.panel_bg};
                border: 1px solid {tokens.border_subtle};
                border-radius: 16px;
            }}
            QFrame#followingSearchResultCard[selected="true"] {{
                border: 1px solid {tokens.accent};
                background: {tokens.menu_hover_bg};
            }}
            QLabel {{
                color: {tokens.text_primary};
                border: 0;
                background: transparent;
            }}
            QLabel[resultTitle="true"] {{
                font-size: 16px;
                font-weight: 600;
            }}
            QLabel[resultMeta="true"] {{
                color: {tokens.text_secondary};
            }}
            QLabel[resultOverview="true"] {{
                color: {tokens.text_secondary};
            }}
            QLabel[resultRating="true"] {{
                color: {tokens.button_primary_text};
                background: {tokens.accent};
                border-radius: 10px;
                padding: 2px 8px;
                font-weight: 600;
            }}
            """
        )

        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(92, 132)
        self.poster_label.setStyleSheet(
            f"""
            QLabel {{
                color: {tokens.text_secondary};
                background: {tokens.panel_alt_bg};
                border: 1px solid {tokens.border_subtle};
                border-radius: 12px;
            }}
            """
        )

        self.title_label.setProperty("resultTitle", True)
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.rating_label.setProperty("resultRating", True)
        self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rating_label.setHidden(not self.rating_label.text().strip())

        self.meta_label.setProperty("resultMeta", True)
        self.meta_label.setWordWrap(True)

        self.overview_label.setProperty("resultOverview", True)
        self.overview_label.setWordWrap(True)
        self.overview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.rating_label, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        text_layout.addLayout(title_row)
        text_layout.addWidget(self.meta_label)
        text_layout.addWidget(self.overview_label, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        self._apply_overview_clamp()

    def _candidate_raw(self) -> dict[str, object]:
        return dict(getattr(self.candidate, "raw", {}) or {})

    def _poster_source(self) -> str:
        raw = self._candidate_raw()
        return str(raw.get("poster") or raw.get("poster_url") or "").strip()

    def _rating_text(self) -> str:
        return str(self._candidate_raw().get("rating") or "").strip()

    def _meta_text(self) -> str:
        year = str(getattr(self.candidate, "year", "") or "").strip()
        media_type = following_search_candidate_media_type(self.candidate)
        return " · ".join(part for part in (year, media_type) if part)

    def _overview_text(self) -> str:
        return str(self._candidate_raw().get("overview") or "").strip() or "暂无简介"

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", self._selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _start_poster_load(self) -> None:
        source = self._poster_source()
        if not source:
            return
        target_size = QSize(self.poster_label.width(), self.poster_label.height())

        def load() -> None:
            image = load_local_poster_image(source, target_size)
            if image is None:
                image = load_remote_poster_image(normalize_poster_url(source), target_size)
            if image is not None:
                self.image_loaded.emit(image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_image_loaded(self, image) -> None:
        if not shiboken6.isValid(self.poster_label):
            return
        self.poster_label.setText("")
        self.poster_label.setPixmap(QPixmap.fromImage(image))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_overview_clamp()

    def _apply_overview_clamp(self) -> None:
        width = max(0, self.overview_label.contentsRect().width())
        if width <= 0:
            width = max(0, self.overview_label.width() - 2)
        if width <= 0:
            self.overview_label.setText(self._overview_full_text)
            return

        metrics = self.overview_label.fontMetrics()
        max_lines = 3
        line_height = metrics.lineSpacing()
        self.overview_label.setFixedHeight(line_height * max_lines)
        lines: list[str] = []
        current = ""
        text = self._overview_full_text.replace("\r\n", "\n").replace("\r", "\n")
        index = 0
        length = len(text)

        while index < length and len(lines) < max_lines:
            char = text[index]
            if char == "\n":
                lines.append(current.rstrip())
                current = ""
                index += 1
                continue
            proposed = current + char
            if current and metrics.horizontalAdvance(proposed) > width:
                lines.append(current.rstrip())
                current = ""
                continue
            current = proposed
            index += 1

        if len(lines) < max_lines and current:
            lines.append(current.rstrip())

        remaining = text[index:]
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if remaining:
            last = lines[max_lines - 1] if len(lines) >= max_lines else ""
            overflow_text = f"{last}{remaining}"
            if len(lines) >= max_lines:
                lines[max_lines - 1] = metrics.elidedText(overflow_text, Qt.TextElideMode.ElideRight, width)
            else:
                lines.append(metrics.elidedText(overflow_text, Qt.TextElideMode.ElideRight, width))

        self.overview_label.setText("\n".join(lines) if lines else self._overview_full_text)
