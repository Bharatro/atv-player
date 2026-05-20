from atv_player.metadata.models import MetadataContext
from atv_player.models import VodItem


def test_metadata_context_infers_anime_category_from_raw_title_suffix() -> None:
    query = MetadataContext(
        vod=VodItem(vod_id="v1", vod_name="仙剑奇侠传叁动漫", vod_year="2025"),
        source_kind="browse",
    ).to_query()

    assert query.title == "仙剑奇侠传叁"
    assert query.year == "2025"
    assert query.category_name == "动漫"
