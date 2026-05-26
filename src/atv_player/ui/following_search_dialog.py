# ruff: noqa: E501
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)

from atv_player.ui.following_search_result_card import FollowingSearchResultCard
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.theme import build_search_line_edit_qss, current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class FollowingSearchDialog(ThemedDialogBase, AsyncGuardMixin):
    candidate_selected = Signal(object)
    search_finished = Signal(int, object, str)
    add_finished = Signal(int, object, str)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(title="添加追更", parent=parent)
        self._init_async_guard()
        self.controller = controller
        self.resize(760, 480)
        self.groups = []
        self._search_request_id = 0
        self._add_request_id = 0
        self._search_in_progress = False
        self._add_in_progress = False

        host = self.content_widget()
        layout = self.content_layout()

        search_row = QGridLayout()
        search_row.setHorizontalSpacing(6)
        search_row.setVerticalSpacing(6)
        search_row.addWidget(QLabel("标题", host), 0, 0)
        self.search_edit = QLineEdit(host)
        self.search_edit.setPlaceholderText("搜索标题或粘贴 Bangumi / 豆瓣 / TMDB 链接")
        search_row.addWidget(self.search_edit, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        self.search_button = QPushButton("搜索", host)
        self.search_button.setAutoDefault(False)
        self.search_button.setDefault(False)
        search_row.addWidget(self.search_button, 1, 1, alignment=Qt.AlignmentFlag.AlignTop)
        search_row.setColumnStretch(0, 1)
        layout.addLayout(search_row)

        self.result_list = QListWidget(host)
        self.result_list.setSpacing(10)
        layout.addWidget(self.result_list, 1)

        self.status_label = QLabel("请输入标题搜索可追更媒体", host)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.add_button = QPushButton("加入追更", host)
        self.close_button = QPushButton("关闭", host)
        self.add_button.setAutoDefault(False)
        self.add_button.setDefault(False)
        self.close_button.setAutoDefault(False)
        self.close_button.setDefault(False)
        actions.addStretch(1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.search_button.clicked.connect(self.run_search)
        self.search_edit.returnPressed.connect(self.run_search)
        self.result_list.currentRowChanged.connect(self._handle_result_selection_changed)
        self.result_list.itemDoubleClicked.connect(lambda _item: self._add_selected_candidate())
        self.add_button.clicked.connect(self._add_selected_candidate)
        self.close_button.clicked.connect(self.reject)
        self._connect_async_signal(self.search_finished, self._handle_search_finished)
        self._connect_async_signal(self.add_finished, self._handle_add_finished)
        self._apply_theme()
        self._sync_action_state()

    def run_search(self) -> None:
        if self._search_in_progress or self._add_in_progress:
            return
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.status_label.setText("请输入标题")
            self._clear_results()
            return
        self._search_request_id += 1
        request_id = self._search_request_id
        self._set_search_loading(True)

        def run() -> None:
            try:
                groups = self.controller.search_media(keyword)
                error = ""
            except Exception as exc:
                groups = []
                error = str(exc)
            if self._can_deliver_async_result():
                self.search_finished.emit(request_id, groups, error)

        threading.Thread(target=run, daemon=True).start()

    def _clear_results(self) -> None:
        self.groups = []
        self.result_list.clear()
        self._sync_action_state()

    def _render_groups(self, groups) -> None:
        self.groups = list(groups or [])
        self.result_list.clear()
        total = 0
        for group in self.groups:
            items = list(getattr(group, "items", []) or [])
            total += len(items)
            error_text = str(getattr(group, "error_text", "") or "").strip()
            if error_text and not items:
                item = QListWidgetItem(error_text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.result_list.addItem(item)
                continue
            for candidate in items:
                self._append_candidate_item(candidate)
        if self.result_list.count():
            self.result_list.setCurrentRow(0)
        else:
            self._sync_action_state()
        self.status_label.setText(f"找到 {total} 个结果" if total else "没有找到可加入追更的结果")

    def _append_candidate_item(self, candidate) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, candidate)
        card = FollowingSearchResultCard(candidate, self.result_list)
        item.setSizeHint(card.sizeHint())
        self.result_list.addItem(item)
        self.result_list.setItemWidget(item, card)

    def _handle_result_selection_changed(self, _row: int) -> None:
        for index in range(self.result_list.count()):
            item = self.result_list.item(index)
            card = self.result_list.itemWidget(item)
            if isinstance(card, FollowingSearchResultCard):
                card.set_selected(item is self.result_list.currentItem())
        self._sync_action_state()

    def _selected_candidate(self):
        item = self.result_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _add_selected_candidate(self) -> None:
        if self._search_in_progress or self._add_in_progress:
            return
        candidate = self._selected_candidate()
        if candidate is None:
            self.status_label.setText("请选择一个结果")
            return
        self._add_request_id += 1
        request_id = self._add_request_id
        self._set_add_loading(True)

        def run() -> None:
            try:
                self.controller.add_candidate(candidate)
                error = ""
            except Exception as exc:
                error = str(exc)
            if self._can_deliver_async_result():
                self.add_finished.emit(request_id, candidate, error)

        threading.Thread(target=run, daemon=True).start()

    def _sync_action_state(self) -> None:
        self.add_button.setEnabled(
            not self._search_in_progress
            and not self._add_in_progress
            and self._selected_candidate() is not None
        )

    def _set_search_loading(self, loading: bool) -> None:
        self._search_in_progress = bool(loading)
        self._apply_busy_state()
        if loading:
            self.status_label.setText("搜索中...")

    def _set_add_loading(self, loading: bool) -> None:
        self._add_in_progress = bool(loading)
        self._apply_busy_state()
        if loading:
            self.status_label.setText("加入追更中...")

    def _apply_busy_state(self) -> None:
        busy = self._search_in_progress or self._add_in_progress
        self.search_edit.setEnabled(not busy)
        self.search_button.setEnabled(not busy)
        self.result_list.setEnabled(not busy)
        self.close_button.setEnabled(not self._add_in_progress)
        self._sync_action_state()

    def _handle_search_finished(self, request_id: int, groups, error: str) -> None:
        if request_id != self._search_request_id:
            return
        self._set_search_loading(False)
        if error:
            self.status_label.setText(f"搜索失败: {error}")
            self._clear_results()
            return
        self._render_groups(groups)

    def _handle_add_finished(self, request_id: int, candidate, error: str) -> None:
        if request_id != self._add_request_id:
            return
        self._set_add_loading(False)
        if error:
            self.status_label.setText(f"加入失败: {error}")
            return
        self.candidate_selected.emit(candidate)
        self.accept()

    def _apply_theme(self) -> None:
        tokens = current_tokens()
        self.search_edit.setStyleSheet(build_search_line_edit_qss(tokens, border_radius=14, min_height=40))
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
            padding: 4px;
        }}
        QListWidget::item:selected {{
            background: {tokens.menu_selected_bg};
            color: {tokens.text_primary};
        }}
        QListWidget::item:hover {{
            background: {tokens.menu_hover_bg};
        }}
        """
        self.result_list.setStyleSheet(list_qss)
        self.status_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )
