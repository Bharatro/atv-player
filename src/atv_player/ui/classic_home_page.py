from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import DoubanCategory
from atv_player.ui.poster_grid_page import PosterGridPage


@dataclass(slots=True)
class SourceEntry:
    key: str
    title: str
    controller: object


class ClassicHomePage(QWidget):
    category_selected = Signal(str)
    source_changed = Signal(str)

    def __init__(
        self,
        source_entries: list[SourceEntry],
        initial_source_key: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_entries = source_entries
        self._current_source_key = initial_source_key or (
            source_entries[0].key if source_entries else ""
        )
        self._categories: list[DoubanCategory] = []

        # Source picker
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(120)
        for entry in source_entries:
            self.source_combo.addItem(entry.title, entry.key)
        if initial_source_key:
            idx = self.source_combo.findData(initial_source_key)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        self.source_combo.currentIndexChanged.connect(self._handle_source_changed)

        # Category tab bar
        self.category_tab_bar = QTabBar()
        self.category_tab_bar.setDrawBase(False)
        self.category_tab_bar.currentChanged.connect(self._handle_category_changed)

        # Poster grid page for the active source
        initial_entry = self._current_entry()
        self.grid_page = PosterGridPage(
            initial_entry.controller if initial_entry else _FakeEmptyController(),
            click_action="open",
            search_enabled=True,
            category_layout="tabs",
        )

        # Layout
        top_row = QHBoxLayout()
        top_row.addWidget(self.source_combo)
        top_row.addWidget(self.category_tab_bar, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_row)
        layout.addWidget(self.grid_page, 1)

        # Load initial categories synchronously
        if initial_entry is not None:
            self._load_categories_from_controller(initial_entry.controller)

    def _current_entry(self) -> SourceEntry | None:
        for entry in self._source_entries:
            if entry.key == self._current_source_key:
                return entry
        return self._source_entries[0] if self._source_entries else None

    def _handle_source_changed(self, index: int) -> None:
        key = self.source_combo.itemData(index)
        if not key or key == self._current_source_key:
            return
        self._current_source_key = key
        entry = self._current_entry()
        if entry is None:
            return
        # Replace the grid page with a new one for the new source
        new_page = PosterGridPage(
            entry.controller,
            click_action="open",
            search_enabled=True,
            category_layout="tabs",
        )
        layout = self.layout()
        old_page = self.grid_page
        layout.replaceWidget(old_page, new_page)
        old_page.deleteLater()
        self.grid_page = new_page
        self._load_categories_from_controller(entry.controller)
        self.source_changed.emit(key)

    def _handle_category_changed(self, index: int) -> None:
        if not (0 <= index < len(self._categories)):
            return
        category_id = self._categories[index].type_id
        self.category_selected.emit(category_id)
        self.grid_page.load_items(category_id, 1)

    def _load_categories_from_controller(self, controller) -> None:
        try:
            categories = controller.load_categories()
        except Exception:
            categories = []
        self._categories = list(categories)
        self.category_tab_bar.blockSignals(True)
        while self.category_tab_bar.count() > 0:
            self.category_tab_bar.removeTab(0)
        for cat in self._categories:
            self.category_tab_bar.addTab(cat.type_name)
        self.category_tab_bar.blockSignals(False)
        if self._categories:
            self.grid_page.selected_category_id = self._categories[0].type_id
            self.grid_page.load_items(self._categories[0].type_id, 1)
            self.category_tab_bar.setCurrentIndex(0)

    def current_source_key(self) -> str:
        return self._current_source_key


class _FakeEmptyController:
    def load_categories(self):
        return []

    def load_items(self, category_id, page, filters=None):
        return [], 0
