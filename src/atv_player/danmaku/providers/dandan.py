from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from urllib.parse import urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.providers._concurrency import iter_bounded_settled
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "atv-player/0.1.0",
}
_MAX_SERIES = 5
_MAX_EPISODES_PER_SERIES = 200


class DandanDanmakuProvider:
    """弹弹Play 弹幕源，指向一台 dandanplay 协议兼容的自建服务器。

    服务器地址（可含 token 路径段，如 ``http://host:9321/87654321``）由
    ``base_url_loader`` 运行时提供。地址留空时该源视为关闭：不参与搜索、
    不解析任何地址。
    """

    key = "dandan"

    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        base_url_loader: Callable[[], str] | None = None,
    ) -> None:
        self._get = get
        self._base_url_loader = base_url_loader or (lambda: "")

    def _base(self) -> str:
        return (self._base_url_loader() or "").strip().rstrip("/")

    def supports(self, page_url: str) -> bool:
        if not self._base():
            return False
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
        if not self._base():
            return []
        requested_episode = extract_episode_number(original_name or name)
        try:
            payload = self._request_json("/v2/search/anime", params={"keyword": name})
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuSearchError(f"弹弹Play服务器连接失败: {exc}") from exc
        animes = payload.get("animes") if isinstance(payload, dict) else None
        if not isinstance(animes, list):
            return []
        items: list[DanmakuSearchItem] = []
        for batch in iter_bounded_settled(
            animes[:_MAX_SERIES],
            lambda anime: self._expand_anime(name, anime),
        ):
            for settled in batch:
                if settled.error is None and settled.value is not None:
                    items.extend(settled.value)
        return self._prefer_requested_episode(items, requested_episode)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        if not self._base():
            raise DanmakuResolveError("未配置弹弹Play服务器地址")
        episode_id = self._episode_id(page_url)
        try:
            payload = self._request_json(
                f"/v2/comment/{episode_id}",
                params={"from": "0", "withRelated": "true", "chConvert": "0"},
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuResolveError(f"弹弹Play服务器连接失败: {exc}") from exc
        comments = payload.get("comments") if isinstance(payload, dict) else None
        if not isinstance(comments, list):
            raise DanmakuResolveError("弹弹Play弹幕响应解析失败")
        return [record for row in comments if (record := self._record(row)) is not None]

    def _request_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> object:
        response = self._get(
            f"{self._base()}/api{path}",
            params=params,
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

    def _expand_anime(
        self,
        query_name: str,
        anime: object,
    ) -> list[DanmakuSearchItem]:
        if not isinstance(anime, dict):
            return []
        anime_id = str(anime.get("animeId") or "").strip()
        title = str(anime.get("animeTitle") or "").strip()
        if not anime_id or not title or should_filter_name(query_name, title):
            return []
        details = self._request_json(f"/v2/bangumi/{anime_id}")
        bangumi = details.get("bangumi") if isinstance(details, dict) else None
        episodes = bangumi.get("episodes") if isinstance(bangumi, dict) else None
        if not isinstance(episodes, list):
            return []
        return [
            item
            for episode in episodes[:_MAX_EPISODES_PER_SERIES]
            if (item := self._episode_item(title, anime_id, episode)) is not None
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
            raw_time = float(parts[0])
            mode = int(parts[1])
            color = int(parts[2])
        except (TypeError, ValueError):
            return None
        if not isfinite(raw_time):
            return None
        return DanmakuRecord(
            time_offset=max(0.0, raw_time),
            pos=mode if mode in {1, 4, 5} else 1,
            color=str(color if 0 <= color <= 0xFFFFFF else 0xFFFFFF),
            content=content,
        )


def probe_dandan_server(
    get: Callable[..., httpx.Response] = httpx.get,
    base_url: str = "",
    timeout: float = 5.0,
) -> tuple[bool, str]:
    """探测一台 dandanplay 兼容服务器是否可用，供设置页"测试连接"使用。

    打真实 search 端点（而非免 token 的 ``/api/config``），可同时校验地址与
    token。返回 ``(是否可用, 提示信息)``，永不向调用方抛异常。
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return (False, "未填写服务器地址")
    try:
        response = get(
            f"{base}/api/v2/search/anime",
            params={"keyword": "test"},
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return (False, f"连接失败: {exc}")
    if response.status_code >= 400:
        return (False, f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - 探测绝不能向 UI 抛异常
        return (False, "响应非 JSON")
    if not isinstance(payload, dict) or not isinstance(payload.get("animes"), list):
        return (False, "响应格式不符")
    return (True, "连接正常")
