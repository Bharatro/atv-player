from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import RLock
import time
from typing import Any, cast

from atv_player.danmaku.models import DanmakuSeriesPreference
from atv_player.danmaku.utils import infer_playlist_episode_number
from atv_player.models import PlayItem
from atv_player.paths import app_data_dir


def danmaku_series_preference_path() -> Path:
    path = app_data_dir() / "danmaku-series-preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_danmaku_episode_key(
    item: PlayItem,
    playlist: list[PlayItem] | None = None,
) -> str:
    number = infer_playlist_episode_number(item, playlist)
    if number is not None and number > 0:
        return f"episode:{number}"
    label = re.sub(r"\s+", "", item.danmaku_search_episode).casefold()
    if label:
        return f"label:{label}"
    identity = str(item.vod_id or item.original_url or item.url or "").strip()
    if identity:
        digest = sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"item:{digest}"
    return "single"


def _normalize_persisted_offsets(value: object) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, dict[str, float]] = {}
    for raw_episode_key, raw_providers in value.items():
        episode_key = str(raw_episode_key or "").strip()
        if not episode_key or not isinstance(raw_providers, dict):
            continue
        providers: dict[str, float] = {}
        for raw_provider, raw_value in raw_providers.items():
            provider = str(raw_provider or "").strip()
            try:
                offset = float(cast(Any, raw_value))
            except (TypeError, ValueError):
                continue
            if not provider or not math.isfinite(offset) or not -600.0 <= offset <= 600.0:
                continue
            if offset != 0.0:
                providers[provider] = offset
        if providers:
            output[episode_key] = providers
    return output


def _normalize_offset_for_save(value: object) -> float:
    try:
        offset = float(cast(Any, value))
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(offset):
        return 0.0
    return max(-600.0, min(offset, 600.0))


class DanmakuSeriesPreferenceStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else danmaku_series_preference_path()
        self._lock = RLock()

    def load(self, series_key: str) -> DanmakuSeriesPreference | None:
        with self._lock:
            raw = self._read_all().get(series_key)
            if not isinstance(raw, dict):
                return None
            try:
                updated_at = int(cast(Any, raw.get("updated_at") or 0))
            except (TypeError, ValueError):
                updated_at = 0
            return DanmakuSeriesPreference(
                series_key=series_key,
                provider=str(raw.get("provider") or ""),
                page_url=str(raw.get("page_url") or ""),
                title=str(raw.get("title") or ""),
                search_title=str(raw.get("search_title") or ""),
                updated_at=updated_at,
                episode_source_offsets=_normalize_persisted_offsets(
                    raw.get("episode_source_offsets")
                ),
            )

    def save(self, preference: DanmakuSeriesPreference) -> DanmakuSeriesPreference:
        with self._lock:
            payload = self._read_all()
            payload[preference.series_key] = {
                "provider": preference.provider,
                "page_url": preference.page_url,
                "title": preference.title,
                "search_title": preference.search_title,
                "updated_at": preference.updated_at or int(time.time()),
                "episode_source_offsets": _normalize_persisted_offsets(
                    preference.episode_source_offsets
                ),
            }
            self._write_all(payload)
            return preference

    def load_offset(self, series_key: str, episode_key: str, provider: str) -> float:
        preference = self.load(series_key)
        if preference is None:
            return 0.0
        return preference.episode_source_offsets.get(episode_key, {}).get(provider, 0.0)

    def save_offset(
        self,
        series_key: str,
        episode_key: str,
        provider: str,
        value: float,
    ) -> None:
        series_key = str(series_key or "").strip()
        episode_key = str(episode_key or "").strip()
        provider = str(provider or "").strip()
        if not series_key or not episode_key or not provider:
            return
        offset = _normalize_offset_for_save(value)
        with self._lock:
            payload = self._read_all()
            raw = payload.get(series_key)
            if not isinstance(raw, dict):
                raw = {}
                payload[series_key] = raw
            offsets = _normalize_persisted_offsets(raw.get("episode_source_offsets"))
            providers = offsets.setdefault(episode_key, {})
            if offset == 0.0:
                providers.pop(provider, None)
                if not providers:
                    offsets.pop(episode_key, None)
            else:
                providers[provider] = offset
            raw["episode_source_offsets"] = offsets
            raw["updated_at"] = int(time.time())
            self._write_all(payload)

    def _read_all(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_all(self, payload: dict[str, dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2, sort_keys=True)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            temp_path.replace(self._path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def _ensure_item_series_key(item: PlayItem) -> str:
    if item.danmaku_series_key.strip():
        return item.danmaku_series_key.strip()
    from atv_player.danmaku.service import build_danmaku_series_key

    item.danmaku_series_key = build_danmaku_series_key(
        item.media_title or item.danmaku_search_title or item.title
    )
    return item.danmaku_series_key


def load_item_danmaku_offset(
    store: DanmakuSeriesPreferenceStore | None,
    item: PlayItem,
    playlist: list[PlayItem] | None = None,
) -> float:
    if store is None:
        return 0.0
    series_key = _ensure_item_series_key(item)
    provider = item.selected_danmaku_provider.strip()
    if not series_key or not provider:
        return 0.0
    return store.load_offset(
        series_key,
        build_danmaku_episode_key(item, playlist),
        provider,
    )


def save_item_danmaku_offset(
    store: DanmakuSeriesPreferenceStore | None,
    item: PlayItem,
    value: float,
    playlist: list[PlayItem] | None = None,
) -> float:
    if store is None:
        return 0.0
    series_key = _ensure_item_series_key(item)
    provider = item.selected_danmaku_provider.strip()
    if not series_key or not provider:
        return 0.0
    episode_key = build_danmaku_episode_key(item, playlist)
    store.save_offset(series_key, episode_key, provider, value)
    return store.load_offset(series_key, episode_key, provider)
