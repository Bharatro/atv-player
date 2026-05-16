import httpx

from atv_player.metadata.providers.tmdb_client import TMDBClient


def test_tmdb_client_search_movie_sends_api_key_language_and_year() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        if request.url.path == "/3/search/movie":
            return httpx.Response(200, json={"results": [{"id": 1, "title": "深空彼岸"}]})
        raise AssertionError(request.url.path)

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    results = client.search_movie("深空彼岸", year="2026")

    assert results == [{"id": 1, "title": "深空彼岸"}]
    assert seen["path"] == "/3/search/movie"
    assert seen["query"] == {
        "api_key": "tmdb-key",
        "language": "zh-CN",
        "query": "深空彼岸",
        "year": "2026",
    }


def test_tmdb_client_get_movie_detail_appends_response_and_builds_image_urls() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/3/configuration":
            return httpx.Response(
                200,
                json={
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/",
                        "poster_sizes": ["w185", "w500"],
                        "backdrop_sizes": ["w300", "w1280"],
                    }
                },
            )
        if request.url.path == "/3/movie/42":
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "title": "深空彼岸",
                    "poster_path": "/poster.jpg",
                    "backdrop_path": "/backdrop.jpg",
                    "external_ids": {"imdb_id": "tt123"},
                },
            )
        raise AssertionError(request.url.path)

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    detail = client.get_movie_detail("42")

    assert detail["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert detail["backdrop_url"] == "https://image.tmdb.org/t/p/w1280/backdrop.jpg"
    assert detail["external_ids"] == {"imdb_id": "tt123"}
    assert calls == ["/3/configuration", "/3/movie/42"]


def test_tmdb_client_get_tv_season_detail_requests_language_and_season() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "season_number": 1,
                "episodes": [{"episode_number": 1, "name": "星门初启"}],
            },
        )

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    detail = client.get_tv_season_detail("42", 1)

    assert detail["episodes"][0]["name"] == "星门初启"
    assert seen["path"] == "/3/tv/42/season/1"
    assert seen["query"]["language"] == "zh-CN"
