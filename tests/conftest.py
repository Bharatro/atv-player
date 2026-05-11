import os

import pytest

import atv_player.danmaku.cache as danmaku_cache_module

# Force a headless Qt backend so pytest-qt does not depend on a live X server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolate_danmaku_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
