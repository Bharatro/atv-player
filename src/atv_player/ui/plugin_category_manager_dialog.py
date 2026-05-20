from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
)

from atv_player.models import SpiderPluginCategoryOverrides
from atv_player.plugins.category_overrides import dumps_category_overrides_json, parse_category_overrides_json
from atv_player.ui.window_chrome import ThemedDialogBase


@dataclass(slots=True)
class _CategoryRow:
    type_id: str
    raw_name: str
    display_name: str
    hidden: bool = False


class PluginCategoryManagerDialog(ThemedDialogBase):
    def __init__(self, plugin_manager, plugin_id: int, parent=None) -> None:
        super().__init__(title="分类管理", parent=parent)
        self.plugin_manager = plugin_manager
        self.plugin_id = plugin_id
        self.resize(520, 460)

        self.plugin = next(
            item for item in self.plugin_manager.list_plugins() if int(getattr(item, "id", 0)) == int(plugin_id)
        )
        self.raw_categories = list(self.plugin_manager.load_plugin_categories(plugin_id))
        self._default_rows = self._build_default_rows()
        self._draft_rows = self._build_rows_from_overrides(
            parse_category_overrides_json(getattr(self.plugin, "category_overrides_json", ""))
        )

        self.category_list = QListWidget(self)
        self.category_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.top_button = QPushButton("置顶", self)
        self.up_button = QPushButton("上移", self)
        self.down_button = QPushButton("下移", self)
        self.bottom_button = QPushButton("置底", self)
        self.rename_button = QPushButton("重命名", self)
        self.hide_button = QPushButton("隐藏/显示", self)
        self.reset_button = QPushButton("恢复默认", self)
        self.save_button = QPushButton("保存", self)
        self.cancel_button = QPushButton("取消", self)

        controls = QHBoxLayout()
        for button in (
            self.top_button,
            self.up_button,
            self.down_button,
            self.bottom_button,
            self.rename_button,
            self.hide_button,
            self.reset_button,
        ):
            controls.addWidget(button)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)

        layout = self.content_layout()
        layout.addWidget(self.category_list)
        layout.addLayout(controls)
        layout.addLayout(footer)

        self.top_button.clicked.connect(self._move_to_top)
        self.up_button.clicked.connect(self._move_up)
        self.down_button.clicked.connect(self._move_down)
        self.bottom_button.clicked.connect(self._move_to_bottom)
        self.rename_button.clicked.connect(self._rename_selected)
        self.hide_button.clicked.connect(self._toggle_hidden)
        self.reset_button.clicked.connect(self._restore_defaults)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self.category_list.currentRowChanged.connect(self._sync_action_state)

        self._render_rows()

    def _build_default_rows(self) -> list[_CategoryRow]:
        return [
            _CategoryRow(type_id=item.type_id, raw_name=item.type_name, display_name=item.type_name, hidden=False)
            for item in self.raw_categories
        ]

    def _copy_row(self, row: _CategoryRow) -> _CategoryRow:
        return _CategoryRow(
            type_id=row.type_id,
            raw_name=row.raw_name,
            display_name=row.display_name,
            hidden=row.hidden,
        )

    def _build_rows_from_overrides(self, overrides: SpiderPluginCategoryOverrides) -> list[_CategoryRow]:
        base_rows = [self._copy_row(row) for row in self._default_rows]
        by_id = {row.type_id: row for row in base_rows}
        ordered_ids: list[str] = []
        for type_id in overrides.order:
            if type_id in by_id and type_id not in ordered_ids:
                ordered_ids.append(type_id)
        for row in base_rows:
            if row.type_id not in ordered_ids:
                ordered_ids.append(row.type_id)
        hidden = set(overrides.hidden)
        rows: list[_CategoryRow] = []
        for type_id in ordered_ids:
            row = self._copy_row(by_id[type_id])
            renamed = overrides.renames.get(type_id, "")
            if renamed:
                row.display_name = renamed
            row.hidden = type_id in hidden
            rows.append(row)
        return rows

    def _current_row(self) -> int:
        return self.category_list.currentRow()

    def _current_row_object(self) -> _CategoryRow | None:
        row = self._current_row()
        if row < 0 or row >= len(self._draft_rows):
            return None
        return self._draft_rows[row]

    def _render_rows(self, current_row: int | None = None) -> None:
        if current_row is None:
            current_row = self._current_row()
        self.category_list.clear()
        for row in self._draft_rows:
            label = row.display_name
            if row.hidden:
                label = f"{label}（已隐藏）"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, row.type_id)
            self.category_list.addItem(item)
        if self.category_list.count():
            if current_row is None or current_row < 0:
                current_row = 0
            self.category_list.setCurrentRow(min(current_row, self.category_list.count() - 1))
        self._sync_action_state()

    def _move_row(self, target_row: int) -> None:
        row = self._current_row()
        if row < 0 or row == target_row or not (0 <= target_row < len(self._draft_rows)):
            return
        item = self._draft_rows.pop(row)
        self._draft_rows.insert(target_row, item)
        self._render_rows(target_row)

    def _move_to_top(self) -> None:
        self._move_row(0)

    def _move_up(self) -> None:
        row = self._current_row()
        if row > 0:
            self._move_row(row - 1)

    def _move_down(self) -> None:
        row = self._current_row()
        if 0 <= row < len(self._draft_rows) - 1:
            self._move_row(row + 1)

    def _move_to_bottom(self) -> None:
        if self._draft_rows:
            self._move_row(len(self._draft_rows) - 1)

    def _prompt_display_name(self, current: str) -> str:
        value, accepted = QInputDialog.getText(self, "重命名分类", "显示名称", text=current)
        return value.strip() if accepted else ""

    def _rename_selected(self) -> None:
        row = self._current_row_object()
        if row is None:
            return
        value = self._prompt_display_name(row.display_name)
        if not value:
            return
        row.display_name = value
        self._render_rows()

    def _toggle_hidden(self) -> None:
        row = self._current_row_object()
        if row is None:
            return
        row.hidden = not row.hidden
        self._render_rows()

    def _restore_defaults(self) -> None:
        self._draft_rows = [self._copy_row(row) for row in self._default_rows]
        self._render_rows(0)

    def _compose_override_json(self) -> str:
        overrides = SpiderPluginCategoryOverrides(
            order=[row.type_id for row in self._draft_rows],
            hidden=[row.type_id for row in self._draft_rows if row.hidden],
            renames={
                row.type_id: row.display_name
                for row in self._draft_rows
                if row.display_name.strip() and row.display_name.strip() != row.raw_name
            },
        )
        return dumps_category_overrides_json(overrides)

    def _save(self) -> None:
        try:
            self.plugin_manager.set_plugin_category_overrides(self.plugin_id, self._compose_override_json())
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.accept()

    def _sync_action_state(self, *_args) -> None:
        row = self._current_row()
        last_row = len(self._draft_rows) - 1
        has_selection = row >= 0
        self.top_button.setEnabled(has_selection and row > 0)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row >= 0 and row < last_row)
        self.bottom_button.setEnabled(has_selection and row >= 0 and row < last_row)
        self.rename_button.setEnabled(has_selection)
        self.hide_button.setEnabled(has_selection)
