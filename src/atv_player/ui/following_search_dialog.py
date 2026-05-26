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
from atv_player.ui.theme import FlatComboBox, build_search_line_edit_qss, current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


class FollowingSearchDialog(ThemedDialogBase, AsyncGuardMixin):
    candidate_selected = Signal(object)
    search_finished = Signal(int, object, str)
    add_finished = Signal(int, object, str)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(title="添加追更", parent=parent)
        self._init_async_guard()
        self.controller = controller
        self.resize(760, 560)
        self.groups = []
        self._search_request_id = 0
        self._add_request_id = 0
        self._search_in_progress = False
        self._add_in_progress = False
        self._discovery_mode = callable(getattr(controller, "load_discovery_tab", None)) and bool(
            getattr(controller, "has_discovery_tabs", lambda: True)()
        )
        self._active_tab = "search"

        host = self.content_widget()
        layout = self.content_layout()

        self.tab_bar = FlatComboBox(host)
        self.tab_bar.addItem("推荐", "recommendation")
        self.tab_bar.addItem("热门", "trending")
        self.tab_bar.addItem("筛选", "discover")
        self.tab_bar.addItem("搜索", "search")
        layout.addWidget(self.tab_bar)

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
        self._search_row = search_row

        self.filter_media_combo = FlatComboBox(host)
        self.filter_media_combo.addItem("全部", "")
        self.filter_media_combo.addItem("剧集", "tv")
        self.filter_media_combo.addItem("电影", "movie")
        layout.addWidget(self.filter_media_combo)

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

        self.tab_bar.currentIndexChanged.connect(self._handle_tab_changed)
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
        if self._discovery_mode:
            self._activate_tab("recommendation")
        else:
            self.tab_bar.hide()
            self.filter_media_combo.hide()

    def run_search(self) -> None:
        if self._search_in_progress or self._add_in_progress:
            return
        if self._discovery_mode and self._active_tab != "search":
            self._load_active_tab()
            return
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.status_label.setText("请输入标题")
            self._clear_results()
            return
        if self._discovery_mode:
            self._load_active_tab()
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

    def _handle_tab_changed(self, _index: int) -> None:
        if not self._discovery_mode:
            return
        self._activate_tab(str(self.tab_bar.currentData() or "recommendation"))

    def _activate_tab(self, tab_key: str) -> None:
        normalized_tab = str(tab_key or "").strip() or "recommendation"
        self._active_tab = normalized_tab
        self._search_request_id += 1
        self._set_search_loading(False)
        if self.tab_bar.currentData() != normalized_tab:
            for index in range(self.tab_bar.count()):
                if self.tab_bar.itemData(index) == normalized_tab:
                    self.tab_bar.setCurrentIndex(index)
                    break
        search_visible = normalized_tab == "search"
        self.search_edit.setVisible(search_visible)
        self.search_button.setVisible(search_visible)
        self.filter_media_combo.setVisible(normalized_tab in {"trending", "discover"})
        if normalized_tab == "search":
            self.status_label.setText("输入标题或粘贴链接搜索可追更媒体")
            self._clear_results()
            return
        self._load_active_tab()

    def _load_active_tab(self) -> None:
        self._search_request_id += 1
        request_id = self._search_request_id
        self._set_search_loading(True)

        def run() -> None:
            try:
                result = self.controller.load_discovery_tab(
                    self._active_tab,
                    query=self.search_edit.text().strip(),
                    page=1,
                    filters={"media_type": str(self.filter_media_combo.currentData() or "")},
                )
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.search_finished.emit(request_id, result, error)

        threading.Thread(target=run, daemon=True).start()

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

    def _render_discovery_result(self, result) -> None:
        self.groups = []
        self.result_list.clear()
        items = list(getattr(result, "items", []) or [])
        for candidate in items:
            self._append_candidate_item(candidate)
        if self.result_list.count():
            self.result_list.setCurrentRow(0)
        else:
            self._sync_action_state()
        source_label = str(getattr(result, "source_label", "") or "搜索")
        fallback_reason = str(getattr(result, "fallback_reason", "") or "").strip()
        suffix = " · 推荐不足，已补充热门内容" if fallback_reason == "recommendation-empty" else ""
        self.status_label.setText(f"{source_label} · 找到 {len(items)} 个结果{suffix}")

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
        if self._discovery_mode:
            self._render_discovery_result(groups)
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
        self.tab_bar.setFixedHeight(40)
        self.filter_media_combo.setFixedHeight(40)
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
