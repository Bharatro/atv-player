from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx
from opencc import OpenCC

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_SEARCH_URL = "https://api.gamer.com.tw/mobile_app/anime/v1/search.php"
_DETAIL_URL = "https://api.gamer.com.tw/anime/v1/video.php"
_DANMAKU_URL = "https://api.gamer.com.tw/anime/v1/danmu.php"
_USER_AGENT = (
    "Anime/2.29.2 (7N5749MM3F.tw.com.gamer.anime; build:972; iOS 26.0.0) "
    "Alamofire/5.6.4"
)
_HEADERS = {"Accept": "application/json", "User-Agent": _USER_AGENT}
_CONVERTER = OpenCC("s2twp")
_MAX_SERIES = 5


def _to_traditional(value: str) -> str:
    return _CONVERTER.convert(value)


class BahamutDanmakuProvider:
    key = "bahamut"

    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        traditionalize: Callable[[str], str] = _to_traditional,
    ) -> None:
        self._get = get
        self._traditionalize = traditionalize

    def supports(self, page_url: str) -> bool:
        parsed = urlparse(page_url)
        return (
            parsed.scheme == self.key
            and parsed.netloc == "episode"
            and bool(parsed.path.strip("/"))
        )

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name or name)
        traditional_name = self._traditionalize(name)
        try:
            search_payload = self._get_json(
                _SEARCH_URL,
                params={"kw": traditional_name},
            )
            animes = (
                search_payload.get("anime")
                if isinstance(search_payload, dict)
                else None
            )
            if not isinstance(animes, list):
                return []
            items: list[DanmakuSearchItem] = []
            for anime in animes[:_MAX_SERIES]:
                if not isinstance(anime, dict):
                    continue
                source_title = str(anime.get("title") or "").strip()
                video_sn = str(
                    anime.get("video_sn") or anime.get("videoSn") or ""
                ).strip()
                if not source_title or not video_sn:
                    continue
                if should_filter_name(traditional_name, source_title):
                    continue
                detail_payload = self._get_json(
                    _DETAIL_URL,
                    params={"videoSn": video_sn},
                )
                data = (
                    detail_payload.get("data")
                    if isinstance(detail_payload, dict)
                    else None
                )
                series = data.get("anime") if isinstance(data, dict) else None
                for episode in self._episodes(series):
                    episode_no = str(episode.get("episode") or "").strip()
                    episode_video_sn = str(episode.get("videoSn") or "").strip()
                    if not episode_no or not episode_video_sn:
                        continue
                    items.append(
                        DanmakuSearchItem(
                            provider=self.key,
                            name=f"{name} 第{episode_no}集",
                            url=f"bahamut://episode/{episode_video_sn}",
                            resolve_context={
                                "series_video_sn": video_sn,
                                "source_title": source_title,
                            },
                        )
                    )
        except (httpx.HTTPError, TypeError, ValueError):
            return []
        return self._prefer_requested_episode(items, requested_episode)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        video_sn = self._episode_id(page_url)
        try:
            payload = self._get_json(
                _DANMAKU_URL,
                params={"geo": "TW,HK", "videoSn": video_sn},
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuResolveError("巴哈姆特弹幕获取失败") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        comments = data.get("danmu") if isinstance(data, dict) else None
        if not isinstance(comments, list):
            raise DanmakuResolveError("巴哈姆特弹幕响应解析失败")
        return [
            record
            for row in comments
            if (record := self._record(row)) is not None
        ]

    def _get_json(self, url: str, *, params: dict[str, str]) -> object:
        response = self._get(
            url,
            params=params,
            headers=_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise httpx.HTTPError(f"Bahamut returned {response.status_code}")
        return response.json()

    def _episodes(self, series: object) -> list[dict]:
        if not isinstance(series, dict):
            return []
        groups = series.get("episodes")
        if isinstance(groups, list):
            return [item for item in groups if isinstance(item, dict)]
        if not isinstance(groups, dict):
            return []
        return [
            item
            for group in groups.values()
            if isinstance(group, list)
            for item in group
            if isinstance(item, dict)
        ]

    def _prefer_requested_episode(
        self,
        items: list[DanmakuSearchItem],
        requested_episode: int | None,
    ) -> list[DanmakuSearchItem]:
        if requested_episode is None:
            return items
        matched = [
            item
            for item in items
            if extract_episode_number(item.name) == requested_episode
        ]
        return matched if matched else items[:3]

    def _episode_id(self, page_url: str) -> str:
        if not self.supports(page_url):
            raise DanmakuResolveError("巴哈姆特弹幕地址无效")
        return urlparse(page_url).path.strip("/")

    def _record(self, row: object) -> DanmakuRecord | None:
        if not isinstance(row, dict):
            return None
        content = str(row.get("text") or "").strip()
        if not content:
            return None
        try:
            time_offset = max(0.0, float(row.get("time")) / 10.0)
        except (TypeError, ValueError):
            return None
        position = {0: 1, 1: 5, 2: 4}.get(row.get("position"), 1)
        color_text = str(row.get("color") or "").strip().lstrip("#")
        try:
            color = int(color_text, 16)
        except ValueError:
            color = 0xFFFFFF
        return DanmakuRecord(
            time_offset=time_offset,
            pos=position,
            color=str(color if 0 <= color <= 0xFFFFFF else 0xFFFFFF),
            content=content,
        )
