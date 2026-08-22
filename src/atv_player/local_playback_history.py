from __future__ import annotations

import sqlite3
from pathlib import Path

from atv_player.models import HistoryRecord
from atv_player.sqlite_utils import managed_connection


class LocalPlaybackHistoryRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._account_namespace = ""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return managed_connection(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_playback_history (
                    account_namespace TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    vod_name TEXT NOT NULL DEFAULT '',
                    vod_pic TEXT NOT NULL DEFAULT '',
                    vod_remarks TEXT NOT NULL DEFAULT '',
                    episode INTEGER NOT NULL DEFAULT 0,
                    episode_url TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL DEFAULT 0,
                    duration INTEGER NOT NULL DEFAULT 0,
                    opening INTEGER NOT NULL DEFAULT 0,
                    ending INTEGER NOT NULL DEFAULT 0,
                    speed REAL NOT NULL DEFAULT 1.0,
                    playlist_index INTEGER NOT NULL DEFAULT 0,
                    source_group_index INTEGER NOT NULL DEFAULT 0,
                    source_index INTEGER NOT NULL DEFAULT 0,
                    source_subgroup_index INTEGER NOT NULL DEFAULT 0,
                    source_subgroup_name TEXT NOT NULL DEFAULT '',
                    drive_dir_id TEXT NOT NULL DEFAULT '',
                    drive_share_key TEXT NOT NULL DEFAULT '',
                    drive_path TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_namespace, source_kind, source_key, vod_id)
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(media_playback_history)").fetchall()
            }
            if "source_group_index" not in columns:
                conn.execute("ALTER TABLE media_playback_history ADD COLUMN source_group_index INTEGER NOT NULL DEFAULT 0")
            if "duration" not in columns:
                conn.execute("ALTER TABLE media_playback_history ADD COLUMN duration INTEGER NOT NULL DEFAULT 0")
            if "source_index" not in columns:
                conn.execute("ALTER TABLE media_playback_history ADD COLUMN source_index INTEGER NOT NULL DEFAULT 0")
            if "source_subgroup_index" not in columns:
                conn.execute(
                    "ALTER TABLE media_playback_history ADD COLUMN source_subgroup_index INTEGER NOT NULL DEFAULT 0"
                )
            if "source_subgroup_name" not in columns:
                conn.execute(
                    "ALTER TABLE media_playback_history ADD COLUMN source_subgroup_name TEXT NOT NULL DEFAULT ''"
                )
            if "drive_dir_id" not in columns:
                conn.execute("ALTER TABLE media_playback_history ADD COLUMN drive_dir_id TEXT NOT NULL DEFAULT ''")
            if "drive_share_key" not in columns:
                conn.execute(
                    "ALTER TABLE media_playback_history ADD COLUMN drive_share_key TEXT NOT NULL DEFAULT ''"
                )
            if "drive_path" not in columns:
                conn.execute("ALTER TABLE media_playback_history ADD COLUMN drive_path TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback_sync_state (
                    namespace TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_value TEXT NOT NULL,
                    PRIMARY KEY (namespace, state_key)
                )
                """
            )
            self._migrate_spider_plugin_history(conn)
            if "account_namespace" not in columns:
                self._migrate_account_namespace(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback_sync_snapshot (
                    namespace TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    vod_id TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (namespace, source_kind, source_key, vod_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback_sync_pending_deletions (
                    account_namespace TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    deleted_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_namespace, source_kind, source_key, vod_id)
                )
                """
            )

    def _migrate_account_namespace(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE media_playback_history_account (
                account_namespace TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL,
                source_key TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                duration INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                playlist_index INTEGER NOT NULL DEFAULT 0,
                source_group_index INTEGER NOT NULL DEFAULT 0,
                source_index INTEGER NOT NULL DEFAULT 0,
                source_subgroup_index INTEGER NOT NULL DEFAULT 0,
                source_subgroup_name TEXT NOT NULL DEFAULT '',
                drive_dir_id TEXT NOT NULL DEFAULT '',
                drive_share_key TEXT NOT NULL DEFAULT '',
                drive_path TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_namespace, source_kind, source_key, vod_id)
            )
            """
        )
        conn.execute(
                """
                INSERT INTO media_playback_history_account (
                    source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                    episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                    source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                    drive_dir_id, drive_share_key, drive_path, updated_at
                )
                SELECT source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                       episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                       source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                       drive_dir_id, drive_share_key, drive_path, updated_at
                FROM media_playback_history
                """
            )
        conn.execute("DROP TABLE media_playback_history")
        conn.execute("ALTER TABLE media_playback_history_account RENAME TO media_playback_history")

    def set_active_account(self, namespace: str) -> None:
        value = str(namespace or "").strip()
        if not value:
            raise ValueError("playback history account namespace is required")
        with self._connect() as conn:
            # 旧版本没有账户维度；首次登录时把遗留记录归属给当前账户。
            conn.execute(
                "UPDATE media_playback_history SET account_namespace = ? WHERE account_namespace = ''",
                (value,),
            )
        self._account_namespace = value

    def _migrate_spider_plugin_history(self, conn: sqlite3.Connection) -> None:
        marker = conn.execute(
            """
            SELECT 1 FROM playback_sync_state
            WHERE namespace = '__migration__' AND state_key = 'spider_plugin_history'
            """
        ).fetchone()
        if marker is not None:
            return
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        if "spider_plugin_playback_history" not in tables or "spider_plugins" not in tables:
            return
        rows = conn.execute(
            """
            SELECT history.plugin_id, history.vod_id, history.vod_name, history.vod_pic, history.vod_remarks,
                   history.episode, history.episode_url, history.position, history.opening,
                   history.ending, history.speed, history.playlist_index, history.updated_at,
                   plugin.display_name
            FROM spider_plugin_playback_history AS history
            JOIN spider_plugins AS plugin ON plugin.id = history.plugin_id
            """
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO media_playback_history (
                    source_kind, source_key, source_name, vod_id, vod_name, vod_pic,
                    vod_remarks, episode, episode_url, position, opening, ending,
                    speed, playlist_index, source_group_index, source_index, source_subgroup_index,
                    source_subgroup_name, drive_dir_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "spider_plugin",
                    str(row[0]),
                    str(row[13] or ""),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    int(row[5]),
                    row[6],
                    int(row[7]),
                    int(row[8]),
                    int(row[9]),
                    float(row[10]),
                    int(row[11]),
                    0,
                    0,
                    0,
                    "",
                    "",
                    int(row[12]),
                ),
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO playback_sync_state(namespace, state_key, state_value)
            VALUES ('__migration__', 'spider_plugin_history', '1')
            """
        )

    def get_history(self, source_kind: str, vod_id: str, source_key: str = "") -> HistoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                       episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                       source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                       drive_dir_id, drive_share_key, drive_path, updated_at
                FROM media_playback_history
                WHERE account_namespace = ? AND source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (self._account_namespace, source_kind, source_key, vod_id),
            ).fetchone()
            if row is None and source_kind == "spider_plugin" and source_key:
                row = conn.execute(
                    """
                    SELECT source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                           episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                           source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                           drive_dir_id, drive_share_key, drive_path, updated_at
                    FROM media_playback_history
                    WHERE account_namespace = ? AND source_kind = ? AND source_key = '' AND vod_id = ?
                    """,
                    (self._account_namespace, source_kind, vod_id),
                ).fetchone()
        if row is None:
            return None
        return HistoryRecord(
            id=0,
            key=row[3],
            vod_name=row[4],
            vod_pic=row[5],
            vod_remarks=row[6],
            episode=int(row[7]),
            episode_url=row[8],
            position=int(row[9]),
            duration=int(row[10]),
            opening=int(row[11]),
            ending=int(row[12]),
            speed=float(row[13]),
            playlist_index=int(row[14]),
            source_group_index=int(row[15]),
            source_index=int(row[16]),
            source_subgroup_index=int(row[17]),
            source_subgroup_name=str(row[18]),
            drive_dir_id=str(row[19]),
            drive_share_key=str(row[20]),
            drive_path=str(row[21]),
            create_time=int(row[22]),
            source_kind=str(row[0]),
            source_key=str(row[1]),
            source_name=str(row[2]),
            source_plugin_id=int(row[1]) if str(row[0]) == "spider_plugin" and str(row[1]).isdigit() else 0,
            source_plugin_name=str(row[2]) if str(row[0]) == "spider_plugin" else "",
        )

    def save_history(
        self,
        source_kind: str,
        vod_id: str,
        payload: dict[str, object],
        *,
        source_key: str = "",
        source_name: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_playback_history (
                    account_namespace, source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                    episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                    source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                    drive_dir_id, drive_share_key, drive_path, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_namespace, source_kind, source_key, vod_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    vod_name = excluded.vod_name,
                    vod_pic = excluded.vod_pic,
                    vod_remarks = excluded.vod_remarks,
                    episode = excluded.episode,
                    episode_url = excluded.episode_url,
                    position = excluded.position,
                    duration = excluded.duration,
                    opening = excluded.opening,
                    ending = excluded.ending,
                    speed = excluded.speed,
                    playlist_index = excluded.playlist_index,
                    source_group_index = excluded.source_group_index,
                    source_index = excluded.source_index,
                    source_subgroup_index = excluded.source_subgroup_index,
                    source_subgroup_name = excluded.source_subgroup_name,
                    drive_dir_id = excluded.drive_dir_id,
                    drive_share_key = excluded.drive_share_key,
                    drive_path = excluded.drive_path,
                    updated_at = excluded.updated_at
                WHERE source_name <> excluded.source_name
                   OR vod_name <> excluded.vod_name
                   OR vod_pic <> excluded.vod_pic
                   OR vod_remarks <> excluded.vod_remarks
                   OR episode <> excluded.episode
                   OR episode_url <> excluded.episode_url
                   OR position <> excluded.position
                   OR duration <> excluded.duration
                   OR opening <> excluded.opening
                   OR ending <> excluded.ending
                   OR speed <> excluded.speed
                   OR playlist_index <> excluded.playlist_index
                   OR source_group_index <> excluded.source_group_index
                   OR source_index <> excluded.source_index
                   OR source_subgroup_index <> excluded.source_subgroup_index
                   OR source_subgroup_name <> excluded.source_subgroup_name
                   OR drive_dir_id <> excluded.drive_dir_id
                   OR drive_share_key <> excluded.drive_share_key
                   OR drive_path <> excluded.drive_path
                """,
                (
                    self._account_namespace,
                    source_kind,
                    source_key,
                    source_name,
                    vod_id,
                    str(payload.get("vodName", "")),
                    str(payload.get("vodPic", "")),
                    str(payload.get("vodRemarks", "")),
                    int(payload.get("episode", 0)),
                    str(payload.get("episodeUrl", "")),
                    int(payload.get("position", 0)),
                    int(payload.get("duration", 0)),
                    int(payload.get("opening", 0)),
                    int(payload.get("ending", 0)),
                    float(payload.get("speed", 1.0)),
                    int(payload.get("playlistIndex", 0)),
                    int(payload.get("sourceGroupIndex", 0)),
                    int(payload.get("sourceIndex", 0)),
                    int(payload.get("sourceSubgroupIndex", 0)),
                    str(payload.get("sourceSubgroupName", "")),
                    str(payload.get("driveDirId", "")),
                    str(payload.get("driveShareKey", "")),
                    str(payload.get("drivePath", "")),
                    int(payload.get("createTime", 0)),
                ),
            )

    def list_histories(self) -> list[HistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
                       episode, episode_url, position, duration, opening, ending, speed, playlist_index,
                       source_group_index, source_index, source_subgroup_index, source_subgroup_name,
                       drive_dir_id, drive_share_key, drive_path, updated_at
                FROM media_playback_history
                WHERE account_namespace = ?
                """,
                (self._account_namespace,),
            ).fetchall()
        return [
            HistoryRecord(
                id=0,
                key=row[3],
                vod_name=row[4],
                vod_pic=row[5],
                vod_remarks=row[6],
                episode=int(row[7]),
                episode_url=row[8],
                position=int(row[9]),
                duration=int(row[10]),
                opening=int(row[11]),
                ending=int(row[12]),
                speed=float(row[13]),
                playlist_index=int(row[14]),
                source_group_index=int(row[15]),
                source_index=int(row[16]),
                source_subgroup_index=int(row[17]),
                source_subgroup_name=str(row[18]),
                drive_dir_id=str(row[19]),
                drive_share_key=str(row[20]),
                drive_path=str(row[21]),
                create_time=int(row[22]),
                source_kind=str(row[0]),
                source_key=str(row[1]),
                source_name=str(row[2]),
                source_plugin_id=int(row[1]) if str(row[0]) == "spider_plugin" and str(row[1]).isdigit() else 0,
                source_plugin_name=str(row[2]) if str(row[0]) == "spider_plugin" else "",
            )
            for row in rows
        ]

    def delete_history(self, source_kind: str, vod_id: str, source_key: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM media_playback_history WHERE account_namespace = ? AND source_kind = ? AND source_key = ? AND vod_id = ?",
                (self._account_namespace, source_kind, source_key, vod_id),
            )

    def delete_site_history(self, source_kind: str, source_key: str, deleted_at: int) -> list[tuple[str, str, str]]:
        clause = "account_namespace = ? AND source_kind = ? AND source_key = ?"
        args: list[object] = [self._account_namespace, source_kind, source_key]
        if deleted_at > 0:
            clause += " AND updated_at <= ?"
            args.append(deleted_at)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT source_kind, source_key, vod_id FROM media_playback_history WHERE {clause}",
                args,
            ).fetchall()
            conn.execute(f"DELETE FROM media_playback_history WHERE {clause}", args)
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]

    def delete_all_histories(self, deleted_at: int) -> list[tuple[str, str, str]]:
        clause = "account_namespace = ?"
        args: list[object] = [self._account_namespace]
        if deleted_at > 0:
            clause += " AND updated_at <= ?"
            args.append(deleted_at)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT source_kind, source_key, vod_id FROM media_playback_history WHERE {clause}",
                args,
            ).fetchall()
            conn.execute(f"DELETE FROM media_playback_history WHERE {clause}", args)
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]

    def get_sync_cursor(self, namespace: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_value FROM playback_sync_state WHERE namespace = ? AND state_key = 'cursor'",
                (namespace,),
            ).fetchone()
        try:
            return int(row[0]) if row is not None else 0
        except (TypeError, ValueError):
            return 0

    def set_sync_cursor(self, namespace: str, cursor: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playback_sync_state(namespace, state_key, state_value) VALUES (?, 'cursor', ?)
                ON CONFLICT(namespace, state_key) DO UPDATE SET state_value = excluded.state_value
                """,
                (namespace, str(cursor)),
            )

    def load_sync_snapshot(self, namespace: str) -> dict[tuple[str, str, str], int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, updated_at
                FROM playback_sync_snapshot WHERE namespace = ?
                """,
                (namespace,),
            ).fetchall()
        return {(str(row[0]), str(row[1]), str(row[2])): int(row[3]) for row in rows}

    def replace_sync_snapshot(self, namespace: str, versions: dict[tuple[str, str, str], int]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM playback_sync_snapshot WHERE namespace = ?", (namespace,))
            conn.executemany(
                """
                INSERT INTO playback_sync_snapshot(namespace, source_kind, source_key, vod_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(namespace, *identity, updated_at) for identity, updated_at in versions.items()],
            )

    def set_sync_snapshot_version(
        self,
        namespace: str,
        identity: tuple[str, str, str],
        updated_at: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playback_sync_snapshot(namespace, source_kind, source_key, vod_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace, source_kind, source_key, vod_id)
                DO UPDATE SET updated_at = excluded.updated_at
                """,
                (namespace, *identity, updated_at),
            )

    def remove_sync_snapshot(self, namespace: str, identity: tuple[str, str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM playback_sync_snapshot
                WHERE namespace = ? AND source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (namespace, *identity),
            )

    def record_pending_deletion(
        self, source_kind: str, source_key: str, vod_id: str, deleted_at: int
    ) -> None:
        """记录一条用户显式删除,待下次同步 PUSH 转成服务端 tombstone(替代旧的 list 差集推断)。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playback_sync_pending_deletions
                    (account_namespace, source_kind, source_key, vod_id, deleted_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_namespace, source_kind, source_key, vod_id)
                DO UPDATE SET deleted_at = excluded.deleted_at
                """,
                (self._account_namespace, source_kind, source_key, vod_id, int(deleted_at)),
            )

    def list_pending_deletions(self) -> list[tuple[str, str, str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, deleted_at
                FROM playback_sync_pending_deletions WHERE account_namespace = ?
                """,
                (self._account_namespace,),
            ).fetchall()
        return [(str(row[0]), str(row[1]), str(row[2]), int(row[3])) for row in rows]

    def clear_pending_deletions(self, items: list[tuple[str, str, str]]) -> None:
        if not items:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                DELETE FROM playback_sync_pending_deletions
                WHERE account_namespace = ? AND source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                [
                    (self._account_namespace, source_kind, source_key, vod_id)
                    for source_kind, source_key, vod_id in items
                ],
            )
