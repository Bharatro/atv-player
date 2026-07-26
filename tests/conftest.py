import os

import pytest
from PySide6.QtWidgets import QApplication

import atv_player.danmaku.cache as danmaku_cache_module

# Force a headless Qt backend so pytest-qt does not depend on a live X server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolate_danmaku_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        danmaku_cache_module,
        "app_cache_dir",
        lambda: tmp_path / "app-cache",
    )


@pytest.fixture(autouse=True)
def cleanup_qt_top_level_widgets(request: pytest.FixtureRequest):
    yield

    if "qtbot" not in request.fixturenames:
        return
    app = QApplication.instance()
    if app is None:
        return

    widgets = list(app.topLevelWidgets())
    for widget in widgets:
        if hasattr(widget, "_quit_requested"):
            widget._quit_requested = True
        if hasattr(widget, "_app_quit_requested"):
            widget._app_quit_requested = True
    for widget in widgets:
        widget.close()
