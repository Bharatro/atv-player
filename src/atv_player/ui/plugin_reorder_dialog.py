from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class PluginReorderDialog(QDialog):
    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.setWindowTitle("调整插件顺序")
        self.resize(520, 460)

        self.plugin_list = QListWidget(self)
        self.plugin_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.plugin_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.plugin_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.top_button = QPushButton("置顶", self)
        self.up_button = QPushButton("上移", self)
        self.down_button = QPushButton("下移", self)
        self.bottom_button = QPushButton("置底", self)
        self.save_button = QPushButton("保存", self)
        self.cancel_button = QPushButton("取消", self)

        controls = QHBoxLayout()
        for button in (self.top_button, self.up_button, self.down_button, self.bottom_button):
            controls.addWidget(button)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.plugin_list)
        layout.addLayout(controls)
        layout.addLayout(footer)

        self.top_button.clicked.connect(self._move_to_top)
        self.up_button.clicked.connect(self._move_up)
        self.down_button.clicked.connect(self._move_down)
        self.bottom_button.clicked.connect(self._move_to_bottom)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self.plugin_list.currentRowChanged.connect(self._sync_action_state)

        self._load_plugins()

    def _load_plugins(self) -> None:
        self.plugin_list.clear()
        for plugin in self.plugin_manager.list_plugins():
            label = f"{plugin.display_name}（{'启用' if plugin.enabled else '禁用'}）"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, plugin.id)
            self.plugin_list.addItem(item)
        if self.plugin_list.count():
            self.plugin_list.setCurrentRow(0)
        self._sync_action_state()

    def _current_row(self) -> int:
        return self.plugin_list.currentRow()

    def _move_row(self, target_row: int) -> None:
        row = self._current_row()
        if row < 0 or row == target_row:
            return
        item = self.plugin_list.takeItem(row)
        self.plugin_list.insertItem(target_row, item)
        self.plugin_list.setCurrentRow(target_row)
        self._sync_action_state()

    def _move_to_top(self) -> None:
        self._move_row(0)

    def _move_up(self) -> None:
        row = self._current_row()
        if row > 0:
            self._move_row(row - 1)

    def _move_down(self) -> None:
        row = self._current_row()
        if 0 <= row < self.plugin_list.count() - 1:
            self._move_row(row + 1)

    def _move_to_bottom(self) -> None:
        if self.plugin_list.count():
            self._move_row(self.plugin_list.count() - 1)

    def _ordered_plugin_ids(self) -> list[int]:
        return [
            int(self.plugin_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.plugin_list.count())
        ]

    def _save(self) -> None:
        try:
            self.plugin_manager.reorder_plugins(self._ordered_plugin_ids())
        except Exception as exc:
            QMessageBox.warning(self, "排序保存失败", str(exc))
            return
        self.accept()

    def _sync_action_state(self, *_args) -> None:
        row = self._current_row()
        last_row = self.plugin_list.count() - 1
        has_selection = row >= 0
        self.top_button.setEnabled(has_selection and row > 0)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row >= 0 and row < last_row)
        self.bottom_button.setEnabled(has_selection and row >= 0 and row < last_row)
