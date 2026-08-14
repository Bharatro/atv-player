"""OpenSubtitles.com 字幕站。

需要免费 API Key，免费层每天 5 次下载，超额后 ``/download`` 会返回 406。
搜索不消耗下载配额，所以列表能正常出，点下载才可能撞上限。

文档: https://opensubtitles.stoplight.io/docs/opensubtitles-api
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.subtitles.archive import extract_subtitle
from atv_player.subtitles.errors import (
    SubtitleQuotaExceededError,
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
    http_post,
    response_bytes,
    response_json,
)

# OpenSubtitles 要求带上能标识应用的 User-Agent
_USER_AGENT = "atv-player v0.1.0"
_DEFAULT_LANGUAGES = "zh-CN,zh-TW,en"


class OpenSubtitlesProvider:
    provider_id = "opensubtitles"
    label = "OpenSubtitles"
    requires_token = True
    notice = "免费账号每天限 5 次下载"

    _BASE_URL = "https://api.opensubtitles.com/api/v1"

    def __init__(
        self,
        get: Callable[..., Any] = httpx.get,
        post: Callable[..., Any] = httpx.post,
        api_key_loader: Callable[[], str] | None = None,
        languages: str = "",
    ) -> None:
        self._get = get
        self._post = post
        self._api_key_loader = api_key_loader
        self._languages = str(languages or _DEFAULT_LANGUAGES).strip()

    def _api_key(self) -> str:
        if self._api_key_loader is None:
            return ""
        try:
            return str(self._api_key_loader() or "").strip()
        except Exception:
            return ""

    def available(self) -> bool:
        return bool(self._api_key())

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Api-Key": api_key,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        api_key = self._api_key()
        if not api_key:
            raise SubtitleTokenMissingError("OpenSubtitles 需要先配置 API Key")
        keyword = query.title.strip()
        if not keyword and not query.has_media_id:
            return []
        params: dict[str, Any] = {"languages": self._languages}
        # 有权威 id 时优先按 id 搜
        if query.imdb_id:
            params["imdb_id"] = query.imdb_id.removeprefix("tt")
        elif query.tmdb_id:
            params["tmdb_id"] = query.tmdb_id
        else:
            params["query"] = keyword
        if query.episode is not None:
            params["episode_number"] = query.episode
            if query.season is not None:
                params["season_number"] = query.season
        if query.year:
            params["year"] = query.year
        response = http_get(
            self._get,
            f"{self._BASE_URL}/subtitles",
            params=params,
            headers=self._headers(api_key),
            site="OpenSubtitles",
        )
        payload = response_json(response, "OpenSubtitles")
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        items: list[SubtitleSearchItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = self._build_item(row)
            if item is not None:
                items.append(item)
        return items

    def _build_item(self, row: dict[str, Any]) -> SubtitleSearchItem | None:
        attributes = row.get("attributes")
        if not isinstance(attributes, dict):
            return None
        files = attributes.get("files")
        file_id = ""
        file_name = ""
        if isinstance(files, list):
            for entry in files:
                if isinstance(entry, dict) and entry.get("file_id") is not None:
                    file_id = str(entry.get("file_id"))
                    file_name = str(entry.get("file_name") or "").strip()
                    break
        if not file_id:
            return None
        release = str(attributes.get("release") or "").strip()
        raw_language = str(attributes.get("language") or "").strip()
        display = release or file_name or "OpenSubtitles 字幕"
        language = normalize_language(raw_language, display, file_name)
        return SubtitleSearchItem(
            provider=self.provider_id,
            provider_label=self.label,
            subtitle_id=file_id,
            name=display,
            language=language,
            language_label=language_label(language),
            format=str(attributes.get("format") or "").strip(),
            release_site=str(attributes.get("uploader_name") or "").strip(),
            release_name=release,
            hearing_impaired=bool(attributes.get("hearing_impaired")),
            forced=bool(attributes.get("foreign_parts_only")),
            download_count=self._as_int(attributes.get("download_count")),
            vote_score=self._as_float(attributes.get("ratings")),
            context={"file_name": file_name},
        )

    @staticmethod
    def _as_int(value: object) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return 0.0

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        api_key = self._api_key()
        if not api_key:
            raise SubtitleTokenMissingError("OpenSubtitles 需要先配置 API Key")
        headers = self._headers(api_key)
        headers["Content-Type"] = "application/json"
        response = http_post(
            self._post,
            f"{self._BASE_URL}/download",
            json_body={"file_id": self._as_int(item.subtitle_id)},
            headers=headers,
            site="OpenSubtitles",
        )
        payload = response_json(response, "OpenSubtitles")
        link = str(payload.get("link") or "").strip()
        if not link:
            message = str(payload.get("message") or "").strip()
            raise SubtitleQuotaExceededError(
                f"OpenSubtitles 无法下载: {message or '可能已超出每日配额'}"
            )
        file_response = http_get(
            self._get,
            link,
            timeout=DOWNLOAD_TIMEOUT,
            site="OpenSubtitles",
        )
        name_hint = (
            str(payload.get("file_name") or "").strip()
            or item.context.get("file_name", "")
            or item.name
        )
        return extract_subtitle(response_bytes(file_response), name_hint=name_hint)
