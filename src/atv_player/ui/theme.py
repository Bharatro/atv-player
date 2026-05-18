from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ThemeMode = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]


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
    button_bg: str
    button_primary_bg: str
    button_primary_text: str
    player_overlay_bg: str
    player_controls_bg: str
    player_scrim: str
    player_text_on_dark: str


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
    button_bg="#fffaf5",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
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
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
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
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    player_overlay_bg="#171b24",
    player_controls_bg="#212734",
    player_scrim="rgba(0, 0, 0, 0.45)",
    player_text_on_dark="#f5f7fb",
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
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QTableWidget {{
            background-color: {tokens.input_bg};
            border: 1px solid {tokens.input_border};
            border-radius: 12px;
            color: {tokens.text_primary};
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


def build_player_immersive_qss(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        background-color: {tokens.player_overlay_bg};
        color: {tokens.player_text_on_dark};
    }}
    QLabel {{
        color: {tokens.player_text_on_dark};
    }}
    QPushButton {{
        background-color: {tokens.player_controls_bg};
        color: {tokens.player_text_on_dark};
        border: 1px solid {tokens.player_scrim};
        border-radius: 12px;
    }}
    """
