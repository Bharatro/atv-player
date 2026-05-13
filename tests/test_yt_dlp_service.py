from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from atv_player.models import PlayItem, VodItem


@pytest.fixture
def service():
    from atv_player.yt_dlp_service import YtdlpPlaybackService
    svc = YtdlpPlaybackService()
    return svc


@pytest.fixture
def mock_ytdlp_module():
    mock_module = MagicMock()
    mock_module.utils.GeoRestrictedError = type("GeoRestrictedError", (Exception,), {})
    mock_module.utils.ExtractorError = type("ExtractorError", (Exception,), {})
    mock_module.utils.DownloadError = type("DownloadError", (Exception,), {})
    with patch.dict("sys.modules", {"yt_dlp": mock_module, "yt_dlp.utils": mock_module.utils}):
        yield mock_module


def _sample_info(**overrides):
    info = {
        "id": "test123",
        "title": "Test Video",
        "thumbnail": "https://img.test/thumb.jpg",
        "description": "A test video description",
        "duration": 300,
        "extractor": "youtube",
        "url": "https://stream.test/direct.mp4",
        "http_headers": {"Referer": "https://www.youtube.com/", "User-Agent": "test"},
        "formats": [
            {
                "format_id": "1080",
                "url": "https://stream.test/1080.mp4",
                "height": 1080,
                "width": 1920,
                "tbr": 5000,
                "vcodec": "avc1",
                "acodec": "mp4a",
            },
            {
                "format_id": "720",
                "url": "https://stream.test/720.mp4",
                "height": 720,
                "width": 1280,
                "tbr": 2500,
                "vcodec": "avc1",
                "acodec": "mp4a",
            },
            {
                "format_id": "360",
                "url": "https://stream.test/360.mp4",
                "height": 360,
                "width": 640,
                "tbr": 800,
                "vcodec": "avc1",
                "acodec": "mp4a",
            },
            {
                "format_id": "audio",
                "url": "https://stream.test/audio.mp4",
                "height": None,
                "vcodec": "none",
                "acodec": "mp4a",
            },
        ],
        "subtitles": {
            "en": [{"url": "https://sub.test/en.srt", "ext": "srt"}],
            "zh-Hans": [{"url": "https://sub.test/zh.srt", "ext": "srt"}],
        },
        "automatic_captions": {
            "ja": [{"url": "https://sub.test/ja_auto.vtt", "ext": "vtt"}],
        },
    }
    info.update(overrides)
    return info


class TestIsAvailable:
    def test_not_installed(self, service):
        with patch("builtins.__import__", side_effect=ImportError("no yt_dlp")):
            service._ytdlp_module = ...
            assert service.is_available() is False

    def test_installed(self, service, mock_ytdlp_module):
        service._ytdlp_module = ...
        assert service.is_available() is True


class TestCanResolve:
    def test_known_domain(self, service, mock_ytdlp_module):
        assert service.can_resolve("https://www.youtube.com/watch?v=test") is True
        assert service.can_resolve("https://twitter.com/user/status/123") is True
        assert service.can_resolve("https://x.com/user/status/123") is True
        assert service.can_resolve("https://youtu.be/test123") is True

    def test_unknown_domain(self, service, mock_ytdlp_module):
        assert service.can_resolve("https://example.com/video.mp4") is False
        assert service.can_resolve("https://random-site.org/watch/123") is False

    def test_empty_url(self, service, mock_ytdlp_module):
        assert service.can_resolve("") is False
        assert service.can_resolve("  ") is False

    def test_not_available(self, service):
        service._ytdlp_module = None
        assert service.can_resolve("https://www.youtube.com/watch?v=test") is False


class TestResolve:
    def test_prefers_requested_formats_video_and_audio_pair_over_master_url(self, service, mock_ytdlp_module):
        info = _sample_info(
            url="https://stream.test/master.m3u8",
            formats=[],
            requested_formats=[
                {
                    "format_id": "399",
                    "url": "https://stream.test/video-1080.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 5000,
                    "vcodec": "av01.0.09M.08",
                    "acodec": "none",
                    "ext": "mp4",
                },
                {
                    "format_id": "251",
                    "url": "https://stream.test/audio.webm",
                    "tbr": 126,
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "webm",
                    "audio_channels": 2,
                },
            ],
        )
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url.startswith("data:application/dash+xml;base64,")
        assert result.audio_url == ""
        manifest = base64.b64decode(result.url.partition(",")[2]).decode("utf-8")
        assert "<Representation id=\"399\"" in manifest
        assert "<Representation id=\"251\"" in manifest
        assert "<BaseURL>https://stream.test/video-1080.mp4</BaseURL>" in manifest
        assert "<BaseURL>https://stream.test/audio.webm</BaseURL>" in manifest

    def test_prefers_stable_avc_stream_pair_over_requested_av1_pair_at_same_height(self, service, mock_ytdlp_module):
        info = _sample_info(
            url="https://stream.test/master.m3u8",
            requested_formats=[
                {
                    "format_id": "399",
                    "url": "https://stream.test/video-1080-av1.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 2600,
                    "vcodec": "av01.0.09M.08",
                    "acodec": "none",
                    "ext": "mp4",
                },
                {
                    "format_id": "251",
                    "url": "https://stream.test/audio-251.webm",
                    "tbr": 126,
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "webm",
                },
            ],
            formats=[
                {
                    "format_id": "299",
                    "url": "https://stream.test/video-1080-avc.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 4800,
                    "vcodec": "avc1.64002a",
                    "acodec": "none",
                    "ext": "mp4",
                },
                {
                    "format_id": "303",
                    "url": "https://stream.test/video-1080-vp9.webm",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 3200,
                    "vcodec": "vp9",
                    "acodec": "none",
                    "ext": "webm",
                },
                {
                    "format_id": "399",
                    "url": "https://stream.test/video-1080-av1.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 2600,
                    "vcodec": "av01.0.09M.08",
                    "acodec": "none",
                    "ext": "mp4",
                },
                {
                    "format_id": "251",
                    "url": "https://stream.test/audio-251.webm",
                    "tbr": 126,
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "webm",
                },
                {
                    "format_id": "140",
                    "url": "https://stream.test/audio-140.m4a",
                    "tbr": 128,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                },
            ],
        )
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url.startswith("data:application/dash+xml;base64,")
        assert result.audio_url == ""
        manifest = base64.b64decode(result.url.partition(",")[2]).decode("utf-8")
        assert "<Representation id=\"299\"" in manifest
        assert "<Representation id=\"251\"" in manifest
        assert "<BaseURL>https://stream.test/video-1080-avc.mp4</BaseURL>" in manifest
        assert "<BaseURL>https://stream.test/audio-251.webm</BaseURL>" in manifest

    def test_uses_1080p_cap_for_initial_startup_resolve(self, service, mock_ytdlp_module):
        info = _sample_info()
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        service.resolve("https://www.youtube.com/watch?v=test123")

        options = mock_ytdlp_module.YoutubeDL.call_args.args[0]
        assert options["format"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best"

    def test_prefers_muxed_fallback_url_when_info_url_missing(self, service, mock_ytdlp_module):
        info = _sample_info(
            url="",
            formats=[
                {
                    "format_id": "1080-video",
                    "url": "https://stream.test/1080-video.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 5000,
                    "vcodec": "avc1",
                    "acodec": "none",
                },
                {
                    "format_id": "720-muxed",
                    "url": "https://stream.test/720-muxed.mp4",
                    "height": 720,
                    "width": 1280,
                    "tbr": 2500,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                },
            ],
        )
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://stream.test/720-muxed.mp4"

    def test_uses_cached_result_before_ttl_expires(self, mock_ytdlp_module):
        from atv_player.yt_dlp_service import YtdlpPlaybackService

        info = _sample_info()
        extractor = MagicMock(return_value=info)
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=extractor)
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        clock = {"now": 100.0}
        service = YtdlpPlaybackService(ttl_seconds=300.0, now=lambda: clock["now"])

        first = service.resolve("https://www.youtube.com/watch?v=test123")
        second = service.resolve("https://www.youtube.com/watch?v=test123")

        assert first.url == "https://stream.test/direct.mp4"
        assert second.url == "https://stream.test/direct.mp4"
        assert extractor.call_count == 1

    def test_re_extracts_after_cache_expiry(self, mock_ytdlp_module):
        from atv_player.yt_dlp_service import YtdlpPlaybackService

        info = _sample_info()
        extractor = MagicMock(return_value=info)
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=extractor)
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        clock = {"now": 100.0}
        service = YtdlpPlaybackService(ttl_seconds=5.0, now=lambda: clock["now"])

        service.resolve("https://www.youtube.com/watch?v=test123")
        clock["now"] = 110.0
        service.resolve("https://www.youtube.com/watch?v=test123")

        assert extractor.call_count == 2

    def test_success(self, service, mock_ytdlp_module):
        info = _sample_info()
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://stream.test/direct.mp4"
        assert result.title == "Test Video"
        assert result.thumbnail == "https://img.test/thumb.jpg"
        assert result.description == "A test video description"
        assert result.duration_seconds == 300
        assert result.extractor == "youtube"
        assert result.headers == {"Referer": "https://www.youtube.com/", "User-Agent": "test"}

    def test_qualities(self, service, mock_ytdlp_module):
        info = _sample_info()
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert len(result.qualities) == 3
        assert result.qualities[0].height == 1080
        assert result.qualities[1].height == 720
        assert result.qualities[2].height == 360
        # audio-only format filtered out
        for q in result.qualities:
            assert q.height >= 360

    def test_subtitles(self, service, mock_ytdlp_module):
        info = _sample_info()
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert len(result.subtitles) == 2
        names = [s.name for s in result.subtitles]
        assert any("英文" in n for n in names)
        assert any("简体中文" in n for n in names)
        # Japanese is filtered out (only zh/en kept)

    def test_geo_restricted(self, service, mock_ytdlp_module):
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(
                extract_info=MagicMock(side_effect=mock_ytdlp_module.utils.GeoRestrictedError("geo"))
            )
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="地区限制"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_extractor_error(self, service, mock_ytdlp_module):
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(
                extract_info=MagicMock(
                    side_effect=mock_ytdlp_module.utils.ExtractorError("not found")
                )
            )
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="无法获取视频"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_no_url(self, service, mock_ytdlp_module):
        info = _sample_info(url="", formats=[])
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="未获取到播放地址"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_no_result(self, service, mock_ytdlp_module):
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=None))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="未返回结果"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_not_available(self, service):
        service._ytdlp_module = None
        with pytest.raises(ValueError, match="未安装"):
            service.resolve("https://www.youtube.com/watch?v=test123")


class TestResolveToPlayItem:
    def test_prefers_current_resolved_height_over_highest_available_quality(self, service, mock_ytdlp_module):
        info = _sample_info(
            height=1080,
            formats=[
                {
                    "format_id": "2160-video",
                    "url": "https://stream.test/2160-video.mp4",
                    "height": 2160,
                    "width": 3840,
                    "tbr": 12000,
                    "vcodec": "vp9",
                    "acodec": "none",
                },
                {
                    "format_id": "1080-video",
                    "url": "https://stream.test/1080-video.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 5000,
                    "vcodec": "avc1",
                    "acodec": "none",
                },
                {
                    "format_id": "720-muxed",
                    "url": "https://stream.test/720-muxed.mp4",
                    "height": 720,
                    "width": 1280,
                    "tbr": 2500,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                },
            ],
        )
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        _, item = service.resolve_to_play_item("https://www.youtube.com/watch?v=test123")

        assert [quality.id for quality in item.playback_qualities] == [
            "ytdlp_2160",
            "ytdlp_1080",
            "ytdlp_720",
        ]
        assert item.selected_playback_quality_id == "ytdlp_1080"

    def test_success(self, service, mock_ytdlp_module):
        info = _sample_info()
        mock_ytdlp_module.YoutubeDL.return_value.__enter__ = MagicMock(
            return_value=MagicMock(extract_info=MagicMock(return_value=info))
        )
        mock_ytdlp_module.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        vod, item = service.resolve_to_play_item("https://www.youtube.com/watch?v=test123")

        assert isinstance(vod, VodItem)
        assert isinstance(item, PlayItem)
        assert vod.vod_name == "Test Video"
        assert vod.vod_pic == "https://img.test/thumb.jpg"
        assert item.url == "https://stream.test/direct.mp4"
        assert item.original_url == "https://www.youtube.com/watch?v=test123"
        assert len(item.playback_qualities) == 3
        assert len(item.external_subtitles) == 2
        assert item.duration_seconds == 300
        assert item.selected_playback_quality_id == "ytdlp_1080"


class TestBuildQualityOptions:
    def test_keeps_video_only_formats_for_quality_ladder(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {
                    "format_id": "1080-video",
                    "url": "https://test/1080-video.mp4",
                    "height": 1080,
                    "vcodec": "avc1",
                    "acodec": "none",
                },
                {
                    "format_id": "720-muxed",
                    "url": "https://test/720-muxed.mp4",
                    "height": 720,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                },
            ]
        }
        result = _build_quality_options(info)
        assert [option.id for option in result] == ["ytdlp_1080", "ytdlp_720"]

    def test_filters_low_quality(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "240", "url": "https://test/240.mp4", "height": 240, "vcodec": "avc1"},
                {"format_id": "720", "url": "https://test/720.mp4", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        assert len(result) == 1
        assert result[0].height == 720

    def test_filters_audio_only(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "audio", "url": "https://test/a.mp4", "height": None, "vcodec": "none"},
                {"format_id": "720", "url": "https://test/720.mp4", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        assert len(result) == 1

    def test_deduplicates(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "720", "url": "https://test/720.mp4", "height": 720, "vcodec": "avc1"},
                {"format_id": "720", "url": "https://test/720b.mp4", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        assert len(result) == 1

    def test_sorted_by_height_desc(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "480", "url": "https://test/480.mp4", "height": 480, "vcodec": "avc1"},
                {"format_id": "1080", "url": "https://test/1080.mp4", "height": 1080, "vcodec": "avc1"},
                {"format_id": "720", "url": "https://test/720.mp4", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        heights = [q.height for q in result]
        assert heights == [1080, 720, 480]

    def test_no_url_still_exposes_height_for_re_resolve(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "720", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        assert [option.id for option in result] == ["ytdlp_720"]


class TestBuildSubtitleOptions:
    def test_manual_and_auto(self):
        from atv_player.yt_dlp_service import _build_subtitle_options
        info = {
            "subtitles": {
                "en": [{"url": "https://sub/en.srt", "ext": "srt"}],
            },
            "automatic_captions": {
                "zh-Hans": [{"url": "https://sub/zh.vtt", "ext": "vtt"}],
            },
        }
        result = _build_subtitle_options(info)
        assert len(result) == 2
        en_sub = next(s for s in result if s.lang == "en")
        assert "自动生成" not in en_sub.name
        zh_sub = next(s for s in result if s.lang == "zh-Hans")
        assert "自动生成" in zh_sub.name

    def test_deduplicates_urls(self):
        from atv_player.yt_dlp_service import _build_subtitle_options
        info = {
            "subtitles": {
                "en": [{"url": "https://sub/en.srt", "ext": "srt"}],
            },
            "automatic_captions": {
                "en": [{"url": "https://sub/en.srt", "ext": "srt"}],
            },
        }
        result = _build_subtitle_options(info)
        assert len(result) == 1

    def test_empty(self):
        from atv_player.yt_dlp_service import _build_subtitle_options
        info: dict = {}
        result = _build_subtitle_options(info)
        assert len(result) == 0
