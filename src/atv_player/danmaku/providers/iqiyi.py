from __future__ import annotations

from dataclasses import replace
import html
import json
import math
import re
import xml.etree.ElementTree as ET
import zlib

import httpx

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.providers._concurrency import iter_bounded_settled
from atv_player.danmaku.utils import (
    episode_title_matches,
    extract_episode_number,
    has_explicit_episode_marker,
    normalize_name,
    similarity_score,
)


class IqiyiDanmakuProvider:
    key = "iqiyi"
    _SEARCH_URL = "https://search.video.iqiyi.com/o"
    _MESH_SEARCH_URL = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
    _SEARCH_HEADERS = {"user-agent": "Mozilla/5.0", "referer": "https://www.iqiyi.com/"}
    _PAGE_HEADERS = {"user-agent": "Mozilla/5.0", "referer": "https://www.iqiyi.com/"}
    _DROP_CHANNEL_KEYWORDS = ("生活", "教育")
    _DROP_TITLE_KEYWORDS = ("精彩看点", "精彩片段", "精彩分享")
    _ALLOWED_SITE_IDS = {"iqiyi", ""}
    _ALLOWED_SITE_NAMES = {"爱奇艺", ""}

    def __init__(self, get=httpx.get) -> None:
        self._get = get
        self._metadata_by_url: dict[str, dict[str, str | int | None]] = {}

    def supports(self, page_url: str) -> bool:
        return "iqiyi.com" in page_url

    def search(self, name: str, original_name: str | None = None) -> list[DanmakuSearchItem]:
        original_query = normalize_name(original_name or name)
        explicit_episode_query = has_explicit_episode_marker(original_query) if original_query else False
        requested_episode = extract_episode_number(original_query) if original_query else None
        mesh_error: DanmakuSearchError | None = None
        mesh_queries: list[str] = []
        if explicit_episode_query and original_name:
            mesh_queries.append(original_name)
        if name not in mesh_queries:
            mesh_queries.append(name)
        mesh_items: list[DanmakuSearchItem] = []
        for mesh_query in mesh_queries:
            try:
                mesh_items = self._search_mesh_items(
                    mesh_query,
                    explicit_episode_query=explicit_episode_query,
                    requested_episode=requested_episode,
                )
            except DanmakuSearchError as exc:
                if mesh_error is None:
                    mesh_error = exc
                continue
            if mesh_items:
                break
        if mesh_items and (
            not explicit_episode_query or self._has_exact_episode_match(mesh_items, original_query)
        ):
            return mesh_items
        try:
            legacy_items = self._search_legacy_items(name)
        except DanmakuSearchError:
            if mesh_error is not None:
                legacy_items = []
            else:
                return []
        merged_items = self._merge_search_items(mesh_items, legacy_items)
        if merged_items:
            return merged_items
        if mesh_error is not None:
            raise mesh_error
        return []

    def _has_exact_episode_match(self, items: list[DanmakuSearchItem], query_name: str) -> bool:
        normalized_query = normalize_name(query_name)
        requested_episode = extract_episode_number(normalized_query)
        if requested_episode is None:
            return False
        return any(
            extract_episode_number(item.name) == requested_episode
            and episode_title_matches(normalized_query, item.name)
            for item in items
        )

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        page_url = self._normalize_iqiyi_url(page_url)
        response = self._get(
            page_url,
            headers=dict(self._PAGE_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        page_info = self._try_extract_page_info(response.text)
        cached_metadata = self._metadata_by_url.get(page_url) or self._metadata_by_url.get(self._swap_scheme(page_url))
        if not page_info and cached_metadata is None:
            raise DanmakuResolveError("爱奇艺页面缺少 playPageInfo")
        danmaku_fields = self._resolve_danmaku_fields(page_info, page_url)
        tvid = danmaku_fields["tv_id"]
        album_id = danmaku_fields["album_id"]
        category_id = danmaku_fields["category_id"]
        if not tvid or album_id in ("", None) or category_id in ("", None):
            raise DanmakuResolveError("爱奇艺页面缺少弹幕所需字段")
        duration_seconds = self._resolve_duration_seconds(page_info, cached_metadata)
        total_pages = max(1, math.ceil(duration_seconds / 300.0))
        records: list[DanmakuRecord] = []
        seen: set[tuple[float, str]] = set()
        parse_failures = 0
        page_indexes = range(1, total_pages + 1)
        for batch in iter_bounded_settled(
            page_indexes,
            lambda page_index: self._fetch_segment_content(tvid, album_id, category_id, page_index),
        ):
            for settled in batch:
                if settled.error is not None:
                    raise settled.error
                try:
                    xml_text = zlib.decompress(settled.value or b"", 15 + 32).decode("utf-8", errors="ignore")
                    for record in self._parse_segment_records(xml_text, duration_seconds):
                        key = (record.time_offset, record.content)
                        if key in seen:
                            continue
                        seen.add(key)
                        records.append(record)
                except Exception:
                    parse_failures += 1
        if parse_failures == total_pages and not records:
            raise DanmakuResolveError("爱奇艺弹幕分片解析失败")
        records.sort(key=lambda record: (record.time_offset, record.content))
        return records

    def _fetch_segment_content(self, tvid: str, album_id: str | int, category_id: str | int, page_index: int) -> bytes:
        segment_url = self._segment_url(tvid, page_index)
        segment_response = self._get(
            segment_url,
            params={
                "rn": "0.0123456789123456",
                "business": "danmu",
                "is_iqiyi": "true",
                "is_video_page": "true",
                "tvid": tvid,
                "albumid": album_id,
                "categoryid": category_id,
                "qypid": "01010021010000000000",
            },
            headers=dict(self._PAGE_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        return segment_response.content

    def _extract_search_items(self, payload: dict, query_name: str) -> list[DanmakuSearchItem]:
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("docinfos"), list):
            raise DanmakuSearchError("爱奇艺弹幕搜索结果解析失败")
        results_by_url: dict[str, DanmakuSearchItem] = {}
        mesh_videos_cache: dict[tuple[str, int | None, str], list[dict]] = {}
        for item in data["docinfos"]:
            if self._should_drop_search_item(item):
                continue
            album_info = item.get("albumDocInfo") or {}
            videos = self._collect_search_videos(item, album_info, query_name, mesh_videos_cache)
            for video in videos:
                title = str(video.get("itemTitle") or "").strip()
                url = self._normalize_iqiyi_url(str(video.get("itemLink") or "").strip())
                if not title or not url:
                    continue
                ratio = similarity_score(query_name, title)
                metadata = self._video_metadata(video, album_info)
                existing = results_by_url.get(url)
                merged_metadata = self._merge_search_metadata(
                    existing.resolve_context if existing is not None else None,
                    metadata,
                )
                candidate = DanmakuSearchItem(
                    provider=self.key,
                    name=title,
                    url=url,
                    ratio=ratio,
                    simi=ratio,
                    duration_seconds=self._to_int(merged_metadata.get("duration_seconds")) or 0,
                    resolve_context=dict(merged_metadata),
                )
                if existing is not None:
                    existing = replace(
                        existing,
                        duration_seconds=self._to_int(merged_metadata.get("duration_seconds")) or existing.duration_seconds,
                        resolve_context=dict(merged_metadata),
                    )
                    if self._search_item_rank(candidate) > self._search_item_rank(existing):
                        results_by_url[url] = candidate
                    else:
                        results_by_url[url] = existing
                else:
                    results_by_url[url] = candidate
                self._remember_metadata(url, merged_metadata)
        return list(results_by_url.values())

    def _legacy_search_is_empty(self, payload: dict) -> bool:
        data = payload.get("data")
        return isinstance(data, str) and "search result is empty" in data

    def _search_legacy_items(self, query_name: str) -> list[DanmakuSearchItem]:
        response = self._get(
            self._SEARCH_URL,
            params={
                "key": normalize_name(query_name),
                "pageNum": 1,
                "pageSize": 25,
            },
            headers=dict(self._SEARCH_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("爱奇艺弹幕搜索结果解析失败") from exc
        if self._legacy_search_is_empty(payload):
            return []
        return self._extract_search_items(payload, query_name)

    def _mesh_search_params(self, query_name: str, *, include_site_filter: bool) -> dict[str, object]:
        params: dict[str, object] = {
            "key": normalize_name(query_name),
            "pageNum": 1,
            "pageSize": 25,
            "source": "input",
            "suggest": "",
            "mode": 1,
            "current_page": 1,
        }
        if include_site_filter:
            params["site"] = "iqiyi"
        return params

    def _mesh_search_payload(self, query_name: str, *, include_site_filter: bool) -> dict:
        response = self._get(
            self._MESH_SEARCH_URL,
            params=self._mesh_search_params(query_name, include_site_filter=include_site_filter),
            headers=dict(self._SEARCH_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("爱奇艺弹幕搜索结果解析失败") from exc
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
            raise DanmakuSearchError("爱奇艺弹幕搜索结果解析失败")
        return payload

    def _search_mesh_items(
        self,
        query_name: str,
        *,
        explicit_episode_query: bool = False,
        requested_episode: int | None = None,
    ) -> list[DanmakuSearchItem]:
        payloads = [self._mesh_search_payload(query_name, include_site_filter=True)]
        for payload in payloads:
            items = self._extract_mesh_search_items_from_payload(
                payload,
                query_name,
                explicit_episode_query=explicit_episode_query,
                requested_episode=requested_episode,
            )
            if items:
                return items
            if len(payloads) == 1:
                payloads.append(self._mesh_search_payload(query_name, include_site_filter=False))
        return []

    def _extract_mesh_search_items_from_payload(
        self,
        payload: dict,
        query_name: str,
        *,
        explicit_episode_query: bool = False,
        requested_episode: int | None = None,
    ) -> list[DanmakuSearchItem]:
        results_by_url: dict[str, DanmakuSearchItem] = {}
        for album_info in self._iter_mesh_album_infos(payload):
            if self._should_drop_mesh_album_info(album_info):
                continue
            album_title = normalize_name(str(album_info.get("title") or ""))
            videos = list(album_info.get("videos") or [])
            if not videos:
                try:
                    videos = self._expand_mesh_album_page_videos(album_info)
                except httpx.HTTPError:
                    videos = []
            for video in videos:
                subtitle = str(video.get("subtitle") or "").strip()
                raw_title = str(video.get("title") or "").strip()
                title = raw_title
                if album_title and album_title not in normalize_name(raw_title):
                    title_tail = subtitle or raw_title
                    title = f"{album_title} {title_tail}".strip()
                url = self._normalize_iqiyi_url(str(video.get("pageUrl") or "").strip())
                if not title or not url:
                    continue
                metadata = self._video_metadata(
                    {
                        "tvId": self._to_int(video.get("qipuId")),
                        "albumId": self._to_int(album_info.get("qipuId")),
                        "timeLength": self._mesh_duration_seconds(video.get("duration")),
                        "year": self._to_int(video.get("year")),
                    },
                    album_info,
                )
                ratio = similarity_score(query_name, title)
                candidate = DanmakuSearchItem(
                    provider=self.key,
                    name=title,
                    url=url,
                    ratio=ratio,
                    simi=ratio,
                    duration_seconds=self._to_int(metadata.get("duration_seconds")) or 0,
                    resolve_context=dict(metadata),
                )
                existing = results_by_url.get(url)
                if existing is None or self._search_item_rank(candidate) > self._search_item_rank(existing):
                    results_by_url[url] = candidate
                self._remember_metadata(url, metadata)
            if videos:
                continue
            fallback = self._album_level_episode_candidate(
                album_info,
                query_name,
                explicit_episode_query=explicit_episode_query,
                requested_episode=requested_episode,
            )
            if fallback is None:
                continue
            existing = results_by_url.get(fallback.url)
            if existing is None or self._search_item_rank(fallback) > self._search_item_rank(existing):
                results_by_url[fallback.url] = fallback
            self._remember_metadata(fallback.url, dict(fallback.resolve_context))
        return list(results_by_url.values())

    def _should_drop_mesh_album_info(self, album_info: dict) -> bool:
        channel = str(album_info.get("channel") or "")
        if any(keyword in channel for keyword in self._DROP_CHANNEL_KEYWORDS):
            return True
        title = str(album_info.get("title") or "")
        return any(keyword in title for keyword in self._DROP_TITLE_KEYWORDS)

    def prime_resolve_context(self, page_url: str, resolve_context: dict[str, str | int | None] | None) -> None:
        if not isinstance(resolve_context, dict):
            return
        metadata = {
            "tv_id": resolve_context.get("tv_id"),
            "album_id": resolve_context.get("album_id"),
            "category_id": resolve_context.get("category_id"),
            "duration_seconds": resolve_context.get("duration_seconds"),
        }
        if not any(value not in ("", None) for value in metadata.values()):
            return
        self._remember_metadata(self._normalize_iqiyi_url(page_url), metadata)

    def _collect_search_videos(
        self,
        item: dict,
        album_info: dict,
        query_name: str,
        mesh_videos_cache: dict[tuple[str, int | None, str], list[dict]],
    ) -> list[dict]:
        videos = list(item.get("videoinfos") or album_info.get("videoinfos") or [])
        if self._should_use_mesh_search_videos(videos, album_info):
            mesh_cache_key = self._mesh_cache_key(query_name, album_info)
            cached_mesh_videos = mesh_videos_cache.get(mesh_cache_key)
            if cached_mesh_videos is not None:
                return list(cached_mesh_videos)
            try:
                expanded = self._expand_mesh_videos(query_name, album_info)
            except httpx.HTTPError:
                expanded = []
            mesh_videos_cache[mesh_cache_key] = list(expanded)
            if expanded:
                return expanded
        if not self._should_expand_album_videos(videos, album_info):
            return videos
        try:
            expanded = self._expand_album_videos(album_info)
        except httpx.HTTPError:
            return videos
        if expanded:
            return expanded
        return videos

    def _should_use_mesh_search_videos(self, videos: list[dict], album_info: dict) -> bool:
        item_total = self._to_int(album_info.get("itemTotalNumber"))
        if item_total not in (None, 0):
            return False
        return bool(videos) and any(album_info.get(key) not in ("", None) for key in ("albumId", "albumTitle"))

    def _expand_mesh_videos(self, query_name: str, album_info: dict) -> list[dict]:
        target_album_id = self._to_int(album_info.get("albumId"))
        target_title = normalize_name(str(album_info.get("albumTitle") or ""))
        payloads = [self._mesh_search_payload(query_name, include_site_filter=True)]
        for payload in payloads:
            for matched_album_info in self._iter_mesh_album_infos(payload):
                matched_album_id = self._to_int(matched_album_info.get("qipuId"))
                matched_title = normalize_name(str(matched_album_info.get("title") or ""))
                if target_album_id is not None and matched_album_id != target_album_id:
                    continue
                if target_album_id is None and target_title and matched_title != target_title:
                    continue
                videos: list[dict] = []
                for video in matched_album_info.get("videos") or []:
                    subtitle = str(video.get("subtitle") or "").strip()
                    raw_title = str(video.get("title") or "").strip()
                    album_title = normalize_name(str(matched_album_info.get("title") or album_info.get("albumTitle") or ""))
                    title = raw_title
                    if subtitle and album_title and album_title not in normalize_name(raw_title):
                        title = f"{album_title} {subtitle}".strip()
                    page_url = self._normalize_iqiyi_url(str(video.get("pageUrl") or "").strip())
                    if not title or not page_url:
                        continue
                    videos.append(
                        {
                            "itemTitle": title,
                            "itemLink": page_url,
                            "itemNumber": self._to_int(video.get("number")),
                            "tvId": self._to_int(video.get("qipuId")),
                            "albumId": matched_album_id or target_album_id,
                            "timeLength": self._mesh_duration_seconds(video.get("duration")),
                            "year": self._to_int(video.get("year")),
                            "subtitle": subtitle,
                        }
                    )
                if videos:
                    return videos
            if len(payloads) == 1:
                payloads.append(self._mesh_search_payload(query_name, include_site_filter=False))
        return []

    def _album_level_episode_candidate(
        self,
        album_info: dict,
        query_name: str,
        *,
        explicit_episode_query: bool,
        requested_episode: int | None,
    ) -> DanmakuSearchItem | None:
        if not explicit_episode_query or requested_episode != 1:
            return None
        title = str(album_info.get("title") or "").strip()
        url = self._normalize_iqiyi_url(str(album_info.get("pageUrl") or "").strip())
        tv_id = self._to_int(album_info.get("playQipuId"))
        album_id = self._to_int(album_info.get("qipuId") or album_info.get("albumId"))
        category_id = self._extract_category_id(album_info)
        if not title or not url or tv_id is None or album_id is None or category_id is None:
            return None
        candidate_name = f"{title} 第1集".strip()
        metadata = {
            "tv_id": tv_id,
            "album_id": album_id,
            "category_id": category_id,
            "duration_seconds": 0,
            "variety_year": self._to_int(album_info.get("year")) or 0,
        }
        return DanmakuSearchItem(
            provider=self.key,
            name=candidate_name,
            url=url,
            ratio=similarity_score(query_name, candidate_name),
            simi=similarity_score(query_name, candidate_name),
            duration_seconds=0,
            resolve_context=dict(metadata),
        )

    def _iter_mesh_album_infos(self, payload: dict) -> list[dict]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        templates = data.get("templates")
        if not isinstance(templates, list):
            return []
        albums: list[dict] = []
        for template in templates:
            if not isinstance(template, dict):
                continue
            album_candidates: list[dict] = []
            album_info = template.get("albumInfo")
            if isinstance(album_info, dict):
                album_candidates.append(album_info)
            intent_album_infos = template.get("intentAlbumInfos")
            if isinstance(intent_album_infos, list):
                album_candidates.extend(item for item in intent_album_infos if isinstance(item, dict))
            for album_candidate in album_candidates:
                site_id = str(album_candidate.get("siteId") or "").strip().lower()
                site_name = str(album_candidate.get("siteName") or "").strip()
                if site_id not in self._ALLOWED_SITE_IDS or site_name not in self._ALLOWED_SITE_NAMES:
                    continue
                albums.append(album_candidate)
        return albums

    def _expand_mesh_album_page_videos(self, album_info: dict) -> list[dict]:
        page_url = self._normalize_iqiyi_url(str(album_info.get("pageUrl") or "").strip())
        if not page_url:
            return []
        expanded = self._expand_album_videos(
            {
                "albumLink": page_url,
                "albumId": album_info.get("qipuId") or album_info.get("albumId"),
                "channel": album_info.get("channel"),
            }
        )
        videos: list[dict] = []
        for video in expanded:
            duration_seconds = self._to_int(video.get("timeLength")) or 0
            videos.append(
                {
                    "title": str(video.get("itemTitle") or "").strip(),
                    "subtitle": "",
                    "number": video.get("itemNumber"),
                    "qipuId": video.get("tvId"),
                    "pageUrl": video.get("itemLink"),
                    "duration": duration_seconds * 1000 if duration_seconds > 0 else 0,
                }
            )
        return videos

    def _should_expand_album_videos(self, videos: list[dict], album_info: dict) -> bool:
        item_total = self._to_int(album_info.get("itemTotalNumber"))
        album_link = str(album_info.get("albumLink") or "").strip()
        if item_total is None or item_total <= 0 or not album_link:
            return False
        if len(videos) < item_total:
            return True
        numbers = sorted(
            episode
            for video in videos
            if (episode := self._to_int(video.get("itemNumber") or video.get("order"))) is not None
        )
        if len(numbers) < item_total:
            return True
        return numbers != list(range(1, item_total + 1))

    def _expand_album_videos(self, album_info: dict) -> list[dict]:
        album_link = self._normalize_iqiyi_url(str(album_info.get("albumLink") or "").strip())
        if not album_link:
            return []
        url = album_link if "?" in album_link else f"{album_link}?jump=0"
        response = self._get(
            url,
            headers=dict(self._PAGE_HEADERS),
            follow_redirects=True,
            timeout=10.0,
        )
        element_match = re.search(
            r"<input\b[^>]*\bid=[\"']album-avlist-data[\"'][^>]*>",
            response.text,
            re.S | re.IGNORECASE,
        )
        if element_match is None:
            return []
        value_match = re.search(r"\bvalue=(['\"])(?P<payload>.*?)\1", element_match.group(0), re.S | re.IGNORECASE)
        if value_match is None:
            return []
        try:
            payload = json.loads(html.unescape(value_match.group("payload")))
        except json.JSONDecodeError:
            return []
        episodes = payload.get("epsodelist") or []
        if not episodes and payload.get("urlParam"):
            api_url = self._album_avlist_api_url(str(payload.get("urlParam") or ""))
            if api_url:
                api_response = self._get(
                    api_url,
                    headers=dict(self._PAGE_HEADERS),
                    follow_redirects=True,
                    timeout=10.0,
                )
                try:
                    api_payload = api_response.json()
                except Exception:
                    api_payload = {}
                episodes = (api_payload.get("data") or {}).get("epsodelist") or []
        videos: list[dict] = []
        for episode in episodes:
            title = str(episode.get("shortTitle") or episode.get("subtitle") or "").strip()
            url = self._normalize_iqiyi_url(str(episode.get("playUrl") or "").strip())
            if not title or not url:
                continue
            videos.append(
                {
                    "itemTitle": title,
                    "itemLink": url,
                    "itemNumber": self._to_int(episode.get("order")),
                    "tvId": episode.get("tvId"),
                    "albumId": payload.get("albumId") or album_info.get("albumId"),
                    "timeLength": self._parse_duration_seconds(episode.get("duration")),
                }
            )
        return videos

    def _album_avlist_api_url(self, url_param: str) -> str:
        value = str(url_param or "").strip()
        if not value:
            return ""
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("/"):
            return f"https://www.iqiyi.com{value}"
        return f"https://www.iqiyi.com/{value}"

    def _video_metadata(self, video: dict, album_info: dict) -> dict[str, str | int | None]:
        return {
            "tv_id": self._to_int(video.get("tvId") or video.get("qipu_id")),
            "album_id": self._to_int(video.get("albumId") or album_info.get("albumId")),
            "category_id": self._extract_category_id(album_info),
            "duration_seconds": self._to_int(video.get("timeLength")),
            "variety_year": self._to_int(video.get("year")),
        }

    def _mesh_cache_key(self, query_name: str, album_info: dict) -> tuple[str, int | None, str]:
        return (
            normalize_name(query_name),
            self._to_int(album_info.get("albumId")),
            normalize_name(str(album_info.get("albumTitle") or "")),
        )

    def _merge_search_metadata(
        self,
        base: dict[str, str | int | None] | None,
        incoming: dict[str, str | int | None],
    ) -> dict[str, str | int | None]:
        merged = dict(base or {})
        for key, value in incoming.items():
            if value in ("", None, 0):
                continue
            merged[key] = value
        return merged

    def _search_item_rank(self, item: DanmakuSearchItem) -> tuple[float, float, int, int, int]:
        context_score = sum(1 for value in item.resolve_context.values() if value not in ("", None, 0))
        return (
            item.ratio,
            item.simi,
            int(item.duration_seconds > 0),
            context_score,
            len(item.name),
        )

    def _merge_search_items(
        self,
        primary: list[DanmakuSearchItem],
        secondary: list[DanmakuSearchItem],
    ) -> list[DanmakuSearchItem]:
        results_by_url: dict[str, DanmakuSearchItem] = {}
        for item in [*primary, *secondary]:
            existing = results_by_url.get(item.url)
            if existing is None or self._search_item_rank(item) > self._search_item_rank(existing):
                results_by_url[item.url] = item
        return list(results_by_url.values())

    def _should_drop_search_item(self, item: dict) -> bool:
        album_info = item.get("albumDocInfo") or {}
        site_id = str(album_info.get("siteId") or "").strip().lower()
        site_name = str(album_info.get("siteName") or "").strip()
        if site_id not in self._ALLOWED_SITE_IDS:
            return True
        if site_name not in self._ALLOWED_SITE_NAMES:
            return True
        raw_score = album_info.get("douban_score")
        try:
            score = float(raw_score) if raw_score not in ("", None) else None
        except (TypeError, ValueError):
            score = None
        if score is not None and score < 2:
            return True
        channel = str(album_info.get("channel") or "")
        if any(keyword in channel for keyword in self._DROP_CHANNEL_KEYWORDS):
            return True
        if not album_info.get("itemTotalNumber") and not (item.get("videoinfos") or album_info.get("videoinfos")):
            return True
        title = str(album_info.get("albumTitle") or "")
        return any(keyword in title for keyword in self._DROP_TITLE_KEYWORDS)

    def _extract_page_info(self, html_text: str) -> dict:
        match = re.search(r"window\.Q\.PageInfo\.playPageInfo\s*=\s*(\{.*?\})\s*;", html_text, re.S)
        if match is None:
            raise DanmakuResolveError("爱奇艺页面缺少 playPageInfo")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise DanmakuResolveError("爱奇艺页面 playPageInfo 解析失败") from exc

    def _try_extract_page_info(self, html_text: str) -> dict:
        try:
            return self._extract_page_info(html_text)
        except DanmakuResolveError:
            return {}

    def _resolve_danmaku_fields(self, page_info: dict, page_url: str) -> dict[str, str | int | None]:
        play_page_data = page_info.get("playPageData")
        if not isinstance(play_page_data, dict):
            play_page_data = {}
        cached = self._metadata_by_url.get(page_url) or self._metadata_by_url.get(self._swap_scheme(page_url))
        tv_id = str(page_info.get("tvId") or play_page_data.get("tvId") or (cached or {}).get("tv_id") or "").strip()
        return {
            "tv_id": tv_id,
            "album_id": page_info.get("albumId") or play_page_data.get("albumId") or (cached or {}).get("album_id"),
            "category_id": page_info.get("cid") or play_page_data.get("cid") or (cached or {}).get("category_id"),
        }

    def _remember_metadata(self, page_url: str, metadata: dict[str, str | int | None]) -> None:
        self._metadata_by_url[page_url] = dict(metadata)
        alternate = self._swap_scheme(page_url)
        if alternate != page_url:
            self._metadata_by_url[alternate] = dict(metadata)

    def _swap_scheme(self, page_url: str) -> str:
        if page_url.startswith("http://"):
            return "https://" + page_url[len("http://") :]
        if page_url.startswith("https://"):
            return "http://" + page_url[len("https://") :]
        return page_url

    def _normalize_iqiyi_url(self, page_url: str) -> str:
        value = str(page_url or "").strip()
        if value.startswith("http://") and "iqiyi.com" in value:
            return "https://" + value[len("http://") :]
        return value

    def _extract_category_id(self, album_info: dict) -> int | None:
        channel = str(album_info.get("channel") or "").strip()
        if not channel:
            return None
        tail = channel.rsplit(",", 1)[-1].strip()
        return self._to_int(tail)

    def _to_int(self, value) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _resolve_duration_seconds(self, page_info: dict, cached_metadata: dict[str, str | int | None] | None) -> int:
        duration = self._parse_duration_seconds(page_info.get("duration"))
        if duration > 0:
            return duration
        cached_duration = self._to_int((cached_metadata or {}).get("duration_seconds"))
        if cached_duration is not None and cached_duration > 0:
            return cached_duration
        return 0

    def _segment_url(self, tvid: str, page_index: int) -> str:
        return f"https://cmts.iqiyi.com/bullet/{tvid[-4:-2]}/{tvid[-2:]}/{tvid}_300_{page_index}.z"

    def _parse_duration_seconds(self, raw_duration) -> int:
        text = str(raw_duration or "").strip()
        if not text:
            return 0
        parts = text.split(":")
        try:
            values = [int(part) for part in parts]
        except ValueError:
            return 0
        if len(values) == 3:
            hours, minutes, seconds = values
            return hours * 3600 + minutes * 60 + seconds
        if len(values) == 2:
            minutes, seconds = values
            return minutes * 60 + seconds
        if len(values) == 1:
            return values[0]
        return 0

    def _mesh_duration_seconds(self, raw_duration) -> int:
        duration = self._to_int(raw_duration)
        if duration is None or duration <= 0:
            return 0
        if duration >= 1000:
            return int(round(duration / 1000.0))
        return duration

    def _parse_segment_records(self, xml_text: str, duration_seconds: int) -> list[DanmakuRecord]:
        sanitized_xml = self._sanitize_segment_xml(xml_text)
        try:
            root = ET.fromstring(sanitized_xml)
        except ET.ParseError as exc:
            raise DanmakuResolveError("爱奇艺弹幕 XML 解析失败") from exc
        records: list[DanmakuRecord] = []
        for bullet in root.findall(".//bulletInfo"):
            content = (bullet.findtext("content") or "").strip()
            if not content:
                continue
            time_offset = self._parse_show_time_seconds(bullet.findtext("showTime"), duration_seconds)
            if time_offset is None:
                continue
            color = self._normalize_color(bullet.findtext("color"))
            records.append(DanmakuRecord(time_offset=time_offset, pos=1, color=color, content=content))
        return records

    def _sanitize_segment_xml(self, xml_text: str) -> str:
        sanitized = re.sub(r"&#(x?[0-9A-Fa-f]+);", self._sanitize_numeric_character_reference, xml_text)
        return "".join(ch for ch in sanitized if self._is_valid_xml_char(ord(ch)))

    def _sanitize_numeric_character_reference(self, match: re.Match[str]) -> str:
        raw_value = match.group(1)
        base = 16 if raw_value.lower().startswith("x") else 10
        value_text = raw_value[1:] if base == 16 else raw_value
        try:
            codepoint = int(value_text, base)
        except ValueError:
            return ""
        if not self._is_valid_xml_char(codepoint):
            return ""
        return match.group(0)

    def _is_valid_xml_char(self, codepoint: int) -> bool:
        return (
            codepoint in (0x9, 0xA, 0xD)
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )

    def _parse_show_time_seconds(self, raw_show_time, duration_seconds: int) -> float | None:
        try:
            value = float(str(raw_show_time or "").strip())
        except ValueError:
            return None
        if value < 0:
            return None
        if duration_seconds > 0:
            if value > duration_seconds + 60:
                return round(value / 1000.0, 3)
            return round(value, 3)
        if value >= 1000:
            return round(value / 1000.0, 3)
        return round(value, 3)

    def _normalize_color(self, raw_color) -> str:
        text = str(raw_color or "").strip()
        if not text:
            return "16777215"
        try:
            return str(int(text))
        except ValueError:
            normalized = text.lower().removeprefix("0x").lstrip("#")
            try:
                return str(int(normalized, 16))
            except ValueError:
                return "16777215"
