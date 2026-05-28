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

    def image_base(self, kind: str) -> str:
        return "https://image.tmdb.org/t/p/original"

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

    def get_tv_detail_with_season(self, tmdb_id: str | int, *, season_number: int | None = None) -> dict:
        self.calls.append(("get_tv_detail_with_season", str(tmdb_id), str(season_number or "")))
        payload = dict(self.tv_detail)
        if season_number is not None:
            payload[f"season/{season_number}"] = dict(self.tv_season_detail)
        return payload

    def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict:
        self.calls.append(("get_tv_season_detail", str(tmdb_id), str(season_number)))
        keyed = self.tv_season_details_by_key.get((str(tmdb_id), int(season_number)))
        if keyed is not None:
            return dict(keyed)
        return dict(self.tv_season_detail)


def _detail_field_value(record, label: str):
    for field in record.detail_fields:
        if field.get("label") == label:
            return field.get("value")
    return None


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

    assert matches[0] == MetadataMatch(
        provider="tmdb",
        provider_id="tv:256783:season:2",
        title="成何体统",
        year="2024",
        score=1.0,
        raw={"season_number": 2},
    )


def test_tmdb_provider_prefers_animation_match_for_anime_category_when_title_differs_only_by_chinese_numeral() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {"id": 300001, "name": "仙剑奇侠传三", "genre_ids": [18], "first_air_date": "2025-01-01"},
        {"id": 300002, "name": "仙剑奇侠传3", "genre_ids": [16], "first_air_date": "2025-01-01"},
    ]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="仙剑奇侠传三", year="2025", category_name="动漫"))

    assert matches[0] == MetadataMatch(
        provider="tmdb",
        provider_id="tv:300002",
        title="仙剑奇侠传3",
        year="2025",
        score=1.0,
    )


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

    assert matches[0] == MetadataMatch(
        provider="tmdb",
        provider_id="tv:256783:season:2",
        title="成何体统",
        year="2024",
        score=1.0,
        raw={"season_number": 2},
    )
    assert ("get_tv_season_detail", "280632", "2") in client.calls
    assert ("get_tv_season_detail", "256783", "2") in client.calls


def test_tmdb_provider_search_all_preserves_overview_rating_and_poster_metadata() -> None:
    client = FakeTMDBClient()
    client.tv_search_results = [
        {
            "id": 233295,
            "name": "仙剑奇侠传叁",
            "original_name": "仙剑奇侠传叁",
            "overview": "作品改编自经典游戏《仙剑奇侠传三》。",
            "poster_path": "/gorGXNaHiFIBn7EEafx5uh7VzhT.jpg",
            "genre_ids": [16, 10759],
            "first_air_date": "2025-12-30",
            "vote_average": 7.0,
        }
    ]
    provider = TMDBProvider(client)

    matches = provider.search_all(MetadataQuery(title="仙剑奇侠传叁", category_name="动漫"))

    assert matches == [
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:233295",
            title="仙剑奇侠传叁",
            year="2025",
            score=1.0,
            raw={
                "poster_url": "https://image.tmdb.org/t/p/original/gorGXNaHiFIBn7EEafx5uh7VzhT.jpg",
                "overview": "作品改编自经典游戏《仙剑奇侠传三》。",
                "rating": "7.0",
            },
        )
    ]


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


def test_tmdb_provider_get_detail_formats_vote_average_to_one_decimal() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "仙逆",
        "overview": "简介",
        "first_air_date": "2023-01-01",
        "vote_average": 8,
        "genres": [{"name": "动画"}],
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:1",
            title="仙逆",
        )
    )

    assert record.rating == "8.0"


def test_tmdb_provider_get_detail_full_keeps_season_episode_stills() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "first_air_date": "2026-05-04",
        "number_of_episodes": 44,
        "number_of_seasons": 2,
        "genres": [{"name": "犯罪"}],
        "seasons": [
            {"season_number": 1, "name": "第一季", "episode_count": 24, "poster_path": "/season1.jpg"},
            {"season_number": 2, "name": "第二季", "episode_count": 20, "poster_path": "/season2.jpg"},
        ],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [
            {
                "episode_number": 1,
                "name": "第一集",
                "still_url": "https://image.tmdb.org/t/p/w1280/episode.jpg",
            }
        ],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    assert record.detail_fields[0]["label"] == "episodes"
    assert record.detail_fields[0]["value"][0]["still_url"] == "https://image.tmdb.org/t/p/w1280/episode.jpg"
    assert record.detail_fields[1]["label"] == "seasons"
    assert record.detail_fields[1]["value"][0]["poster_url"] == "https://image.tmdb.org/t/p/original/season1.jpg"
    assert record.detail_fields[1]["value"][1]["poster_url"] == "https://image.tmdb.org/t/p/original/season2.jpg"
    assert {"label": "number_of_episodes", "value": "44"} in record.detail_fields
    assert {"label": "number_of_seasons", "value": "2"} in record.detail_fields
    assert client.calls == [("get_tv_detail_with_season", "272432", "1")]


def test_tmdb_provider_get_detail_full_formats_vote_average_to_one_decimal() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "first_air_date": "2026-05-04",
        "vote_average": 7.66,
        "genres": [{"name": "犯罪"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    assert record.rating == "7.7"


def test_tmdb_provider_get_detail_full_uses_homepage_as_fallback_for_matching_network_platform() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "homepage": "https://www.iqiyi.com/a_25vgx15887l.html",
        "networks": [
            {"id": 1330, "name": "iQiyi", "origin_country": "CN"},
            {"id": 6357, "name": "Migu Video", "origin_country": "CN"},
        ],
        "first_air_date": "2026-05-04",
        "genres": [{"name": "犯罪"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    watch_providers = _detail_field_value(record, "watch_providers")
    assert watch_providers == [
        {
            "provider": "iqiyi",
            "label": "爱奇艺",
            "url": "https://www.iqiyi.com/a_25vgx15887l.html",
        }
    ]


def test_tmdb_provider_get_detail_full_keeps_explicit_watch_provider_url_over_homepage_fallback() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "homepage": "https://v.qq.com/x/cover/mzc002009g0nh88.html",
        "networks": [
            {"id": 2007, "name": "Tencent Video", "origin_country": "CN"},
        ],
        "watch/providers": {
            "results": {
                "CN": {
                    "flatrate": [
                        {
                            "provider_id": 2007,
                            "provider_name": "Tencent Video",
                            "link": "https://www.themoviedb.org/tv/272432/watch?locale=CN",
                            "url": "https://www.themoviedb.org/tv/272432/watch?locale=CN",
                        }
                    ]
                }
            }
        },
        "first_air_date": "2026-05-04",
        "genres": [{"name": "犯罪"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    watch_providers = _detail_field_value(record, "watch_providers")
    assert watch_providers == [
        {
            "provider": "tencent",
            "label": "腾讯",
            "url": "https://www.themoviedb.org/tv/272432/watch?locale=CN",
        }
    ]


def test_tmdb_provider_get_detail_full_does_not_copy_homepage_to_other_network_platforms() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "homepage": "https://www.iqiyi.com/a_1euk1nkfz9l.html",
        "networks": [
            {"id": 1330, "name": "iQiyi", "origin_country": "CN"},
            {"id": 2007, "name": "Tencent Video", "origin_country": "CN"},
        ],
        "first_air_date": "2026-05-04",
        "genres": [{"name": "犯罪"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    watch_providers = _detail_field_value(record, "watch_providers")
    assert watch_providers == [
        {
            "provider": "iqiyi",
            "label": "爱奇艺",
            "url": "https://www.iqiyi.com/a_1euk1nkfz9l.html",
        }
    ]
    watch_provider_sources = _detail_field_value(record, "watch_provider_sources")
    assert sorted(watch_provider_sources, key=lambda item: item["provider"]) == [
        {
            "provider": "iqiyi",
            "label": "爱奇艺",
            "url": "https://www.iqiyi.com/a_1euk1nkfz9l.html",
        },
        {
            "provider": "tencent",
            "label": "腾讯",
            "url": "",
        },
    ]


def test_tmdb_provider_get_detail_full_does_not_copy_shared_country_link_to_other_platforms() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 243224,
        "name": "凡人修仙传",
        "overview": "剧集简介",
        "networks": [
            {"id": 1024, "name": "Youku", "origin_country": "CN"},
        ],
        "watch/providers": {
            "results": {
                "CN": {
                    "link": "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
                    "flatrate": [
                        {"provider_name": "iQiyi"},
                        {"provider_name": "Tencent Video"},
                        {"provider_name": "Youku"},
                    ],
                }
            }
        },
        "first_air_date": "2025-07-27",
        "genres": [{"name": "剧情"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:243224:season:1",
            title="凡人修仙传",
        )
    )

    watch_providers = _detail_field_value(record, "watch_providers")
    assert watch_providers == [
        {
            "provider": "youku",
            "label": "优酷",
            "url": "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
        }
    ]
    watch_provider_sources = _detail_field_value(record, "watch_provider_sources")
    assert watch_provider_sources == [
        {
            "provider": "iqiyi",
            "label": "爱奇艺",
            "url": "",
        },
        {
            "provider": "tencent",
            "label": "腾讯",
            "url": "",
        },
        {
            "provider": "youku",
            "label": "优酷",
            "url": "https://v.youku.com/v_show/id_XNjQ3ODgxMTc1Ng==.html",
        },
    ]


def test_tmdb_provider_get_detail_returns_empty_rating_for_invalid_vote_average() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "仙逆",
        "overview": "简介",
        "first_air_date": "2023-01-01",
        "vote_average": "not-a-number",
        "genres": [{"name": "动画"}],
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:1",
            title="仙逆",
        )
    )

    assert record.rating == ""


def test_tmdb_provider_get_detail_keeps_cast_roles_and_profile_images() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "仙逆",
        "overview": "简介",
        "first_air_date": "2023-01-01",
        "genres": [{"name": "动画"}],
        "aggregate_credits": {
            "cast": [
                {
                    "id": 2027615,
                    "name": "史泽鲲",
                    "profile_path": "/actor.jpg",
                    "roles": [{"character": "王林 (voice)"}],
                }
            ],
            "crew": [
                {
                    "id": 1234,
                    "name": "导演",
                    "profile_path": "/director.jpg",
                    "jobs": [{"job": "Director"}],
                }
            ],
        },
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(MetadataMatch(provider="tmdb", provider_id="tv:42", title="仙逆"))

    assert record.cast_details == [
        {
            "name": "史泽鲲",
            "role": "王林 (voice)",
            "avatar": "/actor.jpg",
            "url": "https://www.themoviedb.org/person/2027615",
        }
    ]
    assert record.crew_details == [
        {
            "name": "导演",
            "job": "Director",
            "avatar": "/director.jpg",
            "url": "https://www.themoviedb.org/person/1234",
        }
    ]


def test_tmdb_provider_get_detail_sorts_backdrops_with_default_first_and_caps_at_eight() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "深空彼岸",
        "backdrop_url": "https://image.tmdb.org/t/p/original/default.jpg",
        "backdrop_path": "/default.jpg",
        "images": {
            "backdrops": [
                {"file_path": "/low.jpg", "vote_average": 3, "vote_count": 5, "width": 1280, "height": 720},
                {"file_path": "/high.jpg", "vote_average": 9, "vote_count": 200, "width": 3840, "height": 2160},
                {"file_path": "/mid.jpg", "vote_average": 6, "vote_count": 80, "width": 1920, "height": 1080},
                {"file_path": "/portrait.jpg", "vote_average": 7, "vote_count": 60, "width": 1080, "height": 1920},
                *[
                    {"file_path": f"/extra{i}.jpg", "vote_average": 1, "vote_count": 1, "width": 1280, "height": 720}
                    for i in range(10)
                ],
            ]
        },
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(MetadataMatch(provider="tmdb", provider_id="tv:42", title="深空彼岸"))

    expected_top4 = [
        "https://image.tmdb.org/t/p/original/default.jpg",
        "https://image.tmdb.org/t/p/original/high.jpg",
        "https://image.tmdb.org/t/p/original/portrait.jpg",
        "https://image.tmdb.org/t/p/original/mid.jpg",
    ]
    assert record.backdrops[:4] == expected_top4
    assert "https://image.tmdb.org/t/p/original/low.jpg" in record.backdrops
    assert len(record.backdrops) == 8
    assert all(url.startswith("https://image.tmdb.org/t/p/original/") for url in record.backdrops)


def test_tmdb_provider_get_detail_penalizes_non_16_9_when_votes_are_equal() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "深空彼岸",
        "images": {
            "backdrops": [
                {"file_path": "/portrait.jpg", "vote_average": 7, "vote_count": 60, "width": 1080, "height": 1920},
                {"file_path": "/landscape.jpg", "vote_average": 7, "vote_count": 60, "width": 1080, "height": 608},
            ]
        },
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(MetadataMatch(provider="tmdb", provider_id="tv:42", title="深空彼岸"))

    assert record.backdrops[0] == "https://image.tmdb.org/t/p/original/landscape.jpg"
    assert record.backdrops[1] == "https://image.tmdb.org/t/p/original/portrait.jpg"


def test_tmdb_provider_get_detail_returns_empty_backdrops_when_no_images_present() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "深空彼岸",
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(MetadataMatch(provider="tmdb", provider_id="tv:42", title="深空彼岸"))

    assert record.backdrops == []
