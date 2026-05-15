from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _executable_name() -> str:
    return "yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp"


def _is_usable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _iter_path_candidates(executable_name: str) -> list[Path]:
    candidates: list[Path] = []
    current_python_dir = Path(sys.executable).resolve().parent
    project_venv_dir = Path(__file__).resolve().parents[3] / ".venv" / "bin"
    for raw_entry in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_entry:
            continue
        directory = Path(raw_entry).expanduser()
        if directory == current_python_dir or directory == project_venv_dir:
            continue
        candidate = directory / executable_name
        if _is_usable_file(candidate):
            candidates.append(candidate)
    return candidates


def resolve_system_ytdlp_path() -> str:
    explicit = os.environ.get("ATV_YTDLP_PATH", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if _is_usable_file(candidate):
            return str(candidate)
        return ""

    candidates = _iter_path_candidates(_executable_name())
    if candidates:
        return str(candidates[0])
    discovered = shutil.which(_executable_name())
    if not discovered:
        return ""
    discovered_path = Path(discovered).expanduser()
    project_venv_dir = Path(__file__).resolve().parents[3] / ".venv" / "bin"
    if discovered_path.parent in {Path(sys.executable).resolve().parent, project_venv_dir}:
        return ""
    return str(discovered_path)


def resolve_mpv_ytdlp_path() -> str:
    return resolve_system_ytdlp_path()
