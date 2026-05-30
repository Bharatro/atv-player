from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _executable_name() -> str:
    return "yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp"


def _is_usable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _normalized_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _escaped_mpv_list_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,")


def _resolved_cookie_browser(cookie_browser: str = "") -> str:
    explicit = str(cookie_browser or "").strip().lower()
    if explicit in {"chrome", "edge", "firefox"}:
        return explicit
    raw_value = _normalized_env("ATV_YTDLP_COOKIES_FROM_BROWSER")
    if raw_value.lower() in {"0", "false", "no", "none", "off"}:
        return ""
    if raw_value:
        return raw_value
    return ""


def _default_remote_components(cookie_browser: str = "") -> str:
    if _resolved_cookie_browser(cookie_browser):
        return "ejs:github"
    return ""


def _iter_path_candidates(executable_name: str) -> list[Path]:
    candidates: list[Path] = []
    current_python_dir = Path(sys.executable).resolve().parent
    project_venv_dir = Path(__file__).resolve().parents[3] / ".venv" / "bin"
    search_dirs = [
        entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry
    ]
    if not sys.platform.startswith("win"):
        search_dirs.append(str(Path.home() / ".local" / "bin"))
    for raw_entry in search_dirs:
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
    ignored_dirs = {Path(sys.executable).resolve().parent, project_venv_dir}
    if discovered_path.parent in ignored_dirs:
        return ""
    return str(discovered_path)


def resolve_mpv_ytdlp_path() -> str:
    return resolve_system_ytdlp_path()


def build_ytdlp_command_args(
    proxy_args: list[str] | None = None,
    *,
    cookie_browser: str = "",
) -> list[str]:
    args: list[str] = []
    if proxy_args:
        args.extend(proxy_args)
    browser = _resolved_cookie_browser(cookie_browser)
    if browser:
        args.extend(["--cookies-from-browser", browser])
    remote_components = _default_remote_components(cookie_browser)
    if remote_components:
        args.extend(["--remote-components", remote_components])
    return args


def resolve_mpv_ytdl_raw_options(*, cookie_browser: str = "") -> str:
    options: list[str] = []
    browser = _resolved_cookie_browser(cookie_browser)
    if browser:
        options.append(f"cookies-from-browser={_escaped_mpv_list_value(browser)}")
    remote_components = _default_remote_components(cookie_browser)
    if remote_components:
        options.append(f"remote-components={_escaped_mpv_list_value(remote_components)}")
    return ",".join(options)
