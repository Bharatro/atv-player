from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from atv_player.heat.models import HeatEvent, HeatMediaSummary, HeatRecommendation

HEAT_API_BASE_URL = "https://v.har01d.cn/api/v1/heat"
_REDACTED_CONTEXT_KEYS = {
    "url",
    "play_url",
    "episode_url",
    "source_url",
    "headers",
    "cookie",
    "cookies",
    "token",
    "auth",
    "password",
    "config",
}
logger = logging.getLogger(__name__)


def _clean_context(context: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in context.items():
        normalized = str(key or "").strip()
        if not normalized or normalized.lower() in _REDACTED_CONTEXT_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[normalized] = value
    return cleaned


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class HeatService:
    def __init__(
        self,
        *,
        base_url: str = HEAT_API_BASE_URL,
        http_client: httpx.Client | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def record_event(self, event: HeatEvent) -> bool:
        payload: dict[str, object] = {
            "event_id": event.event_id,
            "installation_id": event.installation_id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
            "client": event.client.to_payload(),
        }
        if event.media is not None:
            payload["media"] = event.media.to_payload()
        context = _clean_context(event.context)
        if context:
            payload["context"] = context
        try:
            response = self._client.post(f"{self._base_url}/events", json=payload)
            return 200 <= response.status_code < 300
        except Exception as exc:
            logger.debug("Heat event delivery failed: %s", exc)
            return False

    def load_recommendations(self, *, limit: int = 24) -> list[HeatRecommendation]:
        try:
            response = self._client.get(
                f"{self._base_url}/recommendations",
                params={"limit": int(limit)},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug("Heat recommendations load failed: %s", exc)
            return []
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [
            item
            for item in (_recommendation_from_payload(raw) for raw in items)
            if item is not None
        ]

    def load_media_heat(self, media_key: str) -> HeatMediaSummary | None:
        normalized = str(media_key or "").strip()
        if not normalized:
            return None
        try:
            response = self._client.get(
                f"{self._base_url}/media/{quote(normalized, safe='')}"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug("Heat media summary load failed: %s", exc)
            return None
        return _summary_from_payload(payload)


def _recommendation_from_payload(payload: object) -> HeatRecommendation | None:
    if not isinstance(payload, dict):
        return None
    media_key = str(payload.get("media_key") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not media_key or not title:
        return None
    external_ids = payload.get("external_ids")
    return HeatRecommendation(
        media_key=media_key,
        title=title,
        original_title=str(payload.get("original_title") or "").strip(),
        poster=str(payload.get("poster") or "").strip(),
        year=str(payload.get("year") or "").strip(),
        media_type=str(payload.get("media_type") or "").strip(),
        external_ids={str(k): str(v) for k, v in external_ids.items()}
        if isinstance(external_ids, dict)
        else {},
        heat_score=_float_value(payload.get("heat_score")),
        rank=_int_value(payload.get("rank")),
        watching_now=_int_value(payload.get("watching_now")),
        recent_watchers=_int_value(payload.get("recent_watchers")),
        recent_searches=_int_value(payload.get("recent_searches")),
        recent_favorites=_int_value(payload.get("recent_favorites")),
        reason=str(payload.get("reason") or "").strip(),
    )


def _summary_from_payload(payload: Any) -> HeatMediaSummary | None:
    if not isinstance(payload, dict):
        return None
    media_key = str(payload.get("media_key") or "").strip()
    if not media_key:
        return None
    return HeatMediaSummary(
        media_key=media_key,
        display_text=str(payload.get("display_text") or "").strip(),
        watching_now=_int_value(payload.get("watching_now")),
        recent_watchers=_int_value(payload.get("recent_watchers")),
        recent_searches=_int_value(payload.get("recent_searches")),
        recent_favorites=_int_value(payload.get("recent_favorites")),
        recent_following_adds=_int_value(payload.get("recent_following_adds")),
        heat_score=_float_value(payload.get("heat_score")),
    )
