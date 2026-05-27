from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from html import unescape
from threading import Lock
from urllib.parse import urlparse

import httpx

from atv_player.network_proxy import ProxyDecider, build_httpx_kwargs_for_url


class DoubanBlockedError(RuntimeError):
    pass


class DoubanRateLimitedError(DoubanBlockedError):
    pass


class LocalDoubanClient:
    _USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    _SEARCH_URL = "https://movie.douban.com/j/subject_suggest"
    _DETAIL_URL_TEMPLATE = "https://movie.douban.com/subject/{douban_id}/"
    _RATE_LIMIT_SECONDS = 10.0
    _OFFICIAL_LINK_HOSTS = {
        "v.qq.com": ("tencent", "腾讯视频"),
        "m.v.qq.com": ("tencent", "腾讯视频"),
        "v.youku.com": ("youku", "优酷"),
        "m.youku.com": ("youku", "优酷"),
        "www.iqiyi.com": ("iqiyi", "爱奇艺"),
        "m.iqiyi.com": ("iqiyi", "爱奇艺"),
        "www.bilibili.com": ("bilibili", "B站"),
        "www.mgtv.com": ("mgtv", "芒果TV"),
        "tv.sohu.com": ("sohu", "搜狐视频"),
    }
    _rate_limit_lock = Lock()
    _last_allowed_at: float | None = None

    def __init__(
        self,
        cookie: str = "",
        transport: httpx.BaseTransport | None = None,
        proxy_decider: ProxyDecider | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cookie = cookie.strip()
        self._monotonic = monotonic
        client_kwargs = dict(
            transport=transport,
            timeout=15.0,
            follow_redirects=True,
        )
        client_kwargs.update(
            build_httpx_kwargs_for_url(proxy_decider, self._SEARCH_URL)
        )
        self._client = client_factory(**client_kwargs)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Referer": "https://movie.douban.com/",
            "User-Agent": self._USER_AGENT,
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    @staticmethod
    def _ensure_not_blocked(text: str, url: str) -> None:
        if "有异常请求从你的 IP 发出" in text or "https://sec.douban.com/" in text:
            raise DoubanBlockedError(f"被禁止访问: {url}")

    def _ensure_rate_limit_available(self, url: str) -> None:
        now = self._monotonic()
        with self._rate_limit_lock:
            last_allowed_at = type(self)._last_allowed_at
            if (
                last_allowed_at is not None
                and now - last_allowed_at < self._RATE_LIMIT_SECONDS
            ):
                raise DoubanRateLimitedError(f"豆瓣官方请求过于频繁: {url}")
            type(self)._last_allowed_at = now

    def _get_text(self, url: str, params: dict[str, object] | None = None) -> str:
        self._ensure_rate_limit_available(url)
        response = self._client.get(url, params=params, headers=self._headers())
        response.raise_for_status()
        text = response.text
        self._ensure_not_blocked(text, url)
        return text

    def search(self, title: str, year: str = "") -> list[dict[str, object]]:
        text = self._get_text(self._SEARCH_URL, params={"q": title})
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        results: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            item_title = str(item.get("title") or item.get("name") or "").strip()
            item_year = str(item.get("year") or "").strip()
            if not item_id or not item_title:
                continue
            if year and item_year and item_year != str(year).strip():
                continue
            result = {
                "id": item_id,
                "title": item_title,
                "year": item_year,
            }
            cover = str(item.get("img") or item.get("cover") or "").strip()
            if cover:
                result["cover"] = cover
            results.append(result)
        return results

    @staticmethod
    def _extract_first(pattern: str, text: str) -> str:
        matched = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if matched is None:
            return ""
        return unescape(matched.group(1)).strip()

    @staticmethod
    def _strip_tags(text: str) -> str:
        return re.sub(r"<[^>]+>", "", unescape(text or "")).strip()

    @classmethod
    def _extract_people(cls, text: str, pattern: str) -> str:
        matched = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if matched is None:
            return ""
        group_text = next(
            (group for group in matched.groups() if group), matched.group(0)
        )
        names = re.findall(
            r"<a[^>]*>([^<]+)</a>",
            group_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not names:
            names = [cls._strip_tags(group_text)] if cls._strip_tags(group_text) else []
        normalized = [cls._strip_tags(name) for name in names if cls._strip_tags(name)]
        return ",".join(normalized)

    @classmethod
    def _extract_info_value(cls, text: str, label: str) -> str:
        pattern = rf"{re.escape(label)}\s*:?\s*(.+?)(?:<br\s*/?>|</div>|</span>)"
        value = cls._extract_first(pattern, text)
        return cls._strip_tags(value)

    @classmethod
    def _official_link_provider(cls, url: str) -> tuple[str, str]:
        host = (urlparse(str(url or "").strip()).hostname or "").lower().strip(".")
        if not host:
            return "", ""
        if host in cls._OFFICIAL_LINK_HOSTS:
            return cls._OFFICIAL_LINK_HOSTS[host]
        for domain, provider_info in cls._OFFICIAL_LINK_HOSTS.items():
            if host.endswith(f".{domain}"):
                return provider_info
        return "", ""

    @classmethod
    def _extract_official_links(cls, text: str) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for match in re.finditer(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            url = unescape(match.group(1)).strip()
            provider, default_label = cls._official_link_provider(url)
            if not provider:
                continue
            label = cls._strip_tags(match.group(2)) or default_label
            key = (provider, url)
            if key in seen:
                continue
            links.append({"provider": provider, "label": label, "url": url})
            seen.add(key)
        return links

    def get_detail(self, douban_id: int | str) -> dict[str, object] | None:
        normalized_id = str(douban_id).strip()
        text = self._get_text(self._DETAIL_URL_TEMPLATE.format(douban_id=normalized_id))
        name = self._extract_first(r'property="v:itemreviewed"[^>]*>([^<]+)<', text)
        if not name:
            name = self._extract_first(r"<title>\s*([^<(]+?)\s*\(", text)
        if not name:
            return None
        genres = re.findall(
            r'property="v:genre"[^>]*>([^<]+)<',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        summary = self._extract_first(r'property="v:summary"[^>]*>(.*?)</span>', text)
        detail = {
            "id": normalized_id,
            "name": name,
            "year": self._extract_first(r'class="year"[^>]*>\((\d{4})\)<', text),
            "cover": self._extract_first(
                r'<div[^>]+id="mainpic"[^>]*>.*?<img[^>]+src="([^"]+)"',
                text,
            ),
            "dbScore": self._extract_first(r'property="v:average"[^>]*>([^<]+)<', text),
            "directors": self._extract_people(
                text,
                r'rel="v:directedBy"[^>]*>([^<]+)<',
            ),
            "actors": self._extract_people(
                text,
                r'<span[^>]*class="actor"[^>]*>.*?'
                r'<span[^>]*class="attrs"[^>]*>(.*?)</span>',
            ),
            "genre": ",".join(
                self._strip_tags(item) for item in genres if self._strip_tags(item)
            ),
            "country": self._extract_info_value(text, "制片国家/地区"),
            "language": self._extract_info_value(text, "语言"),
            "description": self._strip_tags(summary),
            "official_links": self._extract_official_links(text),
        }
        return detail
