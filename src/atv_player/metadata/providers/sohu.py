from __future__ import annotations

import html
import re
import time

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord

_SEARCH_URL = "https://m.so.tv.sohu.com/search/pc/keyword"
_SEARCH_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "origin": "https://tv.sohu.com",
    "referer": "https://tv.sohu.com/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}
_CID_TYPE_NAMES = {
    1: "电影",
    2: "电视剧",
    7: "综艺",
    8: "纪录片",
    16: "动漫",
}
_TMDB_OVERRIDE_BADGES = {"自制", "独播"}


def _strip_highlight(value: object) -> str:
    return html.unescape(str(value or "").replace("<<<", "").replace(">>>", "")).strip()


def _split_tokens(value: object) -> list[str]:
    return [
        token
        for token in (part.strip() for part in re.split(r"[/|、,，]", str(value or "").strip()))
        if token
    ]


def _link_titles(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [title for item in items if isinstance(item, dict) if (title := str(item.get("title") or "").strip())]


class SohuMetadataProvider:
    name = "sohu"

    def __init__(self, get=httpx.get) -> None:
        self._get = get

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        payload = self._search_payload(title)
        matches: list[MetadataMatch] = []
        for item in self._iter_album_items(payload):
            normalized = self._normalize_item(item)
            provider_id = str(normalized.get("provider_id") or "").strip()
            match_title = str(normalized.get("title") or "").strip()
            if not provider_id or not match_title:
                continue
            match = MetadataMatch(
                provider=self.name,
                provider_id=provider_id,
                title=match_title,
                year=str(normalized.get("year") or "").strip(),
                raw=normalized,
            )
            match.score = score_match(candidate, match)
            matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = dict(match.raw)
        if not payload:
            payload = self._search_detail_payload(match)
        detail_fields: list[dict[str, object]] = []
        update_text = str(payload.get("updateNotification") or "").strip()
        if update_text:
            detail_fields.append({"label": "更新状态", "value": update_text})
        return MetadataRecord(
            provider=self.name,
            provider_id=str(match.provider_id or "").strip(),
            title=str(payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("poster") or "").strip(),
            overview=str(payload.get("overview") or "").strip(),
            actors=list(payload.get("actors") or []),
            directors=list(payload.get("directors") or []),
            genres=list(payload.get("genres") or []),
            country=str(payload.get("country") or "").strip(),
            detail_fields=detail_fields,
        )

    def _search_payload(self, keyword: str) -> dict[str, object]:
        response = self._get(
            _SEARCH_URL,
            params={
                "key": keyword,
                "tabsChosen": 0,
                "poster": 4,
                "tuple": 6,
                "extSource": 1,
                "show_star_detail": 3,
                "pay": 1,
                "hl": 3,
                "type": 1,
                "page": 1,
                "page_size": 15,
                "timeStamp": int(time.time() * 1000),
                "plat": -1,
                "ssl": 0,
            },
            headers=dict(_SEARCH_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        payload = response.json()
        if int(payload.get("status") or 0) != 200:
            raise RuntimeError(f"Sohu metadata search failed: {payload.get('status')}")
        return payload

    def _search_detail_payload(self, match: MetadataMatch) -> dict[str, object]:
        payload = self._search_payload(str(match.title or "").strip())
        target_id = str(match.provider_id or "").strip()
        for item in self._iter_album_items(payload):
            normalized = self._normalize_item(item)
            if str(normalized.get("provider_id") or "").strip() == target_id:
                return normalized
        return {}

    def _iter_album_items(self, payload: dict[str, object]) -> list[dict[str, object]]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [
            item
            for item in items
            if isinstance(item, dict)
            if int(item.get("is_album") or 1) == 1
            if int(item.get("show_type") or 0) in {1, 2}
        ]

    def _normalize_item(self, item: dict[str, object]) -> dict[str, object]:
        badges = self._badges(item)
        cid = int(item.get("cid") or 0)
        genres = _link_titles(item.get("type_links")) or _split_tokens(item.get("second_cate_name"))
        return {
            "title": _strip_highlight(item.get("album_name")),
            "provider_id": self._provider_id(item),
            "year": self._year_value(item),
            "overview": str(item.get("desc") or "").strip(),
            "poster": str(item.get("ver_high_pic") or item.get("ver_big_pic") or "").strip(),
            "country": str(item.get("area") or "").strip(),
            "actors": _link_titles(item.get("actor_links")),
            "directors": _link_titles(item.get("director_links")),
            "genres": genres,
            "typeName": _CID_TYPE_NAMES.get(cid, ""),
            "category": {"value": " / ".join(genres)} if genres else {"value": _CID_TYPE_NAMES.get(cid, "")},
            "corner_mark": dict(item.get("corner_mark") or {}) if isinstance(item.get("corner_mark"), dict) else {},
            "isOnly": int(item.get("isOnly") or 0),
            "isExclusive": int(item.get("isExclusive") or 0),
            "updateNotification": str(item.get("updateNotification") or "").strip(),
            "sohu_badges": badges,
            "sohu_preferred_over_tmdb": any(badge in _TMDB_OVERRIDE_BADGES for badge in badges),
        }

    def _provider_id(self, item: dict[str, object]) -> str:
        for key in ("pc_detail_url", "pc_url"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return _strip_highlight(item.get("album_name"))

    def _year_value(self, item: dict[str, object]) -> str:
        value = item.get("year")
        if isinstance(value, int):
            return str(value) if 1000 <= value <= 9999 else ""
        text = str(value or "").strip()
        return text if text.isdigit() and len(text) == 4 else ""

    def _badges(self, item: dict[str, object]) -> list[str]:
        badges: list[str] = []
        corner_mark = item.get("corner_mark")
        if isinstance(corner_mark, dict):
            text = str(corner_mark.get("text") or "").strip()
            if text:
                badges.append(text)
        if int(item.get("isOnly") or 0) == 1 and "独播" not in badges:
            badges.append("独播")
        if int(item.get("isExclusive") or 0) == 1 and "独家" not in badges:
            badges.append("独家")
        return badges
