from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.tmdb import TMDBProvider, infer_tmdb_media_type


class FakeTMDBClient:
    def __init__(self) -> None:
        self.movie_search_results: list[dict] = []
        self.tv_search_results: list[dict] = []
        self.movie_detail: dict = {}
        self.tv_detail: dict = {}
        self.calls: list[tuple[str, str, str]] = []

    def search_movie(self, title: str, year: str = "") -> list[dict]:
        self.calls.append(("search_movie", title, year))
        return list(self.movie_search_results)

    def search_tv(self, title: str, year: str = "") -> list[dict]:
        self.calls.append(("search_tv", title, year))
        return list(self.tv_search_results)

    def get_movie_detail(self, tmdb_id: str | int) -> dict:
        self.calls.append(("get_movie_detail", str(tmdb_id), ""))
        return dict(self.movie_detail)

    def get_tv_detail(self, tmdb_id: str | int) -> dict:
        self.calls.append(("get_tv_detail", str(tmdb_id), ""))
        return dict(self.tv_detail)


def test_infer_tmdb_media_type_uses_category_name() -> None:
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="电影")) == "movie"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="动漫")) == "tv"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="")) == ""


def test_tmdb_provider_searches_movie_when_category_name_marks_movie() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = [{"id": 42, "title": "深空彼岸", "release_date": "2026-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name="电影"))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸", year="2026")]
    assert client.calls == [("search_movie", "深空彼岸", "2026")]


def test_tmdb_provider_falls_back_from_movie_to_tv_when_category_name_is_ambiguous() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = []
    client.tv_search_results = [{"id": 99, "name": "深空彼岸", "first_air_date": "2026-09-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name=""))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="tv:99", title="深空彼岸", year="2026")]
    assert client.calls == [
        ("search_movie", "深空彼岸", "2026"),
        ("search_tv", "深空彼岸", "2026"),
    ]
