from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import shutil
import threading
import time
from collections.abc import Callable
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urljoin, urlparse

from atv_player.api import ApiError
from atv_player.karaoke import parse_raw_karaoke, render_karaoke_ass
from atv_player.controllers.player_controller import PlayerSession
from atv_player.danmaku.cache import (
    load_cached_danmaku_source_search_result,
    load_cached_danmaku_xml,
    save_cached_danmaku_source_search_result,
    save_cached_danmaku_xml,
)
from atv_player.danmaku.models import DanmakuSeriesPreference, DanmakuSourceGroup, DanmakuSourceOption
from atv_player.danmaku.service import build_danmaku_series_key
from atv_player.danmaku.utils import infer_playlist_episode_number, normalize_name
from atv_player.controllers.browse_controller import _map_vod_item
from atv_player.controllers.douban_controller import _map_item
from atv_player.controllers.telegram_search_controller import build_detail_playlist
from atv_player.models import (
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    ExternalSubtitleOption,
    OpenPlayerRequest,
    PlaybackSource,
    PlaybackSourceGroup,
    PlayItem,
    PlaybackDetailAction,
    PlaybackDetailFieldAction,
    PlaybackDetailField,
    PlaybackDetailValuePart,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)
from atv_player.paths import app_cache_dir
from atv_player.player.resume import resolve_resume_index


logger = logging.getLogger(__name__)
_GROUPED_ROUTE_RE = re.compile(r"^(?P<group>\S*?\D)(?P<number>\d+)$")
_MOVIE_LIKE_TITLE_MARKERS = ("剧场版",)
_SINGLE_VIDEO_GENERIC_TITLES = {"正片", "完整版", "全片"}


def _strip_trailing_title_year_suffix(value: str) -> str:
    title = str(value or "").strip()
    if not title:
        return ""
    stripped = re.sub(r"\s*[\(（\[【]\s*(?:19|20)\d{2}\s*[\)）\]】]\s*$", "", title)
    stripped = stripped.strip()
    return stripped or title


def _looks_like_offline_download_link(value: str) -> bool:
    candidate = value.strip().lower()
    return candidate.startswith("magnet:?") or candidate.startswith("ed2k://")


def _map_filter_option(payload: object) -> CategoryFilterOption | None:
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("n") or "").strip()
    value = str(payload.get("v") or "").strip()
    if not name:
        return None
    return CategoryFilterOption(name=name, value=value)


def _map_category_filters(payload: object) -> list[CategoryFilter]:
    if not isinstance(payload, list):
        return []
    groups: list[CategoryFilter] = []
    for raw_group in payload:
        if not isinstance(raw_group, dict):
            continue
        key = str(raw_group.get("key") or "").strip()
        name = str(raw_group.get("name") or "").strip()
        if not key or not name:
            continue
        options = [
            option
            for option in (_map_filter_option(raw_option) for raw_option in raw_group.get("value") or [])
            if option is not None
        ]
        if not options:
            continue
        groups.append(CategoryFilter(key=key, name=name, options=options))
    return groups


def _looks_like_media_url(value: str) -> bool:
    candidate = value.strip().lower()
    if candidate.endswith(".html"):
        return False
    if candidate.startswith(("http://", "https://", "rtmp://", "rtsp://")):
        return True
    return any(candidate.endswith(ext) or f"{ext}?" in candidate for ext in (".m3u8", ".mkv", ".mp4", ".flv"))


def _has_implicit_numeric_title(value: str) -> bool:
    return re.fullmatch(r"\s*0*\d{1,4}\s*", value or "") is not None


def _looks_like_calendar_episode_title(value: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    return (
        re.match(r"^(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:\D|$)", candidate) is not None
        or re.match(r"^(?:19|20)\d{2}[-/.年](?:0?[1-9]|1[0-2])[-/.月](?:0?[1-9]|[12]\d|3[01])(?:日|\D|$)", candidate)
        is not None
    )


def _is_short_bare_numeric_playlist(item: PlayItem, playlist: list[PlayItem] | None = None) -> bool:
    if item.danmaku_title_only:
        return True
    if not _has_implicit_numeric_title(item.title) or not playlist:
        return False
    if len(playlist) < 2 or len(playlist) > 4:
        return False
    return all(_has_implicit_numeric_title(candidate.title) for candidate in playlist)


def _looks_like_movie_title(item: PlayItem) -> bool:
    return any(
        marker in normalize_name(value)
        for value in (item.title, item.media_title)
        for marker in _MOVIE_LIKE_TITLE_MARKERS
        if value
    )


def _should_omit_default_episode_label(item: PlayItem, playlist: list[PlayItem] | None = None) -> bool:
    del playlist
    normalized_title = normalize_name(item.title)
    if normalized_title in _SINGLE_VIDEO_GENERIC_TITLES:
        return True
    if _looks_like_movie_title(item):
        return True
    return False


def _extract_episode_label(item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
    if _looks_like_calendar_episode_title(item.title):
        return item.title.strip()
    if _should_omit_default_episode_label(item, playlist):
        return ""
    episode_number = infer_playlist_episode_number(item, playlist)
    if episode_number is None:
        return ""
    if _is_short_bare_numeric_playlist(item, playlist):
        return ""
    if _has_implicit_numeric_title(item.title):
        return str(episode_number)
    return f"{episode_number}集"


def _mark_short_bare_numeric_playlist(playlist: list[PlayItem]) -> list[PlayItem]:
    if len(playlist) < 2 or len(playlist) > 4:
        return playlist
    if not all(_has_implicit_numeric_title(item.title) for item in playlist):
        return playlist
    for item in playlist:
        item.danmaku_title_only = True
    return playlist


def _build_danmaku_search_name(item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
    media_title = item.media_title.strip()
    if not media_title:
        return item.title.strip()
    episode_label = _extract_episode_label(item, playlist)
    return " ".join(part for part in (media_title, episode_label) if part).strip()


def _compose_danmaku_search_query(title: str, episode: str) -> str:
    return " ".join(part for part in (title.strip(), episode.strip()) if part).strip()


def _save_cached_danmaku_source_search_result_variants(
    name: str,
    reg_src: str,
    result,
) -> None:
    save_cached_danmaku_source_search_result(name, reg_src, result)
    if reg_src:
        save_cached_danmaku_source_search_result(name, "", result)


def _load_cached_danmaku_source_search_result_variants(name: str, reg_src: str):
    cached = load_cached_danmaku_source_search_result(name, reg_src)
    if cached is not None or not reg_src:
        return cached
    return load_cached_danmaku_source_search_result(name, "")


def _danmaku_cache_query_names(
    item: PlayItem,
    query_name: str,
    playlist: list[PlayItem] | None = None,
) -> list[str]:
    names: list[str] = []
    for candidate in (query_name, _build_danmaku_search_name(item, playlist)):
        normalized = str(candidate).strip()
        if normalized and normalized not in names:
            names.append(normalized)
    return names


def _should_prefetch_danmaku(item: PlayItem, playlist: list[PlayItem] | None = None) -> bool:
    return bool(_extract_episode_label(item, playlist))


def _count_danmaku_entries(xml_text: str) -> int:
    if not xml_text:
        return 0
    return len(re.findall(r"<d\b", xml_text))


def _normalize_headers(raw_headers) -> dict[str, str]:
    if not raw_headers:
        return {}
    if isinstance(raw_headers, Mapping):
        return {str(key): str(value) for key, value in raw_headers.items()}
    if isinstance(raw_headers, str):
        try:
            parsed = json.loads(raw_headers)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): str(value) for key, value in parsed.items()}
        return {}
    return {}


_SUPPORTED_DRIVE_DOMAINS = (
    "alipan.com",
    "aliyundrive.com",
    "mypikpak.com",
    "xunlei.com",
    "123pan.com",
    "123pan.cn",
    "123684.com",
    "123865.com",
    "123912.com",
    "123592.com",
    "quark.cn",
    "139.com",
    "uc.cn",
    "115.com",
    "115cdn.com",
    "anxia.com",
    "189.cn",
    "baidu.com",
)

_DRIVE_PROVIDER_LABELS = {
    "alipan.com": "阿里",
    "aliyundrive.com": "阿里",
    "mypikpak.com": "PikPak",
    "xunlei.com": "迅雷",
    "123pan.com": "123云盘",
    "123pan.cn": "123云盘",
    "123684.com": "123云盘",
    "123865.com": "123云盘",
    "123912.com": "123云盘",
    "123592.com": "123云盘",
    "quark.cn": "夸克",
    "139.com": "移动云盘",
    "uc.cn": "UC",
    "115.com": "115",
    "115cdn.com": "115",
    "anxia.com": "115",
    "189.cn": "天翼",
    "baidu.com": "百度",
}


def _looks_like_drive_share_link(value: str) -> bool:
    candidate = value.strip()
    url = candidate.lower()
    if not url.startswith(("http://", "https://")):
        return False
    if url.endswith((".m3u8", ".mkv", ".mp4", ".flv")):
        return False
    hostname = (urlparse(candidate).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _SUPPORTED_DRIVE_DOMAINS)


def _detect_drive_provider_label(value: str) -> str:
    candidate = value.strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return ""
    hostname = (urlparse(candidate).hostname or "").lower()
    for domain, label in _DRIVE_PROVIDER_LABELS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return label
    return ""


def _infer_external_subtitle_format(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".srt"):
        return "application/x-subrip"
    if path.endswith(".ass"):
        return "text/x-ass"
    if path.endswith(".ssa"):
        return "text/x-ssa"
    if path.endswith(".vtt"):
        return "text/vtt"
    return ""


def _subtitle_suffix_for_format(format_name: str) -> str:
    normalized = str(format_name or "").strip().lower()
    if normalized == "application/x-subrip":
        return ".srt"
    if normalized == "text/x-ass":
        return ".ass"
    if normalized == "text/x-ssa":
        return ".ssa"
    if normalized == "text/vtt":
        return ".vtt"
    return ""


def _map_spider_playback_qualities(
    payload: object,
    selected_url: str,
) -> tuple[list[VideoQualityOption], str]:
    if not isinstance(payload, list):
        return [], ""
    qualities: list[VideoQualityOption] = []
    selected_quality_id = ""
    for raw_quality in payload:
        if not isinstance(raw_quality, Mapping):
            continue
        quality_id = str(raw_quality.get("id") or "").strip()
        label = str(raw_quality.get("label") or "").strip()
        quality_url = str(raw_quality.get("url") or "").strip()
        if not quality_id or not label or not _looks_like_media_url(quality_url):
            continue
        qualities.append(VideoQualityOption(id=quality_id, label=label, url=quality_url))
        if not selected_quality_id and quality_url == selected_url:
            selected_quality_id = quality_id
    if not qualities:
        return [], ""
    return qualities, selected_quality_id or qualities[0].id


def _map_playback_detail_actions(payload: object) -> list[PlaybackDetailAction]:
    if not isinstance(payload, list):
        return []
    actions: list[PlaybackDetailAction] = []
    for raw_action in payload:
        if not isinstance(raw_action, Mapping):
            continue
        action_id = str(raw_action.get("id") or "").strip()
        label = str(raw_action.get("label") or "").strip()
        if not action_id or not label:
            continue
        action = PlaybackDetailAction(
            id=action_id,
            label=label,
            active=bool(raw_action.get("active")),
            enabled=bool(raw_action.get("enabled", True)),
            visible=bool(raw_action.get("visible", True)),
            tooltip=str(raw_action.get("tooltip") or "").strip(),
        )
        if action.visible:
            actions.append(action)
    return actions


def _map_playback_detail_fields(payload: object) -> list[PlaybackDetailField]:
    if not isinstance(payload, list):
        return []
    fields: list[PlaybackDetailField] = []
    for raw_field in payload:
        if not isinstance(raw_field, Mapping):
            continue
        label = str(raw_field.get("label") or "").strip()
        value_parts = _map_playback_detail_field_value_parts(raw_field.get("value"))
        if not label or not value_parts:
            continue
        fields.append(PlaybackDetailField(label=label, value_parts=value_parts))
    return fields


def _map_playback_detail_field_action(payload: object) -> PlaybackDetailFieldAction | None:
    if not isinstance(payload, Mapping):
        return None
    action_type = str(payload.get("type") or "").strip()
    value = str(payload.get("value") or "").strip()
    if action_type not in {"category", "detail", "search", "link"} or not value:
        return None
    return PlaybackDetailFieldAction(type=action_type, value=value)


def _map_playback_detail_field_value_parts(payload: object) -> list[PlaybackDetailValuePart]:
    if isinstance(payload, list):
        parts: list[PlaybackDetailValuePart] = []
        for raw_item in payload:
            if isinstance(raw_item, Mapping):
                label = str(raw_item.get("label") or "").strip()
                if not label:
                    continue
                parts.append(
                    PlaybackDetailValuePart(
                        label=label,
                        action=_map_playback_detail_field_action(raw_item.get("action")),
                    )
                )
                continue
            label = str(raw_item or "").strip()
            if label:
                parts.append(PlaybackDetailValuePart(label=label))
        return parts
    label = str(payload or "").strip()
    return [PlaybackDetailValuePart(label=label)] if label else []


def _merge_playback_detail_actions(
    collection_actions: list[PlaybackDetailAction],
    item_actions: list[PlaybackDetailAction],
) -> list[PlaybackDetailAction]:
    merged: list[PlaybackDetailAction] = list(collection_actions)
    seen_ids = {action.id for action in merged}
    for action in item_actions:
        if action.id in seen_ids:
            merged = [action if existing.id == action.id else existing for existing in merged]
            continue
        merged.append(action)
        seen_ids.add(action.id)
    return merged


def _move_spider_subtitle_to_cache(source_path: Path) -> Path:
    cache_dir = app_cache_dir() / "subtitles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        if source_path.resolve().is_relative_to(cache_dir.resolve()):
            return source_path
    except OSError:
        return source_path
    target_path = cache_dir / source_path.name
    if target_path.exists():
        stem = source_path.stem
        suffix = source_path.suffix
        index = 1
        while True:
            candidate = cache_dir / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                target_path = candidate
                break
            index += 1
    return Path(shutil.move(str(source_path), str(target_path)))


def _write_inline_spider_subtitle_to_cache(format_name: str, text: str) -> Path:
    cache_dir = app_cache_dir() / "subtitles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = _subtitle_suffix_for_format(format_name)
    digest = hashlib.sha256(f"{format_name}\n{text}".encode("utf-8")).hexdigest()
    target_path = cache_dir / f"inline_{digest}{suffix}"
    if not target_path.exists():
        target_path.write_text(text, encoding="utf-8")
    return target_path


def _write_inline_spider_karaoke_to_cache(text: str) -> Path:
    cache_dir = app_cache_dir() / "subtitles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    target_path = cache_dir / f"karaoke_{digest}.ass"
    if not target_path.exists():
        target_path.write_text(text, encoding="utf-8")
    return target_path


def _format_drive_route_label(route: str, provider: str) -> str:
    normalized_route = route.strip()
    if not provider or provider in normalized_route:
        return normalized_route
    return f"{normalized_route}({provider})"


def _split_grouped_route_label(route_label: str) -> tuple[str, str]:
    normalized = route_label.strip()
    if not normalized:
        return "", ""
    if any(char.isspace() for char in normalized):
        return normalized, normalized
    match = _GROUPED_ROUTE_RE.match(normalized)
    if match is None:
        return normalized, normalized
    group_label = match.group("group").strip()
    if not group_label:
        return normalized, normalized
    return group_label, normalized


class SpiderPluginController:
    def __init__(
        self,
        spider,
        plugin_name: str,
        search_enabled: bool,
        drive_detail_loader: Callable[[str], dict] | None = None,
        offline_download_detail_loader: Callable[[str], dict] | None = None,
        playback_history_loader: Callable[[str], object | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        playback_parser_service=None,
        preferred_parse_key_loader: Callable[[], str] | None = None,
        danmaku_service=None,
        danmaku_preference_store=None,
        base_url_loader: Callable[[], str] | None = None,
    ) -> None:
        self.uses_result_length_for_pagination = True
        self._spider = spider
        self._plugin_name = plugin_name
        self.supports_search = bool(search_enabled and callable(getattr(self._spider, "searchContent", None)))
        self._drive_detail_loader = drive_detail_loader
        self._offline_download_detail_loader = offline_download_detail_loader
        self._playback_history_loader = playback_history_loader
        self._playback_history_saver = playback_history_saver
        self._playback_parser_service = playback_parser_service
        self._preferred_parse_key_loader = preferred_parse_key_loader
        self._base_url_loader = base_url_loader
        self._danmaku_service = danmaku_service
        self._danmaku_preference_store = danmaku_preference_store
        self._danmaku_enabled = bool(getattr(self._spider, "danmaku", lambda: False)())
        self._danmaku_lock = threading.Lock()
        self._pending_danmaku_item_ids: set[int] = set()
        self._danmaku_log_handler: Callable[[str], None] | None = None
        self._home_loaded = False
        self._home_categories: list[DoubanCategory] = []
        self._home_items: list[VodItem] = []
        self._search_supports_category = self._detect_search_supports_category()

    def _map_items(self, payload: dict) -> list[VodItem]:
        return [_map_item(item) for item in payload.get("list", [])]

    def _detect_search_supports_category(self) -> bool:
        if not self.supports_search:
            return False
        try:
            params = inspect.signature(self._spider.searchContent).parameters
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug("Spider plugin search signature introspection failed plugin=%s error=%s", self._plugin_name, e)
            return True
        return "category" in params

    def _ensure_home_loaded(self) -> None:
        if self._home_loaded:
            return
        try:
            payload = self._spider.homeContent(False) or {}
        except Exception as exc:
            logger.exception("Spider plugin home load failed plugin=%s", self._plugin_name)
            raise ApiError(str(exc)) from exc
        raw_filters = payload.get("filters") or {}
        categories = [
            DoubanCategory(
                type_id=str(item.get("type_id") or ""),
                type_name=str(item.get("type_name") or ""),
                filters=_map_category_filters(raw_filters.get(str(item.get("type_id") or ""))),
            )
            for item in payload.get("class", [])
        ]
        items = self._map_items(payload)
        if items:
            categories = [DoubanCategory(type_id="home", type_name="推荐"), *categories]
        self._home_categories = categories
        self._home_items = items
        self._home_loaded = True

    def _normalize_spider_subtitle_url(self, value: object) -> str:
        raw_value = str(value or "")
        if not raw_value.strip():
            return ""
        format_name, separator, subtitle_text = raw_value.partition("\n")
        if separator:
            format_name = format_name.strip()
            suffix = _subtitle_suffix_for_format(format_name)
            if suffix and subtitle_text.strip():
                return str(_write_inline_spider_subtitle_to_cache(format_name, subtitle_text))
        raw = raw_value.strip()
        if raw.startswith(("http://", "https://")):
            return raw
        local_path = Path(raw)
        if local_path.is_absolute() and local_path.exists():
            return str(_move_spider_subtitle_to_cache(local_path))
        if not raw.startswith("/"):
            return ""
        base_url = "" if self._base_url_loader is None else str(self._base_url_loader() or "").strip()
        if not base_url:
            return ""
        return urljoin(f"{base_url.rstrip('/')}/", raw.lstrip("/"))

    def _map_spider_external_subtitles(self, payload: object) -> list[ExternalSubtitleOption]:
        url = self._normalize_spider_subtitle_url(payload)
        if not url:
            return []
        return [
            ExternalSubtitleOption(
                name="外挂字幕 [插件]",
                lang="",
                url=url,
                format=_infer_external_subtitle_format(url),
                source="spider",
            )
        ]

    def _map_spider_karaoke_subtitle(self, payload: object) -> list[ExternalSubtitleOption]:
        if not isinstance(payload, Mapping):
            return []
        format_name = str(payload.get("format") or "").strip()
        text = str(payload.get("text") or "")
        translation = str(payload.get("translation") or "")
        if not format_name or not text.strip():
            return []
        document = parse_raw_karaoke(format_name, text, translation=translation)
        if not document.lines:
            return []
        subtitle_path = _write_inline_spider_karaoke_to_cache(render_karaoke_ass(document))
        return [
            ExternalSubtitleOption(
                name="逐字歌词 [插件]",
                lang="",
                url=str(subtitle_path),
                format="text/x-ass",
                source="spider",
            )
        ]

    def load_categories(self) -> list[DoubanCategory]:
        self._ensure_home_loaded()
        return list(self._home_categories)

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        self._ensure_home_loaded()
        if category_id == "home":
            return list(self._home_items), len(self._home_items)
        try:
            payload = self._spider.categoryContent(category_id, page, False, dict(filters or {})) or {}
        except Exception as exc:
            logger.exception(
                "Spider plugin category load failed plugin=%s category_id=%s page=%s",
                self._plugin_name,
                category_id,
                page,
            )
            raise ApiError(str(exc)) from exc
        items = self._map_items(payload)
        total = int(payload.get("total") or 0)
        if total <= 0:
            total = len(items)
        return items, total

    def search_items(
        self,
        keyword: str,
        page: int,
        category_id: str = "",
    ) -> tuple[list[VodItem], int]:
        if not self.supports_search:
            raise ApiError("当前插件不支持搜索")
        category = "" if category_id == "home" else str(category_id or "")
        try:
            if self._search_supports_category:
                payload = self._spider.searchContent(keyword, False, page, category)
            else:
                payload = self._spider.searchContent(keyword, False, page)
            payload = payload or {}
        except Exception as exc:
            logger.exception(
                "Spider plugin search failed plugin=%s keyword=%s page=%s category_id=%s",
                self._plugin_name,
                keyword,
                page,
                category,
            )
            raise ApiError(str(exc)) from exc
        items = self._map_items(payload)
        total = int(payload.get("total") or len(items))
        return items, total

    def _route_name(self, routes: list[str], group_index: int) -> str:
        route = routes[group_index] if group_index < len(routes) else ""
        route = route.strip()
        return route or f"线路 {group_index + 1}"

    def _build_playlist(self, detail: VodItem) -> list[list[PlayItem]]:
        routes = [item.strip() for item in (detail.vod_play_from or "").split("$$$")]
        groups = (detail.vod_play_url or "").split("$$$")
        playlists: list[list[PlayItem]] = []
        for group_index, group in enumerate(groups):
            route = self._route_name(routes, group_index)
            route_label = route
            playlist: list[PlayItem] = []
            for raw_chunk in group.split("#"):
                chunk = raw_chunk.strip()
                if not chunk:
                    continue
                title, separator, value = chunk.partition("$")
                if not separator:
                    title = chunk
                    value = chunk
                clean_value = value.strip()
                is_drive_link = _looks_like_drive_share_link(clean_value)
                is_media_url = _looks_like_media_url(clean_value) and not is_drive_link
                if is_drive_link:
                    provider = _detect_drive_provider_label(clean_value)
                    if provider:
                        route_label = _format_drive_route_label(route, provider)
                playlist.append(
                    PlayItem(
                        title=title.strip() or clean_value or f"选集 {len(playlist) + 1}",
                        url=clean_value if is_media_url else "",
                        media_title=detail.vod_name,
                        path=detail.vod_id if is_drive_link else "",
                        vod_id="" if is_media_url else clean_value,
                        index=len(playlist),
                        play_source=route_label,
                    )
                )
            if playlist:
                playlists.append(_mark_short_bare_numeric_playlist(playlist))
        return playlists

    def _build_grouped_play_item(self, detail: VodItem, raw_media: Mapping[object, object]) -> PlayItem | None:
        display_name = str(raw_media.get("name") or "").strip()
        raw_url = str(raw_media.get("url") or "").strip()
        if not raw_url:
            return None
        title = display_name or raw_url
        is_drive_link = _looks_like_drive_share_link(raw_url)
        is_media_url = _looks_like_media_url(raw_url) and not is_drive_link
        return PlayItem(
            title=title,
            url=raw_url if is_media_url else "",
            media_title=detail.vod_name,
            path=detail.vod_id if is_drive_link else "",
            vod_id="" if is_media_url else raw_url,
            index=0,
            play_source=title,
        )

    def _build_grouped_sources_from_payload(
        self,
        detail: VodItem,
        payload: object,
    ) -> tuple[list[PlaybackSourceGroup], list[list[PlayItem]]]:
        if not isinstance(payload, list):
            return [], []
        source_groups: list[PlaybackSourceGroup] = []
        playlists: list[list[PlayItem]] = []
        for raw_group in payload:
            if not isinstance(raw_group, Mapping):
                continue
            group_name = str(raw_group.get("name") or "").strip()
            raw_media_list = raw_group.get("media")
            if not group_name or not isinstance(raw_media_list, list):
                continue
            sources: list[PlaybackSource] = []
            for raw_media in raw_media_list:
                if not isinstance(raw_media, Mapping):
                    continue
                item = self._build_grouped_play_item(detail, raw_media)
                if item is None:
                    continue
                playlist = [item]
                playlists.append(playlist)
                sources.append(PlaybackSource(label=item.title, playlist=playlist))
            if sources:
                source_groups.append(PlaybackSourceGroup(label=group_name, sources=sources))
        return source_groups, playlists

    def _build_source_groups_from_playlists(self, playlists: list[list[PlayItem]]) -> list[PlaybackSourceGroup]:
        source_groups: list[PlaybackSourceGroup] = []
        group_index_by_label: dict[str, int] = {}
        for playlist_index, playlist in enumerate(playlists):
            route_label = self._route_name([playlist[0].play_source if playlist else ""], 0)
            group_label, source_label = _split_grouped_route_label(route_label)
            if group_label not in group_index_by_label:
                group_index_by_label[group_label] = len(source_groups)
                source_groups.append(PlaybackSourceGroup(label=group_label, sources=[]))
            source_groups[group_index_by_label[group_label]].sources.append(
                PlaybackSource(label=source_label, playlist=playlist)
            )
        return source_groups

    def _build_drive_replacement_playlist(self, detail: VodItem, play_source: str, media_title: str = "") -> list[PlayItem]:
        resolved_media_title = media_title.strip() or detail.vod_name
        if detail.items:
            return _mark_short_bare_numeric_playlist([
                PlayItem(
                    title=item.title,
                    url=item.url,
                    media_title=resolved_media_title,
                    path=item.path,
                    index=index,
                    size=item.size,
                    vod_id=item.vod_id,
                    headers=dict(item.headers),
                    play_source=play_source,
                )
                for index, item in enumerate(detail.items)
                if item.url
            ])
        playlist = build_detail_playlist(detail)
        return _mark_short_bare_numeric_playlist([
            PlayItem(
                title=item.title,
                url=item.url,
                media_title=resolved_media_title,
                path=item.path,
                index=index,
                size=item.size,
                vod_id=item.vod_id,
                headers=dict(item.headers),
                play_source=play_source,
            )
            for index, item in enumerate(playlist)
            if item.url and not _looks_like_drive_share_link(item.url)
        ])

    def _resolve_folder_like_detail(self, item: PlayItem) -> VodItem | None:
        if not item.vod_id or self._drive_detail_loader is None:
            return None
        try:
            payload = self._drive_detail_loader(item.vod_id)
            return _map_vod_item(payload["list"][0])
        except (KeyError, IndexError):
            return None

    def _build_offline_download_replacement_playlist(
        self,
        detail: VodItem,
        play_source: str,
        media_title: str = "",
    ) -> list[PlayItem]:
        playlist = build_detail_playlist(detail)
        resolved_media_title = media_title.strip() or detail.vod_name
        return _mark_short_bare_numeric_playlist([
            PlayItem(
                title=item.title,
                url=item.url,
                media_title=resolved_media_title,
                path=item.path,
                index=index,
                size=item.size,
                vod_id=item.vod_id,
                headers=dict(item.headers),
                play_source=play_source,
            )
            for index, item in enumerate(playlist)
            if item.url or item.vod_id
        ])

    def _apply_single_offline_download_item(self, current_item: PlayItem, replacement: PlayItem) -> None:
        current_item.vod_id = replacement.vod_id
        current_item.path = replacement.path
        current_item.size = replacement.size
        current_item.headers = dict(replacement.headers)
        current_item.external_subtitles = list(replacement.external_subtitles)
        current_item.playback_qualities = list(replacement.playback_qualities)
        current_item.selected_playback_quality_id = replacement.selected_playback_quality_id
        if replacement.url:
            current_item.url = replacement.url

    def _replace_current_playlist_item(
        self,
        playlist: list[PlayItem],
        current_item: PlayItem,
        replacements: list[PlayItem],
    ) -> tuple[list[PlayItem], int]:
        if not playlist:
            updated = list(replacements)
            for index, item in enumerate(updated):
                item.index = index
            return updated, 0
        try:
            current_index = playlist.index(current_item)
        except ValueError:
            current_index = max(0, min(int(current_item.index or 0), len(playlist) - 1))
        updated = list(playlist[:current_index]) + list(replacements) + list(playlist[current_index + 1 :])
        for index, item in enumerate(updated):
            item.index = index
        return updated, current_index

    def _resolve_danmaku_sync(self, item: PlayItem, url: str, playlist: list[PlayItem] | None = None, *, is_prefetch: bool = False) -> None:
        if not self._danmaku_enabled or self._danmaku_service is None:
            return
        lookup = self._prepare_danmaku_lookup(item, url, playlist)
        if lookup is None:
            return
        preference, search_name, reg_src = lookup
        if self._apply_cached_danmaku(item, search_name, reg_src, preference):
            logger.info(
                "Spider plugin loaded cached danmaku plugin=%s source=%s",
                self._plugin_name,
                item.vod_id,
            )
            return
        if not is_prefetch:
            self._log_danmaku_event("弹幕搜索中", detail=search_name)
        try:
            default_url = self._populate_danmaku_candidates(item, search_name, reg_src, playlist=playlist)
        except Exception as exc:
            logger.warning(
                "Spider plugin danmaku search failed plugin=%s source=%s error=%s",
                self._plugin_name,
                item.vod_id,
                exc,
            )
            return
        if not is_prefetch:
            candidate_count = sum(len(group.options) for group in item.danmaku_candidates)
            self._log_danmaku_event("弹幕搜索成功", detail=f"找到 {candidate_count} 个候选")
        candidates = self._iter_danmaku_candidate_options(item.danmaku_candidates, default_url)
        if not candidates:
            return
        provider_label_by_key = {group.provider: group.provider_label for group in item.danmaku_candidates}
        for candidate in candidates:
            try:
                item.selected_danmaku_provider = candidate.provider
                item.selected_danmaku_url = candidate.url
                item.selected_danmaku_title = candidate.name
                platform_label = provider_label_by_key.get(candidate.provider) or candidate.provider
                candidate_label = (candidate.name or candidate.url or "").strip()
                download_detail = f"{platform_label} - {candidate_label}" if platform_label else candidate_label
                if not is_prefetch:
                    self._log_danmaku_event("弹幕下载中", detail=download_detail)
                cached_candidate_xml = load_cached_danmaku_xml(search_name, candidate.url)
                item.danmaku_xml = cached_candidate_xml or self._resolve_danmaku_xml(candidate.url, candidate)
                self._save_danmaku_xml_cache(
                    item,
                    search_name,
                    reg_src,
                    item.danmaku_xml,
                    playlist,
                    page_url=candidate.url,
                )
                self._save_danmaku_source_preference(item)
                if not is_prefetch and item.danmaku_xml:
                    danmaku_count = _count_danmaku_entries(item.danmaku_xml)
                    self._log_danmaku_event(
                        "弹幕下载成功",
                        detail=f"{danmaku_count} 条弹幕",
                    )
                logger.info(
                    "Spider plugin resolved danmaku plugin=%s source=%s candidate=%s",
                    self._plugin_name,
                    item.vod_id,
                    candidate.url,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Spider plugin danmaku candidate failed plugin=%s source=%s candidate=%s error=%s",
                    self._plugin_name,
                    item.vod_id,
                    candidate.url,
                    exc,
                )
                item.danmaku_error = str(exc)

    def _lookup_selected_danmaku_title(self, groups: list[DanmakuSourceGroup], page_url: str) -> str:
        for group in groups:
            for option in group.options:
                if option.url == page_url:
                    return option.name
        return ""

    def _resolve_danmaku_search_title(
        self,
        item: PlayItem,
        preference: DanmakuSeriesPreference | None = None,
    ) -> str:
        if item.danmaku_search_title.strip():
            return item.danmaku_search_title.strip()
        if preference is not None and preference.search_title.strip():
            return preference.search_title.strip()
        return (
            _strip_trailing_title_year_suffix(item.media_title)
            or _strip_trailing_title_year_suffix(item.title)
        )

    def _resolve_danmaku_search_episode(
        self,
        item: PlayItem,
        playlist: list[PlayItem] | None = None,
    ) -> str:
        return item.danmaku_search_episode.strip() or _extract_episode_label(item, playlist).strip()

    def _save_danmaku_search_title_preference(self, item: PlayItem) -> None:
        if self._danmaku_preference_store is None or not item.danmaku_series_key:
            return
        existing = self._danmaku_preference_store.load(item.danmaku_series_key)
        self._danmaku_preference_store.save(
            DanmakuSeriesPreference(
                series_key=item.danmaku_series_key,
                provider=existing.provider if existing is not None else "",
                page_url=existing.page_url if existing is not None else "",
                title=existing.title if existing is not None else "",
                search_title=item.danmaku_search_title,
                updated_at=int(time.time()),
            )
        )

    def _prepare_danmaku_lookup(
        self,
        item: PlayItem,
        url: str,
        playlist: list[PlayItem] | None = None,
    ) -> tuple[DanmakuSeriesPreference | None, str, str] | None:
        series_key = build_danmaku_series_key(item.media_title or item.title)
        preference = self._danmaku_preference_store.load(series_key) if self._danmaku_preference_store is not None else None
        search_title = self._resolve_danmaku_search_title(item, preference)
        search_episode = self._resolve_danmaku_search_episode(item, playlist)
        search_name = _compose_danmaku_search_query(search_title, search_episode)
        if not search_name:
            return None
        item.danmaku_series_key = series_key
        item.danmaku_search_title = search_title
        item.danmaku_search_episode = search_episode
        if not item.danmaku_search_query_overridden or not item.danmaku_search_query:
            item.danmaku_search_query = search_name
        reg_src = str(item.vod_id or url or "").strip()
        return preference, search_name, reg_src

    def _apply_cached_danmaku(
        self,
        item: PlayItem,
        query_name: str,
        reg_src: str,
        preference: DanmakuSeriesPreference | None,
    ) -> bool:
        cached_xml = load_cached_danmaku_xml(query_name, reg_src)
        if cached_xml:
            item.danmaku_xml = cached_xml
            return True
        if self._apply_cached_danmaku_preference_xml(item, query_name, preference):
            logger.info(
                "Spider plugin loaded cached danmaku via preference plugin=%s source=%s page_url=%s",
                self._plugin_name,
                item.vod_id,
                item.selected_danmaku_url,
            )
            return True
        return False

    def _save_danmaku_source_preference(self, item: PlayItem) -> None:
        if self._danmaku_preference_store is None or not item.danmaku_series_key:
            return
        existing = self._danmaku_preference_store.load(item.danmaku_series_key)
        self._danmaku_preference_store.save(
            DanmakuSeriesPreference(
                series_key=item.danmaku_series_key,
                provider=item.selected_danmaku_provider or (existing.provider if existing is not None else ""),
                page_url=item.selected_danmaku_url or (existing.page_url if existing is not None else ""),
                title=item.selected_danmaku_title or (existing.title if existing is not None else ""),
                search_title=item.danmaku_search_title or (existing.search_title if existing is not None else ""),
                updated_at=int(time.time()),
            )
        )

    def _apply_cached_danmaku_preference_xml(
        self,
        item: PlayItem,
        query_name: str,
        preference: DanmakuSeriesPreference | None,
    ) -> bool:
        if preference is None or not preference.page_url:
            return False
        cached_xml = load_cached_danmaku_xml(query_name, preference.page_url)
        if not cached_xml:
            return False
        item.danmaku_xml = cached_xml
        item.selected_danmaku_provider = preference.provider
        item.selected_danmaku_url = preference.page_url
        item.selected_danmaku_title = preference.title
        return True

    def _iter_danmaku_candidate_options(
        self,
        groups: list[DanmakuSourceGroup],
        default_url: str,
    ) -> list[DanmakuSourceOption]:
        ordered: list[DanmakuSourceOption] = []
        fallback: list[DanmakuSourceOption] = []
        for group in groups:
            for option in group.options:
                if option.url == default_url and default_url:
                    ordered.append(option)
                else:
                    fallback.append(option)
        ordered.extend(fallback)
        return ordered

    def _populate_danmaku_candidates(
        self,
        item: PlayItem,
        query_name: str,
        reg_src: str,
        force_refresh: bool = False,
        media_duration_seconds: int = 0,
        playlist: list[PlayItem] | None = None,
        provider_filter: str = "",
    ) -> str:
        series_key = build_danmaku_series_key(item.media_title or query_name)
        target_duration = media_duration_seconds if media_duration_seconds > 0 else int(item.duration_seconds or 0)
        item.danmaku_series_key = series_key
        item.danmaku_search_query = query_name
        item.danmaku_search_provider = provider_filter
        preference = self._danmaku_preference_store.load(series_key) if self._danmaku_preference_store is not None else None
        item.danmaku_search_title = self._resolve_danmaku_search_title(item, preference)
        item.danmaku_search_episode = self._resolve_danmaku_search_episode(item, playlist)
        if not item.danmaku_search_query_overridden or not item.danmaku_search_query:
            item.danmaku_search_query = _compose_danmaku_search_query(item.danmaku_search_title, item.danmaku_search_episode)
        else:
            item.danmaku_search_query = query_name
        query_name = item.danmaku_search_query
        if (
            not provider_filter
            and not force_refresh
            and self.load_cached_danmaku_sources(item, media_duration_seconds=target_duration, playlist=playlist)
        ):
            return item.selected_danmaku_url
        if hasattr(self._danmaku_service, "search_danmu_sources"):
            search_method = self._danmaku_service.search_danmu_sources
            search_kwargs = {
                "preferred_provider": preference.provider if preference is not None else "",
                "preferred_page_url": preference.page_url if preference is not None else "",
                "media_duration_seconds": target_duration,
            }
            if "provider_filter" in inspect.signature(search_method).parameters:
                search_kwargs["provider_filter"] = provider_filter
            result = search_method(query_name, reg_src, **search_kwargs)
        else:
            candidates = self._danmaku_service.search_danmu(query_name, reg_src, provider_filter=provider_filter)
            result = self._legacy_source_search_result(candidates)
        if not provider_filter:
            for cache_query_name in _danmaku_cache_query_names(item, query_name, playlist):
                _save_cached_danmaku_source_search_result_variants(cache_query_name, reg_src, result)
        self._apply_danmaku_source_search_result(item, result)
        if result.groups and item.danmaku_search_title:
            self._save_danmaku_search_title_preference(item)
        return result.default_option_url

    def _save_danmaku_xml_cache(
        self,
        item: PlayItem,
        query_name: str,
        reg_src: str,
        xml_text: str,
        playlist: list[PlayItem] | None = None,
        page_url: str = "",
    ) -> None:
        for cache_query_name in _danmaku_cache_query_names(item, query_name, playlist):
            save_cached_danmaku_xml(cache_query_name, reg_src, xml_text)
            if page_url:
                save_cached_danmaku_xml(cache_query_name, page_url, xml_text)

    def _resolve_danmaku_xml(self, page_url: str, option: DanmakuSourceOption | None = None) -> str:
        resolve_method = self._danmaku_service.resolve_danmu
        if option is not None and "option" in inspect.signature(resolve_method).parameters:
            return resolve_method(page_url, option=option)
        return resolve_method(page_url)

    def _apply_danmaku_source_search_result(self, item: PlayItem, result) -> None:
        item.danmaku_candidates = result.groups
        item.selected_danmaku_provider = result.default_provider
        item.selected_danmaku_url = result.default_option_url
        item.selected_danmaku_title = self._lookup_selected_danmaku_title(result.groups, result.default_option_url)
        item.danmaku_error = ""

    def load_cached_danmaku_sources(
        self,
        item: PlayItem,
        playlist: list[PlayItem] | None = None,
        media_duration_seconds: int = 0,
    ) -> bool:
        series_key = build_danmaku_series_key(item.media_title or item.title or item.danmaku_search_query)
        preference = self._danmaku_preference_store.load(series_key) if self._danmaku_preference_store is not None else None
        item.danmaku_search_title = self._resolve_danmaku_search_title(item, preference)
        item.danmaku_search_episode = self._resolve_danmaku_search_episode(item, playlist)
        query_name = (item.danmaku_search_query or _compose_danmaku_search_query(item.danmaku_search_title, item.danmaku_search_episode)).strip()
        if not query_name:
            return False
        item.danmaku_series_key = series_key
        item.danmaku_search_query = query_name
        reg_src = str(item.vod_id or item.url or "").strip()
        cached_result = _load_cached_danmaku_source_search_result_variants(query_name, reg_src)
        if cached_result is None:
            return False
        target_duration = media_duration_seconds if media_duration_seconds > 0 else int(item.duration_seconds or 0)
        if hasattr(self._danmaku_service, "rerank_danmaku_source_search_result"):
            cached_result = self._danmaku_service.rerank_danmaku_source_search_result(
                cached_result,
                reg_src=reg_src,
                preferred_provider=preference.provider if preference is not None else "",
                preferred_page_url=preference.page_url if preference is not None else "",
                media_duration_seconds=target_duration,
            )
        self._apply_danmaku_source_search_result(item, cached_result)
        return True

    def _legacy_source_search_result(self, candidates: list) -> object:
        groups: dict[str, list[DanmakuSourceOption]] = {}
        for item in candidates:
            groups.setdefault(item.provider, []).append(
                DanmakuSourceOption(
                    provider=item.provider,
                    name=item.name,
                    url=item.url,
                    ratio=getattr(item, "ratio", 0.0),
                    simi=getattr(item, "simi", 0.0),
                    duration_seconds=getattr(item, "duration_seconds", 0),
                    resolve_context=dict(getattr(item, "resolve_context", {})),
                )
            )
        source_groups = [
            DanmakuSourceGroup(provider=provider, provider_label=provider, options=options)
            for provider, options in groups.items()
        ]
        default_option = source_groups[0].options[0] if source_groups and source_groups[0].options else None
        from atv_player.danmaku.models import DanmakuSourceSearchResult

        return DanmakuSourceSearchResult(
            groups=source_groups,
            default_option_url=default_option.url if default_option is not None else "",
            default_provider=default_option.provider if default_option is not None else "",
        )

    def refresh_danmaku_sources(
        self,
        item: PlayItem,
        query_override: str | None = None,
        search_title_override: str | None = None,
        search_episode_override: str | None = None,
        playlist: list[PlayItem] | None = None,
        force_refresh: bool = False,
        media_duration_seconds: int = 0,
        provider_filter: str = "",
    ) -> None:
        if search_title_override is None and search_episode_override is None and query_override is not None:
            query_name = query_override.strip()
            if not query_name:
                return
            item.danmaku_search_query = query_name
            item.danmaku_search_query_overridden = True
        else:
            series_key = build_danmaku_series_key(item.media_title or item.title)
            preference = self._danmaku_preference_store.load(series_key) if self._danmaku_preference_store is not None else None
            item.danmaku_search_title = (
                search_title_override.strip()
                if search_title_override is not None
                else self._resolve_danmaku_search_title(item, preference)
            )
            item.danmaku_search_episode = (
                search_episode_override.strip()
                if search_episode_override is not None
                else self._resolve_danmaku_search_episode(item, playlist)
            )
            query_name = _compose_danmaku_search_query(item.danmaku_search_title, item.danmaku_search_episode)
            item.danmaku_search_query = query_name
            item.danmaku_search_query_overridden = (
                search_title_override is not None or search_episode_override is not None or query_override is not None
            )
        if not query_name:
            return
        reg_src = str(item.vod_id or item.url or "").strip()
        self._log_danmaku_event("弹幕搜索中", detail=query_name)
        self._populate_danmaku_candidates(
            item,
            query_name,
            reg_src,
            force_refresh=force_refresh,
            media_duration_seconds=media_duration_seconds,
            playlist=playlist,
            provider_filter=provider_filter,
        )
        candidate_count = sum(len(group.options) for group in item.danmaku_candidates)
        self._log_danmaku_event("弹幕搜索成功", detail=f"找到 {candidate_count} 个候选")

    def switch_danmaku_source(self, item: PlayItem, page_url: str) -> str:
        selected_option = None
        selected_provider_label = ""
        for group in item.danmaku_candidates:
            for option in group.options:
                if option.url == page_url:
                    selected_option = option
                    selected_provider_label = group.provider_label
                    break
            if selected_option is not None:
                break
        option_label = (selected_option.name if selected_option is not None else "").strip()
        download_detail = option_label
        if selected_provider_label and option_label:
            download_detail = f"{selected_provider_label} - {option_label}"
        elif selected_provider_label:
            download_detail = selected_provider_label
        self._log_danmaku_event("弹幕下载中", detail=download_detail)
        query_name = (item.danmaku_search_query or _build_danmaku_search_name(item)).strip()
        cached_xml = load_cached_danmaku_xml(query_name, page_url)
        xml_text = cached_xml or self._resolve_danmaku_xml(page_url, selected_option)
        item.danmaku_xml = xml_text
        item.selected_danmaku_url = page_url
        item.selected_danmaku_title = self._lookup_selected_danmaku_title(item.danmaku_candidates, page_url)
        for group in item.danmaku_candidates:
            for option in group.options:
                if option.url == page_url:
                    item.selected_danmaku_provider = option.provider
                    break
        query_name = (item.danmaku_search_query or _build_danmaku_search_name(item)).strip()
        reg_src = str(item.vod_id or item.url or "").strip()
        self._save_danmaku_xml_cache(item, query_name, reg_src, xml_text, page_url=page_url)
        self._save_danmaku_source_preference(item)
        danmaku_count = _count_danmaku_entries(xml_text)
        self._log_danmaku_event("弹幕下载成功", detail=f"{danmaku_count} 条弹幕")
        return xml_text

    def prefetch_next_episode_danmaku(
        self,
        item: PlayItem,
        playlist: list[PlayItem],
    ) -> None:
        if not _should_prefetch_danmaku(item, playlist):
            return
        url = (item.url or item.vod_id or "").strip()
        if not url:
            return
        if item.danmaku_xml or item.danmaku_pending:
            return
        if self._danmaku_enabled and self._danmaku_service is not None:
            lookup = self._prepare_danmaku_lookup(item, url, playlist)
            if lookup is not None:
                preference, search_name, reg_src = lookup
                if self._apply_cached_danmaku(item, search_name, reg_src, preference):
                    return
        prefetch_label = _build_danmaku_search_name(item, playlist) or (item.media_title or item.title)
        self._log_danmaku_event("弹幕预下载中", detail=prefetch_label)
        self._maybe_resolve_danmaku(item, url, playlist, is_prefetch=True)

    def set_danmaku_log_handler(self, handler: Callable[[str], None] | None) -> None:
        self._danmaku_log_handler = handler

    def _log_danmaku_event(self, event: str, item: PlayItem | None = None, detail: str = "") -> None:
        handler = self._danmaku_log_handler
        if handler is None:
            return
        label = ""
        if item is not None:
            label = (item.title or item.media_title or "").strip()
        parts = [event]
        if label:
            parts.append(label)
        if detail:
            parts.append(detail)
        message = ": ".join(parts) if len(parts) > 1 else parts[0]
        try:
            handler(message)
        except Exception:
            logger.exception("Danmaku log handler failed event=%s", event)

    def _maybe_resolve_danmaku(self, item: PlayItem, url: str, playlist: list[PlayItem] | None = None, *, is_prefetch: bool = False) -> None:
        if not self._danmaku_enabled or self._danmaku_service is None:
            return
        if item.danmaku_xml or item.danmaku_pending:
            return
        item_id = id(item)
        with self._danmaku_lock:
            if item_id in self._pending_danmaku_item_ids:
                return
            self._pending_danmaku_item_ids.add(item_id)
        item.danmaku_pending = True

        def run() -> None:
            try:
                self._resolve_danmaku_sync(item, url, playlist, is_prefetch=is_prefetch)
                if is_prefetch and item.danmaku_xml:
                    success_label = (item.selected_danmaku_title or _build_danmaku_search_name(item, playlist) or item.media_title or item.title).strip()
                    danmaku_count = _count_danmaku_entries(item.danmaku_xml)
                    self._log_danmaku_event(
                        "弹幕预下载成功",
                        detail=f"{success_label} ({danmaku_count} 条弹幕)",
                    )
            finally:
                item.danmaku_pending = False
                with self._danmaku_lock:
                    self._pending_danmaku_item_ids.discard(item_id)

        threading.Thread(target=run, daemon=True).start()

    def _resolve_replacement_start_index(self, vod_id: str, replacement: list[PlayItem]) -> int:
        if self._playback_history_loader is None or not replacement:
            return 0
        history = self._playback_history_loader(vod_id)
        return resolve_resume_index(history, replacement, 0)

    def _run_detail_action(
        self,
        vod: VodItem,
        playlists: list[list[PlayItem]],
        playlist_index: int,
        item: PlayItem,
        action_id: str,
    ) -> list[PlaybackDetailAction]:
        runner = getattr(self._spider, "runPlayerAction", None)
        if not callable(runner):
            raise ValueError(f"详情动作未注册[{action_id}]")
        context = {
            "action_id": action_id,
            "vod": vod,
            "play_item": item,
            "playlist": playlists[playlist_index] if 0 <= playlist_index < len(playlists) else [],
            "playlist_index": playlist_index,
            "play_index": item.index,
            "log": lambda message: logger.info(
                "Spider detail action plugin=%s action=%s %s",
                self._plugin_name,
                action_id,
                message,
            ),
        }
        payload = runner(action_id, context)
        refreshed_actions: list[PlaybackDetailAction]
        if isinstance(payload, Mapping):
            refreshed_actions = _map_playback_detail_actions(payload.get("actions"))
        else:
            refreshed_actions = _map_playback_detail_actions(payload)
        return _merge_playback_detail_actions(item.detail_actions, refreshed_actions)

    def _resolve_play_item(self, session: PlayerSession, item: PlayItem) -> PlaybackLoadResult | None:
        if item.url:
            session.video_cover_override = item.video_cover_override
            if not item.danmaku_xml:
                self._maybe_resolve_danmaku(item, item.url)
            return
        item.external_subtitles = []
        item.playback_qualities = []
        item.selected_playback_quality_id = ""
        if not item.vod_id:
            return
        if _looks_like_offline_download_link(item.vod_id):
            if self._offline_download_detail_loader is None:
                raise ValueError("当前插件未配置磁力链接解析")
            try:
                payload = self._offline_download_detail_loader(item.vod_id)
                detail = _map_vod_item(payload["list"][0])
            except (KeyError, IndexError) as exc:
                logger.exception(
                    "Spider plugin offline download detail failed plugin=%s source=%s",
                    self._plugin_name,
                    item.vod_id,
                )
                raise ValueError(f"没有可播放的项目: {item.title or item.vod_id}") from exc
            replacement = self._build_offline_download_replacement_playlist(
                detail,
                item.play_source,
                media_title=item.media_title,
            )
            if not replacement:
                raise ValueError(f"没有可播放的项目: {detail.vod_name or item.title}")
            session.detail_resolver = self._resolve_folder_like_detail
            session.resolved_vod_by_id = {}
            merged_playlist, replacement_start_index = self._replace_current_playlist_item(
                session.playlist,
                item,
                replacement,
            )
            logger.info(
                "Spider plugin resolved offline download playlist plugin=%s source=%s items=%s",
                self._plugin_name,
                item.vod_id,
                len(replacement),
            )
            return PlaybackLoadResult(
                replacement_playlist=merged_playlist,
                replacement_start_index=replacement_start_index,
            )
        if _looks_like_drive_share_link(item.vod_id):
            if self._drive_detail_loader is None:
                raise ValueError("当前插件未配置网盘解析")
            try:
                payload = self._drive_detail_loader(item.vod_id)
                detail = _map_vod_item(payload["list"][0])
            except (KeyError, IndexError) as exc:
                logger.exception(
                    "Spider plugin drive detail failed plugin=%s source=%s",
                    self._plugin_name,
                    item.vod_id,
                )
                raise ValueError(f"没有可播放的项目: {item.title or item.vod_id}") from exc
            replacement = self._build_drive_replacement_playlist(detail, item.play_source, media_title=item.media_title)
            if not replacement:
                raise ValueError(f"没有可播放的项目: {detail.vod_name or item.title}")
            replacement_start_index = self._resolve_replacement_start_index(item.path or detail.vod_id, replacement)
            replacement_item = replacement[replacement_start_index]
            if _should_prefetch_danmaku(replacement_item, replacement):
                self._maybe_resolve_danmaku(replacement_item, item.vod_id, replacement)
            logger.info(
                "Spider plugin resolved drive playlist plugin=%s source=%s items=%s",
                self._plugin_name,
                item.vod_id,
                len(replacement),
            )
            return PlaybackLoadResult(
                replacement_playlist=replacement,
                replacement_start_index=replacement_start_index,
            )
        try:
            payload = self._spider.playerContent(item.play_source, item.vod_id, []) or {}
        except Exception as exc:
            logger.exception(
                "Spider plugin playback resolve failed plugin=%s source=%s",
                self._plugin_name,
                item.vod_id,
            )
            raise ValueError(str(exc)) from exc
        cover_source = str(payload.get("cover") or "").strip()
        parse_required = int(payload.get("parse") or 0) == 1
        item.parse_required = parse_required
        url = str(payload.get("url") or "").strip()
        if _looks_like_offline_download_link(url):
            if self._offline_download_detail_loader is None:
                raise ValueError("当前插件未配置磁力链接解析")
            try:
                payload = self._offline_download_detail_loader(url)
                detail = _map_vod_item(payload["list"][0])
            except (KeyError, IndexError) as exc:
                logger.exception(
                    "Spider plugin offline download detail failed plugin=%s source=%s",
                    self._plugin_name,
                    url,
                )
                raise ValueError(f"没有可播放的项目: {item.title or item.vod_id}") from exc
            replacement = self._build_offline_download_replacement_playlist(
                detail,
                item.play_source,
                media_title=item.media_title,
            )
            if not replacement:
                raise ValueError(f"没有可播放的项目: {detail.vod_name or item.title}")
            session.detail_resolver = self._resolve_folder_like_detail
            session.resolved_vod_by_id = {}
            merged_playlist, replacement_start_index = self._replace_current_playlist_item(
                session.playlist,
                item,
                replacement,
            )
            logger.info(
                "Spider plugin resolved offline download playlist from playerContent plugin=%s source=%s items=%s",
                self._plugin_name,
                url,
                len(replacement),
            )
            if cover_source:
                replacement_item = merged_playlist[replacement_start_index]
                replacement_item.video_cover_override = cover_source
                session.video_cover_override = cover_source
            return PlaybackLoadResult(
                replacement_playlist=merged_playlist,
                replacement_start_index=replacement_start_index,
            )
        if _looks_like_drive_share_link(url):
            if self._drive_detail_loader is None:
                raise ValueError("当前插件未配置网盘解析")
            try:
                payload = self._drive_detail_loader(url)
                detail = _map_vod_item(payload["list"][0])
            except (KeyError, IndexError) as exc:
                logger.exception(
                    "Spider plugin drive detail failed plugin=%s source=%s",
                    self._plugin_name,
                    item.vod_id,
                )
                raise ValueError(f"没有可播放的项目: {item.title or item.vod_id}") from exc
            replacement = self._build_drive_replacement_playlist(detail, item.play_source, media_title=item.media_title)
            if not replacement:
                raise ValueError(f"没有可播放的项目: {detail.vod_name or item.title}")
            replacement_start_index = self._resolve_replacement_start_index(item.path or detail.vod_id, replacement)
            replacement_item = replacement[replacement_start_index]
            if _should_prefetch_danmaku(replacement_item, replacement):
                self._maybe_resolve_danmaku(replacement_item, url, replacement)
            logger.info(
                "Spider plugin resolved drive playlist plugin=%s source=%s items=%s",
                self._plugin_name,
                item.vod_id,
                len(replacement),
            )
            if cover_source:
                item.video_cover_override = cover_source
                replacement_item.video_cover_override = cover_source
            session.video_cover_override = replacement_item.video_cover_override or item.video_cover_override
            return PlaybackLoadResult(
                replacement_playlist=replacement,
                replacement_start_index=replacement_start_index,
            )
        if parse_required:
            if self._playback_parser_service is None:
                raise ValueError("当前插件未配置内置解析")
            result = self._playback_parser_service.resolve(
                item.play_source,
                url,
                preferred_key="" if self._preferred_parse_key_loader is None else self._preferred_parse_key_loader(),
            )
            item.url = result.url
            item.headers = dict(result.headers)
            if cover_source:
                item.video_cover_override = cover_source
            session.video_cover_override = item.video_cover_override
            self._maybe_resolve_danmaku(item, url)
            logger.info(
                "Spider plugin resolved parse playback plugin=%s source=%s parser=%s",
                self._plugin_name,
                item.vod_id,
                result.parser_key,
            )
            return None
        if not _looks_like_media_url(url):
            raise ValueError("插件未返回可播放地址")
        item.url = url
        item.headers = _normalize_headers(payload.get("header"))
        item.detail_fields = _map_playback_detail_fields(payload.get("ext"))
        item.detail_actions = _merge_playback_detail_actions(
            item.detail_actions,
            _map_playback_detail_actions(payload.get("actions")),
        )
        item.playback_qualities, item.selected_playback_quality_id = _map_spider_playback_qualities(
            payload.get("qualities"),
            url,
        )
        item.external_subtitles = self._map_spider_karaoke_subtitle(payload.get("lyric"))
        if not item.external_subtitles:
            item.external_subtitles = self._map_spider_external_subtitles(payload.get("subt"))
        if cover_source:
            item.video_cover_override = cover_source
        session.video_cover_override = item.video_cover_override
        self._maybe_resolve_danmaku(item, url)
        logger.info(
            "Spider plugin resolved playback url plugin=%s source=%s play_source=%s",
                self._plugin_name,
                item.vod_id,
            item.play_source,
        )
        return None

    def build_request(self, vod_id: str) -> OpenPlayerRequest:
        try:
            payload = self._spider.detailContent([vod_id]) or {}
        except Exception as exc:
            logger.exception("Spider plugin detail load failed plugin=%s vod_id=%s", self._plugin_name, vod_id)
            raise ValueError(str(exc)) from exc
        try:
            raw_detail = payload["list"][0]
            detail = _map_vod_item(raw_detail)
            detail.detail_fields = _map_playback_detail_fields(raw_detail.get("ext") if isinstance(raw_detail, Mapping) else None)
        except (KeyError, IndexError) as exc:
            raise ValueError(f"没有可播放的项目: {vod_id}") from exc
        source_groups: list[PlaybackSourceGroup] = []
        playlists: list[list[PlayItem]] = []
        if isinstance(raw_detail, Mapping):
            source_groups, playlists = self._build_grouped_sources_from_payload(detail, raw_detail.get("group"))
        if not playlists:
            playlists = self._build_playlist(detail)
            source_groups = self._build_source_groups_from_playlists(playlists)
        collection_actions = _map_playback_detail_actions(raw_detail.get("actions") if isinstance(raw_detail, Mapping) else None)
        if collection_actions:
            for current_playlist in playlists:
                for item in current_playlist:
                    item.detail_actions = list(collection_actions)
        if not playlists:
            raise ValueError(f"没有可播放的项目: {detail.vod_name}")
        logger.info(
            "Spider plugin build request plugin=%s vod_id=%s routes=%s",
            self._plugin_name,
            detail.vod_id,
            len(playlists),
        )
        playlist = playlists[0]
        source_vod_id = vod_id or detail.vod_id
        history_loader = None
        history_saver = None
        if self._playback_history_loader is not None:
            history_loader = lambda source_vod_id=source_vod_id: self._playback_history_loader(source_vod_id)
        if self._playback_history_saver is not None:
            history_saver = lambda payload, source_vod_id=source_vod_id: self._playback_history_saver(
                source_vod_id,
                payload,
            )

        def playback_loader(
            session_or_item: PlayerSession | PlayItem,
            item: PlayItem | None = None,
        ) -> PlaybackLoadResult | None:
            if item is None:
                session = PlayerSession(
                    vod=detail,
                    playlist=playlist,
                    start_index=0,
                    start_position_seconds=0,
                    speed=1.0,
                    playlists=playlists,
                    playlist_index=0,
                    source_groups=source_groups,
                    source_group_index=0,
                    source_index=0,
                )
                current_item = session_or_item
            else:
                session = session_or_item
                current_item = item
            return self._resolve_play_item(session, current_item)

        def detail_action_runner(item: PlayItem, action_id: str) -> list[PlaybackDetailAction]:
            playlist_index = 0
            for current_index, current_playlist in enumerate(playlists):
                if item in current_playlist:
                    playlist_index = current_index
                    break
            return self._run_detail_action(detail, playlists, playlist_index, item, action_id)

        return OpenPlayerRequest(
            vod=detail,
            playlist=playlist,
            playlists=playlists,
            playlist_index=0,
            source_groups=source_groups,
            source_group_index=0,
            source_index=0,
            clicked_index=0,
            source_kind="plugin",
            source_mode="detail",
            source_vod_id=source_vod_id,
            use_local_history=False,
            playback_loader=playback_loader,
            async_playback_loader=True,
            detail_action_runner=detail_action_runner,
            danmaku_controller=self if self._danmaku_enabled and self._danmaku_service is not None else None,
            playback_history_loader=history_loader,
            playback_history_saver=history_saver,
        )
