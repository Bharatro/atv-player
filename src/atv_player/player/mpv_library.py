"""Custom libmpv loading support.

老 CPU 等场景下,应用内置的 libmpv 可能因指令集要求过高而无法加载。把一份
可用的 libmpv 放到以下任一目录(按优先级),应用启动时就会优先加载它,
而不必替换应用目录里的内置文件:

1. 用户目录下的 `mpv` 目录,例如 `~/mpv/libmpv-2.dll`
2. 应用目录下的 `lib` 子目录,例如 `<应用目录>/lib/libmpv-2.dll`
3. 应用目录本身,例如 `<应用目录>/libmpv-2.dll`

候选按上述目录与文件名优先级逐个尝试,某个文件加载失败会继续尝试下一个。

Linux 上,以上自定义候选不存在或全部加载失败时,在系统 libmpv 与应用内置
libmpv 之间选新者预载:内置库加载失败(依赖缺失等)时直接用系统库;两者都
可用时比较 `mpv_client_api_version`,新者胜,相等取系统(与系统环境的驱动/
共享库集成更好)。系统与内置都不可用时维持 python-mpv 的默认查找(即内置
库,PyInstaller 已把 `_internal` 注入 LD_LIBRARY_PATH)。
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_LIBRARY_FILE_NAMES = ("libmpv-2.dll", "mpv-2.dll", "mpv.dll", "mpv-1.dll")
_POSIX_LIBRARY_FILE_NAMES = (
    "libmpv.so",
    "libmpv.so.2",
    "libmpv.dylib",
    "libmpv.2.dylib",
)

# 系统 libmpv 的 soname。AppImage/PyInstaller 运行时 LD_LIBRARY_PATH 指向
# _internal,按 soname dlopen 会抢先命中内置库,因此必须解析出绝对路径预载。
_LINUX_SYSTEM_LIBRARY_SONAME = "libmpv.so.2"
_LDCONFIG_EXECUTABLE_CANDIDATES = ("/sbin/ldconfig", "/usr/sbin/ldconfig")
_LDCONFIG_LINE_PATTERN = re.compile(
    rf"^\s*{re.escape(_LINUX_SYSTEM_LIBRARY_SONAME)}\s+\([^)]*\)\s*(?:=>|->)\s+(\S+)"
)

# python-mpv 在 Windows 上的查找顺序:逐名字扫完整个 PATH 后才试下一个名字。
_PYTHON_MPV_WINDOWS_LOOKUP_NAMES = ("mpv-2.dll", "libmpv-2.dll", "mpv-1.dll")

_PREPARED_STATE: dict[str, object] = {}


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_linux() -> bool:
    return sys.platform == "linux"


def _application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # 源码运行:src/atv_player/player/mpv_library.py → 仓库根目录
    return Path(__file__).resolve().parents[3]


def custom_mpv_library_search_dirs() -> list[Path]:
    application_directory = _application_directory()
    return [
        Path.home() / "mpv",
        application_directory / "lib",
        application_directory,
    ]


def _candidate_file_names() -> tuple[str, ...]:
    if _is_windows():
        return _WINDOWS_LIBRARY_FILE_NAMES
    return _POSIX_LIBRARY_FILE_NAMES


def iter_custom_mpv_library_candidates() -> Iterator[Path]:
    """按优先级逐个产出存在的自定义 libmpv 候选文件。"""
    for directory in custom_mpv_library_search_dirs():
        if not directory.is_dir():
            continue
        for name in _candidate_file_names():
            candidate = directory / name
            if candidate.is_file():
                yield candidate


def resolve_custom_mpv_library() -> Path | None:
    return next(iter_custom_mpv_library_candidates(), None)


def _ldconfig_arch_marker() -> str | None:
    # ldconfig -p 输出里 x86_64 标记为 "x86-64",其余常见架构沿用机器名。
    machine = platform.machine()
    if not machine:
        return None
    return {"x86_64": "x86-64"}.get(machine, machine)


def _ldconfig_executable() -> str | None:
    for candidate in _LDCONFIG_EXECUTABLE_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("ldconfig")


def _system_mpv_paths_from_ldconfig() -> list[Path]:
    """解析 `ldconfig -p` 缓存中 libmpv.so.2 的绝对路径,当前架构优先。"""
    executable = _ldconfig_executable()
    if executable is None:
        return []
    try:
        process = subprocess.run(
            [executable, "-p"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if process.returncode != 0:
        return []

    marker = _ldconfig_arch_marker()
    preferred: list[Path] = []
    others: list[Path] = []
    for line in process.stdout.splitlines():
        match = _LDCONFIG_LINE_PATTERN.match(line)
        if match is None:
            continue
        path = Path(match.group(1))
        # 多架构合并缓存里无架构标记的条目(如 amd64 系统上的 i386 库)靠后。
        if marker is not None and f",{marker})" in line:
            preferred.append(path)
        else:
            others.append(path)
    return preferred + others


def _system_mpv_fallback_paths() -> list[Path]:
    machine = platform.machine()
    names: list[str] = []
    if machine:
        names.append(f"/usr/lib/{machine}-linux-gnu/{_LINUX_SYSTEM_LIBRARY_SONAME}")
    names.extend(
        [
            f"/usr/lib64/{_LINUX_SYSTEM_LIBRARY_SONAME}",
            f"/usr/local/lib/{_LINUX_SYSTEM_LIBRARY_SONAME}",
            f"/usr/lib/{_LINUX_SYSTEM_LIBRARY_SONAME}",
        ]
    )
    return [Path(name) for name in names]


def resolve_system_mpv_library() -> Path | None:
    """返回系统 libmpv 的绝对路径;仅 Linux,未安装时为 None。"""
    if not _is_linux():
        return None
    seen: set[Path] = set()
    for path in _system_mpv_paths_from_ldconfig() + _system_mpv_fallback_paths():
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def _prepend_path_entry(directory: str) -> None:
    normalized = str(directory)
    entries = [
        entry for entry in str(os.environ.get("PATH") or "").split(os.pathsep) if entry
    ]
    entries = [normalized] + [entry for entry in entries if entry != normalized]
    os.environ["PATH"] = os.pathsep.join(entries)


def _preload_mpv_library(path: Path) -> ctypes.CDLL:
    if _is_windows():
        # LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR,
        # 与 python-mpv 加载 DLL 时的 flags 一致,保证其依赖(ffmpeg 等)从同目录解析。
        return ctypes.CDLL(str(path), winmode=0x00001000 | 0x00000100)
    return ctypes.CDLL(str(path))


def _mpv_client_api_version(library: ctypes.CDLL) -> int | None:
    """读取 libmpv 编译期 client API 版本(major<<16 | minor);无符号时 None。"""
    try:
        func = library.mpv_client_api_version
    except AttributeError:
        return None
    func.restype = ctypes.c_ulong
    return int(func())


def _format_client_api_version(value: int | None) -> str:
    if value is None:
        return "不可加载"
    return f"{value >> 16}.{value & 0xFFFF}"


def _read_library_client_api_version(path: Path) -> int | None:
    """在当前进程加载库并读版本;仅供子进程探测使用。"""
    try:
        library = ctypes.CDLL(str(path))
    except Exception:
        return None
    return _mpv_client_api_version(library)


def _probe_mpv_client_api_version_via_fork(path: Path) -> int | None:
    """fork 短命子进程加载库读版本,返回 None 表示该库不可加载或无版本符号。

    必须在子进程里探测:dlclose 对 libmpv(及其 TLS 依赖)是"假卸载",
    先加载的同 soname 库会永久占据后续按 soname 的 dlopen 命中(python-mpv
    正是按 soname 加载),主进程一旦为读版本加载过任何一份,选择就不可逆。
    子进程只做 dlopen + 读常量 + os._exit,不触碰 Qt/信号/atexit。
    """
    try:
        read_fd, write_fd = os.pipe()
    except OSError:
        return None
    try:
        pid = os.fork()
    except OSError:
        os.close(read_fd)
        os.close(write_fd)
        return None
    if pid == 0:
        status = 1
        try:
            os.close(read_fd)
            value = _read_library_client_api_version(path)
            if value is not None:
                os.write(write_fd, value.to_bytes(8, "big"))
                status = 0
        except BaseException:
            status = 1
        finally:
            os._exit(status)
    os.close(write_fd)
    data = b""
    try:
        while len(data) < 8:
            chunk = os.read(read_fd, 8 - len(data))
            if not chunk:
                break
            data += chunk
    except OSError:
        data = b""
    finally:
        os.close(read_fd)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    if len(data) != 8:
        return None
    return int.from_bytes(data, "big")


def _bundled_mpv_library_path() -> Path | None:
    """返回打包内置的 libmpv 路径;源码运行(未冻结)时为 None。"""
    if not getattr(sys, "frozen", False):
        return None
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # onefile 指向解包目录,onedir 指向 _internal
        candidates.append(Path(meipass) / _LINUX_SYSTEM_LIBRARY_SONAME)
    executable_dir = Path(sys.executable).resolve().parent
    candidates.append(executable_dir / "_internal" / _LINUX_SYSTEM_LIBRARY_SONAME)
    candidates.append(executable_dir / _LINUX_SYSTEM_LIBRARY_SONAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return str(left) == str(right)


def _simulate_python_mpv_windows_lookup() -> str:
    # 与 python-mpv + Python 3.12 ctypes.util.find_library(Windows) 的行为一致:
    # 按名字优先级逐个扫完整个 PATH,名字优先级高于目录顺序。
    path_entries = [
        entry for entry in str(os.environ.get("PATH") or "").split(os.pathsep) if entry
    ]
    for name in _PYTHON_MPV_WINDOWS_LOOKUP_NAMES:
        for entry in path_entries:
            candidate = Path(entry) / name
            if candidate.is_file():
                return str(candidate)
    return ""


def _ensure_first_name_alias(resolved: Path) -> bool:
    """在自定义 DLL 同目录生成 python-mpv 首选名字(mpv-2.dll)的硬链接。

    python-mpv 扫到 mpv-2.dll 就不会再找 libmpv-2.dll,首名字命中自定义目录
    即可避免 PATH 中其它同名 DLL 抢先。硬链接失败时退化为复制。
    """
    alias_name = _PYTHON_MPV_WINDOWS_LOOKUP_NAMES[0]
    if resolved.name.lower() == alias_name:
        return True
    alias = resolved.parent / alias_name
    try:
        if alias.exists():
            try:
                if alias.samefile(resolved):
                    return True
            except OSError:
                pass
            alias.unlink()
        os.link(resolved, alias)
        return True
    except OSError:
        pass
    try:
        shutil.copy2(resolved, alias)
        return True
    except OSError:
        return False


def _activate_custom_mpv_library(resolved: Path) -> Path:
    directory = str(resolved.parent)
    if _is_windows():
        try:
            os.add_dll_directory(directory)
        except (AttributeError, OSError):
            pass
    _prepend_path_entry(directory)

    if _is_windows():
        # python-mpv 在 Windows 上按名字优先级扫整个 PATH(mpv-2.dll 先于
        # libmpv-2.dll),PATH 中别处的 mpv-2.dll 会抢先于自定义目录里的其它
        # 名字。检测到冲突时自动补一个首名字硬链接兜底。
        lookup = _simulate_python_mpv_windows_lookup()
        if lookup and not _same_path(Path(lookup), resolved):
            if _ensure_first_name_alias(resolved):
                logger.warning(
                    "PATH 中 %s 会按名字优先级抢先于自定义 libmpv,已在 %s 生成 %s 硬链接以确保加载自定义库",
                    lookup,
                    resolved.parent,
                    _PYTHON_MPV_WINDOWS_LOOKUP_NAMES[0],
                    extra={"log_category": "player", "log_source": "app"},
                )
            else:
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
    _PREPARED_STATE["source"] = "custom"
    return resolved


def _try_select_preferred_mpv_library() -> Path | None:
    """Linux 上在系统与应用内置 libmpv 之间选新者预载,主进程只加载胜者,
    python-mpv 后续按 soname 复用该实例。"""
    if not _is_linux():
        return None
    resolved = resolve_system_mpv_library()
    if resolved is None:
        return None
    bundled_path = _bundled_mpv_library_path()
    if bundled_path is None:
        return _load_preferred_mpv_library(
            [("system", resolved)], note="未找到应用内置 libmpv"
        )

    bundled_version = _probe_mpv_client_api_version_via_fork(bundled_path)
    system_version = _probe_mpv_client_api_version_via_fork(resolved)
    if system_version is None and bundled_version is None:
        logger.warning(
            "系统 libmpv(%s)与应用内置 libmpv(%s)均无法加载,维持 python-mpv 默认查找",
            resolved,
            bundled_path,
            extra={"log_category": "player", "log_source": "app"},
        )
        return None
    if bundled_version is not None and (
        system_version is None or bundled_version > system_version
    ):
        order = [("builtin", bundled_path), ("system", resolved)]
        note = (
            f"系统 libmpv client API {_format_client_api_version(system_version)}"
            f"旧于内置 {_format_client_api_version(bundled_version)}"
        )
    else:
        # 相等取系统:与系统环境的驱动/共享库集成更好
        order = [("system", resolved), ("builtin", bundled_path)]
        note = (
            f"内置 libmpv client API {_format_client_api_version(bundled_version)}"
            f"不新于系统 {_format_client_api_version(system_version)}"
        )
    return _load_preferred_mpv_library(order, note=note)


def _load_preferred_mpv_library(
    order: list[tuple[str, Path]], *, note: str
) -> Path | None:
    labels = {"system": "系统", "builtin": "应用内置"}
    for source, path in order:
        try:
            _preload_mpv_library(path)
        except Exception as exc:
            logger.warning(
                "%s libmpv 加载失败:%s(%r),尝试下一个候选",
                labels.get(source, source),
                path,
                exc,
                extra={"log_category": "player", "log_source": "app"},
            )
            continue
        logger.info(
            "优先加载%s libmpv:%s(%s)",
            labels.get(source, source),
            path,
            note,
            extra={"log_category": "player", "log_source": "app"},
        )
        _PREPARED_STATE["path"] = path
        _PREPARED_STATE["source"] = source
        return path
    logger.error(
        "系统与应用内置 libmpv 均无法在主进程加载,维持 python-mpv 默认查找",
        extra={"log_category": "player", "log_source": "app"},
    )
    return None


def prepare_custom_mpv_library() -> Path | None:
    """在 `import mpv` 之前调用;幂等,候选全部加载失败或不存在时保持内置 libmpv。"""
    if _PREPARED_STATE:
        path = _PREPARED_STATE.get("path")
        return path if isinstance(path, Path) else None

    attempted: list[Path] = []
    for candidate in iter_custom_mpv_library_candidates():
        attempted.append(candidate)
        try:
            _preload_mpv_library(candidate)
        except Exception as exc:
            logger.error(
                "自定义 libmpv 加载失败:%s(%r),继续尝试下一个候选",
                candidate,
                exc,
                extra={"log_category": "player", "log_source": "app"},
            )
            continue
        return _activate_custom_mpv_library(candidate)

    system_path = _try_select_preferred_mpv_library()
    if system_path is not None:
        return system_path

    if attempted:
        logger.error(
            "自定义 libmpv 候选共 %d 个,全部加载失败,回退内置 libmpv:%s",
            len(attempted),
            ", ".join(str(path) for path in attempted),
            extra={"log_category": "player", "log_source": "app"},
        )
    _PREPARED_STATE["path"] = None
    return None


def active_mpv_library_description() -> tuple[str, str]:
    """返回 (来源, 路径) 供系统信息展示;来源为 自定义/系统/应用内置。

    `prepare_custom_mpv_library()` 已执行时报告实际生效结果;未执行时(如主窗口
    首次播放前打开帮助)按加载优先级预测,只查候选文件是否存在,不触发 dlopen
    和版本比较(新者胜判定在 prepare 阶段做),因此预测可能偏乐观。
    """
    source_labels = {"custom": "自定义", "system": "系统", "builtin": "应用内置"}
    if _PREPARED_STATE:
        path = _PREPARED_STATE.get("path")
        source = str(_PREPARED_STATE.get("source") or "")
        if isinstance(path, Path) and source in source_labels:
            return source_labels[source], str(path)
        return "应用内置", ""
    custom = resolve_custom_mpv_library()
    if custom is not None:
        return "自定义", str(custom)
    system = resolve_system_mpv_library() if _is_linux() else None
    if system is not None:
        return "系统", str(system)
    return "应用内置", ""


def custom_mpv_library_diagnostics() -> dict[str, object]:
    prepared_path = _PREPARED_STATE.get("path") if _PREPARED_STATE else None
    resolved = (
        prepared_path if prepared_path is not None else resolve_custom_mpv_library()
    )
    source = _PREPARED_STATE.get("source") if _PREPARED_STATE else None
    return {
        "custom_mpv_library_search_dirs": [
            str(directory) for directory in custom_mpv_library_search_dirs()
        ],
        "custom_mpv_library_resolved": str(resolved or ""),
        "custom_mpv_library_active": source == "custom",
        "mpv_library_source": str(source or ""),
        "system_mpv_library_resolved": str(resolve_system_mpv_library() or ""),
    }


def _reset_custom_mpv_library_state() -> None:
    _PREPARED_STATE.clear()
