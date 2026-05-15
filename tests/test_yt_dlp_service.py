from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from atv_player.models import PlayItem, VodItem


@pytest.fixture(autouse=True)
def stub_system_ytdlp(monkeypatch):
    monkeypatch.setattr("atv_player.yt_dlp_service.resolve_system_ytdlp_path", lambda: "/usr/bin/yt-dlp")


@pytest.fixture
def service():
    from atv_player.yt_dlp_service import YtdlpPlaybackService
    svc = YtdlpPlaybackService()
    return svc


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


def _stub_extract_info(monkeypatch, service, payload):
    calls: list[tuple[str, int | None]] = []

    def fake_extract_info(url: str, max_height: int | None):
        calls.append((url, max_height))
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(service, "_extract_info_via_command", fake_extract_info)
    return calls


class TestIsAvailable:
    def test_not_installed(self, service):
        service._ytdlp_path = None
        assert service.is_available() is True

    def test_returns_false_when_system_ytdlp_missing(self, monkeypatch, service):
        service._ytdlp_path = None
        monkeypatch.setattr("atv_player.yt_dlp_service.resolve_system_ytdlp_path", lambda: "")
        assert service.is_available() is False

    def test_extract_info_via_command_includes_browser_cookies(self, monkeypatch, service):
        monkeypatch.setenv("ATV_YTDLP_COOKIES_FROM_BROWSER", "chrome")
        run_calls: list[list[str]] = []

        def fake_run(command, **_kwargs):
            run_calls.append(command)
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(_sample_info()),
                stderr="",
            )

        monkeypatch.setattr("atv_player.yt_dlp_service.subprocess.run", fake_run)

        result = service._extract_info_via_command("https://www.youtube.com/watch?v=test123", 1080)

        assert result["id"] == "test123"
        command = run_calls[0]
        assert "--cookies-from-browser" in command
        assert command[command.index("--cookies-from-browser") + 1] == "chrome"


class TestCanResolve:
    def test_known_domain(self, service):
        assert service.can_resolve("https://www.youtube.com/watch?v=test") is True
        assert service.can_resolve("https://twitter.com/user/status/123") is True
        assert service.can_resolve("https://x.com/user/status/123") is True
        assert service.can_resolve("https://youtu.be/test123") is True

    def test_unknown_domain(self, service):
        assert service.can_resolve("https://example.com/video.mp4") is False
        assert service.can_resolve("https://random-site.org/watch/123") is False

    def test_empty_url(self, service):
        assert service.can_resolve("") is False
        assert service.can_resolve("  ") is False

    def test_not_available(self, monkeypatch, service):
        service._ytdlp_path = None
        monkeypatch.setattr("atv_player.yt_dlp_service.resolve_system_ytdlp_path", lambda: "")
        assert service.can_resolve("https://www.youtube.com/watch?v=test") is False


class TestResolve:
    def test_prefers_requested_formats_video_and_audio_pair_over_master_url(self, monkeypatch, service):
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
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://www.youtube.com/watch?v=test123"
        assert result.audio_url == ""
        assert result.ytdl_format == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best"

    def test_prefers_mp4a_audio_pair_with_stable_avc_mp4_video_at_same_height(self, monkeypatch, service):
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
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://www.youtube.com/watch?v=test123"
        assert result.audio_url == ""
        assert result.ytdl_format == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best"

    def test_embeds_segment_base_ranges_in_generated_dash_manifest(self, monkeypatch, service):
        info = _sample_info(
            extractor="vimeo",
            url="https://stream.test/master.m3u8",
            requested_formats=[
                {
                    "format_id": "299",
                    "url": "https://stream.test/video-1080-avc.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 4800,
                    "vcodec": "avc1.64002a",
                    "acodec": "none",
                    "ext": "mp4",
                    "init_range": {"start": "0", "end": "737"},
                    "index_range": {"start": "738", "end": "1425"},
                },
                {
                    "format_id": "140",
                    "url": "https://stream.test/audio-140.m4a",
                    "tbr": 128,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                    "init_range": {"start": "0", "end": "701"},
                    "index_range": {"start": "702", "end": "1189"},
                },
            ],
            formats=[],
        )
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        manifest = base64.b64decode(result.url.partition(",")[2]).decode("utf-8")
        assert '<SegmentBase indexRange="738-1425"><Initialization range="0-737"/></SegmentBase>' in manifest
        assert '<SegmentBase indexRange="702-1189"><Initialization range="0-701"/></SegmentBase>' in manifest

    def test_uses_1080p_cap_for_initial_startup_resolve(self, monkeypatch, service):
        info = _sample_info()
        calls = _stub_extract_info(monkeypatch, service, info)

        service.resolve("https://www.youtube.com/watch?v=test123")

        assert calls == [("https://www.youtube.com/watch?v=test123", 1080)]

    def test_prefers_muxed_fallback_url_when_info_url_missing(self, monkeypatch, service):
        info = _sample_info(
            extractor="vimeo",
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
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://stream.test/720-muxed.mp4"

    def test_uses_cached_result_before_ttl_expires(self, monkeypatch):
        from atv_player.yt_dlp_service import YtdlpPlaybackService

        info = _sample_info()
        clock = {"now": 100.0}
        service = YtdlpPlaybackService(ttl_seconds=300.0, now=lambda: clock["now"])
        calls = _stub_extract_info(monkeypatch, service, info)

        first = service.resolve("https://www.youtube.com/watch?v=test123")
        second = service.resolve("https://www.youtube.com/watch?v=test123")

        assert first.url == "https://www.youtube.com/watch?v=test123"
        assert second.url == "https://www.youtube.com/watch?v=test123"
        assert len(calls) == 1

    def test_re_extracts_after_cache_expiry(self, monkeypatch):
        from atv_player.yt_dlp_service import YtdlpPlaybackService

        info = _sample_info()
        clock = {"now": 100.0}
        service = YtdlpPlaybackService(ttl_seconds=5.0, now=lambda: clock["now"])
        calls = _stub_extract_info(monkeypatch, service, info)

        service.resolve("https://www.youtube.com/watch?v=test123")
        clock["now"] = 110.0
        service.resolve("https://www.youtube.com/watch?v=test123")

        assert len(calls) == 2

    def test_success(self, monkeypatch, service):
        info = _sample_info()
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.url == "https://www.youtube.com/watch?v=test123"
        assert result.audio_url == ""
        assert result.title == "Test Video"
        assert result.thumbnail == "https://img.test/thumb.jpg"
        assert result.description == "A test video description"
        assert result.duration_seconds == 300
        assert result.extractor == "youtube"
        assert result.headers == {"Referer": "https://www.youtube.com/", "User-Agent": "test"}
        assert result.selected_quality_id == "ytdlp_1080"
        assert result.ytdl_format == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best"

    def test_prefers_selected_format_http_headers_when_top_level_headers_missing(self, monkeypatch, service):
        info = _sample_info(
            http_headers={},
            requested_formats=[
                {
                    "format_id": "299",
                    "url": "https://stream.test/video-1080-avc.mp4",
                    "height": 1080,
                    "width": 1920,
                    "tbr": 4800,
                    "vcodec": "avc1.64002a",
                    "acodec": "none",
                    "ext": "mp4",
                    "http_headers": {
                        "Referer": "https://www.youtube.com/",
                        "User-Agent": "Mozilla/5.0 Test",
                    },
                },
                {
                    "format_id": "140",
                    "url": "https://stream.test/audio-140.m4a",
                    "tbr": 128,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                    "http_headers": {
                        "Referer": "https://www.youtube.com/",
                        "User-Agent": "Mozilla/5.0 Test",
                    },
                },
            ],
            formats=[],
        )
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert result.headers == {
            "Referer": "https://www.youtube.com/",
            "User-Agent": "Mozilla/5.0 Test",
        }

    def test_qualities(self, monkeypatch, service):
        info = _sample_info()
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert len(result.qualities) == 3
        assert result.qualities[0].height == 1080
        assert result.qualities[1].height == 720
        assert result.qualities[2].height == 360
        # audio-only format filtered out
        for q in result.qualities:
            assert q.height >= 360

    def test_subtitles(self, monkeypatch, service):
        info = _sample_info()
        _stub_extract_info(monkeypatch, service, info)

        result = service.resolve("https://www.youtube.com/watch?v=test123")

        assert len(result.subtitles) == 2
        names = [s.name for s in result.subtitles]
        assert any("英文" in n for n in names)
        assert any("简体中文" in n for n in names)
        # Japanese is filtered out (only zh/en kept)

    def test_geo_restricted(self, monkeypatch, service):
        _stub_extract_info(monkeypatch, service, ValueError("该内容受地区限制"))

        with pytest.raises(ValueError, match="地区限制"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_extractor_error(self, monkeypatch, service):
        _stub_extract_info(monkeypatch, service, ValueError("下载错误: not found"))

        with pytest.raises(ValueError, match="下载错误"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_no_url(self, monkeypatch, service):
        info = _sample_info(url="", formats=[])
        _stub_extract_info(monkeypatch, service, info)

        with pytest.raises(ValueError, match="未获取到播放地址"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_no_result(self, monkeypatch, service):
        _stub_extract_info(monkeypatch, service, None)

        with pytest.raises(ValueError, match="未返回结果"):
            service.resolve("https://www.youtube.com/watch?v=test123")

    def test_not_available(self, monkeypatch, service):
        service._ytdlp_path = None
        monkeypatch.setattr("atv_player.yt_dlp_service.resolve_system_ytdlp_path", lambda: "")
        with pytest.raises(ValueError, match="未安装"):
            service.resolve("https://www.youtube.com/watch?v=test123")


class TestResolveToPlayItem:
    def test_prefers_current_resolved_height_over_highest_available_quality(self, monkeypatch, service):
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
        _stub_extract_info(monkeypatch, service, info)

        _, item = service.resolve_to_play_item("https://www.youtube.com/watch?v=test123")

        assert [quality.id for quality in item.playback_qualities] == [
            "ytdlp_2160",
            "ytdlp_1080",
            "ytdlp_720",
        ]
        assert [quality.ytdl_format for quality in item.playback_qualities] == [
            "bestvideo[height<=2160]+bestaudio/best[height<=2160]/bestvideo+bestaudio/best",
            "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best",
            "bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best",
        ]
        assert item.selected_playback_quality_id == "ytdlp_1080"

    def test_success(self, monkeypatch, service):
        info = _sample_info()
        _stub_extract_info(monkeypatch, service, info)

        vod, item = service.resolve_to_play_item("https://www.youtube.com/watch?v=test123")

        assert isinstance(vod, VodItem)
        assert isinstance(item, PlayItem)
        assert vod.vod_name == "Test Video"
        assert vod.vod_pic == "https://img.test/thumb.jpg"
        assert item.url == "https://www.youtube.com/watch?v=test123"
        assert item.original_url == "https://www.youtube.com/watch?v=test123"
        assert len(item.playback_qualities) == 3
        assert len(item.external_subtitles) == 2
        assert item.duration_seconds == 300
        assert item.selected_playback_quality_id == "ytdlp_1080"
        assert item.ytdl_format == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best"


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
