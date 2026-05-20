from atv_player.metadata.merge import choose_preferred_title, merge_metadata_record, replace_metadata_record
from atv_player.metadata.models import MetadataRecord
from atv_player.models import PlaybackDetailField, PlaybackDetailFieldAction, VodItem


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


def test_merge_metadata_prefers_tmdb_visual_fields_but_keeps_official_douban_overview_and_rating() -> None:
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
        provider="official_douban",
        provider_id="35746415",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    merge_metadata_record(vod, tmdb_record, provider_priority=["tmdb"])
    merge_metadata_record(vod, douban_record, provider_priority=["official_douban", "tmdb"])

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


def test_merge_metadata_attaches_exact_tmdb_link_target_from_provider_id() -> None:
    movie_vod = VodItem(vod_id="v1", vod_name="深空彼岸")
    tv_vod = VodItem(vod_id="v2", vod_name="七王国的骑士")
    movie_record = MetadataRecord(provider="tmdb", provider_id="movie:42", tmdb_id="42")
    tv_record = MetadataRecord(provider="tmdb", provider_id="tv:76479", tmdb_id="76479")

    merge_metadata_record(movie_vod, movie_record, provider_priority=["tmdb"])
    merge_metadata_record(tv_vod, tv_record, provider_priority=["tmdb"])

    assert movie_vod.detail_fields[0].value_parts[0].action == PlaybackDetailFieldAction(
        type="link",
        value="42",
        target="movie",
    )
    assert tv_vod.detail_fields[0].value_parts[0].action == PlaybackDetailFieldAction(
        type="link",
        value="76479",
        target="tv",
    )


def test_merge_metadata_prefers_bangumi_text_fields_but_keeps_tmdb_poster() -> None:
    vod = VodItem(vod_id="v1", vod_name="旧标题", vod_pic="https://img.tmdb/poster.jpg")
    vod.metadata_field_sources["poster"] = "tmdb"
    bangumi = MetadataRecord(
        provider="bangumi",
        provider_id="subject:1",
        overview="Bangumi简介",
        actors=["种崎敦美"],
        genres=["动画", "奇幻"],
        poster="https://img.bgm/poster.jpg",
    )

    merge_metadata_record(vod, bangumi, provider_priority=["bangumi", "tmdb"])

    assert vod.vod_content == "Bangumi简介"
    assert vod.vod_actor == "种崎敦美"
    assert vod.type_name == "动画 / 奇幻"
    assert vod.vod_pic == "https://img.tmdb/poster.jpg"


def test_merge_metadata_promotes_higher_priority_poster_and_keeps_previous_candidate() -> None:
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_pic="https://img.site/poster.jpg")
    record = MetadataRecord(
        provider="tmdb",
        provider_id="movie:42",
        poster="https://img.tmdb/poster.jpg",
    )

    merge_metadata_record(vod, record, provider_priority=["tmdb"])

    assert vod.vod_pic == "https://img.tmdb/poster.jpg"
    assert vod.poster_candidates == [
        "https://img.tmdb/poster.jpg",
        "https://img.site/poster.jpg",
    ]


def test_merge_metadata_appends_lower_priority_poster_without_overriding_primary() -> None:
    vod = VodItem(vod_id="v1", vod_name="旧标题", vod_pic="https://img.tmdb/poster.jpg")
    vod.metadata_field_sources["poster"] = "tmdb"
    record = MetadataRecord(
        provider="bangumi",
        provider_id="subject:1",
        poster="https://img.bgm/poster.jpg",
    )

    merge_metadata_record(vod, record, provider_priority=["bangumi", "tmdb"])

    assert vod.vod_pic == "https://img.tmdb/poster.jpg"
    assert vod.poster_candidates == [
        "https://img.tmdb/poster.jpg",
        "https://img.bgm/poster.jpg",
    ]


def test_choose_preferred_title_overrides_garbage_title_with_clean_candidate() -> None:
    assert choose_preferred_title("J【加@页】", "国色芳华") == "国色芳华"


def test_choose_preferred_title_preserves_clean_title_when_candidate_too_different() -> None:
    assert choose_preferred_title("国色芳花", "国色芳华") == "国色芳花"


def test_choose_preferred_title_preserves_garbage_when_candidate_is_also_garbage() -> None:
    assert choose_preferred_title("J【加@页】", "X【推@广】") == "J【加@页】"


def test_merge_metadata_iqiyi_overrides_low_quality_title_with_record_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="J【加@页】")
    record = MetadataRecord(provider="iqiyi", provider_id="iqiyi:1", title="国色芳华")

    merge_metadata_record(vod, record, provider_priority=["iqiyi"])

    assert vod.vod_name == "国色芳华"


def test_merge_metadata_iqiyi_preserves_clean_existing_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="国色芳花")
    record = MetadataRecord(provider="iqiyi", provider_id="iqiyi:1", title="国色芳华")

    merge_metadata_record(vod, record, provider_priority=["iqiyi"])

    assert vod.vod_name == "国色芳花"


def test_merge_metadata_iqiyi_overrides_drive_folder_style_title_with_record_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="di|纸上|f|紫微(2026)")
    record = MetadataRecord(provider="iqiyi", provider_id="iqiyi:1", title="纸上紫微", year="2026")

    merge_metadata_record(vod, record, provider_priority=["iqiyi"])

    assert vod.vod_name == "纸上紫微"


def test_merge_metadata_tmdb_overrides_decorated_title_with_record_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="大盗毒⭐")
    record = MetadataRecord(provider="tmdb", provider_id="tv:317320", title="大道独行", year="2026")

    merge_metadata_record(vod, record, provider_priority=["tmdb"])

    assert vod.vod_name == "大道独行"


def test_replace_metadata_record_strips_html_tags_from_detail_fields() -> None:
    vod = VodItem(vod_id="v1", vod_name="百炼成神")
    record = MetadataRecord(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        detail_fields=[
            {
                "label": "制作信息",
                "value": '作者：燃哉工作室 漫画：<em class="keyword">百炼成神</em> 导演：邓沐',
            }
        ],
    )

    replace_metadata_record(vod, record)

    assert [(field.label, field.value) for field in vod.detail_fields] == [
        ("制作信息", "作者：燃哉工作室 漫画：百炼成神 导演：邓沐")
    ]
