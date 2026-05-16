from __future__ import annotations

import hashlib
import html
import re
import time
from urllib.parse import urlencode

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord

_RISK_CONTROL_CODES = {-352, -412}
_BROWSER_HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "referer": "https://www.bilibili.com/",
    "origin": "https://www.bilibili.com",
    "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,ja;q=0.6,zh-TW;q=0.5",
    "accept": "*/*",
}
_MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def _strip_html(value: object) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def _split_tokens(value: object) -> list[str]:
    return [
        token
        for token in (part.strip() for part in re.split(r"[/|、,，]", str(value or "").strip()))
        if token
    ]


def _collapse_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip()


class BilibiliMetadataProvider:
    name = "bilibili"
    _SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
    _SEARCH_TYPE = "media_bangumi"

    def __init__(self, get=httpx.get) -> None:
        self._get = get

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        self._prime_web_state()
        payload = self._search_payload(title)
        matches: list[MetadataMatch] = []
        for item in (payload.get("data") or {}).get("result") or []:
            if not isinstance(item, dict):
                continue
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
        genres = self._genres(payload)
        detail_fields: list[dict[str, object]] = []
        for label, value in (
            ("分区", str(payload.get("season_type_name") or "").strip()),
            ("更新状态", str(payload.get("index_show") or "").strip()),
            ("声优", _collapse_text(payload.get("cv"))),
            ("制作信息", _collapse_text(payload.get("staff"))),
        ):
            if value:
                detail_fields.append({"label": label, "value": value})
        return MetadataRecord(
            provider=self.name,
            provider_id=str(match.provider_id or "").strip(),
            title=str(payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster="",
            overview=_collapse_text(payload.get("desc") or payload.get("overview")),
            rating="",
            genres=genres,
            country=str(payload.get("areas") or payload.get("country") or "").strip(),
            detail_fields=detail_fields,
        )

    def _search_detail_payload(self, match: MetadataMatch) -> dict[str, object]:
        payload = self._search_payload(str(match.title or "").strip())
        for item in (payload.get("data") or {}).get("result") or []:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_item(item)
            if str(normalized.get("provider_id") or "").strip() == str(match.provider_id or "").strip():
                return normalized
        return {}

    def _search_payload(self, keyword: str) -> dict:
        params = {"keyword": keyword, "search_type": self._SEARCH_TYPE}
        params.update(self._build_wbi_params(params))
        payload = self._request_json(self._SEARCH_URL, params=params)
        if payload.get("code") in _RISK_CONTROL_CODES:
            self._refresh_ticket()
            retry_params = {"keyword": keyword, "search_type": self._SEARCH_TYPE}
            retry_params.update(self._build_wbi_params(retry_params))
            payload = self._request_json(self._SEARCH_URL, params=retry_params)
        if payload.get("code") != 0:
            raise RuntimeError(f"Bilibili metadata search failed: {payload.get('code')}")
        return payload

    def _request_json(self, url: str, *, params: dict[str, str] | None = None) -> dict:
        response = self._get(
            url,
            params=params,
            headers=dict(_BROWSER_HEADERS),
            timeout=10.0,
            follow_redirects=True,
        )
        return response.json()

    def _prime_web_state(self) -> None:
        self._request_json("https://api.bilibili.com/x/frontend/finger/spi")

    def _refresh_ticket(self) -> None:
        self._request_json(
            "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
            params={"key_id": "ec02", "hexsign": "ignored", "context[ts]": str(int(time.time()))},
        )

    def _build_wbi_params(self, params: dict[str, str]) -> dict[str, str]:
        nav = self._request_json("https://api.bilibili.com/x/web-interface/nav")
        wbi_img = (nav.get("data") or {}).get("wbi_img") or {}
        img_key = str(wbi_img.get("img_url") or "").rsplit("/", 1)[-1].split(".", 1)[0]
        sub_key = str(wbi_img.get("sub_url") or "").rsplit("/", 1)[-1].split(".", 1)[0]
        mixin_source = img_key + sub_key
        mixin = "".join(mixin_source[index] for index in _MIXIN_KEY_ENC_TAB if index < len(mixin_source))[:32]
        signed = {key: str(value) for key, value in params.items()}
        signed["wts"] = str(int(time.time()))
        query = urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5(f"{query}{mixin}".encode()).hexdigest()
        return signed

    def _normalize_item(self, item: dict[str, object]) -> dict[str, object]:
        normalized = dict(item)
        normalized["title"] = _strip_html(item.get("title") or item.get("org_title"))
        normalized["provider_id"] = self._provider_id(item)
        normalized["year"] = self._year_value(item)
        normalized["genres"] = self._genres(item)
        normalized["subtitle"] = self._subtitle_value(item)
        return normalized

    def _provider_id(self, item: dict[str, object]) -> str:
        for key in ("url", "goto_url"):
            value = str(item.get(key) or "").strip()
            if value:
                return f"https:{value}" if value.startswith("//") else value
        season_id = str(item.get("season_id") or item.get("pgc_season_id") or "").strip()
        if season_id:
            return f"https://www.bilibili.com/bangumi/play/ss{season_id}"
        media_id = str(item.get("media_id") or "").strip()
        return f"media:{media_id}" if media_id else ""

    def _year_value(self, item: dict[str, object]) -> str:
        for key in ("pubtime", "pub_time"):
            raw = item.get(key)
            try:
                timestamp = int(raw or 0)
            except (TypeError, ValueError):
                continue
            if timestamp > 0:
                return time.strftime("%Y", time.localtime(timestamp))
        return ""

    def _genres(self, item: dict[str, object]) -> list[str]:
        values = item.get("genres")
        if isinstance(values, list):
            return [str(value or "").strip() for value in values if str(value or "").strip()]
        return _split_tokens(item.get("styles"))

    def _subtitle_value(self, item: dict[str, object]) -> str:
        values = [
            str(item.get("season_type_name") or "").strip(),
            str(item.get("index_show") or "").strip(),
        ]
        return " · ".join(value for value in values if value)
