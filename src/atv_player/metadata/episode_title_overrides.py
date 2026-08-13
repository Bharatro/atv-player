from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from time import time

from atv_player.episode_titles import seed_original_titles
from atv_player.models import PlayItem
from atv_player.sqlite_utils import managed_connection

logger = logging.getLogger(__name__)

MANUAL_EPISODE_TITLE_SOURCE = "manual"


def episode_override_item_key(item: PlayItem) -> str:
    """Stable per-file identity within a vod/source, used to key manual overrides.

    Durable ids win (play_id/url/original_url); path basename is the fallback so
    local-drive / alist sources without a play id still key consistently. The same
    item must resolve to the same key at save time and at load time, so the lookup
    order here is the single source of truth.
    """
    for attr in ("play_id", "url", "original_url"):
        value = str(getattr(item, attr, "") or "").strip()
        if value:
            return value
    path = str(getattr(item, "path", "") or "").strip().rstrip("/\\")
    if path:
        return re.split(r"[\\/]", path)[-1]
    return str(getattr(item, "title", "") or "").strip()


@dataclass(slots=True)
class EpisodeTitleOverride:
    source_kind: str
    source_key: str
    vod_id: str
    item_key: str
    display_title: str
    updated_at: int = 0


class EpisodeTitleOverrideRepository:
    """Per-episode manual title overrides.

    Overrides carry the implicit ``manual`` source (rank 0 in the episode-title
    source priority), so a saved override always beats any auto-derived title.
    Keyed globally by (source_kind, source_key, vod_id, item_key); deliberately
    not namespaced per account (a title correction is objective, not personal).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return managed_connection(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_title_overrides (
                    source_kind TEXT NOT NULL DEFAULT '',
                    source_key TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    display_title TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (source_kind, source_key, vod_id, item_key)
                )
                """
            )

    def load_for_session(
        self,
        *,
        source_kind: str,
        source_key: str,
        vod_id: str,
    ) -> dict[str, str]:
        if not str(vod_id or "").strip():
            return {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_key, display_title FROM episode_title_overrides
                WHERE source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (str(source_kind or ""), str(source_key or ""), str(vod_id)),
            ).fetchall()
        return {str(item_key): str(title) for item_key, title in rows if item_key}

    def upsert(
        self,
        *,
        source_kind: str,
        source_key: str,
        vod_id: str,
        item_key: str,
        display_title: str,
    ) -> None:
        item_key = str(item_key or "").strip()
        display_title = str(display_title or "").strip()
        if not item_key or not display_title or not str(vod_id or "").strip():
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episode_title_overrides (
                    source_kind, source_key, vod_id, item_key, display_title, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_key, vod_id, item_key) DO UPDATE SET
                    display_title = excluded.display_title,
                    updated_at = excluded.updated_at
                """,
                (
                    str(source_kind or ""),
                    str(source_key or ""),
                    str(vod_id),
                    item_key,
                    display_title,
                    int(time()),
                ),
            )

    def delete(
        self,
        *,
        source_kind: str,
        source_key: str,
        vod_id: str,
        item_key: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM episode_title_overrides
                WHERE source_kind = ? AND source_key = ? AND vod_id = ? AND item_key = ?
                """,
                (
                    str(source_kind or ""),
                    str(source_key or ""),
                    str(vod_id),
                    str(item_key or ""),
                ),
            )


def apply_episode_title_overrides(
    playlist: list[PlayItem],
    overrides: dict[str, str],
) -> bool:
    """Stamp manual overrides onto matching playlist items in place.

    ``manual`` is the highest-priority source, so this is safe to run after every
    auto-derived rewrite: it only overwrites titles for items that have a saved
    override. Returns True if any item changed.
    """
    if not overrides:
        return False
    seed_original_titles(playlist)
    changed = False
    for item in playlist:
        key = episode_override_item_key(item)
        title = overrides.get(key)
        if not title:
            continue
        if item.episode_display_title == title and item.episode_title_source == MANUAL_EPISODE_TITLE_SOURCE:
            continue
        item.episode_display_title = title
        item.episode_title_source = MANUAL_EPISODE_TITLE_SOURCE
        changed = True
    return changed
