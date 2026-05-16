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
