from atv_player.metadata.query import normalize_metadata_query_inputs, normalize_metadata_title


def test_normalize_metadata_title_strips_trailing_color_quality_parentheses() -> None:
    assert normalize_metadata_title("良陈美锦（臻彩）") == "良陈美锦"
    assert normalize_metadata_title("百万诱惑（真彩）") == "百万诱惑"


def test_normalize_metadata_query_inputs_keeps_embedded_year_parentheses() -> None:
    assert normalize_metadata_query_inputs("良陈美锦 (2026)", "") == ("良陈美锦", "2026")
