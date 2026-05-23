from atv_player.controllers.youtube_controller import YouTubeController
from atv_player.models import AppConfig, PlaybackDetailFieldAction


class FakeYtdlpService:
    def __init__(self) -> None:
        self.flat_calls: list[tuple[str, int, int]] = []

    def is_available(self) -> bool:
        return True

    def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
        self.flat_calls.append((url, page, page_size))
        return [
            {
                "id": "abc123",
                "title": "订阅视频",
                "url": "https://www.youtube.com/watch?v=abc123",
                "thumbnail": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
                "channel": "频道",
                "duration_string": "3:21",
                "ie_key": "Youtube",
            }
        ]


class ChannelYtdlpService(FakeYtdlpService):
    def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
        self.flat_calls.append((url, page, page_size))
        return [
            {
                "id": "island12345",
                "title": "Survive 30 Days On An Island With Your Ex, Win $250,000",
                "url": "https://www.youtube.com/watch?v=island12345",
                "thumbnail": "https://i.ytimg.com/vi/island12345/hqdefault.jpg",
                "channel": "MrBeast 野兽先生",
                "duration_string": "26:10",
                "ie_key": "Youtube",
            }
            ,
            {
                "id": "train123456",
                "title": "I Built a Train To Cross America",
                "url": "https://www.youtube.com/watch?v=train123456",
                "channel": "MrBeast 野兽先生",
                "duration_string": "17:10",
                "ie_key": "Youtube",
            },
        ]


def test_youtube_controller_hides_login_categories_without_cookie_browser() -> None:
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser=""),
        yt_dlp_service=FakeYtdlpService(),
    )

    category_names = [category.type_name for category in controller.load_categories()]

    assert "我的订阅视频" not in category_names
    assert "播放历史" not in category_names
    assert "首页推荐" in category_names


def test_youtube_controller_shows_login_categories_with_cookie_browser() -> None:
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=FakeYtdlpService(),
    )

    categories = controller.load_categories()

    assert [category.type_name for category in categories[:4]] == [
        "我的订阅视频",
        "我的订阅频道",
        "播放历史",
        "稍后再看",
    ]


def test_youtube_controller_loads_login_feed_through_ytdlp_shortcut() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
    )

    items, total = controller.load_items("cat_sub_feed", 1)

    assert service.flat_calls == [(":ytsubs", 1, 30)]
    assert total == 1
    assert items[0].vod_id == "yt:video:abc123"
    assert items[0].vod_name == "订阅视频"
    assert items[0].vod_remarks == "频道 | 3:21"


def test_youtube_controller_build_request_accepts_bare_channel_id_from_history() -> None:
    service = ChannelYtdlpService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
    )

    request = controller.build_request("UCX6OQ3DkcsbYNE6H8uQQuVA")

    assert service.flat_calls == [
        ("https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA/videos", 1, 200)
    ]
    assert request.vod.vod_id == "yt:channel:UCX6OQ3DkcsbYNE6H8uQQuVA"
    assert request.vod.vod_name == "MrBeast 野兽先生"
    assert request.source_groups == []
    assert request.playlists == [request.playlist]
    assert [item.title for item in request.playlist] == [
        "Survive 30 Days On An Island With Your Ex, Win $250,000",
        "I Built a Train To Cross America",
    ]
    assert request.playlist[1].url == ""
    assert request.playlist[1].vod_id == "yt:video:train123456"


def test_youtube_controller_synthesizes_video_thumbnails_when_flat_items_omit_them() -> None:
    service = ChannelYtdlpService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
    )

    items, _total = controller.load_items("cat_sub_feed", 1)

    assert items[1].vod_id == "yt:video:train123456"
    assert items[1].vod_pic == "https://i.ytimg.com/vi/train123456/hqdefault.jpg"


def test_youtube_controller_searches_all_result_types_for_channels() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
    )

    controller.search_items("openai", 1)

    assert service.flat_calls == [("ytsearchall:openai", 1, 30)]


def test_youtube_controller_loads_category_through_ytdlp_search_all_scheme() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
    )

    controller.load_items("cat_recommend", 1)

    assert service.flat_calls == [("ytsearchall:推荐", 1, 30)]


def test_youtube_controller_uses_last_ytdlp_thumbnail_candidate() -> None:
    class ThumbnailService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "abc123",
                    "title": "视频",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "thumbnails": [
                        {"url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg", "width": 480},
                        {"url": "https://i.ytimg.com/vi/abc123/hq720.jpg", "width": 720},
                    ],
                    "ie_key": "Youtube",
                }
            ]

    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=ThumbnailService(),
    )

    items, _total = controller.load_items("cat_recommend", 1)

    assert items[0].vod_pic == "https://i.ytimg.com/vi/abc123/hq720.jpg"


def test_youtube_controller_normalizes_protocol_relative_ytdlp_thumbnails() -> None:
    class ThumbnailService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "abc123",
                    "title": "视频",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "thumbnail": "//yt3.googleusercontent.com/avatar=s176",
                    "ie_key": "Youtube",
                }
            ]

    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=ThumbnailService(),
    )

    items, _total = controller.load_items("cat_recommend", 1)

    assert items[0].vod_pic == "https://yt3.googleusercontent.com/avatar=s176"


def test_youtube_controller_uses_ytdlp_metadata_for_video_detail_title() -> None:
    class VideoDetailService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "abc123",
                    "title": "真实 YouTube 标题",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "thumbnail": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
                    "channel": "频道",
                    "duration_string": "3:21",
                    "ie_key": "Youtube",
                }
            ]

    service = VideoDetailService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
    )

    request = controller.build_request("yt:video:abc123")

    assert service.flat_calls == [("https://www.youtube.com/watch?v=abc123", 1, 1)]
    assert request.vod.vod_name == "真实 YouTube 标题"
    assert request.playlist[0].title == "真实 YouTube 标题"


def test_youtube_controller_builds_fast_video_request_from_card_without_loading_detail() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
    )
    card = type(
        "Card",
        (),
        {
            "vod_id": "yt:video:abc123",
            "vod_name": "卡片标题",
            "vod_pic": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
            "vod_remarks": "频道 | 3:21",
            "type_name": "",
            "category_name": "",
            "vod_content": "",
        },
    )()

    request = controller.build_request_from_item(card)

    assert service.flat_calls == []
    assert request.vod.vod_name == "卡片标题"
    assert request.vod.vod_pic == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    assert request.playlist[0].title == "卡片标题"
    assert request.playlist[0].original_url == "https://www.youtube.com/watch?v=abc123"
    assert request.playback_loader is not None
    assert request.async_playback_loader is True


def test_youtube_controller_builds_youtube_detail_fields_from_ytdlp_metadata() -> None:
    class VideoDetailService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "abc123",
                    "title": "Harness Engineering 到底是什么？概念、实战与争议，一次全部讲清楚",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "channel": "马克的技术工作坊",
                    "upload_date": "20260505",
                    "duration_string": "37:24",
                    "view_count": 52000,
                    "like_count": 1501,
                    "comment_count": 73,
                    "categories": ["Science & Technology"],
                    "tags": ["Harness Engineering", "AI"],
                    "description": "本期介绍 Harness Engineering 的概念与实践。",
                    "ie_key": "Youtube",
                }
            ]

    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=VideoDetailService(),
    )

    request = controller.build_request("yt:video:abc123")

    assert request.vod.detail_style == "youtube"
    assert [(field.label, field.value) for field in request.vod.detail_fields] == [
        ("VID", "abc123"),
        ("频道", "马克的技术工作坊"),
        ("发布", "2026-05-05"),
        ("时长", "37:24"),
        ("播放", "5.2万"),
        ("点赞", "1501"),
        ("评论", "73"),
        ("分类", "Science & Technology"),
        ("标签", "Harness Engineering / AI"),
        ("简介", "本期介绍 Harness Engineering 的概念与实践。"),
    ]
    assert request.playlist[0].detail_fields == request.vod.detail_fields


def test_youtube_controller_adds_clickable_vid_to_youtube_detail_fields() -> None:
    class VideoDetailService(FakeYtdlpService):
        def extract_flat_playlist(
            self,
            url: str,
            *,
            page: int = 1,
            page_size: int = 30,
        ):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "abc123xyz89",
                    "title": "YouTube 视频",
                    "url": "https://www.youtube.com/watch?v=abc123xyz89",
                    "channel": "频道",
                    "ie_key": "Youtube",
                }
            ]

    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=VideoDetailService(),
    )

    request = controller.build_request("yt:video:abc123xyz89")

    vid_field = next(
        field for field in request.vod.detail_fields if field.label == "VID"
    )
    assert vid_field.value == "abc123xyz89"
    assert vid_field.value_parts[0].action == PlaybackDetailFieldAction(
        type="link",
        value="https://www.youtube.com/watch?v=abc123xyz89",
    )
    assert request.playlist[0].detail_fields == request.vod.detail_fields


def test_youtube_controller_maps_subscription_channel_urls() -> None:
    class ChannelService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "title": "频道A",
                    "url": "https://www.youtube.com/@channel-a",
                    "ie_key": "YoutubeTab",
                }
            ]

    service = ChannelService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
    )

    items, _total = controller.load_items("cat_sub_channels", 1)

    assert service.flat_calls == [
        ("https://www.youtube.com/feed/channels", 1, 30),
        ("https://www.youtube.com/@channel-a", 1, 1),
    ]
    assert items[0].vod_id == "yt:channel:https://www.youtube.com/@channel-a"
    assert items[0].vod_remarks == "频道"


def test_youtube_controller_enriches_subscription_channel_thumbnails() -> None:
    class ChannelService(FakeYtdlpService):
        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            if url == "https://www.youtube.com/feed/channels":
                return [
                    {
                        "title": "频道A",
                        "url": "https://www.youtube.com/@channel-a",
                        "ie_key": "YoutubeTab",
                    }
                ]
            return [
                {
                    "title": "频道A - Videos",
                    "url": "https://www.youtube.com/@channel-a/videos",
                    "channel": "频道A",
                    "thumbnails": [
                        {"url": "https://yt3.googleusercontent.com/banner=w1060", "id": "banner"},
                        {
                            "url": "https://yt3.googleusercontent.com/avatar=s900",
                            "id": "avatar",
                            "width": 900,
                            "height": 900,
                        },
                    ],
                    "ie_key": "YoutubeTab",
                }
            ]

    service = ChannelService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
    )

    items, _total = controller.load_items("cat_sub_channels", 1)

    assert service.flat_calls == [
        ("https://www.youtube.com/feed/channels", 1, 30),
        ("https://www.youtube.com/@channel-a", 1, 1),
    ]
    assert items[0].vod_pic == "https://yt3.googleusercontent.com/avatar=s900"
