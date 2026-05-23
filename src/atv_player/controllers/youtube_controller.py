from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx

from atv_player.api import ApiError
from atv_player.models import (
    AppConfig,
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    OpenPlayerRequest,
    PlaybackDetailField,
    PlayItem,
    VodItem,
)


_DEFAULT_CATEGORIES = [
    {"id": "cat_recommend", "name": "首页推荐", "query": "推荐", "order": 1},
    {"id": "cat_trending", "name": "热门", "query": "热门", "order": 2},
    {"id": "cat_recent", "name": "最近更新", "query": "最新", "order": 3},
    {"id": "cat_live", "name": "直播", "query": "直播", "order": 4},
    {"id": "cat_news", "name": "新闻", "query": "新闻", "order": 5},
    {"id": "cat_cdrama", "name": "中国电视", "query": "中国电视", "playlistOnly": True, "order": 6},
    {"id": "cat_drama", "name": "剧集", "query": "剧集", "playlistOnly": True, "order": 7},
    {"id": "cat_movie", "name": "中国电影", "query": "最新电影", "order": 8},
    {"id": "cat_movie_zh", "name": "电影", "query": "电影", "order": 9},
    {"id": "cat_movie_en", "name": "movie", "query": "movie", "order": 10},
    {"id": "cat_variety", "name": "中国综艺", "query": "喜剧综艺", "playlistOnly": True, "order": 11},
    {"id": "cat_variety_zh", "name": "综艺", "query": "综艺", "playlistOnly": True, "order": 12},
    {"id": "cat_anime", "name": "中国动漫", "query": "中国动漫", "playlistOnly": True, "order": 13},
    {"id": "cat_doc", "name": "中国纪录", "query": "中国纪录", "playlistOnly": True, "order": 14},
    {"id": "cat_doc_zh", "name": "纪录片", "query": "纪录片", "playlistOnly": True, "order": 15},
    {"id": "cat_doc_en", "name": "documentary", "query": "documentary", "playlistOnly": True, "order": 16},
    {"id": "cat_doc_bbc", "name": "BBC纪录", "query": "bbc documentary", "playlistOnly": True, "order": 17},
    {"id": "cat_music", "name": "中国音乐", "query": "华语音乐", "order": 18},
    {"id": "cat_music_zh", "name": "音乐", "query": "音乐", "order": 19},
    {"id": "cat_music_en", "name": "music", "query": "music", "order": 20},
    {"id": "cat_short", "name": "中国短剧", "query": "中国短剧", "playlistOnly": True, "order": 21},
    {"id": "cat_shorts", "name": "Shorts", "query": "#shorts", "order": 22},
    {"id": "cat_sports", "name": "体育", "query": "体育", "order": 23},
    {"id": "cat_animal", "name": "动物", "query": "动物世界", "order": 24},
    {"id": "cat_scenery", "name": "风光", "query": "风光", "order": 25},
    {"id": "cat_relax", "name": "放松", "query": "放松", "order": 26},
    {"id": "cat_4k", "name": "4K", "query": "4K", "order": 27},
    {"id": "cat_hdr", "name": "HDR", "query": "HDR", "order": 28},
]

_DEFAULT_FILTERS = [
    {"id": "filter_action", "name": "动作片", "categoryId": "cat_movie", "query": "动作电影", "order": 1},
    {"id": "filter_scifi", "name": "科幻片", "categoryId": "cat_movie", "query": "科幻电影", "order": 2},
    {"id": "filter_romance", "name": "爱情片", "categoryId": "cat_movie", "query": "爱情电影", "order": 3},
    {"id": "filter_comedy", "name": "喜剧片", "categoryId": "cat_movie", "query": "喜剧电影", "order": 4},
    {"id": "filter_horror", "name": "恐怖片", "categoryId": "cat_movie", "query": "恐怖电影", "order": 5},
    {"id": "filter_thriller", "name": "悬疑片", "categoryId": "cat_movie", "query": "悬疑电影", "order": 6},
    {"id": "filter_doc_cctv", "name": "CCTV纪录", "categoryId": "cat_doc", "query": "CCTV纪录", "order": 1},
    {"id": "filter_doc_natgeo", "name": "国家地理", "categoryId": "cat_doc", "query": "国家地理", "order": 2},
]

_LOGIN_CATEGORIES = [
    {"id": "cat_sub_feed", "name": "我的订阅视频"},
    {"id": "cat_sub_channels", "name": "我的订阅频道"},
    {"id": "cat_history", "name": "播放历史"},
    {"id": "cat_watch_later", "name": "稍后再看"},
]

_LOGIN_FEED_URLS = {
    "cat_sub_feed": ":ytsubs",
    "cat_sub_channels": "https://www.youtube.com/feed/channels",
    "cat_history": ":ythis",
    "cat_watch_later": ":ytwatchlater",
}
_YOUTUBE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _youtube_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _youtube_video_thumbnail(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""


def _entry_url(entry: dict) -> str:
    value = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    entry_id = str(entry.get("id") or "").strip()
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if ie_key == "youtube" and entry_id:
        return _youtube_video_url(entry_id)
    if value and len(value) == 11:
        return _youtube_video_url(value)
    return value


def _video_id(entry: dict, url: str) -> str:
    entry_id = str(entry.get("id") or "").strip()
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if ie_key == "youtube" and entry_id:
        return entry_id
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("v", [""])[0]
    if query_id:
        return query_id
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/")
    return entry_id if len(entry_id) == 11 else ""


def _playlist_id(entry: dict, url: str) -> str:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("list", [""])[0]
    if query_id:
        return query_id
    entry_id = str(entry.get("id") or "").strip()
    return entry_id if entry_id.startswith(("PL", "RD", "OLAK")) else ""


def _channel_id(entry: dict, url: str) -> str:
    entry_id = str(entry.get("channel_id") or entry.get("id") or "").strip()
    if entry_id.startswith("UC"):
        return entry_id
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "channel" and parts[1].startswith("UC"):
        return parts[1]
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if "youtubetab" in ie_key and url:
        return url.rstrip("/")
    return ""


def _entry_title(entry: dict, fallback: str = "") -> str:
    return str(entry.get("title") or entry.get("fulltitle") or fallback).strip()


def _entry_thumbnail(entry: dict, video_id: str = "") -> str:
    value = str(entry.get("thumbnail") or "").strip()
    if value:
        return value
    thumbnails = entry.get("thumbnails")
    if isinstance(thumbnails, list):
        avatar_candidates = []
        square_candidates = []
        fallback_candidates = []
        for thumbnail in reversed(thumbnails):
            if not isinstance(thumbnail, dict):
                continue
            value = str(thumbnail.get("url") or "").strip()
            if not value:
                continue
            thumbnail_id = str(thumbnail.get("id") or "").lower()
            if "avatar" in thumbnail_id:
                avatar_candidates.append(value)
                continue
            try:
                width = int(thumbnail.get("width") or 0)
                height = int(thumbnail.get("height") or 0)
            except (TypeError, ValueError):
                width = 0
                height = 0
            if width > 0 and height > 0 and abs(width - height) <= max(2, width // 20):
                square_candidates.append(value)
                continue
            fallback_candidates.append(value)
        if avatar_candidates:
            return avatar_candidates[0]
        if square_candidates:
            return square_candidates[0]
        if fallback_candidates:
            return fallback_candidates[0]
    return _youtube_video_thumbnail(video_id)


def _entry_remarks(entry: dict) -> str:
    channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
    duration = _format_detail_duration(entry.get("duration_string") or entry.get("duration"))
    return " | ".join(part for part in (channel, duration) if part)


def _format_detail_stat_value(raw_value: object) -> str:
    if isinstance(raw_value, bool):
        return str(raw_value)
    if isinstance(raw_value, int | float):
        numeric_value = float(raw_value)
        if numeric_value >= 10000:
            return f"{numeric_value / 10000:.1f}万"
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(raw_value)
    value = str(raw_value or "").strip()
    if not value:
        return ""
    try:
        numeric_value = float(value)
    except ValueError:
        return value
    if numeric_value >= 10000:
        return f"{numeric_value / 10000:.1f}万"
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return value


def _format_detail_date(raw_value: object) -> str:
    value = str(raw_value or "").strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _format_detail_duration(raw_value: object) -> str:
    value = str(raw_value or "").strip()
    if value and ":" in value:
        return value
    try:
        total_seconds = int(raw_value or 0)
    except (TypeError, ValueError):
        return ""
    if total_seconds <= 0:
        return ""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_detail_list(raw_value: object, *, limit: int = 8) -> str:
    if isinstance(raw_value, (list, tuple)):
        parts = [str(item or "").strip() for item in raw_value]
        parts = [part for part in parts if part]
        if limit > 0:
            parts = parts[:limit]
        return " / ".join(parts)
    return str(raw_value or "").strip()


def _append_detail_field(fields: list[PlaybackDetailField], label: str, value: object) -> None:
    normalized = str(value or "").strip()
    if not normalized:
        return
    fields.append(PlaybackDetailField(label, normalized))


def _extract_text(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    content = node.get("content")
    if content is not None:
        return str(content)
    simple_text = node.get("simpleText")
    if simple_text is not None:
        return str(simple_text)
    runs = node.get("runs")
    if isinstance(runs, list):
        return "".join(str(run.get("text") or "") for run in runs if isinstance(run, dict))
    return ""


def _extract_youtube_thumbnail(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    sources = (
        (((node.get("contentImage") or {}).get("collectionThumbnailViewModel") or {})
         .get("primaryThumbnail", {})
         .get("thumbnailViewModel", {})
         .get("image", {})
         .get("sources"))
        or (((node.get("contentImage") or {}).get("thumbnailViewModel") or {})
            .get("image", {})
            .get("sources"))
    )
    if isinstance(sources, list) and sources:
        value = str((sources[-1] or {}).get("url") or "").strip()
        return f"https:{value}" if value.startswith("//") else value
    thumbnail = node.get("thumbnail") or node.get("thumbnails") or node.get("avatar")
    if not thumbnail:
        return ""
    if isinstance(thumbnail, list):
        thumbnails = thumbnail
    elif isinstance(thumbnail, dict):
        thumbnails = thumbnail.get("thumbnails")
    else:
        thumbnails = []
    if not isinstance(thumbnails, list) or not thumbnails:
        return ""
    value = str((thumbnails[-1] or {}).get("url") or "").strip()
    return f"https:{value}" if value.startswith("//") else value


def _extract_yt_initial_data(html_text: str) -> dict:
    match = re.search(r"\bytInitialData\s*=", html_text)
    if match is None:
        return {}
    start = html_text.find("{", match.end())
    if start < 0:
        return {}
    in_string = False
    escape = False
    depth = 0
    for index in range(start, len(html_text)):
        char = html_text[index]
        if escape:
            escape = False
            continue
        if in_string:
            if char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(html_text[start:index + 1])
                except json.JSONDecodeError:
                    return {}
                return data if isinstance(data, dict) else {}
    return {}


def _video_detail_fields(entry: dict) -> list[PlaybackDetailField]:
    fields: list[PlaybackDetailField] = []
    _append_detail_field(fields, "频道", entry.get("channel") or entry.get("uploader") or entry.get("creator"))
    _append_detail_field(fields, "发布", _format_detail_date(entry.get("upload_date") or entry.get("release_date")))
    _append_detail_field(fields, "时长", _format_detail_duration(entry.get("duration_string") or entry.get("duration")))
    _append_detail_field(fields, "播放", _format_detail_stat_value(entry.get("view_count")))
    _append_detail_field(fields, "点赞", _format_detail_stat_value(entry.get("like_count")))
    _append_detail_field(fields, "评论", _format_detail_stat_value(entry.get("comment_count")))
    _append_detail_field(fields, "分类", _format_detail_list(entry.get("categories"), limit=3))
    _append_detail_field(fields, "标签", _format_detail_list(entry.get("tags"), limit=8))
    _append_detail_field(fields, "简介", entry.get("description"))
    return fields


class YouTubeController:
    supports_search = True

    def __init__(
        self,
        config: AppConfig,
        *,
        yt_dlp_service,
        playback_history_loader: Callable[[str], object | None] | None = None,
        playback_history_saver: Callable[[str, dict[str, object]], None] | None = None,
        http_get: Callable[..., object] = httpx.get,
    ) -> None:
        self._config = config
        self._yt_dlp_service = yt_dlp_service
        self._playback_history_loader = playback_history_loader
        self._playback_history_saver = playback_history_saver
        self._http_get = http_get
        self._channel_thumbnail_cache: dict[str, str] = {}

    def _has_cookie_browser(self) -> bool:
        return bool(str(getattr(self._config, "youtube_cookie_browser", "") or "").strip())

    def _youtube_cookie_header(self) -> str:
        service = self._yt_dlp_service
        cookie_header = getattr(service, "youtube_cookie_header", None)
        if not callable(cookie_header):
            return ""
        try:
            return str(cookie_header() or "").strip()
        except Exception:
            return ""

    def _clear_youtube_cookie_header_cache(self) -> None:
        service = self._yt_dlp_service
        clear_cache = getattr(service, "clear_youtube_cookie_header_cache", None)
        if callable(clear_cache):
            clear_cache()

    def _youtube_http_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": _YOUTUBE_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        cookie = self._youtube_cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _channel_item_from_renderer(self, renderer: dict) -> VodItem | None:
        channel_ref = str(renderer.get("channelId") or "").strip()
        endpoint = (renderer.get("navigationEndpoint") or {}).get("browseEndpoint") or {}
        if not channel_ref:
            channel_ref = str(endpoint.get("browseId") or "").strip()
        command_metadata = (
            (renderer.get("navigationEndpoint") or {}).get("commandMetadata") or {}
        )
        canonical_url = str(
            (command_metadata.get("webCommandMetadata") or {}).get("url") or ""
        ).strip()
        if not channel_ref and canonical_url:
            channel_ref = (
                f"https://www.youtube.com{canonical_url}"
                if canonical_url.startswith("/")
                else canonical_url
            )
        if not channel_ref:
            return None
        return VodItem(
            vod_id=f"yt:channel:{channel_ref}",
            vod_name=_extract_text(renderer.get("title")) or channel_ref,
            vod_pic=_extract_youtube_thumbnail(renderer),
            vod_remarks="频道",
            vod_tag="file",
        )

    def _channel_item_from_lockup(self, model: dict) -> VodItem | None:
        content_type = str(model.get("contentType") or "")
        if "CHANNEL" not in content_type:
            return None
        channel_ref = str(model.get("contentId") or "").strip()
        if not channel_ref:
            return None
        metadata = (model.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        return VodItem(
            vod_id=f"yt:channel:{channel_ref}",
            vod_name=_extract_text(metadata.get("title")) or channel_ref,
            vod_pic=_extract_youtube_thumbnail(model),
            vod_remarks="频道",
            vod_tag="file",
        )

    def _collect_channel_items(self, payload: object) -> list[VodItem]:
        items: list[VodItem] = []
        seen: set[str] = set()

        def add(item: VodItem | None) -> None:
            if item is None or not item.vod_id or item.vod_id in seen:
                return
            seen.add(item.vod_id)
            items.append(item)

        def walk(node: object) -> None:
            if isinstance(node, list):
                for value in node:
                    walk(value)
                return
            if not isinstance(node, dict):
                return
            renderer = node.get("channelRenderer")
            if isinstance(renderer, dict):
                add(self._channel_item_from_renderer(renderer))
            lockup = node.get("lockupViewModel")
            if isinstance(lockup, dict):
                add(self._channel_item_from_lockup(lockup))
            for value in node.values():
                walk(value)

        walk(payload)
        return items

    def _fetch_subscription_channels_page(self) -> str:
        headers = self._youtube_http_headers()
        if not headers.get("Cookie"):
            return ""
        response = self._http_get(
            "https://www.youtube.com/feed/channels",
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        return str(getattr(response, "text", "") or "")

    def _looks_like_login_required_page(self, html_text: str) -> bool:
        return any(
            token in html_text
            for token in (
                "accounts.google.com",
                "ServiceLogin",
                '"LOGIN_REQUIRED"',
            )
        )

    def _load_subscription_channels_direct_once(self) -> list[VodItem]:
        text = self._fetch_subscription_channels_page()
        if not text or self._looks_like_login_required_page(text):
            return []
        payload = _extract_yt_initial_data(text)
        return self._collect_channel_items(payload)

    def _load_subscription_channels_direct(self) -> list[VodItem]:
        try:
            items = self._load_subscription_channels_direct_once()
        except Exception:
            items = []
        if items:
            return items
        self._clear_youtube_cookie_header_cache()
        try:
            return self._load_subscription_channels_direct_once()
        except Exception:
            return []

    def _flat_entries(self, url: str, page: int, page_size: int = 30) -> list[dict]:
        service = self._yt_dlp_service
        if service is None or not service.is_available():
            return []
        extract = getattr(service, "extract_flat_playlist", None)
        if not callable(extract):
            return []
        try:
            return list(extract(url, page=page, page_size=page_size) or [])
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(f"YouTube 列表加载失败: {exc}") from exc

    def load_categories(self) -> list[DoubanCategory]:
        categories = [
            DoubanCategory(
                type_id=str(item["id"]),
                type_name=str(item["name"]),
                filters=self._filters_for_category(str(item["id"])),
            )
            for item in sorted(_DEFAULT_CATEGORIES, key=lambda item: int(item["order"]))
        ]
        if self._has_cookie_browser():
            categories = [
                DoubanCategory(type_id=str(item["id"]), type_name=str(item["name"]))
                for item in _LOGIN_CATEGORIES
            ] + categories
        return categories

    def _filters_for_category(self, category_id: str) -> list[CategoryFilter]:
        options = [
            CategoryFilterOption(name=str(item["name"]), value=str(item["id"]))
            for item in sorted(_DEFAULT_FILTERS, key=lambda item: int(item["order"]))
            if item["categoryId"] == category_id
        ]
        return [CategoryFilter(key="filter", name="筛选", options=options)] if options else []

    def _map_entry(self, entry: dict) -> VodItem | None:
        url = _entry_url(entry)
        video_id = _video_id(entry, url)
        playlist_id = _playlist_id(entry, url)
        channel_id = _channel_id(entry, url)
        if channel_id and not video_id and not playlist_id:
            return VodItem(
                vod_id=f"yt:channel:{channel_id}",
                vod_name=_entry_title(entry, channel_id),
                vod_pic=_entry_thumbnail(entry),
                vod_remarks="频道",
                vod_tag="file",
            )
        if playlist_id and not video_id:
            return VodItem(
                vod_id=f"yt:playlist:{playlist_id}",
                vod_name=_entry_title(entry, playlist_id),
                vod_pic=_entry_thumbnail(entry),
                vod_remarks="Playlist",
                vod_tag="file",
            )
        if video_id:
            return VodItem(
                vod_id=f"yt:video:{video_id}",
                vod_name=_entry_title(entry, video_id),
                vod_pic=_entry_thumbnail(entry, video_id),
                vod_remarks=_entry_remarks(entry),
                vod_tag="file",
            )
        return None

    def _map_entries(self, entries: list[dict], *, channels_only: bool = False, videos_only: bool = False) -> list[VodItem]:
        items = []
        seen = set()
        for entry in entries:
            item = self._map_entry(entry)
            if item is None:
                continue
            if channels_only and not item.vod_id.startswith("yt:channel:"):
                continue
            if videos_only and not item.vod_id.startswith("yt:video:"):
                continue
            if item.vod_id in seen:
                continue
            seen.add(item.vod_id)
            items.append(item)
        return items

    def _channel_ref_from_vod_id(self, vod_id: str) -> str:
        if not vod_id.startswith("yt:channel:"):
            return ""
        return vod_id.split(":", 2)[2].strip()

    def _channel_metadata_url(self, channel_ref: str) -> str:
        if channel_ref.startswith(("http://", "https://")):
            return channel_ref.rstrip("/")
        if channel_ref.startswith("UC"):
            return f"https://www.youtube.com/channel/{channel_ref}"
        return channel_ref

    def _load_channel_thumbnail(self, channel_ref: str) -> str:
        metadata_url = self._channel_metadata_url(channel_ref)
        if not metadata_url:
            return ""
        if metadata_url in self._channel_thumbnail_cache:
            return self._channel_thumbnail_cache[metadata_url]
        thumbnail = ""
        try:
            entries = self._flat_entries(metadata_url, 1, 1)
        except Exception:
            entries = []
        for entry in entries:
            thumbnail = _entry_thumbnail(entry)
            if thumbnail:
                break
        self._channel_thumbnail_cache[metadata_url] = thumbnail
        return thumbnail

    def _enrich_channel_thumbnails(self, items: list[VodItem]) -> list[VodItem]:
        enriched = []
        for item in items:
            if item.vod_pic or not item.vod_id.startswith("yt:channel:"):
                enriched.append(item)
                continue
            thumbnail = self._load_channel_thumbnail(self._channel_ref_from_vod_id(item.vod_id))
            if thumbnail:
                item = VodItem(
                    vod_id=item.vod_id,
                    vod_name=item.vod_name,
                    detail_style=item.detail_style,
                    path=item.path,
                    share_type=item.share_type,
                    vod_pic=thumbnail,
                    poster_candidates=list(item.poster_candidates),
                    vod_tag=item.vod_tag,
                    vod_time=item.vod_time,
                    vod_remarks=item.vod_remarks,
                    vod_play_from=item.vod_play_from,
                    vod_play_url=item.vod_play_url,
                    type_name=item.type_name,
                    category_name=item.category_name,
                    vod_content=item.vod_content,
                    vod_year=item.vod_year,
                    vod_area=item.vod_area,
                    vod_lang=item.vod_lang,
                    vod_director=item.vod_director,
                    vod_actor=item.vod_actor,
                    epg_current=item.epg_current,
                    epg_schedule=item.epg_schedule,
                    dbid=item.dbid,
                    type=item.type,
                    detail_fields=list(item.detail_fields),
                    items=list(item.items),
                )
            enriched.append(item)
        return enriched

    def _resolve_category_query(self, category_id: str, filters: dict[str, str]) -> tuple[str, bool]:
        category = next((item for item in _DEFAULT_CATEGORIES if item["id"] == category_id), None)
        if category is None:
            return "", False
        query = str(category["query"])
        playlist_only = bool(category.get("playlistOnly", False))
        filter_id = str((filters or {}).get("filter") or "")
        selected = next(
            (
                item for item in _DEFAULT_FILTERS
                if item["id"] == filter_id and item["categoryId"] == category_id
            ),
            None,
        )
        if selected is not None:
            query = str(selected["query"])
        return query, playlist_only

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        page_number = max(1, int(page or 1))
        if category_id in _LOGIN_FEED_URLS:
            if not self._has_cookie_browser():
                return [], 0
            if category_id == "cat_sub_channels" and page_number == 1:
                direct_items = self._load_subscription_channels_direct()
                if direct_items:
                    return self._enrich_channel_thumbnails(direct_items), len(direct_items)
            entries = self._flat_entries(_LOGIN_FEED_URLS[category_id], page_number)
            items = self._map_entries(
                entries,
                channels_only=category_id == "cat_sub_channels",
                videos_only=category_id in {"cat_sub_feed", "cat_history", "cat_watch_later"},
            )
            if category_id == "cat_sub_channels":
                items = self._enrich_channel_thumbnails(items)
            return items, (page_number - 1) * 30 + len(items)
        query, playlist_only = self._resolve_category_query(category_id, filters or {})
        if not query:
            return [], 0
        if playlist_only:
            query = f"{query} playlist"
        entries = self._flat_entries(f"ytsearchall:{query}", page_number)
        items = self._map_entries(entries)
        return items, (page_number - 1) * 30 + len(items)

    def search_items(
        self,
        keyword: str,
        page: int,
        category_id: str = "",
    ) -> tuple[list[VodItem], int]:
        del category_id
        page_number = max(1, int(page or 1))
        query = str(keyword or "").strip()
        if not query:
            return [], 0
        entries = self._flat_entries(f"ytsearchall:{query}", page_number)
        items = self._map_entries(entries)
        return items, (page_number - 1) * 30 + len(items)

    def _entry_for_video(self, video_id: str) -> dict:
        entries = self._flat_entries(_youtube_video_url(video_id), 1, 1)
        for entry in entries:
            if _video_id(entry, _entry_url(entry)) == video_id or str(entry.get("id") or "") == video_id:
                return entry
        return {"id": video_id, "title": "YouTube视频", "url": _youtube_video_url(video_id), "ie_key": "Youtube"}

    def _play_item_from_entry(self, entry: dict, *, media_title: str = "", playlist_id: str = "") -> PlayItem | None:
        url = _entry_url(entry)
        video_id = _video_id(entry, url)
        if not video_id:
            return None
        title = _entry_title(entry, video_id)
        vod_id = f"yt:entry:{playlist_id}:{video_id}" if playlist_id else f"yt:video:{video_id}"
        return PlayItem(
            title=title,
            url="",
            original_url=_youtube_video_url(video_id),
            vod_id=vod_id,
            media_title=media_title,
            video_cover_override=_entry_thumbnail(entry, video_id),
            play_source="YouTube",
            detail_fields=_video_detail_fields(entry),
        )

    def _build_video_request(self, video_id: str, source_vod_id: str) -> OpenPlayerRequest:
        entry = self._entry_for_video(video_id)
        title = _entry_title(entry, "YouTube视频")
        thumb = _entry_thumbnail(entry, video_id)
        vod = VodItem(
            vod_id=f"yt:video:{video_id}",
            vod_name=title,
            detail_style="youtube",
            vod_pic=thumb,
            vod_remarks=_entry_remarks(entry),
            detail_fields=_video_detail_fields(entry),
        )
        item = self._play_item_from_entry(entry, media_title=title)
        if item is None:
            item = PlayItem(
                title=title,
                url="",
                original_url=_youtube_video_url(video_id),
                vod_id=f"yt:video:{video_id}",
                media_title=title,
                video_cover_override=thumb,
                play_source="YouTube",
            )
        return self._request(vod, [item], source_vod_id)

    def _build_playlist_request(self, playlist_id: str, source_vod_id: str) -> OpenPlayerRequest:
        entries = self._flat_entries(f"https://www.youtube.com/playlist?list={playlist_id}", 1, 200)
        playlist = [
            item for item in (self._play_item_from_entry(entry, media_title="YouTube播放列表", playlist_id=playlist_id) for entry in entries)
            if item is not None
        ]
        vod = VodItem(
            vod_id=f"yt:playlist:{playlist_id}",
            vod_name="YouTube播放列表",
            detail_style="youtube",
            vod_remarks="播放列表",
            vod_pic=playlist[0].video_cover_override if playlist else "",
        )
        return self._request(vod, playlist, source_vod_id)

    def _build_channel_request(self, channel_ref: str, source_vod_id: str) -> OpenPlayerRequest:
        channel_url = (
            f"{channel_ref.rstrip('/')}/videos"
            if channel_ref.startswith(("http://", "https://"))
            else f"https://www.youtube.com/channel/{channel_ref}/videos"
        )
        entries = self._flat_entries(channel_url, 1, 200)
        channel_title = channel_ref
        for entry in entries:
            title = str(entry.get("channel") or entry.get("uploader") or "").strip()
            if title:
                channel_title = title
                break
        playlist = [
            item for item in (self._play_item_from_entry(entry, media_title=channel_title) for entry in entries)
            if item is not None
        ]
        vod = VodItem(
            vod_id=f"yt:channel:{channel_ref}",
            vod_name=channel_title,
            detail_style="youtube",
            vod_remarks="频道",
            vod_pic=playlist[0].video_cover_override if playlist else "",
        )
        return self._request(vod, playlist, source_vod_id)

    def build_request(self, vod_id: str) -> OpenPlayerRequest:
        normalized = str(vod_id or "").strip()
        if normalized.startswith("UC"):
            normalized = f"yt:channel:{normalized}"
        if normalized.startswith("yt:video:"):
            return self._build_video_request(normalized.split(":", 2)[2], normalized)
        if normalized.startswith("yt:entry:"):
            _prefix, _entry, playlist_id, video_id = normalized.split(":", 3)
            return self._build_video_request(video_id, normalized if not playlist_id else f"yt:playlist:{playlist_id}")
        if normalized.startswith("yt:playlist:"):
            return self._build_playlist_request(normalized.split(":", 2)[2], normalized)
        if normalized.startswith("yt:channel:"):
            return self._build_channel_request(normalized.split(":", 2)[2], normalized)
        raise ValueError(f"没有可播放的项目: {vod_id}")

    def _request(self, vod: VodItem, playlist: list[PlayItem], source_vod_id: str) -> OpenPlayerRequest:
        if not playlist:
            raise ValueError(f"没有可播放的项目: {vod.vod_name or source_vod_id}")
        source_vod_id = source_vod_id or vod.vod_id
        history_loader = None
        if self._playback_history_loader is not None:
            def history_loader(source_vod_id=source_vod_id):
                return self._playback_history_loader(source_vod_id)
        history_saver = None
        if self._playback_history_saver is not None:
            def history_saver(payload, source_vod_id=source_vod_id):
                return self._playback_history_saver(source_vod_id, payload)
        return OpenPlayerRequest(
            vod=vod,
            playlist=playlist,
            playlists=[playlist],
            clicked_index=0,
            source_kind="youtube",
            source_mode="detail",
            source_vod_id=source_vod_id,
            use_local_history=False,
            playback_loader=self._load_playback_item,
            async_playback_loader=True,
            playback_history_loader=history_loader,
            playback_history_saver=history_saver,
        )

    def _playback_url(self, value: str) -> str:
        if value.startswith("yt:video:"):
            return _youtube_video_url(value.split(":", 2)[2])
        if value.startswith("yt:entry:"):
            _prefix, _entry, playlist_id, video_id = value.split(":", 3)
            return f"{_youtube_video_url(video_id)}&list={playlist_id}" if playlist_id else _youtube_video_url(video_id)
        return value

    def _load_playback_item(self, session_or_item, item: PlayItem | None = None):
        session = session_or_item if item is not None else None
        current_item = item or session_or_item
        source_url = (current_item.original_url or self._playback_url(current_item.vod_id)).strip()
        service = self._yt_dlp_service
        if service is None or not service.is_available():
            raise ValueError("yt-dlp 不可用")
        selected_quality_id = current_item.selected_playback_quality_id or ""
        selected_audio_track_id = current_item.selected_audio_track_id or ""
        if selected_quality_id.startswith("ytdlp_"):
            result = service.resolve_for_quality(
                source_url,
                selected_quality_id,
                audio_track_id=selected_audio_track_id,
            )
        else:
            result = service.resolve(
                source_url,
                max_height=None,
                selected_audio_track_id=selected_audio_track_id,
            )
        service.apply_result(
            result,
            vod=None if session is None else session.vod,
            item=current_item,
            source_url=source_url,
        )
        return None
