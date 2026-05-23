from atv_player.controllers.youtube_controller import YouTubeController
from atv_player.models import AppConfig


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


def test_youtube_controller_loads_subscription_channels_with_cookie_header() -> None:
    class CookieService(FakeYtdlpService):
        def youtube_cookie_header(self) -> str:
            return "SID=direct-cookie"

    requests: list[tuple[str, dict[str, str]]] = []
    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "channelRenderer": {
          "channelId": "UCdirect",
          "title": {"simpleText": "频道A"},
          "thumbnail": {
            "thumbnails": [
              {"url": "https://yt3.googleusercontent.com/avatar=s88"},
              {"url": "https://yt3.googleusercontent.com/avatar=s900"}
            ]
          }
        }
      }
    };
    </script>
    """

    class Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs):
        requests.append((url, dict(kwargs.get("headers") or {})))
        return Response()

    service = CookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=fake_get,
    )

    items, total = controller.load_items("cat_sub_channels", 1)

    assert total == 1
    assert service.flat_calls == []
    assert requests == [
        (
            "https://www.youtube.com/feed/channels",
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cookie": "SID=direct-cookie",
            },
        )
    ]
    assert items[0].vod_id == "yt:channel:UCdirect"
    assert items[0].vod_name == "频道A"
    assert items[0].vod_pic == "https://yt3.googleusercontent.com/avatar=s900"


def test_youtube_controller_extracts_nested_subscription_channel_avatar() -> None:
    class CookieService(FakeYtdlpService):
        def youtube_cookie_header(self) -> str:
            return "SID=direct-cookie"

    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "channelRenderer": {
          "channelId": "UCnested",
          "title": {"simpleText": "嵌套头像频道"},
          "avatar": {
            "decoratedAvatarViewModel": {
              "avatar": {
                "avatarViewModel": {
                  "image": {
                    "sources": [
                      {"url": "https://yt3.googleusercontent.com/nested=s88"},
                      {"url": "https://yt3.googleusercontent.com/nested=s900"}
                    ]
                  }
                }
              }
            }
          }
        }
      }
    };
    </script>
    """

    class Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    service = CookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=lambda *_args, **_kwargs: Response(),
    )

    items, _total = controller.load_items("cat_sub_channels", 1)

    assert service.flat_calls == []
    assert items[0].vod_id == "yt:channel:UCnested"
    assert items[0].vod_pic == "https://yt3.googleusercontent.com/nested=s900"


def test_youtube_controller_does_not_enrich_direct_subscription_channels_with_ytdlp() -> None:
    class CookieService(FakeYtdlpService):
        def youtube_cookie_header(self) -> str:
            return "SID=direct-cookie"

    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "channelRenderer": {
          "channelId": "UCnocover",
          "title": {"simpleText": "无头像频道"}
        }
      }
    };
    </script>
    """

    class Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    service = CookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=lambda *_args, **_kwargs: Response(),
    )

    items, _total = controller.load_items("cat_sub_channels", 1)

    assert service.flat_calls == []
    assert items[0].vod_id == "yt:channel:UCnocover"
    assert items[0].vod_pic == ""


def test_youtube_controller_retries_subscription_channels_after_cookie_refresh() -> None:
    class RefreshableCookieService(FakeYtdlpService):
        def __init__(self) -> None:
            super().__init__()
            self.clear_calls = 0

        def youtube_cookie_header(self) -> str:
            return "SID=fresh-cookie" if self.clear_calls else "SID=stale-cookie"

        def clear_youtube_cookie_header_cache(self) -> None:
            self.clear_calls += 1

    requests: list[str] = []
    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "channelRenderer": {
          "channelId": "UCfresh",
          "title": {"simpleText": "刷新后频道"},
          "thumbnail": {"thumbnails": [{"url": "https://yt3.googleusercontent.com/fresh"}]}
        }
      }
    };
    </script>
    """

    class Response:
        def __init__(self, text: str, status_code: int = 200) -> None:
            self.text = text
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    def fake_get(_url: str, **kwargs):
        cookie = dict(kwargs.get("headers") or {}).get("Cookie", "")
        requests.append(cookie)
        if cookie == "SID=stale-cookie":
            return Response("forbidden", status_code=403)
        return Response(html)

    service = RefreshableCookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=fake_get,
    )

    items, total = controller.load_items("cat_sub_channels", 1)

    assert total == 1
    assert service.clear_calls == 1
    assert service.flat_calls == []
    assert requests == ["SID=stale-cookie", "SID=fresh-cookie"]
    assert items[0].vod_id == "yt:channel:UCfresh"


def test_youtube_controller_does_not_retry_direct_login_list_without_cookie() -> None:
    class EmptyCookieService(FakeYtdlpService):
        def __init__(self) -> None:
            super().__init__()
            self.cookie_calls = 0
            self.clear_calls = 0

        def youtube_cookie_header(self) -> str:
            self.cookie_calls += 1
            return ""

        def clear_youtube_cookie_header_cache(self) -> None:
            self.clear_calls += 1

        def extract_flat_playlist(self, url: str, *, page: int = 1, page_size: int = 30):
            self.flat_calls.append((url, page, page_size))
            return [
                {
                    "id": "UCabc123",
                    "title": "频道A",
                    "url": "https://www.youtube.com/channel/UCabc123",
                    "thumbnail": "https://yt3.googleusercontent.com/channel=s900",
                    "ie_key": "YoutubeTab",
                }
            ]

    http_calls = 0

    def fake_get(*_args, **_kwargs):
        nonlocal http_calls
        http_calls += 1
        raise AssertionError("direct HTTP should not run without a cookie")

    service = EmptyCookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=fake_get,
    )

    items, total = controller.load_items("cat_sub_channels", 1)

    assert http_calls == 0
    assert service.clear_calls == 0
    assert service.flat_calls == [
        ("https://www.youtube.com/feed/channels", 1, 30),
    ]
    assert total == 1
    assert items[0].vod_id == "yt:channel:UCabc123"


def test_youtube_controller_directly_loads_login_video_lists_with_cookie() -> None:
    class CookieService(FakeYtdlpService):
        def youtube_cookie_header(self) -> str:
            return "SID=direct-cookie"

    requests: list[tuple[str, str]] = []
    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "videoRenderer": {
          "videoId": "vid12345678",
          "title": {"runs": [{"text": "登录视频"}]},
          "thumbnail": {
            "thumbnails": [
              {"url": "https://i.ytimg.com/vi/vid12345678/hqdefault.jpg"}
            ]
          },
          "ownerText": {"runs": [{"text": "频道A"}]},
          "lengthText": {"simpleText": "12:34"}
        }
      }
    };
    </script>
    """

    class Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs):
        requests.append((url, dict(kwargs.get("headers") or {}).get("Cookie", "")))
        return Response()

    service = CookieService()
    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=service,
        http_get=fake_get,
    )

    expected_urls = {
        "cat_sub_feed": "https://www.youtube.com/feed/subscriptions",
        "cat_history": "https://www.youtube.com/feed/history",
        "cat_watch_later": "https://www.youtube.com/playlist?list=WL",
    }
    for category_id, expected_url in expected_urls.items():
        items, total = controller.load_items(category_id, 1)

        assert total == 1
        assert items[0].vod_id == "yt:video:vid12345678"
        assert items[0].vod_name == "登录视频"
        assert items[0].vod_pic == "https://i.ytimg.com/vi/vid12345678/hqdefault.jpg"
        assert items[0].vod_remarks == "频道A | 12:34"
        assert requests[-1] == (expected_url, "SID=direct-cookie")

    assert service.flat_calls == []


def test_youtube_controller_caches_direct_login_lists_briefly() -> None:
    class CookieService(FakeYtdlpService):
        def youtube_cookie_header(self) -> str:
            return "SID=direct-cookie"

    current_time = 1000.0
    request_count = 0
    html = """
    <script>
    var ytInitialData = {
      "contents": {
        "videoRenderer": {
          "videoId": "cached12345",
          "title": {"simpleText": "缓存视频"},
          "thumbnail": {"thumbnails": [{"url": "https://i.ytimg.com/vi/cached12345/hqdefault.jpg"}]}
        }
      }
    };
    </script>
    """

    class Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    def fake_get(_url: str, **_kwargs):
        nonlocal request_count
        request_count += 1
        return Response()

    def fake_now() -> float:
        return current_time

    controller = YouTubeController(
        AppConfig(youtube_cookie_browser="chrome"),
        yt_dlp_service=CookieService(),
        http_get=fake_get,
        now=fake_now,
    )

    first_items, _first_total = controller.load_items("cat_sub_feed", 1)
    second_items, _second_total = controller.load_items("cat_sub_feed", 1)

    assert request_count == 1
    assert [item.vod_id for item in second_items] == [item.vod_id for item in first_items]

    current_time = 1061.0
    controller.load_items("cat_sub_feed", 1)

    assert request_count == 2
