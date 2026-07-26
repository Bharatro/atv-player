from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote, urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_BASE_URL = "https://api.danmaku.weeblify.app/ddp/v1"
_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "atv-player/0.1.0",
}
_MAX_SERIES = 5
_MAX_EPISODES_PER_SERIES = 200


class DandanDanmakuProvider:
    key = "dandan"

    def __init__(self, get: Callable[..., httpx.Response] = httpx.get) -> None:
        self._get = get

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
        try:
            payload = self._request_json(f"/v2/search/anime?keyword={quote(name)}")
            animes = payload.get("animes") if isinstance(payload, dict) else None
            if not isinstance(animes, list):
                return []
            items: list[DanmakuSearchItem] = []
            for anime in animes[:_MAX_SERIES]:
                if not isinstance(anime, dict):
                    continue
                anime_id = str(anime.get("animeId") or "").strip()
                title = str(anime.get("animeTitle") or "").strip()
                if not anime_id or not title or should_filter_name(name, title):
                    continue
                details = self._request_json(f"/v2/bangumi/{anime_id}")
                bangumi = details.get("bangumi") if isinstance(details, dict) else None
                episodes = (
                    bangumi.get("episodes") if isinstance(bangumi, dict) else None
                )
                if not isinstance(episodes, list):
                    continue
                for episode in episodes[:_MAX_EPISODES_PER_SERIES]:
                    item = self._episode_item(title, anime_id, episode)
                    if item is not None:
                        items.append(item)
        except (httpx.HTTPError, TypeError, ValueError):
            return []
        return self._prefer_requested_episode(items, requested_episode)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        episode_id = self._episode_id(page_url)
        try:
            payload = self._request_json(
                f"/v2/comment/{episode_id}?from=0&withRelated=true&chConvert=0"
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuResolveError("弹弹Play弹幕获取失败") from exc
        comments = payload.get("comments") if isinstance(payload, dict) else None
        if not isinstance(comments, list):
            raise DanmakuResolveError("弹弹Play弹幕响应解析失败")
        return [record for row in comments if (record := self._record(row)) is not None]

    def _request_json(self, path: str) -> object:
        response = self._get(
            _BASE_URL,
            params={"path": path},
            headers=_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise httpx.HTTPError(f"DandanPlay returned {response.status_code}")
        return response.json()

    def _episode_item(
        self,
        title: str,
        anime_id: str,
        episode: object,
    ) -> DanmakuSearchItem | None:
        if not isinstance(episode, dict):
            return None
        episode_id = str(episode.get("episodeId") or "").strip()
        episode_number = str(episode.get("episodeNumber") or "").strip()
        if not episode_id or not episode_number:
            return None
        episode_title = str(episode.get("episodeTitle") or "").strip()
        candidate_name = f"{title} 第{episode_number}集 {episode_title}".strip()
        return DanmakuSearchItem(
            provider=self.key,
            name=candidate_name,
            url=f"dandan://episode/{episode_id}",
            resolve_context={"anime_id": anime_id, "episode_id": episode_id},
        )

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
            raise DanmakuResolveError("弹弹Play弹幕地址无效")
        return urlparse(page_url).path.strip("/")

    def _record(self, row: object) -> DanmakuRecord | None:
        if not isinstance(row, dict):
            return None
        content = str(row.get("m") or "").strip()
        parts = str(row.get("p") or "").split(",")
        if not content or len(parts) < 3:
            return None
        try:
            time_offset = max(0.0, float(parts[0]))
            mode = int(parts[1])
            color = int(parts[2])
        except (TypeError, ValueError):
            return None
        return DanmakuRecord(
            time_offset=time_offset,
            pos=mode if mode in {1, 4, 5} else 1,
            color=str(color if 0 <= color <= 0xFFFFFF else 0xFFFFFF),
            content=content,
        )
