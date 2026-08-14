"""SubSource 字幕站（subsource.net）。

官方 REST API，免费 API Key（注册后在个人资料页生成）。中文字幕统一挂在
``Chinese BG code`` 这个语言名下（对照 bazarr converters/subsource.py 的注释：
站内所有中文字幕都用这个名称上传），因此搜索时按语言名逐个请求。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.subtitles.archive import extract_subtitle
from atv_player.subtitles.errors import (
    SubtitleProviderError,
    SubtitleTokenMissingError,
)
from atv_player.subtitles.languages import language_label, normalize_language
from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleQuery,
    SubtitleSearchItem,
)
from atv_player.subtitles.providers._common import (
    DOWNLOAD_TIMEOUT,
    http_get,
    response_bytes,
    response_json,
)
from atv_player.subtitles.release_parser import parse_release_name


class SubsourceSubtitleProvider:
    provider_id = "subsource"
    label = "SubSource"
    requires_token = True
    notice = ""

    _API_BASE = "https://api.subsource.net/api/v1"
    _PAGE_BASE = "https://subsource.net"
    # 中文字幕全部以 "Chinese BG code" 提交；英文是兜底语言
    _LANGUAGES = ("chinese bg code", "english")
    _PAGE_SIZE = 100

    def __init__(
        self,
        get: Callable[..., Any] = httpx.get,
        api_key_loader: Callable[[], str] | None = None,
    ) -> None:
        self._get = get
        self._api_key_loader = api_key_loader

    def _api_key(self) -> str:
        if self._api_key_loader is None:
            return ""
        try:
            return str(self._api_key_loader() or "").strip()
        except Exception:
            return ""

    def available(self) -> bool:
        return bool(self._api_key())

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        api_key = self._api_key()
        if not api_key:
            raise SubtitleTokenMissingError("SubSource 需要先配置 API Key")
        title = (query.title or "").strip()
        if not title and not query.imdb_id:
            return []

        movie_id = self._find_movie_id(api_key, query, title)
        if not movie_id:
            return []

        items: list[SubtitleSearchItem] = []
        seen: set[str] = set()
        for language_name in self._LANGUAGES:
            for item in self._query_subtitles(api_key, movie_id, language_name, query):
                if item.subtitle_id in seen:
                    continue
                seen.add(item.subtitle_id)
                items.append(item)
        return items

    def _find_movie_id(
        self,
        api_key: str,
        query: SubtitleQuery,
        title: str,
    ) -> str:
        """先按 IMDb id 搜片，没结果再按片名搜（对照 bazarr 的回退顺序）。"""
        results: list[dict[str, Any]] = []
        if query.imdb_id:
            results = self._search_movies(
                api_key,
                {"searchType": "imdb", "imdb": query.imdb_id.removeprefix("tt")},
                query,
            )
        if not results and title:
            results = self._search_movies(
                api_key, {"searchType": "text", "q": title.lower()}, query
            )

        query_title = title.casefold().strip()
        for result in results:
            if "title" not in result or "releaseYear" not in result:
                continue
            site_titles = {str(result["title"]).casefold()}
            alternate = str(result.get("alternateTitle") or "").casefold()
            if alternate:
                site_titles.add(alternate)
            # 与 bazarr 一致用子串匹配：查询片名是站点片名的子串即算命中
            if not any(query_title in site_title for site_title in site_titles):
                continue
            release_year = self._as_int(result.get("releaseYear"))
            if query.year and release_year and release_year != query.year:
                continue
            movie_id = str(result.get("movieId") or "").strip()
            if movie_id:
                return movie_id
        return ""

    def _search_movies(
        self,
        api_key: str,
        extra_params: dict[str, Any],
        query: SubtitleQuery,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = dict(extra_params)
        if query.season is not None:
            params["season"] = query.season
        payload = self._request_json(f"{self._API_BASE}/movies/search", api_key, params)
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        return [row for row in data if isinstance(row, dict)]

    def _query_subtitles(
        self,
        api_key: str,
        movie_id: str,
        language_name: str,
        query: SubtitleQuery,
    ) -> list[SubtitleSearchItem]:
        params: dict[str, Any] = {
            "language": language_name,
            "limit": self._PAGE_SIZE,
            "movieId": movie_id,
        }
        if query.season is not None:
            params["seasonNumber"] = query.season
        if query.episode is not None:
            params["episodeNumber"] = query.episode
        payload = self._request_json(f"{self._API_BASE}/subtitles", api_key, params)
        if payload.get("success") is False:
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []

        items: list[SubtitleSearchItem] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            item = self._build_item(entry, language_name, query)
            if item is not None:
                items.append(item)
        return items

    def _build_item(
        self,
        entry: dict[str, Any],
        language_name: str,
        query: SubtitleQuery,
    ) -> SubtitleSearchItem | None:
        subtitle_id = str(entry.get("subtitleId") or "").strip()
        if not subtitle_id:
            return None
        releases = [
            str(name or "").strip()
            for name in (
                entry.get("releaseInfo")
                if isinstance(entry.get("releaseInfo"), list)
                else [entry.get("releaseInfo")]
            )
            if str(name or "").strip()
        ]
        release_name = ", ".join(releases)
        display = releases[0] if releases else "SubSource 字幕"
        season, episode = self._season_episode(releases)
        if query.season is not None and season is not None and season != query.season:
            return None
        # 无集数的是整季包，保留给 matcher 打分；有集数但与查询不一致的丢弃
        if (
            query.episode is not None
            and episode is not None
            and episode != query.episode
        ):
            return None
        language = normalize_language(
            str(entry.get("language") or language_name),
            release_name,
            display,
        )
        return SubtitleSearchItem(
            provider=self.provider_id,
            provider_label=self.label,
            subtitle_id=subtitle_id,
            name=display,
            language=language,
            language_label=language_label(language),
            format="",
            release_site=self._uploader_name(entry),
            release_name=release_name or display,
            season=season,
            episode=episode,
            hearing_impaired=self._is_hearing_impaired(entry),
            forced=self._is_forced(entry),
            url=f"{self._PAGE_BASE}{entry.get('link') or ''}",
        )

    def _request_json(
        self,
        url: str,
        api_key: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = http_get(
            self._get,
            url,
            params=dict(params, api_key=api_key),
            headers={"Accept": "application/json"},
            site="SubSource",
        )
        return response_json(response, "SubSource")

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        if not item.subtitle_id:
            raise SubtitleProviderError("SubSource 字幕缺少下载 id")
        response = http_get(
            self._get,
            f"{self._API_BASE}/subtitles/{item.subtitle_id}/download",
            params={"api_key": self._api_key()},
            timeout=DOWNLOAD_TIMEOUT,
            site="SubSource",
        )
        return extract_subtitle(response_bytes(response), name_hint=item.name)

    @staticmethod
    def _season_episode(releases: list[str]) -> tuple[int | None, int | None]:
        """从发布名里取季集（bazarr 用 guessit，这里复用 release_parser）。"""
        season: int | None = None
        episode: int | None = None
        for release in releases:
            parsed = parse_release_name(release)
            if season is None:
                season = parsed.season
            if episode is None:
                episode = parsed.episode
            if season is not None and episode is not None:
                break
        return season, episode

    @staticmethod
    def _is_hearing_impaired(entry: dict[str, Any]) -> bool:
        """对照 bazarr：优先看 hearingImpaired 标志，再看备注里的关键词。"""
        if entry.get("hearingImpaired"):
            return True
        commentary = str(entry.get("commentary") or "").lower()
        if any(
            tag in commentary
            for tag in (
                "hi remove",
                "non hi",
                "nonhi",
                "non-hi",
                "non-sdh",
                "non sdh",
                "nonsdh",
                "sdh remove",
            )
        ):
            return False
        return any(
            tag in commentary
            for tag in (
                "_hi_",
                " hi ",
                ".hi.",
                "hi ",
                " hi",
                "sdh",
                "_cc_",
                " cc ",
                ".cc.",
                "closed caption",
            )
        )

    @staticmethod
    def _is_forced(entry: dict[str, Any]) -> bool:
        if entry.get("foreignParts"):
            return True
        commentary = str(entry.get("commentary") or "").lower()
        return "forced" in commentary or "foreign" in commentary

    @staticmethod
    def _uploader_name(entry: dict[str, Any]) -> str:
        contributors = entry.get("contributors")
        if not isinstance(contributors, list):
            return ""
        uploader_id = entry.get("uploaderId")
        for contributor in contributors:
            if isinstance(contributor, dict) and contributor.get("id") == uploader_id:
                return str(contributor.get("displayname") or "")
        return ""

    @staticmethod
    def _as_int(value: object) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None
