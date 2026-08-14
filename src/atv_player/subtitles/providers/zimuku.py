"""字幕库 Zimuku（抓取，无需 token）。

注意：该站带有验证码防火墙，命中时会返回"网站访问认证"页面。这里通过
``guard_blocked`` 明确抛出 SubtitleBlockedError，让界面显示"触发验证码"，
而不是让用户以为是"没搜到字幕"。

站点域名与 HTML 结构历史上变动频繁，选择器写成多分支回退。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import etree

from atv_player.subtitles.archive import extract_subtitle
from atv_player.subtitles.errors import SubtitleProviderError
from atv_player.subtitles.languages import language_label, normalize_language
from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleQuery,
    SubtitleSearchItem,
)
from atv_player.subtitles.providers._common import (
    DOWNLOAD_TIMEOUT,
    guard_blocked,
    http_get,
    response_bytes,
    response_text,
)

_DETAIL_HREF = re.compile(r"/(?:detail|subs)/(\w+)\.html")
_WHITESPACE = re.compile(r"\s+")


class ZimukuSubtitleProvider:
    provider_id = "zimuku"
    label = "字幕库"
    requires_token = False
    notice = "该站启用云锁验证码，通常无法使用"

    _BASE_URL = "https://srtku.com"
    _MAX_ITEMS = 30

    def __init__(
        self,
        get: Callable[..., Any] = httpx.get,
        base_url: str = "",
    ) -> None:
        self._get = get
        self._base_url = (base_url or self._BASE_URL).rstrip("/")

    def available(self) -> bool:
        return True

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        keyword = (query.title or query.file_name).strip()
        if not keyword:
            return []
        response = http_get(
            self._get,
            f"{self._base_url}/search",
            params={"q": keyword},
            site="字幕库",
        )
        text = response_text(response)
        guard_blocked(text, "字幕库")
        return self._parse_search(text)

    def _parse_search(self, text: str) -> list[SubtitleSearchItem]:
        tree = etree.HTML(text)
        if tree is None:
            raise SubtitleProviderError("字幕库返回的页面无法解析")
        items: list[SubtitleSearchItem] = []
        seen: set[str] = set()
        for anchor in tree.xpath("//a[@href]"):
            href = str(anchor.get("href") or "")
            matched = _DETAIL_HREF.search(href)
            if matched is None:
                continue
            subtitle_id = matched.group(1)
            if subtitle_id in seen:
                continue
            name = self._text_of(anchor)
            if not name:
                continue
            seen.add(subtitle_id)
            context_text = self._container_text(anchor)
            language = normalize_language(context_text, name)
            items.append(
                SubtitleSearchItem(
                    provider=self.provider_id,
                    provider_label=self.label,
                    subtitle_id=subtitle_id,
                    name=name,
                    language=language,
                    language_label=language_label(language),
                    context={"detail_url": urljoin(f"{self._base_url}/", href)},
                )
            )
            if len(items) >= self._MAX_ITEMS:
                break
        return items

    @staticmethod
    def _text_of(node: Any) -> str:
        return _WHITESPACE.sub(" ", "".join(node.itertext())).strip()

    def _container_text(self, anchor: Any) -> str:
        for expression in (
            'ancestor::div[contains(@class, "item")][1]',
            "ancestor::tr[1]",
            "ancestor::div[2]",
            "..",
        ):
            found = anchor.xpath(expression)
            if found:
                return self._text_of(found[0])[:400]
        return ""

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        detail_url = item.context.get("detail_url") or (
            f"{self._base_url}/detail/{item.subtitle_id}.html"
        )
        download_page = self._resolve_download_page(detail_url)
        file_url = self._resolve_file_url(download_page, referer=detail_url)
        response = http_get(
            self._get,
            file_url,
            headers={"Referer": download_page},
            timeout=DOWNLOAD_TIMEOUT,
            site="字幕库",
        )
        return extract_subtitle(response_bytes(response), name_hint=item.name)

    def _resolve_download_page(self, detail_url: str) -> str:
        response = http_get(self._get, detail_url, site="字幕库")
        text = response_text(response)
        guard_blocked(text, "字幕库")
        tree = etree.HTML(text)
        if tree is not None:
            for href in tree.xpath('//a[contains(@href, "/dld/")]/@href'):
                return urljoin(f"{self._base_url}/", str(href))
        # 详情页与下载页 id 一致时可以直接推出地址
        matched = _DETAIL_HREF.search(detail_url)
        if matched is not None:
            return f"{self._base_url}/dld/{matched.group(1)}.html"
        raise SubtitleProviderError("字幕库未找到下载页地址")

    def _resolve_file_url(self, download_page: str, *, referer: str) -> str:
        response = http_get(
            self._get,
            download_page,
            headers={"Referer": referer},
            site="字幕库",
        )
        text = response_text(response)
        guard_blocked(text, "字幕库")
        tree = etree.HTML(text)
        if tree is None:
            raise SubtitleProviderError("字幕库下载页无法解析")
        for expression in (
            '//a[@id="down1"]/@href',
            '//a[contains(@href, "/download/")]/@href',
            '//a[contains(@rel, "nofollow") and contains(@href, "zip")]/@href',
        ):
            found = tree.xpath(expression)
            if found:
                return urljoin(f"{self._base_url}/", str(found[0]))
        raise SubtitleProviderError("字幕库未找到实际下载链接")
