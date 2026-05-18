from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPolygon
from PySide6.QtWidgets import QApplication, QComboBox

ThemeMode = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]
_ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"


class FlatComboBox(QComboBox):
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        left_padding = int(self.property("flat_combo_left_padding") or 12)
        indicator_padding = int(self.property("flat_combo_indicator_padding") or 40)
        drop_down_width = int(self.property("flat_combo_drop_down_width") or 30)
        border_radius = int(self.property("flat_combo_border_radius") or 14)

        if self.isEnabled():
            background = self._resolved_color("flat_combo_field_bg", QColor(0, 0, 0, 0))
            border = self._resolved_color("flat_combo_border_color", QColor(0, 0, 0, 0))
            if self.underMouse():
                background = self._resolved_color("flat_combo_hover_field_bg", background)
                border = self._resolved_color("flat_combo_hover_border_color", border)
            if self.hasFocus():
                border = self._resolved_color("flat_combo_focus_border_color", border)
        else:
            background = self._resolved_color("flat_combo_disabled_field_bg", QColor(0, 0, 0, 0))
            border = self._resolved_color("flat_combo_disabled_border_color", QColor(0, 0, 0, 0))

        rect = self.rect().adjusted(0, 0, -1, -1)
        if background.alpha() > 0 or border.alpha() > 0:
            painter.setBrush(background if background.alpha() > 0 else Qt.BrushStyle.NoBrush)
            painter.setPen(border if border.alpha() > 0 else Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, border_radius, border_radius)

        text = self.currentText() if self.currentIndex() >= 0 else self.placeholderText()
        text_color_name = "flat_combo_text_color" if self.isEnabled() else "flat_combo_disabled_text_color"
        fallback_role = QPalette.ColorRole.Text if self.isEnabled() else QPalette.ColorRole.Mid
        text_color = self._resolved_color(text_color_name, self.palette().color(fallback_role))
        painter.setPen(text_color)
        text_rect = self.rect().adjusted(left_padding, 0, -indicator_padding, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        arrow_color_name = "flat_combo_arrow_color" if self.isEnabled() else "flat_combo_disabled_arrow_color"
        arrow_color = self._resolved_color(arrow_color_name, text_color)
        painter.setBrush(arrow_color)
        painter.setPen(Qt.PenStyle.NoPen)
        center_x = self.width() - max(8, drop_down_width // 2) - 2
        center_y = self.height() // 2 + 1
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(center_x - 4, center_y - 2),
                    QPoint(center_x + 4, center_y - 2),
                    QPoint(center_x, center_y + 3),
                ]
            )
        )

    def _resolved_color(self, property_name: str, fallback: QColor) -> QColor:
        value = self.property(property_name)
        if isinstance(value, QColor):
            return value
        if isinstance(value, str) and value:
            color = QColor(value)
            if color.isValid():
                return color
        return fallback


def configure_flat_combobox(
    combo: QComboBox,
    *,
    text_color: str | None = None,
    disabled_text_color: str | None = None,
    arrow_color: str | None = None,
    disabled_arrow_color: str | None = None,
    border_color: str | None = None,
    field_bg: str | None = None,
    hover_field_bg: str | None = None,
    disabled_field_bg: str | None = None,
    hover_border_color: str | None = None,
    focus_border_color: str | None = None,
    disabled_border_color: str | None = None,
    border_radius: int = 14,
    left_padding: int = 12,
    indicator_padding: int = 40,
    drop_down_width: int = 30,
) -> None:
    combo.setProperty("flat_combo_border_color", border_color or "")
    combo.setProperty("flat_combo_text_color", text_color or "")
    combo.setProperty("flat_combo_disabled_text_color", disabled_text_color or "")
    combo.setProperty("flat_combo_arrow_color", arrow_color or "")
    combo.setProperty("flat_combo_disabled_arrow_color", disabled_arrow_color or "")
    combo.setProperty("flat_combo_field_bg", field_bg or "")
    combo.setProperty("flat_combo_hover_field_bg", hover_field_bg or "")
    combo.setProperty("flat_combo_disabled_field_bg", disabled_field_bg or "")
    combo.setProperty("flat_combo_hover_border_color", hover_border_color or "")
    combo.setProperty("flat_combo_focus_border_color", focus_border_color or "")
    combo.setProperty("flat_combo_disabled_border_color", disabled_border_color or "")
    combo.setProperty("flat_combo_border_radius", border_radius)
    combo.setProperty("flat_combo_left_padding", left_padding)
    combo.setProperty("flat_combo_indicator_padding", indicator_padding)
    combo.setProperty("flat_combo_drop_down_width", drop_down_width)
    combo.update()


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    window_bg: str
    panel_bg: str
    panel_alt_bg: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    input_bg: str
    input_border: str
    input_hover_border: str
    input_focus_ring: str
    button_bg: str
    button_primary_bg: str
    button_primary_text: str
    menu_bg: str
    menu_hover_bg: str
    menu_selected_bg: str
    player_overlay_bg: str
    player_controls_bg: str
    player_scrim: str
    player_text_on_dark: str
    player_button_bg: str
    player_button_hover_bg: str
    player_button_pressed_bg: str
    player_button_border: str
    player_button_icon: str
    player_primary_button_bg: str
    player_primary_button_hover_bg: str
    player_primary_button_pressed_bg: str
    player_primary_button_icon: str


LIGHT_TOKENS = ThemeTokens(
    window_bg="#f7f2eb",
    panel_bg="#fffdfa",
    panel_alt_bg="#f3ebe1",
    border_subtle="#d8cabc",
    text_primary="#241f1a",
    text_secondary="#6f6254",
    accent="#ff6a3d",
    accent_hover="#e95528",
    input_bg="#ffffff",
    input_border="#d4c5b7",
    input_hover_border="#c3a88d",
    input_focus_ring="#ff6a3d",
    button_bg="#fffaf5",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    menu_bg="#fffdfa",
    menu_hover_bg="#f8ede2",
    menu_selected_bg="#ffe0d5",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
    player_button_bg="#262d3c",
    player_button_hover_bg="#313a4d",
    player_button_pressed_bg="#1d2430",
    player_button_border="#536078",
    player_button_icon="#f5f7fb",
    player_primary_button_bg="#ff6a3d",
    player_primary_button_hover_bg="#ff835b",
    player_primary_button_pressed_bg="#e95528",
    player_primary_button_icon="#ffffff",
)

DARK_TOKENS = ThemeTokens(
    window_bg="#12161e",
    panel_bg="#1a1f2a",
    panel_alt_bg="#222836",
    border_subtle="#343c4d",
    text_primary="#f3f5f8",
    text_secondary="#b0b8c7",
    accent="#ff6a3d",
    accent_hover="#ff8a63",
    input_bg="#0f131b",
    input_border="#394254",
    input_hover_border="#556177",
    input_focus_ring="#ff6a3d",
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    menu_bg="#1a1f2a",
    menu_hover_bg="#262d3b",
    menu_selected_bg="#3a2b28",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
    player_button_bg="#262d3c",
    player_button_hover_bg="#313a4d",
    player_button_pressed_bg="#1d2430",
    player_button_border="#536078",
    player_button_icon="#f5f7fb",
    player_primary_button_bg="#ff6a3d",
    player_primary_button_hover_bg="#ff835b",
    player_primary_button_pressed_bg="#e95528",
    player_primary_button_icon="#ffffff",
)

PLAYER_IMMERSIVE_TOKENS = ThemeTokens(
    window_bg="#12161e",
    panel_bg="#1a1f2a",
    panel_alt_bg="#222836",
    border_subtle="#343c4d",
    text_primary="#f3f5f8",
    text_secondary="#b0b8c7",
    accent="#ff6a3d",
    accent_hover="#ff8a63",
    input_bg="#0f131b",
    input_border="#394254",
    input_hover_border="#556177",
    input_focus_ring="#ff6a3d",
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    menu_bg="#1a1f2a",
    menu_hover_bg="#262d3b",
    menu_selected_bg="#3a2b28",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
    player_button_bg="#262d3c",
    player_button_hover_bg="#313a4d",
    player_button_pressed_bg="#1d2430",
    player_button_border="#536078",
    player_button_icon="#f5f7fb",
    player_primary_button_bg="#ff6a3d",
    player_primary_button_hover_bg="#ff835b",
    player_primary_button_pressed_bg="#e95528",
    player_primary_button_icon="#ffffff",
)


class ThemeManager:
    def __init__(self, system_theme_getter=None) -> None:
        self._system_theme_getter = system_theme_getter or self._default_system_theme

    def resolve_mode(self, mode: str) -> ResolvedTheme:
        normalized = str(mode or "system").strip().lower()
        if normalized == "light":
            return "light"
        if normalized == "dark":
            return "dark"
        system_theme = self._system_theme_getter()
        return "dark" if system_theme == "dark" else "light"

    def tokens_for(self, theme: ResolvedTheme) -> ThemeTokens:
        return DARK_TOKENS if theme == "dark" else LIGHT_TOKENS

    def player_tokens_for(self, _theme: ResolvedTheme) -> ThemeTokens:
        return PLAYER_IMMERSIVE_TOKENS

    def build_palette(self, theme: ResolvedTheme) -> QPalette:
        tokens = self.tokens_for(theme)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens.window_bg))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.input_bg))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.panel_alt_bg))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens.button_bg))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.button_primary_text))
        return palette

    def build_application_stylesheet(self, theme: ResolvedTheme) -> str:
        tokens = self.tokens_for(theme)
        return f"""
        QWidget {{
            color: {tokens.text_primary};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QTableWidget {{
            background-color: {tokens.input_bg};
            border: 1px solid {tokens.input_border};
            border-radius: 12px;
            color: {tokens.text_primary};
        }}
        QComboBox {{
            background-color: {tokens.input_bg};
            border: none;
            border-radius: 12px;
            color: {tokens.text_primary};
        }}
        QComboBox:hover {{
            border: 1px solid {tokens.input_hover_border};
        }}
        QComboBox:focus {{
            border: 1px solid {tokens.input_focus_ring};
        }}
        QPushButton {{
            background-color: {tokens.button_bg};
            border: 1px solid {tokens.border_subtle};
            border-radius: 12px;
            color: {tokens.text_primary};
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            border-color: {tokens.accent_hover};
        }}
        """

    @staticmethod
    def _default_system_theme() -> str | None:
        app = QApplication.instance()
        if app is None:
            return None
        style_hints = getattr(app, "styleHints", lambda: None)()
        color_scheme = getattr(style_hints, "colorScheme", lambda: None)()
        if color_scheme == Qt.ColorScheme.Dark:
            return "dark"
        if color_scheme == Qt.ColorScheme.Light:
            return "light"
        return None


def install_theme(app: QApplication, manager: ThemeManager, mode: str) -> str:
    resolved = manager.resolve_mode(mode)
    if hasattr(app, "setPalette"):
        app.setPalette(manager.build_palette(resolved))
    if hasattr(app, "setStyleSheet"):
        app.setStyleSheet(manager.build_application_stylesheet(resolved))
    if hasattr(app, "setProperty"):
        app.setProperty("resolved_theme", resolved)
        app.setProperty("theme_mode", mode)
    else:
        setattr(app, "resolved_theme", resolved)
        setattr(app, "theme_mode", mode)
    setattr(app, "_theme_manager", manager)
    return resolved


def current_theme_manager() -> ThemeManager:
    app = QApplication.instance()
    manager = getattr(app, "_theme_manager", None) if app is not None else None
    return manager if isinstance(manager, ThemeManager) else ThemeManager()


def current_resolved_theme() -> ResolvedTheme:
    app = QApplication.instance()
    if app is None or not hasattr(app, "property"):
        return "light"
    resolved = str(app.property("resolved_theme") or "light").strip().lower()
    return "dark" if resolved == "dark" else "light"


def current_tokens() -> ThemeTokens:
    return current_theme_manager().tokens_for(current_resolved_theme())


def build_search_line_edit_qss(tokens: ThemeTokens, *, border_radius: int = 15, min_height: int = 30) -> str:
    return f"""
    QLineEdit {{
        min-height: {min_height}px;
        padding: 0 10px;
        border: 1px solid {tokens.input_border};
        border-radius: {border_radius}px;
        background: {tokens.input_bg};
        color: {tokens.text_primary};
    }}
    QLineEdit:focus {{
        border: 1px solid {tokens.accent};
    }}
    """


def build_combobox_qss(
    tokens: ThemeTokens,
    *,
    border_radius: int = 14,
    min_height: int = 34,
    horizontal_padding: int = 12,
    indicator_padding: int = 40,
    drop_down_width: int = 30,
    borderless: bool = False,
    field_bg: str | None = None,
    drop_down_bg: str | None = None,
    text_color: str | None = None,
    hover_field_bg: str | None = None,
    hover_drop_down_bg: str | None = None,
    disabled_field_bg: str | None = None,
    disabled_drop_down_bg: str | None = None,
    disabled_text_color: str | None = None,
    border_color: str | None = None,
    hover_border_color: str | None = None,
    focus_border_color: str | None = None,
    disabled_border_color: str | None = None,
    drop_down_border_left_color: str | None = None,
    disabled_drop_down_border_left_color: str | None = None,
) -> str:
    resolved_field_bg = field_bg or tokens.input_bg
    resolved_drop_down_bg = drop_down_bg or (resolved_field_bg if borderless else tokens.panel_alt_bg)
    resolved_text_color = text_color or tokens.text_primary
    resolved_hover_field_bg = hover_field_bg or resolved_field_bg
    resolved_hover_drop_down_bg = hover_drop_down_bg or resolved_drop_down_bg
    resolved_disabled_field_bg = disabled_field_bg or tokens.panel_alt_bg
    resolved_disabled_drop_down_bg = disabled_drop_down_bg or (
        resolved_disabled_field_bg if borderless else tokens.panel_bg
    )
    resolved_disabled_text_color = disabled_text_color or tokens.text_secondary
    resolved_border_color = border_color or ("transparent" if borderless else "transparent")
    resolved_hover_border_color = hover_border_color or ("transparent" if borderless else tokens.input_hover_border)
    resolved_focus_border_color = focus_border_color or ("transparent" if borderless else tokens.input_focus_ring)
    resolved_disabled_border_color = disabled_border_color or ("transparent" if borderless else "transparent")
    resolved_drop_down_border_left_color = drop_down_border_left_color or "transparent"
    resolved_disabled_drop_down_border_left_color = disabled_drop_down_border_left_color or "transparent"
    return f"""
    QComboBox {{
        min-height: {min_height}px;
        padding: 0 {indicator_padding}px 0 {horizontal_padding}px;
        border: none;
        border-radius: {border_radius}px;
        background: {resolved_field_bg};
        color: {resolved_text_color};
    }}
    QComboBox:hover {{
        background: {resolved_hover_field_bg};
        border: 1px solid {resolved_hover_border_color};
    }}
    QComboBox:hover::drop-down {{
        background: {resolved_hover_drop_down_bg};
    }}
    QComboBox:focus {{
        border: 1px solid {resolved_focus_border_color};
    }}
    QComboBox:disabled {{
        border: 1px solid {resolved_disabled_border_color};
        background: {resolved_disabled_field_bg};
        color: {resolved_disabled_text_color};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: {drop_down_width}px;
        border: none;
        border-left: 1px solid {resolved_drop_down_border_left_color};
        background: {resolved_drop_down_bg};
        border-top-right-radius: {max(0, border_radius - 1)}px;
        border-bottom-right-radius: {max(0, border_radius - 1)}px;
    }}
    QComboBox::down-arrow {{
        width: 0px;
        height: 0px;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {tokens.text_secondary};
    }}
    QComboBox:disabled::drop-down {{
        border-left: 1px solid {resolved_disabled_drop_down_border_left_color};
        background: {resolved_disabled_drop_down_bg};
    }}
    QComboBox:disabled::down-arrow {{
        border-top: 6px solid {tokens.border_subtle};
    }}
    QComboBox QAbstractItemView {{
        background: {tokens.menu_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.input_border};
        selection-background-color: {tokens.menu_selected_bg};
        selection-color: {tokens.text_primary};
        outline: 0;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 28px;
        padding: 4px 10px;
        background: transparent;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {tokens.menu_hover_bg};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {tokens.menu_selected_bg};
    }}
    """


def build_combobox_popup_qss(
    *,
    background: str,
    text_color: str,
    border_color: str,
    hover_bg: str,
    selected_bg: str,
    selected_text_color: str | None = None,
) -> str:
    resolved_selected_text_color = selected_text_color or text_color
    return f"""
    QAbstractItemView {{
        background: {background};
        color: {text_color};
        border: 1px solid {border_color};
        selection-background-color: {selected_bg};
        selection-color: {resolved_selected_text_color};
        outline: 0;
    }}
    QAbstractItemView::item {{
        min-height: 28px;
        padding: 4px 10px;
        background: transparent;
    }}
    QAbstractItemView::item:hover {{
        background: {hover_bg};
    }}
    QAbstractItemView::item:selected {{
        background: {selected_bg};
        color: {resolved_selected_text_color};
    }}
    """


def build_round_icon_button_qss(tokens: ThemeTokens, *, border_radius: int = 18) -> str:
    return f"""
    QPushButton {{
        border: 1px solid {tokens.input_border};
        border-radius: {border_radius}px;
        background: {tokens.input_bg};
        color: {tokens.text_primary};
        padding: 0;
    }}
    QPushButton:hover {{
        background: {tokens.panel_alt_bg};
        border-color: {tokens.accent_hover};
    }}
    """


def build_pill_button_qss(tokens: ThemeTokens, *, checked_accent: bool = False) -> str:
    checked_block = ""
    if checked_accent:
        checked_block = f"""
        QPushButton:checked {{
            background-color: {tokens.input_bg};
            color: {tokens.accent};
            border: 1px solid {tokens.accent};
        }}
        QPushButton:checked:hover {{
            color: {tokens.accent_hover};
            border: 1px solid {tokens.accent_hover};
        }}
        """
    return f"""
    QPushButton {{
        background-color: {tokens.input_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.input_border};
        border-radius: 14px;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        background-color: {tokens.panel_alt_bg};
        border-color: {tokens.accent_hover};
    }}
    {checked_block}
    """


def build_accent_label_qss(tokens: ThemeTokens) -> str:
    return f"color: {tokens.accent};"


def build_placeholder_label_qss(tokens: ThemeTokens) -> str:
    return f"""
    QLabel {{
        border: 1px solid {tokens.border_subtle};
        padding: 4px 14px;
        background-color: {tokens.panel_alt_bg};
        color: {tokens.text_secondary};
    }}
    """


def build_player_panel_qss(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        background-color: {tokens.panel_bg};
        color: {tokens.text_primary};
    }}
    QLabel {{
        color: {tokens.text_primary};
    }}
    QPushButton {{
        background-color: {tokens.button_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 12px;
    }}
    """


def build_player_list_qss(tokens: ThemeTokens) -> str:
    return f"""
    QListWidget {{
        background-color: {tokens.panel_alt_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 16px;
        padding: 6px;
        outline: 0;
    }}
    QListWidget::item {{
        min-height: 24px;
        margin: 1px 0;
        padding: 4px 8px;
        border: 1px solid transparent;
        border-radius: 10px;
        background: transparent;
    }}
    QListWidget::item:hover {{
        background: {tokens.menu_hover_bg};
        border-color: {tokens.input_hover_border};
    }}
    QListWidget::item:selected {{
        background: {tokens.menu_selected_bg};
        border-color: {tokens.accent};
        color: {tokens.text_primary};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 8px 2px 8px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens.input_border};
        min-height: 28px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {tokens.input_hover_border};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """


def build_player_text_panel_qss(tokens: ThemeTokens, *, padding: str = "12px 14px") -> str:
    return f"""
    QTextBrowser, QTextEdit {{
        background-color: {tokens.panel_alt_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 16px;
        padding: {padding};
        selection-background-color: {tokens.menu_selected_bg};
        selection-color: {tokens.text_primary};
    }}
    QTextBrowser:hover, QTextEdit:hover {{
        border-color: {tokens.input_hover_border};
    }}
    QTextBrowser a {{
        color: {tokens.accent};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 8px 2px 8px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens.input_border};
        min-height: 28px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {tokens.input_hover_border};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """


def build_player_section_heading_qss(tokens: ThemeTokens) -> str:
    return f"""
    QLabel {{
        color: {tokens.accent};
        font-size: 15px;
        font-weight: 700;
        padding: 2px 2px 0 2px;
    }}
    """


def build_player_tabbar_qss(tokens: ThemeTokens) -> str:
    return f"""
    QTabBar::tab {{
        background: {tokens.panel_alt_bg};
        color: {tokens.text_secondary};
        border: 1px solid {tokens.border_subtle};
        border-radius: 12px;
        padding: 8px 14px;
        margin-right: 6px;
    }}
    QTabBar::tab:hover {{
        color: {tokens.text_primary};
        border-color: {tokens.input_hover_border};
    }}
    QTabBar::tab:selected {{
        background: {tokens.menu_selected_bg};
        color: {tokens.text_primary};
        border-color: {tokens.accent};
    }}
    """


def build_player_immersive_qss(tokens: ThemeTokens) -> str:
    return f"""
    background-color: {tokens.player_overlay_bg};
    color: {tokens.player_text_on_dark};
    QWidget {{
        background-color: transparent;
        color: {tokens.player_text_on_dark};
    }}
    QLabel {{
        background-color: transparent;
        color: {tokens.player_text_on_dark};
    }}
    QPushButton {{
        background-color: {tokens.player_controls_bg};
        color: {tokens.player_text_on_dark};
        border: 1px solid {tokens.player_scrim};
        border-radius: 12px;
    }}
    """


def build_player_control_button_qss(
    tokens: ThemeTokens,
    *,
    role: Literal["primary", "secondary"] = "secondary",
    border_radius: int = 16,
) -> str:
    if role == "primary":
        background = tokens.player_primary_button_bg
        hover_bg = tokens.player_primary_button_hover_bg
        pressed_bg = tokens.player_primary_button_pressed_bg
        border = tokens.player_primary_button_bg
        text = tokens.player_primary_button_icon
    else:
        background = tokens.player_button_bg
        hover_bg = tokens.player_button_hover_bg
        pressed_bg = tokens.player_button_pressed_bg
        border = tokens.player_button_border
        text = tokens.player_button_icon
    return f"""
    QPushButton {{
        background-color: {background};
        color: {text};
        border: 1px solid {border};
        border-radius: {border_radius}px;
        padding: 0;
    }}
    QPushButton:hover {{
        background-color: {hover_bg};
        border-color: {tokens.accent_hover};
    }}
    QPushButton:pressed {{
        background-color: {pressed_bg};
    }}
    QPushButton:checked {{
        border-color: {tokens.accent};
    }}
    """


def build_player_spinbox_qss(tokens: ThemeTokens, *, border_radius: int = 12, min_height: int = 28) -> str:
    up_arrow_url = (_ICONS_DIR / "spinbox-step-up.svg").resolve().as_posix()
    down_arrow_url = (_ICONS_DIR / "spinbox-step-down.svg").resolve().as_posix()
    return f"""
    QSpinBox {{
        min-height: {min_height}px;
        padding: 0 20px 0 8px;
        background-color: {tokens.player_button_bg};
        color: {tokens.player_text_on_dark};
        border: 1px solid {tokens.player_button_border};
        border-radius: {border_radius}px;
    }}
    QSpinBox:hover {{
        border-color: {tokens.accent_hover};
    }}
    QSpinBox:focus {{
        border-color: {tokens.accent};
    }}
    QSpinBox:disabled {{
        color: {tokens.text_secondary};
        border-color: {tokens.border_subtle};
    }}
    QSpinBox::up-button,
    QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 16px;
        height: 13px;
        background: {tokens.player_button_hover_bg};
        border-left: 1px solid {tokens.player_button_border};
    }}
    QSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: {max(0, border_radius - 1)}px;
        border-bottom: 1px solid {tokens.player_button_border};
    }}
    QSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: {max(0, border_radius - 1)}px;
    }}
    QSpinBox::up-button:hover,
    QSpinBox::down-button:hover {{
        background: {tokens.player_button_pressed_bg};
    }}
    QSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed {{
        background: {tokens.player_button_bg};
    }}
    QSpinBox::up-arrow {{
        width: 8px;
        height: 5px;
        image: url("{up_arrow_url}");
    }}
    QSpinBox::down-arrow {{
        width: 8px;
        height: 5px;
        image: url("{down_arrow_url}");
    }}
    """


def build_slider_qss(
    tokens: ThemeTokens,
    *,
    groove_height: int = 6,
    handle_diameter: int = 16,
    add_page_color: str | None = None,
) -> str:
    handle_margin = max(0, (handle_diameter - groove_height) // 2)
    hover_diameter = handle_diameter + 4
    hover_margin = max(0, (hover_diameter - groove_height) // 2)
    fill = add_page_color or tokens.accent
    return f"""
    QSlider {{
        background: transparent;
        border: none;
    }}
    QSlider::groove:horizontal {{
        height: {groove_height}px;
        border: none;
        border-radius: {max(1, groove_height // 2)}px;
        background: transparent;
    }}
    QSlider::sub-page:horizontal {{
        height: {groove_height}px;
        border: none;
        border-radius: {max(1, groove_height // 2)}px;
        background: {fill};
    }}
    QSlider::add-page:horizontal {{
        height: {groove_height}px;
        border: none;
        border-radius: {max(1, groove_height // 2)}px;
        background: transparent;
    }}
    QSlider::handle:horizontal {{
        width: {handle_diameter}px;
        height: {handle_diameter}px;
        margin: -{handle_margin}px 0;
        border-radius: {max(1, handle_diameter // 2)}px;
        border: none;
        background: {tokens.player_text_on_dark};
    }}
    QSlider::handle:horizontal:hover {{
        width: {hover_diameter}px;
        height: {hover_diameter}px;
        margin: -{hover_margin}px 0;
        border-radius: {max(1, hover_diameter // 2)}px;
        border: none;
        background: {tokens.accent};
    }}
    QSlider::handle:horizontal:pressed {{
        border: none;
        background: {tokens.accent_hover};
    }}
    QSlider:disabled::groove:horizontal {{
        background: transparent;
    }}
    QSlider:disabled::sub-page:horizontal {{
        background: {tokens.player_button_border};
    }}
    QSlider:disabled::handle:horizontal {{
        background: {tokens.text_secondary};
    }}
    """
