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

    def record_search(
        self,
        query: str,
        *,
        source_kind: str = "global_search",
        media: HeatMediaIdentity | None = None,
    ) -> None:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return
        self._record_event(
            "search",
            media,
            {"query": normalized_query, "source_kind": source_kind},
        )

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
            threshold = min(threshold, max(1, int(duration_seconds * 0.2)))
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

    def _record_event(
        self,
        event_type: str,
        media: HeatMediaIdentity | None,
        context: dict[str, object],
    ) -> None:
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
