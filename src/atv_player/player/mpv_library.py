"""Custom libmpv loading support.

老 CPU 等场景下,应用内置的 libmpv 可能因指令集要求过高而无法加载。把一份
可用的 libmpv 放到以下任一目录(按优先级),应用启动时就会优先加载它,
而不必替换应用目录里的内置文件:

1. 用户目录下的 `mpv` 目录,例如 `~/mpv/libmpv-2.dll`
2. 应用目录下的 `lib` 子目录,例如 `<应用目录>/lib/libmpv-2.dll`
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_LIBRARY_FILE_NAMES = ("libmpv-2.dll", "mpv-2.dll", "mpv.dll", "mpv-1.dll")
_POSIX_LIBRARY_FILE_NAMES = (
    "libmpv.so",
    "libmpv.so.2",
    "libmpv.dylib",
    "libmpv.2.dylib",
)

# python-mpv 在 Windows 上的查找顺序:逐名字扫完整个 PATH 后才试下一个名字。
_PYTHON_MPV_WINDOWS_LOOKUP_NAMES = ("mpv-2.dll", "libmpv-2.dll", "mpv-1.dll")

_PREPARED_STATE: dict[str, object] = {}


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # 源码运行:src/atv_player/player/mpv_library.py → 仓库根目录
    return Path(__file__).resolve().parents[3]


def custom_mpv_library_search_dirs() -> list[Path]:
    return [
        Path.home() / "mpv",
        _application_directory() / "lib",
    ]


def _candidate_file_names() -> tuple[str, ...]:
    if _is_windows():
        return _WINDOWS_LIBRARY_FILE_NAMES
    return _POSIX_LIBRARY_FILE_NAMES


def resolve_custom_mpv_library() -> Path | None:
    for directory in custom_mpv_library_search_dirs():
        if not directory.is_dir():
            continue
        for name in _candidate_file_names():
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _prepend_path_entry(directory: str) -> None:
    normalized = str(directory)
    entries = [
        entry for entry in str(os.environ.get("PATH") or "").split(os.pathsep) if entry
    ]
    entries = [normalized] + [entry for entry in entries if entry != normalized]
    os.environ["PATH"] = os.pathsep.join(entries)


def _preload_mpv_library(path: Path) -> None:
    if _is_windows():
        # LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR,
        # 与 python-mpv 加载 DLL 时的 flags 一致,保证其依赖(ffmpeg 等)从同目录解析。
        ctypes.CDLL(str(path), winmode=0x00001000 | 0x00000100)
    else:
        ctypes.CDLL(str(path))


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return str(left) == str(right)


def _simulate_python_mpv_windows_lookup() -> str:
    for name in _PYTHON_MPV_WINDOWS_LOOKUP_NAMES:
        found = ctypes.util.find_library(name)
        if found:
            return found
    return ""


def prepare_custom_mpv_library() -> Path | None:
    """在 `import mpv` 之前调用;幂等,未找到自定义库时保持内置 libmpv。"""
    if _PREPARED_STATE:
        path = _PREPARED_STATE.get("path")
        return path if isinstance(path, Path) else None

    resolved = resolve_custom_mpv_library()
    if resolved is None:
        _PREPARED_STATE["path"] = None
        return None

    try:
        _preload_mpv_library(resolved)
    except Exception as exc:
        logger.error(
            "自定义 libmpv 加载失败:%s(%r),回退内置 libmpv",
            resolved,
            exc,
            extra={"log_category": "player", "log_source": "app"},
        )
        _PREPARED_STATE["path"] = None
        return None

    directory = str(resolved.parent)
    if _is_windows():
        try:
            os.add_dll_directory(directory)
        except (AttributeError, OSError):
            pass
    _prepend_path_entry(directory)

    if _is_windows():
        # python-mpv 按名字优先级扫 PATH;若自定义文件名排在后面,可能被
        # PATH 中其它目录的同批候选抢先,此时给出明确告警。
        lookup = _simulate_python_mpv_windows_lookup()
        if lookup and not _same_path(Path(lookup), resolved):
            logger.warning(
                "python-mpv 将优先加载 %s 而不是 %s(名字优先级/PATH 顺序导致),"
                "建议把自定义 DLL 重命名为 %s 或移出 PATH 中更靠前的同名库",
                lookup,
                resolved,
                _PYTHON_MPV_WINDOWS_LOOKUP_NAMES[0],
                extra={"log_category": "player", "log_source": "app"},
            )

    logger.info(
        "使用自定义 libmpv:%s",
        resolved,
        extra={"log_category": "player", "log_source": "app"},
    )
    _PREPARED_STATE["path"] = resolved
    return resolved


def custom_mpv_library_diagnostics() -> dict[str, object]:
    prepared_path = _PREPARED_STATE.get("path") if _PREPARED_STATE else None
    resolved = (
        prepared_path if prepared_path is not None else resolve_custom_mpv_library()
    )
    return {
        "custom_mpv_library_search_dirs": [
            str(directory) for directory in custom_mpv_library_search_dirs()
        ],
        "custom_mpv_library_resolved": str(resolved or ""),
        "custom_mpv_library_active": bool(_PREPARED_STATE)
        and isinstance(prepared_path, Path),
    }


def _reset_custom_mpv_library_state() -> None:
    _PREPARED_STATE.clear()
