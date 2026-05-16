from atv_player.metadata.merge import merge_metadata_record
from atv_player.metadata.models import MetadataRecord
from atv_player.models import PlaybackDetailField, VodItem


def test_merge_metadata_overrides_overview_with_douban_and_preserves_existing_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="插件标题", vod_content="插件简介", vod_pic="poster.jpg")
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        title="豆瓣标题",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    merge_metadata_record(vod, record, provider_priority=["douban"])

    assert vod.vod_name == "插件标题"
    assert vod.vod_content == "豆瓣简介"
    assert vod.vod_remarks == "8.1"
    assert vod.dbid == 35746415


def test_merge_metadata_replaces_same_label_detail_field_and_appends_new_labels() -> None:
    vod = VodItem(
        vod_id="v1",
        vod_name="深空彼岸",
        detail_fields=[
            PlaybackDetailField(label="别名", value="插件别名"),
            PlaybackDetailField(label="IMDb ID", value="tt-old"),
        ],
    )
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        detail_fields=[
            {"label": "别名", "value": "豆瓣别名"},
            {"label": "TMDB ID", "value": "12345"},
        ],
    )

    merge_metadata_record(vod, record, provider_priority=["douban"])

    assert [(field.label, field.value) for field in vod.detail_fields] == [
        ("别名", "豆瓣别名"),
        ("IMDb ID", "tt-old"),
        ("TMDB ID", "12345"),
    ]


def test_merge_metadata_fills_core_detail_rows_from_douban_record() -> None:
    vod = VodItem(vod_id="v1", vod_name="深空彼岸")
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        year="2026",
        rating="8.1",
        actors=["梁达伟", "唐雅菁"],
        genres=["动画", "科幻"],
        country="中国大陆",
        language="汉语普通话",
        directors=["周琛"],
    )

    merge_metadata_record(vod, record, provider_priority=["douban"])

    assert vod.vod_year == "2026"
    assert vod.vod_remarks == "8.1"
    assert vod.vod_actor == "梁达伟,唐雅菁"
    assert vod.type_name == "动画 / 科幻"
    assert vod.vod_area == "中国大陆"
    assert vod.vod_lang == "汉语普通话"
    assert vod.vod_director == "周琛"


def test_merge_metadata_prefers_tmdb_visual_fields_but_keeps_douban_overview_and_rating() -> None:
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_content="原始简介")
    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="movie:42",
        poster="https://img.example/tmdb-poster.jpg",
        backdrop="https://img.example/tmdb-backdrop.jpg",
        year="2026",
        actors=["梁达伟"],
        directors=["周琛"],
        genres=["动画"],
        aliases=["The First Sequence"],
        imdb_id="tt123",
        tmdb_id="42",
        overview="TMDB简介",
        rating="7.2",
    )
    douban_record = MetadataRecord(
        provider="local_douban",
        provider_id="35746415",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    merge_metadata_record(vod, tmdb_record, provider_priority=["tmdb"])
    merge_metadata_record(vod, douban_record, provider_priority=["local_douban", "tmdb"])

    assert vod.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert vod.vod_content == "豆瓣简介"
    assert vod.vod_remarks == "8.1"
    assert vod.vod_year == "2026"
    assert vod.vod_actor == "梁达伟"
    assert vod.vod_director == "周琛"
    assert vod.type_name == "动画"
    assert vod.dbid == 35746415
    assert [(field.label, field.value) for field in vod.detail_fields] == [
        ("别名", "The First Sequence"),
        ("IMDb ID", "tt123"),
        ("TMDB ID", "42"),
    ]
