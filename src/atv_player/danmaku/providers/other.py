from __future__ import annotations

import httpx

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem

__all__ = ["OtherDanmakuProvider"]


class OtherDanmakuProvider:
    """Third-party danmaku fallback source.

    Used as the last tier of the acquisition chain: when builtin providers and
    douban discovery both miss, and the user's reg_src is a real play-page URL,
    this provider asks a third-party danmaku service (default dmku.hls.one) for
    danmaku by URL. Not added to provider_order — only resolves when explicitly
    selected, so it never pollutes normal search/ranking.
    """

    key = "other"

    def __init__(self, get=httpx.get, server: str = "https://dmku.hls.one/") -> None:
        self._get = get
        self._server = server

    def supports(self, page_url: str) -> bool:
        return True

    def search(self, name: str, original_name: str | None = None) -> list[DanmakuSearchItem]:
        return []

    def expand_page_url(self, page_url: str, query_name: str) -> list[DanmakuSearchItem]:
        return []

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        try:
            response = self._get(
                self._server,
                params={"ac": "dm", "url": page_url},
                timeout=10.0,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        if not isinstance(payload, dict):
            return []
        records: list[DanmakuRecord] = []
        for entry in payload.get("danmuku") or []:
            if not isinstance(entry, list) or len(entry) < 5:
                continue
            try:
                time_offset = max(0.0, float(entry[0]))
            except (TypeError, ValueError):
                continue
            content = str(entry[4] or "").strip()
            if not content:
                continue
            records.append(
                DanmakuRecord(
                    time_offset=time_offset,
                    pos=self._mode_to_pos(entry[1]),
                    color=str(self._color_to_int(entry[2])),
                    content=content,
                )
            )
        return records

    def _mode_to_pos(self, value: object) -> int:
        normalized = str(value or "").strip().lower()
        if normalized == "top":
            return 5
        if normalized == "bottom":
            return 4
        return 1

    def _color_to_int(self, value: object) -> int:
        text = str(value or "").strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        try:
            return int(text, 16)
        except ValueError:
            return 16777215
