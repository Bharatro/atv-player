import re

from atv_player.danmaku.models import DanmakuRecord
from atv_player.danmaku.processing import (
    apply_time_offset,
    build_blocked_matchers,
    clean_records,
    convert_top_bottom_to_scroll,
    group_by_time_window,
)


def _r(t, content, pos=1, color="16777215"):
    return DanmakuRecord(time_offset=t, pos=pos, color=color, content=content)


def test_clean_records_uses_casefolded_plain_substrings() -> None:
    records = [
        _r(1, "SPAM link"),
        _r(2, "正常"),
        _r(3, "spam again"),
    ]

    cleaned = clean_records(
        records,
        blocked_words=["spam"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )

    assert [record.content for record in cleaned] == ["正常"]


def test_clean_records_applies_blocking_dedupe_and_conversion_in_order() -> None:
    records = [
        _r(1, "drop duplicate", pos=5),
        _r(2, "duplicate", pos=5),
        _r(3, "duplicate", pos=4),
        _r(70, "duplicate", pos=4),
    ]

    cleaned = clean_records(
        records,
        blocked_words=["drop"],
        duplicate_window_minutes=1,
        convert_top_bottom=True,
    )

    assert [(record.time_offset, record.pos, record.content) for record in cleaned] == [
        (2, 1, "duplicate"),
        (70, 1, "duplicate"),
    ]


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


def test_clean_records_supports_regex_blocked_words() -> None:
    records = [
        _r(1, "广告123点链接"),
        _r(2, "正常弹幕"),
        _r(3, "广告链接"),
    ]

    cleaned = clean_records(
        records,
        blocked_words=[r"/广告\d+/"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )

    assert [record.content for record in cleaned] == ["正常弹幕", "广告链接"]


def test_clean_records_regex_flags_control_case_sensitivity() -> None:
    records = [_r(1, "SPAM link"), _r(2, "spam link")]

    cleaned = clean_records(
        records,
        blocked_words=["/spam/"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )
    assert [record.content for record in cleaned] == ["SPAM link"]

    cleaned = clean_records(
        records,
        blocked_words=["/spam/i"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )
    assert [record.content for record in cleaned] == []


def test_clean_records_degrades_invalid_regex_to_literal_match() -> None:
    records = [_r(1, "看/[/广告]"), _r(2, "正常")]

    cleaned = clean_records(
        records,
        blocked_words=["/[/", "正常"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )

    # "/[/" 不是合法正则，按字面量处理仍能命中 "/[/" 子串
    assert [record.content for record in cleaned] == []


def test_build_blocked_matchers_keeps_plain_words_casefolded() -> None:
    matchers = build_blocked_matchers(["  SPAM  ", "", "/ok/i"])

    assert matchers == [
        ("text", "spam"),
        ("regex", re.compile("ok", re.IGNORECASE)),
    ]
