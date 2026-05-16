from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import time

from atv_player.metadata.models import MetadataMatch, MetadataRecord


class MetadataCache:
    def __init__(self, cache_root: Path) -> None:
        self._root = Path(cache_root)

    def load_search(self, provider: str, title: str, year: str, ttl_seconds: int) -> list[MetadataMatch] | None:
        payload = self._load_json(self._search_path(provider, title, year), ttl_seconds)
        if payload is None:
            return None
        return [MetadataMatch(**item) for item in payload.get("items", [])]

    def save_search(self, provider: str, title: str, year: str, matches: list[MetadataMatch]) -> None:
        self._save_json(
            self._search_path(provider, title, year),
            {"items": [asdict(match) for match in matches]},
        )

    def load_detail(self, provider: str, provider_id: str, ttl_seconds: int) -> MetadataRecord | None:
        payload = self._load_json(self._detail_path(provider, provider_id), ttl_seconds)
        if payload is None:
            return None
        return MetadataRecord(**payload)

    def save_detail(self, provider: str, provider_id: str, record: MetadataRecord) -> None:
        self._save_json(self._detail_path(provider, provider_id), asdict(record))

    def _search_path(self, provider: str, title: str, year: str) -> Path:
        digest = self._hash_key(provider, title, year)
        return self._root / "search" / provider / f"{digest}.json"

    def _detail_path(self, provider: str, provider_id: str) -> Path:
        digest = self._hash_key(provider, provider_id)
        return self._root / "detail" / provider / f"{digest}.json"

    @staticmethod
    def _hash_key(*parts: str) -> str:
        payload = "\x1f".join(part.strip() for part in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_json(self, path: Path, ttl_seconds: int) -> dict[str, object] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        updated_at = float(payload.get("_updated_at") or 0.0)
        if ttl_seconds > 0 and updated_at > 0 and (time() - updated_at) > ttl_seconds:
            return None
        if "_updated_at" in payload:
            payload = dict(payload)
            payload.pop("_updated_at", None)
        return payload

    def _save_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable = dict(payload)
        serializable["_updated_at"] = time()
        path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
