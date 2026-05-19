from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.tmdb import TMDBProvider, infer_tmdb_media_type


class FakeTMDBClient:
    def __init__(self) -> None:
        self.movie_search_results: list[dict] = []
        self.tv_search_results: list[dict] = []
        self.movie_detail: dict = {}
        self.tv_detail: dict = {}
        self.tv_season_detail: dict = {}
        self.tv_season_details_by_key: dict[tuple[str, int], dict] = {}
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

    def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict:
        self.calls.append(("get_tv_season_detail", str(tmdb_id), str(season_number)))
        keyed = self.tv_season_details_by_key.get((str(tmdb_id), int(season_number)))
        if keyed is not None:
            return dict(keyed)
        return dict(self.tv_season_detail)


def test_infer_tmdb_media_type_uses_category_name() -> None:
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="电影")) == "movie"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", type_name="电影")) == "movie"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="动漫")) == "tv"
    assert infer_tmdb_media_type(MetadataQuery(title="掩耳盗邻第二季", category_name="")) == "tv"
    assert infer_tmdb_media_type(MetadataQuery(title="七王国的骑士 第一季", category_name="")) == "tv"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="")) == ""


def test_tmdb_provider_searches_movie_when_category_name_marks_movie() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = [{"id": 42, "title": "深空彼岸", "release_date": "2026-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name="电影"))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸", year="2026", score=1.0)]
    assert client.calls == [("search_movie", "深空彼岸", "2026")]


def test_tmdb_provider_falls_back_from_movie_to_tv_when_category_name_is_ambiguous() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = []
    client.tv_search_results = [{"id": 99, "name": "深空彼岸", "first_air_date": "2026-09-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name=""))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="tv:99", title="深空彼岸", year="2026", score=1.0)]
    assert client.calls == [
        ("search_movie", "深空彼岸", "2026"),
        ("search_tv", "深空彼岸", "2026"),
    ]


def test_tmdb_provider_strips_season_suffix_from_tv_search_title() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [{"id": 42, "name": "掩耳盗邻", "first_air_date": "2025-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="掩耳盗邻第二季", year="2025", category_name="电视剧"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:2",
            title="掩耳盗邻",
            year="2025",
            score=1.0,
            raw={"season_number": 2},
        )
    ]
    assert client.calls == [("search_tv", "掩耳盗邻", ""), ("get_tv_season_detail", "42", "2")]


def test_tmdb_provider_falls_back_to_first_tv_result_when_exact_title_match_is_missing() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {
            "id": 314,
            "name": "A Knight of the Seven Kingdoms: The Hedge Knight",
            "first_air_date": "2025-01-01",
        }
    ]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="七王国的骑士 第一季", year="2025", category_name="电视剧"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:314:season:1",
            title="A Knight of the Seven Kingdoms: The Hedge Knight",
            year="2025",
            score=0.55,
            raw={"season_number": 1},
        )
    ]
    assert client.calls == [("search_tv", "七王国的骑士", ""), ("get_tv_season_detail", "314", "1")]


def test_tmdb_provider_accepts_tv_result_when_query_year_differs_from_series_first_air_date() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [{"id": 42, "name": "掩耳盗邻", "first_air_date": "2025-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="掩耳盗邻第二季", year="2026", category_name="电视剧"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:2",
            title="掩耳盗邻",
            year="2025",
            score=1.0,
            raw={"season_number": 2},
        )
    ]
    assert client.calls == [("search_tv", "掩耳盗邻", ""), ("get_tv_season_detail", "42", "2")]


def test_tmdb_provider_prefers_tv_search_for_titles_with_season_marker_even_without_category() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [{"id": 42, "name": "掩耳盗邻", "first_air_date": "2025-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="掩耳盗邻第二季", year="2026", category_name=""))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:2",
            title="掩耳盗邻",
            year="2025",
            score=1.0,
            raw={"season_number": 2},
        )
    ]
    assert client.calls == [("search_tv", "掩耳盗邻", ""), ("get_tv_season_detail", "42", "2")]


def test_tmdb_provider_search_cache_key_ignores_year_for_season_marked_tv_titles() -> None:
    provider = TMDBProvider(FakeTMDBClient())

    assert provider.search_cache_key(MetadataQuery(title="掩耳盗邻第二季", year="2026", category_name="电视剧")) == (
        "掩耳盗邻",
        "",
    )


def test_tmdb_provider_does_not_fallback_to_raw_season_title_search() -> None:
    client = FakeTMDBClient()
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="掩耳盗邻第二季", year="2026", category_name="电视剧"))

    assert matches == []
    assert client.calls == [("search_tv", "掩耳盗邻", "")]


def test_tmdb_provider_prefers_animation_match_for_anime_category_when_same_title_has_multiple_results() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {"id": 280632, "name": "成何体统", "genre_ids": [18], "first_air_date": "2024-01-01"},
        {"id": 256783, "name": "成何体统", "genre_ids": [16, 35], "first_air_date": "2024-01-01"},
        {"id": 291021, "name": "成何体统", "genre_ids": [10766], "first_air_date": "2024-01-01"},
    ]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="成何体统第二季", year="", category_name="动漫"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:256783:season:2",
            title="成何体统",
            year="2024",
            score=1.0,
            raw={"season_number": 2},
        )
    ]


def test_tmdb_provider_prefers_animation_match_for_anime_category_when_title_differs_only_by_chinese_numeral() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {"id": 300001, "name": "仙剑奇侠传三", "genre_ids": [18], "first_air_date": "2025-01-01"},
        {"id": 300002, "name": "仙剑奇侠传3", "genre_ids": [16], "first_air_date": "2025-01-01"},
    ]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="仙剑奇侠传三", year="2025", category_name="动漫"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:300002",
            title="仙剑奇侠传3",
            year="2025",
            score=1.0,
        )
    ]


def test_tmdb_provider_prefers_candidate_with_requested_season_when_same_title_results_differ() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {"id": 280632, "name": "成何体统", "genre_ids": [16], "first_air_date": "2024-01-01"},
        {"id": 256783, "name": "成何体统", "genre_ids": [16], "first_air_date": "2024-01-01"},
    ]
    client.tv_season_details_by_key = {
        ("280632", 2): {},
        ("256783", 2): {"episodes": [{"episode_number": 1, "name": "第2季第1集"}]},
    }
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="成何体统第二季", year="", category_name="动漫"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:256783:season:2",
            title="成何体统",
            year="2024",
            score=1.0,
            raw={"season_number": 2},
        )
    ]
    assert ("get_tv_season_detail", "280632", "2") in client.calls
    assert ("get_tv_season_detail", "256783", "2") in client.calls


def test_tmdb_provider_get_detail_uses_tv_season_overview_when_provider_id_contains_season() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "黑袍纠察队",
        "overview": "剧集总简介",
        "first_air_date": "2019-01-01",
        "genres": [{"name": "剧情"}],
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {"imdb_id": "tt1190634"},
    }
    client.tv_season_detail = {
        "season_number": 5,
        "overview": "第五季简介",
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:5",
            title="黑袍纠察队",
            year="2019",
            raw={"season_number": 5},
        )
    )

    assert record.title == "黑袍纠察队"
    assert record.overview == "第五季简介"
    assert client.calls == [
        ("get_tv_detail", "42", ""),
        ("get_tv_season_detail", "42", "5"),
    ]
