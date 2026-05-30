from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DependencyInstallResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str


class DependencyInstallError(RuntimeError):
    def __init__(self, message: str, *, command: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.command = command


def install_dependency(
    component: str, *, timeout: float = 600
) -> DependencyInstallResult:
    command = build_dependency_install_command(component)
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DependencyInstallError(
            f"{component} 安装超时，请稍后重试。", command=command
        ) from exc
    except OSError as exc:
        raise DependencyInstallError(
            f"{component} 安装命令启动失败：{exc}", command=command
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if detail:
            raise DependencyInstallError(
                f"{component} 安装失败：{detail}", command=command
            )
        raise DependencyInstallError(
            f"{component} 安装失败，退出码 {completed.returncode}。", command=command
        )
    return DependencyInstallResult(
        command=command,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def build_dependency_install_command(component: str) -> tuple[str, ...]:
    label = component.strip()
    if label == "yt-dlp":
        return _build_ytdlp_install_command()
    if label == "Node.js":
        return _build_nodejs_install_command()
    raise DependencyInstallError(f"不支持安装 {component}")


def _build_ytdlp_install_command() -> tuple[str, ...]:
    system = platform.system()
    if system == "Windows":
        winget = _required_tool("winget", "未找到 winget，无法自动安装 yt-dlp。")
        return (
            winget,
            "install",
            "--id",
            "yt-dlp.yt-dlp",
            "--exact",
            "--accept-package-agreements",
            "--accept-source-agreements",
        )
    if system == "Darwin":
        brew = _required_tool("brew", "未找到 Homebrew，无法自动安装 yt-dlp。")
        return (brew, "install", "yt-dlp")

    pipx = shutil.which("pipx")
    if pipx:
        return (pipx, "install", "yt-dlp")
    python = shutil.which("python3") or sys.executable
    if python:
        return (python, "-m", "pip", "install", "--user", "-U", "yt-dlp")
    raise DependencyInstallError("未找到 pipx 或 Python，无法自动安装 yt-dlp。")


def _build_nodejs_install_command() -> tuple[str, ...]:
    system = platform.system()
    if system == "Windows":
        winget = _required_tool("winget", "未找到 winget，无法自动安装 Node.js。")
        return (
            winget,
            "install",
            "--id",
            "OpenJS.NodeJS.LTS",
            "--exact",
            "--accept-package-agreements",
            "--accept-source-agreements",
        )
    if system == "Darwin":
        brew = _required_tool("brew", "未找到 Homebrew，无法自动安装 Node.js。")
        return (brew, "install", "node")

    package_commands: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("apt-get", ("apt-get", "install", "-y", "nodejs", "npm")),
        ("dnf", ("dnf", "install", "-y", "nodejs", "npm")),
        ("yum", ("yum", "install", "-y", "nodejs", "npm")),
        ("pacman", ("pacman", "-S", "--needed", "--noconfirm", "nodejs", "npm")),
        ("zypper", ("zypper", "install", "-y", "nodejs", "npm")),
    )
    for tool, command in package_commands:
        resolved = shutil.which(tool)
        if resolved:
            return _with_privilege((resolved, *command[1:]))
    raise DependencyInstallError("未找到可用的系统包管理器，无法自动安装 Node.js。")


def _with_privilege(command: tuple[str, ...]) -> tuple[str, ...]:
    if getattr(os, "geteuid", lambda: 1)() == 0:
        return command
    pkexec = shutil.which("pkexec")
    if pkexec:
        return (pkexec, *command)
    sudo = shutil.which("sudo")
    if sudo:
        return (sudo, *command)
    raise DependencyInstallError(
        "安装 Node.js 需要管理员权限，但未找到 pkexec 或 sudo。"
    )


def _required_tool(name: str, message: str) -> str:
    path = shutil.which(name)
    if not path:
        raise DependencyInstallError(message)
    return path
