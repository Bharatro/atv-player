from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class FollowingSearchDialog(QDialog):
    candidate_selected = Signal(object)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("添加追更")
        self.resize(760, 520)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题")
        self.search_button = QPushButton("搜索")
        self.provider_tabs = QTabWidget()
        self.status_label = QLabel("")

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(self.search_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.provider_tabs, 1)
        layout.addWidget(self.status_label)

        self.search_button.clicked.connect(self.run_search)
        self.search_edit.returnPressed.connect(self.run_search)

    def run_search(self) -> None:
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.status_label.setText("请输入标题")
            return
        try:
            groups = self.controller.search_media(keyword)
        except Exception as exc:
            self.status_label.setText(f"搜索失败: {exc}")
            return
        self._render_groups(groups)

    def _render_groups(self, groups) -> None:
        self.provider_tabs.clear()
        for group in groups:
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(8, 8, 8, 8)
            tab_layout.setSpacing(8)
            if getattr(group, "error_text", ""):
                tab_layout.addWidget(QLabel(str(group.error_text)))
            for candidate in list(getattr(group, "items", []) or []):
                tab_layout.addWidget(self._candidate_row(candidate))
            tab_layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(tab)
            self.provider_tabs.addTab(scroll, str(getattr(group, "provider_label", "") or getattr(group, "provider", "")))
        self.status_label.setText("")

    def _candidate_row(self, candidate) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 6, 6, 6)
        title = str(getattr(candidate, "title", "") or "")
        year = str(getattr(candidate, "year", "") or "")
        subtitle = str(getattr(candidate, "subtitle", "") or "")
        label = QLabel(" · ".join(part for part in (title, year, subtitle) if part))
        add_button = QPushButton("加入追更")
        add_button.clicked.connect(lambda: self._add_candidate(candidate))
        layout.addWidget(label, 1)
        layout.addWidget(add_button)
        return row

    def _add_candidate(self, candidate) -> None:
        self.controller.add_candidate(candidate)
        self.candidate_selected.emit(candidate)
        self.accept()
