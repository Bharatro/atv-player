from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atv_player.sqlite_utils import managed_connection


@dataclass(slots=True)
class FavoriteTMDBBinding:
    source_kind: str
    source_key: str
    vod_id: str
    provider_id: str
    tmdb_id: str
    media_type: str
    title: str
    year: str
    updated_at: int


class FavoriteTMDBBindingRepository:
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
                CREATE TABLE IF NOT EXISTS favorite_tmdb_bindings (
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    tmdb_id TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    year TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source_kind, source_key, vod_id)
                )
                """
            )

    def save(
        self,
        *,
        source_kind: str,
        source_key: str,
        vod_id: str,
        provider_id: str,
        tmdb_id: str,
        media_type: str,
        title: str,
        year: str,
        updated_at: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO favorite_tmdb_bindings (
                    source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_key, vod_id) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    tmdb_id = excluded.tmdb_id,
                    media_type = excluded.media_type,
                    title = excluded.title,
                    year = excluded.year,
                    updated_at = excluded.updated_at
                """,
                (
                    str(source_kind or "").strip(),
                    str(source_key or "").strip(),
                    str(vod_id or "").strip(),
                    str(provider_id or "").strip(),
                    str(tmdb_id or "").strip(),
                    str(media_type or "").strip(),
                    str(title or "").strip(),
                    str(year or "").strip(),
                    int(updated_at or 0),
                ),
            )

    def load(self, *, source_kind: str, source_key: str, vod_id: str) -> FavoriteTMDBBinding | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                FROM favorite_tmdb_bindings
                WHERE source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (
                    str(source_kind or "").strip(),
                    str(source_key or "").strip(),
                    str(vod_id or "").strip(),
                ),
            ).fetchone()
        if row is None:
            return None
        return FavoriteTMDBBinding(*row)

    def load_recent(self, *, limit: int) -> list[FavoriteTMDBBinding]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                FROM favorite_tmdb_bindings
                ORDER BY updated_at DESC, vod_id ASC
                LIMIT ?
                """,
                (max(0, int(limit or 0)),),
            ).fetchall()
        return [FavoriteTMDBBinding(*row) for row in rows]
