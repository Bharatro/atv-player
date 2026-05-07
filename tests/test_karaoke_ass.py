from atv_player.karaoke.ass import render_karaoke_ass
from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord


def test_render_karaoke_ass_emits_kf_segments_for_each_word() -> None:
    document = KaraokeDocument(
        source_format="qqmusic-qrc",
        lines=[
            KaraokeLine(
                start_ms=29264,
                end_ms=32710,
                text="故事的小黄花",
                words=[
                    KaraokeWord(text="故", start_ms=29264, end_ms=29654),
                    KaraokeWord(text="事", start_ms=29654, end_ms=30046),
                    KaraokeWord(text="的", start_ms=30046, end_ms=30494),
                ],
            )
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert "Style: KaraokeMain" in subtitle
    assert "Dialogue: 0,0:00:29.26,0:00:32.71,KaraokeMain" in subtitle
    assert r"{\kf39}故{\kf39}事{\kf45}的" in subtitle


def test_render_karaoke_ass_adds_static_translation_dialogue() -> None:
    document = KaraokeDocument(
        source_format="kugou-krc",
        lines=[
            KaraokeLine(
                start_ms=0,
                end_ms=1800,
                text="轻舟已过",
                translation="Light boat already crossed",
                words=[
                    KaraokeWord(text="轻", start_ms=0, end_ms=450),
                    KaraokeWord(text="舟", start_ms=450, end_ms=900),
                    KaraokeWord(text="已", start_ms=900, end_ms=1200),
                    KaraokeWord(text="过", start_ms=1200, end_ms=1800),
                ],
            )
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert "Style: KaraokeTranslation" in subtitle
    assert "Dialogue: 0,0:00:00.00,0:00:01.80,KaraokeTranslation" in subtitle
    assert "Light boat already crossed" in subtitle


def test_render_karaoke_ass_clamps_zero_length_tokens_and_degrades_to_static_line() -> None:
    document = KaraokeDocument(
        source_format="kugou-krc",
        lines=[
            KaraokeLine(
                start_ms=180,
                end_ms=1200,
                text="轻 舟",
                words=[
                    KaraokeWord(text="轻", start_ms=180, end_ms=180),
                    KaraokeWord(text=" ", start_ms=180, end_ms=180),
                    KaraokeWord(text="舟", start_ms=180, end_ms=660),
                ],
            ),
            KaraokeLine(start_ms=1500, end_ms=2200, text="静态行", words=[]),
        ],
    )

    subtitle = render_karaoke_ass(document)

    assert r"{\kf1}轻" in subtitle
    assert "Dialogue: 0,0:00:01.50,0:00:02.20,KaraokeMain,,0,0,0,,静态行" in subtitle
