import ctypes
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atv_player.player import mpv_library
from atv_player.player.mpv_library import (
    custom_mpv_library_diagnostics,
    custom_mpv_library_search_dirs,
    prepare_custom_mpv_library,
    resolve_custom_mpv_library,
    resolve_system_mpv_library,
)


@pytest.fixture(autouse=True)
def _reset_state():
    mpv_library._reset_custom_mpv_library_state()
    yield
    mpv_library._reset_custom_mpv_library_state()


@pytest.fixture(autouse=True)
def _isolated_system_mpv(monkeypatch):
    """默认屏蔽系统 libmpv 解析,避免开发机环境影响既有用例。"""
    monkeypatch.setattr(mpv_library, "resolve_system_mpv_library", lambda: None)


@pytest.fixture()
def search_dirs(tmp_path, monkeypatch):
    """把查找目录替换为临时目录,避免受开发机上真实 ~/mpv 影响。"""
    user_dir = tmp_path / "user-mpv"
    app_lib_dir = tmp_path / "app" / "lib"
    user_dir.mkdir()
    app_lib_dir.mkdir(parents=True)
    monkeypatch.setattr(
        mpv_library, "custom_mpv_library_search_dirs", lambda: [user_dir, app_lib_dir]
    )
    return user_dir, app_lib_dir


class FakeCDLL:
    def __init__(self, path: str, *args: object, **kwargs: object) -> None:
        self.path = path
        self.kwargs = kwargs
        self._handle = 0
        if not Path(path).is_file():
            raise OSError(f"cannot open shared object file: {path}")


def install_fake_cdll(monkeypatch) -> list[str]:
    """替换 ctypes.CDLL 记录加载路径;版本探测走 fork,被单独 mock。"""
    loads: list[str] = []

    def factory(path: str, **kwargs: object):
        library = FakeCDLL(path, **kwargs)
        library._handle = len(loads) + 1
        loads.append(path)
        return library

    monkeypatch.setattr(ctypes, "CDLL", factory)
    return loads


def test_search_dirs_prefer_user_mpv_dir_then_app_lib(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr(sys, "executable", str(app_dir / "atv-player.exe"))

    directories = custom_mpv_library_search_dirs()

    assert directories == [
        tmp_path / "home" / "mpv",
        app_dir / "lib",
        app_dir,
    ]


def test_search_dirs_use_repo_root_when_running_from_source() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert mpv_library._application_directory() == repo_root


def test_resolve_custom_mpv_library_prefers_user_dir(search_dirs, monkeypatch) -> None:
    user_dir, app_lib_dir = search_dirs
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    (user_dir / "libmpv-2.dll").write_bytes(b"")
    (app_lib_dir / "libmpv-2.dll").write_bytes(b"")

    assert resolve_custom_mpv_library() == user_dir / "libmpv-2.dll"


def test_resolve_custom_mpv_library_falls_back_to_app_lib(
    search_dirs, monkeypatch
) -> None:
    user_dir, app_lib_dir = search_dirs
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    (app_lib_dir / "mpv.dll").write_bytes(b"")

    assert resolve_custom_mpv_library() == app_lib_dir / "mpv.dll"


def test_resolve_custom_mpv_library_file_name_priority_in_dir(
    search_dirs, monkeypatch
) -> None:
    user_dir, _app_lib_dir = search_dirs
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    first = user_dir / "libmpv-2.dll"
    second = user_dir / "mpv.dll"
    first.write_bytes(b"")
    second.write_bytes(b"")

    assert resolve_custom_mpv_library() == first

    first.unlink()

    assert resolve_custom_mpv_library() == second


def test_resolve_custom_mpv_library_returns_none_when_no_candidate(search_dirs) -> None:
    assert resolve_custom_mpv_library() is None


def test_prepare_custom_mpv_library_without_candidate_is_noop(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() is None
    assert prepare_custom_mpv_library() is None
    assert os.environ.get("PATH", "") == ""


def test_prepare_custom_mpv_library_preloads_and_prepends_path(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"")
    loads: list[str] = []
    monkeypatch.setattr(
        ctypes, "CDLL", lambda path, **kwargs: loads.append(path) or FakeCDLL(path)
    )
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() == dll
    assert loads == [str(dll)]
    assert os.environ["PATH"].split(os.pathsep)[0] == str(user_dir)

    # 幂等:重复调用不会再次加载或重复前插 PATH
    assert prepare_custom_mpv_library() == dll
    assert loads == [str(dll)]
    assert os.environ["PATH"].split(os.pathsep).count(str(user_dir)) == 1


def test_prepare_custom_mpv_library_tries_next_candidate_when_dll_broken(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, app_lib_dir = search_dirs
    broken = user_dir / "libmpv-2.dll"
    broken.write_bytes(b"")
    good = app_lib_dir / "libmpv-2.dll"
    good.write_bytes(b"")
    attempts: list[str] = []

    def flaky_cdll(path: str, **_kwargs: object):
        attempts.append(path)
        if Path(path).parent == user_dir:
            raise OSError("illegal instruction")
        return FakeCDLL(path)

    monkeypatch.setattr(ctypes, "CDLL", flaky_cdll)
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() == good
    assert attempts == [str(broken), str(good)]
    # 前插的是最终成功候选所在的目录
    assert os.environ["PATH"].split(os.pathsep)[0] == str(app_lib_dir)


def test_prepare_custom_mpv_library_falls_back_when_dll_broken(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"")

    def broken_cdll(path: str, **_kwargs: object):
        raise OSError("illegal instruction")

    monkeypatch.setattr(ctypes, "CDLL", broken_cdll)
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() is None
    # 全部候选加载失败后不前插 PATH
    assert os.environ.get("PATH", "") == ""
    assert prepare_custom_mpv_library() is None


def test_prepare_custom_mpv_library_windows_flags_passed(
    search_dirs, monkeypatch
) -> None:
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"")
    recorded: dict[str, object] = {}

    def recording_cdll(path: str, mode=0, handle=None, **kwargs: object):
        recorded["path"] = path
        recorded["kwargs"] = kwargs
        return FakeCDLL(path)

    monkeypatch.setattr(ctypes, "CDLL", recording_cdll)
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() == dll
    assert recorded["kwargs"] == {"winmode": 0x00001000 | 0x00000100}


def test_prepare_custom_mpv_library_creates_alias_when_first_name_shadowed(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"custom-dll")
    stray_dir = user_dir.parent / "stray"
    stray_dir.mkdir()
    (stray_dir / "mpv-2.dll").write_bytes(b"stray-dll")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)
    monkeypatch.setenv("PATH", str(stray_dir))

    assert prepare_custom_mpv_library() == dll

    # PATH 中别处的 mpv-2.dll 抢先时,自动在自定义目录生成首名字硬链接
    alias = user_dir / "mpv-2.dll"
    assert alias.is_file()
    assert alias.samefile(dll)


def test_prepare_custom_mpv_library_alias_falls_back_to_copy(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"custom-dll")
    stray_dir = user_dir.parent / "stray"
    stray_dir.mkdir()
    (stray_dir / "mpv-2.dll").write_bytes(b"stray-dll")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)
    monkeypatch.setenv("PATH", str(stray_dir))

    def broken_link(*_args: object, **_kwargs: object):
        raise OSError("link unsupported")

    monkeypatch.setattr(os, "link", broken_link)

    assert prepare_custom_mpv_library() == dll

    alias = user_dir / "mpv-2.dll"
    assert alias.is_file()
    assert alias.read_bytes() == b"custom-dll"


def test_prepare_custom_mpv_library_skips_alias_without_conflict(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"custom-dll")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() == dll

    assert not (user_dir / "mpv-2.dll").exists()


def test_custom_mpv_library_diagnostics_reports_resolved_path(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(mpv_library, "_is_windows", lambda: True)
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv-2.dll"
    dll.write_bytes(b"")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)

    before = custom_mpv_library_diagnostics()
    assert before["custom_mpv_library_resolved"] == str(dll)
    assert before["custom_mpv_library_active"] is False

    prepare_custom_mpv_library()

    after = custom_mpv_library_diagnostics()
    assert after["custom_mpv_library_resolved"] == str(dll)
    assert after["custom_mpv_library_active"] is True


def test_custom_mpv_library_diagnostics_lists_search_dirs(search_dirs) -> None:
    user_dir, app_lib_dir = search_dirs

    diagnostics = custom_mpv_library_diagnostics()

    assert diagnostics["custom_mpv_library_search_dirs"] == [
        str(user_dir),
        str(app_lib_dir),
    ]


def test_active_mpv_library_description_reports_active_source(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv.so.2"
    dll.write_bytes(b"")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)

    assert prepare_custom_mpv_library() == dll
    assert mpv_library.active_mpv_library_description() == ("自定义", str(dll))

    # 换到系统库场景:清掉状态与自定义候选文件
    mpv_library._reset_custom_mpv_library_state()
    dll.unlink()
    system_library = user_dir.parent / "system" / "libmpv.so.2"
    system_library.parent.mkdir(parents=True, exist_ok=True)
    system_library.write_bytes(b"")
    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", lambda: system_library
    )

    assert prepare_custom_mpv_library() == system_library
    assert mpv_library.active_mpv_library_description() == ("系统", str(system_library))


def test_active_mpv_library_description_reports_builtin_fallback(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv.so.2"
    dll.write_bytes(b"")

    def broken_cdll(path: str, **_kwargs: object):
        raise OSError("cannot open shared object file")

    monkeypatch.setattr(ctypes, "CDLL", broken_cdll)

    assert prepare_custom_mpv_library() is None
    assert mpv_library.active_mpv_library_description() == ("应用内置", "")


def test_active_mpv_library_description_predicts_priority_before_prepare(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    user_dir, _app_lib_dir = search_dirs

    # 未初始化且无任何候选:应用内置
    assert mpv_library.active_mpv_library_description() == ("应用内置", "")

    # 未初始化但系统库存在:预测系统优先于内置
    system_library = user_dir.parent / "system" / "libmpv.so.2"
    system_library.parent.mkdir(parents=True, exist_ok=True)
    system_library.write_bytes(b"")
    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", lambda: system_library
    )
    assert mpv_library.active_mpv_library_description() == ("系统", str(system_library))

    # 自定义候选存在时预测自定义优先
    dll = user_dir / "libmpv.so.2"
    dll.write_bytes(b"")
    assert mpv_library.active_mpv_library_description() == ("自定义", str(dll))


def test_resolve_system_mpv_library_none_on_non_linux(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert resolve_system_mpv_library() is None
    monkeypatch.setattr(sys, "platform", "darwin")
    assert resolve_system_mpv_library() is None


def _fake_ldconfig(monkeypatch, stdout: str) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(mpv_library, "_ldconfig_executable", lambda: "/sbin/ldconfig")
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    completed.stdout = stdout
    completed.stderr = ""
    monkeypatch.setattr(
        mpv_library.subprocess, "run", lambda *args, **kwargs: completed
    )
    monkeypatch.setattr(mpv_library, "_ldconfig_arch_marker", lambda: "x86-64")


def test_resolve_system_mpv_library_prefers_current_arch_entry(monkeypatch) -> None:
    _fake_ldconfig(
        monkeypatch,
        "\n".join(
            [
                " libmpv.so (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/libmpv.so",
                " libmpv.so.2 (libc6) => /usr/lib/i386-linux-gnu/libmpv.so.2",
                " libmpv.so.2 (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/libmpv.so.2",
            ]
        ),
    )

    assert resolve_system_mpv_library() == Path("/usr/lib/x86_64-linux-gnu/libmpv.so.2")


def test_system_mpv_ldconfig_parsing_falls_back_to_unmarked_entry(monkeypatch) -> None:
    _fake_ldconfig(
        monkeypatch,
        "        libmpv.so.2 (libc6) => /usr/local/lib/libmpv.so.2",
    )

    assert mpv_library._system_mpv_paths_from_ldconfig() == [
        Path("/usr/local/lib/libmpv.so.2")
    ]


def test_resolve_system_mpv_library_ignores_ldconfig_failure(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(mpv_library, "_ldconfig_executable", lambda: "/sbin/ldconfig")
    completed = subprocess.CompletedProcess(args=[], returncode=1)
    completed.stdout = ""
    completed.stderr = "boom"

    monkeypatch.setattr(
        mpv_library.subprocess, "run", lambda *args, **kwargs: completed
    )
    monkeypatch.setattr(mpv_library, "_system_mpv_fallback_paths", lambda: [])

    assert resolve_system_mpv_library() is None


def test_resolve_system_mpv_library_uses_fallback_paths_without_ldconfig(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    system_library = tmp_path / "libmpv.so.2"
    system_library.write_bytes(b"")
    monkeypatch.setattr(mpv_library, "_ldconfig_executable", lambda: None)
    monkeypatch.setattr(
        mpv_library, "_system_mpv_fallback_paths", lambda: [system_library]
    )

    assert resolve_system_mpv_library() == system_library


def test_prepare_prefers_system_library_over_builtin(search_dirs, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    system_library = search_dirs[0].parent / "system" / "libmpv.so.2"
    system_library.parent.mkdir(parents=True, exist_ok=True)
    system_library.write_bytes(b"")
    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", lambda: system_library
    )
    loads: list[str] = []
    monkeypatch.setattr(
        ctypes, "CDLL", lambda path, **kwargs: loads.append(path) or FakeCDLL(path)
    )
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() == system_library
    assert loads == [str(system_library)]
    # 系统库预载不修改 PATH,后续 import mpv 按 soname 复用已加载实例
    assert os.environ.get("PATH", "") == ""
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "system"

    # 幂等:重复调用不会再次加载
    assert prepare_custom_mpv_library() == system_library
    assert loads == [str(system_library)]


def test_prepare_falls_back_to_builtin_when_system_library_broken(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    system_library = search_dirs[0].parent / "system" / "libmpv.so.2"
    system_library.parent.mkdir(parents=True, exist_ok=True)
    system_library.write_bytes(b"")
    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", lambda: system_library
    )

    def broken_cdll(path: str, **_kwargs: object):
        raise OSError("cannot open shared object file")

    monkeypatch.setattr(ctypes, "CDLL", broken_cdll)
    monkeypatch.delenv("PATH", raising=False)

    assert prepare_custom_mpv_library() is None
    assert os.environ.get("PATH", "") == ""
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == ""


def test_prepare_custom_candidate_beats_system_library(
    search_dirs, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    user_dir, _app_lib_dir = search_dirs
    dll = user_dir / "libmpv.so.2"
    dll.write_bytes(b"")
    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)
    monkeypatch.delenv("PATH", raising=False)

    system_lookups: list[None] = []

    def _recording_system_lookup() -> Path | None:
        system_lookups.append(None)
        return None

    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", _recording_system_lookup
    )

    assert prepare_custom_mpv_library() == dll
    assert system_lookups == []
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "custom"


def test_bundled_mpv_library_path_prefers_meipass(monkeypatch, tmp_path) -> None:
    meipass = tmp_path / "onefile-extract"
    meipass.mkdir()
    (meipass / "libmpv.so.2").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "executable", str(exe_dir / "atv-player"))

    assert mpv_library._bundled_mpv_library_path() == meipass / "libmpv.so.2"


def test_bundled_mpv_library_path_falls_back_to_internal(monkeypatch, tmp_path) -> None:
    exe_dir = tmp_path / "app"
    (exe_dir / "_internal").mkdir(parents=True)
    (exe_dir / "_internal" / "libmpv.so.2").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "atv-player"))

    assert (
        mpv_library._bundled_mpv_library_path() == exe_dir / "_internal" / "libmpv.so.2"
    )


def test_bundled_mpv_library_path_none_when_running_from_source() -> None:
    assert mpv_library._bundled_mpv_library_path() is None


def _api_version(major: int, minor: int) -> int:
    return (major << 16) | minor


def _install_newer_wins_fixture(
    monkeypatch,
    tmp_path,
    *,
    system_version: int | None,
    bundled_version: int | None,
    bundled_exists: bool = True,
) -> tuple[Path, Path, list[str]]:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("PATH", raising=False)
    system_library = tmp_path / "system" / "libmpv.so.2"
    system_library.parent.mkdir(parents=True, exist_ok=True)
    system_library.write_bytes(b"")
    bundled_library = tmp_path / "bundled" / "libmpv.so.2"
    bundled_library.parent.mkdir(parents=True, exist_ok=True)
    if bundled_exists:
        bundled_library.write_bytes(b"")

    monkeypatch.setattr(
        mpv_library, "resolve_system_mpv_library", lambda: system_library
    )
    monkeypatch.setattr(
        mpv_library, "_bundled_mpv_library_path", lambda: bundled_library
    )
    probe_results = {
        system_library: system_version,
        bundled_library: bundled_version,
    }
    monkeypatch.setattr(
        mpv_library,
        "_probe_mpv_client_api_version_via_fork",
        lambda path: probe_results.get(Path(path)),
    )
    loads = install_fake_cdll(monkeypatch)
    return system_library, bundled_library, loads


def test_select_prefers_system_when_bundled_older(monkeypatch, tmp_path) -> None:
    system_library, _bundled, loads = _install_newer_wins_fixture(
        monkeypatch,
        tmp_path,
        system_version=_api_version(2, 5),
        bundled_version=_api_version(2, 2),
    )

    assert prepare_custom_mpv_library() == system_library
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "system"
    # 版本比较在子进程完成,主进程只加载胜者这一份
    assert loads == [str(system_library)]


def test_select_prefers_system_when_versions_equal(monkeypatch, tmp_path) -> None:
    system_library, _bundled, loads = _install_newer_wins_fixture(
        monkeypatch,
        tmp_path,
        system_version=_api_version(2, 3),
        bundled_version=_api_version(2, 3),
    )

    assert prepare_custom_mpv_library() == system_library
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "system"
    assert loads == [str(system_library)]


def test_select_prefers_bundled_when_system_older(monkeypatch, tmp_path) -> None:
    (
        system_library,
        bundled_library,
        loads,
    ) = _install_newer_wins_fixture(
        monkeypatch,
        tmp_path,
        system_version=_api_version(2, 2),
        bundled_version=_api_version(2, 5),
    )

    assert prepare_custom_mpv_library() == bundled_library
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "builtin"
    # 主进程只加载内置一份,系统库完全未被加载,soname 命中无歧义
    assert loads == [str(bundled_library)]
    assert mpv_library.active_mpv_library_description() == (
        "应用内置",
        str(bundled_library),
    )


def test_select_prefers_system_when_bundled_unloadable(monkeypatch, tmp_path) -> None:
    system_library, _bundled, loads = _install_newer_wins_fixture(
        monkeypatch,
        tmp_path,
        system_version=_api_version(2, 2),
        bundled_version=None,
        bundled_exists=False,
    )

    # 内置不可加载(子进程探测失败):不比版本,直接用系统
    assert prepare_custom_mpv_library() == system_library
    assert loads == [str(system_library)]


def test_select_falls_back_to_system_when_bundled_load_fails(
    monkeypatch, tmp_path
) -> None:
    (
        system_library,
        bundled_library,
        loads,
    ) = _install_newer_wins_fixture(
        monkeypatch,
        tmp_path,
        system_version=_api_version(2, 2),
        bundled_version=_api_version(2, 5),
    )

    def flaky_cdll(path: str, **_kwargs: object):
        if Path(path) == bundled_library:
            raise OSError("undefined symbol")
        library = FakeCDLL(path)
        library._handle = len(loads) + 1
        loads.append(path)
        return library

    monkeypatch.setattr(ctypes, "CDLL", flaky_cdll)

    # 内置版本更新但主进程加载失败:回退系统
    assert prepare_custom_mpv_library() == system_library
    assert custom_mpv_library_diagnostics()["mpv_library_source"] == "system"
    assert loads == [str(system_library)]


def test_select_returns_none_when_both_unloadable(monkeypatch, tmp_path) -> None:
    _system, _bundled, loads = _install_newer_wins_fixture(
        monkeypatch, tmp_path, system_version=None, bundled_version=None
    )

    def broken_cdll(path: str, **_kwargs: object):
        raise OSError("cannot open shared object file")

    monkeypatch.setattr(ctypes, "CDLL", broken_cdll)

    assert prepare_custom_mpv_library() is None
    assert loads == []


def test_probe_mpv_client_api_version_via_fork_missing_file(tmp_path) -> None:
    assert (
        mpv_library._probe_mpv_client_api_version_via_fork(tmp_path / "missing.so")
        is None
    )


def test_probe_mpv_client_api_version_via_fork_library_without_symbol() -> None:
    # libc 存在但没有 mpv_client_api_version 符号
    libc_path = Path("/lib/x86_64-linux-gnu/libc.so.6")
    if not libc_path.is_file():
        pytest.skip("libc path not available on this platform")
    assert mpv_library._probe_mpv_client_api_version_via_fork(libc_path) is None


def test_probe_mpv_client_api_version_via_fork_reads_real_libmpv() -> None:
    candidates = [
        Path("/usr/local/lib/x86_64-linux-gnu/libmpv.so.2"),
        Path("/usr/lib/x86_64-linux-gnu/libmpv.so.2"),
    ]
    library = next((path for path in candidates if path.is_file()), None)
    if library is None:
        pytest.skip("system libmpv not available")

    value = mpv_library._probe_mpv_client_api_version_via_fork(library)

    assert value is not None
    assert (value >> 16, value & 0xFFFF) >= (2, 0)
    # 探测发生在子进程,主进程不应残留任何 libmpv 映射
    maps = Path("/proc/self/maps").read_text(encoding="utf-8", errors="ignore")
    assert "libmpv" not in maps


def test_mpv_widget_prepares_custom_library_before_import(qtbot, monkeypatch) -> None:
    from atv_player.player import mpv_widget as mpv_widget_module
    from atv_player.player.mpv_widget import MpvWidget

    widget = MpvWidget()
    qtbot.addWidget(widget)
    calls: list[str] = []
    monkeypatch.setattr(
        mpv_widget_module, "prepare_custom_mpv_library", lambda: calls.append("prepare")
    )

    class FakeMpvModule:
        @staticmethod
        def MPV(**_kwargs):
            return object()

    monkeypatch.setitem(sys.modules, "mpv", FakeMpvModule)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "atv_player.player.mpv_widget.resolve_mpv_ytdlp_path", lambda: ""
    )

    widget._create_player()

    assert calls == ["prepare"]
