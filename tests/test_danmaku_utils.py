from atv_player.danmaku.models import DanmakuRecord
from atv_player.danmaku.utils import (
    build_xml,
    extract_episode_number,
    extract_variety_issue_key,
    infer_playlist_episode_number,
    is_likely_variety_title,
    match_provider,
    normalize_name,
    should_filter_name,
    strip_variety_issue_suffix,
)
from atv_player.models import PlayItem


def test_normalize_name_strips_noise_tokens() -> None:
    assert normalize_name(" 剑来 第1集【高清】(qq.com) ") == "剑来 第1集"


def test_match_provider_maps_known_domains() -> None:
    assert match_provider("https://v.qq.com/x/cover/demo.html") == "tencent"
    assert match_provider("https://v.youku.com/v_show/id_demo.html") == "youku"
    assert match_provider("https://www.iqiyi.com/v_demo.html") == "iqiyi"
    assert match_provider("https://www.mgtv.com/b/demo.html") == "mgtv"
    assert match_provider("https://example.com/watch/1") is None


def test_should_filter_name_rejects_unrelated_titles() -> None:
    target = normalize_name("剑来 第1集")
    assert should_filter_name(target, "凡人修仙传 第1集") is True
    assert should_filter_name(target, "剑来 第1集") is False


def test_should_filter_name_rejects_sequel_mismatch() -> None:
    target = normalize_name("疯狂动物城2")
    assert should_filter_name(target, "疯狂动物城") is True
    assert should_filter_name(target, "疯狂动物城2（普通话版）") is False


def test_should_filter_name_accepts_season_number_format_variants() -> None:
    target = normalize_name("哈哈哈哈哈第六季")
    assert should_filter_name(target, "哈哈哈哈哈第6季 第1期上 邓超陈赫癫狂式唱山歌") is False


def test_extract_episode_number_supports_numeric_title_with_size_suffix() -> None:
    assert extract_episode_number("12(1.26 GB)") == 12


def test_extract_episode_number_supports_chinese_numerals() -> None:
    assert extract_episode_number("第十二集") == 12


def test_extract_episode_number_supports_zero_padded_prefix_titles() -> None:
    assert extract_episode_number("0002 剑来-笼中雀") == 2


def test_extract_variety_issue_key_supports_calendar_issue_titles() -> None:
    assert extract_variety_issue_key("你好星期六 20250104期") == "20250104"


def test_is_likely_variety_title_distinguishes_issue_from_episode_titles() -> None:
    assert is_likely_variety_title("歌手2026 第12期") is True
    assert is_likely_variety_title("剑来 第12集") is False


def test_strip_variety_issue_suffix_keeps_base_title() -> None:
    assert strip_variety_issue_suffix("你好星期六 20250104期") == "你好星期六"
    assert strip_variety_issue_suffix("你好星期六 2025-01-04") == "你好星期六"
    assert strip_variety_issue_suffix("哈哈哈哈哈第六季 20260404期 第1期上：最狠开局！五哈团命悬一线好刺激 4K60") == "哈哈哈哈哈第六季"


def test_extract_episode_number_supports_cjk_bar_separated_prefix_titles() -> None:
    assert extract_episode_number("01丨4K.mp4") == 1


def test_extract_episode_number_prefers_trailing_episode_over_range_prefix() -> None:
    assert extract_episode_number("01-99集 - 39(147.67 MB)") == 39


def test_extract_episode_number_ignores_range_only_prefix_titles() -> None:
    assert extract_episode_number("01-99集") is None


def test_extract_episode_number_supports_quality_variant_prefix_titles() -> None:
    assert extract_episode_number("160-4K.mp4(471.43 MB)") == 160


def test_infer_playlist_episode_number_prefers_current_title() -> None:
    playlist = [
        PlayItem(title="0001 剑来-总管坐镇剑气长城", url="http://m/1.mp4", index=0),
        PlayItem(title="0002 剑来-笼中雀", url="http://m/2.mp4", index=1),
        PlayItem(title="0003 剑来-第三集", url="http://m/3.mp4", index=2),
    ]

    assert infer_playlist_episode_number(playlist[1], playlist) == 2


def test_infer_playlist_episode_number_prefers_trailing_episode_over_range_prefix() -> None:
    playlist = [
        PlayItem(title="01-08 - 01(1.66 GB)", url="http://m/1.mp4", index=0),
        PlayItem(title="01-08 - 02(1.54 GB)", url="http://m/2.mp4", index=1),
        PlayItem(title="01-08 - 03(1.42 GB)", url="http://m/3.mp4", index=2),
    ]

    assert infer_playlist_episode_number(playlist[1], playlist) == 2


def test_infer_playlist_episode_number_prefers_cjk_bar_separated_prefix_titles_over_playlist_position() -> None:
    playlist = [
        PlayItem(title="01~4K.mp4", url="http://m/1.mp4", index=0),
        PlayItem(title="01丨4K.mp4", url="http://m/1b.mp4", index=1),
        PlayItem(title="02丨4K.mp4", url="http://m/2.mp4", index=2),
        PlayItem(title="03-4K.mp4", url="http://m/3.mp4", index=3),
    ]

    assert infer_playlist_episode_number(playlist[1], playlist) == 1
    assert infer_playlist_episode_number(playlist[2], playlist) == 2


def test_infer_playlist_episode_number_falls_back_to_playlist_position() -> None:
    playlist = [
        PlayItem(title="正片.mp4", url="http://m/1.mp4", index=0),
        PlayItem(title="国语.mp4", url="http://m/2.mp4", index=1),
        PlayItem(title="超清.mp4", url="http://m/3.mp4", index=2),
    ]

    assert infer_playlist_episode_number(playlist[1], playlist) == 2


def test_infer_playlist_episode_number_ignores_year_prefixed_media_filename() -> None:
    playlist = [
        PlayItem(
            title="2025.2160p.iTunes.WEB-DL.H265.DV.HDR.DDP5.1.Atmos.mkv(18.87 GB)",
            url="http://m/1.mp4",
            index=0,
        ),
        PlayItem(
            title="Zootopia.2.2025.1080p.AMZN.WEB-DL.English.DDP5.1.H.264.mkv(5.51 GB)",
            url="http://m/2.mp4",
            index=1,
        ),
    ]

    assert infer_playlist_episode_number(playlist[0], playlist) is None


def test_infer_playlist_episode_number_falls_back_to_path_when_display_title_hides_numeric_filename() -> None:
    playlist = [
        PlayItem(
            title="The.Boys.S05E06(8.5 GB)",
            url="http://m/6.mp4",
            path="/show/Season5/S05E06.2160p.AMZN.WEB-DL.DDP5.1.Atmos.HDR10P.H.265.mkv",
            index=0,
        ),
        PlayItem(
            title="4K内嵌中英双语 - 1.mp4(3.46 GB)",
            url="http://m/1.mp4",
            path="/show/Season5/4K内嵌中英双语/1.mp4",
            index=1,
        ),
    ]

    assert infer_playlist_episode_number(playlist[1], playlist) == 1


def test_build_xml_escapes_content_and_keeps_expected_shape() -> None:
    xml = build_xml(
        [
            DanmakuRecord(time_offset=1.5, pos=1, color="16777215", content="a < b & c"),
            DanmakuRecord(time_offset=3.0, pos=4, color="255", content='"quoted"'),
        ]
    )

    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?><i>')
    assert '<d p="1.5,1,25,16777215">a &lt; b &amp; c</d>' in xml
    assert '<d p="3.0,4,25,255">"quoted"</d>' in xml
    assert xml.endswith("</i>")
