from __future__ import annotations

import subprocess
import sys

import pytest

from atv_player import dependency_installer


def test_build_ytdlp_install_command_uses_winget_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(dependency_installer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        dependency_installer.shutil,
        "which",
        lambda name: f"C:/Windows/System32/{name}.exe" if name == "winget" else None,
    )

    assert dependency_installer.build_dependency_install_command("yt-dlp") == (
        "C:/Windows/System32/winget.exe",
        "install",
        "--id",
        "yt-dlp.yt-dlp",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    )


def test_build_nodejs_install_command_uses_winget_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(dependency_installer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        dependency_installer.shutil,
        "which",
        lambda name: f"C:/Windows/System32/{name}.exe" if name == "winget" else None,
    )

    assert dependency_installer.build_dependency_install_command("Node.js") == (
        "C:/Windows/System32/winget.exe",
        "install",
        "--id",
        "OpenJS.NodeJS.LTS",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    )


def test_build_ytdlp_install_command_uses_pipx_on_linux(monkeypatch) -> None:
    monkeypatch.setattr(dependency_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        dependency_installer.shutil,
        "which",
        lambda name: "/usr/bin/pipx" if name == "pipx" else None,
    )

    assert dependency_installer.build_dependency_install_command("yt-dlp") == (
        "/usr/bin/pipx",
        "install",
        "yt-dlp",
    )


def test_build_ytdlp_install_command_falls_back_to_user_pip_on_linux(
    monkeypatch,
) -> None:
    monkeypatch.setattr(dependency_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(dependency_installer.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        dependency_installer,
        "sys",
        type("Sys", (), {"executable": sys.executable}),
    )

    assert dependency_installer.build_dependency_install_command("yt-dlp") == (
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "-U",
        "yt-dlp",
    )


def test_build_nodejs_install_command_uses_pkexec_for_linux_package_manager(
    monkeypatch,
) -> None:
    monkeypatch.setattr(dependency_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(dependency_installer.os, "geteuid", lambda: 1000)

    def fake_which(name: str) -> str | None:
        return {
            "apt-get": "/usr/bin/apt-get",
            "pkexec": "/usr/bin/pkexec",
        }.get(name)

    monkeypatch.setattr(dependency_installer.shutil, "which", fake_which)

    assert dependency_installer.build_dependency_install_command("Node.js") == (
        "/usr/bin/pkexec",
        "/usr/bin/apt-get",
        "install",
        "-y",
        "nodejs",
        "npm",
    )


def test_install_dependency_raises_error_with_command_output(monkeypatch) -> None:
    monkeypatch.setattr(
        dependency_installer,
        "build_dependency_install_command",
        lambda component: ("installer", component),
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="boom")

    monkeypatch.setattr(dependency_installer.subprocess, "run", fake_run)

    with pytest.raises(dependency_installer.DependencyInstallError, match="boom"):
        dependency_installer.install_dependency("yt-dlp")
