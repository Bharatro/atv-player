# ruff: noqa: E501
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
)

from atv_player.ui.theme import build_search_line_edit_qss, current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class FollowingSearchDialog(ThemedDialogBase):
    candidate_selected = Signal(object)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(title="添加追更", parent=parent)
        self.controller = controller
        self.resize(760, 480)
        self.groups = []

        host = self.content_widget()
        layout = self.content_layout()

        search_row = QGridLayout()
        search_row.setHorizontalSpacing(6)
        search_row.setVerticalSpacing(6)
        search_row.addWidget(QLabel("标题", host), 0, 0)
        self.search_edit = QLineEdit(host)
        self.search_edit.setPlaceholderText("搜索标题或粘贴 Bangumi / 豆瓣 / TMDB 链接")
        search_row.addWidget(self.search_edit, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        search_row.addWidget(QLabel("当前集数", host), 0, 1)
        self.current_episode_spin = QSpinBox(host)
        self.current_episode_spin.setRange(0, 9999)
        self.current_episode_spin.setSpecialValueText(" ")
        search_row.addWidget(self.current_episode_spin, 1, 1, alignment=Qt.AlignmentFlag.AlignTop)
        self.search_button = QPushButton("搜索", host)
        search_row.addWidget(self.search_button, 1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        search_row.setColumnStretch(0, 1)
        layout.addLayout(search_row)

        columns = QHBoxLayout()
        self.group_list = QListWidget(host)
        self.result_list = QListWidget(host)
        columns.addWidget(self.group_list, 1)
        columns.addWidget(self.result_list, 2)
        layout.addLayout(columns)

        self.status_label = QLabel("请输入标题搜索可追更媒体", host)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.add_button = QPushButton("加入追更", host)
        self.close_button = QPushButton("关闭", host)
        actions.addStretch(1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.search_button.clicked.connect(self.run_search)
        self.search_edit.returnPressed.connect(self.run_search)
        self.group_list.currentRowChanged.connect(self._populate_results)
        self.result_list.currentRowChanged.connect(lambda _row: self._sync_action_state())
        self.result_list.itemDoubleClicked.connect(lambda _item: self._add_selected_candidate())
        self.add_button.clicked.connect(self._add_selected_candidate)
        self.close_button.clicked.connect(self.reject)
        self._apply_theme()
        self._sync_action_state()

    def run_search(self) -> None:
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.status_label.setText("请输入标题")
            self._clear_results()
            return
        self.status_label.setText("搜索中...")
        try:
            groups = self.controller.search_media(keyword)
        except Exception as exc:
            self.status_label.setText(f"搜索失败: {exc}")
            self._clear_results()
            return
        self._render_groups(groups)

    def _clear_results(self) -> None:
        self.groups = []
        self.group_list.clear()
        self.result_list.clear()
        self._sync_action_state()

    def _render_groups(self, groups) -> None:
        self.groups = list(groups or [])
        self.group_list.clear()
        self.result_list.clear()
        total = 0
        for group in self.groups:
            items = list(getattr(group, "items", []) or [])
            total += len(items)
            provider_label = str(getattr(group, "provider_label", "") or getattr(group, "provider", "") or "未知来源")
            self.group_list.addItem(f"{provider_label} ({len(items)})")
        if self.groups:
            first_non_empty = next(
                (index for index, group in enumerate(self.groups) if list(getattr(group, "items", []) or [])),
                0,
            )
            self.group_list.setCurrentRow(first_non_empty)
        else:
            self._sync_action_state()
        self.status_label.setText(f"找到 {total} 个结果" if total else "没有找到可加入追更的结果")

    def _populate_results(self, group_index: int) -> None:
        self.result_list.clear()
        if group_index < 0 or group_index >= len(self.groups):
            self._sync_action_state()
            return
        group = self.groups[group_index]
        error_text = str(getattr(group, "error_text", "") or "")
        if error_text:
            item = QListWidgetItem(error_text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.result_list.addItem(item)
        for candidate in list(getattr(group, "items", []) or []):
            item = QListWidgetItem(self._candidate_text(candidate))
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.result_list.addItem(item)
        if self.result_list.count():
            self.result_list.setCurrentRow(0)
        self._sync_action_state()

    def _candidate_text(self, candidate) -> str:
        title = str(getattr(candidate, "title", "") or "")
        year = str(getattr(candidate, "year", "") or "")
        subtitle = str(getattr(candidate, "subtitle", "") or "")
        return " · ".join(part for part in (title, year, subtitle) if part) or "未命名条目"

    def _selected_candidate(self):
        item = self.result_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _add_selected_candidate(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            self.status_label.setText("请选择一个结果")
            return
        try:
            self.controller.add_candidate(candidate, current_episode=int(self.current_episode_spin.value()))
        except TypeError:
            self.controller.add_candidate(candidate)
        self.candidate_selected.emit(candidate)
        self.accept()

    def _sync_action_state(self) -> None:
        self.add_button.setEnabled(self._selected_candidate() is not None)

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self.search_edit.setStyleSheet(build_search_line_edit_qss(tokens, border_radius=14, min_height=40))
        self.current_episode_spin.setFixedHeight(40)
        self.current_episode_spin.setStyleSheet(
            f"""
            QSpinBox {{
                min-height: 40px;
                padding: 0 10px;
                border: 1px solid {tokens.input_border};
                border-radius: 14px;
                background: {tokens.input_bg};
                color: {tokens.text_primary};
            }}
            QSpinBox:focus {{
                border: 1px solid {tokens.accent};
            }}
            """
        )
        self.search_button.setFixedHeight(40)
        button_qss = f"""
        QPushButton {{
            background-color: {tokens.button_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 12px;
            color: {tokens.text_primary};
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            border-color: {tokens.accent_hover};
        }}
        QPushButton:disabled {{
            background-color: {tokens.button_disabled_bg};
            border: 1px solid {tokens.button_disabled_border};
            color: {tokens.button_disabled_text};
        }}
        """
        for button in (self.search_button, self.add_button, self.close_button):
            button.setStyleSheet(button_qss)
        list_qss = f"""
        QListWidget {{
            background: {tokens.input_bg};
            color: {tokens.text_primary};
            border: 1px solid {tokens.input_border};
            border-radius: 12px;
            padding: 6px;
        }}
        QListWidget::item {{
            border-radius: 8px;
            padding: 8px;
        }}
        QListWidget::item:selected {{
            background: {tokens.menu_selected_bg};
            color: {tokens.text_primary};
        }}
        QListWidget::item:hover {{
            background: {tokens.menu_hover_bg};
        }}
        """
        self.group_list.setStyleSheet(list_qss)
        self.result_list.setStyleSheet(list_qss)
        self.status_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )
