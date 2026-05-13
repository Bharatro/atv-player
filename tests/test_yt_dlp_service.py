from __future__ import annotations

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

    def test_no_url_skipped(self):
        from atv_player.yt_dlp_service import _build_quality_options
        info = {
            "formats": [
                {"format_id": "720", "height": 720, "vcodec": "avc1"},
            ]
        }
        result = _build_quality_options(info)
        assert len(result) == 0


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
