from PySide6.QtWidgets import QApplication

from atv_player.ui.theme import ThemeManager, install_theme


def test_theme_manager_resolves_system_mode_to_dark_when_style_hints_report_dark() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")

    assert manager.resolve_mode("system") == "dark"


def test_theme_manager_falls_back_to_light_when_system_theme_unknown() -> None:
    manager = ThemeManager(system_theme_getter=lambda: None)

    assert manager.resolve_mode("system") == "light"


def test_theme_manager_player_tokens_remain_dark_in_light_app_theme() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")

    app_tokens = manager.tokens_for("light")
    player_tokens = manager.player_tokens_for("light")

    assert app_tokens.window_bg != player_tokens.player_overlay_bg
    assert player_tokens.player_text_on_dark.startswith("#")


def test_install_theme_sets_resolved_theme_property() -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "dark")

    resolved = install_theme(app, manager, "system")

    assert resolved == "dark"
    assert app.property("resolved_theme") == "dark"
    assert app.property("theme_mode") == "system"
