import re

from atv_player.danmaku.models import DanmakuRecord
from atv_player.danmaku.processing import (
    apply_time_offset,
    convert_top_bottom_to_scroll,
    filter_blocked_words,
    group_by_time_window,
    parse_offset_rules,
    resolve_offset_seconds,
)


def _r(t, content, pos=1, color="16777215"):
    return DanmakuRecord(time_offset=t, pos=pos, color=color, content=content)


def test_filter_blocked_words_drops_regex_matches() -> None:
    records = [
        _r(1, "正常弹幕"),
        _r(2, "加微信abc123"),
        _r(3, "广告链接http://spam.com"),
        _r(4, "继续正常"),
    ]
    patterns = [re.compile(r"加微信"), re.compile(r"http://")]

    kept = filter_blocked_words(records, patterns)

    assert [r.content for r in kept] == ["正常弹幕", "继续正常"]


def test_filter_blocked_words_no_patterns_returns_all() -> None:
    records = [_r(1, "a"), _r(2, "b")]
    assert filter_blocked_words(records, []) is not None and len(filter_blocked_words(records, [])) == 2


def test_group_by_time_window_dedupes_same_content_in_window() -> None:
    records = [
        _r(0, "前方高能"),
        _r(30, "前方高能"),   # same 1-min window, same content -> dedupe
        _r(70, "前方高能"),   # next window -> kept
        _r(5, "别的弹幕"),
    ]
    kept = group_by_time_window(records, minutes=1)

    contents = [r.content for r in kept]
    assert contents.count("前方高能") == 2  # one per window
    assert "别的弹幕" in contents


def test_group_by_time_window_zero_minutes_keeps_all() -> None:
    records = [_r(0, "x"), _r(1, "x"), _r(2, "x")]
    assert len(group_by_time_window(records, minutes=0)) == 3


def test_convert_top_bottom_to_scroll_flattens_pos_four_and_five() -> None:
    records = [_r(1, "滚动", pos=1), _r(2, "顶", pos=5), _r(3, "底", pos=4)]
    converted = convert_top_bottom_to_scroll(records)
    assert [r.pos for r in converted] == [1, 1, 1]


def test_apply_time_offset_shifts_seconds_and_clamps_to_zero() -> None:
    records = [_r(5, "a"), _r(0, "b"), _r(10, "c")]
    shifted = apply_time_offset(records, offset_seconds=-3)
    assert [r.time_offset for r in shifted] == [2, 0, 7]


def test_apply_time_offset_zero_is_noop() -> None:
    records = [_r(5, "a")]
    assert apply_time_offset(records, offset_seconds=0) == records


def test_apply_time_offset_percent_scales_by_duration() -> None:
    records = [_r(100, "a"), _r(0, "b")]
    # percent mode: offset is seconds; scale ratio = (duration+offset)/duration.
    # offset=10 over duration=1000 -> ratio 1.01 -> 100*1.01=101.
    shifted = apply_time_offset(records, offset_seconds=10, use_percent=True, video_duration_seconds=1000)
    assert [r.time_offset for r in shifted] == [101, 0]


def test_parse_offset_rules_and_resolve_anime_level() -> None:
    rules = parse_offset_rules("百花杀:-5, 百花杀/S01/E03:3, 季番/S02@tencent:1.5")
    assert resolve_offset_seconds(rules, anime="百花杀") == -5
    # episode-level beats anime-level
    assert resolve_offset_seconds(rules, anime="百花杀", season="S01", episode="E03") == 3
    # source-specific
    assert resolve_offset_seconds(rules, anime="季番", season="S02", source="tencent") == 1.5
    assert resolve_offset_seconds(rules, anime="季番", season="S02", source="iqiyi") == 0


def test_resolve_offset_seconds_no_rules_returns_zero() -> None:
    assert resolve_offset_seconds([], anime="x") == 0
    assert resolve_offset_seconds(parse_offset_rules("a:1"), anime="") == 0
