from atv_player.danmaku.subtitle import render_danmaku_ass, render_danmaku_srt


def test_render_danmaku_srt_builds_top_line_timeline_from_xml() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">第一条</d>'
        '<d p="0.5,1,25,16777215">第二条</d>'
        '<d p="1.0,1,25,16777215">第三条</d>'
        '<d p="4.1,1,25,16777215">第四条</d>'
        "</i>"
    )

    subtitle = render_danmaku_srt(xml_text, line_count=2, duration_seconds=4.0)

    assert subtitle == "\n".join(
        [
            "1",
            "00:00:00,000 --> 00:00:00,500",
            "第一条",
            "",
            "2",
            "00:00:00,500 --> 00:00:04,000",
            "第一条",
            "第二条",
            "",
            "3",
            "00:00:04,000 --> 00:00:04,100",
            "第二条",
            "",
            "4",
            "00:00:04,100 --> 00:00:04,500",
            "第四条",
            "第二条",
            "",
            "5",
            "00:00:04,500 --> 00:00:08,100",
            "第四条",
            "",
        ]
    )


def test_render_danmaku_srt_returns_empty_string_for_invalid_or_empty_xml() -> None:
    assert render_danmaku_srt("", line_count=1) == ""
    assert render_danmaku_srt("<i><d></i>", line_count=1) == ""


def test_render_danmaku_ass_embeds_font_size_and_top_alignment() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">第一条</d>'
        '<d p="0.5,1,25,16777215">第二条</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(xml_text, line_count=2, duration_seconds=4.0)

    assert "[Script Info]" in subtitle
    assert "Style: Danmaku" in subtitle
    assert ",32," in subtitle
    assert ",8," in subtitle
    assert ",4,1" in subtitle
    assert "Dialogue:" in subtitle
    assert "第一条\\N第二条" in subtitle


def test_render_danmaku_ass_uses_uniform_color_and_scroll_mode() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,255">滚动蓝字</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FF0000",
        position_preset="upper",
    )

    assert "\\move(" in subtitle
    assert "\\1c&H0000FF&" in subtitle
    assert "\\1c&HFF0000&" not in subtitle


def test_render_danmaku_outputs_count_intro_before_real_comments() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="1.0,1,25,16777215">第一条</d>'
        '<d p="2.0,1,25,16777215">第二条</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(xml_text, line_count=2, duration_seconds=4.0)

    assert "2条弹幕来袭！" in subtitle
    assert subtitle.index("2条弹幕来袭！") < subtitle.index("第一条")


def test_render_danmaku_keeps_count_intro_visible_for_longer() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="1.0,1,25,16777215">第一条</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(xml_text, line_count=1, duration_seconds=4.0)

    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Danmaku,,0,0,0,,1条弹幕来袭！" in subtitle


def test_render_danmaku_ass_scroll_mode_uses_slower_default_duration() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">慢一点</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "Dialogue: 0,0:00:00.00,0:00:12.00" in subtitle


def test_render_danmaku_ass_applies_custom_scroll_speed_and_font_size() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">慢速大字</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
        scroll_speed=0.5,
        font_size=40,
    )

    assert ",40," in subtitle
    assert "Dialogue: 0,0:00:00.00,0:00:24.00" in subtitle


def test_render_danmaku_ass_places_top_scroll_comments_closer_to_top_edge() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">更靠上</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "{\\an8\\move(2000,30,-400,30)\\1c&HFFFFFF&}更靠上" in subtitle


def test_render_danmaku_ass_preserves_source_top_and_bottom_in_mixed_mode() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,5,25,16777215">顶部</d>'
        '<d p="1.0,4,25,65280">底部</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=2,
        render_mode="mixed",
        color_mode="source",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "顶部" in subtitle
    assert "底部" in subtitle
    assert "\\move(" not in subtitle.split("顶部", 1)[0]


def test_render_danmaku_ass_uses_source_color_in_static_mode() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16711680">红色</d>'
        '<d p="0.5,1,25,255">蓝色</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=2,
        render_mode="static",
        color_mode="source",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "{\\1c&H0000FF&}红色" in subtitle
    assert "{\\1c&HFF0000&}蓝色" in subtitle


def test_render_danmaku_ass_keeps_static_comments_top_aligned_regardless_of_position_preset() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">固定顶部</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="static",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="bottom",
    )

    assert ",8," in subtitle
    assert "\\pos(" not in subtitle
    assert "\\move(" not in subtitle


def test_render_danmaku_ass_prioritizes_colored_static_comments_when_lines_are_limited() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">白色占位</d>'
        '<d p="1.0,1,25,16711680">红色保留</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        duration_seconds=4.0,
        render_mode="static",
        color_mode="source",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "白色占位" in subtitle
    assert "{\\1c&H0000FF&}红色保留" in subtitle


def test_render_danmaku_ass_prioritizes_colored_scroll_comments_when_lines_are_limited() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">白色滚动</d>'
        '<d p="1.0,1,25,65280">绿色滚动</d>'
        "</i>"
    )

    subtitle = render_danmaku_ass(
        xml_text,
        line_count=1,
        duration_seconds=4.0,
        render_mode="scroll_only",
        color_mode="source",
        uniform_color="#FFFFFF",
        position_preset="top",
    )

    assert "白色滚动" in subtitle
    assert "{\\an8\\move(2000,30,-400,30)\\1c&H00FF00&}绿色滚动" in subtitle
