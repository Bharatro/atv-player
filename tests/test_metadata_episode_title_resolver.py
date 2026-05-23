from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
    is_high_confidence_iqiyi_episode_candidate,
    resolve_episode_title_source_priority,
)
from atv_player.metadata.models import MetadataMatch
from atv_player.models import PlayItem, VodItem


def test_build_provider_episode_playlist_prefers_tencent_episode_info_list() -> None:
    vod = VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", category_name="少儿")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="米小圈上学记4",
        year="2026",
        raw={
            "title": "米小圈上学记4",
            "episode_sites": [
                {"episodeInfoList": [{"title": "第01话 金银米小圈1"}, {"title": "第02话 金银米小圈2"}]}
            ],
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1集 第01话 金银米小圈1",
        "第2集 第02话 金银米小圈2",
    ]


def test_build_provider_episode_playlist_maps_iqiyi_videos_for_multi_season_playlist() -> None:
    vod = VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧")
    playlist = [PlayItem(title="S05E01.mkv", original_title="S05E01.mkv", url="http://m/501.mp4")]
    match = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="黑袍纠察队 第五季",
        year="2026",
        raw={
            "title": "黑袍纠察队 第五季",
            "videos": [{"itemNumber": 1, "itemTitle": "终局开篇"}],
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert updated[0].episode_display_title == "第1集 终局开篇"


def test_build_provider_episode_playlist_maps_tmdb_multi_season_titles_with_complete_series_count_filenames() -> None:
    vod = VodItem(vod_id="v1", vod_name="模范剧集", vod_year="2026", category_name="电视剧")
    playlist = [
        PlayItem(
            title="第一季 1080P 6集全 - 01(3.67 GB)",
            original_title="第一季 1080P 6集全 - 01(3.67 GB)",
            url="http://m/s1e1.mp4",
        ),
        PlayItem(
            title="第二季 1080P 6集全 - 02(2.76 GB)",
            original_title="第二季 1080P 6集全 - 02(2.76 GB)",
            url="http://m/s2e2.mp4",
        ),
        PlayItem(
            title="S03 - 01(1).mkv(7.28 GB)",
            original_title="S03 - 01(1).mkv(7.28 GB)",
            path="/show/The Capture/S03E01.mkv",
            url="http://m/s3e1.mp4",
        ),
    ]
    match = MetadataMatch(
        provider="tmdb",
        provider_id="tv:42",
        title="模范剧集",
        year="2026",
        raw={
            "episodes": [
                {"episode_number": 1, "name": "不要看镜头"},
                {"episode_number": 2, "name": "孤狼"},
            ]
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1季 第1集 不要看镜头",
        "第2季 第2集 孤狼",
        "第3季 第1集 不要看镜头",
    ]


def test_build_provider_episode_playlist_maps_iqiyi_videos_with_number_and_subtitle() -> None:
    vod = VodItem(vod_id="v1", vod_name="择天记", vod_year="2026", category_name="动漫")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="择天记（2026）",
        year="2026",
        raw={
            "title": "择天记",
            "videos": [
                {"number": "1", "title": "择天记 第1集", "subtitle": "小道士下山了"},
                {"number": "2", "title": "择天记 第2集", "subtitle": "一间院，与一颗星"},
            ],
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1集 小道士下山了",
        "第2集 一间院，与一颗星",
    ]


def test_build_provider_episode_playlist_maps_bilibili_eps_long_titles() -> None:
    vod = VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        title="牧神记",
        year="2024",
        raw={
            "season_id": 45969,
            "episodes": [
                {"episode_number": 1, "episode_type": "main", "sort": 1},
                {"episode_number": 2, "episode_type": "main", "sort": 2},
            ],
            "eps": [
                {"title": "1", "index_title": "1", "long_title": "天黑别出门"},
                {"title": "2", "index_title": "2", "long_title": "我是霸体"},
            ]
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1集 天黑别出门",
        "第2集 我是霸体",
    ]


def test_build_provider_episode_playlist_prefers_normalized_bilibili_episodes_over_eps() -> None:
    vod = VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫")
    playlist = [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")]
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss148433",
        title="凸变英雄X",
        year="2025",
        raw={
            "season_id": 148433,
            "season_type_name": "国创",
            "episodes": [{"episode_number": 28, "long_title": "答案", "episode_type": "main", "sort": 28}],
            "eps": [{"title": "28", "long_title": ""}],
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert updated[0].episode_display_title == "第28集 答案"


def test_build_provider_episode_playlist_skips_bilibili_candidate_without_confirmed_anime_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="示例动画", vod_year="2025", category_name="动漫")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss999",
        title="示例动画",
        year="2025",
        raw={"season_type_name": "国创", "eps": [{"title": "1", "long_title": "搜索摘要标题"}]},
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is None


def test_build_provider_episode_playlist_maps_bangumi_episode_names() -> None:
    vod = VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="bangumi",
        provider_id="subject:1",
        title="牧神记",
        year="2024",
        raw={
            "episodes": [
                {"sort": 1, "type": 0, "name_cn": "天黑别出门", "name": "Episode 1"},
                {"sort": 2, "type": 0, "name_cn": "我是霸体", "name": "Episode 2"},
            ]
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1集 天黑别出门",
        "第2集 我是霸体",
    ]


def test_build_provider_episode_playlist_sorts_bangumi_titles_by_episode_number_with_late_episode_and_duplicate() -> None:
    vod = VodItem(vod_id="v1", vod_name="仙剑奇侠传三", vod_year="2025", category_name="动漫")
    original_titles = [
        "S01E01.mkv",
        "S01E02.mkv",
        "S01E03.mkv",
        "S01E04.mkv",
        "S01E05.mkv",
        "S01E06.mkv",
        "S01E07.mkv",
        "S01E08.mkv",
        "S01E09.mp4",
        "S01E10.mp4",
        "S01E11.mkv",
        "S01E13.mp4",
        "S01E14.mp4",
        "S01E15.mp4",
        "S01E16.mkv",
        "S01E17.mp4",
        "S01E18.mp4",
        "S01E19.mp4",
        "S01E20.mp4",
        "S01E21.mp4",
        "S01E22.mp4",
        "S01E23.mp4",
        "S01E11.mp4",
        "S01E12.mkv",
    ]
    playlist = [
        PlayItem(title=title, original_title=title, url=f"http://m/{index}.mp4")
        for index, title in enumerate(original_titles, start=1)
    ]
    match = MetadataMatch(
        provider="bangumi",
        provider_id="subject:1",
        title="仙剑奇侠传三",
        year="2025",
        raw={
            "episodes": [
                {"sort": index, "type": 0, "name_cn": f"标题{index}"}
                for index in range(1, 24)
            ]
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.original_title for item in updated] == [
        "S01E01.mkv",
        "S01E02.mkv",
        "S01E03.mkv",
        "S01E04.mkv",
        "S01E05.mkv",
        "S01E06.mkv",
        "S01E07.mkv",
        "S01E08.mkv",
        "S01E09.mp4",
        "S01E10.mp4",
        "S01E11.mkv",
        "S01E12.mkv",
        "S01E13.mp4",
        "S01E14.mp4",
        "S01E15.mp4",
        "S01E16.mkv",
        "S01E17.mp4",
        "S01E18.mp4",
        "S01E19.mp4",
        "S01E20.mp4",
        "S01E21.mp4",
        "S01E22.mp4",
        "S01E23.mp4",
        "S01E11.mp4",
    ]


def test_build_provider_episode_playlist_skips_movie_vod_when_only_type_name_marks_movie() -> None:
    vod = VodItem(vod_id="v1", vod_name="长安的荔枝", vod_year="2025", type_name="电影")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    match = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="长安的荔枝",
        year="2025",
        raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 误匹配标题"}]}]},
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is None


def test_iqiyi_confidence_succeeds_for_bound_iqiyi_candidate() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    candidate = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:bound",
        title="临江仙",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(
        vod,
        playlist,
        candidate,
        preferred_provider="iqiyi",
    ) is True


def test_iqiyi_confidence_succeeds_for_matching_title_year_and_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙 第一季", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="S01E01.mkv", original_title="S01E01.mkv", url="http://m/1.mp4")]
    candidate = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:match",
        title="临江仙 第一季",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, candidate) is True


def test_iqiyi_confidence_accepts_native_site_candidate_with_episode_videos() -> None:
    vod = VodItem(vod_id="v1", vod_name="家业", vod_year="2026", category_name="电视剧")
    playlist = [
        PlayItem(title="01 (1.24 GB)", original_title="01 (1.24 GB)", url="http://m/1.mp4"),
        PlayItem(title="02 (1.14 GB)", original_title="02 (1.14 GB)", url="http://m/2.mp4"),
    ]
    candidate = MetadataMatch(
        provider="iqiyi",
        provider_id="https://www.iqiyi.com/v_227sdi27y7k.html",
        title="家业 正片",
        year="2026",
        raw={
            "siteId": "iqiyi",
            "siteName": "爱奇艺",
            "videos": [
                {"number": "1", "title": "家业第1集", "subtitle": "那我就不做李家人了！"},
                {"number": "2", "title": "家业第2集", "subtitle": "家人才是我的底气"},
            ],
        },
    )

    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, candidate) is True


def test_iqiyi_confidence_rejects_conflicting_year_or_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙 第一季", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="S01E01.mkv", original_title="S01E01.mkv", url="http://m/1.mp4")]
    wrong_year = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:wrong-year",
        title="临江仙 第一季",
        year="2024",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )
    wrong_season = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:wrong-season",
        title="临江仙 第二季",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, wrong_year) is False
    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, wrong_season) is False


def test_resolve_episode_title_source_priority_moves_iqiyi_ahead_of_tmdb_only_for_high_confidence_match() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    iqiyi = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="临江仙",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )
    tmdb = MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")

    assert resolve_episode_title_source_priority(vod, playlist, [iqiyi, tmdb]) == [
        "plugin",
        "bangumi",
        "bilibili",
        "iqiyi",
        "tmdb",
        "tencent",
    ]
    assert resolve_episode_title_source_priority(vod, playlist, [tmdb]) == METADATA_EPISODE_TITLE_SOURCE_PRIORITY
