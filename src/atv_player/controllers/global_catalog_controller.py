from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory, VodItem


GENRE_MAP = {
    12: "冒险",
    14: "奇幻",
    16: "动画",
    18: "剧情",
    27: "恐怖",
    28: "动作",
    35: "喜剧",
    36: "历史",
    37: "西部",
    53: "惊悚",
    80: "犯罪",
    99: "纪录片",
    878: "科幻",
    9648: "悬疑",
    10402: "音乐",
    10749: "爱情",
    10751: "家庭",
    10752: "战争",
    10759: "动作冒险",
    10762: "儿童",
    10763: "新闻",
    10764: "真人秀",
    10765: "科幻奇幻",
    10766: "肥皂剧",
    10767: "脱口秀",
    10768: "战综",
    10770: "电视电影",
}

ADVANCED_GENRE_MAP = {
    "all": {"movie": "", "tv": ""},
    "scifi": {"movie": "878", "tv": "10765"},
    "mystery": {"movie": "9648", "tv": "9648"},
    "horror": {"movie": "27", "tv": "27"},
    "crime": {"movie": "80", "tv": "80"},
    "action": {"movie": "28", "tv": "10759"},
    "comedy": {"movie": "35", "tv": "35"},
    "romance": {"movie": "10749", "tv": "10749"},
    "drama": {"movie": "18", "tv": "18"},
    "fantasy": {"movie": "14", "tv": "10765"},
    "animation": {"movie": "16", "tv": "16"},
    "documentary": {"movie": "99", "tv": "99"},
}

REGION_MAP = {
    "all": "",
    "cn": "CN",
    "hk": "HK",
    "tw": "TW",
    "hktw": "HK|TW",
    "jp": "JP",
    "kr": "KR",
    "jpkr": "JP|KR",
    "th": "TH",
    "sg": "SG",
    "my": "MY",
    "in": "IN",
    "apac": "CN|HK|TW|JP|KR|TH|SG|MY|IN",
    "us": "US",
    "gb": "GB",
    "de": "DE",
    "se": "SE",
    "europe": "GB|DE|FR|IT|ES|SE|NO|DK|FI|NL|BE|CH|AT|IE",
    "es": "ES",
    "mx": "MX",
    "latin": "ES|MX|AR|CO|CL|PE|VE",
}


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
            type_name="流媒体TOP10",
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
    ]


class GlobalCatalogService:
    _TMDB_BASE_URL = "https://api.themoviedb.org/3"

    def __init__(
        self,
        tmdb_api_key: str = "",
        *,
        transport: httpx.BaseTransport | None = None,
        client_factory=httpx.Client,
        external_title_loader=None,
    ) -> None:
        self._tmdb_api_key = str(tmdb_api_key or "").strip()
        self._client = client_factory(base_url=self._TMDB_BASE_URL, timeout=20.0, transport=transport)
        self._external_title_loader = external_title_loader or self._default_external_title_loader

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        filters = dict(filters or {})
        page = max(int(page or 1), 1)
        try:
            if category_id == "anime":
                return self._load_anime(page, filters)
            if category_id == "movies":
                return self._load_movies(page, filters)
            if category_id == "genre_rank":
                return self._load_genre_rank(page, filters)
            if category_id == "variety":
                return self._load_variety(page, filters)
            if category_id == "platform":
                return self._load_platform(page, filters)
            if category_id == "trends":
                return self._load_trends(page, filters)
            if category_id == "top10":
                return self._load_top10(page, filters)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return [
                VodItem(
                    vod_id="global_catalog:error",
                    vod_name="全球片单加载失败",
                    vod_content="当前榜单暂时无法获取",
                )
            ], 1
        return [], 0

    def _tmdb_get(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        query = {"api_key": self._tmdb_api_key, "language": "zh-CN"}
        query.update({key: value for key, value in params.items() if value not in ("", None)})
        response = self._client.get(path, params=query)
        response.raise_for_status()
        return dict(response.json())

    def _load_tmdb_list(
        self,
        path: str,
        *,
        media_type: str,
        page: int,
        params: dict[str, object] | None = None,
    ) -> tuple[list[VodItem], int]:
        payload = self._tmdb_get(path, {"page": page, **dict(params or {})})
        items = [self._map_tmdb_item(item, media_type=media_type) for item in payload.get("results") or []]
        return [item for item in items if item is not None], int(payload.get("total_pages") or 1)

    def _load_anime(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        if filters.get("anime_source", "tmdb") != "tmdb":
            return self._load_external_title_source(page, filters.get("anime_source", "tmdb"), filters)
        sort = filters.get("tmdb_sort", "trending")
        sort_by = "popularity.desc"
        if sort == "new":
            sort_by = "first_air_date.desc"
        elif sort == "top":
            sort_by = "vote_average.desc"
        return self._load_tmdb_list(
            "/discover/tv",
            media_type="tv",
            page=page,
            params={"with_genres": "16", "with_original_language": "ja", "sort_by": sort_by},
        )

    def _load_movies(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        source = filters.get("movie_source", "general")
        if source == "yearly":
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={
                    "primary_release_year": filters.get("yearly_sort", "2026"),
                    "sort_by": "vote_average.desc",
                    "vote_count.gte": 500,
                },
            )
        if source == "genre":
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={"with_genres": filters.get("genre_sort", "878"), "sort_by": "popularity.desc"},
            )
        sort = filters.get("general_sort", "popular")
        if sort == "top_rated":
            return self._load_tmdb_list("/movie/top_rated", media_type="movie", page=page)
        if sort == "box_office":
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={"sort_by": "revenue.desc"},
            )
        if sort == "oscar":
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={"with_keywords": "818", "sort_by": "vote_average.desc", "vote_count.gte": 1000},
            )
        return self._load_tmdb_list("/movie/popular", media_type="movie", page=page)

    def _load_genre_rank(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        media_type = filters.get("sort_by", "all")
        if media_type == "all":
            movies, movie_total = self._load_genre_rank_media("movie", page, filters)
            tvs, tv_total = self._load_genre_rank_media("tv", page, filters)
            return [*movies, *tvs][:30], max(movie_total, tv_total)
        return self._load_genre_rank_media(media_type, page, filters)

    def _load_genre_rank_media(
        self,
        media_type: str,
        page: int,
        filters: dict[str, str],
    ) -> tuple[list[VodItem], int]:
        sort_rule = filters.get("order_rule", "popularity")
        sort_by = "popularity.desc"
        if sort_rule == "rating":
            sort_by = "vote_average.desc"
        elif sort_rule == "time":
            sort_by = "primary_release_date.desc" if media_type == "movie" else "first_air_date.desc"
        genre_id = ADVANCED_GENRE_MAP.get(filters.get("genre", "all"), {}).get(media_type, "")
        region = REGION_MAP.get(filters.get("region", "all"), "")
        return self._load_tmdb_list(
            f"/discover/{media_type}",
            media_type=media_type,
            page=page,
            params={
                "sort_by": sort_by,
                "with_genres": genre_id,
                "with_origin_country": region,
                "vote_count.gte": 200 if sort_rule == "rating" else 10,
            },
        )

    def _load_variety(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        regions = {
            "all": "",
            "cn": "CN",
            "kr": "KR",
            "jp": "JP",
            "tw": "TW",
            "hk": "HK",
            "eu_us": "US|GB|DE|FR|IT|ES|CA|AU",
        }
        params: dict[str, object] = {
            "with_genres": "10764|10767",
            "with_origin_country": regions.get(filters.get("sort_by", "cn"), ""),
            "sort_by": "popularity.desc",
        }
        if filters.get("list_type") == "top":
            params["sort_by"] = "vote_average.desc"
            params["vote_count.gte"] = 15
        return self._load_tmdb_list("/discover/tv", media_type="tv", page=page, params=params)

    def _load_platform(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        category = filters.get("sort_by", "tv_drama")
        platform = filters.get("platform", "2007")
        sort = filters.get("sort", "popularity.desc")
        if category == "movie":
            provider_map = {"213": "8", "2739": "337", "49": "1899|15", "2552": "350"}
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={
                    "watch_region": "US",
                    "with_watch_providers": provider_map.get(platform, ""),
                    "sort_by": sort,
                },
            )
        params: dict[str, object] = {"with_networks": platform, "sort_by": sort}
        if category == "tv_anime":
            params["with_genres"] = "16"
        elif category == "tv_variety":
            params["with_genres"] = "10764|10767"
        elif category == "tv_drama":
            params["without_genres"] = "16,10764,10767"
        return self._load_tmdb_list("/discover/tv", media_type="tv", page=page, params=params)

    def _load_trends(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        source = filters.get("hub_source", "imdb")
        if source != "imdb":
            return self._load_external_title_source(page, source, filters)
        category = filters.get("imdb_sort", "trending_week")
        media_type = filters.get("mediaType", "all")
        if category == "china_tv":
            return self._load_tmdb_list(
                "/discover/tv",
                media_type="tv",
                page=page,
                params={"sort_by": "popularity.desc", "with_original_language": "zh"},
            )
        if category == "china_movie":
            return self._load_tmdb_list(
                "/discover/movie",
                media_type="movie",
                page=page,
                params={"sort_by": "popularity.desc", "with_original_language": "zh"},
            )
        if category.startswith("trending_"):
            window = "day" if category == "trending_day" else "week"
            if media_type == "all":
                movies, movie_total = self._load_tmdb_list(f"/trending/movie/{window}", media_type="movie", page=page)
                tvs, tv_total = self._load_tmdb_list(f"/trending/tv/{window}", media_type="tv", page=page)
                return [*movies, *tvs][:30], max(movie_total, tv_total)
            return self._load_tmdb_list(f"/trending/{media_type}/{window}", media_type=media_type, page=page)
        if media_type == "all":
            movies, movie_total = self._load_tmdb_list(f"/movie/{category}", media_type="movie", page=page)
            tvs, tv_total = self._load_tmdb_list(f"/tv/{category}", media_type="tv", page=page)
            return [*movies, *tvs][:30], max(movie_total, tv_total)
        return self._load_tmdb_list(f"/{media_type}/{category}", media_type=media_type, page=page)

    def _load_top10(self, page: int, filters: dict[str, str]) -> tuple[list[VodItem], int]:
        del page
        platform = filters.get("platform", "netflix")
        region = filters.get("region", "united-states")
        media_type = filters.get("mediaType", "tv")
        provider_map = {
            "netflix": "8",
            "disney": "337",
            "hbo": "1899|118",
            "apple-tv": "350",
            "amazon-prime": "119",
        }
        region_map = {
            "united-states": "US",
            "south-korea": "KR",
            "taiwan": "TW",
            "hong-kong": "HK",
            "japan": "JP",
            "united-kingdom": "GB",
            "world": "US",
        }
        items, _total = self._load_tmdb_list(
            f"/discover/{media_type}",
            media_type=media_type,
            page=1,
            params={
                "watch_region": region_map.get(region, "US"),
                "with_watch_providers": provider_map.get(platform, "8"),
                "sort_by": "popularity.desc",
            },
        )
        for index, item in enumerate(items[:10], start=1):
            item.vod_remarks = f"TOP {index}"
        return items[:10], 1

    def _default_external_title_loader(
        self,
        source: str,
        page: int,
        filters: dict[str, str],
    ) -> list[tuple[str, str, str]]:
        del source, page, filters
        return []

    def _load_external_title_source(
        self,
        page: int,
        source: str,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        title_rows = self._external_title_loader(source, page, dict(filters or {}))
        items: list[VodItem] = []
        for title, media_type, remarks in title_rows:
            mapped = self._search_tmdb_title(title, media_type)
            if mapped is None:
                continue
            if remarks:
                mapped.vod_remarks = remarks
            items.append(mapped)
        if not items:
            return [
                VodItem(
                    vod_id="global_catalog:empty",
                    vod_name="暂无数据",
                    vod_content="当前外部榜单暂未返回内容",
                )
            ], 1
        return items, 1

    def _search_tmdb_title(self, title: str, media_type: str) -> VodItem | None:
        normalized_media_type = "movie" if media_type == "movie" else "tv"
        payload = self._tmdb_get(f"/search/{normalized_media_type}", {"query": str(title or "").strip(), "page": 1})
        for result in payload.get("results") or []:
            mapped = self._map_tmdb_item(result, media_type=normalized_media_type)
            if mapped is not None:
                return mapped
        return None

    def _map_tmdb_item(self, item: dict[str, Any], *, media_type: str) -> VodItem | None:
        tmdb_id = str(item.get("id") or "").strip()
        if not tmdb_id:
            return None
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            return None
        date = str(item.get("release_date") or item.get("first_air_date") or "").strip()
        genres = [GENRE_MAP.get(int(genre_id), "") for genre_id in item.get("genre_ids") or []]
        genre_text = " / ".join([genre for genre in genres if genre][:2])
        poster_path = str(item.get("poster_path") or "").strip()
        rating = item.get("vote_average")
        remarks = f"{float(rating):.1f}" if isinstance(rating, int | float) and rating else ""
        return VodItem(
            vod_id=f"tmdb:{media_type}:{tmdb_id}",
            vod_name=title,
            vod_pic=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
            poster_candidates=[f"https://image.tmdb.org/t/p/w500{poster_path}"] if poster_path else [],
            vod_remarks=remarks,
            vod_year=date[:4],
            vod_content=f"{date}\n{item.get('overview') or '暂无简介'}" if date else str(item.get("overview") or "暂无简介"),
            type_name=genre_text or ("电影" if media_type == "movie" else "剧集"),
            vod_tag=media_type,
        )


@dataclass(slots=True)
class GlobalCatalogController:
    _service: GlobalCatalogServiceProtocol
    uses_page_count_for_pagination: bool = True

    @classmethod
    def from_config_tmdb_key(cls, tmdb_api_key: str) -> "GlobalCatalogController":
        return cls(GlobalCatalogService(tmdb_api_key=tmdb_api_key))

    def load_categories(self) -> list[DoubanCategory]:
        return _categories()

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        return self._service.load_items(category_id, page, filters)
