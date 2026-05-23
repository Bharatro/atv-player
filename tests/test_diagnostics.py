from __future__ import annotations

import importlib.metadata
from pathlib import Path

from atv_player import diagnostics


def test_resolve_app_version_prefers_running_application_version(monkeypatch) -> None:
    class FakeApp:
        def applicationVersion(self) -> str:
            return "0.8.2"

        def processEvents(self) -> None:
            return None

    monkeypatch.setattr(diagnostics.QApplication, "instance", lambda: FakeApp())
    monkeypatch.setattr(diagnostics.importlib.metadata, "version", lambda name: "0.1.0")

    assert diagnostics.resolve_app_version() == "0.8.2"


def test_resolve_app_version_falls_back_to_pyproject_for_source_run(
    monkeypatch, tmp_path
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        'name = "atv-player"\nversion = "0.8.2"\n', encoding="utf-8"
    )

    def raise_package_not_found(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(diagnostics.QApplication, "instance", lambda: None)
    monkeypatch.setattr(
        diagnostics.importlib.metadata, "version", raise_package_not_found
    )
    monkeypatch.setattr(diagnostics, "_PYPROJECT_PATH", Path(pyproject_path))

    assert diagnostics.resolve_app_version() == "0.8.2"


def test_resolve_app_version_prefers_bundled_build_version(
    monkeypatch, tmp_path
) -> None:
    version_path = tmp_path / "_build_version.txt"
    version_path.write_text("1.2.3", encoding="utf-8")

    monkeypatch.setattr(diagnostics.QApplication, "instance", lambda: None)
    monkeypatch.setattr(diagnostics.importlib.metadata, "version", lambda name: "0.1.0")
    monkeypatch.setattr(diagnostics, "_BUNDLED_VERSION_PATH", Path(version_path))

    assert diagnostics.resolve_app_version() == "1.2.3"


def test_collect_system_info_entries_adds_links_for_all_non_platform_rows(
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics, "resolve_app_version", lambda: "0.8.2")
    monkeypatch.setattr(diagnostics.platform, "python_version", lambda: "3.12.8")
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(diagnostics.platform, "version", lambda: "#1 SMP")
    monkeypatch.setattr(diagnostics.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(diagnostics, "pyside_version", "6.8.1")
    monkeypatch.setattr(diagnostics, "resolve_system_ytdlp_path", lambda: "yt-dlp")

    versions = iter(["20.11.1", "0.39", "7.1", "2026.05.17"])
    monkeypatch.setattr(
        diagnostics, "_read_command_version", lambda command, parser: next(versions)
    )

    entries = diagnostics.collect_system_info_entries()

    assert entries == (
        diagnostics.SystemInfoEntry(
            "atv-player",
            "0.8.2",
            "https://github.com/power721/atv-player/releases/latest",
        ),
        diagnostics.SystemInfoEntry(
            "Python", "3.12.8", "https://www.python.org/downloads/"
        ),
        diagnostics.SystemInfoEntry(
            "PySide6", "6.8.1", "https://doc.qt.io/qtforpython-6/"
        ),
        diagnostics.SystemInfoEntry(
            "Node.js", "20.11.1", "https://nodejs.org/en/download"
        ),
        diagnostics.SystemInfoEntry("mpv", "0.39", "https://mpv.io/installation/"),
        diagnostics.SystemInfoEntry(
            "ffmpeg", "7.1", "https://www.ffmpeg.org/download.html"
        ),
        diagnostics.SystemInfoEntry(
            "yt-dlp", "2026.05.17", "https://github.com/yt-dlp/yt-dlp/releases/latest"
        ),
        diagnostics.SystemInfoEntry("Platform", "Linux 6.8.0 (x86_64)"),
    )


def test_resolve_platform_display_value_formats_windows_version_and_arch(
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.platform, "release", lambda: "11")
    monkeypatch.setattr(diagnostics.platform, "version", lambda: "10.0.22631")
    monkeypatch.setattr(diagnostics.platform, "machine", lambda: "AMD64")

    assert (
        diagnostics._resolve_platform_display_value() == "Windows 11 10.0.22631 (AMD64)"
    )


def test_parse_nodejs_version_strips_leading_v() -> None:
    assert diagnostics._parse_nodejs_version("v20.11.1\n") == "20.11.1"
