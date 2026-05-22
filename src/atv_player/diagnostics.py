from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtWidgets import QApplication

from atv_player.player.ytdlp_runtime import resolve_system_ytdlp_path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"
_BUNDLED_VERSION_PATH = Path(__file__).with_name("_build_version.txt")
_MISSING_VALUE = "未安装"
_UNAVAILABLE_VALUE = "不可用"
_TIMEOUT_VALUE = "超时"


@dataclass(frozen=True, slots=True)
class SystemInfoEntry:
    label: str
    value: str
    url: str | None = None


_ATV_PLAYER_DOWNLOAD_URL = "https://github.com/power721/atv-player/releases/latest"
_PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
_PYSIDE6_HOME_URL = "https://doc.qt.io/qtforpython-6/"
_MPV_HOME_URL = "https://mpv.io/installation/"
_FFMPEG_HOME_URL = "https://www.ffmpeg.org/download.html"
_YTDLP_DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest"


def collect_system_info_entries() -> tuple[SystemInfoEntry, ...]:
    ytdlp_path = resolve_system_ytdlp_path() or "yt-dlp"
    return (
        SystemInfoEntry("atv-player", resolve_app_version(), _ATV_PLAYER_DOWNLOAD_URL),
        SystemInfoEntry("Python", platform.python_version(), _PYTHON_DOWNLOAD_URL),
        SystemInfoEntry("PySide6", pyside_version, _PYSIDE6_HOME_URL),
        SystemInfoEntry("mpv", _read_command_version(["mpv", "--version"], _parse_mpv_version), _MPV_HOME_URL),
        SystemInfoEntry("ffmpeg", _read_command_version(["ffmpeg", "-version"], _parse_ffmpeg_version), _FFMPEG_HOME_URL),
        SystemInfoEntry("yt-dlp", _read_command_version([ytdlp_path, "--version"], _parse_ytdlp_version), _YTDLP_DOWNLOAD_URL),
        SystemInfoEntry("Platform", platform.system() or platform.platform() or "Unknown"),
    )


def resolve_app_version() -> str:
    env_version = os.environ.get("ATV_BUILD_VERSION", "").strip()
    if env_version:
        return env_version
    app = QApplication.instance()
    if app is not None:
        runtime_version = app.applicationVersion().strip()
        if runtime_version:
            return runtime_version
    bundled_version = _read_bundled_version()
    if bundled_version:
        return bundled_version
    try:
        return importlib.metadata.version("atv-player")
    except importlib.metadata.PackageNotFoundError:
        return _read_pyproject_version()


def _read_bundled_version() -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates = [
            Path(meipass) / "atv_player" / "_build_version.txt",
            Path(meipass) / "_build_version.txt",
        ]
    else:
        candidates = [_BUNDLED_VERSION_PATH]
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError:
            continue
    return ""


def _read_pyproject_version() -> str:
    if not _PYPROJECT_PATH.exists():
        return _UNAVAILABLE_VALUE
    try:
        text = _PYPROJECT_PATH.read_text(encoding="utf-8")
    except OSError:
        return _UNAVAILABLE_VALUE
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
    if match is None:
        return _UNAVAILABLE_VALUE
    return match.group(1).strip() or _UNAVAILABLE_VALUE


def _read_command_version(command: list[str], parser) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=2,
            check=False,
        )
    except FileNotFoundError:
        return _MISSING_VALUE
    except OSError:
        return _UNAVAILABLE_VALUE
    except subprocess.TimeoutExpired:
        return _TIMEOUT_VALUE

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if not output:
        return _UNAVAILABLE_VALUE
    parsed = parser(output)
    return parsed or _UNAVAILABLE_VALUE


def _parse_mpv_version(output: str) -> str:
    match = re.search(r"(?m)^mpv\s+([^\s]+)", output)
    return match.group(1) if match is not None else ""


def _parse_ffmpeg_version(output: str) -> str:
    match = re.search(r"(?m)^ffmpeg version\s+([^\s]+)", output)
    return match.group(1) if match is not None else ""


def _parse_ytdlp_version(output: str) -> str:
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return first_line.split()[0] if first_line else ""
