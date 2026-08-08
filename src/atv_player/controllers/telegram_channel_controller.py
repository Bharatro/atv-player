from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from atv_player.controllers.browse_controller import _map_vod_item, build_drive_grouped_sources
from atv_player.controllers.douban_controller import _map_category, _map_item
from atv_player.controllers.pagination import page_count_from_payload
from atv_player.controllers.telegram_search_controller import _map_telegram_item
from atv_player.models import DoubanCategory, HistoryRecord, OpenPlayerRequest, PlayItem, VodItem
from atv_player.share_types import infer_share_type

logger = logging.getLogger(__name__)


def _looks_like_media_url(value: str) -> bool:
    candidate = value.strip().lower()
    return candidate.startswith(("http://", "https://", "rtmp://", "rtsp://")) or any(
        candidate.endswith(ext) or f"{ext}?" in candidate for ext in (".m3u8", ".mkv", ".mp4", ".flv")
    )


def _looks_like_backend_vod_id(value: str) -> bool:
    candidate = value.strip()
    return "$" in candidate and not candidate.startswith(("http://", "https://"))


def _parse_playlist(vod_play_url: str) -> list[PlayItem]:
    playlist: list[PlayItem] = []
    for chunk in (vod_play_url or "").split("#"):
        if not chunk:
            continue
        title, separator, value = chunk.partition("$")
        if not separator:
            clean_value = title.strip()
            if not _looks_like_media_url(clean_value):
                clean_value = ""
        else:
            clean_value = value.strip()
        if not clean_value:
            continue
        playlist.append(
            PlayItem(
                title=title.strip(),
                url=clean_value if _looks_like_media_url(clean_value) else "",
                index=len(playlist),
                vod_id="" if _looks_like_media_url(clean_value) else clean_value,
            )
        )
    return playlist


def build_detail_playlist(detail: VodItem) -> list[PlayItem]:
    if detail.items and len(detail.items) == 1 and detail.items[0].url and _looks_like_media_url(detail.vod_play_url):
        return list(detail.items)
    playlist = _parse_playlist(detail.vod_play_url)
    if not playlist and detail.items:
        playlist = list(detail.items)
    return playlist


class TelegramChannelController:
    _PAGE_SIZE = 30
    uses_page_count_for_pagination = True

    def __init__(
        self,
        api_client,
        playback_history_loader: Callable[[str], HistoryRecord | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        drive_resolver: Callable[..., dict] | None = None,
        drive_files_loader: Callable[..., list] | None = None,
    ) -> None:
        self._api_client = api_client
        self._playback_history_loader = playback_history_loader
        self._playback_history_saver = playback_history_saver
        self._drive_resolver = drive_resolver
        self._drive_files_loader = drive_files_loader
        # Dedup concurrent resolve calls (the open flow can fire build_request twice for
        # the same resource) so both callers share one backend resolve / temp-share mount.
        self._resolve_lock = threading.Lock()
        self._resolve_cache: dict[str, tuple[float, dict]] = {}
        self._resolve_inflight: dict[str, threading.Event] = {}

    def _resolve_drive_share(self, vod_id: str, title: str) -> dict:
        cache_ttl = 30.0
        with self._resolve_lock:
            cached = self._resolve_cache.get(vod_id)
            if cached and (time.time() - cached[0]) < cache_ttl:
                return cached[1]
            event = self._resolve_inflight.get(vod_id)
            if event is None:
                event = threading.Event()
                self._resolve_inflight[vod_id] = event
                fetch = True
            else:
                fetch = False
        if fetch:
            try:
                result = (self._drive_resolver(vod_id, title) or {}) if self._drive_resolver else {}
            except Exception:
                logger.warning("drive resolve failed vod_id=%s", vod_id, exc_info=True)
                result = {}
            with self._resolve_lock:
                self._resolve_cache[vod_id] = (time.time(), result)
                self._resolve_inflight.pop(vod_id, None)
                event.set()
            return result
        event.wait(timeout=30.0)
        with self._resolve_lock:
            cached = self._resolve_cache.get(vod_id)
        return cached[1] if cached else {}

    def load_categories(self) -> list[DoubanCategory]:
        payload = self._api_client.list_telegram_channel_categories()
        categories = [_map_category(item) for item in payload.get("class", [])]
        categories = [category for category in categories if category.type_id != "0"]
        return [DoubanCategory(type_id="0", type_name="推荐"), *categories]

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        payload = self._api_client.list_telegram_channel_items(category_id, page=page)
        items = [_map_item(item) for item in payload.get("list", [])]
        page_count = page_count_from_payload(payload, fallback_total=len(items), page_size=self._PAGE_SIZE)
        return items, page_count

    def search_items(self, keyword: str, page: int, category_id: str = "") -> tuple[list[VodItem], int]:
        payload = self._api_client.search_telegram_channel_items(keyword, page=page)
        items = [_map_telegram_item(item) for item in payload.get("list", [])]
        page_count = page_count_from_payload(payload, fallback_total=len(items), page_size=self._PAGE_SIZE)
        return items, page_count

    def resolve_playlist_item(self, item: PlayItem) -> VodItem | None:
        if not item.vod_id:
            return None
        try:
            payload = self._api_client.get_detail(item.vod_id)
            return _map_vod_item(payload["list"][0])
        except (KeyError, IndexError):
            return None

    def build_request(self, vod_id: str, title: str = "") -> OpenPlayerRequest:
        # Drive resources: use ONLY the new /api/drive resolve (per-directory, no legacy
        # dfs flatten). Falls back to legacy flat detail for non-drive or resolve failure.
        if self._drive_resolver is not None and (
            _looks_like_backend_vod_id(vod_id) or bool(infer_share_type(vod_id))
        ):
            request = self._build_drive_request(vod_id, title)
            if request is not None:
                return request
        if _looks_like_backend_vod_id(vod_id):
            payload = self._api_client.get_detail(vod_id)
        else:
            payload = self._api_client.get_telegram_channel_detail(vod_id)
        detail = _map_vod_item(payload["list"][0])
        playlist = build_detail_playlist(detail)
        if not playlist:
            raise ValueError(f"没有可播放的项目: {detail.vod_name}")
        media_title = str(detail.vod_name or "").strip()
        if media_title:
            for item in playlist:
                if not item.media_title:
                    item.media_title = media_title
        source_vod_id = str(detail.vod_id or vod_id or "").strip()
        history_loader, history_saver = self._build_history_callbacks(source_vod_id, str(vod_id or "").strip())
        return OpenPlayerRequest(
            vod=detail,
            playlist=playlist,
            clicked_index=0,
            source_kind="telegram_channel",
            source_mode="detail",
            source_vod_id=source_vod_id,
            detail_resolver=self.resolve_playlist_item,
            use_local_history=False,
            playback_history_loader=history_loader,
            playback_history_saver=history_saver,
        )

    def _build_history_callbacks(self, source_vod_id: str, legacy_vod_id: str):
        history_loader = None
        history_saver = None
        if self._playback_history_loader is not None:
            def history_loader(source_vod_id=source_vod_id, legacy_vod_id=legacy_vod_id):
                history = self._playback_history_loader(source_vod_id)
                if history is None and legacy_vod_id and legacy_vod_id != source_vod_id:
                    history = self._playback_history_loader(legacy_vod_id)
                return history
        if self._playback_history_saver is not None:
            history_saver = lambda payload, source_vod_id=source_vod_id: self._playback_history_saver(source_vod_id, payload)
        return history_loader, history_saver

    def _build_drive_request(self, vod_id: str, title: str) -> OpenPlayerRequest | None:
        result = self._resolve_drive_share(vod_id, title)
        resource_id = str(result.get("resourceId") or "")
        vod_name = str(result.get("vodName") or "").strip() or title or vod_id
        detail = VodItem(vod_id=vod_id, vod_name=vod_name)
        source_groups, playlists = build_drive_grouped_sources(
            detail,
            resource_id,
            result.get("directories") or [],
            result.get("files") or [],
            self._drive_files_loader,
        )
        if not source_groups or not any(playlists):
            logger.info("drive resolve yielded no playable items vod_id=%s", vod_id)
            return None
        source_vod_id = str(detail.vod_id or vod_id or "").strip()
        history_loader, history_saver = self._build_history_callbacks(source_vod_id, str(vod_id or "").strip())
        logger.info("DRIVE_GROUPED (channel) vod_id=%s groups=%s", vod_id, len(source_groups))
        return OpenPlayerRequest(
            vod=detail,
            playlist=playlists[0],
            clicked_index=0,
            playlists=playlists,
            source_groups=source_groups,
            source_kind="telegram_channel",
            source_mode="detail",
            source_vod_id=source_vod_id,
            detail_resolver=None,
            use_local_history=False,
            playback_history_loader=history_loader,
            playback_history_saver=history_saver,
            drive_resource_id=resource_id,
            drive_files_loader=self._drive_files_loader,
        )
