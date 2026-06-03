from __future__ import annotations

import re
from urllib.parse import urlparse

from atv_player.episode_titles import extract_season_number
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord

_TV_SEARCH_CACHE_VERSION = "tv-season-year-v3"

_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNIT_VALUES = {
    "十": 10,
    "百": 100,
    "千": 1000,
}


def _title_has_season_marker(value: object) -> bool:
    return re.search(
        r"(?:第\s*[0-9零一二两三四五六七八九十百]+\s*季|season\s*\d+|\bS\d+\b)",
        str(value or "").strip(),
        re.IGNORECASE,
    ) is not None


def _provider_id_with_season(media_type: str, provider_id: str, title: str) -> str:
    if media_type != "tv":
        return provider_id
    season_number = extract_season_number(title)
    if season_number is None:
        return provider_id
    return f"{provider_id}:season:{season_number}"


def _season_number_from_provider_id(provider_id: str) -> tuple[str, int | None]:
    match = re.match(r"^(.*):season:(\d+)$", str(provider_id or "").strip())
    if match is None:
        return str(provider_id or "").strip(), None
    return match.group(1), int(match.group(2))


def _tmdb_person_image(path: object) -> str:
    return str(path or "").strip()


def _tmdb_person_url(person_id: object) -> str:
    text = str(person_id or "").strip()
    if not text:
        return ""
    return f"https://www.themoviedb.org/person/{text}"


def _poster_url_from_payload(payload: dict[str, object], poster_base_url: str = "https://image.tmdb.org/t/p/original") -> str:
    url = str(payload.get("poster_url") or "").strip()
    if url:
        return url
    path = str(payload.get("poster_path") or "").strip()
    if not path:
        return ""
    return f"{poster_base_url}{path}"


def _tmdb_cast_role(item: dict[str, object]) -> str:
    roles = item.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and str(role.get("character") or "").strip():
                return str(role.get("character") or "").strip()
    return str(item.get("character") or "").strip()


def _tmdb_crew_job(item: dict[str, object]) -> str:
    jobs = item.get("jobs")
    if isinstance(jobs, list):
        for job in jobs:
            if isinstance(job, dict) and str(job.get("job") or "").strip():
                return str(job.get("job") or "").strip()
    return str(item.get("job") or "").strip()


def _cast_detail(item: dict[str, object]) -> dict[str, object]:
    detail = {
        "name": str(item.get("name") or "").strip(),
        "role": _tmdb_cast_role(item),
        "avatar": _tmdb_person_image(item.get("profile_path")),
    }
    url = _tmdb_person_url(item.get("id"))
    if url:
        detail["url"] = url
    return detail


def _crew_detail(item: dict[str, object]) -> dict[str, object]:
    detail = {
        "name": str(item.get("name") or "").strip(),
        "job": _tmdb_crew_job(item),
        "avatar": _tmdb_person_image(item.get("profile_path")),
    }
    url = _tmdb_person_url(item.get("id"))
    if url:
        detail["url"] = url
    return detail


def _backdrop_score(img: dict[str, object]) -> float:
    def _num(value: object) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    vote = _num(img.get("vote_average"))
    count = _num(img.get("vote_count"))
    width = _num(img.get("width"))
    height = _num(img.get("height"))
    ratio = (width / height) if width > 0 and height > 0 else 16 / 9
    ratio_penalty = abs(ratio - 16 / 9) * 1.4
    return vote * 1000 + min(count, 1000) * 2 + min(width, 3840) / 20 - ratio_penalty * 100


def _best_backdrop_urls(payload: dict[str, object], base_url: str, *, limit: int = 8) -> list[str]:
    candidates: list[dict[str, object]] = []
    default_path = str(payload.get("backdrop_path") or "").strip()
    if default_path:
        candidates.append(
            {
                "file_path": default_path,
                "vote_average": 11,
                "vote_count": float("inf"),
                "width": 1280,
                "height": 720,
            }
        )
    images = payload.get("images") if isinstance(payload, dict) else None
    raw_backdrops = (images or {}).get("backdrops") if isinstance(images, dict) else None
    for img in raw_backdrops or []:
        if isinstance(img, dict) and str(img.get("file_path") or "").strip():
            candidates.append(img)
    candidates.sort(key=_backdrop_score, reverse=True)
    seen: set[str] = set()
    urls: list[str] = []
    for img in candidates:
        path = str(img.get("file_path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        urls.append(f"{base_url}{path}")
        if len(urls) >= limit:
            break
    return urls


def _season_rows(payload: dict[str, object], *, poster_base_url: str = "https://image.tmdb.org/t/p/original") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for season in payload.get("seasons") or []:
        if not isinstance(season, dict):
            continue
        normalized = dict(season)
        poster_url = _poster_url_from_payload(normalized, poster_base_url)
        if poster_url:
            normalized["poster_url"] = poster_url
        rows.append(normalized)
    return rows


def _format_tmdb_rating(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        normalized = round(float(text), 1)
    except (TypeError, ValueError):
        return ""
    return f"{normalized:.1f}"


def infer_tmdb_media_type(query: MetadataQuery) -> str:
    media_hints = " ".join(
        str(value or "").strip().lower()
        for value in (query.category_name, query.type_name)
        if str(value or "").strip()
    )
    if any(token in media_hints for token in ("电影", "影片", "movie")):
        return "movie"
    if any(token in media_hints for token in ("电视剧", "剧集", "动漫", "番剧", "综艺", "纪录片", "tv")):
        return "tv"
    if _title_has_season_marker(query.title):
        return "tv"
    return ""


def _normalize_title(value: object) -> str:
    normalized = re.sub(r"\s+", "", str(value or "").strip().lower())
    return re.sub(r"[零一二两三四五六七八九十百千]+", _replace_chinese_number_token, normalized)


def _replace_chinese_number_token(match: re.Match[str]) -> str:
    parsed = _parse_chinese_number(match.group(0))
    return str(parsed) if parsed is not None else match.group(0)


def _parse_chinese_number(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    total = 0
    current = 0
    saw_value = False
    for char in text:
        if char in _CHINESE_DIGIT_VALUES:
            current = _CHINESE_DIGIT_VALUES[char]
            saw_value = True
            continue
        if char in _CHINESE_UNIT_VALUES:
            saw_value = True
            if current == 0:
                current = 1
            total += current * _CHINESE_UNIT_VALUES[char]
            current = 0
            continue
        return None
    total += current
    if not saw_value:
        return None
    return total


def _strip_search_season_suffix(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = re.sub(
        r"(?:\s*[-:：]\s*)?(?:第\s*[0-9零一二两三四五六七八九十百]+\s*季|season\s*\d+|s\d+)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or text


def _extract_year(payload: dict[str, object], *, media_type: str) -> str:
    raw = str(
        payload.get("year")
        or (
            payload.get("release_date")
            if media_type == "movie"
            else payload.get("first_air_date")
        )
        or ""
    ).strip()
    return raw[:4] if len(raw) >= 4 and raw[:4].isdigit() else ""


def _search_result_raw(
    item: dict[str, object],
    *,
    poster_base_url: str = "https://image.tmdb.org/t/p/original",
    season_number: int | None = None,
) -> dict[str, object]:
    raw: dict[str, object] = {}
    if season_number is not None:
        raw["season_number"] = season_number
    poster_url = _poster_url_from_payload(item, poster_base_url)
    if poster_url:
        raw["poster_url"] = poster_url
    overview = str(item.get("overview") or "").strip()
    if overview:
        raw["overview"] = overview
    rating = _format_tmdb_rating(item.get("vote_average"))
    if rating:
        raw["rating"] = rating
    original_language = str(item.get("original_language") or "").strip()
    if original_language:
        raw["original_language"] = original_language
    original_name = str(item.get("original_name") or item.get("original_title") or "").strip()
    if original_name:
        raw["original_name"] = original_name
    return raw


def _extract_year_int(payload: dict[str, object], *, media_type: str) -> int | None:
    year = _extract_year(payload, media_type=media_type)
    return int(year) if year.isdigit() else None


def _should_reject_year_mismatch(media_type: str, expected_year: str, actual_year: str) -> bool:
    if media_type != "movie":
        return False
    return bool(expected_year and actual_year and actual_year != str(expected_year).strip())


def _split_names(values: list[object] | None) -> list[str]:
    return [str(value or "").strip() for value in values or [] if str(value or "").strip()]


def _person_name_tokens(value: object) -> set[str]:
    if isinstance(value, list):
        values = value
    else:
        values = re.split(r"[,/|、]", str(value or ""))
    return {
        re.sub(
            r"[\s\-_:.：,，/\\|·•'\"`()（）《》【】\[\]]+",
            "",
            str(item or "").strip().lower(),
        )
        for item in values
        if str(item or "").strip()
    } - {""}


_TMDB_PLATFORM_LABELS = {
    "bilibili": "B站",
    "iqiyi": "爱奇艺",
    "mgtv": "芒果",
    "migu": "咪咕",
    "sohu": "搜狐",
    "tencent": "腾讯",
    "youku": "优酷",
}
_TMDB_PLATFORM_HOSTS = {
    "bilibili.com": "bilibili",
    "iqiyi.com": "iqiyi",
    "mgtv.com": "mgtv",
    "migu.cn": "migu",
    "miguvideo.com": "migu",
    "sohu.com": "sohu",
    "v.qq.com": "tencent",
    "youku.com": "youku",
}
_TMDB_NETWORK_NAME_MAP = {
    "bilibili": "bilibili",
    "bilibilibangumi": "bilibili",
    "dragontelevision东方卫视": "",
    "iqiyi": "iqiyi",
    "jiangsutelevision": "",
    "miguvideo": "migu",
    "sohu": "sohu",
    "sohutv": "sohu",
    "tencentvideo": "tencent",
    "youku": "youku",
}


def _normalize_tmdb_platform_name(value: object) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def _tmdb_platform_key_from_network_name(value: object) -> str:
    normalized = _normalize_tmdb_platform_name(value)
    return _TMDB_NETWORK_NAME_MAP.get(normalized, "")


def _tmdb_platform_key_from_homepage(url: object) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    host = (urlparse(text).hostname or "").lower().strip(".")
    if not host:
        return ""
    if host in _TMDB_PLATFORM_HOSTS:
        return _TMDB_PLATFORM_HOSTS[host]
    for domain, provider in _TMDB_PLATFORM_HOSTS.items():
        if host.endswith(f".{domain}"):
            return provider
    return ""


def _tmdb_platform_label(provider: str) -> str:
    return _TMDB_PLATFORM_LABELS.get(str(provider or "").strip(), str(provider or "").strip())


def _tmdb_network_platform_keys(payload: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for item in payload.get("networks") or []:
        if not isinstance(item, dict):
            continue
        key = _tmdb_platform_key_from_network_name(item.get("name"))
        if key:
            keys.add(key)
    return keys


def _tmdb_watch_provider_entries(payload: dict[str, object], *, require_url: bool = True) -> list[dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    watch_payload = payload.get("watch/providers")
    if not isinstance(watch_payload, dict):
        watch_payload = payload.get("watch_providers")
    country = (watch_payload or {}).get("results", {}).get("CN") if isinstance(watch_payload, dict) else None
    if isinstance(country, dict):
        shared_link = str(country.get("link") or country.get("url") or "").strip()
        shared_link_provider = _tmdb_platform_key_from_homepage(shared_link)
        for bucket in ("flatrate", "free", "ads", "buy", "rent"):
            providers = country.get(bucket)
            if not isinstance(providers, list):
                continue
            for item in providers:
                if not isinstance(item, dict):
                    continue
                provider = _tmdb_platform_key_from_network_name(item.get("provider_name"))
                if not provider:
                    continue
                current = entries.get(provider)
                if current is None:
                    current = {
                        "provider": provider,
                        "label": _tmdb_platform_label(provider),
                        "url": "",
                    }
                    entries[provider] = current
                explicit_url = str(item.get("url") or item.get("link") or "").strip()
                if explicit_url:
                    current["url"] = explicit_url
                elif not current["url"] and shared_link and shared_link_provider == provider:
                    current["url"] = shared_link
    homepage = str(payload.get("homepage") or "").strip()
    homepage_provider = _tmdb_platform_key_from_homepage(homepage)
    if homepage_provider and homepage_provider in _tmdb_network_platform_keys(payload):
        current = entries.get(homepage_provider)
        if current is None:
            entries[homepage_provider] = {
                "provider": homepage_provider,
                "label": _tmdb_platform_label(homepage_provider),
                "url": homepage,
            }
        elif not str(current.get("url") or "").strip():
            current["url"] = homepage
    if not require_url:
        for provider in _tmdb_network_platform_keys(payload):
            if provider not in entries:
                entries[provider] = {
                    "provider": provider,
                    "label": _tmdb_platform_label(provider),
                    "url": "",
                }
    values = list(entries.values())
    if require_url:
        return [entry for entry in values if str(entry.get("url") or "").strip()]
    return values


class TMDBProvider:
    name = "tmdb"

    def __init__(self, client) -> None:
        self._client = client

    def can_enrich(self, _context) -> bool:
        return True

    def _poster_base_url(self) -> str:
        return str(self._client.image_base("poster") or "https://image.tmdb.org/t/p/original").strip()

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str] | None:
        media_type = infer_tmdb_media_type(candidate)
        title = candidate.title
        year = candidate.year
        if media_type == "tv":
            title = _strip_search_season_suffix(title)
            title = f"{title}\x1f{_TV_SEARCH_CACHE_VERSION}"
            if _title_has_season_marker(candidate.title) and extract_season_number(candidate.title) != 1:
                year = ""
        return (title, year)

    def _search_year(self, media_type: str, candidate: MetadataQuery) -> str:
        if media_type != "tv":
            return candidate.year
        if _title_has_season_marker(candidate.title) and extract_season_number(candidate.title) != 1:
            return ""
        return candidate.year

    def _tv_category_preference(self, candidate: MetadataQuery, item: dict[str, object]) -> int:
        category = str(candidate.category_name or "").strip().lower()
        try:
            genre_ids = {int(value) for value in item.get("genre_ids") or []}
        except (TypeError, ValueError):
            genre_ids = set()
        if any(token in category for token in ("动漫", "动画", "anime", "国创", "番剧")):
            return 2 if 16 in genre_ids else 0
        if any(token in category for token in ("短剧", "短片")):
            return 2 if 10766 in genre_ids else 0
        if any(token in category for token in ("电视剧", "剧集", "连续剧", "真人")):
            if 10766 in genre_ids:
                return 0
            return 2 if 16 not in genre_ids else 1
        return 0

    def _tv_year_closeness(self, candidate: MetadataQuery, item: dict[str, object]) -> int:
        if not str(candidate.year or "").isdigit():
            return 0
        item_year = _extract_year_int(item, media_type="tv")
        if item_year is None:
            return 0
        return -abs(item_year - int(str(candidate.year)))

    def _tv_season_coverage(self, item: dict[str, object], query_title: str) -> int:
        season_number = extract_season_number(query_title)
        if season_number is None:
            return 0
        tmdb_id = str(item.get("id") or "").strip()
        if not tmdb_id:
            return 0
        try:
            payload = self._client.get_tv_season_detail(tmdb_id, season_number) or {}
        except Exception:
            return 0
        episodes = payload.get("episodes")
        return 1 if isinstance(episodes, list) and len(episodes) > 0 else 0

    def _tv_original_people_match_score(
        self,
        candidate: MetadataQuery,
        item: dict[str, object],
    ) -> int:
        query_directors = _person_name_tokens(candidate.vod_director)
        query_actors = _person_name_tokens(candidate.vod_actor)
        if not query_directors and not query_actors:
            return 0
        tmdb_id = str(item.get("id") or "").strip()
        if not tmdb_id:
            return 0
        try:
            payload = self._client.get_tv_detail(tmdb_id) or {}
        except Exception:
            return 0
        credits = payload.get("aggregate_credits") or payload.get("credits") or {}
        cast = credits.get("cast") if isinstance(credits, dict) else []
        crew = credits.get("crew") if isinstance(credits, dict) else []
        actor_names = _person_name_tokens(
            [
                cast_item.get("name")
                for cast_item in cast or []
                if isinstance(cast_item, dict)
            ]
        )
        director_names = _person_name_tokens(
            [
                crew_item.get("name")
                for crew_item in crew or []
                if isinstance(crew_item, dict)
                and _tmdb_crew_job(crew_item).lower() == "director"
            ]
        )
        return (
            len(query_directors & director_names) * 3
            + len(query_actors & actor_names)
        )

    def _select_best_tv_match(
        self,
        candidate: MetadataQuery,
        search_title: str,
        payload: list[dict[str, object]],
    ) -> list[MetadataMatch]:
        if not payload:
            return []
        normalized_search_title = _normalize_title(search_title)
        normalized_query_title = _normalize_title(candidate.title)
        query_base = _normalize_title(_strip_search_season_suffix(candidate.title))

        ranked: list[tuple[tuple[int, int, int, int, int, int], MetadataMatch]] = []
        for raw_item in payload:
            item = dict(raw_item)
            provider_id = str(item.get("id") or "").strip()
            item_title = str(
                item.get("title")
                or item.get("name")
                or item.get("original_title")
                or item.get("original_name")
                or ""
            ).strip()
            if not provider_id or not item_title:
                continue
            item_year = _extract_year(item, media_type="tv")
            title_for_match = search_title
            match = self._match_from_payload("tv", item, title_for_match, candidate.year, candidate.title)
            if match is None:
                if _should_reject_year_mismatch("tv", candidate.year, item_year):
                    continue
                fallback_raw: dict[str, object] = {}
                if extract_season_number(candidate.title) is not None:
                    fallback_raw["season_number"] = extract_season_number(candidate.title)
                fallback_poster = _poster_url_from_payload(item, self._poster_base_url())
                if fallback_poster:
                    fallback_raw["poster_url"] = fallback_poster
                match = MetadataMatch(
                    provider=self.name,
                    provider_id=f"tv:{_provider_id_with_season('tv', provider_id, candidate.title)}",
                    title=item_title,
                    year=item_year,
                    score=0.55,
                    raw=fallback_raw,
                )
            normalized_item_title = _normalize_title(item_title)
            item_base = _normalize_title(_strip_search_season_suffix(item_title))
            exact_query_match = 1 if normalized_item_title == normalized_query_title else 0
            exact_search_match = 1 if normalized_item_title == normalized_search_title else 0
            base_match = 1 if query_base and item_base == query_base else 0
            category_preference = self._tv_category_preference(candidate, item)
            season_coverage = self._tv_season_coverage(item, candidate.title)
            people_match_score = self._tv_original_people_match_score(candidate, item)
            year_closeness = self._tv_year_closeness(candidate, item)
            ranked.append(
                (
                    (
                        exact_query_match,
                        exact_search_match,
                        base_match,
                        season_coverage,
                        people_match_score,
                        category_preference,
                        year_closeness,
                    ),
                    match,
                )
            )
        if not ranked:
            return []
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [ranked[0][1]]

    def _match_from_payload(
        self,
        media_type: str,
        item: dict[str, object],
        title: str,
        year: str,
        query_title: str,
    ) -> MetadataMatch | None:
        item_title = str(item.get("title") or item.get("name") or "").strip()
        normalized_title = _normalize_title(title)
        normalized_item = _normalize_title(item_title)
        aliases = {
            _normalize_title(alias)
            for alias in item.get("aliases") or []
            if _normalize_title(alias)
        }
        if normalized_title not in {normalized_item, *aliases}:
            return None
        item_year = _extract_year(item, media_type=media_type)
        if _should_reject_year_mismatch(media_type, year, item_year):
            return None
        provider_id = str(item.get("id") or "").strip()
        if not provider_id:
            return None
        season_number = extract_season_number(query_title) if media_type == "tv" else None
        return MetadataMatch(
            provider=self.name,
            provider_id=f"{media_type}:{_provider_id_with_season(media_type, provider_id, query_title)}",
            title=item_title,
            year=item_year,
            score=1.0,
            raw=_search_result_raw(item, season_number=season_number),
        )

    def _search_media_type(self, media_type: str, candidate: MetadataQuery) -> list[MetadataMatch]:
        search_fn = self._client.search_movie if media_type == "movie" else self._client.search_tv
        search_title = _strip_search_season_suffix(candidate.title) if media_type == "tv" else candidate.title
        search_year = self._search_year(media_type, candidate)
        payload = search_fn(search_title, year=search_year)
        if not payload and search_title != candidate.title and not (media_type == "tv" and _title_has_season_marker(candidate.title)):
            payload = search_fn(candidate.title, year=search_year)
        if media_type == "tv":
            return self._select_best_tv_match(candidate, search_title, payload)
        matches: list[MetadataMatch] = []
        fallback_matches: list[MetadataMatch] = []
        for item in payload:
            normalized_item = dict(item)
            match = self._match_from_payload(media_type, normalized_item, search_title, candidate.year, candidate.title)
            if match is not None:
                matches.append(match)
                continue
            provider_id = str(normalized_item.get("id") or "").strip()
            item_title = str(
                normalized_item.get("title")
                or normalized_item.get("name")
                or normalized_item.get("original_title")
                or normalized_item.get("original_name")
                or ""
            ).strip()
            if not provider_id or not item_title:
                continue
            item_year = _extract_year(normalized_item, media_type=media_type)
            if _should_reject_year_mismatch(media_type, candidate.year, item_year):
                continue
            fb_raw = _search_result_raw(
                normalized_item,
                season_number=extract_season_number(candidate.title) if media_type == "tv" else None,
            )
            fallback_matches.append(
                MetadataMatch(
                    provider=self.name,
                    provider_id=f"{media_type}:{_provider_id_with_season(media_type, provider_id, candidate.title)}",
                    title=item_title,
                    year=item_year,
                    score=0.55,
                    raw=fb_raw,
                )
            )
        return matches or fallback_matches[:1]

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title:
            return []
        inferred = infer_tmdb_media_type(candidate)
        if inferred:
            return self._search_media_type(inferred, candidate)
        for media_type in ("movie", "tv"):
            matches = self._search_media_type(media_type, candidate)
            if matches:
                return matches
        return []

    def _search_all_media_type(self, media_type: str, candidate: MetadataQuery) -> list[MetadataMatch]:
        search_fn = self._client.search_movie if media_type == "movie" else self._client.search_tv
        search_title = _strip_search_season_suffix(candidate.title) if media_type == "tv" else candidate.title
        search_year = self._search_year(media_type, candidate)
        payload = search_fn(search_title, year=search_year)
        if not payload and search_title != candidate.title and not (media_type == "tv" and _title_has_season_marker(candidate.title)):
            payload = search_fn(candidate.title, year=search_year)
        if media_type == "tv":
            ranked: list[tuple[tuple[int, int, int, int, int, int], MetadataMatch]] = []
            for raw_item in payload:
                item = dict(raw_item)
                provider_id = str(item.get("id") or "").strip()
                item_title = str(
                    item.get("title")
                    or item.get("name")
                    or item.get("original_title")
                    or item.get("original_name")
                    or ""
                ).strip()
                if not provider_id or not item_title:
                    continue
                item_year = _extract_year(item, media_type="tv")
                match = self._match_from_payload("tv", item, search_title, candidate.year, candidate.title)
                if match is None:
                    if _should_reject_year_mismatch("tv", candidate.year, item_year):
                        continue
                    sa_raw = _search_result_raw(
                        item,
                        poster_base_url=self._poster_base_url(),
                        season_number=extract_season_number(candidate.title),
                    )
                    match = MetadataMatch(
                        provider=self.name,
                        provider_id=f"tv:{_provider_id_with_season('tv', provider_id, candidate.title)}",
                        title=item_title,
                        year=item_year,
                        score=0.55,
                        raw=sa_raw,
                    )
                ranked.append(
                    (
                        (
                            1 if _normalize_title(item_title) == _normalize_title(candidate.title) else 0,
                            1 if _normalize_title(item_title) == _normalize_title(search_title) else 0,
                            self._tv_original_people_match_score(candidate, item),
                            self._tv_category_preference(candidate, item),
                            self._tv_season_coverage(item, candidate.title),
                            self._tv_year_closeness(candidate, item),
                        ),
                        match,
                    )
                )
            ranked.sort(key=lambda entry: entry[0], reverse=True)
            return [match for _, match in ranked]
        all_matches: list[MetadataMatch] = []
        fallback_matches: list[MetadataMatch] = []
        for item in payload:
            normalized_item = dict(item)
            match = self._match_from_payload(media_type, normalized_item, search_title, candidate.year, candidate.title)
            if match is not None:
                all_matches.append(match)
                continue
            provider_id = str(normalized_item.get("id") or "").strip()
            item_title = str(
                normalized_item.get("title")
                or normalized_item.get("name")
                or normalized_item.get("original_title")
                or normalized_item.get("original_name")
                or ""
            ).strip()
            if not provider_id or not item_title:
                continue
            item_year = _extract_year(normalized_item, media_type=media_type)
            if _should_reject_year_mismatch(media_type, candidate.year, item_year):
                continue
            fb_raw = _search_result_raw(
                normalized_item,
                poster_base_url=self._poster_base_url(),
                season_number=extract_season_number(candidate.title) if media_type == "tv" else None,
            )
            fallback_matches.append(
                MetadataMatch(
                    provider=self.name,
                    provider_id=f"{media_type}:{_provider_id_with_season(media_type, provider_id, candidate.title)}",
                    title=item_title,
                    year=item_year,
                    score=0.55,
                    raw=fb_raw,
                )
            )
        return all_matches + fallback_matches

    def search_all(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title:
            return []
        inferred = infer_tmdb_media_type(candidate)
        if inferred:
            return self._search_all_media_type(inferred, candidate)
        all_matches: list[MetadataMatch] = []
        for media_type in ("movie", "tv"):
            all_matches.extend(self._search_all_media_type(media_type, candidate))
        return all_matches

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        media_type, provider_id = str(match.provider_id).split(":", 1)
        provider_id, season_number = _season_number_from_provider_id(provider_id)
        payload = (
            self._client.get_movie_detail(provider_id)
            if media_type == "movie"
            else self._client.get_tv_detail(provider_id)
        )
        season_overview = ""
        detail_fields: list[dict[str, object]] = []
        if media_type == "tv" and season_number is not None:
            season_payload = self._client.get_tv_season_detail(provider_id, season_number) or {}
            season_overview = str(season_payload.get("overview") or "").strip()
            detail_fields.append({"label": "episodes", "value": list(season_payload.get("episodes") or [])})
        if media_type == "tv":
            detail_fields.append({"label": "seasons", "value": _season_rows(payload, poster_base_url=self._poster_base_url())})
            number_of_episodes = str(payload.get("number_of_episodes") or "").strip()
            if number_of_episodes:
                detail_fields.append(
                    {"label": "number_of_episodes", "value": number_of_episodes}
                )
            number_of_seasons = str(payload.get("number_of_seasons") or "").strip()
            if number_of_seasons:
                detail_fields.append(
                    {"label": "number_of_seasons", "value": number_of_seasons}
                )
            last_ep = payload.get("last_episode_to_air")
            if isinstance(last_ep, dict):
                detail_fields.append({"label": "last_episode_to_air", "value": last_ep})
            next_ep = payload.get("next_episode_to_air")
            if isinstance(next_ep, dict):
                detail_fields.append({"label": "next_episode_to_air", "value": next_ep})
            last_air = str(payload.get("last_air_date") or "").strip()
            if last_air:
                detail_fields.append({"label": "last_air_date", "value": last_air})
        watch_providers = _tmdb_watch_provider_entries(payload)
        if watch_providers:
            detail_fields.append({"label": "watch_providers", "value": watch_providers})
        watch_provider_sources = _tmdb_watch_provider_entries(payload, require_url=False)
        if watch_provider_sources:
            detail_fields.append({"label": "watch_provider_sources", "value": watch_provider_sources})
        genres = [
            str(item.get("name") or "").strip()
            for item in payload.get("genres") or []
            if str(item.get("name") or "").strip()
        ]
        if media_type == "movie":
            credits = payload.get("credits") or {}
            cast = credits.get("cast") or []
            crew = credits.get("crew") or []
            alt_titles = ((payload.get("alternative_titles") or {}).get("titles") or [])
        else:
            credits = payload.get("aggregate_credits") or {}
            cast = credits.get("cast") or []
            crew = credits.get("crew") or []
            alt_titles = ((payload.get("alternative_titles") or {}).get("results") or [])
        cast_details = [_cast_detail(item) for item in cast]
        cast_details = [item for item in cast_details if item.get("name")]
        crew_details = [_crew_detail(item) for item in crew]
        crew_details = [item for item in crew_details if item.get("name")]
        actors = [str(item.get("name") or "").strip() for item in cast_details]
        directors = [
            str(item.get("name") or "").strip()
            for item in crew_details
            if str(item.get("job") or "").strip() == "Director"
        ]
        aliases = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in alt_titles
            if str(item.get("title") or item.get("name") or "").strip()
        ]
        external_ids = payload.get("external_ids") or {}
        backdrops = _best_backdrop_urls(payload, self._client.image_base("backdrop"))
        return MetadataRecord(
            provider=self.name,
            provider_id=match.provider_id,
            title=str(payload.get("title") or payload.get("name") or match.title or "").strip(),
            original_title=str(payload.get("original_title") or payload.get("original_name") or "").strip(),
            year=_extract_year(payload, media_type=media_type) or str(match.year or "").strip(),
            poster=str(payload.get("poster_url") or "").strip(),
            backdrop=str(payload.get("backdrop_url") or "").strip(),
            backdrops=backdrops,
            overview=season_overview or str(payload.get("overview") or "").strip(),
            rating=_format_tmdb_rating(payload.get("vote_average")),
            actors=_split_names(actors),
            directors=_split_names(directors),
            cast_details=cast_details,
            crew_details=crew_details,
            genres=_split_names(genres),
            aliases=_split_names(aliases),
            imdb_id=str(external_ids.get("imdb_id") or "").strip(),
            tmdb_id=str(payload.get("id") or "").strip(),
            detail_fields=detail_fields,
        )

    def get_detail_full(self, match: MetadataMatch) -> MetadataRecord:
        media_type, provider_id = str(match.provider_id).split(":", 1)
        provider_id, season_number = _season_number_from_provider_id(provider_id)
        if media_type == "movie":
            return self.get_detail(match)
        payload = self._client.get_tv_detail_with_season(provider_id, season_number=season_number)
        season_overview = ""
        detail_fields: list[dict[str, object]] = []
        season_key = f"season/{season_number}" if season_number else None
        if season_key and isinstance(payload.get(season_key), dict):
            season_payload = payload[season_key]
            season_overview = str(season_payload.get("overview") or "").strip()
            detail_fields.append({"label": "episodes", "value": list(season_payload.get("episodes") or [])})
        elif season_number is not None:
            season_payload = self._client.get_tv_season_detail(provider_id, season_number) or {}
            season_overview = str(season_payload.get("overview") or "").strip()
            detail_fields.append({"label": "episodes", "value": list(season_payload.get("episodes") or [])})
        detail_fields.append({"label": "seasons", "value": _season_rows(payload, poster_base_url=self._poster_base_url())})
        number_of_episodes = str(payload.get("number_of_episodes") or "").strip()
        if number_of_episodes:
            detail_fields.append(
                {"label": "number_of_episodes", "value": number_of_episodes}
            )
        number_of_seasons = str(payload.get("number_of_seasons") or "").strip()
        if number_of_seasons:
            detail_fields.append(
                {"label": "number_of_seasons", "value": number_of_seasons}
            )
        last_ep = payload.get("last_episode_to_air")
        if isinstance(last_ep, dict):
            detail_fields.append({"label": "last_episode_to_air", "value": last_ep})
        next_ep = payload.get("next_episode_to_air")
        if isinstance(next_ep, dict):
            detail_fields.append({"label": "next_episode_to_air", "value": next_ep})
        last_air = str(payload.get("last_air_date") or "").strip()
        if last_air:
            detail_fields.append({"label": "last_air_date", "value": last_air})
        watch_providers = _tmdb_watch_provider_entries(payload)
        if watch_providers:
            detail_fields.append({"label": "watch_providers", "value": watch_providers})
        watch_provider_sources = _tmdb_watch_provider_entries(payload, require_url=False)
        if watch_provider_sources:
            detail_fields.append({"label": "watch_provider_sources", "value": watch_provider_sources})
        genres = [
            str(item.get("name") or "").strip()
            for item in payload.get("genres") or []
            if str(item.get("name") or "").strip()
        ]
        credits = payload.get("credits") or {}
        cast = credits.get("cast") or []
        crew = credits.get("crew") or []
        alt_titles = ((payload.get("alternative_titles") or {}).get("results") or [])
        cast_details = [_cast_detail(item) for item in cast]
        cast_details = [item for item in cast_details if item.get("name")]
        crew_details = [_crew_detail(item) for item in crew]
        crew_details = [item for item in crew_details if item.get("name")]
        actors = [str(item.get("name") or "").strip() for item in cast_details]
        directors = [
            str(item.get("name") or "").strip()
            for item in crew_details
            if str(item.get("job") or "").strip() == "Director"
        ]
        aliases = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in alt_titles
            if str(item.get("title") or item.get("name") or "").strip()
        ]
        external_ids = payload.get("external_ids") or {}
        backdrops = _best_backdrop_urls(payload, self._client.image_base("backdrop"))
        return MetadataRecord(
            provider=self.name,
            provider_id=match.provider_id,
            title=str(payload.get("title") or payload.get("name") or match.title or "").strip(),
            original_title=str(payload.get("original_title") or payload.get("original_name") or "").strip(),
            year=_extract_year(payload, media_type="tv") or str(match.year or "").strip(),
            poster=str(payload.get("poster_url") or "").strip(),
            backdrop=str(payload.get("backdrop_url") or "").strip(),
            backdrops=backdrops,
            overview=season_overview or str(payload.get("overview") or "").strip(),
            rating=_format_tmdb_rating(payload.get("vote_average")),
            actors=_split_names(actors),
            directors=_split_names(directors),
            cast_details=cast_details,
            crew_details=crew_details,
            genres=_split_names(genres),
            aliases=_split_names(aliases),
            imdb_id=str(external_ids.get("imdb_id") or "").strip(),
            tmdb_id=str(payload.get("id") or "").strip(),
            detail_fields=detail_fields,
        )
