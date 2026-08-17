import ctypes
import os
import sys
from pathlib import Path

import pytest

from atv_player.player import mpv_library
from atv_player.player.mpv_library import (
    custom_mpv_library_diagnostics,
    custom_mpv_library_search_dirs,
    prepare_custom_mpv_library,
    resolve_custom_mpv_library,
)


@pytest.fixture(autouse=True)
def _reset_state():
    mpv_library._reset_custom_mpv_library_state()
    yield
    mpv_library._reset_custom_mpv_library_state()


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
        if not Path(path).is_file():
            raise OSError(f"cannot open shared object file: {path}")


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
    # 加载失败后不再前插 PATH,也不再重试
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
