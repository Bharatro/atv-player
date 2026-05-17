from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any
from xml.sax.saxutils import escape

import httpx

from atv_player.danmaku.cache import load_cached_danmaku_xml, save_cached_danmaku_xml
from atv_player.danmaku.models import DanmakuSourceGroup, DanmakuSourceOption, DanmakuSourceSearchResult
from atv_player.models import PlayItem
from atv_player.network_proxy import ProxyDecider, build_httpx_kwargs_for_url

_DIRECT_PARSE_DANMAKU_API = "https://dmku.hls.one/"
_DIRECT_PARSE_PROVIDER = "direct_parse"
_DIRECT_PARSE_PROVIDER_LABEL = "全局解析"


def load_direct_parse_danmaku(
    url: str,
    get=httpx.get,
    proxy_decider: ProxyDecider | None = None,
) -> dict[str, Any]:
    response = get(
        _DIRECT_PARSE_DANMAKU_API,
        params={"ac": "dm", "url": url},
        timeout=10.0,
        follow_redirects=True,
        **build_httpx_kwargs_for_url(proxy_decider, _DIRECT_PARSE_DANMAKU_API),
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


class DirectParseDanmakuController:
    def __init__(self, load: Callable[[str], dict[str, Any]] = load_direct_parse_danmaku) -> None:
        self._load = load

    def _page_url(self, item: PlayItem) -> str:
        return (item.original_url or item.vod_id or item.url).strip()

    def _query_name(self, item: PlayItem) -> str:
        title = item.danmaku_search_title.strip() or item.media_title.strip() or item.title.strip()
        episode = item.danmaku_search_episode.strip() or item.title.strip()
        item.danmaku_search_title = title
        item.danmaku_search_episode = episode
        item.danmaku_search_query = " ".join(part for part in (title, episode) if part).strip()
        return item.danmaku_search_query

    def _apply_single_source(self, item: PlayItem, page_url: str) -> None:
        option = DanmakuSourceOption(
            provider=_DIRECT_PARSE_PROVIDER,
            name=item.title.strip() or "弹幕",
            url=page_url,
        )
        item.danmaku_candidates = [
            DanmakuSourceGroup(
                provider=_DIRECT_PARSE_PROVIDER,
                provider_label=_DIRECT_PARSE_PROVIDER_LABEL,
                options=[option],
            )
        ]
        item.selected_danmaku_provider = _DIRECT_PARSE_PROVIDER
        item.selected_danmaku_url = page_url
        item.selected_danmaku_title = option.name
        item.danmaku_error = ""

    def load_cached_danmaku_sources(
        self,
        item: PlayItem,
        playlist: list[PlayItem] | None = None,
        media_duration_seconds: int = 0,
    ) -> bool:
        del playlist, media_duration_seconds
        page_url = self._page_url(item)
        if not page_url:
            return False
        self._query_name(item)
        self._apply_single_source(item, page_url)
        return True

    def refresh_danmaku_sources(
        self,
        item: PlayItem,
        query_override: str | None = None,
        search_title_override: str | None = None,
        search_episode_override: str | None = None,
        playlist: list[PlayItem] | None = None,
        force_refresh: bool = False,
        media_duration_seconds: int = 0,
    ) -> None:
        del playlist, force_refresh, media_duration_seconds
        if search_title_override is not None:
            item.danmaku_search_title = search_title_override.strip()
        if search_episode_override is not None:
            item.danmaku_search_episode = search_episode_override.strip()
        if query_override is not None:
            item.danmaku_search_query = query_override.strip()
        self.load_cached_danmaku_sources(item)

    def switch_danmaku_source(self, item: PlayItem, page_url: str) -> str:
        self._apply_single_source(item, page_url)
        query_name = self._query_name(item)
        cached_xml = load_cached_danmaku_xml(query_name, page_url)
        if cached_xml:
            item.danmaku_xml = cached_xml
            return cached_xml
        payload = self._load(page_url)
        xml_text = self._payload_to_xml(payload)
        item.danmaku_xml = xml_text
        save_cached_danmaku_xml(query_name, page_url, xml_text)
        return xml_text

    def maybe_resolve(self, item: PlayItem) -> None:
        if item.danmaku_xml or item.danmaku_pending:
            return
        page_url = self._page_url(item)
        if not page_url:
            return
        self._apply_single_source(item, page_url)
        query_name = self._query_name(item)
        cached_xml = load_cached_danmaku_xml(query_name, page_url)
        if cached_xml:
            item.danmaku_xml = cached_xml
            return
        item.danmaku_pending = True

        def run() -> None:
            try:
                self.switch_danmaku_source(item, page_url)
            finally:
                item.danmaku_pending = False

        threading.Thread(target=run, daemon=True).start()

    def _payload_to_xml(self, payload: dict[str, Any]) -> str:
        lines = ['<?xml version="1.0" encoding="UTF-8"?><i>']
        for entry in payload.get("danmuku") or []:
            if not isinstance(entry, list) or len(entry) < 5:
                continue
            try:
                time_offset = max(0.0, float(entry[0]))
            except (TypeError, ValueError):
                continue
            mode = self._danmaku_mode(entry[1] if len(entry) > 1 else "")
            color = self._danmaku_color(entry[2] if len(entry) > 2 else "")
            content = str(entry[4] or "").strip()
            if not content:
                continue
            lines.append(
                f'<d p="{time_offset:g},{mode},25,{color},0,0,0,0">{escape(content)}</d>'
            )
        lines.append("</i>")
        return "".join(lines)

    def _danmaku_mode(self, value: object) -> int:
        normalized = str(value or "").strip().lower()
        if normalized == "top":
            return 5
        if normalized == "bottom":
            return 4
        return 1

    def _danmaku_color(self, value: object) -> int:
        text = str(value or "").strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        try:
            return int(text, 16)
        except ValueError:
            return 16777215
