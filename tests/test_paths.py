from pathlib import Path

from atv_player import paths


def test_app_data_dir_scopes_generic_data_location_to_app_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        paths.QStandardPaths,
        "writableLocation",
        lambda location: str(tmp_path / "share"),
    )

    resolved = paths.app_data_dir()

    assert resolved == tmp_path / "share" / paths.APP_NAME
    assert resolved.is_dir()


def test_app_data_dir_keeps_existing_app_name_suffix(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        paths.QStandardPaths,
        "writableLocation",
        lambda location: str(tmp_path / "share" / paths.APP_NAME),
    )

    resolved = paths.app_data_dir()

    assert resolved == tmp_path / "share" / paths.APP_NAME
    assert resolved.is_dir()


def test_app_cache_dir_scopes_generic_cache_location_to_app_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        paths.QStandardPaths,
        "writableLocation",
        lambda location: str(tmp_path / "cache"),
    )

    resolved = paths.app_cache_dir()

    assert resolved == tmp_path / "cache" / paths.APP_NAME
    assert resolved.is_dir()
