from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from atv_player.paths import app_cache_dir

_METADATA_SCRAPE_DIALOG_CACHE_VERSION = "v1"


@dataclass(slots=True)
class MetadataScrapeDialogState:
    title: str = ""
    year: str = ""
    category: str = ""


def metadata_scrape_dialog_cache_dir() -> Path | None:
    try:
        return app_cache_dir() / "metadata" / "dialog-state"
    except OSError:
        return None


def _metadata_scrape_dialog_cache_key(binding_title: str, binding_year: str) -> str:
    return sha256(
        "\0".join(
            (
                _METADATA_SCRAPE_DIALOG_CACHE_VERSION,
                str(binding_title or "").strip(),
                str(binding_year or "").strip(),
            )
        ).encode("utf-8")
    ).hexdigest()


def metadata_scrape_dialog_cache_path(binding_title: str, binding_year: str) -> Path | None:
    cache_dir = metadata_scrape_dialog_cache_dir()
    if cache_dir is None:
        return None
    return cache_dir / f"{_metadata_scrape_dialog_cache_key(binding_title, binding_year)}.json"


def load_cached_metadata_scrape_dialog_state(binding_title: str, binding_year: str) -> MetadataScrapeDialogState | None:
    cache_path = metadata_scrape_dialog_cache_path(binding_title, binding_year)
    if cache_path is None or not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return MetadataScrapeDialogState(
        title=str(payload.get("title") or "").strip(),
        year=str(payload.get("year") or "").strip(),
        category=str(payload.get("category") or "").strip(),
    )


def save_cached_metadata_scrape_dialog_state(
    binding_title: str,
    binding_year: str,
    state: MetadataScrapeDialogState,
) -> Path | None:
    cache_path = metadata_scrape_dialog_cache_path(binding_title, binding_year)
    if cache_path is None:
        return None
    payload = {
        "title": str(state.title or "").strip(),
        "year": str(state.year or "").strip(),
        "category": str(state.category or "").strip(),
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        return None
    return cache_path
