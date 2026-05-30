from __future__ import annotations


def test_resolve_mpv_ytdlp_path_prefers_explicit_env_path(monkeypatch, tmp_path) -> None:
    from atv_player.player import ytdlp_runtime

    tool_path = tmp_path / "yt-dlp"
    tool_path.write_text("#!/bin/sh\n", encoding="utf-8")
    tool_path.chmod(0o755)

    monkeypatch.setenv("ATV_YTDLP_PATH", str(tool_path))
    monkeypatch.setattr(ytdlp_runtime.shutil, "which", lambda name: None)

    assert ytdlp_runtime.resolve_mpv_ytdlp_path() == str(tool_path)
    assert ytdlp_runtime.resolve_system_ytdlp_path() == str(tool_path)


def test_resolve_mpv_ytdlp_path_falls_back_to_system_path(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_PATH", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", "/home/demo/project/.venv/bin/python")
    monkeypatch.setattr(ytdlp_runtime, "_is_usable_file", lambda path: str(path) == "/usr/bin/yt-dlp")

    assert ytdlp_runtime.resolve_mpv_ytdlp_path() == "/usr/bin/yt-dlp"
    assert ytdlp_runtime.resolve_system_ytdlp_path() == "/usr/bin/yt-dlp"


def test_resolve_system_ytdlp_path_skips_current_venv_bin(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_PATH", raising=False)
    monkeypatch.setenv("PATH", "/home/demo/project/.venv/bin:/usr/local/bin")
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", "/home/demo/project/.venv/bin/python")
    monkeypatch.setattr(
        ytdlp_runtime,
        "_is_usable_file",
        lambda path: str(path) in {"/home/demo/project/.venv/bin/yt-dlp", "/usr/local/bin/yt-dlp"},
    )

    assert ytdlp_runtime.resolve_system_ytdlp_path() == "/usr/local/bin/yt-dlp"


def test_resolve_system_ytdlp_path_finds_user_local_bin_after_user_pip_install(
    monkeypatch,
) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_PATH", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(
        ytdlp_runtime.sys,
        "executable",
        "/home/demo/project/.venv/bin/python",
    )
    monkeypatch.setattr(
        ytdlp_runtime.Path,
        "home",
        lambda: ytdlp_runtime.Path("/home/demo"),
    )
    monkeypatch.setattr(
        ytdlp_runtime,
        "_is_usable_file",
        lambda path: str(path) == "/home/demo/.local/bin/yt-dlp",
    )
    monkeypatch.setattr(ytdlp_runtime.shutil, "which", lambda name: None)

    assert ytdlp_runtime.resolve_system_ytdlp_path() == "/home/demo/.local/bin/yt-dlp"


def test_resolve_mpv_ytdlp_path_returns_empty_when_no_candidate_exists(
    monkeypatch,
) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_PATH", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(
        ytdlp_runtime.sys,
        "executable",
        "/home/demo/project/.venv/bin/python",
    )
    monkeypatch.setattr(
        ytdlp_runtime.Path,
        "home",
        lambda: ytdlp_runtime.Path("/home/demo"),
    )
    monkeypatch.setattr(ytdlp_runtime.shutil, "which", lambda name: None)

    assert ytdlp_runtime.resolve_mpv_ytdlp_path() == ""
    assert ytdlp_runtime.resolve_system_ytdlp_path() == ""


def test_build_ytdlp_command_args_prefers_browser_cookies(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.setenv("ATV_YTDLP_COOKIES_FROM_BROWSER", "chrome")

    assert ytdlp_runtime.build_ytdlp_command_args() == [
        "--cookies-from-browser",
        "chrome",
        "--remote-components",
        "ejs:github",
    ]


def test_build_ytdlp_command_args_defaults_to_no_browser_cookies(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_COOKIES_FROM_BROWSER", raising=False)

    assert ytdlp_runtime.build_ytdlp_command_args(cookie_browser="") == []


def test_resolve_mpv_ytdl_raw_options_uses_explicit_browser_value() -> None:
    from atv_player.player import ytdlp_runtime

    assert ytdlp_runtime.resolve_mpv_ytdl_raw_options(cookie_browser="edge") == (
        "cookies-from-browser=edge,remote-components=ejs:github"
    )


def test_build_ytdlp_command_args_uses_explicit_browser_value(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_COOKIES_FROM_BROWSER", raising=False)

    assert ytdlp_runtime.build_ytdlp_command_args(cookie_browser="firefox") == [
        "--cookies-from-browser",
        "firefox",
        "--remote-components",
        "ejs:github",
    ]


def test_build_mpv_ytdl_raw_options_defaults_to_empty_without_browser(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_COOKIES_FROM_BROWSER", raising=False)

    assert ytdlp_runtime.resolve_mpv_ytdl_raw_options() == ""


def test_build_ytdlp_command_args_allows_disabling_default_browser_cookies(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.setenv("ATV_YTDLP_COOKIES_FROM_BROWSER", "off")

    assert ytdlp_runtime.build_ytdlp_command_args() == []
