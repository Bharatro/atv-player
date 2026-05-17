from __future__ import annotations

from pathlib import Path

import importlib.metadata

from atv_player import diagnostics


def test_resolve_app_version_prefers_running_application_version(monkeypatch) -> None:
    class FakeApp:
        def applicationVersion(self) -> str:
            return "0.8.2"

    monkeypatch.setattr(diagnostics.QApplication, "instance", lambda: FakeApp())
    monkeypatch.setattr(diagnostics.importlib.metadata, "version", lambda name: "0.1.0")

    assert diagnostics.resolve_app_version() == "0.8.2"


def test_resolve_app_version_falls_back_to_pyproject_for_source_run(monkeypatch, tmp_path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('name = "atv-player"\nversion = "0.8.2"\n', encoding="utf-8")

    def raise_package_not_found(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(diagnostics.QApplication, "instance", lambda: None)
    monkeypatch.setattr(diagnostics.importlib.metadata, "version", raise_package_not_found)
    monkeypatch.setattr(diagnostics, "_PYPROJECT_PATH", Path(pyproject_path))

    assert diagnostics.resolve_app_version() == "0.8.2"
