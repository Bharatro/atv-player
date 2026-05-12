from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class PluginTabDrawer(QWidget):
    plugin_selected = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.SubWindow)
        self.setFixedWidth(280)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索隐藏插件")
        self.empty_label = QLabel("没有匹配的插件", self)
        self.list_widget = QListWidget(self)
        self._items: list[tuple[str, str, bool]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.list_widget, 1)

        self.setStyleSheet(
            """
            PluginTabDrawer {
                background: #ffffff;
                border: 1px solid #d0d7de;
            }
            """
        )

        self.search_edit.textChanged.connect(self._apply_filter)
        self.list_widget.itemActivated.connect(self._handle_item_activated)
        self.list_widget.itemClicked.connect(self._handle_item_activated)
        escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape_shortcut.activated.connect(self.close_requested.emit)

    def set_plugins(self, items: list[tuple[str, str, bool]]) -> None:
        self._items = list(items)
        self._apply_filter()

    def visible_items(self) -> list[QListWidgetItem]:
        return [self.list_widget.item(index) for index in range(self.list_widget.count())]

    def select_plugin_by_title(self, title: str) -> None:
        for item in self.visible_items():
            if item.text() == title:
                self.list_widget.setCurrentItem(item)
                self._handle_item_activated(item)
                return
        raise ValueError(f"unknown plugin title: {title}")

    def _handle_item_activated(self, item: QListWidgetItem) -> None:
        plugin_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(plugin_key, str) and plugin_key:
            self.plugin_selected.emit(plugin_key)

    def _apply_filter(self) -> None:
        keyword = self.search_edit.text().strip().lower()
        self.list_widget.clear()
        active_item: QListWidgetItem | None = None
        for key, title, active in self._items:
            if keyword and keyword not in title.lower():
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            if active:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                active_item = item
            self.list_widget.addItem(item)
        self.empty_label.setVisible(self.list_widget.count() == 0)
        self.list_widget.setVisible(self.list_widget.count() > 0)
        if active_item is not None:
            self.list_widget.setCurrentItem(active_item)

    def minimumSizeHint(self) -> QSize:
        if self.isHidden():
            return QSize(0, 0)
        return super().minimumSizeHint()

    def sizeHint(self) -> QSize:
        if self.isHidden():
            return QSize(0, 0)
        return super().sizeHint()
