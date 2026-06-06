import httpx

from atv_player.controllers.global_catalog_controller import GlobalCatalogService
from atv_player.controllers.global_catalog_controller import GlobalCatalogController
from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory, VodItem


class FakeService:
    def load_items(self, category_id: str, page: int, filters=None):
        return [], 0


def test_global_catalog_categories_expose_seven_modules_and_representative_filters() -> None:
    controller = GlobalCatalogController(FakeService())

    categories = controller.load_categories()

    assert [(category.type_id, category.type_name) for category in categories] == [
        ("anime", "动漫全境聚合"),
        ("genre_rank", "全球影剧类别"),
        ("movies", "全能电影榜单"),
        ("variety", "全球综艺频道"),
        ("trends", "影剧流行风向"),
        ("platform", "平台分流片库"),
        ("top10", "流媒体 TOP10"),
    ]
    anime = categories[0]
    assert anime.filters[0] == CategoryFilter(
        key="anime_source",
        name="选择数据源",
        options=[
            CategoryFilterOption(name="Bangumi 追番日历", value="cal"),
            CategoryFilterOption(name="Bilibili 热度榜单", value="bili"),
            CategoryFilterOption(name="Bangumi 近期热门", value="hot"),
            CategoryFilterOption(name="Bangumi 年季度榜", value="rank"),
            CategoryFilterOption(name="Bangumi 每日放送", value="daily"),
            CategoryFilterOption(name="TMDB 热门/新番", value="tmdb"),
            CategoryFilterOption(name="AniList 流行榜单", value="anilist"),
            CategoryFilterOption(name="MAL 权威榜单", value="mal"),
        ],
    )
    assert any(filter_group.key == "platform" for filter_group in categories[5].filters)
    assert any(filter_group.key == "region" for filter_group in categories[6].filters)


def test_global_catalog_tmdb_anime_maps_discover_results_to_vod_items() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/3/discover/tv"
        assert request.url.params["api_key"] == "tmdb-key"
        assert request.url.params["with_genres"] == "16"
        return httpx.Response(
            200,
            json={
                "total_pages": 4,
                "results": [
                    {
                        "id": 76479,
                        "name": "黑袍纠察队动画",
                        "first_air_date": "2026-04-01",
                        "poster_path": "/poster.jpg",
                        "backdrop_path": "/backdrop.jpg",
                        "genre_ids": [16, 10765],
                        "overview": "简介",
                        "vote_average": 8.3,
                    }
                ],
            },
        )

    service = GlobalCatalogService(tmdb_api_key="tmdb-key", transport=httpx.MockTransport(handler))

    items, total = service.load_items("anime", 2, {"anime_source": "tmdb", "tmdb_sort": "trending"})

    assert total == 4
    assert items[0].vod_id == "tmdb:tv:76479"
    assert items[0].vod_name == "黑袍纠察队动画"
    assert items[0].vod_pic == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert items[0].vod_remarks == "8.3"
    assert items[0].vod_year == "2026"
    assert items[0].type_name == "动画 / 科幻奇幻"
    assert items[0].vod_content == "2026-04-01\n简介"
    assert requests


def test_global_catalog_service_uses_tmdb_proxy_base_for_api_and_images() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        assert request.url.path == "/3/movie/popular"
        return httpx.Response(
            200,
            json={
                "total_pages": 1,
                "results": [
                    {
                        "id": 550,
                        "title": "搏击俱乐部",
                        "release_date": "1999-10-15",
                        "poster_path": "/abc.jpg",
                    }
                ],
            },
        )

    service = GlobalCatalogService(
        tmdb_api_key="tmdb-key",
        tmdb_proxy_base_url="https://tmdb.example.com/3",
        transport=httpx.MockTransport(handler),
    )

    items, total = service.load_items("movies", 1, {"movie_source": "general", "general_sort": "popular"})

    assert total == 1
    assert seen_urls[0].startswith("https://tmdb.example.com/3/movie/popular?")
    assert items[0].vod_pic == "https://tmdb.example.com/t/p/w500/abc.jpg"
    assert items[0].poster_candidates == ["https://tmdb.example.com/t/p/w500/abc.jpg"]


def test_global_catalog_movie_general_top_rated_uses_tmdb_movie_endpoint() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.url.params["page"] == "1"
        return httpx.Response(
            200,
            json={"total_pages": 1, "results": [{"id": 1, "title": "电影", "release_date": "2025-01-02"}]},
        )

    service = GlobalCatalogService(tmdb_api_key="tmdb-key", transport=httpx.MockTransport(handler))

    items, total = service.load_items("movies", 1, {"movie_source": "general", "general_sort": "top_rated"})

    assert seen_paths == ["/3/movie/top_rated"]
    assert total == 1
    assert items[0].vod_id == "tmdb:movie:1"
    assert items[0].vod_name == "电影"


def test_global_catalog_external_title_source_resolves_title_through_tmdb() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/3/search/tv":
            assert request.url.params["query"] == "外部剧集"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 42,
                            "name": "外部剧集",
                            "first_air_date": "2026-06-01",
                            "poster_path": "/tv.jpg",
                            "genre_ids": [18],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    service = GlobalCatalogService(
        tmdb_api_key="tmdb-key",
        transport=httpx.MockTransport(handler),
        external_title_loader=lambda source, page, filters: [("外部剧集", "tv", "No. 1")],
    )

    items, total = service.load_items("trends", 1, {"hub_source": "rt"})

    assert total == 1
    assert items[0].vod_id == "tmdb:tv:42"
    assert items[0].vod_name == "外部剧集"
    assert items[0].vod_remarks == "No. 1"


def test_global_catalog_external_title_source_returns_empty_item_when_no_titles_resolve() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    service = GlobalCatalogService(
        tmdb_api_key="tmdb-key",
        transport=httpx.MockTransport(handler),
        external_title_loader=lambda source, page, filters: [("无法匹配", "movie", "TOP 1")],
    )

    items, total = service.load_items("trends", 1, {"hub_source": "rt"})

    assert total == 1
    assert items == [VodItem(vod_id="global_catalog:empty", vod_name="暂无数据", vod_content="当前外部榜单暂未返回内容")]


def test_global_catalog_controller_default_factory_uses_tmdb_key() -> None:
    controller = GlobalCatalogController.from_config_tmdb_key("abc123")

    assert isinstance(controller, GlobalCatalogController)
    items, total = controller.load_items("unknown", 1)
    assert items == []
    assert total == 0


def test_global_catalog_service_returns_error_item_on_tmdb_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status_message": "down"})

    service = GlobalCatalogService(tmdb_api_key="tmdb-key", transport=httpx.MockTransport(handler))

    items, total = service.load_items("movies", 1, {"movie_source": "general", "general_sort": "popular"})

    assert total == 1
    assert items == [
        VodItem(
            vod_id="global_catalog:error",
            vod_name="环球片单加载失败",
            vod_content="当前榜单暂时无法获取",
        )
    ]
