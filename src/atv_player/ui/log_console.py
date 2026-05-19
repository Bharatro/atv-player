from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from atv_player.log_store import AppLogFilter
from atv_player.ui.theme import (
    FlatComboBox,
    build_form_combobox_qss,
    build_form_line_edit_qss,
    configure_form_flat_combobox,
    current_tokens,
)


class LogConsoleWidget(QWidget):
    def __init__(self, *, config, save_config, app_log_service) -> None:
        super().__init__()
        self._config = config
        self._save_config = save_config
        self._app_log_service = app_log_service
        self._records = []
        self.logging_enabled_checkbox = QCheckBox("启用日志记录")
        self.logging_enabled_checkbox.setChecked(bool(getattr(config, "logging_enabled", True)))
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索消息 / 剧名 / 剧集")
        self.source_combo = FlatComboBox()
        self.source_combo.addItem("全部来源", "")
        self.source_combo.addItem("播放窗口", "player")
        self.source_combo.addItem("后台", "app")
        self.level_combo = FlatComboBox()
        self.level_combo.addItem("全部级别", "")
        self.level_combo.addItem("DEBUG", "DEBUG")
        self.level_combo.addItem("INFO", "INFO")
        self.level_combo.addItem("WARNING", "WARNING")
        self.level_combo.addItem("ERROR", "ERROR")
        self.level_combo.addItem("CRITICAL", "CRITICAL")
        self.category_combo = FlatComboBox()
        self.category_combo.addItem("全部分类", "")
        for label, value in (
            ("播放", "playback"),
            ("应用", "app"),
            ("直播", "live"),
            ("元数据", "metadata"),
            ("插件", "plugin"),
            ("网络", "network"),
            ("弹幕", "danmaku"),
        ):
            self.category_combo.addItem(label, value)
        self.refresh_button = QPushButton("刷新")
        self.export_button = QPushButton("导出日志")
        self.clear_button = QPushButton("清空日志")
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["时间", "级别", "来源", "分类", "消息"])
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("选择一条日志后显示详情")

        top_row = QHBoxLayout()
        top_row.addWidget(self.logging_enabled_checkbox)
        top_row.addStretch(1)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.search_edit, 3)
        filter_row.addWidget(self.source_combo, 1)
        filter_row.addWidget(self.level_combo, 1)
        filter_row.addWidget(self.category_combo, 1)
        filter_row.addWidget(self.refresh_button)
        filter_row.addWidget(self.export_button)
        filter_row.addWidget(self.clear_button)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.log_table)
        splitter.addWidget(self.detail_view)
        splitter.setSizes([320, 180])

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.status_label)
        layout.addLayout(filter_row)
        layout.addWidget(splitter, 1)

        self.logging_enabled_checkbox.toggled.connect(self._update_status_banner)
        self.search_edit.returnPressed.connect(self.reload_records)
        self.refresh_button.clicked.connect(self.reload_records)
        self.export_button.clicked.connect(self._export_records)
        self.clear_button.clicked.connect(self._clear_logs)
        self.log_table.itemSelectionChanged.connect(self._render_selected_detail)

        self.apply_theme()
        self.reload_records()

    def apply_theme(self) -> None:
        tokens = current_tokens()
        combo_qss = build_form_combobox_qss(tokens)
        line_edit_qss = build_form_line_edit_qss(tokens)
        for combo in (self.source_combo, self.level_combo, self.category_combo):
            combo.setStyleSheet(combo_qss)
            configure_form_flat_combobox(combo, tokens)
        self.search_edit.setStyleSheet(line_edit_qss)
        self.search_edit.setFixedHeight(42)
        self.status_label.setStyleSheet(f"color: {tokens.text_secondary};")
        self.log_table.setStyleSheet(
            f"""
            QTableWidget {{
                background: {tokens.panel_bg};
                color: {tokens.text_primary};
                border: 1px solid {tokens.input_border};
                gridline-color: {tokens.border_subtle};
                alternate-background-color: {tokens.panel_alt_bg};
            }}
            QHeaderView::section {{
                background: {tokens.panel_alt_bg};
                color: {tokens.text_primary};
                border: none;
                border-bottom: 1px solid {tokens.border_subtle};
                padding: 6px 8px;
            }}
            QTableWidget::item:selected {{
                background: {tokens.menu_selected_bg};
                color: {tokens.text_primary};
            }}
            """
        )
        self.detail_view.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: {tokens.panel_bg};
                color: {tokens.text_primary};
                border: 1px solid {tokens.input_border};
                border-radius: 12px;
                padding: 10px;
            }}
            """
        )

    def reload_records(self) -> None:
        if self._app_log_service is None:
            self._records = []
            self._render_records()
            self._update_status_banner("日志服务不可用")
            return
        try:
            self._records = self._app_log_service.load_records(
                limit=2000,
                log_filter=AppLogFilter(
                    query=self.search_edit.text().strip(),
                    source=str(self.source_combo.currentData() or ""),
                    level=str(self.level_combo.currentData() or ""),
                    category=str(self.category_combo.currentData() or ""),
                ),
            )
        except Exception as exc:
            self._records = []
            self._render_records()
            self._update_status_banner(f"日志读取失败: {exc}")
            return
        self._render_records()
        self._update_status_banner()

    def _render_records(self) -> None:
        self.log_table.clearContents()
        self.log_table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            self.log_table.setItem(row, 0, QTableWidgetItem(record.timestamp))
            self.log_table.setItem(row, 1, QTableWidgetItem(record.level))
            self.log_table.setItem(row, 2, QTableWidgetItem(record.source))
            self.log_table.setItem(row, 3, QTableWidgetItem(record.category))
            self.log_table.setItem(row, 4, QTableWidgetItem(record.message))
        if self._records:
            self.log_table.selectRow(0)
        else:
            self.detail_view.clear()

    def _render_selected_detail(self) -> None:
        row = self.log_table.currentRow()
        if not (0 <= row < len(self._records)):
            self.detail_view.clear()
            return
        record = self._records[row]
        lines = [
            f"时间: {record.timestamp}",
            f"级别: {record.level}",
            f"来源: {record.source}",
            f"分类: {record.category}",
            f"模块: {record.module}",
            f"消息: {record.message}",
            f"剧名: {record.vod_name}" if record.vod_name else "",
            f"剧集: {record.episode_title}" if record.episode_title else "",
            f"会话: {record.session_id}" if record.session_id else "",
            f"URL 摘要: {record.url_summary}" if record.url_summary else "",
            f"异常: {record.exception}" if record.exception else "",
        ]
        self.detail_view.setPlainText("\n".join(line for line in lines if line))

    def _update_status_banner(self, override: str | bool | None = None) -> None:
        if isinstance(override, bool):
            override = None
        if override is not None:
            self.status_label.setText(override)
            return
        if self._app_log_service is None:
            self.status_label.setText("日志服务不可用")
            return
        if not self.logging_enabled_checkbox.isChecked():
            self.status_label.setText("日志记录已关闭，当前仅可查看历史日志")
            return
        if self._records:
            self.status_label.setText(f"已加载 {len(self._records)} 条日志")
            return
        self.status_label.setText("暂无日志")

    def _export_records(self) -> None:
        if self._app_log_service is None or not self._records:
            return
        filename, _selected = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            "atv-player.log",
            "Log Files (*.log)",
        )
        if not filename:
            return
        try:
            self._app_log_service.export_records(self._records, Path(filename))
        except Exception as exc:
            self._update_status_banner(f"日志导出失败: {exc}")
            return
        self._update_status_banner(f"已导出 {len(self._records)} 条日志")

    def _clear_logs(self) -> None:
        if self._app_log_service is None:
            return
        answer = QMessageBox.question(self, "清空日志", "确认清空所有日志和归档吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._app_log_service.clear()
        except Exception as exc:
            self._update_status_banner(f"日志清空失败: {exc}")
            return
        self.reload_records()
