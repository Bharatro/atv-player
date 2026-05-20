from atv_player.models import DoubanCategory, SpiderPluginConfig
from atv_player.ui.plugin_category_manager_dialog import PluginCategoryManagerDialog


class FakePluginManager:
    def __init__(self) -> None:
        self.plugin = SpiderPluginConfig(
            id=7,
            source_type="local",
            source_value="/plugins/demo.py",
            display_name="演示插件",
            enabled=True,
            category_overrides_json='{"order":["tv","movie"],"hidden":["adult"],"renames":{"movie":"影片"}}',
        )
        self.saved_overrides: list[tuple[int, str]] = []

    def list_plugins(self):
        return [self.plugin]

    def load_plugin_categories(self, plugin_id: int):
        assert plugin_id == 7
        return [
            DoubanCategory(type_id="movie", type_name="电影"),
            DoubanCategory(type_id="tv", type_name="剧集"),
            DoubanCategory(type_id="adult", type_name="成人视频"),
        ]

    def set_plugin_category_overrides(self, plugin_id: int, category_overrides_json: str) -> None:
        self.saved_overrides.append((plugin_id, category_overrides_json))
        self.plugin.category_overrides_json = category_overrides_json


def _row_texts(dialog: PluginCategoryManagerDialog) -> list[str]:
    return [dialog.category_list.item(index).text() for index in range(dialog.category_list.count())]


def test_plugin_category_manager_dialog_uses_override_order_and_hidden_marker(qtbot) -> None:
    dialog = PluginCategoryManagerDialog(FakePluginManager(), plugin_id=7)
    qtbot.addWidget(dialog)

    assert _row_texts(dialog) == ["剧集", "影片", "成人视频（已隐藏）"]


def test_plugin_category_manager_dialog_restore_defaults_resets_draft(qtbot) -> None:
    dialog = PluginCategoryManagerDialog(FakePluginManager(), plugin_id=7)
    qtbot.addWidget(dialog)
    dialog._move_to_bottom()
    dialog._toggle_hidden()

    dialog._restore_defaults()

    assert _row_texts(dialog) == ["电影", "剧集", "成人视频"]


def test_plugin_category_manager_dialog_save_persists_compact_override_json(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginCategoryManagerDialog(manager, plugin_id=7)
    qtbot.addWidget(dialog)
    dialog.category_list.setCurrentRow(0)
    monkeypatch.setattr(dialog, "_prompt_display_name", lambda current: "长剧")
    dialog._rename_selected()
    dialog._move_to_bottom()

    dialog._save()

    assert manager.saved_overrides == [
        (7, '{"order":["movie","adult","tv"],"hidden":["adult"],"renames":{"movie":"影片","tv":"长剧"}}')
    ]
    assert dialog.result() == dialog.DialogCode.Accepted
