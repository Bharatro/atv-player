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
