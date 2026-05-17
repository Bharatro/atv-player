from __future__ import annotations

from datetime import datetime
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from atv_player.api import ApiError, UnauthorizedError
from atv_player.models import HistoryRecord
from atv_player.ui.async_guard import AsyncGuardMixin
from atv_player.ui.table_utils import configure_table_columns


class _HistoryLoadSignals(QObject):
    succeeded = Signal(int, int, int, object, int)
    failed = Signal(int)
    unauthorized = Signal(int)


class _HistoryMutationSignals(QObject):
    succeeded = Signal(int, int)
    failed = Signal(int)
    unauthorized = Signal(int)


class HistoryPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(object)
    unauthorized = Signal()

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._initial_load_started = False
        self.delete_button = QPushButton("删除")
        self.clear_button = QPushButton("清空")
        self.refresh_button = QPushButton("刷新")
        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
        self.page_size_combo = QComboBox()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["标题", "集数", "当前播放", "进度", "时间", "来源"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_table_columns(self.table, stretch_column=0)
        self.records: list[HistoryRecord] = []
        self.current_page = 1
        self.page_size = 100
        self.total_items = 0
        self._load_request_id = 0
        self._mutation_request_id = 0
        self._keyword = ""
        self._source_kind = ""
        self._time_range = ""
        self._continue_watching = False
        self._load_signals = _HistoryLoadSignals()
        self._connect_async_signal(self._load_signals.succeeded, self._handle_load_succeeded)
        self._connect_async_signal(self._load_signals.failed, self._handle_load_failed)
        self._connect_async_signal(self._load_signals.unauthorized, self._handle_load_unauthorized)
        self._mutation_signals = _HistoryMutationSignals()
        self._connect_async_signal(self._mutation_signals.succeeded, self._handle_mutation_succeeded)
        self._connect_async_signal(self._mutation_signals.failed, self._handle_mutation_failed)
        self._connect_async_signal(self._mutation_signals.unauthorized, self._handle_mutation_unauthorized)
        for size in ("20", "30", "50", "100"):
            self.page_size_combo.addItem(size, int(size))
        self.page_size_combo.setCurrentText(str(self.page_size))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            """
            QLineEdit {
                min-height: 30px;
                padding: 0 10px;
                border: 1px solid #d0d7de;
                border-radius: 15px;
                background: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #409eff;
            }
            """
        )

        self.source_combo = QComboBox()
        for label, value in (
            ("全部来源", ""),
            ("远程", "remote"),
            ("插件", "spider_plugin"),
            ("Emby", "emby"),
            ("B站", "bilibili"),
            ("Jellyfin", "jellyfin"),
            ("飞牛影视", "feiniu"),
            ("全局解析", "direct_parse"),
        ):
            self.source_combo.addItem(label, value)

        self.time_combo = QComboBox()
        self.time_combo.addItem("全部时间", "")
        self.time_combo.addItem("最近7天", "7d")
        self.time_combo.addItem("最近30天", "30d")

        self.continue_button = QPushButton("继续观看")
        self.continue_button.setCheckable(True)
        self.continue_button.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                color: #1a1a1a;
                border: 1px solid #d0d0d0;
                border-radius: 14px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton:checked {
                background-color: #ffffff;
                color: #0066cc;
                border: 1px solid #0066cc;
            }
            """
        )

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)

        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.prev_page_button)
        actions.addWidget(self.page_label)
        actions.addWidget(self.next_page_button)
        actions.addWidget(self.page_size_combo)

        self.content_container = QWidget()
        self.content_container.setMaximumWidth(1800)
        self.content_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)

        filters = QHBoxLayout()
        filters.addWidget(self.search_edit, 3)
        filters.addWidget(self.source_combo)
        filters.addWidget(self.time_combo)
        filters.addWidget(self.continue_button)
        content_layout.addLayout(filters)

        content_layout.addLayout(actions)
        content_layout.addWidget(self.table)

        layout = QHBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.content_container, 100)
        layout.addStretch(1)

        self.delete_button.clicked.connect(self.delete_selected)
        self.clear_button.clicked.connect(self.clear_all)
        self.refresh_button.clicked.connect(self.load_history)
        self.table.cellDoubleClicked.connect(self._open_selected)
        self.table.itemSelectionChanged.connect(self._sync_action_state)
        self.prev_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.page_size_combo.currentIndexChanged.connect(self._change_page_size)
        self._search_timer.timeout.connect(self._apply_search)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.time_combo.currentIndexChanged.connect(self._on_time_changed)
        self.continue_button.toggled.connect(self._on_continue_watching_toggled)
        self._update_pagination_controls()
        self._sync_action_state()

    def ensure_loaded(self) -> None:
        if self._initial_load_started:
            return
        self._initial_load_started = True
        self.load_history()

    def load_history(self) -> None:
        self._initial_load_started = True
        self._load_request_id += 1
        request_id = self._load_request_id
        page = self.current_page
        size = self.page_size
        keyword = self._keyword
        source_kind = self._source_kind
        time_range = self._time_range
        continue_watching = self._continue_watching

        def run() -> None:
            try:
                records, total = self.controller.load_page(
                    page=page,
                    size=size,
                    keyword=keyword,
                    source_kind=source_kind,
                    time_range=time_range,
                    continue_watching=continue_watching,
                )
            except UnauthorizedError:
                if not self._can_deliver_worker_result():
                    return
                self._load_signals.unauthorized.emit(request_id)
                return
            except ApiError:
                if not self._can_deliver_worker_result():
                    return
                self._load_signals.failed.emit(request_id)
                return
            if not self._can_deliver_worker_result():
                return
            self._load_signals.succeeded.emit(request_id, page, size, records, total)

        threading.Thread(target=run, daemon=True).start()

    def delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        records = [self.records[row] for row in rows]
        next_page = (
            self.current_page - 1 if len(records) == len(self.records) and self.current_page > 1 else self.current_page
        )

        def run() -> None:
            try:
                self.controller.delete_many(records)
            except UnauthorizedError:
                if not self._can_deliver_worker_result():
                    return
                self._mutation_signals.unauthorized.emit(request_id)
                return
            except ApiError:
                if not self._can_deliver_worker_result():
                    return
                self._mutation_signals.failed.emit(request_id)
                return
            if not self._can_deliver_worker_result():
                return
            self._mutation_signals.succeeded.emit(request_id, next_page)

        self._mutation_request_id += 1
        request_id = self._mutation_request_id
        threading.Thread(target=run, daemon=True).start()

    def clear_all(self) -> None:
        records = list(self.records)
        self._mutation_request_id += 1
        request_id = self._mutation_request_id

        def run() -> None:
            try:
                self.controller.clear_page(records)
            except UnauthorizedError:
                if not self._can_deliver_worker_result():
                    return
                self._mutation_signals.unauthorized.emit(request_id)
                return
            except ApiError:
                if not self._can_deliver_worker_result():
                    return
                self._mutation_signals.failed.emit(request_id)
                return
            if not self._can_deliver_worker_result():
                return
            self._mutation_signals.succeeded.emit(request_id, 1)

        threading.Thread(target=run, daemon=True).start()

    def _open_selected(self, row: int, _column: int) -> None:
        if not (0 <= row < len(self.records)):
            return
        self.open_detail_requested.emit(self.records[row])

    def _on_search_text_changed(self) -> None:
        self._search_timer.start()

    def _apply_search(self) -> None:
        keyword = self.search_edit.text().strip()
        if keyword == self._keyword:
            return
        self._keyword = keyword
        self.current_page = 1
        self.load_history()

    def _on_source_changed(self) -> None:
        self._source_kind = self.source_combo.currentData() or ""
        self.current_page = 1
        self.load_history()

    def _on_time_changed(self) -> None:
        self._time_range = self.time_combo.currentData() or ""
        self.current_page = 1
        self.load_history()

    def _on_continue_watching_toggled(self, checked: bool) -> None:
        self._continue_watching = checked
        self.current_page = 1
        self.load_history()

    def _source_label(self, record: HistoryRecord) -> str:
        if record.source_kind == "spider_plugin":
            return record.source_name or record.source_plugin_name or "插件"
        if record.source_kind == "emby":
            return record.source_name or "Emby"
        if record.source_kind == "bilibili":
            return record.source_name or "B站"
        if record.source_kind == "jellyfin":
            return record.source_name or "Jellyfin"
        if record.source_kind == "feiniu":
            return record.source_name or "飞牛影视"
        if record.source_kind == "direct_parse":
            return record.source_name or "全局解析"
        return "远程"

    def _format_episode(self, episode: int) -> str:
        return str(episode + 1) if episode >= 0 else ""

    def _format_duration(self, milliseconds: int) -> str:
        total_seconds = max(milliseconds // 1000, 0)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _format_timestamp(self, milliseconds: int) -> str:
        return datetime.fromtimestamp(milliseconds / 1000).strftime("%Y-%m-%d %H:%M:%S")

    def previous_page(self) -> None:
        if self.current_page <= 1:
            return
        self.current_page -= 1
        self.load_history()

    def next_page(self) -> None:
        if self.current_page >= self._total_pages():
            return
        self.current_page += 1
        self.load_history()

    def _change_page_size(self) -> None:
        page_size = self.page_size_combo.currentData()
        if page_size is None:
            return
        page_size = int(page_size)
        if page_size == self.page_size:
            return
        self.page_size = page_size
        self.current_page = 1
        self.load_history()

    def _total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)

    def _update_pagination_controls(self) -> None:
        total_pages = self._total_pages()
        self.page_label.setText(f"第 {self.current_page} / {total_pages} 页")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < total_pages)

    def _sync_action_state(self) -> None:
        selection_model = self.table.selectionModel()
        has_selection = bool(selection_model is not None and selection_model.hasSelection())
        self.delete_button.setEnabled(has_selection)
        self.clear_button.setEnabled(bool(self.records))

    def _handle_load_succeeded(
        self,
        request_id: int,
        page: int,
        size: int,
        records: list[HistoryRecord],
        total: int,
    ) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._load_request_id:
            return
        if page != self.current_page or size != self.page_size:
            return
        self.total_items = total
        self.records = list(records)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(record.vod_name))
            self.table.setItem(row, 1, QTableWidgetItem(self._format_episode(record.episode)))
            self.table.setItem(row, 2, QTableWidgetItem(record.vod_remarks))
            self.table.setItem(row, 3, QTableWidgetItem(self._format_duration(record.position)))
            self.table.setItem(row, 4, QTableWidgetItem(self._format_timestamp(record.create_time)))
            self.table.setItem(row, 5, QTableWidgetItem(self._source_label(record)))
        self._sync_action_state()
        self._update_pagination_controls()

    def _handle_load_failed(self, request_id: int) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._load_request_id:
            return

    def _handle_load_unauthorized(self, request_id: int) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._load_request_id:
            return
        self.unauthorized.emit()

    def _handle_mutation_succeeded(self, request_id: int, next_page: int) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._mutation_request_id:
            return
        self.current_page = next_page
        self.load_history()

    def _handle_mutation_failed(self, request_id: int) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._mutation_request_id:
            return

    def _handle_mutation_unauthorized(self, request_id: int) -> None:
        if not self._can_deliver_worker_result():
            return
        if request_id != self._mutation_request_id:
            return
        self.unauthorized.emit()

    def _can_deliver_worker_result(self) -> bool:
        return self._can_deliver_async_result()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._deactivate_async_guard()
        super().closeEvent(event)
