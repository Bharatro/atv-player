from atv_player.karaoke.parser import parse_raw_karaoke


def test_parse_qqmusic_qrc_normalizes_word_timing_and_ignores_metadata() -> None:
    document = parse_raw_karaoke(
        "qqmusic-qrc",
        """<?xml version="1.0" encoding="utf-8"?>
<QrcInfos>
<LyricInfo LyricCount="1">
<Lyric_1 LyricType="1" LyricContent="[ti:晴天]
[offset:0]
[29264,3446]故(29264,390)事(29654,392)的(30046,448)小(30494,922)黄(31416,374)花(31790,504)
"/>
</LyricInfo>
</QrcInfos>
""",
    )

    assert document.source_format == "qqmusic-qrc"
    assert document.lines[0].start_ms == 29264
    assert document.lines[0].end_ms == 32710
    assert document.lines[0].text == "故事的小黄花"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("故", 29264, 29654),
        ("事", 29654, 30046),
        ("的", 30046, 30494),
        ("小", 30494, 31416),
        ("黄", 31416, 31790),
        ("花", 31790, 32294),
    ]


def test_parse_kugou_krc_normalizes_relative_offsets_and_preserves_spaces() -> None:
    document = parse_raw_karaoke(
        "kugou-krc",
        """[180,5340]<0,480,0>轻<480,570,0>舟<1050,480,0>已<1530,900,0>过<2430,0,0> <2430,570,0>万<3000,750,0>重<3750,1080,0>山""",
    )

    assert document.source_format == "kugou-krc"
    assert document.lines[0].text == "轻舟已过 万重山"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("轻", 180, 660),
        ("舟", 660, 1230),
        ("已", 1230, 1710),
        ("过", 1710, 2610),
        (" ", 2610, 2610),
        ("万", 2610, 3180),
        ("重", 3180, 3930),
        ("山", 3930, 5010),
    ]


def test_parse_raw_karaoke_rejects_unsupported_format() -> None:
    document = parse_raw_karaoke("netease-yrc", "[0,1000](0,1000,0)测试")
    assert document.lines == []
