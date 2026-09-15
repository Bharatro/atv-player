import httpx

from atv_player.metadata.providers.tmdb_client import TMDBClient
from atv_player.metadata.tmdb_pool import BUILTIN_WORKER_POOL, WORKER_POOL_VALUE
from atv_player.network_proxy import ProxyConfig, ProxyDecider


def test_tmdb_client_builds_manual_proxy_httpx_client() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []})))

    client = TMDBClient(
        api_key="tmdb-key",
        proxy_decider=ProxyDecider(
            ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])
        ),
        client_factory=fake_client_factory,
    )

    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["trust_env"] is False
    client._client.close()


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


def test_tmdb_client_uses_proxy_base_url_for_api_and_images_without_local_api_key() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "api_key" not in request.url.params
        if request.url.path == "/3/configuration":
            return httpx.Response(
                200,
                json={
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/",
                        "poster_sizes": ["w500", "original"],
                        "backdrop_sizes": ["w300", "w1280"],
                    }
                },
            )
        if request.url.path == "/3/movie/550":
            return httpx.Response(
                200,
                json={
                    "id": 550,
                    "title": "Fight Club",
                    "poster_path": "/abc.jpg",
                    "backdrop_path": "/bd.jpg",
                },
            )
        raise AssertionError(request.url.path)

    client = TMDBClient(
        api_key="",
        proxy_base_url="https://tmdb.example.com/",
        transport=httpx.MockTransport(handler),
    )

    detail = client.get_movie_detail("550")

    assert seen[0].startswith("https://tmdb.example.com/3/configuration?")
    assert seen[1].startswith("https://tmdb.example.com/3/movie/550?")
    assert detail["poster_url"] == "https://tmdb.example.com/t/p/original/abc.jpg"
    assert detail["backdrop_url"] == "https://tmdb.example.com/t/p/w1280/bd.jpg"


def test_tmdb_client_get_movie_detail_prefers_original_poster_and_builds_image_urls() -> None:
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

    assert detail["poster_url"] == "https://image.tmdb.org/t/p/original/poster.jpg"
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


def test_tmdb_client_get_tv_detail_with_season_builds_episode_still_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
        if request.url.path == "/3/tv/272432":
            return httpx.Response(
                200,
                json={
                    "id": 272432,
                    "name": "低智商犯罪",
                    "season/1": {
                        "episodes": [
                            {
                                "episode_number": 1,
                                "name": "第一集",
                                "still_path": "/episode.jpg",
                            }
                        ]
                    },
                },
            )
        raise AssertionError(request.url.path)

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    detail = client.get_tv_detail_with_season("272432", season_number=1)

    episode = detail["season/1"]["episodes"][0]
    assert episode["still_url"] == "https://image.tmdb.org/t/p/w1280/episode.jpg"
    assert episode["season_number"] == 1


def test_tmdb_client_trending_tv_sends_window_and_page() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": [{"id": 76479, "name": "The Boys"}]})

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    results = client.get_trending(media_type="tv", window="week", page=2)

    assert results == [{"id": 76479, "name": "The Boys"}]
    assert seen["path"] == "/3/trending/tv/week"
    assert seen["query"] == {
        "api_key": "tmdb-key",
        "language": "zh-CN",
        "page": "2",
    }


def test_tmdb_client_discover_tv_passes_filters() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": []})

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    results = client.discover(
        media_type="tv",
        page=3,
        sort_by="vote_average.desc",
        year="2025",
        with_genres="18",
        with_origin_country="KR",
    )

    assert results == []
    assert seen["path"] == "/3/discover/tv"
    assert seen["query"] == {
        "api_key": "tmdb-key",
        "language": "zh-CN",
        "page": "3",
        "sort_by": "vote_average.desc",
        "first_air_date_year": "2025",
        "with_genres": "18",
        "with_origin_country": "KR",
    }


def test_tmdb_client_rotates_mirror_pool_per_request() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        return httpx.Response(200, json={"results": []})

    client = TMDBClient(
        api_key="tmdb-key",
        proxy_base_url="https://mirror-a.example.com,https://mirror-b.example.com",
        transport=httpx.MockTransport(handler),
    )

    client.search_movie("深空彼岸")
    client.search_movie("深空彼岸")

    assert sorted(set(seen_hosts)) == ["mirror-a.example.com", "mirror-b.example.com"]
    assert len(seen_hosts) == 2


def test_tmdb_client_worker_pool_sentinel_targets_builtin_hosts() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        return httpx.Response(200, json={"results": []})

    client = TMDBClient(
        api_key="tmdb-key",
        proxy_base_url=WORKER_POOL_VALUE,
        transport=httpx.MockTransport(handler),
    )

    client.search_movie("深空彼岸")

    builtin_hosts = {host.removeprefix("https://") for host in BUILTIN_WORKER_POOL}
    assert seen_hosts == [seen_hosts[0]]
    assert seen_hosts[0] in builtin_hosts


def test_tmdb_client_image_urls_follow_mirror_pool() -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.path == "/3/configuration":
            return httpx.Response(
                200,
                json={
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/",
                        "poster_sizes": ["w500", "original"],
                        "backdrop_sizes": ["w300", "w1280"],
                    }
                },
            )
        if request.url.path == "/3/movie/550":
            return httpx.Response(
                200,
                json={"id": 550, "poster_path": "/abc.jpg", "backdrop_path": "/bd.jpg"},
            )
        raise AssertionError(request.url.path)

    client = TMDBClient(
        api_key="",
        proxy_base_url="https://mirror-a.example.com",
        transport=httpx.MockTransport(handler),
    )

    detail = client.get_movie_detail("550")

    assert detail["poster_url"] == "https://mirror-a.example.com/t/p/original/abc.jpg"
    assert detail["backdrop_url"] == "https://mirror-a.example.com/t/p/w1280/bd.jpg"
    assert set(requested_hosts) == {"mirror-a.example.com"}


def test_tmdb_client_invalid_proxy_value_falls_back_to_official() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        return httpx.Response(200, json={"results": []})

    client = TMDBClient(
        api_key="tmdb-key",
        proxy_base_url="not-a-url",
        transport=httpx.MockTransport(handler),
    )

    client.search_movie("深空彼岸")

    assert seen["host"] == "api.themoviedb.org"
