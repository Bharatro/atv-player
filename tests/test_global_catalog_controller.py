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
