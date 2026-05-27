# ruff: noqa: E501
from __future__ import annotations

import threading
from datetime import date
import json

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QWidget,
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
        self.resize(800, 600)
        self.groups = []
        self._search_request_id = 0
        self._add_request_id = 0
        self._search_in_progress = False
        self._add_in_progress = False
        self._discovery_mode = callable(getattr(controller, "load_discovery_tab", None)) and bool(
            getattr(controller, "has_discovery_tabs", lambda: True)()
        )
        self._active_tab = "search"
        self._tab_state: dict[str, dict[str, object]] = {}
        self._rendered_state_key: str | None = None
        self._render_cache: dict[str, QListWidget] = {}
        self._result_lists: list[QListWidget] = []
        self._result_list_qss = ""

        host = self.content_widget()
        layout = self.content_layout()

        self.tab_buttons: list[QPushButton] = []
        self._tab_buttons_by_key: dict[str, QPushButton] = {}
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        for label, key in (
            ("推荐", "recommendation"),
            ("热门", "trending"),
            ("筛选", "discover"),
            ("搜索", "search"),
        ):
            button = QPushButton(label, host)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, current_key=key: self._activate_tab(current_key))
            tab_row.addWidget(button)
            self.tab_buttons.append(button)
            self._tab_buttons_by_key[key] = button
        layout.addLayout(tab_row)

        search_row = QGridLayout()
        search_row.setHorizontalSpacing(6)
        search_row.setVerticalSpacing(6)
        self.search_title_label = QLabel("标题", host)
        self.search_year_label = QLabel("年份", host)
        search_row.addWidget(self.search_title_label, 0, 0)
        search_row.addWidget(self.search_year_label, 0, 1)
        self.search_edit = QLineEdit(host)
        self.search_edit.setPlaceholderText("搜索标题或粘贴 Bangumi / 豆瓣 / TMDB 链接")
        search_row.addWidget(self.search_edit, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        self.search_year_edit = QLineEdit(host)
        self.search_year_edit.setPlaceholderText("留空不过滤")
        self.search_year_edit.setMaxLength(4)
        self.search_year_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,4}"), self))
        self.search_year_edit.setFixedWidth(120)
        search_row.addWidget(self.search_year_edit, 1, 1, alignment=Qt.AlignmentFlag.AlignTop)
        self.search_button = QPushButton("搜索", host)
        self.search_button.setAutoDefault(False)
        self.search_button.setDefault(False)
        search_row.addWidget(self.search_button, 1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        search_row.setColumnStretch(0, 1)
        layout.addLayout(search_row)
        self._search_row = search_row

        self.trending_filters_widget = QWidget(host)
        trending_filters_layout = QHBoxLayout(self.trending_filters_widget)
        trending_filters_layout.setContentsMargins(0, 0, 0, 0)
        trending_filters_layout.setSpacing(6)
        self.trending_list_combo = FlatComboBox(self.trending_filters_widget)
        self.trending_list_combo.addItem("本周趋势", "trending_week")
        self.trending_list_combo.addItem("今日趋势", "trending_day")
        trending_filters_layout.addWidget(self.trending_list_combo)
        self.trending_media_combo = FlatComboBox(self.trending_filters_widget)
        self.trending_media_combo.addItem("全部媒体", "all")
        self.trending_media_combo.addItem("剧集", "tv")
        self.trending_media_combo.addItem("电影", "movie")
        trending_filters_layout.addWidget(self.trending_media_combo)
        layout.addWidget(self.trending_filters_widget)

        self.discover_filters_widget = QWidget(host)
        discover_filters_layout = QHBoxLayout(self.discover_filters_widget)
        discover_filters_layout.setContentsMargins(0, 0, 0, 0)
        discover_filters_layout.setSpacing(6)
        self.discover_media_combo = FlatComboBox(self.discover_filters_widget)
        self.discover_media_combo.addItem("剧集", "tv")
        self.discover_media_combo.addItem("电影", "movie")
        discover_filters_layout.addWidget(self.discover_media_combo)
        self.discover_sort_combo = FlatComboBox(self.discover_filters_widget)
        self.discover_sort_combo.addItem("热门优先", "popularity.desc")
        self.discover_sort_combo.addItem("评分优先", "vote_average.desc")
        self.discover_sort_combo.addItem("讨论度优先", "vote_count.desc")
        discover_filters_layout.addWidget(self.discover_sort_combo)
        self.discover_year_combo = FlatComboBox(self.discover_filters_widget)
        self.discover_year_combo.addItem("全部年份", "")
        for year in range(date.today().year, date.today().year - 12, -1):
            self.discover_year_combo.addItem(str(year), str(year))
        discover_filters_layout.addWidget(self.discover_year_combo)
        layout.addWidget(self.discover_filters_widget)

        self.result_stack = QStackedWidget(host)
        self._default_result_list = self._create_result_list()
        self.result_list = self._default_result_list
        self.result_stack.addWidget(self.result_list)
        layout.addWidget(self.result_stack, 1)

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
        self.search_year_edit.returnPressed.connect(self.run_search)
        self.trending_list_combo.currentIndexChanged.connect(lambda _index: self._handle_filter_changed("trending"))
        self.trending_media_combo.currentIndexChanged.connect(lambda _index: self._handle_filter_changed("trending"))
        self.discover_media_combo.currentIndexChanged.connect(lambda _index: self._handle_filter_changed("discover"))
        self.discover_sort_combo.currentIndexChanged.connect(lambda _index: self._handle_filter_changed("discover"))
        self.discover_year_combo.currentIndexChanged.connect(lambda _index: self._handle_filter_changed("discover"))
        self.add_button.clicked.connect(self._add_selected_candidate)
        self.close_button.clicked.connect(self.reject)
        self._connect_async_signal(self.search_finished, self._handle_search_finished)
        self._connect_async_signal(self.add_finished, self._handle_add_finished)
        self._apply_theme()
        self._sync_action_state()
        if self._discovery_mode:
            self._activate_tab("recommendation")
        else:
            for button in self.tab_buttons:
                button.hide()
            self.trending_filters_widget.hide()
            self.discover_filters_widget.hide()

    def _create_result_list(self) -> QListWidget:
        result_list = QListWidget(self.result_stack)
        result_list.setSpacing(10)
        result_list.currentRowChanged.connect(self._handle_result_selection_changed)
        result_list.itemDoubleClicked.connect(lambda _item: self._add_selected_candidate())
        if self._result_list_qss:
            result_list.setStyleSheet(self._result_list_qss)
        self._result_lists.append(result_list)
        return result_list

    def _set_active_result_list(self, result_list: QListWidget) -> None:
        self.result_list = result_list
        self.result_stack.setCurrentWidget(result_list)
        self.result_list.setEnabled(not (self._search_in_progress or self._add_in_progress))

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
        search_year = self._validated_search_year()
        if search_year is None:
            self.status_label.setText("请输入 4 位年份")
            return
        if self._discovery_mode:
            self._load_active_tab()
            return
        self._search_request_id += 1
        request_id = self._search_request_id
        self._set_search_loading(True)

        def run() -> None:
            try:
                groups = self.controller.search_media(keyword, year=search_year)
                error = ""
            except Exception as exc:
                groups = []
                error = str(exc)
            if self._can_deliver_async_result():
                self.search_finished.emit(request_id, groups, error)

        threading.Thread(target=run, daemon=True).start()

    def _validated_search_year(self) -> str | None:
        value = self.search_year_edit.text().strip()
        if not value:
            return ""
        if len(value) != 4 or not value.isdigit():
            return None
        return value

    def _clear_results(self) -> None:
        self.groups = []
        self._set_active_result_list(self._default_result_list)
        self._rendered_state_key = None
        self.result_list.clear()
        self._sync_action_state()

    def _activate_tab(self, tab_key: str) -> None:
        normalized_tab = str(tab_key or "").strip() or "recommendation"
        self._active_tab = normalized_tab
        self._search_request_id += 1
        self._set_search_loading(False)
        button = self._tab_buttons_by_key.get(normalized_tab)
        if button is not None:
            button.setChecked(True)
        search_visible = normalized_tab == "search"
        self.search_title_label.setVisible(search_visible)
        self.search_year_label.setVisible(search_visible)
        self.search_edit.setVisible(search_visible)
        self.search_year_edit.setVisible(search_visible)
        self.search_button.setVisible(search_visible)
        self.trending_filters_widget.setVisible(normalized_tab == "trending")
        self.discover_filters_widget.setVisible(normalized_tab == "discover")
        state_key = self._state_key(normalized_tab)
        state = self._tab_state.get(state_key, {})
        cached_items = list(state.get("items", []) or [])
        if state.get("loaded", False):
            self._render_cached_state(state_key, state, cached_items)
        if normalized_tab == "search":
            self.status_label.setText("输入标题或粘贴链接搜索可追更媒体")
            if not state.get("loaded", False):
                self._clear_results()
            return
        if not state.get("loaded", False):
            self._load_active_tab()

    def _load_active_tab(self) -> None:
        self._search_request_id += 1
        request_id = self._search_request_id
        tab_key = self._active_tab
        state_key = self._state_key(tab_key)
        self._set_search_loading(True)

        def run() -> None:
            try:
                result = self.controller.load_discovery_tab(
                    tab_key,
                    query=self.search_edit.text().strip(),
                    page=1,
                    filters=self._filters_for_tab(tab_key),
                )
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.search_finished.emit(request_id, (tab_key, state_key, result), error)

        threading.Thread(target=run, daemon=True).start()

    def _render_groups(self, groups) -> None:
        self.groups = list(groups or [])
        self._set_active_result_list(self._default_result_list)
        self._rendered_state_key = None
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

    def _render_discovery_result(self, result, *, state_key: str | None = None) -> None:
        self.groups = []
        self._prepare_rendered_state_replacement(state_key)
        self.result_list.clear()
        items = list(getattr(result, "items", []) or [])
        for candidate in items:
            self._append_candidate_item(candidate)
        self._rendered_state_key = state_key
        if self.result_list.count():
            self.result_list.setCurrentRow(0)
        else:
            self._sync_action_state()
        source_label = str(getattr(result, "source_label", "") or "搜索")
        fallback_reason = str(getattr(result, "fallback_reason", "") or "").strip()
        self._set_discovery_status(source_label=source_label, item_count=len(items), fallback_reason=fallback_reason)

    def _prepare_rendered_state_replacement(self, state_key: str | None) -> None:
        if state_key is None:
            self._set_active_result_list(self._default_result_list)
            self._rendered_state_key = None
            return
        result_list = self._render_cache.get(state_key)
        if result_list is None:
            result_list = self._create_result_list()
            self._render_cache[state_key] = result_list
            self.result_stack.addWidget(result_list)
        self._set_active_result_list(result_list)
        self._rendered_state_key = state_key

    def _restore_rendered_state(self, state_key: str) -> bool:
        result_list = self._render_cache.get(state_key)
        if result_list is None:
            return False
        self._set_active_result_list(result_list)
        self._rendered_state_key = state_key
        if self.result_list.count():
            if self.result_list.currentRow() < 0:
                self.result_list.setCurrentRow(0)
            self._handle_result_selection_changed(self.result_list.currentRow())
        else:
            self._sync_action_state()
        return True

    def _set_discovery_status(self, *, source_label: str, item_count: int, fallback_reason: str) -> None:
        suffix = " · 推荐不足，已补充热门内容" if fallback_reason == "recommendation-empty" else ""
        self.status_label.setText(f"{source_label} · 找到 {item_count} 个结果{suffix}")

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
        self.search_year_edit.setEnabled(not busy)
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
            return
        if self._discovery_mode:
            tab_key, state_key, result = groups
            self._tab_state[state_key] = {
                "items": list(getattr(result, "items", []) or []),
                "source_label": str(getattr(result, "source_label", "") or ""),
                "fallback_reason": str(getattr(result, "fallback_reason", "") or ""),
                "loaded": True,
            }
            if tab_key != self._active_tab or state_key != self._state_key(tab_key):
                return
            self._render_discovery_result(result, state_key=state_key)
            return
        self._render_groups(groups)

    def active_tab_button(self) -> QPushButton | None:
        return self._tab_buttons_by_key.get(self._active_tab)

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
        self.search_year_edit.setStyleSheet(build_search_line_edit_qss(tokens, border_radius=14, min_height=40))
        self.search_button.setFixedHeight(40)
        for combo in (
            self.trending_list_combo,
            self.trending_media_combo,
            self.discover_media_combo,
            self.discover_sort_combo,
            self.discover_year_combo,
        ):
            combo.setFixedHeight(40)
        for button in self.tab_buttons:
            button.setFixedHeight(40)
        button_qss = f"""
        QPushButton {{
            background-color: {tokens.button_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 12px;
            color: {tokens.text_primary};
            padding: 6px 14px;
        }}
        QPushButton:checked {{
            background-color: {tokens.accent};
            border-color: {tokens.accent};
            color: {tokens.button_primary_text};
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
        for button in (*self.tab_buttons, self.search_button, self.add_button, self.close_button):
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
        self._result_list_qss = list_qss
        for result_list in self._result_lists:
            result_list.setStyleSheet(list_qss)
        self.status_label.setStyleSheet(
            "background: transparent;"
            f"color: {tokens.text_secondary};"
        )

    def _handle_filter_changed(self, tab_key: str) -> None:
        if not self._discovery_mode or self._active_tab != tab_key:
            return
        state = self._tab_state.get(self._state_key(tab_key), {})
        cached_items = list(state.get("items", []) or [])
        if state.get("loaded", False):
            self._render_cached_state(self._state_key(tab_key), state, cached_items)
            return
        self._load_active_tab()

    def _filters_for_tab(self, tab_key: str) -> dict[str, str]:
        normalized_tab = str(tab_key or "").strip() or "recommendation"
        if normalized_tab == "trending":
            return {
                "list_key": str(self.trending_list_combo.currentData() or "trending_week"),
                "media_type": str(self.trending_media_combo.currentData() or "all"),
            }
        if normalized_tab == "discover":
            return {
                "media_type": str(self.discover_media_combo.currentData() or "tv"),
                "sort_by": str(self.discover_sort_combo.currentData() or "popularity.desc"),
                "year": str(self.discover_year_combo.currentData() or ""),
            }
        if normalized_tab == "search":
            return {"year": self._validated_search_year() or ""}
        return {}

    def _state_key(self, tab_key: str) -> str:
        normalized_tab = str(tab_key or "").strip() or "recommendation"
        if normalized_tab == "search":
            payload = {
                "tab": normalized_tab,
                "query": self.search_edit.text().strip(),
                "year": self.search_year_edit.text().strip(),
            }
        else:
            payload = {"tab": normalized_tab, "filters": self._filters_for_tab(normalized_tab)}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def _render_cached_state(self, state_key: str, state: dict[str, object], cached_items: list[object]) -> None:
        if self._restore_rendered_state(state_key):
            self._set_discovery_status(
                source_label=str(state.get("source_label", "") or "搜索"),
                item_count=len(cached_items),
                fallback_reason=str(state.get("fallback_reason", "") or ""),
            )
            return
        self._render_discovery_result(
            type(
                "CachedResult",
                (),
                {
                    "items": cached_items,
                    "source_label": state.get("source_label", ""),
                    "fallback_reason": state.get("fallback_reason", ""),
                },
            )(),
            state_key=state_key,
        )
