from PySide6.QtCore import Qt

from atv_player.models import SpiderPluginConfig
from atv_player.ui.plugin_reorder_dialog import PluginReorderDialog


class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SpiderPluginConfig(
                id=1,
                source_type="local",
                source_value="/plugins/1.py",
                display_name="插件1",
                enabled=True,
                sort_order=0,
            ),
            SpiderPluginConfig(
                id=2,
                source_type="local",
                source_value="/plugins/2.py",
                display_name="插件2",
                enabled=False,
                sort_order=1,
            ),
            SpiderPluginConfig(
                id=3,
                source_type="local",
                source_value="/plugins/3.py",
                display_name="插件3",
                enabled=True,
                sort_order=2,
            ),
        ]
        self.reorder_calls: list[list[int]] = []
        self.reorder_error: Exception | None = None

    def list_plugins(self):
        return list(self.plugins)

    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        if self.reorder_error is not None:
            raise self.reorder_error
        self.reorder_calls.append(list(plugin_ids_in_order))
        by_id = {plugin.id: plugin for plugin in self.plugins}
        self.plugins = [by_id[plugin_id] for plugin_id in plugin_ids_in_order]
        for sort_order, plugin in enumerate(self.plugins):
            plugin.sort_order = sort_order


def test_plugin_reorder_dialog_uses_custom_title_bar(qtbot) -> None:
    dialog = PluginReorderDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert dialog.title_bar().title_label.text() == "调整插件顺序"


def test_plugin_reorder_dialog_uses_current_plugin_order_as_initial_draft(qtbot) -> None:
    dialog = PluginReorderDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    assert [
        dialog.plugin_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(dialog.plugin_list.count())
    ] == [1, 2, 3]


def test_plugin_reorder_dialog_buttons_only_change_local_draft_until_save(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_list.setCurrentRow(2)

    dialog._move_to_top()
    dialog._move_down()

    assert [
        dialog.plugin_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(dialog.plugin_list.count())
    ] == [1, 3, 2]
    assert manager.reorder_calls == []


def test_plugin_reorder_dialog_save_persists_current_list_order(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    item = dialog.plugin_list.takeItem(2)
    dialog.plugin_list.insertItem(0, item)
    dialog.plugin_list.setCurrentRow(0)

    dialog._save()

    assert manager.reorder_calls == [[3, 1, 2]]
    assert dialog.result() == dialog.DialogCode.Accepted


def test_plugin_reorder_dialog_cancel_discards_changes(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_list.setCurrentRow(1)
    dialog._move_to_bottom()

    dialog.reject()

    assert manager.reorder_calls == []


def test_plugin_reorder_dialog_save_failure_shows_warning_and_keeps_dialog_open(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    manager.reorder_error = ValueError("插件列表已变化，请重新打开排序窗口")
    dialog = PluginReorderDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    warnings: list[str] = []

    monkeypatch.setattr(
        "atv_player.ui.plugin_reorder_dialog.QMessageBox.warning",
        lambda *args: warnings.append(args[2]),
    )

    dialog._save()

    assert warnings == ["插件列表已变化，请重新打开排序窗口"]
    assert dialog.isVisible() is True
    assert dialog.result() == 0
