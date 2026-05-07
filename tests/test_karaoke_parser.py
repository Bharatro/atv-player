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


def test_parse_netease_yrc_normalizes_absolute_word_timing_and_preserves_spaces() -> None:
    document = parse_raw_karaoke(
        "netease-yrc",
        """[20100,4770](20100,470,0)音(20570,270,0)乐(20840,460,0)停(21300,280,0)止(21580,1090,0)了 (22670,330,0)引(23000,260,0)擎(23260,530,0)熄(23790,350,0)火(24140,730,0)了""",
    )

    assert document.source_format == "netease-yrc"
    assert document.lines[0].start_ms == 20100
    assert document.lines[0].end_ms == 24870
    assert document.lines[0].text == "音乐停止了 引擎熄火了"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("音", 20100, 20570),
        ("乐", 20570, 20840),
        ("停", 20840, 21300),
        ("止", 21300, 21580),
        ("了 ", 21580, 22670),
        ("引", 22670, 23000),
        ("擎", 23000, 23260),
        ("熄", 23260, 23790),
        ("火", 23790, 24140),
        ("了", 24140, 24870),
    ]


def test_parse_netease_yrc_skips_bad_tokens_but_keeps_valid_words() -> None:
    document = parse_raw_karaoke(
        "netease-yrc",
        """[0,1600](0,400,0)我(bad)坏(400,400,0)很(800,0,0)词(1200,400,0)好""",
    )

    assert document.source_format == "netease-yrc"
    assert len(document.lines) == 1
    assert document.lines[0].text == "我很好"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("我", 0, 400),
        ("很", 400, 800),
        ("好", 1200, 1600),
    ]


def test_parse_raw_karaoke_rejects_unsupported_format() -> None:
    document = parse_raw_karaoke("unknown-karaoke", "[0,1000](0,1000,0)测试")
    assert document.lines == []
