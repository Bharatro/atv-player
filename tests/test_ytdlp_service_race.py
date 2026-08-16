import threading

import pytest

from atv_player.models import AppConfig
from atv_player.yt_dlp_service import YtdlpPlaybackService, YtdlpResolveResult

_DASH_URL = "data:application/dash+xml;base64,QUJD"
_VIDEO_URL = "https://www.youtube.com/watch?v=race12345"


def _make_result(url: str) -> YtdlpResolveResult:
    return YtdlpResolveResult(
        url=url,
        audio_url="",
        ytdl_format="",
        video_format_id="",
        audio_format_id="",
        audio_tracks=[],
        selected_audio_track_id="",
        title="Race Video",
        thumbnail="",
        description="",
        duration_seconds=61,
        headers={},
        subtitles=[],
        qualities=[],
        selected_quality_id="ytdlp_1080",
        extractor="youtube",
        detail_fields=[],
    )


def _make_service() -> YtdlpPlaybackService:
    service = YtdlpPlaybackService(config_loader=lambda: AppConfig(youtube_max_height=1080))
    service._ytdlp_path = "/usr/bin/true"  # bypass binary discovery in tests
    return service


def _install_fake_uncached(service: YtdlpPlaybackService, produce) -> None:
    """Replace _resolve_uncached while keeping its store-to-cache contract."""

    def fake_uncached(
        canonical_url,
        cache_height,
        *,
        extraction_max_height,
        selected_audio_track_id,
        include_subtitles,
        log=None,
    ):
        result = produce(cache_height)
        service._store_cached_result(
            canonical_url,
            cache_height,
            selected_audio_track_id,
            result,
            include_subtitles=include_subtitles,
        )
        return result

    service._resolve_uncached = fake_uncached


def test_racing_full_resolve_is_reused_by_matching_resolve() -> None:
    service = _make_service()
    extraction_calls: list[object] = []
    race_started = threading.Event()
    release_race = threading.Event()

    def produce(cache_height):
        extraction_calls.append(cache_height)
        if len(extraction_calls) == 1:
            race_started.set()
            assert release_race.wait(timeout=5)
        return _make_result(_DASH_URL)

    _install_fake_uncached(service, produce)

    race = service.start_full_resolve_race(_VIDEO_URL)
    assert race is not None
    assert race_started.wait(timeout=5)
    # A second race start dedupes onto the same pending future.
    assert service.start_full_resolve_race(_VIDEO_URL) is race

    resolved: dict[str, object] = {}

    def consume() -> None:
        resolved["value"] = service.resolve(_VIDEO_URL, max_height=1080, include_subtitles=True)

    consumer = threading.Thread(target=consume)
    consumer.start()
    release_race.set()
    consumer.join(timeout=5)

    # The matching resolve() reused the racing result instead of extracting again.
    assert getattr(resolved["value"], "url") == _DASH_URL
    assert extraction_calls == [1080]

    # The race result is cached, so later resolves and race starts do not re-extract.
    again = service.resolve(_VIDEO_URL, max_height=1080, include_subtitles=True)
    assert again.url == _DASH_URL
    assert service.start_full_resolve_race(_VIDEO_URL) is None
    assert extraction_calls == [1080]


def test_racing_full_resolve_is_not_reused_for_mismatched_parameters() -> None:
    service = _make_service()
    extraction_calls: list[object] = []
    race_started = threading.Event()
    release_race = threading.Event()

    def produce(cache_height):
        extraction_calls.append(cache_height)
        if len(extraction_calls) == 1:
            race_started.set()
            assert release_race.wait(timeout=5)
        return _make_result(f"https://gv.example/h{cache_height}.mp4")

    _install_fake_uncached(service, produce)

    race = service.start_full_resolve_race(_VIDEO_URL)
    assert race is not None
    assert race_started.wait(timeout=5)

    # A manual quality switch with different parameters resolves on its own.
    other = service.resolve(_VIDEO_URL, max_height=480, include_subtitles=True)
    assert other.url == "https://gv.example/h480.mp4"
    assert extraction_calls == [1080, 480]

    release_race.set()
    assert race.result(timeout=5).url == "https://gv.example/h1080.mp4"


def test_resolve_falls_back_when_racing_full_resolve_fails() -> None:
    service = _make_service()
    attempts: list[object] = []
    race_started = threading.Event()
    release_race = threading.Event()

    def produce(cache_height):
        attempts.append(cache_height)
        if len(attempts) == 1:
            race_started.set()
            assert release_race.wait(timeout=5)
            raise ValueError("下载错误: race failed")
        return _make_result("https://gv.example/local.mp4")

    _install_fake_uncached(service, produce)

    race = service.start_full_resolve_race(_VIDEO_URL)
    assert race is not None
    assert race_started.wait(timeout=5)

    resolved: dict[str, object] = {}

    def consume() -> None:
        resolved["value"] = service.resolve(_VIDEO_URL, max_height=1080, include_subtitles=True)

    consumer = threading.Thread(target=consume)
    consumer.start()
    release_race.set()
    consumer.join(timeout=5)

    assert getattr(resolved["value"], "url") == "https://gv.example/local.mp4"
    assert attempts == [1080, 1080]
    with pytest.raises(ValueError):
        race.result(timeout=5)


def test_resolve_fast_or_full_prefers_fast_result_while_race_pending() -> None:
    service = _make_service()
    race_started = threading.Event()
    release_race = threading.Event()

    def produce(cache_height):
        race_started.set()
        assert release_race.wait(timeout=5)
        return _make_result(_DASH_URL)

    _install_fake_uncached(service, produce)
    service._extract_fast_urls_via_command = (
        lambda url, max_height, *, include_browser_cookies=False: ["https://gv.example/fast-360.mp4"]
    )

    result = service.resolve_fast_or_full(_VIDEO_URL)
    assert result.url == "https://gv.example/fast-360.mp4"
    assert result.audio_url == ""

    assert race_started.wait(timeout=5)
    release_race.set()


def test_resolve_fast_or_full_uses_race_result_when_fast_fails() -> None:
    service = _make_service()
    race_finished = threading.Event()

    def produce(cache_height):
        race_finished.set()
        return _make_result(_DASH_URL)

    _install_fake_uncached(service, produce)

    def fake_fast_urls(url, max_height, *, include_browser_cookies=False):
        assert race_finished.wait(timeout=5)
        raise ValueError("yt-dlp 快速解析超时")

    service._extract_fast_urls_via_command = fake_fast_urls

    result = service.resolve_fast_or_full(_VIDEO_URL)
    assert result.url == _DASH_URL


def test_resolve_fast_or_full_falls_back_to_cached_full_result_when_fast_fails() -> None:
    service = _make_service()
    extraction_calls: list[object] = []

    def produce(cache_height):
        extraction_calls.append(cache_height)
        return _make_result(_DASH_URL)

    _install_fake_uncached(service, produce)

    # Populate the cache first; the next race start will refuse to run.
    warm = service.start_full_resolve_race(_VIDEO_URL)
    assert warm is not None
    assert warm.result(timeout=5).url == _DASH_URL
    assert extraction_calls == [1080]

    def fake_fast_urls(url, max_height, *, include_browser_cookies=False):
        raise ValueError("yt-dlp 快速解析超时")

    service._extract_fast_urls_via_command = fake_fast_urls
    result = service.resolve_fast_or_full(_VIDEO_URL)
    assert result.url == _DASH_URL
    assert extraction_calls == [1080]
