"""SubHD 字幕站（抓取，无需 token）。

站点没有公开 API，只能解析页面。HTML 结构随时可能变，所以：

- 选择器写多个回退分支，任一命中即可；
- 全部落空时抛 SubtitleProviderError，由 service 收敛成"该站失败"，
  不会影响其他站点的结果。

下载走 2026-08 改版后的多步校验链路（详情页 → prepare-download →
/down/ 中转页 → /api/sub/down → 直链），全程匿名但依赖 cookie，见 ``download``。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urljoin

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
    http_post,
    response_bytes,
    response_json,
    response_text,
)
from atv_player.subtitles.release_parser import parse_release_name

_DETAIL_HREF = re.compile(r"^/a/(\w+)")
_WHITESPACE = re.compile(r"\s+")


class SubHDSubtitleProvider:
    provider_id = "subhd"
    label = "SubHD"
    requires_token = False
    notice = ""

    _BASE_URL = "https://www.subhd.tv"
    _MAX_ITEMS = 30

    def __init__(
        self,
        get: Callable[..., Any],
        post: Callable[..., Any] = lambda *a, **k: None,
        base_url: str = "",
    ) -> None:
        self._get = get
        self._post = post
        self._base_url = (base_url or self._BASE_URL).rstrip("/")

    def available(self) -> bool:
        return True

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        keyword = (query.title or query.file_name).strip()
        if not keyword:
            return []
        url = f"{self._base_url}/search/{quote(keyword)}"
        response = http_get(self._get, url, site="SubHD")
        text = response_text(response)
        guard_blocked(text, "SubHD")
        return self._parse_search(text, query)

    def _parse_search(
        self, text: str, query: SubtitleQuery | None = None
    ) -> list[SubtitleSearchItem]:
        tree = etree.HTML(text)
        if tree is None:
            raise SubtitleProviderError("SubHD 返回的页面无法解析")
        # 每个结果卡片里同一个 sid 有多个锚：短中文标题 + 带 SxxEyy 的发布名。
        # 只取第一个锚会让所有条目坍缩成同一个标题，季集信息全丢，
        # 用户就总是下到排最前面的那一集——这里保留最长（信息最全）的锚文本
        candidates: dict[str, dict[str, str]] = {}
        for anchor in tree.xpath('//a[starts-with(@href, "/a/")]'):
            href = str(anchor.get("href") or "")
            matched = _DETAIL_HREF.match(href)
            if matched is None:
                continue
            subtitle_id = matched.group(1)
            name = self._text_of(anchor)
            if not name:
                continue
            current = candidates.get(subtitle_id)
            if current is None:
                candidates[subtitle_id] = {
                    "name": name,
                    "href": href,
                    "context": self._container_text(anchor),
                }
                continue
            if len(name) > len(current["name"]):
                # 中文标题有展示价值，发布名有匹配价值，两个都要
                if current["name"] not in name:
                    name = f"{current['name']} {name}"
                current["name"] = name
        items: list[SubtitleSearchItem] = []
        for subtitle_id, info in candidates.items():
            season, episode = self._season_episode(info["name"])
            # 能明确判定季集且与查询不符的直接丢弃；判定不出的（整季包）保留
            if query is not None and query.season is not None:
                if season is not None and season != query.season:
                    continue
                if query.episode is not None and episode is not None:
                    if episode != query.episode:
                        continue
            language = normalize_language(info["context"], info["name"])
            items.append(
                SubtitleSearchItem(
                    provider=self.provider_id,
                    provider_label=self.label,
                    subtitle_id=subtitle_id,
                    name=info["name"],
                    language=language,
                    language_label=language_label(language),
                    season=season,
                    episode=episode,
                    context={"detail_url": urljoin(self._base_url, info["href"])},
                )
            )
            if len(items) >= self._MAX_ITEMS:
                break
        return items

    @staticmethod
    def _season_episode(name: str) -> tuple[int | None, int | None]:
        parsed = parse_release_name(name)
        return parsed.season, parsed.episode

    @staticmethod
    def _text_of(node: Any) -> str:
        return _WHITESPACE.sub(" ", "".join(node.itertext())).strip()

    def _container_text(self, anchor: Any) -> str:
        # 语言标签通常在结果卡片里，取最近的容器文本作为归一依据
        for expression in (
            'ancestor::div[contains(@class, "box")][1]',
            "ancestor::div[2]",
            "..",
        ):
            found = anchor.xpath(expression)
            if found:
                return self._text_of(found[0])[:400]
        return ""

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        """匿名下载（2026-08 改版后的链路，对照站点 subhd.js）。

        /api/sub/prepare-download 会下发带 Path 的校验 cookie（down_* 只对
        /api/sub/down 生效），后续每一步都要带上，否则 /down/ 直接 403
        "下载页面已失效"。注入的 get/post 是无状态的，所以在这里自己攒 cookie。
        """
        subtitle_id = item.subtitle_id
        detail_url = item.context.get("detail_url") or (
            f"{self._base_url}/a/{subtitle_id}"
        )
        cookies: dict[str, str] = {}

        # 1) 访问详情页，像浏览器一样建立会话
        response = http_get(self._get, detail_url, site="SubHD")
        self._merge_cookies(cookies, response)

        # 2) 预备下载：校验会话并换 /down/ 入口
        response = http_post(
            self._post,
            f"{self._base_url}/api/sub/prepare-download",
            json_body={"sid": subtitle_id},
            headers={
                "Referer": detail_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=cookies,
            site="SubHD",
        )
        self._merge_cookies(cookies, response)
        payload = response_json(response, "SubHD")
        if payload.get("success") is not True:
            raise SubtitleProviderError(
                f"SubHD: {payload.get('msg') or '准备下载失败'}"
            )
        down_url = urljoin(
            self._base_url, str(payload.get("url") or f"/down/{subtitle_id}")
        )

        # 3) 打开下载中转页（刷新校验 cookie；cookie 缺失时这里 403）
        response = http_get(
            self._get,
            down_url,
            headers={"Referer": detail_url},
            cookies=cookies,
            site="SubHD",
        )
        self._merge_cookies(cookies, response)

        # 4) 真正的下载校验，返回直链
        response = http_post(
            self._post,
            f"{self._base_url}/api/sub/down",
            json_body={"sid": subtitle_id},
            headers={
                "Referer": down_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=cookies,
            site="SubHD",
        )
        self._merge_cookies(cookies, response)
        payload = response_json(response, "SubHD")
        if payload.get("success") is not True or payload.get("pass") is not True:
            raise SubtitleProviderError(
                f"SubHD: {payload.get('msg') or '下载校验未通过'}"
            )
        file_url = str(payload.get("url") or "").strip()
        if not file_url:
            raise SubtitleProviderError("SubHD 未返回字幕文件地址")

        # 5) 直链在 dl.subhd.me，无需 cookie（页面 JS 也是 credentials: omit）
        response = http_get(
            self._get,
            file_url,
            timeout=DOWNLOAD_TIMEOUT,
            site="SubHD",
        )
        return extract_subtitle(response_bytes(response), name_hint=item.name)

    @staticmethod
    def _merge_cookies(target: dict[str, str], response: Any) -> None:
        jar = getattr(response, "cookies", None)
        if not jar:
            return
        try:
            for key, value in dict(jar).items():
                target[str(key)] = str(value)
        except Exception:
            return
