"""ASSRT（射手网(伪)）字幕站。

需要免费 token（用户面板获取），配额 20 次/分钟且 token 与 IP 共享。
``sub/detail`` 返回的 ``filelist`` 是站点侧已解包的直链，优先用它，避免解压。

文档: https://2.assrt.net/api/doc
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atv_player.subtitles.archive import extract_subtitle, subtitle_name_sort_key
from atv_player.subtitles.errors import (
    SubtitleProviderError,
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
    raise_for_status,
    response_bytes,
    response_json,
)

# langlist 的键 -> 语言提示词，用于归一
_LANG_FLAGS = {
    "langchs": "简体",
    "langcht": "繁体",
    "langeng": "英文",
    "langdou": "双语",
    "langjpn": "日文",
    "langkor": "韩文",
}

_QUOTA_ERROR_CODE = 30900
_TOKEN_ERROR_CODE = 20001
_NOT_FOUND_ERROR_CODE = 20900


class AssrtSubtitleProvider:
    provider_id = "assrt"
    label = "射手网(伪)"
    requires_token = True
    notice = "字幕服务由 assrt.net 提供"

    _BASE_URL = "https://api.assrt.net/v1"
    _MIN_KEYWORD_LENGTH = 3
    _PAGE_SIZE = 15

    def __init__(
        self,
        get: Callable[..., Any] = httpx.get,
        token_loader: Callable[[], str] | None = None,
    ) -> None:
        self._get = get
        self._token_loader = token_loader

    def _token(self) -> str:
        if self._token_loader is None:
            return ""
        try:
            return str(self._token_loader() or "").strip()
        except Exception:
            return ""

    def available(self) -> bool:
        return bool(self._token())

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        token = self._token()
        if not token:
            raise SubtitleTokenMissingError("射手网需要先配置 Token")
        keyword = self._build_keyword(query)
        if len(keyword) < self._MIN_KEYWORD_LENGTH:
            return []
        # 对照 bazarr：is_file=1 让站点把查询串当文件名解析，
        # "剧名 S01E01" 这种格式命中率比纯片名高很多
        params: dict[str, Any] = {
            "token": token,
            "q": keyword,
            "is_file": 1,
            "cnt": self._PAGE_SIZE,
            "pos": 0,
        }
        payload = self._request("sub/search", params)
        subs = self._subs_of(payload)
        return [
            self._build_item(entry)
            for entry in subs
            if isinstance(entry, dict) and entry.get("id") is not None
        ]

    @staticmethod
    def _build_keyword(query: SubtitleQuery) -> str:
        """对照 bazarr 的 query 构造：剧集拼 S01E01，电影拼年份。"""
        parts: list[str] = []
        title = (query.title or query.file_name).strip()
        if title:
            parts.append(title)
        if query.season is not None and query.episode is not None:
            parts.append(f"S{query.season:02d}E{query.episode:02d}")
        elif query.episode is not None:
            parts.append(f"E{query.episode:02d}")
        elif query.year:
            parts.append(str(query.year))
        return " ".join(parts).strip()

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        # 射手网会把 JSON 错误码漏进 HTTP 状态码（文档：ClientFail/ServerFail
        # 分别映射 4xx/5xx，实测 20001→400；用户遇到过 492 这类非标准码），
        # 真正的错误信息在响应体里，所以先解析 body 再兜底状态码
        response = http_get(
            self._get,
            f"{self._BASE_URL}/{endpoint}",
            params=params,
            headers={"Accept": "application/json"},
            site="射手网",
            ignore_status=True,
        )
        try:
            payload = response_json(response, "射手网")
        except SubtitleProviderError as exc:
            # body 不是 JSON：若状态码异常先按状态码报错，否则报解析失败
            raise_for_status(response, "射手网")
            raise SubtitleProviderError("射手网返回了无法解析的响应") from exc
        status = payload.get("status")
        if status not in (0, None):
            if status == _QUOTA_ERROR_CODE:
                raise SubtitleQuotaExceededError(
                    "射手网配额超限（20 次/分钟，Token 与 IP 共享），稍后再试"
                )
            if status == _TOKEN_ERROR_CODE:
                raise SubtitleProviderError(
                    "射手网 Token 无效，请到 assrt.net 用户面板核对后重新填写"
                )
            if status == _NOT_FOUND_ERROR_CODE:
                raise SubtitleProviderError("射手网上该字幕已下架，请换一条")
            message = str(payload.get("errmsg") or payload.get("error") or "").strip()
            raise SubtitleProviderError(f"射手网错误 {status}: {message or '请求失败'}")
        return payload

    @staticmethod
    def _subs_of(payload: dict[str, Any]) -> list[Any]:
        sub = payload.get("sub")
        if not isinstance(sub, dict):
            return []
        subs = sub.get("subs")
        return subs if isinstance(subs, list) else []

    @staticmethod
    def _language_hint(entry: dict[str, Any]) -> str:
        lang = entry.get("lang")
        if not isinstance(lang, dict):
            return ""
        parts = [str(lang.get("desc") or "")]
        langlist = lang.get("langlist")
        if isinstance(langlist, dict):
            parts.extend(hint for key, hint in _LANG_FLAGS.items() if langlist.get(key))
        return " ".join(part for part in parts if part)

    def _build_item(self, entry: dict[str, Any]) -> SubtitleSearchItem:
        name = str(entry.get("native_name") or "").strip()
        video_name = str(entry.get("videoname") or "").strip()
        display = name or video_name or "射手网字幕"
        language = normalize_language(self._language_hint(entry), display, video_name)
        return SubtitleSearchItem(
            provider=self.provider_id,
            provider_label=self.label,
            subtitle_id=str(entry.get("id")),
            name=display,
            language=language,
            language_label=language_label(language),
            format=str(entry.get("subtype") or "").strip(),
            release_site=str(entry.get("release_site") or "").strip(),
            vote_score=self._as_float(entry.get("vote_score")),
            context={"videoname": video_name},
        )

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return 0.0

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        token = self._token()
        if not token:
            raise SubtitleTokenMissingError("射手网需要先配置 Token")
        payload = self._request(
            "sub/detail",
            {"token": token, "id": item.subtitle_id},
        )
        subs = self._subs_of(payload)
        detail = next((row for row in subs if isinstance(row, dict)), None)
        if detail is None:
            raise SubtitleProviderError("射手网未返回字幕详情")
        url, name_hint = self._pick_download_target(detail)
        if not url:
            raise SubtitleProviderError("射手网未返回可用的下载地址")
        response = http_get(
            self._get,
            url,
            timeout=DOWNLOAD_TIMEOUT,
            site="射手网",
        )
        return extract_subtitle(response_bytes(response), name_hint=name_hint)

    @staticmethod
    def _pick_download_target(detail: dict[str, Any]) -> tuple[str, str]:
        """优先取 filelist 里的直链，退回整包地址。"""
        filelist = detail.get("filelist")
        if isinstance(filelist, list):
            rows = [
                row
                for row in filelist
                if isinstance(row, dict) and str(row.get("url") or "").strip()
            ]
            rows.sort(key=lambda row: subtitle_name_sort_key(str(row.get("f") or "")))
            if rows:
                return (
                    str(rows[0].get("url") or "").strip(),
                    str(rows[0].get("f") or "").strip(),
                )
        return (
            str(detail.get("url") or "").strip(),
            str(detail.get("filename") or "").strip(),
        )
