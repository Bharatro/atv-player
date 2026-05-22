from atv_player.youtube_subtitle_ass import convert_youtube_subtitle_text_to_ass


def test_convert_webvtt_with_speaker_prefixes_emits_ass_styles_and_kf_tags() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:01.200\n"
        "Alice: Hello!\n\n"
        "00:00:01.200 --> 00:00:02.400\n"
        "[Bob] Hi.\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "[Script Info]" in subtitle
    assert "Style: YouTubeDefault" in subtitle
    assert "Style: YouTubeSpeaker1" in subtitle
    assert "Style: YouTubeSpeaker2" in subtitle
    assert "Dialogue: 0,0:00:00.00,0:00:01.20,YouTubeSpeaker1" in subtitle
    assert "Dialogue: 0,0:00:01.20,0:00:02.40,YouTubeSpeaker2" in subtitle
    assert r"{\kf" in subtitle
    assert "Alice:" not in subtitle
    assert "[Bob]" not in subtitle


def test_convert_srt_without_speaker_prefix_uses_default_style() -> None:
    text = (
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "你好 世界\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,YouTubeDefault" in subtitle
    assert r"{\kf" in subtitle


def test_convert_returns_none_for_unsupported_or_empty_text() -> None:
    assert convert_youtube_subtitle_text_to_ass("") is None
    assert convert_youtube_subtitle_text_to_ass("<tt>Hello</tt>") is None


def test_convert_reuses_same_style_for_repeated_speaker() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:01.000\n"
        "Alice: One\n\n"
        "00:00:01.000 --> 00:00:02.000\n"
        "Alice: Two\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert subtitle.count("Style: YouTubeSpeaker1") == 1
    assert subtitle.count("Dialogue: 0,0:00:00.00,0:00:01.00,YouTubeSpeaker1") == 1
    assert subtitle.count("Dialogue: 0,0:00:01.00,0:00:02.00,YouTubeSpeaker1") == 1


def test_convert_degrades_punctuation_only_cue_to_static_dialogue() -> None:
    text = (
        "1\n"
        "00:00:00,000 --> 00:00:00,400\n"
        "...\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "Dialogue: 0,0:00:00.00,0:00:00.40,YouTubeDefault" in subtitle
    assert r"{\kf" not in subtitle
