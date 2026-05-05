from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

import httpx

from atv_player.controllers.browse_controller import _map_vod_item
from atv_player.controllers.douban_controller import _map_categories, _map_item
from atv_player.controllers.telegram_search_controller import _parse_playlist
from atv_player.models import DoubanCategory, HistoryRecord, OpenPlayerRequest, PlayItem, VodItem

_JAVA_MAP_HEADER_ENTRY_RE = re.compile(r"(?:^|,\s*)([A-Za-z0-9-]+)=(.*?)(?=,\s*[A-Za-z0-9-]+=|$)")
_BILIBILI_DANMAKU_URL_RE = re.compile(r"^https?://comment\.bilibili\.com/\d+\.xml(?:\?.*)?$", re.IGNORECASE)

logger = logging.getLogger(__name__)


def _parse_bilibili_headers(headers: object) -> dict[str, str]:
    if isinstance(headers, dict):
        return {str(key): str(value) for key, value in headers.items()}
    if not isinstance(headers, str):
        return {}
    text = headers.strip()
    if not text:
        return {}
    try:
        parsed_headers = json.loads(text)
    except json.JSONDecodeError:
        parsed_headers = None
    if isinstance(parsed_headers, dict):
        return {str(key): str(value) for key, value in parsed_headers.items()}
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()
    parsed: dict[str, str] = {}
    for match in _JAVA_MAP_HEADER_ENTRY_RE.finditer(text):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key:
            parsed[key] = value
    return parsed


class BilibiliController:
    _PAGE_SIZE = 30

    def __init__(
        self,
        api_client,
        playback_history_loader: Callable[[str], HistoryRecord | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        http_get: Callable[..., object] = httpx.get,
    ) -> None:
        self._api_client = api_client
        self._playback_history_loader = playback_history_loader
        self._playback_history_saver = playback_history_saver
        self._http_get = http_get

    def _is_bilibili_danmaku_url(self, value: object) -> bool:
        return isinstance(value, str) and _BILIBILI_DANMAKU_URL_RE.match(value.strip()) is not None

    def _build_danmaku_headers(self, headers: dict[str, str]) -> dict[str, str]:
        if not headers:
            return {}
        allowed = {"referer", "user-agent", "cookie"}
        return {key: value for key, value in headers.items() if key.lower() in allowed and value}

    def _load_bilibili_danmaku(self, item: PlayItem, payload: dict[str, object]) -> None:
        danmaku_url = str(payload.get("danmaku") or "").strip()
        if not self._is_bilibili_danmaku_url(danmaku_url):
            return
        headers = self._build_danmaku_headers(item.headers)
        try:
            response = self._http_get(
                danmaku_url,
                headers=headers,
                timeout=10.0,
                follow_redirects=True,
            )
        except Exception as exc:
            item.danmaku_error = str(exc)
            logger.warning("Bilibili danmaku fetch failed vod_id=%s url=%s error=%s", item.vod_id, danmaku_url, exc)
            return
        xml_text = str(getattr(response, "text", "") or "").strip()
        if not xml_text:
            return
        item.danmaku_xml = xml_text
        item.selected_danmaku_provider = "bilibili"
        item.selected_danmaku_url = danmaku_url
        item.selected_danmaku_title = (item.media_title or item.title).strip()
        item.danmaku_error = ""

    def load_categories(self) -> list[DoubanCategory]:
        payload = self._api_client.list_bilibili_categories()
        return _map_categories(payload)

    def _decorate_card_subtitle(self, item: VodItem) -> VodItem:
        subtitle_parts = [item.vod_year.strip(), item.vod_remarks.strip()]
        item.vod_remarks = " - ".join(part for part in subtitle_parts if part)
        return item

    def _map_bilibili_items(self, payload: dict) -> list[VodItem]:
        return [self._decorate_card_subtitle(_map_item(item)) for item in payload.get("list", [])]

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        payload = self._api_client.list_bilibili_items(category_id, page=page, filters=filters)
        items = self._map_bilibili_items(payload)
        total_raw = payload.get("total")
        if total_raw is not None:
            total = int(total_raw)
        else:
            pagecount = int(payload.get("pagecount") or 0)
            total = pagecount * self._PAGE_SIZE
        return items, total

    def search_items(self, keyword: str, page: int) -> tuple[list[VodItem], int]:
        payload = self._api_client.search_bilibili_items(keyword, page=page)
        items = self._map_bilibili_items(payload)
        total_raw = payload.get("total")
        if total_raw is not None:
            total = int(total_raw)
        else:
            pagecount = int(payload.get("pagecount") or 0)
            total = pagecount * self._PAGE_SIZE
        return items, total

    def load_folder_items(self, vod_id: str) -> tuple[list[VodItem], int]:
        payload = self._api_client.list_bilibili_items(vod_id, page=1)
        items = self._map_bilibili_items(payload)
        total_raw = payload.get("total")
        total = int(total_raw) if total_raw is not None else len(items)
        return items, total

    def resolve_playlist_item(self, item: PlayItem) -> VodItem | None:
        if not item.vod_id:
            return None
        try:
            payload = self._api_client.get_bilibili_detail(item.vod_id)
            detail = _map_vod_item(payload["list"][0])
            detail.detail_style = "bilibili"
            return detail
        except (KeyError, IndexError):
            return None

    def load_playback_item(self, item: PlayItem) -> None:
        if not item.vod_id:
            raise ValueError("缺少 B站 播放 ID")
        payload = self._api_client.get_bilibili_playback_source(item.vod_id)
        raw_url = payload.get("url")
        if isinstance(raw_url, list):
            candidates = [str(value or "").strip() for index, value in enumerate(raw_url) if index % 2 == 1]
            play_url = next((candidate for candidate in candidates if candidate), "")
        else:
            play_url = str(raw_url or "")
        if not play_url:
            raise ValueError(f"没有可用的播放地址: {item.title}")
        item.url = play_url
        item.headers = _parse_bilibili_headers(payload.get("header") or {})
        self._load_bilibili_danmaku(item, payload)

    def _route_name(self, routes: list[str], group_index: int) -> str:
        route = routes[group_index] if group_index < len(routes) else ""
        route = route.strip()
        return route or f"线路 {group_index + 1}"

    def _build_playlists(self, detail: VodItem) -> list[list[PlayItem]]:
        routes = [item.strip() for item in (detail.vod_play_from or "").split("$$$")]
        groups = (detail.vod_play_url or "").split("$$$")
        playlists: list[list[PlayItem]] = []
        for group_index, group in enumerate(groups):
            route = self._route_name(routes, group_index)
            playlist = _parse_playlist(group)
            for item_index, item in enumerate(playlist):
                item.index = item_index
                item.play_source = route
                item.media_title = detail.vod_name
            if len(playlist) == 1 and not playlist[0].vod_id:
                playlist[0].title = detail.vod_name or playlist[0].title
                playlist[0].vod_id = group.strip() or detail.vod_id
            if playlist:
                playlists.append(playlist)
        if not playlists and detail.vod_play_url:
            playlists = [[
                PlayItem(
                    title=detail.vod_name or detail.vod_play_url,
                    url="",
                    vod_id=detail.vod_play_url.strip() or detail.vod_id,
                    play_source=self._route_name(routes, 0),
                    media_title=detail.vod_name,
                )
            ]]
        return playlists

    def build_request(self, vod_id: str) -> OpenPlayerRequest:
        payload = self._api_client.get_bilibili_detail(vod_id)
        detail = _map_vod_item(payload["list"][0])
        detail.detail_style = "bilibili"
        playlists = self._build_playlists(detail)
        if not playlists and detail.items:
            playlists = [list(detail.items)]
        if not playlists:
            raise ValueError(f"没有可播放的项目: {detail.vod_name}")
        playlist_index = 0
        playlist = playlists[playlist_index]
        history_loader = None
        history_saver = None
        if self._playback_history_loader is not None:
            history_loader = lambda source_vod_id=detail.vod_id: self._playback_history_loader(source_vod_id)
        if self._playback_history_saver is not None:
            history_saver = lambda payload, source_vod_id=detail.vod_id: self._playback_history_saver(
                source_vod_id,
                payload,
            )
        return OpenPlayerRequest(
            vod=detail,
            playlist=playlist,
            clicked_index=0,
            playlists=playlists,
            playlist_index=playlist_index,
            source_kind="bilibili",
            source_mode="detail",
            source_vod_id=detail.vod_id,
            use_local_history=False,
            detail_resolver=self.resolve_playlist_item,
            playback_loader=self.load_playback_item,
            async_playback_loader=True,
            playback_history_loader=history_loader,
            playback_history_saver=history_saver,
        )
