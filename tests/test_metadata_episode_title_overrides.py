from pathlib import Path

from atv_player.metadata.episode_title_overrides import (
    EpisodeTitleOverrideRepository,
    apply_episode_title_overrides,
    episode_override_item_key,
)
from atv_player.models import PlayItem


def test_item_key_prefers_play_id_then_url_then_path_basename() -> None:
    assert episode_override_item_key(PlayItem(title="a", url="", play_id="pid1")) == "pid1"
    assert episode_override_item_key(PlayItem(title="a", url="http://m/1.mp4", play_id="")) == "http://m/1.mp4"
    # url wins over original_url/path when present
    assert (
        episode_override_item_key(
            PlayItem(title="a", url="http://m/1.mp4", original_url="x", path="/d/1.mp4")
        )
        == "http://m/1.mp4"
    )
    # path basename fallback when no ids
    assert episode_override_item_key(PlayItem(title="a", url="", path="/some/dir/EP01.mp4")) == "EP01.mp4"
    # title last resort
    assert episode_override_item_key(PlayItem(title="裸标题", url="")) == "裸标题"


def test_override_repository_round_trip_upsert_load_delete(tmp_path: Path) -> None:
    repo = EpisodeTitleOverrideRepository(tmp_path / "app.db")

    repo.upsert(
        source_kind="browse",
        source_key="",
        vod_id="1$/media/信号$1",
        item_key="http://m/08-03.mp4",
        display_title="08-03 第1期上：心动",
    )

    overrides = repo.load_for_session(
        source_kind="browse", source_key="", vod_id="1$/media/信号$1"
    )
    assert overrides == {"http://m/08-03.mp4": "08-03 第1期上：心动"}

    # upsert overwrites
    repo.upsert(
        source_kind="browse",
        source_key="",
        vod_id="1$/media/信号$1",
        item_key="http://m/08-03.mp4",
        display_title="08-03 改过的标题",
    )
    assert repo.load_for_session(
        source_kind="browse", source_key="", vod_id="1$/media/信号$1"
    ) == {"http://m/08-03.mp4": "08-03 改过的标题"}

    repo.delete(
        source_kind="browse", source_key="", vod_id="1$/media/信号$1", item_key="http://m/08-03.mp4"
    )
    assert repo.load_for_session(source_kind="browse", source_key="", vod_id="1$/media/信号$1") == {}


def test_override_repository_isolates_by_vod_and_source(tmp_path: Path) -> None:
    repo = EpisodeTitleOverrideRepository(tmp_path / "app.db")
    repo.upsert(source_kind="browse", source_key="", vod_id="v1", item_key="k1", display_title="t1")
    repo.upsert(source_kind="browse", source_key="", vod_id="v2", item_key="k1", display_title="t2")

    assert repo.load_for_session(source_kind="browse", source_key="", vod_id="v1") == {"k1": "t1"}
    assert repo.load_for_session(source_kind="browse", source_key="", vod_id="v2") == {"k1": "t2"}
    # empty vod_id never loads
    assert repo.load_for_session(source_kind="browse", source_key="", vod_id="") == {}


def test_override_repository_ignores_empty_inputs(tmp_path: Path) -> None:
    repo = EpisodeTitleOverrideRepository(tmp_path / "app.db")
    repo.upsert(source_kind="browse", source_key="", vod_id="", item_key="k", display_title="t")
    repo.upsert(source_kind="browse", source_key="", vod_id="v", item_key="", display_title="t")
    repo.upsert(source_kind="browse", source_key="", vod_id="v", item_key="k", display_title="")
    assert repo.load_for_session(source_kind="browse", source_key="", vod_id="v") == {}


def test_apply_overrides_stamps_manual_source_and_wins_over_auto(tmp_path: Path) -> None:
    playlist = [
        PlayItem(title="20260803.第1期上.mp4", url="http://m/1.mp4", episode_display_title="第1集 自动", episode_title_source="tmdb"),
        PlayItem(title="20260803.第1期中.mp4", url="http://m/2.mp4"),
    ]
    overrides = {"http://m/1.mp4": "08-03 第1期上：又争又抢"}

    changed = apply_episode_title_overrides(playlist, overrides)

    assert changed is True
    assert playlist[0].episode_display_title == "08-03 第1期上：又争又抢"
    assert playlist[0].episode_title_source == "manual"
    assert playlist[1].episode_display_title == ""  # untouched
    assert playlist[1].episode_title_source == ""


def test_apply_overrides_seeds_original_title(tmp_path: Path) -> None:
    item = PlayItem(title="file.mp4", url="http://m/1.mp4")
    apply_episode_title_overrides([item], {"http://m/1.mp4": "改写标题"})
    assert item.original_title == "file.mp4"
