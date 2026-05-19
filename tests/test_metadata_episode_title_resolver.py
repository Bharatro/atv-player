from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
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
