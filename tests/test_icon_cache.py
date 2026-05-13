from pathlib import Path

from PySide6.QtGui import QIcon

import atv_player.ui.icon_cache as icon_cache_module


def test_load_icon_caches_qicon_instances(monkeypatch) -> None:
    icon_cache_module.clear_icon_cache()
    calls: list[str] = []

    class RecordingIcon(QIcon):
        def __init__(self, path: str) -> None:
            calls.append(path)
            super().__init__()

    monkeypatch.setattr(icon_cache_module, "QIcon", RecordingIcon)

    first = icon_cache_module.load_icon(Path("/tmp/icon.svg"))
    second = icon_cache_module.load_icon("/tmp/icon.svg")

    assert first is second
    assert calls == ["/tmp/icon.svg"]


def test_player_sidebar_toggle_icons_share_grayscale_asset_style() -> None:
    icons_dir = Path(__file__).resolve().parent.parent / "src" / "atv_player" / "icons"

    queue_svg = (icons_dir / "queue.svg").read_text(encoding="utf-8")
    info_svg = (icons_dir / "info.svg").read_text(encoding="utf-8")
    logs_svg = (icons_dir / "logs.svg").read_text(encoding="utf-8")

    for svg in (queue_svg, info_svg, logs_svg):
        assert 'fill="#c0c0c0"' in svg
        assert "currentColor" not in svg


def test_player_log_icon_uses_terminal_window_shape() -> None:
    icons_dir = Path(__file__).resolve().parent.parent / "src" / "atv_player" / "icons"
    logs_svg = (icons_dir / "logs.svg").read_text(encoding="utf-8")

    assert '<path d="M4 5h16v14H4z"/>' in logs_svg
    assert '<path d="M7 9l2 2-2 2"/>' in logs_svg
    assert '<path d="M11 13h5v-2h-5z"/>' in logs_svg
