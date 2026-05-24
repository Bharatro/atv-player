from PySide6.QtWidgets import QApplication, QTabBar, QVBoxLayout, QWidget

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


def test_theme_tokens_expose_button_disabled_colors() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    assert tokens.button_disabled_bg.startswith("#")
    assert tokens.button_disabled_border.startswith("#")
    assert tokens.button_disabled_text.startswith("#")


def test_build_combobox_qss_uses_brand_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_combobox_qss(tokens)

    assert tokens.accent in qss
    assert "QComboBox::drop-down" in qss
    assert "QAbstractItemView" in qss
    assert "QComboBox:disabled" in qss
    assert "QComboBox:disabled::drop-down" in qss


def test_build_combobox_qss_uses_fill_first_default_state() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_combobox_qss(tokens)

    assert "QComboBox {" in qss
    assert "height: 34px;" in qss
    assert "min-height: 34px;" in qss
    assert "max-height: 34px;" in qss
    assert "padding: 0 40px 0 12px;" in qss
    assert "border: none;" in qss
    assert f"background: {tokens.input_bg};" in qss
    assert f"border: 1px solid {tokens.input_hover_border};" in qss
    assert f"border: 1px solid {tokens.input_focus_ring};" in qss
    assert "border-left: 1px solid transparent;" in qss
    assert "QComboBox:disabled" in qss
    assert "QComboBox:disabled::drop-down" in qss


def test_build_application_stylesheet_uses_borderless_default_comboboxes() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    qss = manager.build_application_stylesheet("light")

    assert "QComboBox {\n            background-color:" in qss
    assert "border: none;" in qss
    assert "QLineEdit:disabled" in qss
    assert "QPlainTextEdit:disabled" in qss


def test_build_application_stylesheet_uses_dedicated_disabled_button_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = manager.build_application_stylesheet("dark")

    assert "QPushButton:disabled" in qss
    assert f"background-color: {tokens.button_disabled_bg};" in qss
    assert f"border: 1px solid {tokens.button_disabled_border};" in qss
    assert f"color: {tokens.button_disabled_text};" in qss


def test_build_application_stylesheet_styles_tooltips_with_subtle_panel_border() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = manager.build_application_stylesheet("dark")

    assert "QToolTip {" in qss
    assert f"background-color: {tokens.panel_bg};" in qss
    assert f"color: {tokens.text_primary};" in qss
    assert f"border: 1px solid {tokens.border_subtle};" in qss
    assert "border-radius: 10px;" in qss


def test_flat_combobox_avoids_native_top_border_line_when_background_is_transparent() -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "light")
    theme = install_theme(app, manager, "light")
    tokens = manager.tokens_for(theme)

    root = QWidget()
    root.setStyleSheet(f"background: {tokens.panel_bg};")
    layout = QVBoxLayout(root)
    combo = theme_module.FlatComboBox()
    combo.addItems(["备用线", "极速线"])
    combo.setStyleSheet(
        theme_module.build_combobox_qss(
            tokens,
            field_bg="transparent",
            drop_down_bg="transparent",
            disabled_field_bg="transparent",
            disabled_drop_down_bg="transparent",
        )
    )
    layout.addWidget(combo)
    root.resize(360, 120)
    root.show()
    app.processEvents()

    image = root.grab().toImage()
    top_center = combo.geometry().center().x(), combo.geometry().top() + 3
    assert image.pixelColor(*top_center).name() == tokens.panel_bg


def test_build_combobox_qss_accepts_surface_overrides() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_combobox_qss(
        tokens,
        min_height=30,
        field_bg="#202734",
        drop_down_bg="#202734",
        text_color="#f5f7fb",
        disabled_field_bg="#212734",
        disabled_drop_down_bg="#212734",
        disabled_text_color="#b0b8c7",
    )

    assert "min-height: 30px" in qss
    assert "background: #202734;" in qss
    assert "color: #f5f7fb;" in qss
    assert "background: #212734;" in qss
    assert "color: #b0b8c7;" in qss


def test_button_helpers_emit_disabled_rules_without_opacity() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    round_qss = theme_module.build_round_icon_button_qss(tokens)
    pill_qss = theme_module.build_pill_button_qss(tokens, checked_accent=True)

    for qss in (round_qss, pill_qss):
        assert "QPushButton:disabled" in qss
        assert tokens.button_disabled_bg in qss
        assert tokens.button_disabled_border in qss
        assert tokens.button_disabled_text in qss
        assert "opacity" not in qss


def test_build_round_icon_button_qss_accepts_surface_overrides() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_round_icon_button_qss(
        tokens,
        background=tokens.button_bg,
        border_color=tokens.input_hover_border,
        text_color=tokens.text_primary,
        hover_background=tokens.panel_alt_bg,
        hover_border_color=tokens.accent_hover,
    )

    assert f"background: {tokens.button_bg};" in qss
    assert f"border: 1px solid {tokens.input_hover_border};" in qss
    assert f"color: {tokens.text_primary};" in qss
    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"border-color: {tokens.accent_hover};" in qss
    assert "QPushButton:disabled" in qss


def test_build_navigation_tabbar_qss_uses_explicit_dark_theme_text_colors() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_navigation_tabbar_qss(tokens)

    assert f"color: {tokens.text_primary};" in qss
    assert f"color: {tokens.accent};" in qss
    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"border-color: {tokens.input_hover_border};" in qss
    assert "padding: 8px 8px;" in qss
    assert "margin-right: 2px;" in qss


def test_build_player_tabbar_qss_uses_default_player_tab_spacing() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_player_tabbar_qss(tokens)

    assert "font-size: 13px;" in qss
    assert "padding: 8px 14px;" in qss
    assert "border-radius: 12px;" in qss
    assert "margin-right: 6px;" in qss


def test_build_compact_player_tabbar_qss_uses_smaller_chrome() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_compact_player_tabbar_qss(tokens)

    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"color: {tokens.text_secondary};" in qss
    assert "font-size: 11px;" in qss
    assert "padding: 4px 8px;" in qss
    assert "border-radius: 8px;" in qss
    assert "margin-right: 2px;" in qss
    assert f"border-color: {tokens.accent};" in qss


def test_build_compact_player_tabbar_qss_shrinks_actual_tabbar_size_hint() -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    default_bar = QTabBar()
    default_bar.addTab("剧集标题")
    default_bar.addTab("原始文件名")
    default_bar.setStyleSheet(theme_module.build_player_tabbar_qss(tokens))
    default_bar.ensurePolished()
    default_bar.adjustSize()

    compact_bar = QTabBar()
    compact_bar.addTab("剧集标题")
    compact_bar.addTab("原始文件名")
    compact_bar.setStyleSheet(theme_module.build_compact_player_tabbar_qss(tokens))
    compact_bar.ensurePolished()
    compact_bar.adjustSize()

    app.processEvents()

    default_hint = default_bar.sizeHint()
    compact_hint = compact_bar.sizeHint()

    assert default_hint.height() == 35
    assert compact_hint.height() <= 25
    assert compact_hint.width() <= 140
    assert compact_hint.height() <= default_hint.height() - 10
    assert compact_hint.width() <= default_hint.width() - 40


def test_build_form_line_edit_qss_uses_disabled_surface_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_form_line_edit_qss(tokens)

    assert f"border: 1px solid {tokens.input_border};" in qss
    assert f"background: {tokens.input_bg};" in qss
    assert "QLineEdit:disabled" in qss
    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"color: {tokens.text_secondary};" in qss
    assert f"border: 1px solid {tokens.border_subtle};" in qss


def test_build_form_spinbox_qss_uses_disabled_surface_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_form_spinbox_qss(tokens)

    assert "QSpinBox," in qss
    assert "QDoubleSpinBox {" in qss
    assert f"border: 1px solid {tokens.input_border};" in qss
    assert f"background-color: {tokens.input_bg};" in qss
    assert "QSpinBox:disabled," in qss
    assert f"background-color: {tokens.panel_alt_bg};" in qss
    assert f"color: {tokens.text_secondary};" in qss
    assert f"border-color: {tokens.border_subtle};" in qss


def test_build_slider_qss_uses_brand_fill_and_hover_handle() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.player_tokens_for("dark")

    qss = theme_module.build_slider_qss(tokens, groove_height=8, handle_diameter=18)

    assert tokens.accent in qss
    assert "QSlider {\n        background: transparent;\n        border: none;" in qss
    assert "QSlider::sub-page:horizontal" in qss
    assert "QSlider::groove:horizontal" in qss
    assert "QSlider::add-page:horizontal" in qss
    assert "QSlider::handle:horizontal:hover" in qss
    assert "QSlider::groove:horizontal {\n        height: 8px;\n        border: none;\n        border-radius: 4px;\n        background: transparent;" in qss
    assert "QSlider::add-page:horizontal {\n        height: 8px;\n        border: none;\n        border-radius: 4px;\n        background: transparent;" in qss
    assert f"background: {tokens.accent};" in qss
    assert f"background: {tokens.player_text_on_dark};" in qss
    assert "border: none;" in qss


def test_build_player_list_qss_uses_brand_state_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_player_list_qss(tokens)

    assert tokens.accent in qss
    assert "QListWidget::item:selected" in qss
    assert "QScrollBar:vertical" in qss
    assert "min-height: 24px" in qss
    assert "padding: 4px 8px" in qss


def test_build_player_text_panel_qss_uses_brand_panel_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_player_text_panel_qss(tokens)

    assert tokens.panel_alt_bg in qss
    assert "padding: 12px 14px" in qss
    assert "selection-background-color" in qss


def test_build_player_spinbox_qss_draws_full_height_step_buttons() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.player_tokens_for("dark")

    qss = theme_module.build_player_spinbox_qss(tokens)

    assert f"border: 1px solid {tokens.player_button_border};" in qss
    assert "QSpinBox::up-button" in qss
    assert "QSpinBox::down-button" in qss
    assert "height: 13px;" in qss
    assert f"background: {tokens.player_button_hover_bg};" in qss
    assert f"border-left: 1px solid {tokens.player_button_border};" in qss
    assert "spinbox-step-up.svg" in qss
    assert "spinbox-step-down.svg" in qss
