from atv_player.metadata.query import (
    infer_metadata_category_name_from_title,
    is_short_drama_collection,
    normalize_metadata_query_inputs,
    normalize_metadata_title,
)


def test_normalize_metadata_title_strips_trailing_color_quality_parentheses() -> None:
    assert normalize_metadata_title("良陈美锦（臻彩）") == "良陈美锦"
    assert normalize_metadata_title("百万诱惑（真彩）") == "百万诱惑"


def test_normalize_metadata_query_inputs_keeps_embedded_year_parentheses() -> None:
    assert normalize_metadata_query_inputs("良陈美锦 (2026)", "") == ("良陈美锦", "2026")


def test_infer_metadata_category_name_treats_drama_version_as_live_action() -> None:
    assert infer_metadata_category_name_from_title("成何体统剧版") == "剧集"


def test_short_drama_collection_detection_uses_category_or_catalogue_title() -> None:
    assert is_short_drama_collection("年8月7日 短剧更新目录9")
    assert is_short_drama_collection("任意标题", "短剧")
    assert is_short_drama_collection("任意标题", "剧情 / 短片")
    assert not is_short_drama_collection("这是一个短剧名字")
    assert not is_short_drama_collection("普通电视剧", "剧集")
