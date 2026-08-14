"""SubDL 字幕站。

官方 REST API，免费 API Key（每天 2000 次请求）。``unpack=1`` 会额外返回压缩包内
逐集的字幕直链，可直接下载单个 .srt，省去解压这一步。

文档: https://subdl.com/api-doc
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.subtitles.archive import extract_subtitle, subtitle_name_sort_key
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


class SubDLSubtitleProvider:
    provider_id = "subdl"
    label = "SubDL"
    requires_token = True
    notice = ""

    _SEARCH_URL = "https://api.subdl.com/api/v1/subtitles"
    _DOWNLOAD_BASE = "https://dl.subdl.com"
    _DEFAULT_LANGUAGES = "ZH,EN"
    _PAGE_SIZE = 30

    def __init__(
        self,
        get: Callable[..., Any] = httpx.get,
        api_key_loader: Callable[[], str] | None = None,
        languages: str = "",
    ) -> None:
        self._get = get
        self._api_key_loader = api_key_loader
        self._languages = str(languages or self._DEFAULT_LANGUAGES).strip()

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
            raise SubtitleTokenMissingError("SubDL 需要先配置 API Key")
        keyword = (query.file_name or query.title).strip()
        if not keyword:
            return []
        params: dict[str, Any] = {
            "api_key": api_key,
            "subs_per_page": self._PAGE_SIZE,
            "unpack": 1,
            "hi": 1,
            "comment": 1,
            "releases": 1,
            # 对照 bazarr：bazarr=1 过滤掉不兼容的图片字幕/txt 字幕，
            # 只保留文本字幕（v1 端点的官方过滤标志
            "bazarr": 1,
        }
        # 有权威 id 时优先按 id 搜，命中率远高于按片名
        if query.imdb_id:
            params["imdb_id"] = query.imdb_id.removeprefix("tt")
        elif query.tmdb_id:
            params["tmdb_id"] = query.tmdb_id
        elif query.title:
            params["film_name"] = query.title
        else:
            params["file_name"] = query.file_name
        # 只要有季或集就按剧集搜：整季搜索（只有 season 没有 episode）也很常见，
        # 不能因为 episode 为空就误判成电影
        if query.season is not None or query.episode is not None:
            params["type"] = "tv"
            if query.season is not None:
                params["season_number"] = query.season
            if query.episode is not None:
                params["episode_number"] = query.episode
        elif query.title or query.has_media_id:
            params["type"] = "movie"
        if query.year:
            params["year"] = query.year

        payload = self._request(dict(params, languages=self._languages))
        subtitles = payload.get("subtitles")
        if not subtitles:
            # 语言代码可能不被接受或过滤过窄，放开语言再试一次。
            payload = self._request(params)
            subtitles = payload.get("subtitles")
        if not isinstance(subtitles, list):
            return []
        items: list[SubtitleSearchItem] = []
        for entry in subtitles:
            if isinstance(entry, dict):
                items.extend(self._build_items(entry, query))
        return items

    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        response = http_get(
            self._get,
            self._SEARCH_URL,
            params=params,
            headers={"Accept": "application/json"},
            site="SubDL",
        )
        payload = response_json(response, "SubDL")
        if payload.get("status") is False:
            message = str(payload.get("error") or "").strip()
            raise SubtitleProviderError(f"SubDL: {message or '搜索失败'}")
        return payload

    def _build_items(
        self,
        entry: dict[str, Any],
        query: SubtitleQuery,
    ) -> list[SubtitleSearchItem]:
        release = str(entry.get("release_name") or "").strip()
        base_name = str(entry.get("name") or "").strip()
        unpack_files = entry.get("unpack_files")
        if isinstance(unpack_files, list) and unpack_files:
            return self._build_unpacked_items(unpack_files, release, query)
        url = self._absolute_url(str(entry.get("url") or "").strip())
        if not url:
            return []
        display = release or base_name or "SubDL 字幕"
        language = normalize_language(
            str(entry.get("language") or ""),
            display,
            base_name,
        )
        return [
            SubtitleSearchItem(
                provider=self.provider_id,
                provider_label=self.label,
                subtitle_id=url,
                name=display,
                language=language,
                language_label=language_label(language),
                format=self._format_of(base_name),
                release_site=str(entry.get("author") or "").strip(),
                release_name=release or base_name,
                season=self._as_int(entry.get("season")),
                episode=self._as_int(entry.get("episode")),
                hearing_impaired=bool(entry.get("hi")),
                url=url,
            )
        ]

    def _build_unpacked_items(
        self,
        unpack_files: list[Any],
        release: str,
        query: SubtitleQuery,
    ) -> list[SubtitleSearchItem]:
        rows = [row for row in unpack_files if isinstance(row, dict)]
        if query.episode is not None:
            matched = [
                row
                for row in rows
                if self._as_int(row.get("episode")) == query.episode
            ]
            # 整季包里没有对应集数时不强行降级，交给其他结果。
            rows = matched or []
        rows.sort(key=lambda row: subtitle_name_sort_key(str(row.get("name") or "")))
        items: list[SubtitleSearchItem] = []
        for row in rows:
            url = self._absolute_url(str(row.get("url") or "").strip())
            if not url:
                continue
            file_name = str(row.get("name") or "").strip()
            display = str(row.get("release_name") or "").strip() or file_name or release
            language = normalize_language(
                str(row.get("language") or ""),
                file_name,
                display,
            )
            items.append(
                SubtitleSearchItem(
                    provider=self.provider_id,
                    provider_label=self.label,
                    subtitle_id=url,
                    name=display or "SubDL 字幕",
                    language=language,
                    language_label=language_label(language),
                    format=str(row.get("format") or "").strip()
                    or self._format_of(file_name),
                    release_name=display or release,
                    season=self._as_int(row.get("season")),
                    episode=self._as_int(row.get("episode")),
                    hearing_impaired=bool(row.get("hi")),
                    url=url,
                    context={"file_name": file_name},
                )
            )
        return items

    def _absolute_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._DOWNLOAD_BASE}/{url.lstrip('/')}"

    @staticmethod
    def _as_int(value: object) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_of(name: str) -> str:
        lowered = name.casefold()
        for suffix in (".ass", ".ssa", ".srt", ".vtt"):
            if lowered.endswith(suffix):
                return suffix.lstrip(".")
        return ""

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        url = item.url or item.subtitle_id
        if not url:
            raise SubtitleProviderError("SubDL 字幕缺少下载地址")
        # 免费 Key 不能给下载链接带 api_key（那会走付费配额），走匿名下载即可。
        response = http_get(
            self._get,
            url,
            timeout=DOWNLOAD_TIMEOUT,
            site="SubDL",
        )
        return extract_subtitle(
            response_bytes(response),
            name_hint=item.context.get("file_name", "") or item.name,
        )
