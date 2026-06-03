from PySide6.QtWidgets import QStackedWidget

from atv_player.models import AppConfig
from atv_player.ui.main_window import MainWindow

from tests.test_main_window_ui import (
    FakeStaticController,
    DummyHistoryController,
    FakePlayerController,
)


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

    # Media mode is not implemented yet — it falls back to browse gracefully
    assert window._home_stack is not None
    assert window._home_stack.currentWidget() is window.nav_tabs
