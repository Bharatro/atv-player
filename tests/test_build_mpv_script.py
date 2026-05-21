from __future__ import annotations

import os
from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_mpv.sh"


def _write_fake_tool(fake_bin: Path, name: str) -> None:
    path = fake_bin / name
    if path.exists():
        return
    if name == "dirname":
        path.write_text("#!/bin/sh\n/usr/bin/dirname \"$@\"\n", encoding="utf-8")
    elif name == "mkdir":
        path.write_text("#!/bin/sh\n/bin/mkdir \"$@\"\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(path, 0o755)


def _write_fake_mpv_build_repo(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / ".git").mkdir()
    for name in (
        "rebuild",
        "install",
        "update",
        "use-mpv-release",
        "use-ffmpeg-release",
        "use-mpv-master",
        "use-ffmpeg-master",
    ):
        path = workdir / name
        path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        os.chmod(path, 0o755)


def _run_script(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    for tool in ("git", "meson", "ninja", "pkg-config", "sudo", "dirname"):
        _write_fake_tool(fake_bin, tool)
    merged_env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        **(env or {}),
    }
    return subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), *args],
        cwd=tmp_path,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_build_mpv_script_requires_nasm_unless_disable_x86asm(tmp_path: Path) -> None:
    result = _run_script(
        tmp_path,
        "--dry-run",
        "--no-install",
        env={"PATH": str(tmp_path / "fake-bin")},
    )

    assert result.returncode == 1
    assert "nasm not found or too old" in result.stderr
    assert "--disable-x86asm" in result.stderr


def test_build_mpv_script_auto_installs_liblua52_dev_when_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "apt-get", "dirname"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *lua*|*luajit*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "+ sudo apt-get install -y liblua5.2-dev" in result.stdout


def test_build_mpv_script_fails_when_lua_dev_runtime_missing_and_apt_get_unavailable(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "dirname"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *lua*|*luajit*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing required Lua development package" in result.stderr
    assert "liblua5.2-dev" in result.stderr


def test_build_mpv_script_auto_installs_libxpresent_dev_for_x11_sessions(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "apt-get", "dirname"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *xpresent*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "XDG_SESSION_TYPE": "x11",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "+ sudo apt-get install -y libxpresent-dev" in result.stdout


def test_build_mpv_script_auto_installs_hardware_decode_dev_packages_when_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "apt-get", "dirname"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *libva*|*vdpau*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "+ sudo apt-get install -y libva-dev libvdpau-dev" in result.stdout


def test_build_mpv_script_fails_when_hardware_decode_dev_packages_missing_and_apt_get_unavailable(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "dirname", "mkdir"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *libva*|*vdpau*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing required hardware decode development packages" in result.stderr
    assert "libva-dev" in result.stderr
    assert "libvdpau-dev" in result.stderr


def test_build_mpv_script_auto_installs_nvcodec_headers_when_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "apt-get", "dirname"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *ffnvcodec*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "+ sudo apt-get install -y libffmpeg-nvenc-dev" in result.stdout


def test_build_mpv_script_fails_when_nvcodec_headers_missing_and_apt_get_unavailable(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "dirname", "mkdir"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *ffnvcodec*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing required NVIDIA codec development package" in result.stderr
    assert "libffmpeg-nvenc-dev" in result.stderr


def test_build_mpv_script_fails_when_x11_session_needs_xpresent_and_apt_get_unavailable(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for tool in ("git", "meson", "ninja", "sudo", "nasm", "dirname", "mkdir"):
        _write_fake_tool(fake_bin, tool)
    (fake_bin / "pkg-config").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *xpresent*) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "pkg-config", 0o755)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_PATH), "--dry-run", "--no-install"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(fake_bin),
            "XDG_SESSION_TYPE": "x11",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing required X11 development package" in result.stderr
    assert "libxpresent-dev" in result.stderr


def test_build_mpv_script_writes_disable_x86asm_option_and_uses_release_track_by_default(tmp_path: Path) -> None:
    workdir = tmp_path / "mpv-build"
    _write_fake_mpv_build_repo(workdir)

    result = _run_script(
        tmp_path,
        "--workdir",
        str(workdir),
        "--disable-x86asm",
        "--dry-run",
        "--no-install",
        "--jobs",
        "8",
    )

    assert result.returncode == 0
    assert (workdir / "ffmpeg_options").read_text(encoding="utf-8") == "--disable-x86asm\n"
    assert "+ ./use-mpv-release" in result.stdout
    assert "+ ./use-ffmpeg-release" in result.stdout
    assert "+ ./rebuild -j8" in result.stdout


def test_build_mpv_script_can_switch_to_master_track(tmp_path: Path) -> None:
    workdir = tmp_path / "mpv-build"
    _write_fake_mpv_build_repo(workdir)

    result = _run_script(
        tmp_path,
        "--workdir",
        str(workdir),
        "--disable-x86asm",
        "--dry-run",
        "--no-install",
        "--master",
    )

    assert result.returncode == 0
    assert "+ ./use-mpv-master" in result.stdout
    assert "+ ./use-ffmpeg-master" in result.stdout


def test_build_mpv_script_clears_pyenv_version_during_rebuild(tmp_path: Path) -> None:
    workdir = tmp_path / "mpv-build"
    _write_fake_mpv_build_repo(workdir)
    (workdir / "rebuild").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'PYENV_VERSION=%s\\n' \"${PYENV_VERSION:-}\" > rebuild-env.log\n",
        encoding="utf-8",
    )
    os.chmod(workdir / "rebuild", 0o755)

    result = _run_script(
        tmp_path,
        "--workdir",
        str(workdir),
        "--disable-x86asm",
        "--no-install",
        env={"PYENV_VERSION": "3.12"},
    )

    assert result.returncode == 0
    assert (workdir / "rebuild-env.log").read_text(encoding="utf-8") == "PYENV_VERSION=\n"


def test_build_mpv_script_runs_ldconfig_after_install(tmp_path: Path) -> None:
    workdir = tmp_path / "mpv-build"
    _write_fake_mpv_build_repo(workdir)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    sudo_log = tmp_path / "sudo.log"
    (fake_bin / "sudo").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'sudo:%s\\n' \"$*\" >> \"" + str(sudo_log) + "\"\n"
        "if [[ \"$1\" == \"./install\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == \"ldconfig\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    os.chmod(fake_bin / "sudo", 0o755)

    result = _run_script(
        tmp_path,
        "--workdir",
        str(workdir),
        "--disable-x86asm",
    )

    assert result.returncode == 0
    assert sudo_log.read_text(encoding="utf-8").splitlines() == [
        "sudo:./install",
        "sudo:ldconfig",
    ]


def test_build_mpv_script_prints_post_install_verification_commands(tmp_path: Path) -> None:
    workdir = tmp_path / "mpv-build"
    _write_fake_mpv_build_repo(workdir)

    result = _run_script(
        tmp_path,
        "--workdir",
        str(workdir),
        "--disable-x86asm",
        "--dry-run",
    )

    assert result.returncode == 0
    assert "hash -r" in result.stdout
    assert "which mpv" in result.stdout
    assert "/usr/local/bin/mpv --version" in result.stdout
    assert "ldconfig -p | grep libmpv" in result.stdout
