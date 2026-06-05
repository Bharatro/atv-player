from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory, VodItem


class GlobalCatalogServiceProtocol(Protocol):
    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        ...


def _option(name: str, value: str) -> CategoryFilterOption:
    return CategoryFilterOption(name=name, value=value)


def _filter(key: str, name: str, options: list[tuple[str, str]]) -> CategoryFilter:
    return CategoryFilter(key=key, name=name, options=[_option(label, value) for label, value in options])


def _year_options() -> list[tuple[str, str]]:
    return [(str(year), str(year)) for year in range(2026, 2014, -1)]


def _categories() -> list[DoubanCategory]:
    return [
        DoubanCategory(
            type_id="anime",
            type_name="动漫全境聚合",
            filters=[
                _filter(
                    "anime_source",
                    "选择数据源",
                    [
                        ("Bangumi 追番日历", "cal"),
                        ("Bilibili 热度榜单", "bili"),
                        ("Bangumi 近期热门", "hot"),
                        ("Bangumi 年季度榜", "rank"),
                        ("Bangumi 每日放送", "daily"),
                        ("TMDB 热门/新番", "tmdb"),
                        ("AniList 流行榜单", "anilist"),
                        ("MAL 权威榜单", "mal"),
                    ],
                ),
                _filter(
                    "cal_day",
                    "选择日期",
                    [
                        ("今日更新", "today"),
                        ("周一", "1"),
                        ("周二", "2"),
                        ("周三", "3"),
                        ("周四", "4"),
                        ("周五", "5"),
                        ("周六", "6"),
                        ("周日", "7"),
                    ],
                ),
                _filter("tmdb_sort", "TMDB 榜单", [("实时流行", "trending"), ("最新首播", "new"), ("高分神作", "top")]),
                _filter("rank_year", "年份", _year_options()),
                _filter(
                    "rank_month",
                    "月份/季度",
                    [("全年", "all"), ("冬季", "1"), ("春季", "4"), ("夏季", "7"), ("秋季", "10")],
                ),
            ],
        ),
        DoubanCategory(
            type_id="genre_rank",
            type_name="全球影剧类别",
            filters=[
                _filter("sort_by", "影视类型", [("全部", "all"), ("电影", "movie"), ("电视剧", "tv")]),
                _filter(
                    "genre",
                    "题材流派",
                    [
                        ("全部题材", "all"),
                        ("科幻", "scifi"),
                        ("悬疑", "mystery"),
                        ("恐怖", "horror"),
                        ("犯罪", "crime"),
                        ("动作", "action"),
                        ("喜剧", "comedy"),
                        ("爱情", "romance"),
                        ("剧情", "drama"),
                        ("奇幻", "fantasy"),
                        ("动画", "animation"),
                        ("纪录片", "documentary"),
                    ],
                ),
                _filter(
                    "region",
                    "国家/地区",
                    [
                        ("全球", "all"),
                        ("中国大陆", "cn"),
                        ("日本", "jp"),
                        ("韩国", "kr"),
                        ("美国", "us"),
                        ("英国", "gb"),
                        ("欧洲全境", "europe"),
                        ("西语/拉美", "latin"),
                    ],
                ),
                _filter("order_rule", "排序规则", [("热门趋势", "popularity"), ("评分最高", "rating"), ("最新上线", "time")]),
            ],
        ),
        DoubanCategory(
            type_id="movies",
            type_name="全能电影榜单",
            filters=[
                _filter("movie_source", "榜单模式", [("电影综合榜", "general"), ("年度最佳电影", "yearly"), ("按类型探索", "genre")]),
                _filter(
                    "general_sort",
                    "榜单分类",
                    [("流行趋势", "popular"), ("历史高分", "top_rated"), ("全球票房榜", "box_office"), ("奥斯卡佳片", "oscar")],
                ),
                _filter("yearly_sort", "选择年份", _year_options()),
                _filter(
                    "genre_sort",
                    "选择类型",
                    [
                        ("科幻", "878"),
                        ("剧情", "18"),
                        ("悬疑", "9648"),
                        ("动作", "28"),
                        ("喜剧", "35"),
                        ("爱情", "10749"),
                        ("恐怖", "27"),
                        ("犯罪", "80"),
                        ("奇幻", "14"),
                        ("动画", "16"),
                    ],
                ),
            ],
        ),
        DoubanCategory(
            type_id="variety",
            type_name="全球综艺频道",
            filters=[
                _filter(
                    "sort_by",
                    "国家/地区",
                    [("中国大陆", "cn"), ("韩国", "kr"), ("日本", "jp"), ("中国台湾", "tw"), ("中国香港", "hk"), ("欧美综合", "eu_us"), ("全球综合", "all")],
                ),
                _filter(
                    "list_type",
                    "排播与榜单",
                    [("近期热播", "hot"), ("今日更新", "today"), ("明日预告", "tomorrow"), ("流行趋势", "trend"), ("高分神级", "top")],
                ),
            ],
        ),
        DoubanCategory(
            type_id="trends",
            type_name="影剧流行风向",
            filters=[
                _filter(
                    "hub_source",
                    "选择平台",
                    [("IMDb 权威榜单", "imdb"), ("烂番茄风向标", "rt"), ("Trakt 趋势榜", "trakt"), ("豆瓣 国内风向", "douban")],
                ),
                _filter(
                    "imdb_sort",
                    "IMDb 榜单",
                    [
                        ("本周热榜", "trending_week"),
                        ("今日热榜", "trending_day"),
                        ("流行趋势", "popular"),
                        ("高分神作", "top_rated"),
                        ("国产剧热度", "china_tv"),
                        ("国产电影热度", "china_movie"),
                    ],
                ),
                _filter("mediaType", "范围", [("全部", "all"), ("电影", "movie"), ("剧集", "tv")]),
                _filter(
                    "rt_sort",
                    "烂番茄榜单",
                    [("流媒体热映", "rt_movies_home"), ("院线热映", "rt_movies_theater"), ("最佳流媒体", "rt_movies_best"), ("热门剧集", "rt_tv_popular"), ("最新上线", "rt_tv_new")],
                ),
                _filter("trakt_sort", "Trakt 榜单", [("实时热播", "trending"), ("最受欢迎", "popular"), ("最受期待", "anticipated")]),
                _filter("traktType", "Trakt 类型", [("全部", "all"), ("剧集", "shows"), ("电影", "movies")]),
                _filter(
                    "db_sort",
                    "豆瓣榜单",
                    [("热门国产剧", "db_tv_cn"), ("热门综艺", "db_variety"), ("热门电影", "db_movie"), ("热门美剧", "db_tv_us")],
                ),
            ],
        ),
        DoubanCategory(
            type_id="platform",
            type_name="平台分流片库",
            filters=[
                _filter("sort_by", "内容分类", [("电视剧", "tv_drama"), ("综艺", "tv_variety"), ("动漫", "tv_anime"), ("电影", "movie")]),
                _filter(
                    "platform",
                    "播出平台",
                    [
                        ("腾讯视频", "2007"),
                        ("爱奇艺", "1330"),
                        ("优酷", "1419"),
                        ("芒果TV", "1631"),
                        ("Bilibili", "1605"),
                        ("Netflix", "213"),
                        ("Disney+", "2739"),
                        ("HBO", "49"),
                        ("Apple TV+", "2552"),
                    ],
                ),
                _filter("sort", "排序", [("热度最高", "popularity.desc"), ("最新首播", "first_air_date.desc"), ("评分最高", "vote_average.desc")]),
            ],
        ),
        DoubanCategory(
            type_id="top10",
            type_name="流媒体 TOP10",
            filters=[
                _filter(
                    "region",
                    "榜单地区",
                    [("美国", "united-states"), ("韩国", "south-korea"), ("台湾", "taiwan"), ("香港", "hong-kong"), ("日本", "japan"), ("英国", "united-kingdom"), ("全球", "world")],
                ),
                _filter(
                    "platform",
                    "流媒体平台",
                    [("Netflix", "netflix"), ("HBO", "hbo"), ("Disney+", "disney"), ("Apple TV+", "apple-tv"), ("Amazon Prime", "amazon-prime")],
                ),
                _filter("mediaType", "榜单类型", [("剧集", "tv"), ("电影", "movie")]),
            ],
        ),
    ]


@dataclass(slots=True)
class GlobalCatalogController:
    _service: GlobalCatalogServiceProtocol
    uses_page_count_for_pagination: bool = True

    def load_categories(self) -> list[DoubanCategory]:
        return _categories()

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        return self._service.load_items(category_id, page, filters)
