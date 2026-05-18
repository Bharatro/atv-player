from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

_ICON_CACHE: dict[str, QIcon] = {}
_TINTED_ICON_CACHE: dict[tuple[int, str, int, int], QIcon] = {}


def load_icon(path: str | Path) -> QIcon:
    key = str(path)
    icon = _ICON_CACHE.get(key)
    if icon is None:
        icon = QIcon(key)
        _ICON_CACHE[key] = icon
    return icon


def load_tinted_icon(path: str | Path, color: str, *, size: int | QSize = 24) -> QIcon:
    return tint_icon(load_icon(path), color, size=size)


def tint_icon(icon: QIcon, color: str, *, size: int | QSize = 24) -> QIcon:
    target_size = QSize(size, size) if isinstance(size, int) else size
    key = (icon.cacheKey(), color, target_size.width(), target_size.height())
    cached = _TINTED_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap = icon.pixmap(target_size)
    if pixmap.isNull():
        return icon
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    tinted_icon = QIcon(tinted)
    _TINTED_ICON_CACHE[key] = tinted_icon
    return tinted_icon


def clear_icon_cache() -> None:
    _ICON_CACHE.clear()
    _TINTED_ICON_CACHE.clear()
