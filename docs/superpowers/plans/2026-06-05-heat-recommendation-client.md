# Heat Recommendation Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fixed-backend anonymous heat recommendation reporting and display to ATV Player.

**Architecture:** Add a focused `atv_player.heat` package for payload models, media identity extraction, and HTTP access to `https://v.har01d.cn/api/v1/heat`. Inject a thin controller into `MainWindow` and `PlayerWindow` so UI/playback events can report heat and read recommendations without changing existing playback, favorites, following, or search storage behavior. All heat calls run in background threads, fail silently in UI, and log only diagnostic failures.

**Tech Stack:** Python 3.12, PySide6, `httpx`, pytest, pytest-qt, existing `SettingsRepository.ensure_app_identity()`.

---

## File Structure

- Create `src/atv_player/heat/__init__.py`: public exports for tests and application wiring.
- Create `src/atv_player/heat/models.py`: dataclasses for event payloads, recommendation items, media summaries, and client context.
- Create `src/atv_player/heat/identity.py`: helpers that derive safe `media_key` and public media metadata from `VodItem`, `PlayItem`, `FavoriteRecord`, `FollowingRecord`, and recommendation payloads.
- Create `src/atv_player/heat/service.py`: fixed-base-url HTTP client for `/events`, `/recommendations`, and `/media/{media_key}`.
- Create `src/atv_player/heat/controller.py`: throttling, one-shot effective-watch tracking, and background-safe reporting/read helpers.
- Modify `src/atv_player/app.py`: construct `HeatService`/`HeatController` with the existing immutable app identity and inject it into `MainWindow`.
- Modify `src/atv_player/ui/main_window.py`: accept `heat_controller`, load “大家在看” items into `GlobalSearchPopup`, emit search events, and report favorite/following/play starts through existing hooks.
- Modify `src/atv_player/ui/player_window.py`: accept `heat_controller`, fetch per-media heat for the current item, render a `热度` detail row, and report effective watch once.
- Test `tests/test_heat_service.py`: fixed URL, JSON payload shape, redaction, response parsing, silent failure.
- Test `tests/test_heat_identity.py`: media key extraction priority and title fallback.
- Extend `tests/test_main_window_ui.py`: recommendations section behavior and recommendation click starts global search.
- Extend `tests/test_player_window_ui.py`: heat row rendering/hiding and effective-watch event trigger.

## Task 1: Heat Models And HTTP Service

**Files:**
- Create: `src/atv_player/heat/__init__.py`
- Create: `src/atv_player/heat/models.py`
- Create: `src/atv_player/heat/service.py`
- Test: `tests/test_heat_service.py`

- [ ] **Step 1: Write failing service tests**

Add `tests/test_heat_service.py`:

```python
from __future__ import annotations

import httpx

from atv_player.heat.models import HeatClientContext, HeatEvent, HeatMediaIdentity
from atv_player.heat.service import HEAT_API_BASE_URL, HeatService


def test_heat_service_posts_events_to_fixed_backend() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(202, json={"ok": True, "accepted": True, "event_id": "evt-1"})

    service = HeatService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    delivered = service.record_event(
        HeatEvent(
            event_id="evt-1",
            installation_id="install-1",
            event_type="play_start",
            occurred_at=1780660000000,
            client=HeatClientContext(app="atv-player", version="0.69.1", platform="linux"),
            media=HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏"),
            context={"position_seconds": 0, "episode_url": "https://secret.example/1.m3u8"},
        )
    )

    assert delivered is True
    assert captured["method"] == "POST"
    assert captured["url"] == f"{HEAT_API_BASE_URL}/events"
    assert "episode_url" not in captured["json"]
    assert "tmdb:tv:1399" in captured["json"]


def test_heat_service_loads_recommendations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{HEAT_API_BASE_URL}/recommendations?limit=24"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "generated_at": 1780660000000,
                "window_seconds": 86400,
                "items": [
                    {
                        "media_key": "tmdb:movie:1",
                        "title": "测试电影",
                        "poster": "https://image.example/p.jpg",
                        "heat_score": 10.5,
                        "rank": 1,
                        "watching_now": 2,
                        "reason": "2 人正在播放",
                    }
                ],
            },
        )

    service = HeatService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    items = service.load_recommendations(limit=24)

    assert len(items) == 1
    assert items[0].media_key == "tmdb:movie:1"
    assert items[0].title == "测试电影"
    assert items[0].reason == "2 人正在播放"


def test_heat_service_loads_media_summary_with_percent_encoded_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{HEAT_API_BASE_URL}/media/tmdb%3Atv%3A1399"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "media_key": "tmdb:tv:1399",
                "watching_now": 23,
                "recent_watchers": 128,
                "display_text": "23 人正在播放",
            },
        )

    service = HeatService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    summary = service.load_media_heat("tmdb:tv:1399")

    assert summary is not None
    assert summary.display_text == "23 人正在播放"


def test_heat_service_returns_empty_results_on_failures() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False})

    service = HeatService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert service.load_recommendations(limit=24) == []
    assert service.load_media_heat("tmdb:tv:1399") is None
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_heat_service.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.heat'`.

- [ ] **Step 3: Implement models and service**

Create `src/atv_player/heat/models.py` with frozen/slotted dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class HeatClientContext:
    app: str = "atv-player"
    version: str = ""
    platform: str = ""

    def to_payload(self) -> dict[str, object]:
        return {"app": self.app, "version": self.version, "platform": self.platform}


@dataclass(slots=True, frozen=True)
class HeatMediaIdentity:
    media_key: str
    title: str
    original_title: str = ""
    poster: str = ""
    year: str = ""
    media_type: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"media_key": self.media_key, "title": self.title}
        for key, value in (
            ("original_title", self.original_title),
            ("poster", self.poster),
            ("year", self.year),
            ("media_type", self.media_type),
        ):
            if value:
                payload[key] = value
        ids = {key: value for key, value in self.external_ids.items() if value}
        if ids:
            payload["external_ids"] = ids
        return payload


@dataclass(slots=True, frozen=True)
class HeatEvent:
    event_id: str
    installation_id: str
    event_type: str
    occurred_at: int
    client: HeatClientContext
    media: HeatMediaIdentity | None = None
    context: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class HeatRecommendation:
    media_key: str
    title: str
    original_title: str = ""
    poster: str = ""
    year: str = ""
    media_type: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)
    heat_score: float = 0.0
    rank: int = 0
    watching_now: int = 0
    recent_watchers: int = 0
    recent_searches: int = 0
    recent_favorites: int = 0
    reason: str = ""


@dataclass(slots=True, frozen=True)
class HeatMediaSummary:
    media_key: str
    display_text: str = ""
    watching_now: int = 0
    recent_watchers: int = 0
    recent_searches: int = 0
    recent_favorites: int = 0
    recent_following_adds: int = 0
    heat_score: float = 0.0

    def best_display_text(self) -> str:
        if self.display_text:
            return self.display_text
        if self.watching_now > 0:
            return f"{self.watching_now} 人正在播放"
        if self.recent_watchers > 0:
            return f"{self.recent_watchers} 人近期观看"
        return ""
```

Create `src/atv_player/heat/service.py`:

```python
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
            response = self._client.get(f"{self._base_url}/recommendations", params={"limit": int(limit)})
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
        return [item for item in (_recommendation_from_payload(raw) for raw in items) if item is not None]

    def load_media_heat(self, media_key: str) -> HeatMediaSummary | None:
        normalized = str(media_key or "").strip()
        if not normalized:
            return None
        try:
            response = self._client.get(f"{self._base_url}/media/{quote(normalized, safe='')}")
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
        external_ids={str(k): str(v) for k, v in external_ids.items()} if isinstance(external_ids, dict) else {},
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
```

Create `src/atv_player/heat/__init__.py`:

```python
from atv_player.heat.models import (
    HeatClientContext,
    HeatEvent,
    HeatMediaIdentity,
    HeatMediaSummary,
    HeatRecommendation,
)
from atv_player.heat.service import HEAT_API_BASE_URL, HeatService

__all__ = [
    "HEAT_API_BASE_URL",
    "HeatClientContext",
    "HeatEvent",
    "HeatMediaIdentity",
    "HeatMediaSummary",
    "HeatRecommendation",
    "HeatService",
]
```

- [ ] **Step 4: Run service tests**

Run: `uv run pytest tests/test_heat_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/heat/__init__.py src/atv_player/heat/models.py src/atv_player/heat/service.py tests/test_heat_service.py
git commit -m "feat: add heat api client"
```

## Task 2: Media Identity Extraction

**Files:**
- Create: `src/atv_player/heat/identity.py`
- Modify: `src/atv_player/heat/__init__.py`
- Test: `tests/test_heat_identity.py`

- [ ] **Step 1: Write failing identity tests**

Add `tests/test_heat_identity.py`:

```python
from __future__ import annotations

from atv_player.following_models import FollowingRecord
from atv_player.heat.identity import heat_identity_from_following, heat_identity_from_vod
from atv_player.models import PlaybackDetailField, PlayItem, VodItem


def test_heat_identity_prefers_tmdb_detail_field() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="权力的游戏",
            vod_pic="https://image.example/p.jpg",
            vod_year="2011",
            type_name="剧集",
            detail_fields=[PlaybackDetailField("TMDB ID", "1399")],
        )
    )

    assert identity is not None
    assert identity.media_key == "tmdb:tv:1399"
    assert identity.external_ids["tmdb"] == "tv:1399"


def test_heat_identity_extracts_douban_when_tmdb_missing() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="测试电影",
            type_name="电影",
            detail_fields=[PlaybackDetailField("豆瓣ID", "3016187")],
        )
    )

    assert identity is not None
    assert identity.media_key == "douban:3016187"
    assert identity.external_ids["douban"] == "3016187"


def test_heat_identity_falls_back_to_normalized_title() -> None:
    identity = heat_identity_from_vod(VodItem(vod_id="x", vod_name="测试：电影 第一季"))

    assert identity is not None
    assert identity.media_key == "title:测试电影"


def test_heat_identity_merges_play_item_fields() -> None:
    vod = VodItem(vod_id="x", vod_name="集合名", type_name="剧集")
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        media_title="单集名",
        detail_fields=[PlaybackDetailField("Bangumi ID", "526975")],
    )

    identity = heat_identity_from_vod(vod, item)

    assert identity is not None
    assert identity.media_key == "bangumi:526975"
    assert identity.title == "单集名"


def test_heat_identity_from_following_uses_provider_identity() -> None:
    record = FollowingRecord(
        id=1,
        title="追更剧",
        provider="tmdb",
        provider_id="tv:1399",
        poster="https://image.example/p.jpg",
        media_kind="tv",
    )

    identity = heat_identity_from_following(record)

    assert identity is not None
    assert identity.media_key == "tmdb:tv:1399"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_heat_identity.py -q`

Expected: FAIL with missing `atv_player.heat.identity`.

- [ ] **Step 3: Implement identity helpers**

Create `src/atv_player/heat/identity.py`:

```python
from __future__ import annotations

import re

from atv_player.following_models import FollowingRecord
from atv_player.heat.models import HeatMediaIdentity
from atv_player.metadata.providers.tmdb import infer_tmdb_media_type
from atv_player.metadata.models import MetadataQuery
from atv_player.models import FavoriteRecord, PlayItem, PlaybackDetailField, VodItem


def normalize_heat_title(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[第][一二三四五六七八九十0-9]+[季部]?", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[·:：,，.。!！?？'\"“”‘’《》<>【】()[\]{}_-]", "", text)
    return text.strip()


def _field_value(fields: list[PlaybackDetailField], labels: set[str]) -> str:
    normalized_labels = {label.casefold() for label in labels}
    for field in fields:
        if str(field.label or "").strip().casefold() not in normalized_labels:
            continue
        return str(field.value or "").strip()
    return ""


def _tmdb_media_type(vod: VodItem, explicit: str = "") -> str:
    if explicit in {"movie", "tv"}:
        return explicit
    inferred = infer_tmdb_media_type(
        MetadataQuery(
            title=str(vod.vod_name or ""),
            year=str(vod.vod_year or ""),
            type_name=str(vod.type_name or ""),
            category_name=str(vod.category_name or ""),
        )
    )
    return inferred or "movie"


def heat_identity_from_vod(vod: VodItem, item: PlayItem | None = None) -> HeatMediaIdentity | None:
    fields = [*list(getattr(vod, "detail_fields", []) or []), *list(getattr(item, "detail_fields", []) or [])]
    title = (
        str(getattr(item, "media_title", "") or "").strip()
        or str(getattr(vod, "vod_name", "") or "").strip()
        or str(getattr(item, "title", "") or "").strip()
    )
    if not title:
        return None
    media_type = _tmdb_media_type(vod)
    external_ids: dict[str, str] = {}
    tmdb_id = _field_value(fields, {"TMDB ID", "tmdb id"})
    if tmdb_id:
        external_ids["tmdb"] = f"{media_type}:{tmdb_id}"
        media_key = f"tmdb:{media_type}:{tmdb_id}"
    else:
        douban_id = _field_value(fields, {"豆瓣ID", "豆瓣id", "dbid", "douban id"})
        bangumi_id = _field_value(fields, {"Bangumi ID", "bangumi id"})
        if douban_id:
            external_ids["douban"] = douban_id
            media_key = f"douban:{douban_id}"
        elif bangumi_id:
            external_ids["bangumi"] = bangumi_id
            media_key = f"bangumi:{bangumi_id}"
        else:
            normalized_title = normalize_heat_title(title)
            if not normalized_title:
                return None
            media_key = f"title:{normalized_title}"
    return HeatMediaIdentity(
        media_key=media_key,
        title=title,
        poster=str(getattr(vod, "vod_pic", "") or getattr(item, "video_cover_override", "") or "").strip(),
        year=str(getattr(vod, "vod_year", "") or "").strip(),
        media_type=media_type,
        external_ids=external_ids,
    )


def heat_identity_from_following(record: FollowingRecord) -> HeatMediaIdentity | None:
    title = str(getattr(record, "title", "") or "").strip()
    if not title:
        return None
    provider = str(getattr(record, "provider", "") or "").strip()
    provider_id = str(getattr(record, "provider_id", "") or "").strip()
    media_kind = str(getattr(record, "media_kind", "") or "").strip()
    media_type = "tv" if media_kind in {"tv", "剧集", "动漫"} else "movie"
    external_ids: dict[str, str] = {}
    if provider == "tmdb" and provider_id:
        tmdb_value = provider_id if ":" in provider_id else f"{media_type}:{provider_id}"
        external_ids["tmdb"] = tmdb_value
        media_key = f"tmdb:{tmdb_value}"
    elif provider in {"douban", "official_douban", "local_douban"} and provider_id:
        external_ids["douban"] = provider_id
        media_key = f"douban:{provider_id}"
    elif provider == "bangumi" and provider_id:
        external_ids["bangumi"] = provider_id
        media_key = f"bangumi:{provider_id}"
    else:
        normalized_title = normalize_heat_title(title)
        if not normalized_title:
            return None
        media_key = f"title:{normalized_title}"
    return HeatMediaIdentity(
        media_key=media_key,
        title=title,
        poster=str(getattr(record, "poster", "") or "").strip(),
        year=str(getattr(record, "year", "") or "").strip(),
        media_type=media_type,
        external_ids=external_ids,
    )


def heat_identity_from_favorite(record: FavoriteRecord) -> HeatMediaIdentity | None:
    title = str(getattr(record, "latest_vod_name", "") or getattr(record, "vod_name_snapshot", "") or "").strip()
    if not title:
        return None
    normalized_title = normalize_heat_title(title)
    if not normalized_title:
        return None
    return HeatMediaIdentity(
        media_key=f"title:{normalized_title}",
        title=title,
        poster=str(getattr(record, "vod_pic", "") or "").strip(),
    )
```

Modify `src/atv_player/heat/__init__.py` to export:

```python
from atv_player.heat.identity import (
    heat_identity_from_favorite,
    heat_identity_from_following,
    heat_identity_from_vod,
    normalize_heat_title,
)
```

and add those names to `__all__`.

- [ ] **Step 4: Run identity tests**

Run: `uv run pytest tests/test_heat_identity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/heat/__init__.py src/atv_player/heat/identity.py tests/test_heat_identity.py
git commit -m "feat: derive heat media identities"
```

## Task 3: Heat Controller And Application Wiring

**Files:**
- Create: `src/atv_player/heat/controller.py`
- Modify: `src/atv_player/heat/__init__.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_heat_controller.py`

- [ ] **Step 1: Write failing controller tests**

Add `tests/test_heat_controller.py`:

```python
from __future__ import annotations

from atv_player.heat.controller import HeatController
from atv_player.heat.models import HeatClientContext, HeatMediaIdentity


class FakeService:
    def __init__(self) -> None:
        self.events = []

    def record_event(self, event):
        self.events.append(event)
        return True

    def load_recommendations(self, *, limit=24):
        return []

    def load_media_heat(self, media_key: str):
        return None


def test_heat_controller_records_media_event_with_installation_id() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        client=HeatClientContext(version="test", platform="linux"),
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: "evt-1",
    )

    controller.record_media_event(
        "play_start",
        HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏"),
        context={"source_kind": "plugin"},
    )

    assert len(service.events) == 1
    assert service.events[0].installation_id == "install-1"
    assert service.events[0].event_type == "play_start"


def test_heat_controller_sends_effective_watch_once_per_media_key() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: f"evt-{len(service.events) + 1}",
    )
    media = HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏")

    assert controller.maybe_record_effective_watch(media, position_seconds=600, duration_seconds=2700) is True
    assert controller.maybe_record_effective_watch(media, position_seconds=900, duration_seconds=2700) is False
    assert [event.event_type for event in service.events] == ["watch_progress"]


def test_heat_controller_uses_short_media_threshold() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: "evt-1",
    )

    sent = controller.maybe_record_effective_watch(
        HeatMediaIdentity(media_key="tmdb:movie:1", title="短片"),
        position_seconds=180,
        duration_seconds=300,
    )

    assert sent is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_heat_controller.py -q`

Expected: FAIL with missing controller.

- [ ] **Step 3: Implement controller**

Create `src/atv_player/heat/controller.py`:

```python
from __future__ import annotations

import platform
import threading
import time
import uuid
from collections.abc import Callable

from atv_player.diagnostics import resolve_app_version
from atv_player.heat.models import HeatClientContext, HeatEvent, HeatMediaIdentity
from atv_player.heat.service import HeatService


class HeatController:
    def __init__(
        self,
        service: HeatService,
        *,
        installation_id: str,
        client: HeatClientContext | None = None,
        async_runner: Callable[[Callable[[], None]], None] | None = None,
        clock_ms: Callable[[], int] | None = None,
        event_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._service = service
        self._installation_id = str(installation_id or "").strip()
        self._client = client or HeatClientContext(
            version=resolve_app_version(),
            platform=platform.system().lower(),
        )
        self._async_runner = async_runner or self._run_async
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._event_id_factory = event_id_factory or (lambda: uuid.uuid4().hex)
        self._effective_watch_keys: set[str] = set()

    def record_search(self, query: str, *, source_kind: str = "global_search", media: HeatMediaIdentity | None = None) -> None:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return
        self._record_event("search", media, {"query": normalized_query, "source_kind": source_kind})

    def record_media_event(
        self,
        event_type: str,
        media: HeatMediaIdentity | None,
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        if media is None:
            return
        self._record_event(event_type, media, context or {})

    def maybe_record_effective_watch(
        self,
        media: HeatMediaIdentity | None,
        *,
        position_seconds: int,
        duration_seconds: int,
        episode_index: int = 0,
    ) -> bool:
        if media is None or media.media_key in self._effective_watch_keys:
            return False
        threshold = 600
        if duration_seconds > 0:
            threshold = min(threshold, max(1, int(duration_seconds * 0.3)))
        if int(position_seconds or 0) < threshold:
            return False
        self._effective_watch_keys.add(media.media_key)
        self.record_media_event(
            "watch_progress",
            media,
            context={
                "position_seconds": int(position_seconds or 0),
                "duration_seconds": int(duration_seconds or 0),
                "episode_index": int(episode_index or 0),
                "effective_watch": True,
            },
        )
        return True

    def load_recommendations(self, *, limit: int = 24):
        return self._service.load_recommendations(limit=limit)

    def load_media_heat(self, media_key: str):
        return self._service.load_media_heat(media_key)

    def _record_event(self, event_type: str, media: HeatMediaIdentity | None, context: dict[str, object]) -> None:
        if not self._installation_id:
            return
        event = HeatEvent(
            event_id=self._event_id_factory(),
            installation_id=self._installation_id,
            event_type=event_type,
            occurred_at=self._clock_ms(),
            client=self._client,
            media=media,
            context=context,
        )
        self._async_runner(lambda: self._service.record_event(event))

    @staticmethod
    def _run_async(fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()
```

Modify `src/atv_player/heat/__init__.py` to export `HeatController`.

- [ ] **Step 4: Wire app construction**

Modify `src/atv_player/app.py`:

1. Add imports near other services:

```python
from atv_player.heat import HeatController, HeatService
```

2. In `AppCoordinator.start()` before `MainWindow(...)`, add:

```python
app_identity = self.repo.ensure_app_identity()
heat_controller = HeatController(
    HeatService(),
    installation_id=app_identity.installation_id,
)
```

3. Pass `heat_controller=heat_controller` to `MainWindow(...)`.

- [ ] **Step 5: Run controller tests**

Run: `uv run pytest tests/test_heat_controller.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/atv_player/heat/__init__.py src/atv_player/heat/controller.py src/atv_player/app.py tests/test_heat_controller.py
git commit -m "feat: add heat event controller"
```

## Task 4: Global Search Popup Recommendations And Search Events

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing popup tests**

Append to `tests/test_main_window_ui.py`:

```python
def test_global_search_popup_renders_heat_recommendations(qtbot) -> None:
    popup = main_window_module.GlobalSearchPopup()
    qtbot.addWidget(popup)

    popup.set_heat_items(
        [
            SimpleNamespace(
                media_key="tmdb:tv:1399",
                title="权力的游戏",
                poster="",
                reason="23 人正在播放",
            )
        ]
    )

    assert popup.heat_item_texts() == ["权力的游戏"]
    assert popup.heat_item_button("权力的游戏").toolTip() == "23 人正在播放"


def test_main_window_reports_global_search_event(qtbot) -> None:
    class FakeHeatController:
        def __init__(self):
            self.searches = []

        def record_search(self, query, *, source_kind="global_search", media=None):
            self.searches.append((query, source_kind, media))

        def load_recommendations(self, *, limit=24):
            return []

    heat = FakeHeatController()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        heat_controller=heat,
    )
    qtbot.addWidget(window)

    window.global_search_edit.setText("权力的游戏")
    window._start_global_search()

    assert heat.searches[0][0] == "权力的游戏"
    assert heat.searches[0][1] == "global_search"
```

- [ ] **Step 2: Run targeted tests and verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py::test_global_search_popup_renders_heat_recommendations tests/test_main_window_ui.py::test_main_window_reports_global_search_event -q`

Expected: FAIL because `set_heat_items` and `heat_controller` injection do not exist.

- [ ] **Step 3: Extend `GlobalSearchPopup`**

Modify `src/atv_player/ui/main_window.py` inside `GlobalSearchPopup`:

1. Add instance fields in `__init__`:

```python
self._heat_item_buttons: dict[str, QPushButton] = {}
self._heat_item_texts: list[str] = []
self._heat_items_by_title: dict[str, object] = {}
self._heat_title_label: QLabel | None = None
```

2. Add public accessors:

```python
def heat_item_texts(self) -> list[str]:
    return list(self._heat_item_texts)

def heat_item_button(self, text: str) -> QPushButton:
    return self._heat_item_buttons[text]
```

3. In `_build_hot_panel()`, add a `大家在看` label and `_heat_items_widget` above the hot source tabs:

```python
heat_title = QLabel("大家在看", self._hot_panel)
heat_title.setContentsMargins(16, 14, 16, 8)
heat_title.setStyleSheet(self._section_title_qss())
self._heat_title_label = heat_title
self._hot_layout.addWidget(heat_title)
self._heat_items_widget = QWidget(self._hot_panel)
self._heat_items_layout = QVBoxLayout(self._heat_items_widget)
self._heat_items_layout.setContentsMargins(8, 0, 8, 8)
self._heat_items_layout.setSpacing(0)
self._hot_layout.addWidget(self._heat_items_widget)
```

4. Add `set_heat_items()`:

```python
def set_heat_items(self, items: list[object]) -> None:
    self._clear_layout(self._heat_items_layout)
    self._heat_item_buttons = {}
    self._heat_item_texts = []
    self._heat_items_by_title = {}
    for index, item in enumerate(items[:6], start=1):
        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            continue
        reason = str(getattr(item, "reason", "") or "").strip()
        row = QWidget(self._heat_items_widget)
        row.setFixedHeight(self.HOT_ITEM_HEIGHT)
        row.setStyleSheet(self._hot_row_qss())
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 6, 12, 6)
        row_layout.setSpacing(10)
        rank_label = QLabel(f"{index:02d}", row)
        rank_label.setStyleSheet(self._hot_rank_qss())
        button = QPushButton(title, row)
        button.setToolTip(reason)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFlat(True)
        button.setStyleSheet(self._hot_button_qss())
        button.clicked.connect(lambda checked=False, current_title=title: self._on_item_clicked(current_title))
        row_layout.addWidget(rank_label)
        row_layout.addWidget(button, 1)
        self._heat_item_buttons[title] = button
        self._heat_item_texts.append(title)
        self._heat_items_by_title[title] = item
        self._heat_items_layout.addWidget(row)
    self._heat_title_label.setHidden(not self._heat_item_texts)
    self._heat_items_widget.setHidden(not self._heat_item_texts)
    self.adjustSize()
```

5. Update `_apply_theme()` to style `_heat_title_label` and heat buttons like hot buttons.

- [ ] **Step 4: Inject and use heat controller in main window**

Modify `MainWindow.__init__` signature:

```python
heat_controller=None,
```

Store:

```python
self._heat_controller = heat_controller
self._heat_recommendation_request_id = 0
```

In `_start_global_search()`, after normalizing non-empty keyword and before/after existing search starts, add:

```python
if self._heat_controller is not None:
    self._heat_controller.record_search(normalized_keyword, source_kind="global_search")
```

In `_ensure_global_search_popup()` or `_toggle_global_search_popup()` where the popup is created/shown, add a helper:

```python
def _refresh_heat_recommendations(self) -> None:
    if self._heat_controller is None or self._global_search_popup is None:
        return
    self._heat_recommendation_request_id += 1
    request_id = self._heat_recommendation_request_id

    def run() -> None:
        try:
            items = self._heat_controller.load_recommendations(limit=24)
        except Exception:
            items = []
        if self._can_deliver_async_result():
            QTimer.singleShot(0, lambda: self._handle_heat_recommendations_loaded(request_id, items))

    threading.Thread(target=run, daemon=True).start()

def _handle_heat_recommendations_loaded(self, request_id: int, items: object) -> None:
    if request_id != self._heat_recommendation_request_id or self._global_search_popup is None:
        return
    self._global_search_popup.set_heat_items(list(items or []))
```

Call `_refresh_heat_recommendations()` when showing the popup.

- [ ] **Step 5: Run popup tests**

Run: `uv run pytest tests/test_main_window_ui.py::test_global_search_popup_renders_heat_recommendations tests/test_main_window_ui.py::test_main_window_reports_global_search_event -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: show heat recommendations in search popup"
```

## Task 5: Favorite, Following, And Playback Event Hooks

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing hook tests**

Append focused tests using fake heat controller methods:

```python
def test_main_window_reports_recommendation_click_as_search(qtbot) -> None:
    class FakeHeatController:
        def __init__(self):
            self.searches = []

        def record_search(self, query, *, source_kind="global_search", media=None):
            self.searches.append((query, source_kind, media))

        def load_recommendations(self, *, limit=24):
            return []

    heat = FakeHeatController()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        heat_controller=heat,
    )
    qtbot.addWidget(window)

    window._handle_heat_recommendation_clicked("权力的游戏")

    assert heat.searches == [("权力的游戏", "heat_recommendation", None)]
    assert window.global_search_edit.text() == "权力的游戏"


def test_main_window_reports_player_open_event(qtbot) -> None:
    class FakeHeatController:
        def __init__(self):
            self.events = []

        def record_media_event(self, event_type, media, *, context=None):
            self.events.append((event_type, media, context or {}))

    heat = FakeHeatController()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        heat_controller=heat,
    )
    qtbot.addWidget(window)

    request = OpenPlayerRequest(
        vod=VodItem(vod_id="v1", vod_name="权力的游戏", detail_fields=[PlaybackDetailField("TMDB ID", "1399")]),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
        clicked_index=0,
    )
    window._record_heat_play_start(request)

    assert heat.events[0][0] == "play_start"
    assert heat.events[0][1].media_key == "tmdb:movie:1399"
```

- [ ] **Step 2: Run targeted tests and verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py::test_main_window_reports_recommendation_click_as_search tests/test_main_window_ui.py::test_main_window_reports_player_open_event -q`

Expected: FAIL because helper methods do not exist.

- [ ] **Step 3: Add heat helper methods**

Modify `src/atv_player/ui/main_window.py`:

1. Import:

```python
from atv_player.heat.identity import heat_identity_from_favorite, heat_identity_from_following, heat_identity_from_vod
```

2. Add helper:

```python
def _record_heat_play_start(self, request: OpenPlayerRequest) -> None:
    if self._heat_controller is None:
        return
    playlist = list(getattr(request, "playlist", []) or [])
    clicked_index = max(0, int(getattr(request, "clicked_index", 0) or 0))
    item = playlist[clicked_index] if 0 <= clicked_index < len(playlist) else None
    identity = heat_identity_from_vod(request.vod, item)
    self._heat_controller.record_media_event(
        "play_start",
        identity,
        context={"source_kind": str(getattr(request, "source_mode", "") or getattr(self.config, "last_playback_source", "") or "")},
    )
```

3. Call `_record_heat_play_start(request)` in the success path immediately before/after opening `PlayerWindow` with an `OpenPlayerRequest`.

4. Add:

```python
def _handle_heat_recommendation_clicked(self, title: str) -> None:
    if self._heat_controller is not None:
        self._heat_controller.record_search(title, source_kind="heat_recommendation")
    self.global_search_edit.setText(str(title or "").strip())
    self._start_global_search()
```

5. Wire heat popup recommendation clicks to `_handle_heat_recommendation_clicked` rather than the generic hot item handler if a separate signal is introduced. If reusing `item_clicked`, detect heat section by a stored item map in popup.

6. In favorite/following add success handlers, call:

```python
identity = heat_identity_from_favorite(record)
self._heat_controller.record_media_event("favorite_add", identity, context={"source_kind": "favorite"})
```

and:

```python
identity = heat_identity_from_following(record)
self._heat_controller.record_media_event("following_add", identity, context={"source_kind": "following"})
```

Place these only after successful add operations, not on removal.

- [ ] **Step 4: Run targeted hook tests**

Run: `uv run pytest tests/test_main_window_ui.py::test_main_window_reports_recommendation_click_as_search tests/test_main_window_ui.py::test_main_window_reports_player_open_event -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: report heat interaction events"
```

## Task 6: Player Detail Heat Summary And Effective Watch

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing player tests**

Append to `tests/test_player_window_ui.py`:

```python
def test_player_window_renders_heat_detail_row(qtbot) -> None:
    class FakeHeatController:
        def load_media_heat(self, media_key):
            return SimpleNamespace(best_display_text=lambda: "23 人正在播放")

    window = PlayerWindow(FakePlayerController(), heat_controller=FakeHeatController())
    qtbot.addWidget(window)
    window.session = PlayerSession(
        vod=VodItem(
            vod_id="v1",
            vod_name="权力的游戏",
            detail_fields=[PlaybackDetailField("TMDB ID", "1399")],
        ),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window.current_index = 0

    window._refresh_heat_summary_for_current_item()
    qtbot.waitUntil(lambda: window._heat_summary_text == "23 人正在播放", timeout=1000)
    window._render_detail_fields()

    assert any("热度" in label.text() for label in window.detail_fields_widget.findChildren(QLabel))


def test_player_window_reports_effective_watch_once(qtbot) -> None:
    class FakeHeatController:
        def __init__(self):
            self.calls = []

        def maybe_record_effective_watch(self, media, *, position_seconds, duration_seconds, episode_index=0):
            self.calls.append((media.media_key if media else "", position_seconds, duration_seconds, episode_index))
            return True

    heat = FakeHeatController()
    window = PlayerWindow(FakePlayerController(), heat_controller=heat)
    qtbot.addWidget(window)
    window.session = PlayerSession(
        vod=VodItem(
            vod_id="v1",
            vod_name="权力的游戏",
            detail_fields=[PlaybackDetailField("TMDB ID", "1399")],
        ),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window.current_index = 0

    window._record_heat_effective_watch_if_needed(position_seconds=600, duration_seconds=2700)

    assert heat.calls[0][1:] == (600, 2700, 0)
```

- [ ] **Step 2: Run player tests and verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "heat_detail_row or effective_watch" -q`

Expected: FAIL because `heat_controller` and helpers do not exist.

- [ ] **Step 3: Add player heat state and rendering**

Modify `PlayerWindow.__init__` signature:

```python
heat_controller=None,
```

Store:

```python
self._heat_controller = heat_controller
self._heat_summary_request_id = 0
self._heat_summary_text = ""
```

Import:

```python
from atv_player.heat.identity import heat_identity_from_vod
```

Add helpers:

```python
def _current_heat_identity(self):
    if self.session is None:
        return None
    item = self._current_play_item()
    return heat_identity_from_vod(self.session.vod, item)

def _refresh_heat_summary_for_current_item(self) -> None:
    self._heat_summary_text = ""
    if self._heat_controller is None:
        return
    identity = self._current_heat_identity()
    if identity is None:
        return
    self._heat_summary_request_id += 1
    request_id = self._heat_summary_request_id

    def run() -> None:
        try:
            summary = self._heat_controller.load_media_heat(identity.media_key)
            text = summary.best_display_text() if summary is not None else ""
        except Exception:
            text = ""
        if self._can_deliver_async_result():
            self._heat_summary_signals.loaded.emit(request_id, text)

    threading.Thread(target=run, daemon=True).start()
```

Add a dedicated Qt signal near the existing signal helper classes:

```python
class _HeatSummarySignals(QObject):
    loaded = Signal(int, str)
```

Create and connect it in `__init__`:

```python
self._heat_summary_signals = _HeatSummarySignals()
self._connect_async_signal(self._heat_summary_signals.loaded, self._handle_heat_summary_loaded)
```

Add the handler:

```python
def _handle_heat_summary_loaded(self, request_id: int, text: str) -> None:
    if request_id != self._heat_summary_request_id:
        return
    self._heat_summary_text = str(text or "").strip()
    self._render_detail_fields()
```

Modify `_current_detail_fields()` or `_render_detail_fields()` so the visible detail field list includes:

```python
if self._heat_summary_text:
    fields = [PlaybackDetailField("热度", self._heat_summary_text), *fields]
```

Call `_refresh_heat_summary_for_current_item()` after session open and after current playlist item changes.

- [ ] **Step 4: Add effective watch reporting**

Add:

```python
def _record_heat_effective_watch_if_needed(self, *, position_seconds: int, duration_seconds: int) -> None:
    if self._heat_controller is None:
        return
    identity = self._current_heat_identity()
    self._heat_controller.maybe_record_effective_watch(
        identity,
        position_seconds=int(position_seconds or 0),
        duration_seconds=int(duration_seconds or 0),
        episode_index=int(self.current_index or 0),
    )
```

Call it from the existing progress-reporting timer/path after `controller.report_progress(...)` with the same `position_seconds` and `duration_seconds`.

- [ ] **Step 5: Pass controller from main window to player window**

Modify the `PlayerWindow(...)` construction in `src/atv_player/ui/main_window.py` to include:

```python
heat_controller=self._heat_controller,
```

- [ ] **Step 6: Run player heat tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "heat_detail_row or effective_watch" -q`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/atv_player/ui/player_window.py src/atv_player/ui/main_window.py tests/test_player_window_ui.py
git commit -m "feat: show player heat summary"
```

## Task 7: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run heat unit tests**

Run: `uv run pytest tests/test_heat_service.py tests/test_heat_identity.py tests/test_heat_controller.py -q`

Expected: PASS.

- [ ] **Step 2: Run focused UI tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "heat or global_search_popup" -q`

Expected: PASS.

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "heat or detail_fields" -q`

Expected: PASS.

- [ ] **Step 3: Run static checks**

Run: `uv run ruff check src/atv_player/heat src/atv_player/ui/main_window.py src/atv_player/ui/player_window.py tests/test_heat_service.py tests/test_heat_identity.py tests/test_heat_controller.py`

Expected: PASS.

Run: `uv run pyright src/atv_player/heat`

Expected: PASS.

- [ ] **Step 4: Final status**

Run: `git status --short`

Expected: clean worktree after all commits.

## Self-Review

- Spec coverage: fixed HTTP base URL, `/events`, `/recommendations`, `/media/{media_key}`, anonymous installation ID, no user-facing settings, search/recommendation/play/favorite/following/effective-watch triggers, player heat row, silent failure, and tests are all covered by tasks.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or unspecified tests remain.
- Type consistency: `HeatMediaIdentity`, `HeatEvent`, `HeatRecommendation`, `HeatMediaSummary`, `HeatService`, and `HeatController` are defined before later tasks use them.
