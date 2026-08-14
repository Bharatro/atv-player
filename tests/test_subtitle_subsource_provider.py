import httpx
import pytest

from atv_player.subtitles.errors import (
    SubtitleProviderError,
    SubtitleTokenMissingError,
)
from atv_player.subtitles.languages import ENG, ZH
from atv_player.subtitles.models import SubtitleQuery
from atv_player.subtitles.providers.subsource import SubsourceSubtitleProvider

MOVIES_API = "https://api.subsource.net/api/v1/movies/search"
SUBTITLES_API = "https://api.subsource.net/api/v1/subtitles"


def _provider(get, api_key: str = "key-1") -> SubsourceSubtitleProvider:
    return SubsourceSubtitleProvider(get=get, api_key_loader=lambda: api_key)


def _movies_response(*rows):
    return httpx.Response(200, json={"data": list(rows)})


def _movie(movie_id="77", title="The Ark", year=2023, alternate=""):
    return {
        "movieId": movie_id,
        "title": title,
        "alternateTitle": alternate,
        "releaseYear": year,
    }


def _subtitles_response(*rows):
    return httpx.Response(200, json={"data": list(rows)})


def test_unavailable_without_api_key() -> None:
    provider = _provider(lambda *a, **k: None, api_key="")
    assert provider.available() is False
    with pytest.raises(SubtitleTokenMissingError):
        provider.search(SubtitleQuery(title="The Ark"))


def test_search_by_title_matches_movie_and_parses_items() -> None:
    seen: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        seen.append((url, kwargs["params"]))
        if url == MOVIES_API:
            return _movies_response(_movie())
        assert url == SUBTITLES_API
        if kwargs["params"]["language"] == "chinese bg code":
            return _subtitles_response(
                {
                    "subtitleId": 501,
                    "link": "/subtitle/501",
                    "releaseInfo": ["The.Ark.S03E06.1080p.WEB-DL-GROUP"],
                    "language": "Chinese BG code",
                    "contributors": [{"id": 9, "displayname": "someone"}],
                    "uploaderId": 9,
                }
            )
        return _subtitles_response()

    items = _provider(fake_get).search(
        SubtitleQuery(title="The Ark", season=3, episode=6)
    )

    assert seen[0][1]["searchType"] == "text"
    assert seen[0][1]["q"] == "the ark"
    assert seen[0][1]["season"] == 3
    assert seen[1][1]["movieId"] == "77"
    assert seen[1][1]["language"] == "chinese bg code"
    assert seen[1][1]["seasonNumber"] == 3
    assert seen[1][1]["episodeNumber"] == 6
    assert seen[2][1]["language"] == "english"
    assert len(items) == 1
    assert items[0].provider == "subsource"
    # 站内中文统一叫 "Chinese BG code"，归一成通用中文
    assert items[0].language == ZH
    assert items[0].season == 3
    assert items[0].episode == 6
    assert items[0].url == "https://subsource.net/subtitle/501"
    assert items[0].release_site == "someone"


def test_search_prefers_imdb_and_falls_back_to_text() -> None:
    calls: list[dict] = []

    def fake_get(url: str, **kwargs):
        params = kwargs["params"]
        calls.append(params)
        if url == MOVIES_API:
            if params["searchType"] == "imdb":
                return _movies_response()
            return _movies_response(_movie())
        return _subtitles_response()

    items = _provider(fake_get).search(
        SubtitleQuery(title="The Ark", imdb_id="tt2199999")
    )

    assert calls[0]["searchType"] == "imdb"
    assert calls[0]["imdb"] == "2199999"
    assert calls[1]["searchType"] == "text"
    assert items == []


def test_search_skips_mismatched_title_or_year() -> None:
    def fake_get(url: str, **kwargs):
        if url == MOVIES_API:
            return _movies_response(
                _movie(title="Totally Different Show"),
                _movie(movie_id="88", year=1999),
            )
        raise AssertionError("不应走到字幕查询")

    items = _provider(fake_get).search(SubtitleQuery(title="The Ark", year=2023))

    assert items == []


def test_search_keeps_season_pack_and_drops_other_episode() -> None:
    def fake_get(url: str, **kwargs):
        if url == MOVIES_API:
            return _movies_response(_movie())
        if kwargs["params"]["language"] != "chinese bg code":
            return _subtitles_response()
        return _subtitles_response(
            # 集数不符 → 丢弃
            {
                "subtitleId": 1,
                "releaseInfo": ["The.Ark.S03E05.1080p-GROUP"],
                "language": "Chinese BG code",
            },
            # 整季包（无集数）→ 保留
            {
                "subtitleId": 2,
                "releaseInfo": ["The.Ark.S03.1080p-GROUP"],
                "language": "Chinese BG code",
            },
        )

    items = _provider(fake_get).search(
        SubtitleQuery(title="The Ark", season=3, episode=6)
    )

    assert [item.subtitle_id for item in items] == ["2"]
    assert items[0].episode is None


def test_search_marks_forced_and_hearing_impaired() -> None:
    def fake_get(url: str, **kwargs):
        if url == MOVIES_API:
            return _movies_response(_movie(title="Movie", year=2020))
        return (
            _subtitles_response(
                {
                    "subtitleId": 1,
                    "releaseInfo": ["Movie.2020.1080p"],
                    "language": "English",
                    "foreignParts": True,
                },
                {
                    "subtitleId": 2,
                    "releaseInfo": ["Movie.2020.1080p"],
                    "language": "English",
                    "commentary": "SDH included",
                },
                {
                    "subtitleId": 3,
                    "releaseInfo": ["Movie.2020.1080p"],
                    "language": "English",
                },
            )
            if kwargs["params"]["language"] == "english"
            else _subtitles_response()
        )

    items = _provider(fake_get).search(SubtitleQuery(title="Movie", year=2020))

    assert [item.language for item in items] == [ENG, ENG, ENG]
    forced = {item.subtitle_id: item for item in items}
    assert forced["1"].forced is True
    assert forced["2"].hearing_impaired is True
    assert forced["3"].forced is False
    assert forced["3"].hearing_impaired is False


def test_success_false_returns_empty() -> None:
    def fake_get(url: str, **kwargs):
        if url == MOVIES_API:
            return _movies_response(_movie())
        return httpx.Response(200, json={"success": False})

    items = _provider(fake_get).search(SubtitleQuery(title="The Ark"))

    assert items == []


def test_http_error_raises_provider_error() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(401, json={"error": "API key required"})

    with pytest.raises(SubtitleProviderError):
        _provider(fake_get).search(SubtitleQuery(title="The Ark"))


def test_download_uses_subtitle_id_and_decodes() -> None:
    def fake_get(url: str, **kwargs):
        if url == MOVIES_API:
            return _movies_response(_movie())
        if url == SUBTITLES_API:
            if kwargs["params"]["language"] != "chinese bg code":
                return _subtitles_response()
            return _subtitles_response(
                {
                    "subtitleId": 501,
                    "link": "/subtitle/501",
                    "releaseInfo": ["The.Ark.S03E06.1080p-GROUP"],
                    "language": "Chinese BG code",
                }
            )
        assert url == ("https://api.subsource.net/api/v1/subtitles/501/download")
        assert kwargs["params"]["api_key"] == "key-1"
        return httpx.Response(
            200, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n".encode()
        )

    provider = _provider(fake_get)
    item = provider.search(SubtitleQuery(title="The Ark"))[0]
    content = provider.download(item)

    assert "你好" in content.text
    assert content.suffix == ".srt"
