from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_NAME = "atv-player"


def _writable_location(
    location: QStandardPaths.StandardLocation,
    fallback: Path,
) -> Path:
    resolved = QStandardPaths.writableLocation(location)
    if resolved:
        return Path(resolved)
    return fallback


def _app_scoped_location(
    location: QStandardPaths.StandardLocation,
    fallback_base: Path,
) -> Path:
    path = _writable_location(location, fallback_base)
    if path.name != APP_NAME:
        path = path / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_data_dir() -> Path:
    return _app_scoped_location(
        QStandardPaths.StandardLocation.GenericDataLocation,
        Path.home() / ".local" / "share",
    )


def app_cache_dir() -> Path:
    return _app_scoped_location(
        QStandardPaths.StandardLocation.GenericCacheLocation,
        Path.home() / ".cache",
    )
