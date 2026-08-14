from atv_player.subtitles.languages import (
    CHS,
    CHS_ENG,
    CHT,
    CHT_ENG,
    ENG,
    OTHER,
    ZH,
    language_label,
    language_rank,
    normalize_language,
)


def test_simplified_english_bilingual_has_highest_priority() -> None:
    ranks = [
        language_rank(CHS_ENG),
        language_rank(CHT_ENG),
        language_rank(CHS),
        language_rank(ZH),
        language_rank(CHT),
        language_rank(ENG),
        language_rank(OTHER),
    ]
    assert ranks == sorted(ranks)
    assert language_rank(CHS_ENG) == min(ranks)


def test_normalize_recognizes_bilingual_variants() -> None:
    assert normalize_language("简英双语") == CHS_ENG
    assert normalize_language("chs&eng") == CHS_ENG
    assert normalize_language("繁英双语") == CHT_ENG
    assert normalize_language("cht", "English") == CHT_ENG


def test_normalize_recognizes_single_language() -> None:
    assert normalize_language("简体") == CHS
    assert normalize_language("chs") == CHS
    assert normalize_language("繁體中文") == CHT
    assert normalize_language("big5") == CHT
    assert normalize_language("English") == ENG
    assert normalize_language("") == OTHER


def test_normalize_uses_later_hints_when_first_is_empty() -> None:
    assert normalize_language("", "Movie.2020.chs.srt") == CHS


def test_language_label_falls_back_for_unknown_code() -> None:
    assert language_label(CHS_ENG) == "简英双语"
    assert language_label("no-such-code") == "其他"
