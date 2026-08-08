from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse, parse_qs

_REXXAR_SEARCH_URL = "https://m.douban.com/rexxar/api/v2/search"
_REXXAR_DETAIL_URL = "https://m.douban.com/rexxar/api/v2/movie"
_PUBLIC_SEARCH_URL = "https://api.douban.com/v2/movie/search"
_PUBLIC_APIKEY = "0ac44ae016490db2204ce0a042db2916"

_REXXAR_HEADERS = {
    "Referer": "https://m.douban.com/movie/",
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}
_PUBLIC_HEADERS = {
    "Referer": "https://api.douban.com",
    "Content-Type": "application/json",
    "User-Agent": _REXXAR_HEADERS["User-Agent"],
}


@dataclass(frozen=True, slots=True)
class DoubanSubject:
    douban_id: str
    title: str
    year: str
    type_name: str


@dataclass(frozen=True, slots=True)
class DoubanVendor:
    provider: str
    media_id: str


class DoubanDiscovery:
    def __init__(self, get, post) -> None:
        self._get = get
        self._post = post

    def search_subjects(self, keyword: str) -> list[DoubanSubject]:
        data = self._rexxar_search(keyword)
        subjects = self._parse_rexxar_subjects(data)
        if subjects:
            return subjects
        return self._parse_public_subjects(self._public_search(keyword))

    def fetch_vendors(self, douban_id: str) -> list[DoubanVendor]:
        data = self._rexxar_detail(douban_id)
        if not isinstance(data, dict):
            return []
        vendors: list[DoubanVendor] = []
        for vendor in data.get("vendors") or []:
            if not isinstance(vendor, dict):
                continue
            parsed = self._vendor_to_media(vendor)
            if parsed is not None:
                vendors.append(parsed)
        return vendors

    def _rexxar_detail(self, douban_id: str) -> dict | None:
        url = f"{_REXXAR_DETAIL_URL}/{quote(str(douban_id))}?for_mobile=1"
        try:
            response = self._get(url, headers=dict(_REXXAR_HEADERS), follow_redirects=True, timeout=10.0)
        except Exception:
            return None
        if getattr(response, "status_code", 200) != 200:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _vendor_to_media(self, vendor: dict) -> DoubanVendor | None:
        vendor_id = str(vendor.get("id") or "").strip()
        uri = str(vendor.get("uri") or "").strip()
        if not vendor_id or not uri:
            return None
        if vendor_id == "qq":
            cid = self._query_param(uri, "cid")
            return DoubanVendor(provider="tencent", media_id=cid) if cid else None
        if vendor_id == "iqiyi":
            tvid = self._query_param(uri, "tvid")
            return DoubanVendor(provider="iqiyi", media_id=tvid) if tvid else None
        if vendor_id == "youku":
            showid = self._query_param(uri, "showid")
            return DoubanVendor(provider="youku", media_id=showid) if showid else None
        if vendor_id == "bilibili":
            season_id = urlparse(uri).path.rstrip("/").split("/")[-1]
            season_id = re.sub(r"^md", "", season_id)
            return DoubanVendor(provider="bilibili", media_id=f"ss{season_id}") if season_id else None
        if vendor_id == "miguvideo":
            from urllib.parse import unquote

            match = re.search(r'"contentID":"([^"]+)"', unquote(uri))
            if match:
                ep_id = match.group(1)
                return DoubanVendor(
                    provider="migu",
                    media_id=f"https://v3-sc.miguvideo.com/program/v4/cont/content-info/{ep_id}/1",
                )
            return None
        return None

    def _query_param(self, uri: str, key: str) -> str:
        return (parse_qs(urlparse(uri).query).get(key) or [""])[0].strip()

    def _rexxar_search(self, keyword: str) -> dict | None:
        url = f"{_REXXAR_SEARCH_URL}?q={quote(keyword)}&start=0&count=20&type=movie"
        try:
            response = self._get(url, headers=dict(_REXXAR_HEADERS), follow_redirects=True, timeout=10.0)
        except Exception:
            return None
        if getattr(response, "status_code", 200) != 200:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _public_search(self, keyword: str) -> dict | None:
        try:
            response = self._post(
                _PUBLIC_SEARCH_URL,
                json={"q": keyword, "start": 0, "count": 20, "apikey": _PUBLIC_APIKEY},
                headers=dict(_PUBLIC_HEADERS),
                follow_redirects=True,
                timeout=10.0,
            )
        except Exception:
            return None
        if getattr(response, "status_code", 200) != 200:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _parse_rexxar_subjects(self, data: dict | None) -> list[DoubanSubject]:
        if not isinstance(data, dict):
            return []
        raw_items: list[dict] = []
        items = (((data.get("subjects") or {}).get("items")) or [])
        if isinstance(items, list):
            raw_items.extend(item for item in items if isinstance(item, dict))
        smart_box = data.get("smart_box") or []
        if isinstance(smart_box, list):
            raw_items.extend(item for item in smart_box if isinstance(item, dict))
        subjects: list[DoubanSubject] = []
        for item in raw_items:
            subject = self._rexxar_item_to_subject(item)
            if subject is not None:
                subjects.append(subject)
        return subjects

    def _rexxar_item_to_subject(self, item: dict) -> DoubanSubject | None:
        if item.get("layout") != "subject":
            return None
        target = item.get("target") or {}
        douban_id = str(item.get("target_id") or target.get("id") or "").strip()
        title = str(target.get("title") or "").strip()
        if not douban_id or not title:
            return None
        return DoubanSubject(
            douban_id=douban_id,
            title=title,
            year=str(target.get("year") or "").strip(),
            type_name=str(item.get("type_name") or "").strip(),
        )

    def _parse_public_subjects(self, data: dict | None) -> list[DoubanSubject]:
        if not isinstance(data, dict):
            return []
        subjects: list[DoubanSubject] = []
        for item in data.get("subjects") or []:
            if not isinstance(item, dict):
                continue
            douban_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not douban_id or not title:
                continue
            type_map = {"movie": "电影", "tv": "电视剧"}
            subjects.append(
                DoubanSubject(
                    douban_id=douban_id,
                    title=title,
                    year=str(item.get("year") or "").strip(),
                    type_name=type_map.get(str(item.get("subtype") or ""), str(item.get("subtype") or "")),
                )
            )
        return subjects


def vendor_to_page_url(vendor: DoubanVendor) -> str:
    """Build a platform page URL that the matching provider can expand/resolve.

    Tencent only needs the cover id, but TencentDanmakuProvider._extract_cover_id
    requires a trailing slash after the cover id, so we build /x/cover/{cid}/.
    Migu's media_id is already a full content-info URL and is passed through.
    """
    provider = vendor.provider
    media_id = vendor.media_id
    if not media_id:
        return ""
    if provider == "tencent":
        return f"https://v.qq.com/x/cover/{media_id}/"
    if provider == "iqiyi":
        return f"https://www.iqiyi.com/v_{media_id}.html"
    if provider == "youku":
        return f"https://v.youku.com/v_show/id_{media_id}.html"
    if provider == "bilibili":
        return f"https://www.bilibili.com/bangumi/play/{media_id}"
    if provider == "migu":
        return media_id
    return ""
