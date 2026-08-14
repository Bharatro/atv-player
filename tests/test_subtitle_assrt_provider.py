import httpx
import pytest

from atv_player.subtitles.errors import (
    SubtitleProviderError,
    SubtitleQuotaExceededError,
    SubtitleTokenMissingError,
)
from atv_player.subtitles.languages import CHS_ENG
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem
from atv_player.subtitles.providers.assrt import AssrtSubtitleProvider

SEARCH = "https://api.assrt.net/v1/sub/search"
DETAIL = "https://api.assrt.net/v1/sub/detail"


def _provider(get, token: str = "tok") -> AssrtSubtitleProvider:
    return AssrtSubtitleProvider(get=get, token_loader=lambda: token)


def test_unavailable_without_token() -> None:
    provider = _provider(lambda *a, **k: None, token="")
    assert provider.available() is False
    with pytest.raises(SubtitleTokenMissingError):
        provider.search(SubtitleQuery(title="流浪地球"))


def test_short_keyword_is_skipped() -> None:
    def fake_get(url: str, **kwargs):
        raise AssertionError("should not hit the network")

    assert _provider(fake_get).search(SubtitleQuery(title="ab")) == []


def test_search_parses_language_from_langlist() -> None:
    def fake_get(url: str, **kwargs):
        assert url == SEARCH
        assert kwargs["params"]["token"] == "tok"
        assert kwargs["params"]["q"] == "流浪地球"
        return httpx.Response(
            200,
            json={
                "status": 0,
                "sub": {
                    "subs": [
                        {
                            "id": 602333,
                            "native_name": "流浪地球",
                            "videoname": "The.Wandering.Earth.2019",
                            "subtype": "Subrip(srt)",
                            "release_site": "个人",
                            "vote_score": 80,
                            "lang": {
                                "desc": "简 英 双语",
                                "langlist": {"langchs": True, "langeng": True},
                            },
                        }
                    ]
                },
            },
        )

    items = _provider(fake_get).search(SubtitleQuery(title="流浪地球"))

    assert len(items) == 1
    assert items[0].subtitle_id == "602333"
    assert items[0].language == CHS_ENG
    assert items[0].vote_score == 80.0


def test_episode_query_appends_season_episode_and_uses_is_file() -> None:
    """剧集查询应拼成 '剧名 S03E06' 并带 is_file=1，对照 bazarr。"""
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs["params"])
        return httpx.Response(200, json={"status": 0, "sub": {"subs": []}})

    _provider(fake_get).search(SubtitleQuery(title="方舟号", season=3, episode=6))

    assert seen["q"] == "方舟号 S03E06"
    assert seen["is_file"] == 1


def test_movie_query_appends_year_when_no_episode() -> None:
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs["params"])
        return httpx.Response(200, json={"status": 0, "sub": {"subs": []}})

    _provider(fake_get).search(SubtitleQuery(title="流浪地球", year=2019))

    assert seen["q"] == "流浪地球 2019"
    assert seen["is_file"] == 1


def test_quota_error_maps_to_quota_exception() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, json={"status": 30900, "errmsg": "limit"})

    with pytest.raises(SubtitleQuotaExceededError):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_other_error_status_raises_provider_error() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, json={"status": 20001, "errmsg": "invalid token"})

    with pytest.raises(SubtitleProviderError, match="Token 无效"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_error_body_is_parsed_even_when_http_status_leaks_error_code() -> None:
    """射手网会把错误码漏进 HTTP 状态码（如 492），真实错误在 body 里。"""

    def fake_get(url: str, **kwargs):
        return httpx.Response(
            492, json={"status": 30900, "errmsg": "you are exceeding request limits"}
        )

    with pytest.raises(SubtitleQuotaExceededError, match="配额超限"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_non_json_error_response_falls_back_to_status_error() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(492, text="<html>gateway</html>")

    with pytest.raises(SubtitleProviderError, match="492"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def test_subtitle_not_found_error_has_friendly_message() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(
            200, json={"status": 20900, "errmsg": "subtitle not found"}
        )

    with pytest.raises(SubtitleProviderError, match="已下架"):
        _provider(fake_get).search(SubtitleQuery(title="流浪地球"))


def _item() -> SubtitleSearchItem:
    return SubtitleSearchItem(
        provider="assrt",
        provider_label="射手网(伪)",
        subtitle_id="602333",
        name="流浪地球",
    )


def test_download_prefers_unpacked_filelist_entry() -> None:
    def fake_get(url: str, **kwargs):
        if url == DETAIL:
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "sub": {
                        "subs": [
                            {
                                "filename": "pack.rar",
                                "url": "http://file0.assrt.net/download/602333/pack.rar",
                                "filelist": [
                                    {"f": "movie.eng.srt", "url": "http://f/eng.srt"},
                                    {"f": "movie.chs.ass", "url": "http://f/chs.ass"},
                                ],
                            }
                        ]
                    },
                },
            )
        assert url == "http://f/chs.ass"
        return httpx.Response(200, content="[Script Info]\n简体".encode())

    content = _provider(fake_get).download(_item())

    assert content.suffix == ".ass"
    assert "简体" in content.text


def test_download_falls_back_to_archive_url_without_filelist() -> None:
    def fake_get(url: str, **kwargs):
        if url == DETAIL:
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "sub": {
                        "subs": [
                            {"filename": "movie.srt", "url": "http://file0/movie.srt"}
                        ]
                    },
                },
            )
        assert url == "http://file0/movie.srt"
        return httpx.Response(
            200, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n".encode()
        )

    content = _provider(fake_get).download(_item())
    assert "你好" in content.text


def test_download_without_detail_rows_raises() -> None:
    def fake_get(url: str, **kwargs):
        return httpx.Response(200, json={"status": 0, "sub": {"subs": []}})

    with pytest.raises(SubtitleProviderError):
        _provider(fake_get).download(_item())
