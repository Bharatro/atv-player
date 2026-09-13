from pathlib import Path

from atv_player.local_playback_history import LocalPlaybackHistoryRepository


def _make_repo(tmp_path: Path) -> LocalPlaybackHistoryRepository:
    return LocalPlaybackHistoryRepository(tmp_path / "app.db")


def _payload(episode: int = 5, position_ms: int = 65000) -> dict:
    return {
        "vodName": "同系列第二季",
        "episode": episode,
        "episodeUrl": "http://127.0.0.1:2323/cenc/abc/video.mp4",
        "position": position_ms,
        "duration": 58000,
        "speed": 1.0,
    }


def test_get_history_matches_exact_vod_id(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save_history("spider_plugin", "7680883072278989849", _payload(), source_key="683", source_name="短剧百科")

    record = repo.get_history("spider_plugin", "7680883072278989849", source_key="683")

    assert record is not None
    assert record.episode == 5
    assert record.position == 65000


def test_get_history_falls_back_to_same_plugin_name_and_rekeys_row(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save_history("spider_plugin", "7680883072278989849", _payload(), source_key="683", source_name="短剧百科")

    record = repo.get_history(
        "spider_plugin",
        "mj:7680883072278989849",
        source_key="683",
        vod_name="同系列第二季",
    )

    assert record is not None
    assert record.episode == 5

    # 兜底命中后历史行重键到当前 vod_id:新形态精确可查,旧形态不再命中
    assert repo.get_history("spider_plugin", "mj:7680883072278989849", source_key="683") is not None
    assert repo.get_history("spider_plugin", "7680883072278989849", source_key="683") is None


def test_get_history_without_vod_name_does_not_fall_back(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save_history("spider_plugin", "bare", _payload(), source_key="683")

    assert repo.get_history("spider_plugin", "mj:bare", source_key="683") is None


def test_get_history_name_fallback_requires_same_name(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save_history("spider_plugin", "bare", _payload(), source_key="683")

    assert repo.get_history("spider_plugin", "mj:bare", source_key="683", vod_name="别的作品") is None


def test_get_history_name_fallback_skips_other_source_kinds(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save_history("browse", "/ Movies / Movie", _payload(), source_key="csp_AList")

    assert (
        repo.get_history("browse", "/ Movies / Other", source_key="csp_AList", vod_name="同系列第二季")
        is None
    )
