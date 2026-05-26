from __future__ import annotations

from pathlib import Path

from atv_player.models import FavoriteRecord
from atv_player.sqlite_utils import managed_connection


class FavoritesRepository:
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
                CREATE TABLE IF NOT EXISTS favorites (
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    vod_name_snapshot TEXT NOT NULL DEFAULT '',
                    latest_vod_name TEXT NOT NULL DEFAULT '',
                    vod_pic TEXT NOT NULL DEFAULT '',
                    vod_remarks TEXT NOT NULL DEFAULT '',
                    title_changed INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source_kind, source_key, vod_id)
                )
                """
            )

    def save_favorite(self, payload: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO favorites (
                    source_kind, source_key, source_name, vod_id, vod_name_snapshot,
                    latest_vod_name, vod_pic, vod_remarks, title_changed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_key, vod_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    vod_name_snapshot = excluded.vod_name_snapshot,
                    latest_vod_name = excluded.latest_vod_name,
                    vod_pic = excluded.vod_pic,
                    vod_remarks = excluded.vod_remarks,
                    title_changed = excluded.title_changed,
                    updated_at = excluded.updated_at
                """,
                (
                    str(payload.get("source_kind", "")),
                    str(payload.get("source_key", "")),
                    str(payload.get("source_name", "")),
                    str(payload.get("vod_id", "")),
                    str(payload.get("vod_name_snapshot", "")),
                    str(payload.get("latest_vod_name", "")),
                    str(payload.get("vod_pic", "")),
                    str(payload.get("vod_remarks", "")),
                    1 if bool(payload.get("title_changed", False)) else 0,
                    int(payload.get("created_at", 0)),
                    int(payload.get("updated_at", 0)),
                ),
            )

    def update_refresh_state(
        self,
        source_kind: str,
        source_key: str,
        vod_id: str,
        *,
        latest_vod_name: str,
        vod_pic: str,
        vod_remarks: str,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vod_name_snapshot FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                (source_kind, source_key, vod_id),
            ).fetchone()
            if row is None:
                return
            snapshot = str(row[0] or "")
            conn.execute(
                """
                UPDATE favorites
                SET latest_vod_name = ?, vod_pic = ?, vod_remarks = ?, title_changed = ?
                WHERE source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (
                    latest_vod_name,
                    vod_pic,
                    vod_remarks,
                    1 if latest_vod_name != snapshot else 0,
                    source_kind,
                    source_key,
                    vod_id,
                ),
            )

    def load_page(self, *, page: int, size: int, keyword: str) -> tuple[list[FavoriteRecord], int]:
        where_sql = ""
        params: list[object] = []
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            where_sql = "WHERE latest_vod_name LIKE ? OR vod_name_snapshot LIKE ?"
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        offset = max(page - 1, 0) * size
        with self._connect() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM favorites {where_sql}", params).fetchone()[0])
            rows = conn.execute(
                f"""
                SELECT source_kind, source_key, source_name, vod_id, vod_name_snapshot, latest_vod_name,
                       vod_pic, vod_remarks, title_changed, created_at, updated_at
                FROM favorites
                {where_sql}
                ORDER BY updated_at DESC, created_at DESC, vod_id ASC
                LIMIT ? OFFSET ?
                """,
                [*params, size, offset],
            ).fetchall()
        return ([
            FavoriteRecord(
                source_kind=str(row[0]),
                source_key=str(row[1]),
                source_name=str(row[2]),
                vod_id=str(row[3]),
                vod_name_snapshot=str(row[4]),
                latest_vod_name=str(row[5]),
                vod_pic=str(row[6]),
                vod_remarks=str(row[7]),
                title_changed=bool(row[8]),
                created_at=int(row[9]),
                updated_at=int(row[10]),
            )
            for row in rows
        ], total)

    def load_recent(self, *, limit: int) -> list[FavoriteRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, source_name, vod_id, vod_name_snapshot, latest_vod_name,
                       vod_pic, vod_remarks, title_changed, created_at, updated_at
                FROM favorites
                ORDER BY updated_at DESC, created_at DESC, vod_id ASC
                LIMIT ?
                """,
                (max(0, int(limit or 0)),),
            ).fetchall()
        return [
            FavoriteRecord(
                source_kind=str(row[0]),
                source_key=str(row[1]),
                source_name=str(row[2]),
                vod_id=str(row[3]),
                vod_name_snapshot=str(row[4]),
                latest_vod_name=str(row[5]),
                vod_pic=str(row[6]),
                vod_remarks=str(row[7]),
                title_changed=bool(row[8]),
                created_at=int(row[9]),
                updated_at=int(row[10]),
            )
            for row in rows
        ]

    def delete_favorites(self, records: list[FavoriteRecord]) -> None:
        if not records:
            return
        with self._connect() as conn:
            conn.executemany(
                "DELETE FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                [(record.source_kind, record.source_key, record.vod_id) for record in records],
            )

    def delete_filtered(self, *, keyword: str) -> None:
        normalized_keyword = keyword.strip()
        with self._connect() as conn:
            if not normalized_keyword:
                conn.execute("DELETE FROM favorites")
                return
            like = f"%{normalized_keyword}%"
            conn.execute(
                "DELETE FROM favorites WHERE latest_vod_name LIKE ? OR vod_name_snapshot LIKE ?",
                (like, like),
            )

    def is_favorited(self, source_kind: str, source_key: str, vod_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM favorites WHERE source_kind = ? AND source_key = ? AND vod_id = ?",
                (source_kind, source_key, vod_id),
            ).fetchone()
        return row is not None
