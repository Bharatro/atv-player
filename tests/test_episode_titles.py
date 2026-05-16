from atv_player.episode_titles import (
    apply_episode_title_map,
    extract_season_number,
    playlist_has_title_variants,
    playlist_item_display_title,
    seed_original_titles,
)
from atv_player.models import PlayItem


def test_seed_original_titles_only_fills_missing_original_title() -> None:
    playlist = [
        PlayItem(title="原文件A.mkv", url="http://a"),
        PlayItem(title="原文件B.mkv", url="http://b", original_title="保留值"),
    ]

    seed_original_titles(playlist)

    assert playlist[0].original_title == "原文件A.mkv"
    assert playlist[1].original_title == "保留值"


def test_apply_episode_title_map_uses_higher_priority_source() -> None:
    playlist = [PlayItem(title="01.mkv", url="http://a", original_title="01.mkv")]
    seed_original_titles(playlist)

    apply_episode_title_map(
        playlist,
        {1: "第1集 原始站点标题"},
        source="tencent",
        source_priority=["plugin", "tencent", "tmdb"],
    )
    apply_episode_title_map(
        playlist,
        {1: "第1集 TMDB标题"},
        source="tmdb",
        source_priority=["plugin", "tencent", "tmdb"],
    )

    assert playlist[0].episode_display_title == "第1集 原始站点标题"
    assert playlist[0].episode_title_source == "tencent"


def test_playlist_has_title_variants_requires_different_original_and_enhanced_titles() -> None:
    playlist = [PlayItem(title="第1集", url="http://a", original_title="第1集", episode_display_title="第1集")]

    assert playlist_has_title_variants(playlist) is False

    playlist[0].episode_display_title = "第1集 星门初启"

    assert playlist_has_title_variants(playlist) is True


def test_playlist_item_display_title_switches_between_modes() -> None:
    item = PlayItem(
        title="第1集 星门初启",
        url="http://a",
        original_title="S01E01.mkv",
        episode_display_title="第1集 星门初启",
    )

    assert playlist_item_display_title(item, "episode") == "第1集 星门初启"
    assert playlist_item_display_title(item, "original") == "S01E01.mkv"


def test_extract_season_number_supports_common_formats() -> None:
    assert extract_season_number("黑袍纠察队第五季") == 5
    assert extract_season_number("Season 2") == 2
    assert extract_season_number("S02E01.mkv") == 2
