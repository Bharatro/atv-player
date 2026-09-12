from pathlib import Path

from atv_player.player.mpv_user_config import (
    LOOSE_SHADER_PRESET_NAME,
    discover_shader_presets,
    resolve_mpv_config_dir,
)


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_resolve_mpv_config_dir_returns_none_without_conf() -> None:
    assert resolve_mpv_config_dir([Path("/nonexistent")]) is None


def test_resolve_mpv_config_dir_prefers_first_dir_with_conf(tmp_path: Path) -> None:
    user_dir = tmp_path / "mpv"
    app_dir = tmp_path / "app"
    _write(app_dir / "mpv.conf")

    assert resolve_mpv_config_dir([user_dir, app_dir]) == app_dir

    _write(user_dir / "mpv.conf")
    assert resolve_mpv_config_dir([user_dir, app_dir]) == user_dir


def test_discover_shader_presets_returns_empty_without_shader_dir(tmp_path: Path) -> None:
    assert discover_shader_presets([tmp_path / "mpv"]) == []
    _write(tmp_path / "mpv" / "mpv.conf")
    assert discover_shader_presets([tmp_path / "mpv"]) == []


def test_discover_shader_presets_from_subdirs_and_loose_files(tmp_path: Path) -> None:
    shaders_dir = tmp_path / "mpv" / "shaders"
    _write(shaders_dir / "anime4k-a-high" / "Restore_CNN_S.glsl")
    _write(shaders_dir / "anime4k-a-high" / "Restore_CNN_M.glsl")
    _write(shaders_dir / "anime4k-b-high" / "Restore_CNN_VL.glsl")
    _write(shaders_dir / "loose.glsl")
    _write(shaders_dir / "loose.hook")
    _write(shaders_dir / "readme.txt")

    presets = discover_shader_presets([tmp_path / "mpv"])

    assert [preset.name for preset in presets] == [
        "anime4k-a-high",
        "anime4k-b-high",
        LOOSE_SHADER_PRESET_NAME,
    ]
    assert presets[0].shader_files == (
        str(shaders_dir / "anime4k-a-high" / "Restore_CNN_M.glsl"),
        str(shaders_dir / "anime4k-a-high" / "Restore_CNN_S.glsl"),
    )
    assert presets[2].shader_files == (
        str(shaders_dir / "loose.glsl"),
        str(shaders_dir / "loose.hook"),
    )


def test_discover_shader_presets_skips_subdir_without_shader_files(tmp_path: Path) -> None:
    shaders_dir = tmp_path / "mpv" / "shaders"
    _write(shaders_dir / "notes" / "readme.txt")

    assert discover_shader_presets([tmp_path / "mpv"]) == []


def test_discover_shader_presets_dedupes_same_name_across_search_dirs(tmp_path: Path) -> None:
    user_shaders = tmp_path / "mpv" / "shaders"
    app_shaders = tmp_path / "app" / "shaders"
    _write(user_shaders / "anime4k" / "user.glsl")
    _write(app_shaders / "anime4k" / "app.glsl")
    _write(app_shaders / "extra.glsl")

    presets = discover_shader_presets([tmp_path / "mpv", tmp_path / "app"])

    assert [preset.name for preset in presets] == ["anime4k", LOOSE_SHADER_PRESET_NAME]
    assert presets[0].shader_files == (str(user_shaders / "anime4k" / "user.glsl"),)
    assert presets[1].shader_files == (str(app_shaders / "extra.glsl"),)
