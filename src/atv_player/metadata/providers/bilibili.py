from __future__ import annotations

from dataclasses import replace
import hashlib
import html
import re
import time
from urllib.parse import urlencode

import httpx

from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord

_RISK_CONTROL_CODES = {-352, -412}
_ANIME_CATEGORY_TOKENS = ("动漫", "动画", "番剧", "国创", "anime")
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

    def can_enrich(self, context) -> bool:
        query = context.to_query()
        values = " ".join(
            value.strip().lower()
            for value in (str(query.category_name or ""), str(query.type_name or ""))
            if value and value.strip()
        )
        return any(token in values for token in _ANIME_CATEGORY_TOKENS)

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
        season_id = self._season_id_from_payload(payload)
        if season_id:
            detail = self._season_detail_payload(season_id)
            sections = self._season_section_payload(season_id)
            payload.update(self._merge_season_payload(payload, detail))
            normalized_episodes = self._normalize_bilibili_episodes(detail, sections)
            if normalized_episodes:
                payload["episodes"] = normalized_episodes
                match.raw["episodes"] = normalized_episodes
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
            poster=str(payload.get("poster") or "").strip(),
            overview=_collapse_text(payload.get("desc") or payload.get("overview")),
            rating="",
            genres=genres,
            country=str(payload.get("areas") or payload.get("country") or "").strip(),
            detail_fields=detail_fields,
        )

    def _hydrate_episode_candidate(self, candidate):
        raw = dict(getattr(candidate, "raw", {}) or {})
        season_id = self._season_id_from_payload(raw)
        if not season_id:
            return candidate
        detail = self._season_detail_payload(season_id)
        sections = self._season_section_payload(season_id)
        normalized_episodes = self._normalize_bilibili_episodes(detail, sections)
        if not normalized_episodes:
            return candidate
        raw.update(self._merge_season_payload(raw, detail))
        raw["season_id"] = season_id
        raw["episodes"] = normalized_episodes
        return replace(candidate, raw=raw)

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
        normalized["season_id"] = self._season_id_from_payload(item)
        normalized["year"] = self._year_value(item)
        normalized["genres"] = self._genres(item)
        normalized["subtitle"] = self._subtitle_value(item)
        return normalized

    def _season_id_from_payload(self, payload: dict[str, object]) -> str:
        for key in ("season_id", "pgc_season_id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        provider_id = str(payload.get("provider_id") or payload.get("url") or "").strip()
        match = re.search(r"/ss(\d+)", provider_id)
        return match.group(1) if match else ""

    def _season_detail_payload(self, season_id: str) -> dict[str, object]:
        payload = self._request_json("https://api.bilibili.com/pgc/view/web/season", params={"season_id": season_id})
        if payload.get("code") != 0:
            raise RuntimeError(f"Bilibili season detail failed: {payload.get('code')}")
        return dict(payload.get("result") or {})

    def _season_section_payload(self, season_id: str) -> dict[str, object]:
        payload = self._request_json("https://api.bilibili.com/pgc/web/season/section", params={"season_id": season_id})
        if payload.get("code") != 0:
            return {}
        return dict(payload.get("result") or {})

    def _merge_season_payload(self, current: dict[str, object], detail: dict[str, object]) -> dict[str, object]:
        merged = dict(current)
        title = str(detail.get("title") or "").strip()
        if title:
            merged["title"] = title
        overview = _collapse_text(detail.get("evaluate") or detail.get("overview") or detail.get("desc"))
        if overview:
            merged["overview"] = overview
        poster = str(detail.get("cover") or "").strip()
        if poster:
            merged["poster"] = poster
        country = self._detail_areas(detail)
        if country:
            merged["areas"] = country
        styles = self._detail_styles(detail)
        if styles:
            merged["genres"] = styles
            merged["styles"] = styles
        actors = _collapse_text(str(detail.get("actors") or "").replace("\n", " / "))
        if actors:
            merged["cv"] = actors
        staff = _collapse_text(str(detail.get("staff") or "").replace("\n", " / "))
        if staff:
            merged["staff"] = staff
        index_show = str((detail.get("new_ep") or {}).get("desc") or "").strip()
        if index_show:
            merged["index_show"] = index_show
        season_type_name = str((detail.get("type") or {}).get("name") or detail.get("season_type_name") or "").strip()
        if season_type_name:
            merged["season_type_name"] = season_type_name
        return merged

    def _detail_areas(self, detail: dict[str, object]) -> str:
        areas = detail.get("areas")
        if not isinstance(areas, list):
            return str(detail.get("areas") or "").strip()
        names = [str(item.get("name") or "").strip() for item in areas if isinstance(item, dict)]
        return " / ".join(name for name in names if name)

    def _detail_styles(self, detail: dict[str, object]) -> list[str]:
        styles = detail.get("styles")
        if not isinstance(styles, list):
            return []
        return [str(item.get("name") or "").strip() for item in styles if isinstance(item, dict) and str(item.get("name") or "").strip()]

    def _normalize_bilibili_episodes(self, detail: dict[str, object], sections: dict[str, object]) -> list[dict[str, object]]:
        main_section = sections.get("main_section") if isinstance(sections, dict) else {}
        rows = []
        if isinstance(main_section, dict):
            rows = list(main_section.get("episodes") or [])
        if not rows:
            rows = list(detail.get("episodes") or [])
        normalized: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                episode_number = int(str(row.get("title") or "").strip())
            except (TypeError, ValueError):
                continue
            normalized.append(
                {
                    "episode_number": episode_number,
                    "title": str(row.get("title") or "").strip(),
                    "long_title": str(row.get("long_title") or row.get("share_copy") or row.get("show_title") or "").strip(),
                    "badge": str(row.get("badge") or "").strip(),
                    "episode_type": "main",
                    "sort": episode_number,
                }
            )
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
