from __future__ import annotations

from datetime import datetime
from functools import partial
import threading

from PySide6.QtCore import QItemSelectionModel, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from atv_player.models import SpiderPluginImportCancelled
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.plugin_actions import PluginActions
from atv_player.ui.plugin_category_manager_dialog import PluginCategoryManagerDialog
from atv_player.ui.plugin_reorder_dialog import PluginReorderDialog
from atv_player.ui.theme import FlatComboBox, build_placeholder_label_qss, build_search_line_edit_qss, current_tokens
from atv_player.ui.window_chrome import ThemedDialogBase


def _display_source_type(source_type: str) -> str:
    return {
        "local": "本地",
        "remote": "远程",
    }.get(source_type, source_type)


class _PluginRefreshSignals(QObject):
    completed = Signal()
    failed = Signal(str)


class PluginManagerDialog(ThemedDialogBase, AsyncGuardMixin):
    _ACTION_RELOAD_DELAY_MS = 75

    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(title="插件管理", parent=parent)
        self._init_async_guard()
        self.plugin_manager = plugin_manager
        self.plugin_actions = PluginActions(plugin_manager)
        self.plugin_tabs_dirty = False
        self.changed_plugin_ids: list[int] = []
        self._import_in_progress = False
        self._refresh_in_progress = False
        self._refresh_target_plugin_ids: list[int] = []
        self._initial_plugin_snapshot: dict[int, tuple] = {}
        self._initial_plugin_snapshot_captured = False
        self._all_plugins = []
        self.resize(920, 520)
        tokens = current_tokens()
        self.warning_label = QLabel("支持TvBox Python爬虫。远程插件会执行本地 Python 代码，请只加载受信任来源。")
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("搜索名称或地址")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(build_search_line_edit_qss(tokens))
        self.enabled_filter_combo = FlatComboBox(self)
        self.enabled_filter_combo.addItem("全部", "all")
        self.enabled_filter_combo.addItem("仅启用", "enabled")
        self.enabled_filter_combo.addItem("仅禁用", "disabled")
        self._configure_filter_combo(self.enabled_filter_combo, minimum_contents_length=6)
        self.sort_combo = FlatComboBox(self)
        self.sort_combo.addItem("当前顺序", "sort_order")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.addItem("最近加载", "last_loaded_at")
        self._configure_filter_combo(self.sort_combo, minimum_contents_length=6)
        self.clear_filters_button = QPushButton("清空")
        self.empty_state_label = QLabel("没有匹配的插件", self)
        self.empty_state_label.hide()

        self.plugin_table = QTableWidget(0, 7, self)
        self.plugin_table.setHorizontalHeaderLabels(["名称", "来源", "版本", "地址", "启用", "状态", "最近加载"])
        self.plugin_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plugin_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plugin_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.plugin_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.plugin_table.setColumnWidth(1, 72)
        self.plugin_table.setColumnWidth(2, 64)
        self.plugin_table.setColumnWidth(4, 64)
        self.plugin_table.setColumnWidth(5, 160)
        self.plugin_table.setColumnWidth(6, 168)
        self.add_local_button = QPushButton("添加本地插件")
        self.add_remote_button = QPushButton("添加远程插件")
        self.import_github_button = QPushButton("从 GitHub 导入")
        self.rename_button = QPushButton("编辑名称")
        self.config_button = QPushButton("编辑配置")
        self.category_button = QPushButton("分类管理")
        self.enable_button = QPushButton("启用")
        self.disable_button = QPushButton("禁用")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.reorder_button = QPushButton("调整顺序")
        self.refresh_button = QPushButton("刷新")
        self.logs_button = QPushButton("查看日志")
        self.delete_button = QPushButton("删除")
        self.plugin_actions_label = QLabel("插件动作")
        self.plugin_actions_empty_label = QLabel("请选择插件以查看自定义动作")
        self.plugin_actions_widget = QWidget(self)
        self.plugin_actions_layout = QHBoxLayout(self.plugin_actions_widget)
        self.plugin_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.plugin_action_buttons: list[QWidget] = []
        self._plugin_actions_cache: dict[int, list] = {}
        self._pending_plugin_action_id: int | None = None
        self._refresh_signals = _PluginRefreshSignals(self)
        self._connect_async_signal(self._refresh_signals.completed, self._handle_refresh_completed)
        self._connect_async_signal(self._refresh_signals.failed, self._handle_refresh_failed)
        self._plugin_action_reload_timer = QTimer(self)
        self._plugin_action_reload_timer.setSingleShot(True)
        self._plugin_action_reload_timer.timeout.connect(self._load_pending_plugin_actions)

        actions = QHBoxLayout()
        for button in (
            self.add_local_button,
            self.add_remote_button,
            self.import_github_button,
            self.rename_button,
            self.config_button,
            self.category_button,
            self.enable_button,
            self.disable_button,
            self.up_button,
            self.down_button,
            self.reorder_button,
            self.refresh_button,
            self.logs_button,
            self.delete_button,
        ):
            actions.addWidget(button)

        self.filters_layout = QHBoxLayout()
        self.filters_layout.setSpacing(12)
        self.filters_layout.addWidget(self.search_input, 1)
        self.filters_layout.addWidget(self.enabled_filter_combo)
        self.filters_layout.addWidget(self.sort_combo)
        self.filters_layout.addWidget(self.clear_filters_button)

        layout = self.content_layout()
        layout.addWidget(self.warning_label)
        layout.addLayout(self.filters_layout)
        layout.addLayout(actions)
        layout.addWidget(self.plugin_actions_label)
        layout.addWidget(self.plugin_actions_empty_label)
        layout.addWidget(self.plugin_actions_widget)
        layout.addWidget(self.plugin_table)
        layout.addWidget(self.empty_state_label)

        self.add_local_button.clicked.connect(self._add_local_plugin)
        self.add_remote_button.clicked.connect(self._add_remote_plugin)
        self.import_github_button.clicked.connect(self._import_github_repository)
        self.rename_button.clicked.connect(self._rename_selected)
        self.config_button.clicked.connect(self._edit_selected_config)
        self.category_button.clicked.connect(self._open_category_manager_dialog)
        self.enable_button.clicked.connect(self._enable_selected)
        self.disable_button.clicked.connect(self._disable_selected)
        self.up_button.clicked.connect(lambda: self._move_selected(-1))
        self.down_button.clicked.connect(lambda: self._move_selected(1))
        self.reorder_button.clicked.connect(self._open_reorder_dialog)
        self.refresh_button.clicked.connect(self._refresh_selected)
        self.logs_button.clicked.connect(self._show_logs)
        self.delete_button.clicked.connect(self._delete_selected)
        self.search_input.textChanged.connect(self._apply_view_filters)
        self.enabled_filter_combo.currentIndexChanged.connect(self._apply_view_filters)
        self.sort_combo.currentIndexChanged.connect(self._apply_view_filters)
        self.clear_filters_button.clicked.connect(self._clear_view_filters)
        self.plugin_table.itemSelectionChanged.connect(self._sync_action_state)

        self.reload_plugins()

    def reload_plugins(self, selected_plugin_ids: list[int] | None = None) -> None:
        if selected_plugin_ids is None:
            selected_plugin_ids = self._selected_plugin_ids()
        self._plugin_action_reload_timer.stop()
        self._pending_plugin_action_id = None
        self._plugin_actions_cache.clear()
        plugins = self.plugin_manager.list_plugins()
        current_snapshot = self._plugin_snapshot(plugins)
        if not self._initial_plugin_snapshot_captured:
            self._initial_plugin_snapshot = current_snapshot
            self._initial_plugin_snapshot_captured = True
        self.changed_plugin_ids = self._diff_plugin_ids(self._initial_plugin_snapshot, current_snapshot)
        self.plugin_tabs_dirty = bool(self.changed_plugin_ids)
        self._all_plugins = list(plugins)
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_ids)

    def _apply_view_filters(self) -> None:
        selected_plugin_ids = self._selected_plugin_ids()
        self._render_plugins(self._visible_plugins(self._all_plugins), selected_plugin_ids)

    def _clear_view_filters(self) -> None:
        blockers = [
            QSignalBlocker(self.search_input),
            QSignalBlocker(self.enabled_filter_combo),
            QSignalBlocker(self.sort_combo),
        ]
        self.search_input.clear()
        self.enabled_filter_combo.setCurrentIndex(0)
        self.sort_combo.setCurrentIndex(0)
        del blockers
        self._apply_view_filters()

    def _configure_filter_combo(self, combo: QComboBox, *, minimum_contents_length: int) -> None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(minimum_contents_length)
        combo.setMaxVisibleItems(12)
        longest_label_width = max(combo.fontMetrics().horizontalAdvance(combo.itemText(index)) for index in range(combo.count()))
        left_padding = int(combo.property("flat_combo_left_padding") or 12)
        indicator_padding = int(combo.property("flat_combo_indicator_padding") or 40)
        combo.setMinimumWidth(longest_label_width + left_padding + indicator_padding)
        combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _visible_plugins(self, plugins) -> list:
        search_term = self.search_input.text().strip().casefold()
        enabled_filter = self.enabled_filter_combo.currentData()
        filtered = []
        for plugin in plugins:
            if not self._matches_search(plugin, search_term):
                continue
            if enabled_filter == "enabled" and not plugin.enabled:
                continue
            if enabled_filter == "disabled" and plugin.enabled:
                continue
            filtered.append(plugin)
        return self._sort_plugins(filtered)

    def _matches_search(self, plugin, search_term: str) -> bool:
        if not search_term:
            return True
        display_name = (plugin.display_name or "").casefold()
        source_value = (plugin.source_value or "").casefold()
        return search_term in display_name or search_term in source_value

    def _sort_plugins(self, plugins) -> list:
        sort_mode = self.sort_combo.currentData()
        if sort_mode == "sort_order":
            return sorted(plugins, key=lambda plugin: int(plugin.sort_order))
        if sort_mode == "name":
            return sorted(
                plugins,
                key=lambda plugin: ((plugin.display_name or plugin.source_value or "").casefold(), int(plugin.sort_order)),
            )
        return sorted(
            plugins,
            key=lambda plugin: (
                int(plugin.last_loaded_at) <= 0,
                -int(plugin.last_loaded_at) if int(plugin.last_loaded_at) > 0 else 0,
                int(plugin.sort_order),
            ),
        )

    def _render_plugins(self, plugins, selected_plugin_ids: list[int]) -> None:
        self.plugin_table.setRowCount(len(plugins))
        for row, plugin in enumerate(plugins):
            name_item = QTableWidgetItem(plugin.display_name or "")
            name_item.setData(256, plugin.id)
            self.plugin_table.setItem(row, 0, name_item)
            self.plugin_table.setItem(row, 1, QTableWidgetItem(_display_source_type(plugin.source_type)))
            self.plugin_table.setItem(row, 2, QTableWidgetItem(str(plugin.plugin_version)))
            self.plugin_table.setItem(row, 3, QTableWidgetItem(plugin.source_value))
            self.plugin_table.setItem(row, 4, QTableWidgetItem("是" if plugin.enabled else "否"))
            self.plugin_table.setItem(row, 5, QTableWidgetItem(plugin.last_error or "正常"))
            loaded_at = ""
            if plugin.last_loaded_at:
                loaded_at = datetime.fromtimestamp(plugin.last_loaded_at).strftime("%Y-%m-%d %H:%M:%S")
            self.plugin_table.setItem(row, 6, QTableWidgetItem(loaded_at))
        self.empty_state_label.setVisible(len(plugins) == 0)
        self._restore_selection(selected_plugin_ids)
        self._sync_action_state()

    def _plugin_snapshot(self, plugins) -> dict[int, tuple]:
        snapshot: dict[int, tuple] = {}
        for plugin in plugins:
            snapshot[int(plugin.id)] = (
                plugin.source_type,
                plugin.source_value,
                plugin.display_name,
                bool(plugin.enabled),
                int(plugin.sort_order),
                plugin.cached_file_path,
                int(plugin.last_loaded_at),
                plugin.last_error,
                plugin.config_text,
                int(plugin.plugin_version),
                plugin.category_overrides_json,
            )
        return snapshot

    def _diff_plugin_ids(
        self,
        previous: dict[int, tuple],
        current: dict[int, tuple],
    ) -> list[int]:
        changed = set(previous) ^ set(current)
        for plugin_id in set(previous) & set(current):
            if previous[plugin_id] != current[plugin_id]:
                changed.add(plugin_id)
        return sorted(changed)

    def _has_selection(self) -> bool:
        return bool(self._selected_rows())

    def _selected_rows(self) -> list[int]:
        selection_model = self.plugin_table.selectionModel()
        if selection_model is None:
            return []
        return sorted(index.row() for index in selection_model.selectedRows())

    def _has_single_selection(self) -> bool:
        return len(self._selected_rows()) == 1

    def _is_current_order_sort(self) -> bool:
        return self.sort_combo.currentData() == "sort_order"

    def _selected_plugins(self) -> list:
        plugin_by_id = {int(plugin.id): plugin for plugin in self._all_plugins}
        plugins = []
        for plugin_id in self._selected_plugin_ids():
            plugin = plugin_by_id.get(int(plugin_id))
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    def _has_selected_enabled_plugin(self) -> bool:
        return any(bool(plugin.enabled) for plugin in self._selected_plugins())

    def _has_selected_disabled_plugin(self) -> bool:
        return any(not bool(plugin.enabled) for plugin in self._selected_plugins())

    def _sync_action_state(self) -> None:
        if self._refresh_in_progress:
            self.add_local_button.setEnabled(False)
            self.add_remote_button.setEnabled(False)
            self.import_github_button.setEnabled(False)
            self.rename_button.setEnabled(False)
            self.config_button.setEnabled(False)
            self.category_button.setEnabled(False)
            self.enable_button.setEnabled(False)
            self.disable_button.setEnabled(False)
            self.up_button.setEnabled(False)
            self.down_button.setEnabled(False)
            self.reorder_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.logs_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return
        has_selection = self._has_selection()
        has_single_selection = self._has_single_selection()
        has_selected_enabled_plugin = self._has_selected_enabled_plugin()
        has_selected_disabled_plugin = self._has_selected_disabled_plugin()
        row = self.plugin_table.currentRow() if has_single_selection else -1
        last_row = self.plugin_table.rowCount() - 1
        allow_reorder_nudge = self._is_current_order_sort()
        self.add_local_button.setEnabled(True)
        self.add_remote_button.setEnabled(True)
        self.import_github_button.setEnabled(not self._import_in_progress)
        self.rename_button.setEnabled(has_single_selection)
        self.config_button.setEnabled(has_single_selection)
        self.category_button.setEnabled(has_single_selection)
        self.enable_button.setEnabled(has_selected_disabled_plugin)
        self.disable_button.setEnabled(has_selected_enabled_plugin)
        self.up_button.setEnabled(has_single_selection and allow_reorder_nudge and row > 0)
        self.down_button.setEnabled(has_single_selection and allow_reorder_nudge and row >= 0 and row < last_row)
        self.reorder_button.setEnabled(True)
        self.refresh_button.setEnabled(has_selection)
        self.logs_button.setEnabled(has_single_selection)
        self.delete_button.setEnabled(has_selection)
        self._schedule_plugin_action_reload()

    def _clear_plugin_action_buttons(self) -> None:
        while self.plugin_actions_layout.count():
            item = self.plugin_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.plugin_action_buttons = []

    def _show_placeholder_action_button(self, text: str) -> None:
        self.plugin_actions_empty_label.hide()
        self.plugin_actions_widget.show()
        label = QLabel(text, self.plugin_actions_widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(build_placeholder_label_qss(current_tokens()))
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.plugin_actions_layout.addWidget(label)
        self.plugin_actions_layout.addStretch(1)
        self.plugin_action_buttons.append(label)

    def _render_plugin_actions(self, actions) -> None:
        self._clear_plugin_action_buttons()
        if not actions:
            self._show_placeholder_action_button("无动作")
            return
        self.plugin_actions_empty_label.hide()
        self.plugin_actions_widget.show()
        for action in actions:
            button = QPushButton(action.label, self.plugin_actions_widget)
            button.setEnabled(action.enabled)
            button.setAutoDefault(False)
            button.setDefault(False)
            if action.tooltip:
                button.setToolTip(action.tooltip)
            button.clicked.connect(partial(self._run_plugin_action, action.id))
            self.plugin_actions_layout.addWidget(button)
            self.plugin_action_buttons.append(button)
        self.plugin_actions_layout.addStretch(1)

    def _schedule_plugin_action_reload(self) -> None:
        plugin_id = self._selected_plugin_id()
        self._plugin_action_reload_timer.stop()
        self._pending_plugin_action_id = plugin_id
        if plugin_id is None:
            self._render_plugin_actions([])
            return
        cached_actions = self._plugin_actions_cache.get(plugin_id)
        if cached_actions is not None:
            self._render_plugin_actions(cached_actions)
            return
        self._clear_plugin_action_buttons()
        self._show_placeholder_action_button("加载中")
        self._plugin_action_reload_timer.start(self._ACTION_RELOAD_DELAY_MS)

    def _load_pending_plugin_actions(self) -> None:
        plugin_id = self._pending_plugin_action_id
        if plugin_id is None:
            return
        try:
            actions = self.plugin_manager.list_plugin_actions(plugin_id)
        except Exception:
            actions = []
        self._plugin_actions_cache[plugin_id] = actions
        if self._selected_plugin_id() == plugin_id:
            self._render_plugin_actions(actions)

    def _run_plugin_action(self, action_id: str) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        try:
            self.plugin_manager.run_plugin_action(plugin_id, action_id, parent=self)
        except Exception as exc:
            QMessageBox.warning(self, "插件动作失败", str(exc))
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _restore_selection(self, plugin_ids: list[int]) -> None:
        target_ids = {int(plugin_id) for plugin_id in plugin_ids}
        self.plugin_table.clearSelection()
        self.plugin_table.setCurrentCell(-1, -1)
        selection_model = self.plugin_table.selectionModel()
        if selection_model is None or not target_ids:
            return
        first_row = -1
        for row in range(self.plugin_table.rowCount()):
            item = self.plugin_table.item(row, 0)
            if item is None or int(item.data(256)) not in target_ids:
                continue
            if first_row < 0:
                first_row = row
            index = self.plugin_table.model().index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
        if first_row >= 0:
            current_index = self.plugin_table.model().index(first_row, 0)
            selection_model.setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)

    def _selected_plugin_id(self) -> int | None:
        selected_plugin_ids = self._selected_plugin_ids()
        if len(selected_plugin_ids) != 1:
            return None
        return selected_plugin_ids[0]

    def _selected_plugin_ids(self) -> list[int]:
        plugin_ids: list[int] = []
        for row in self._selected_rows():
            item = self.plugin_table.item(row, 0)
            if item is None:
                continue
            plugin_ids.append(int(item.data(256)))
        return plugin_ids

    def _prompt_display_name(self, current: str) -> str:
        return self.plugin_actions.prompt_display_name(self, current)

    def _prompt_config_text(self, current: str) -> str | None:
        return self.plugin_actions.prompt_config_text(self, current)

    def _pick_local_plugin_path(self) -> str:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Python 插件", "", "Plugin Files (*.py *.txt)")
        return path.strip()

    def _prompt_remote_url(self) -> str:
        value, accepted = QInputDialog.getText(self, "添加远程插件", "Python 文件 URL")
        return value.strip() if accepted else ""

    def _prompt_github_repo_url(self) -> str:
        value, accepted = QInputDialog.getText(self, "从 GitHub 导入", "GitHub 仓库 URL")
        return value.strip() if accepted else ""

    def _update_import_progress(self, dialog: QProgressDialog, event) -> None:
        maximum = max(event.total, 0)
        dialog.setRange(0, maximum)
        dialog.setValue(event.current if maximum else 0)
        dialog.setLabelText(event.message)
        QApplication.processEvents()

    def _add_local_plugin(self) -> None:
        path = self._pick_local_plugin_path()
        if not path:
            return
        self.plugin_manager.add_local_plugin(path)
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _add_remote_plugin(self) -> None:
        url = self._prompt_remote_url()
        if not url:
            return
        self.plugin_manager.add_remote_plugin(url)
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _import_github_repository(self) -> None:
        if self._import_in_progress:
            return
        repo_url = self._prompt_github_repo_url()
        if not repo_url:
            return
        progress = QProgressDialog("", "取消", 0, 0, self)
        progress.setWindowTitle("从 GitHub 导入")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._import_in_progress = True
        self.import_github_button.setEnabled(False)
        progress.setLabelText("正在准备导入...")
        progress.show()
        QApplication.processEvents()
        try:
            result = self.plugin_manager.import_github_repository(
                repo_url,
                progress_callback=lambda event: self._update_import_progress(progress, event),
                cancel_callback=lambda: progress.wasCanceled(),
            )
        except SpiderPluginImportCancelled as exc:
            result = exc.result
            if result.imported_count or result.updated_count:
                self.plugin_tabs_dirty = True
            self.reload_plugins()
            QMessageBox.information(
                self,
                "导入已取消",
                f"已取消：新增 {result.imported_count} 个，更新 {result.updated_count} 个，跳过 {result.skipped_count} 个。",
            )
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
        else:
            if result.imported_count or result.updated_count:
                self.plugin_tabs_dirty = True
            self.reload_plugins()
            QMessageBox.information(
                self,
                "导入完成",
                f"导入完成：新增 {result.imported_count} 个，更新 {result.updated_count} 个，跳过 {result.skipped_count} 个。",
            )
        finally:
            progress.close()
            self._import_in_progress = False
            self.import_github_button.setEnabled(True)

    def _rename_selected(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        current_item = self.plugin_table.item(self.plugin_table.currentRow(), 0)
        if current_item is None:
            return
        current = current_item.text()
        display_name = self._prompt_display_name(current)
        if not display_name:
            return
        try:
            result = self.plugin_actions.apply_rename(plugin_id, display_name)
        except Exception as exc:
            QMessageBox.warning(self, "编辑名称失败", str(exc))
            return
        if not result.changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _edit_selected_config(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        plugin = next((item for item in self.plugin_manager.list_plugins() if item.id == plugin_id), None)
        if plugin is None:
            return
        config_text = self._prompt_config_text(plugin.config_text)
        if config_text is None:
            return
        try:
            result = self.plugin_actions.apply_config(plugin_id, config_text)
        except Exception as exc:
            QMessageBox.warning(self, "编辑配置失败", str(exc))
            return
        if not result.changed:
            return
        self.reload_plugins()

    def _set_selected_enabled(self, enabled: bool) -> None:
        selected_plugin_ids = self._selected_plugin_ids()
        if not selected_plugin_ids:
            return
        plugin_by_id = {int(plugin.id): plugin for plugin in self._all_plugins}
        changed = False
        for plugin_id in selected_plugin_ids:
            plugin = plugin_by_id.get(int(plugin_id))
            if plugin is None or bool(plugin.enabled) == enabled:
                continue
            self.plugin_actions.apply_toggle_enabled(plugin_id, enabled)
            changed = True
        if not changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins(selected_plugin_ids)

    def _enable_selected(self) -> None:
        self._set_selected_enabled(True)

    def _disable_selected(self) -> None:
        self._set_selected_enabled(False)

    def _toggle_selected_enabled(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        enabled_item = self.plugin_table.item(self.plugin_table.currentRow(), 4)
        if enabled_item is None:
            return
        enabled_text = enabled_item.text()
        try:
            result = self.plugin_actions.apply_toggle_enabled(plugin_id, enabled_text != "是")
        except Exception as exc:
            QMessageBox.warning(self, "更新插件状态失败", str(exc))
            return
        if not result.changed:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _move_selected(self, direction: int) -> None:
        if not self._is_current_order_sort():
            return
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        self.plugin_manager.move_plugin(plugin_id, direction)
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _open_reorder_dialog(self) -> None:
        dialog = PluginReorderDialog(self.plugin_manager, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _open_category_manager_dialog(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        dialog = PluginCategoryManagerDialog(self.plugin_manager, plugin_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _refresh_selected(self) -> None:
        if self._refresh_in_progress:
            return
        plugin_ids = self._selected_plugin_ids()
        if not plugin_ids:
            return
        self._refresh_target_plugin_ids = list(plugin_ids)
        self._refresh_in_progress = True
        self._sync_action_state()

        def run() -> None:
            try:
                for plugin_id in plugin_ids:
                    self.plugin_manager.refresh_plugin(plugin_id)
            except Exception as exc:
                self._refresh_signals.failed.emit(str(exc))
                return
            self._refresh_signals.completed.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_refresh_completed(self) -> None:
        target_plugin_ids = list(self._refresh_target_plugin_ids)
        self._refresh_target_plugin_ids = []
        self._refresh_in_progress = False
        self.plugin_tabs_dirty = True
        self.reload_plugins(target_plugin_ids)

    def _handle_refresh_failed(self, message: str) -> None:
        target_plugin_ids = list(self._refresh_target_plugin_ids)
        self._refresh_target_plugin_ids = []
        self._refresh_in_progress = False
        self.reload_plugins(target_plugin_ids)
        QMessageBox.warning(self, "刷新失败", message)

    def _delete_selected(self) -> None:
        plugin_ids = self._selected_plugin_ids()
        if not plugin_ids:
            return
        for plugin_id in plugin_ids:
            self.plugin_manager.delete_plugin(plugin_id)
        self.plugin_tabs_dirty = True
        self.reload_plugins()

    def _show_logs(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("插件日志")
        dialog.resize(680, 420)
        view = QTextEdit(dialog)
        view.setReadOnly(True)
        lines = [f"[{entry.level}] {entry.message}" for entry in self.plugin_manager.list_logs(plugin_id)]
        view.setPlainText("\n".join(lines))
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        dialog.exec()
