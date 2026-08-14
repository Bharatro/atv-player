import httpx
import pytest

from atv_player.subtitles.errors import (
    SubtitleProviderError,
    SubtitleTokenMissingError,
)
from atv_player.subtitles.languages import CHS_ENG, ZH
from atv_player.subtitles.models import SubtitleQuery
from atv_player.subtitles.providers.subdl import SubDLSubtitleProvider

API = "https://api.subdl.com/api/v1/subtitles"


def _provider(get, api_key: str = "key-1") -> SubDLSubtitleProvider:
    return SubDLSubtitleProvider(get=get, api_key_loader=lambda: api_key)


def test_unavailable_without_api_key() -> None:
    provider = _provider(lambda *a, **k: None, api_key="")
    assert provider.available() is False
    with pytest.raises(SubtitleTokenMissingError):
        provider.search(SubtitleQuery(title="流浪地球"))


def test_search_sends_expected_params_and_parses_rows() -> None:
    seen: list[dict] = []

    def fake_get(url: str, **kwargs):
        assert url == API
        seen.append(kwargs["params"])
        return httpx.Response(
            200,
            json={
                "status": True,
                "subtitles": [
                    {
                        "release_name": "The.Wandering.Earth.2019.1080p",
                        "name": "wandering.zip",
                        "url": "/subtitle/111-222.zip",
                        "language": "ZH",
                    }
                ],
            },
        )

    items = _provider(fake_get).search(SubtitleQuery(title="流浪地球", year=2019))

    assert seen[0]["film_name"] == "流浪地球"
    assert seen[0]["year"] == 2019
    assert seen[0]["unpack"] == 1
    assert seen[0]["api_key"] == "key-1"
    assert len(items) == 1
    assert items[0].provider == "subdl"
    # 站点只给了笼统的 "ZH"，发布名里也没有简繁线索，保持通用中文不臆断
    assert items[0].language == ZH
    assert items[0].url == "https://dl.subdl.com/subtitle/111-222.zip"


def test_search_marks_tv_and_filters_unpacked_files_by_episode() -> None:
    def fake_get(url: str, **kwargs):
        assert kwargs["params"]["type"] == "tv"
        assert kwargs["params"]["episode_number"] == 2
        assert kwargs["params"]["season_number"] == 1
        return httpx.Response(
            200,
            json={
                "status": True,
                "subtitles": [
                    {
                        "release_name": "Show.S01",
                        "url": "/subtitle/1-2.zip",
                        "unpack_files": [
                            {
                                "name": "Show.S01E01.chs&eng.srt",
                                "episode": 1,
                                "language": "ZH",
                                "format": "srt",
                                "url": "/subtitle/1/f1",
                            },
                            {
                                "name": "Show.S01E02.chs&eng.srt",
                                "episode": 2,
                                "language": "ZH",
                                "format": "srt",
                                "url": "/subtitle/1/f2",
                            },
                        ],
                    }
                ],
            },
        )

    query = SubtitleQuery(title="Show", episode=2, season=1)
    items = _provider(fake_get).search(query)

    assert len(items) == 1
    assert items[0].url == "https://dl.subdl.com/subtitle/1/f2"
    assert items[0].language == CHS_ENG
    assert items[0].format == "srt"


def test_search_marks_tv_when_only_season_present() -> None:
    """整季搜索（有 season 无 episode）必须按剧集搜，不能误判成电影。"""
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs["params"])
        return httpx.Response(200, json={"status": True, "subtitles": []})

    _provider(fake_get).search(SubtitleQuery(title="The Ark", season=3))

    assert seen["type"] == "tv"
    assert seen["season_number"] == 3
    assert "episode_number" not in seen


def test_search_prefers_imdb_id_and_strips_tt_prefix() -> None:
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs["params"])
        return httpx.Response(200, json={"status": True, "subtitles": []})

    _provider(fake_get).search(SubtitleQuery(title="ignored", imdb_id="tt1234567"))

    assert seen["imdb_id"] == "1234567"
    assert "film_name" not in seen


def test_search_uses_tmdb_id_when_no_imdb() -> None:
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs["params"])
        return httpx.Response(200, json={"status": True, "subtitles": []})

    _provider(fake_get).search(SubtitleQuery(title="ignored", tmdb_id="105923"))

    assert seen["tmdb_id"] == "105923"
    assert seen["type"] == "movie"



def test_search_retries_without_language_filter_when_empty() -> None:
    calls: list[dict] = []

    def fake_get(url: str, **kwargs):
        params = kwargs["params"]
        calls.append(params)
        if "languages" in params:
            return httpx.Response(200, json={"status": True, "subtitles": []})
        return httpx.Response(
            200,
            json={
                "status": True,
                "subtitles": [{"release_name": "any", "url": "/subtitle/9.zip"}],
            },
        )

    items = _provider(fake_get).search(SubtitleQuery(title="冷门片"))

    assert len(calls) == 2
    assert "languages" in calls[0]
    assert "languages" not in calls[1]
    assert len(items) == 1


def test_error_status_raises_with_message() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, json={"status": False, "error": "invalid api key"})

    with pytest.raises(SubtitleProviderError, match="invalid api key"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_download_fetches_absolute_url_and_decodes() -> None:
    def fake_get(url: str, **kwargs):
        if url == API:
            return httpx.Response(
                200,
                json={
                    "status": True,
                    "subtitles": [
                        {
                            "release_name": "x",
                            "name": "x.srt",
                            "url": "/subtitle/5.srt",
                            "language": "ZH",
                        }
                    ],
                },
            )
        assert url == "https://dl.subdl.com/subtitle/5.srt"
        return httpx.Response(
            200, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n".encode()
        )

    provider = _provider(fake_get)
    item = provider.search(SubtitleQuery(title="x"))[0]
    content = provider.download(item)

    assert "你好" in content.text
    assert content.suffix == ".srt"
