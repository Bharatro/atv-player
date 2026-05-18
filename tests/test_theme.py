from PySide6.QtWidgets import QApplication

import atv_player.ui.theme as theme_module
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


def test_build_combobox_qss_uses_brand_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_combobox_qss(tokens)

    assert tokens.accent in qss
    assert "QComboBox::drop-down" in qss
    assert "QAbstractItemView" in qss


def test_build_slider_qss_uses_brand_fill_and_hover_handle() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.player_tokens_for("dark")

    qss = theme_module.build_slider_qss(tokens, groove_height=8, handle_diameter=18)

    assert tokens.accent in qss
    assert "QSlider::sub-page:horizontal" in qss
    assert "QSlider::handle:horizontal:hover" in qss


def test_build_player_list_qss_uses_brand_state_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_player_list_qss(tokens)

    assert tokens.accent in qss
    assert "QListWidget::item:selected" in qss
    assert "QScrollBar:vertical" in qss
    assert "min-height: 28px" in qss
    assert "padding: 6px 10px" in qss


def test_build_player_text_panel_qss_uses_brand_panel_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_player_text_panel_qss(tokens)

    assert tokens.panel_alt_bg in qss
    assert "padding: 12px 14px" in qss
    assert "selection-background-color" in qss
