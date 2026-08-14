import httpx
import pytest

from atv_player.subtitles.errors import (
    SubtitleQuotaExceededError,
    SubtitleTokenMissingError,
)
from atv_player.subtitles.languages import CHS
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem
from atv_player.subtitles.providers.opensubtitles import OpenSubtitlesProvider

SEARCH = "https://api.opensubtitles.com/api/v1/subtitles"
DOWNLOAD = "https://api.opensubtitles.com/api/v1/download"


def _provider(get=None, post=None, api_key: str = "os-key") -> OpenSubtitlesProvider:
    return OpenSubtitlesProvider(
        get=get or (lambda *a, **k: None),
        post=post or (lambda *a, **k: None),
        api_key_loader=lambda: api_key,
    )


def test_unavailable_without_api_key() -> None:
    provider = _provider(api_key="")
    assert provider.available() is False
    with pytest.raises(SubtitleTokenMissingError):
        provider.search(SubtitleQuery(title="Interstellar"))


def test_search_sends_auth_headers_and_parses_files() -> None:
    seen: dict = {}

    def fake_get(url: str, **kwargs):
        assert url == SEARCH
        seen.update(kwargs["headers"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "attributes": {
                            "language": "zh-CN",
                            "release": "Interstellar.2014.1080p",
                            "download_count": 1234,
                            "ratings": 8.5,
                            "files": [{"file_id": 987, "file_name": "inter.srt"}],
                        }
                    },
                    {"attributes": {"language": "en", "files": []}},
                ]
            },
        )

    items = _provider(get=fake_get).search(SubtitleQuery(title="Interstellar"))

    assert seen["Api-Key"] == "os-key"
    assert "atv-player" in seen["User-Agent"]
    # 没有可下载文件的条目会被跳过
    assert len(items) == 1
    assert items[0].subtitle_id == "987"
    assert items[0].language == CHS
    assert items[0].download_count == 1234


def test_search_passes_episode_and_season() -> None:
    def fake_get(url: str, **kwargs):
        assert kwargs["params"]["episode_number"] == 3
        assert kwargs["params"]["season_number"] == 2
        return httpx.Response(200, json={"data": []})

    _provider(get=fake_get).search(SubtitleQuery(title="Show", episode=3, season=2))


def _item() -> SubtitleSearchItem:
    return SubtitleSearchItem(
        provider="opensubtitles",
        provider_label="OpenSubtitles",
        subtitle_id="987",
        name="Interstellar",
    )


def test_download_posts_file_id_then_follows_link() -> None:
    def fake_post(url: str, **kwargs):
        assert url == DOWNLOAD
        assert kwargs["json"] == {"file_id": 987}
        return httpx.Response(
            200,
            json={
                "link": "https://dl.opensubtitles.com/x.srt",
                "file_name": "x.srt",
            },
        )

    def fake_get(url: str, **kwargs):
        assert url == "https://dl.opensubtitles.com/x.srt"
        return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nhi\n")

    content = _provider(get=fake_get, post=fake_post).download(_item())

    assert content.suffix == ".srt"
    assert "hi" in content.text


def test_download_without_link_reports_quota() -> None:
    def fake_post(url: str, **kwargs):
        return httpx.Response(200, json={"message": "download limit reached"})

    with pytest.raises(SubtitleQuotaExceededError, match="download limit reached"):
        _provider(post=fake_post).download(_item())
