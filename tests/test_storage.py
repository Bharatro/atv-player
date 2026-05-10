from atv_player.storage import SettingsRepository


def test_settings_repository_loads_new_danmaku_render_defaults(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    config = repo.load_config()

    assert config.preferred_danmaku_render_mode == "static"
    assert config.preferred_danmaku_color_mode == "uniform"
    assert config.preferred_danmaku_uniform_color == "#FFFFFF"
    assert config.preferred_danmaku_position_preset == "top"


def test_settings_repository_persists_new_danmaku_render_settings(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.preferred_danmaku_render_mode = "mixed"
    config.preferred_danmaku_color_mode = "source"
    config.preferred_danmaku_uniform_color = "#00FF00"
    config.preferred_danmaku_position_preset = "mid_upper"

    repo.save_config(config)

    reloaded = repo.load_config()

    assert reloaded.preferred_danmaku_render_mode == "mixed"
    assert reloaded.preferred_danmaku_color_mode == "source"
    assert reloaded.preferred_danmaku_uniform_color == "#00FF00"
    assert reloaded.preferred_danmaku_position_preset == "mid_upper"
