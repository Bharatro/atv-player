from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from html import unescape
from threading import Lock
from urllib.parse import parse_qs, urlparse

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
        "m.bilibili.com": ("bilibili", "哔哩哔哩"),
        "www.mgtv.com": ("mgtv", "芒果TV"),
        "tv.sohu.com": ("sohu", "搜狐视频"),
    }
    _OFFICIAL_LINK_SOURCE_IDS = {
        "1": ("tencent", "腾讯视频"),
        "3": ("youku", "优酷视频"),
        "8": ("bilibili", "哔哩哔哩"),
        "9": ("iqiyi", "爱奇艺"),
    }
    _OFFICIAL_LINK_SOURCE_KEYS = {
        "qq": ("tencent", "腾讯视频"),
        "tencent": ("tencent", "腾讯视频"),
        "bilibili": ("bilibili", "哔哩哔哩"),
        "youku": ("youku", "优酷视频"),
        "iqiyi": ("iqiyi", "爱奇艺"),
        "mgtv": ("mgtv", "芒果TV"),
        "sohu": ("sohu", "搜狐视频"),
    }
    _OFFICIAL_LINK_LABEL_KEYS = {
        "腾讯视频": ("tencent", "腾讯视频"),
        "腾讯": ("tencent", "腾讯视频"),
        "哔哩哔哩": ("bilibili", "哔哩哔哩"),
        "b站": ("bilibili", "哔哩哔哩"),
        "优酷视频": ("youku", "优酷视频"),
        "优酷": ("youku", "优酷视频"),
        "爱奇艺": ("iqiyi", "爱奇艺"),
        "芒果tv": ("mgtv", "芒果TV"),
        "芒果": ("mgtv", "芒果TV"),
        "搜狐视频": ("sohu", "搜狐视频"),
        "搜狐": ("sohu", "搜狐视频"),
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
        self._recent_search_detail_ids: set[str] = set()
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

    def _get_text(
        self,
        url: str,
        params: dict[str, object] | None = None,
        *,
        skip_rate_limit: bool = False,
    ) -> str:
        if not skip_rate_limit:
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
        self._recent_search_detail_ids.update(
            str(item.get("id") or "").strip()
            for item in results
            if str(item.get("id") or "").strip()
        )
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

    @staticmethod
    def _extract_attr(tag: str, name: str) -> str:
        matched = re.search(
            rf"""\b{re.escape(name)}\s*=\s*(["'])(.*?)\1""",
            tag,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if matched is None:
            return ""
        return unescape(matched.group(2)).strip()

    @classmethod
    def _official_link_provider_from_source(cls, *values: str) -> tuple[str, str]:
        for value in values:
            parsed = urlparse(str(value or "").strip())
            source = parse_qs(parsed.query).get("source", [""])[0].strip().lower()
            if source in cls._OFFICIAL_LINK_SOURCE_KEYS:
                return cls._OFFICIAL_LINK_SOURCE_KEYS[source]
            normalized = str(value or "").strip().lower()
            if normalized in cls._OFFICIAL_LINK_SOURCE_KEYS:
                return cls._OFFICIAL_LINK_SOURCE_KEYS[normalized]
        return "", ""

    @classmethod
    def _official_link_provider_from_label(cls, *values: str) -> tuple[str, str]:
        for value in values:
            normalized = re.sub(r"\s+", "", str(value or "").strip()).lower()
            if normalized in cls._OFFICIAL_LINK_LABEL_KEYS:
                return cls._OFFICIAL_LINK_LABEL_KEYS[normalized]
        return "", ""

    @classmethod
    def _append_official_link(cls, links: list[dict[str, str]], link: dict[str, str]) -> None:
        provider = str(link.get("provider") or "").strip()
        if not provider:
            return
        url = str(link.get("url") or "").strip()
        label = str(link.get("label") or "").strip()
        for existing in links:
            if existing.get("provider") != provider:
                continue
            if url and not existing.get("url"):
                existing["url"] = url
            if label and not existing.get("label"):
                existing["label"] = label
            return
        links.append({"provider": provider, "label": label, "url": url})

    @classmethod
    def _unwrap_douban_play_link(cls, url: str) -> str:
        candidate = unescape(str(url or "").strip())
        if not candidate:
            return ""
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower().strip(".")
        if host in {"douban.com", "www.douban.com"} and parsed.path.startswith("/link2/"):
            linked = parse_qs(parsed.query).get("url", [""])[0].strip()
            return unescape(linked)
        return candidate

    @classmethod
    def _extract_source_play_links(cls, text: str) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for source_match in re.finditer(r"sources\[(\d+)\]\s*=\s*\[", text, flags=re.IGNORECASE):
            source_id = source_match.group(1)
            end = text.find("];", source_match.end())
            if end < 0:
                continue
            block = text[source_match.end() : end]
            play_match = re.search(
                r"""\bplay_link\s*:\s*(["'])(.*?)\1""",
                block,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if play_match is None:
                continue
            url = cls._unwrap_douban_play_link(play_match.group(2))
            provider, label = cls._OFFICIAL_LINK_SOURCE_IDS.get(source_id, ("", ""))
            if not provider:
                provider, label = cls._official_link_provider(url)
            if provider:
                links.append({"provider": provider, "label": label, "url": url})
        return links

    @classmethod
    def _extract_official_links(cls, text: str) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for match in re.finditer(
            r"(<a\b[^>]*>)(.*?)</a>",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            tag = match.group(1)
            url = cls._extract_attr(tag, "href")
            label = cls._extract_attr(tag, "data-cn") or cls._strip_tags(match.group(2))
            provider, default_label = cls._official_link_provider(url)
            if not provider:
                provider, default_label = cls._official_link_provider_from_source(
                    cls._extract_attr(tag, "data-click-track"),
                    cls._extract_attr(tag, "data-impression-track"),
                )
            if not provider:
                provider, default_label = cls._official_link_provider_from_label(label)
            if not provider:
                continue
            if url.lower().startswith("javascript:"):
                url = ""
            label = label or default_label
            cls._append_official_link(links, {"provider": provider, "label": label, "url": url})
        for link in cls._extract_source_play_links(text):
            cls._append_official_link(links, link)
        return links

    def get_detail(self, douban_id: int | str) -> dict[str, object] | None:
        normalized_id = str(douban_id).strip()
        skip_rate_limit = normalized_id in self._recent_search_detail_ids
        self._recent_search_detail_ids.discard(normalized_id)
        text = self._get_text(
            self._DETAIL_URL_TEMPLATE.format(douban_id=normalized_id),
            skip_rate_limit=skip_rate_limit,
        )
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
        info_text = self._extract_first(r'<div[^>]+id="info"[^>]*>(.*?)</div>', text)
        if not info_text:
            info_text = text
        runtime_match = re.search(
            r'property="v:runtime"[^>]*>([^<]+)<', text, flags=re.IGNORECASE
        )
        runtime_value = self._strip_tags(runtime_match.group(1)) if runtime_match else ""
        first_air_date = self._extract_info_value(info_text, "首播")
        release_date = self._extract_info_value(info_text, "上映日期")
        episode_duration = self._extract_info_value(info_text, "单集片长")
        movie_duration = runtime_value or self._extract_info_value(info_text, "片长")
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
            "screenwriter": self._extract_people(
                info_text,
                r'<span[^>]*class="pl"[^>]*>编剧</span>\s*:?\s*.*?'
                r'<span[^>]*class="attrs"[^>]*>(.*?)</span>',
            ),
            "actors": self._extract_people(
                text,
                r'<span[^>]*class="actor"[^>]*>.*?'
                r'<span[^>]*class="attrs"[^>]*>(.*?)</span>',
            ),
            "genre": ",".join(
                self._strip_tags(item) for item in genres if self._strip_tags(item)
            ),
            "country": self._extract_info_value(info_text, "制片国家/地区"),
            "language": self._extract_info_value(info_text, "语言"),
            "first_air_date": first_air_date,
            "release_date": release_date,
            "episode_count": self._extract_info_value(info_text, "集数"),
            "duration": episode_duration or movie_duration,
            "aliases": self._extract_info_value(info_text, "又名"),
            "imdb_id": self._extract_info_value(info_text, "IMDb"),
            "description": self._strip_tags(summary),
            "official_links": self._extract_official_links(text),
        }
        return detail
