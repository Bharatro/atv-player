from PySide6.QtWidgets import QSizePolicy, QStackedWidget

from atv_player.models import AppConfig, DoubanCategory
from atv_player.ui.main_window import MainWindow

from tests.test_main_window_ui import (
    FakeStaticController,
    DummyHistoryController,
    FakePlayerController,
    FakePluginManager,
)


class ClassicCategoryController:
    def __init__(self) -> None:
        self.item_calls: list[tuple[str, int]] = []

    def load_categories(self):
        return [
            DoubanCategory(type_id="movie", type_name="电影"),
            DoubanCategory(type_id="tv", type_name="电视剧"),
        ]

    def load_items(self, category_id: str, page: int, filters=None):
        del filters
        self.item_calls.append((category_id, page))
        return [], 0


def test_main_window_apply_home_mode_browse_shows_nav_tabs(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    window.apply_home_mode("browse")

    assert hasattr(window, "_home_stack")
    assert isinstance(window._home_stack, QStackedWidget)
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()


def test_main_window_default_home_mode_is_browse(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    assert hasattr(window, "_home_stack")
    assert window._home_stack.currentWidget() is window.nav_tabs


def test_main_window_applies_home_mode_after_config_change(qtbot) -> None:
    config = AppConfig()
    config.home_mode = "browse"
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    # Simulate what happens after advanced settings closes with a mode change
    config.home_mode = "media"
    window.apply_home_mode("media")

    # Media mode shows a placeholder page (not nav_tabs)
    assert window._home_stack is not None
    assert hasattr(window, "_home_mode_placeholder")
    assert window._home_stack.currentWidget() is window._home_mode_placeholder
    assert window.nav_tabs.isHidden()
    # Switching back to browse restores nav_tabs
    window.apply_home_mode("browse")
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert not hasattr(window, "_classic_home_page") or window.header_layout.indexOf(
        window._classic_home_page.source_button
    ) < 0


def test_main_window_switching_from_classic_to_browse_starts_deferred_plugin_load(qtbot) -> None:
    config = AppConfig(home_mode="classic")
    load_calls = []

    def plugin_loader_task():
        load_calls.append("load")
        yield {
            "id": "plugin-1",
            "title": "插件一",
            "controller": FakeStaticController(),
            "search_enabled": True,
            "sort_order": 0,
        }

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)

    assert load_calls == []
    assert window._startup_plugin_load_state == "idle"

    window.apply_home_mode("browse")
    qtbot.waitUntil(lambda: window._startup_plugin_load_state == "idle")

    assert load_calls == ["load"]
    assert any(definition.key == "plugin:plugin-1" for definition in window._plugin_tab_definitions)


def test_main_window_apply_home_mode_classic_shows_classic_page(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    # Inject a fake plugin tab definition so _build_plugin_source_entries finds one
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    assert hasattr(window, "_classic_home_page")
    assert window._home_stack.currentWidget() is window._classic_home_page
    assert window.nav_tabs.isHidden()
    assert (
        window.header_layout.indexOf(window._classic_home_page.source_button)
        < window.header_layout.indexOf(window.global_search_container)
    )
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0


def test_main_window_classic_keeps_global_search_centered(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    search_index = window.header_layout.indexOf(window.global_search_container)
    leading_spacer = window.header_layout.itemAt(search_index - 1).spacerItem()
    center_spacer = window.header_layout.itemAt(search_index + 1).spacerItem()
    assert leading_spacer is not None
    assert center_spacer is not None
    assert leading_spacer.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert center_spacer.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_main_window_classic_source_picker_includes_builtin_and_plugin_sources(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "douban" in keys
    assert "telegram" in keys
    assert "live" in keys
    assert "browse" in keys
    assert "favorites" in keys
    assert "following" in keys
    assert "history" in keys
    assert "plugin:1" in keys


def test_main_window_classic_selecting_builtin_non_grid_source_opens_builtin_page(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("favorites").click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.nav_row_widget.isHidden()
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0
    assert window.nav_tabs.currentWidget() is window.favorites_page
    assert config.last_selected_tab == "favorites"


def test_main_window_classic_header_builtin_shortcut_opens_builtin_page(qtbot) -> None:
    config = AppConfig()
    save_calls = []
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        save_config=lambda: save_calls.append(config.last_selected_tab),
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window.following_button.click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.nav_row_widget.isHidden()
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0
    assert window.nav_tabs.currentWidget() is window.following_page
    assert window._classic_home_page.current_source_key() == "following"
    assert window._classic_home_page.source_button.text() == "我的追更"
    assert window._classic_home_page.source_popup.source_button("following").isChecked()
    assert config.last_selected_tab == "following"
    assert save_calls[-1] == "following"


def test_main_window_classic_source_picker_uses_builtin_source_overrides(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig(
        builtin_tab_overrides_json=(
            '{"order":["telegram","douban"],"hidden":["douban"],"renames":{"telegram":"纸飞机"}}'
        )
    )
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    buttons = window._classic_home_page.source_popup.source_buttons
    keys = list(buttons)
    assert "douban" not in keys
    assert keys[0] == "telegram"
    assert keys.index("plugin:1") > keys.index("telegram")
    assert buttons["telegram"].text() == "纸飞机"


def test_main_window_classic_source_picker_refreshes_after_builtin_overrides_saved(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")
    window._handle_builtin_tab_overrides_saved(
        '{"order":["telegram","douban"],"hidden":["douban"],"renames":{"telegram":"纸飞机"}}'
    )

    buttons = window._classic_home_page.source_popup.source_buttons
    assert "douban" not in buttons
    assert list(buttons)[0] == "telegram"
    assert buttons["telegram"].text() == "纸飞机"


def test_main_window_classic_source_picker_refreshes_when_plugins_load_later(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]
    window._refresh_classic_source_entries_if_active()

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "plugin:1" in keys


def test_main_window_classic_source_picker_lists_enabled_plugins_without_loading(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "plugin:1" in keys
    assert "plugin:2" in keys
    assert manager.load_plugins_calls == []


def test_main_window_classic_source_picker_loads_selected_plugin_on_demand(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("plugin:2").click()

    assert manager.load_plugins_calls == [["2"]]
    assert window._classic_home_page.current_source_key() == "plugin:2"


def test_main_window_classic_source_picker_persists_selected_source(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    save_calls = []
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
        save_config=lambda: save_calls.append(config.last_selected_tab),
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("plugin:2").click()

    assert config.last_selected_tab == "plugin:2"
    assert save_calls[-1] == "plugin:2"


def test_main_window_classic_restores_last_selected_source(qtbot) -> None:
    config = AppConfig()
    config.home_mode = "classic"
    config.last_selected_tab = "plugin:2"
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    assert window._classic_home_page.current_source_title() == "插件2"
    assert window._classic_home_page.current_source_key() == "plugin:2"


def test_main_window_classic_restores_last_selected_category_tab(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition
    from atv_player.ui.poster_grid_page import PosterGridPage

    config = AppConfig(
        home_mode="classic",
        last_selected_tab="plugin:1",
        last_selected_category_tab="plugin:1",
        last_selected_category_id="tv",
    )
    controller = ClassicCategoryController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", PosterGridPage(controller), controller),
    ]
    config.last_selected_tab = "plugin:1"

    window.apply_home_mode("classic")

    assert window._classic_home_page.current_source_key() == "plugin:1"
    assert window._classic_home_page.current_category_id() == "tv"
    assert controller.item_calls == [("tv", 1)]


def test_main_window_classic_persists_selected_category_tab(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition
    from atv_player.ui.poster_grid_page import PosterGridPage

    config = AppConfig(home_mode="classic", last_selected_tab="plugin:1")
    save_calls = []
    controller = ClassicCategoryController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        save_config=lambda: save_calls.append((config.last_selected_category_tab, config.last_selected_category_id)),
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", PosterGridPage(controller), controller),
    ]
    config.last_selected_tab = "plugin:1"
    window.apply_home_mode("classic")

    window._classic_home_page.category_tab_bar.setCurrentIndex(1)

    assert config.last_selected_category_tab == "plugin:1"
    assert config.last_selected_category_id == "tv"
    assert ("plugin:1", "tv") in save_calls


def test_main_window_classic_source_picker_has_limited_width(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    assert window._classic_home_page.source_button.maximumWidth() <= 180
