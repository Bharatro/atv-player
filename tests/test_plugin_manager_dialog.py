from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel

from atv_player.models import (
    SpiderPluginAction,
    SpiderPluginConfig,
    SpiderPluginImportProgress,
    SpiderPluginImportResult,
    SpiderPluginLogEntry,
)
from atv_player.ui.plugin_manager_dialog import PluginManagerDialog


class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SpiderPluginConfig(
                id=1,
                source_type="local",
                source_value="/plugins/a.py",
                display_name="本地A",
                enabled=True,
                sort_order=0,
                config_text="token=local",
            ),
            SpiderPluginConfig(
                id=2,
                source_type="remote",
                source_value="https://example.com/b.py",
                display_name="远程B",
                enabled=False,
                sort_order=1,
                last_error="下载失败",
                config_text="token=remote\ncookie=1\n",
            ),
        ]
        self.logs = {
            2: [SpiderPluginLogEntry(id=1, plugin_id=2, level="error", message="下载失败", created_at=1713206400)]
        }
        self.rename_calls: list[tuple[int, str]] = []
        self.config_calls: list[tuple[int, str]] = []
        self.toggle_calls: list[tuple[int, bool]] = []
        self.move_calls: list[tuple[int, int]] = []
        self.refresh_calls: list[int] = []
        self.add_local_calls: list[str] = []
        self.add_remote_calls: list[str] = []
        self.github_import_calls: list[str] = []
        self.delete_calls: list[int] = []
        self.action_calls: list[tuple[int, str, object]] = []
        self.progress_events: list[tuple[str, int, int, str]] = []
        self.action_query_calls: list[int] = []
        self.github_import_result = SpiderPluginImportResult(imported_count=2, updated_count=1, skipped_count=3)
        self.actions = {
            1: [SpiderPluginAction(id="qr_login", label="扫码登录")],
            2: [
                SpiderPluginAction(
                    id="refresh_cookie",
                    label="刷新 Cookie",
                    enabled=False,
                    tooltip="需要先扫码登录",
                )
            ],
        }

    def list_plugins(self):
        return list(self.plugins)

    def add_local_plugin(self, path: str) -> None:
        self.add_local_calls.append(path)

    def add_remote_plugin(self, url: str) -> None:
        self.add_remote_calls.append(url)

    def import_github_repository(self, repo_url: str, *, progress_callback=None):
        self.github_import_calls.append(repo_url)
        if progress_callback is not None:
            for event in (
                SpiderPluginImportProgress(stage="resolve_repo", message="正在解析仓库信息"),
                SpiderPluginImportProgress(stage="fetch_manifest", message="正在读取 spiders_v2.json"),
                SpiderPluginImportProgress(stage="import_plugin", current=1, total=2, message="正在导入 py/a.txt"),
                SpiderPluginImportProgress(stage="import_plugin", current=2, total=2, message="正在导入 py/b.txt"),
            ):
                self.progress_events.append((event.stage, event.current, event.total, event.message))
                progress_callback(event)
        return self.github_import_result

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        self.rename_calls.append((plugin_id, display_name))

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        self.config_calls.append((plugin_id, config_text))

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        self.toggle_calls.append((plugin_id, enabled))

    def move_plugin(self, plugin_id: int, direction: int) -> None:
        self.move_calls.append((plugin_id, direction))

    def refresh_plugin(self, plugin_id: int) -> None:
        self.refresh_calls.append(plugin_id)

    def delete_plugin(self, plugin_id: int) -> None:
        self.delete_calls.append(plugin_id)

    def list_logs(self, plugin_id: int):
        return self.logs.get(plugin_id, [])

    def list_plugin_actions(self, plugin_id: int):
        self.action_query_calls.append(plugin_id)
        return list(self.actions.get(plugin_id, []))

    def run_plugin_action(self, plugin_id: int, action_id: str, parent=None) -> None:
        self.action_calls.append((plugin_id, action_id, parent))


def test_plugin_manager_dialog_renders_rows_and_status(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.plugin_table.rowCount() == 2
    assert dialog.plugin_table.item(0, 0).text() == "本地A"
    assert dialog.plugin_table.item(0, 1).text() == "本地"
    assert dialog.plugin_table.item(1, 1).text() == "远程"
    assert dialog.plugin_table.item(1, 4).text() == "下载失败"


def test_plugin_manager_dialog_stretches_source_column_to_fill_width(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.resize(1200, 520)
    dialog.show()
    qtbot.wait(50)

    header = dialog.plugin_table.horizontalHeader()

    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Fixed
    assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Fixed
    assert header.sectionResizeMode(4) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(5) == QHeaderView.ResizeMode.Fixed
    assert dialog.plugin_table.columnWidth(1) >= 60
    assert dialog.plugin_table.columnWidth(3) >= 50
    assert dialog.plugin_table.columnWidth(4) >= 120
    assert dialog.plugin_table.columnWidth(5) >= 150
    assert dialog.plugin_table.viewport().width() >= 900


def test_plugin_manager_dialog_uses_read_only_row_selection_for_actionable_table(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.plugin_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert dialog.plugin_table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows


def test_plugin_manager_dialog_disables_row_actions_without_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.clearSelection()

    assert dialog.rename_button.isEnabled() is False
    assert dialog.config_button.isEnabled() is False
    assert dialog.toggle_button.isEnabled() is False
    assert dialog.up_button.isEnabled() is False
    assert dialog.down_button.isEnabled() is False
    assert dialog.refresh_button.isEnabled() is False
    assert dialog.logs_button.isEnabled() is False
    assert dialog.delete_button.isEnabled() is False


def test_plugin_manager_dialog_shows_empty_custom_action_state_without_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.clearSelection()
    dialog._sync_action_state()

    assert [button.text() for button in dialog.plugin_action_buttons] == ["无动作"]
    assert isinstance(dialog.plugin_action_buttons[0], QLabel)
    assert dialog.plugin_action_buttons[0].testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True


def test_plugin_manager_dialog_shows_disabled_no_action_button_when_plugin_has_no_custom_actions(qtbot) -> None:
    manager = FakePluginManager()
    manager.actions[1] = []
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)
    qtbot.wait(100)

    assert [button.text() for button in dialog.plugin_action_buttons] == ["无动作"]
    assert isinstance(dialog.plugin_action_buttons[0], QLabel)
    assert dialog.plugin_action_buttons[0].testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True


def test_plugin_manager_dialog_does_not_accumulate_placeholder_action_widgets_across_refreshes(qtbot) -> None:
    manager = FakePluginManager()
    manager.actions[1] = []
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(0)
    for _ in range(3):
        dialog._sync_action_state()
        qtbot.wait(100)

    placeholders = [widget for widget in dialog.plugin_actions_widget.findChildren(QLabel) if widget.text() == "无动作"]

    assert len(placeholders) == 1
    assert len(dialog.plugin_action_buttons) == 1
    assert dialog.plugin_action_buttons[0].text() == "无动作"


def test_plugin_manager_dialog_disables_move_buttons_at_table_edges(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(0)
    dialog._sync_action_state()
    assert dialog.up_button.isEnabled() is False
    assert dialog.down_button.isEnabled() is True

    dialog.plugin_table.selectRow(1)
    dialog._sync_action_state()
    assert dialog.up_button.isEnabled() is True
    assert dialog.down_button.isEnabled() is False


def test_plugin_manager_dialog_renders_dynamic_plugin_action_buttons(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(1)
    qtbot.wait(100)

    assert [button.text() for button in dialog.plugin_action_buttons] == ["刷新 Cookie"]
    assert dialog.plugin_action_buttons[0].isEnabled() is False
    assert dialog.plugin_action_buttons[0].toolTip() == "需要先扫码登录"
    assert dialog.plugin_action_buttons[0].autoDefault() is False
    assert dialog.plugin_action_buttons[0].isDefault() is False


def test_plugin_manager_dialog_actions_call_manager(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(1)

    monkeypatch.setattr(dialog, "_prompt_display_name", lambda current: "远程重命名")
    monkeypatch.setattr(dialog, "_pick_local_plugin_path", lambda: "/plugins/红果短剧.py")
    monkeypatch.setattr(dialog, "_prompt_remote_url", lambda: "https://example.com/红果短剧.py")
    dialog._add_local_plugin()
    dialog._add_remote_plugin()
    dialog._rename_selected()
    dialog._toggle_selected_enabled()
    dialog._move_selected(-1)
    dialog._refresh_selected()
    dialog._delete_selected()

    assert manager.add_local_calls == ["/plugins/红果短剧.py"]
    assert manager.add_remote_calls == ["https://example.com/红果短剧.py"]
    assert manager.rename_calls == [(2, "远程重命名")]
    assert manager.toggle_calls == [(2, True)]
    assert manager.move_calls == [(2, -1)]
    assert manager.refresh_calls == [2]
    assert manager.delete_calls == [2]


def test_plugin_manager_dialog_imports_github_repository_with_progress_and_summary(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    progress_updates: list[tuple[int, int, str]] = []
    summary_messages: list[str] = []

    class FakeProgressDialog:
        def __init__(self, *args, **kwargs) -> None:
            self.values: list[int] = []
            self.maximums: list[int] = []
            self.labels: list[str] = []

        def setWindowTitle(self, title: str) -> None:
            pass

        def setMinimumDuration(self, duration: int) -> None:
            pass

        def setAutoClose(self, auto_close: bool) -> None:
            pass

        def setAutoReset(self, auto_reset: bool) -> None:
            pass

        def setRange(self, minimum: int, maximum: int) -> None:
            self.maximums.append(maximum)

        def setValue(self, value: int) -> None:
            self.values.append(value)

        def setLabelText(self, text: str) -> None:
            self.labels.append(text)
            progress_updates.append((self.values[-1] if self.values else 0, self.maximums[-1] if self.maximums else 0, text))

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QProgressDialog", FakeProgressDialog)
    monkeypatch.setattr(dialog, "_prompt_github_repo_url", lambda: "https://github.com/har01d5/tvbox")
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QMessageBox.information", lambda *args: summary_messages.append(args[2]))
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QApplication.processEvents", lambda *args, **kwargs: None)

    dialog._import_github_repository()

    assert manager.github_import_calls == ["https://github.com/har01d5/tvbox"]
    assert progress_updates[-1] == (2, 2, "正在导入 py/b.txt")
    assert summary_messages == ["导入完成：新增 2 个，更新 1 个，跳过 3 个。"]


def test_plugin_manager_dialog_dispatches_plugin_action_and_reloads_plugins(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)
    qtbot.wait(100)

    reload_calls: list[str] = []
    original_reload = dialog.reload_plugins

    def tracked_reload() -> None:
        reload_calls.append("reload")
        original_reload()

    monkeypatch.setattr(dialog, "reload_plugins", tracked_reload)

    qtbot.mouseClick(dialog.plugin_action_buttons[0], Qt.MouseButton.LeftButton)

    assert manager.action_calls == [(1, "qr_login", dialog)]
    assert reload_calls == ["reload"]


def test_plugin_manager_dialog_debounces_action_loading_to_final_selected_plugin(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(0)
    dialog.plugin_table.selectRow(1)
    dialog.plugin_table.selectRow(0)
    qtbot.wait(100)

    assert manager.action_query_calls == [1]
    assert [button.text() for button in dialog.plugin_action_buttons] == ["扫码登录"]


def test_plugin_manager_dialog_caches_loaded_actions_per_plugin_during_session(qtbot) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.selectRow(0)
    qtbot.wait(100)
    dialog.plugin_table.selectRow(1)
    qtbot.wait(100)
    dialog.plugin_table.selectRow(0)
    qtbot.wait(100)

    assert manager.action_query_calls == [1, 2]


def test_plugin_manager_dialog_edit_config_allows_empty_string_and_keeps_raw_current_value(
    qtbot,
    monkeypatch,
) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(1)

    captured: list[str] = []

    def fake_prompt(current: str) -> str | None:
        captured.append(current)
        return ""

    monkeypatch.setattr(dialog, "_prompt_config_text", fake_prompt)

    dialog._edit_selected_config()

    assert captured == ["token=remote\ncookie=1\n"]
    assert manager.config_calls == [(2, "")]


def test_plugin_manager_dialog_keeps_selection_on_moved_plugin(qtbot) -> None:
    class ReorderingPluginManager(FakePluginManager):
        def move_plugin(self, plugin_id: int, direction: int) -> None:
            super().move_plugin(plugin_id, direction)
            index = next(i for i, plugin in enumerate(self.plugins) if plugin.id == plugin_id)
            target = index + direction
            if not (0 <= target < len(self.plugins)):
                return
            self.plugins[index], self.plugins[target] = self.plugins[target], self.plugins[index]

    manager = ReorderingPluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)

    dialog._move_selected(1)

    assert dialog.plugin_table.currentRow() == 1
    assert dialog._selected_plugin_id() == 1
