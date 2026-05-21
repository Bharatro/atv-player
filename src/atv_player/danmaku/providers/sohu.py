from __future__ import annotations

import re

import httpx

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, extract_variety_issue_key, normalize_name


class SohuDanmakuProvider:
    key = "sohu"
    _SEARCH_URL = "https://m.so.tv.sohu.com/search/pc/keyword"
    _PLAYLIST_URL = "https://pl.hd.sohu.com/videolist"
    _NOISE_KEYWORDS = ("预告", "花絮", "片段", "特辑", "采访", "速看", "解说")
    _POSITION_MAP = {1: 1, 4: 5, 5: 4}

    def __init__(self, get=httpx.get) -> None:
        self._get = get
        self._resolve_context_by_url: dict[str, dict[str, str | int | None]] = {}

    def supports(self, page_url: str) -> bool:
        return "sohu.com" in page_url

    def prime_resolve_context(self, page_url: str, resolve_context: dict[str, str | int | None]) -> None:
        self._resolve_context_by_url[page_url] = dict(resolve_context)

    def search(self, name: str, original_name: str | None = None) -> list[DanmakuSearchItem]:
        response = self._get(
            self._SEARCH_URL,
            params={"key": name, "type": "1", "page": "1", "page_size": "20"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://so.tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("搜狐弹幕搜索结果解析失败") from exc
        items = (payload.get("data") or {}).get("items")
        if not isinstance(items, list):
            raise DanmakuSearchError("搜狐弹幕搜索结果解析失败")
        return self._expand_search_items(items, query_name=name, original_name=original_name or name)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        context = dict(self._resolve_context_by_url.get(page_url) or {})
        aid = str(context.get("aid") or "").strip()
        vid = str(context.get("vid") or "").strip()
        duration_seconds = int(context.get("duration_seconds") or 0)
        if not aid or not vid:
            page_aid, page_vid = self._extract_ids_from_page(page_url)
            aid = aid or page_aid
            vid = vid or page_vid
        if not aid or not vid:
            raise DanmakuResolveError("搜狐页面缺少 aid 或 vid")
        duration_seconds = duration_seconds or self._duration_for_video(aid, vid)
        records = self._fetch_danmaku_records(aid, vid, duration_seconds or 300)
        if not records:
            raise DanmakuResolveError("搜狐弹幕分段解析失败")
        return sorted(records, key=lambda record: (record.time_offset, record.content))

    def _expand_search_items(self, raw_items: list[dict], *, query_name: str, original_name: str) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name)
        requested_issue_key = extract_variety_issue_key(normalize_name(original_name))
        candidates: list[DanmakuSearchItem] = []
        for raw in raw_items:
            album = self._normalize_album(raw)
            if album is None:
                continue
            candidates.extend(
                self._expand_album(
                    album,
                    requested_episode=requested_episode,
                    requested_issue_key=requested_issue_key,
                )
            )
        return candidates

    def _normalize_album(self, raw: dict) -> dict[str, str | int] | None:
        aid = str(raw.get("aid") or "").strip()
        title = str(raw.get("album_name") or "").replace("<<<", "").replace(">>>", "").strip()
        if not aid or not title:
            return None
        if int(raw.get("is_trailer") or 0) == 1:
            return None
        corner_mark = raw.get("corner_mark") or {}
        if str(corner_mark.get("text") or "").strip() == "预告":
            return None
        if any(keyword in title for keyword in self._NOISE_KEYWORDS):
            return None
        return {
            "aid": aid,
            "title": title,
            "year": int(raw.get("year") or 0),
            "category_name": self._category_name(raw),
            "videos": list(raw.get("videos") or []),
        }

    def _category_name(self, raw: dict) -> str:
        for meta in raw.get("meta") or []:
            text = str((meta or {}).get("txt") or "")
            if "|" not in text:
                continue
            parts = [part.strip() for part in text.split("|")]
            if not parts:
                continue
            first = parts[0]
            if "别名" in first and len(parts) > 1:
                return parts[1]
            return first
        return ""

    def _expand_album(
        self,
        album: dict[str, str | int],
        *,
        requested_episode: int | None,
        requested_issue_key: str | None,
    ) -> list[DanmakuSearchItem]:
        embedded_videos = album.get("videos")
        videos = embedded_videos if isinstance(embedded_videos, list) and embedded_videos else self._playlist_videos(str(album["aid"]))
        if not videos:
            return [self._album_fallback_item(album)]
        category_name = str(album.get("category_name") or "")
        if "电影" in category_name:
            best = self._pick_movie_video(str(album["title"]), videos)
            if best is None:
                return [self._album_fallback_item(album)]
            item = self._video_to_item(album, best)
            return [item] if item is not None else [self._album_fallback_item(album)]
        items = [item for item in (self._video_to_item(album, video) for video in videos) if item is not None]
        if not items:
            return [self._album_fallback_item(album)]
        if requested_issue_key:
            matched = [item for item in items if item.resolve_context.get("variety_year") == requested_issue_key]
            if matched:
                return matched
        if requested_episode is not None:
            matched = [item for item in items if extract_episode_number(item.name) == requested_episode]
            if matched:
                return matched
            return items[:3]
        return items

    def _playlist_videos(self, aid: str) -> list[dict]:
        response = self._get(
            self._PLAYLIST_URL,
            params={"playlistid": aid, "api_key": "f351515304020cad28c92f70f002261c"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("搜狐播放列表解析失败") from exc
        videos = payload.get("videos")
        return videos if isinstance(videos, list) else []

    def _extract_ids_from_page(self, page_url: str) -> tuple[str, str]:
        response = self._get(
            page_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        aid_match = re.search(r'id="aid"[^>]*value=["\'](\d+)["\']', response.text)
        playlist_match = re.search(r'playlistId="(\d+)"', response.text)
        vid_match = re.search(r'vid="(\d+)"', response.text)
        return (
            aid_match.group(1) if aid_match else (playlist_match.group(1) if playlist_match else ""),
            vid_match.group(1) if vid_match else "",
        )

    def _duration_for_video(self, aid: str, vid: str) -> int:
        for video in self._playlist_videos(aid):
            if str(video.get("vid") or "").strip() != vid:
                continue
            return int(video.get("playLength") or 0)
        return 0

    def _fetch_danmaku_records(self, aid: str, vid: str, duration_seconds: int) -> list[DanmakuRecord]:
        records: list[DanmakuRecord] = []
        failures = 0
        seen: set[tuple[float, str]] = set()
        for start in range(0, max(duration_seconds, 1), 300):
            response = self._get(
                "https://api.danmu.tv.sohu.com/dmh5/dmListAll",
                params={
                    "act": "dmlist_v2",
                    "vid": vid,
                    "aid": aid,
                    "pct": "2",
                    "time_begin": start,
                    "time_end": min(start + 300, duration_seconds),
                    "dct": "1",
                    "request_from": "h5_js",
                },
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
                follow_redirects=True,
                timeout=10.0,
            )
            try:
                payload = response.json()
            except Exception:
                failures += 1
                continue
            for comment in ((payload.get("info") or {}).get("comments") or []):
                record = self._comment_to_record(comment)
                if record is None:
                    continue
                key = (record.time_offset, record.content)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
        if failures > 0 and not records:
            raise DanmakuResolveError("搜狐弹幕分段解析失败")
        return records

    def _pick_movie_video(self, title: str, videos: list[dict]) -> dict | None:
        candidates = [video for video in videos if not self._is_noise_title(str(video.get("video_name") or ""))]
        if not candidates:
            return None
        normalized_title = normalize_name(title)
        return max(
            candidates,
            key=lambda video: (
                int(normalize_name(str(video.get("video_name") or "")) == normalized_title),
                int(video.get("playLength") or 0),
            ),
        )

    def _video_to_item(self, album: dict[str, str | int], video: dict) -> DanmakuSearchItem | None:
        vid = str(video.get("vid") or "").strip()
        url = str(
            video.get("url_html5")
            or video.get("pageUrl")
            or video.get("page_url")
            or video.get("url")
            or ""
        ).strip()
        if not vid or not url:
            return None
        album_title = self._normalize_display_title(str(album["title"]))
        video_name = self._normalize_display_title(str(video.get("video_name") or "").strip())
        candidate_name = album_title
        if video_name and video_name != album_title:
            if video_name.startswith(album_title):
                candidate_name = video_name
            else:
                candidate_name = f"{album_title} {video_name}".strip()
        candidate_name = self._space_episode_suffix(candidate_name)
        duration_seconds = int(video.get("playLength") or 0)
        resolve_context: dict[str, str | int | None] = {
            "aid": str(album["aid"]),
            "vid": vid,
            "duration_seconds": duration_seconds,
            "category_name": str(album.get("category_name") or ""),
            "year": int(album.get("year") or 0),
            "expanded_from_playlist": 1,
        }
        issue_key = extract_variety_issue_key(video_name)
        if issue_key is not None:
            resolve_context["variety_year"] = issue_key
        item = DanmakuSearchItem(
            provider=self.key,
            name=candidate_name,
            url=url.replace("http://", "https://"),
            duration_seconds=duration_seconds,
            resolve_context=resolve_context,
        )
        self._resolve_context_by_url[item.url] = dict(resolve_context)
        return item

    def _album_fallback_item(self, album: dict[str, str | int]) -> DanmakuSearchItem:
        url = f"https://tv.sohu.com/item/{album['aid']}.html"
        resolve_context: dict[str, str | int | None] = {
            "aid": str(album["aid"]),
            "vid": "",
            "duration_seconds": 0,
            "category_name": str(album.get("category_name") or ""),
            "year": int(album.get("year") or 0),
            "expanded_from_playlist": 0,
        }
        item = DanmakuSearchItem(
            provider=self.key,
            name=self._normalize_display_title(str(album["title"])),
            url=url,
            duration_seconds=0,
            resolve_context=resolve_context,
        )
        self._resolve_context_by_url[item.url] = dict(resolve_context)
        return item

    def _is_noise_title(self, title: str) -> bool:
        return any(keyword in title for keyword in self._NOISE_KEYWORDS)

    def _normalize_display_title(self, title: str) -> str:
        value = str(title or "").replace("<<<", "").replace(">>>", "").strip()
        if not value:
            return ""
        value = re.sub(r"[（(][^()（）]*season\s*1[^()（）]*[)）]", "", value, flags=re.IGNORECASE)
        value = re.sub(r"[（(][A-Za-z0-9 .:'_-]+[)）]", "", value)
        value = re.sub(r"(第[一1]季|season\s*1)", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _space_episode_suffix(self, title: str) -> str:
        return re.sub(r"(?<!\s)(第\s*[0-9零一二两三四五六七八九十百]+\s*[集话期])$", r" \1", title).strip()

    def _comment_to_record(self, comment: dict) -> DanmakuRecord | None:
        content = str(comment.get("c") or "").strip()
        if not content:
            return None
        color_text = str(((comment.get("t") or {}).get("c")) or "#ffffff").strip().lstrip("#")
        try:
            color = str(int(color_text, 16))
        except ValueError:
            color = "16777215"
        position = int(((comment.get("t") or {}).get("p")) or 1)
        return DanmakuRecord(
            time_offset=round(float(comment.get("v") or 0), 3),
            pos=self._POSITION_MAP.get(position, 1),
            color=color,
            content=content,
        )
