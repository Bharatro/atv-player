from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from atv_player.models import HistoryRecord, SpiderPluginConfig, SpiderPluginLogEntry
from atv_player.sqlite_utils import managed_connection


def _require_lastrowid(cursor: sqlite3.Cursor) -> int:
    lastrowid = cursor.lastrowid
    if lastrowid is None:
        raise RuntimeError("插入插件记录后缺少 lastrowid")
    return int(lastrowid)


class SpiderPluginRepository:
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
                CREATE TABLE IF NOT EXISTS spider_plugins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL,
                    cached_file_path TEXT NOT NULL DEFAULT '',
                    last_loaded_at INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    config_text TEXT NOT NULL DEFAULT '',
                    plugin_version INTEGER NOT NULL DEFAULT 1,
                    category_overrides_json TEXT NOT NULL DEFAULT '',
                    manifest_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            plugin_columns = {row[1] for row in conn.execute("PRAGMA table_info(spider_plugins)").fetchall()}
            if "config_text" not in plugin_columns:
                conn.execute("ALTER TABLE spider_plugins ADD COLUMN config_text TEXT NOT NULL DEFAULT ''")
            if "plugin_version" not in plugin_columns:
                conn.execute("ALTER TABLE spider_plugins ADD COLUMN plugin_version INTEGER NOT NULL DEFAULT 1")
            if "category_overrides_json" not in plugin_columns:
                conn.execute("ALTER TABLE spider_plugins ADD COLUMN category_overrides_json TEXT NOT NULL DEFAULT ''")
            if "manifest_id" not in plugin_columns:
                conn.execute("ALTER TABLE spider_plugins ADD COLUMN manifest_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spider_plugin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spider_plugin_playback_history (
                    plugin_id INTEGER NOT NULL,
                    vod_id TEXT NOT NULL,
                    vod_name TEXT NOT NULL DEFAULT '',
                    vod_pic TEXT NOT NULL DEFAULT '',
                    vod_remarks TEXT NOT NULL DEFAULT '',
                    episode INTEGER NOT NULL DEFAULT 0,
                    episode_url TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL DEFAULT 0,
                    opening INTEGER NOT NULL DEFAULT 0,
                    ending INTEGER NOT NULL DEFAULT 0,
                    speed REAL NOT NULL DEFAULT 1.0,
                    playlist_index INTEGER NOT NULL DEFAULT 0,
                    source_group_index INTEGER NOT NULL DEFAULT 0,
                    source_index INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (plugin_id, vod_id)
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(spider_plugin_playback_history)").fetchall()
            }
            if "playlist_index" not in columns:
                conn.execute(
                    "ALTER TABLE spider_plugin_playback_history ADD COLUMN playlist_index INTEGER NOT NULL DEFAULT 0"
                )
            if "source_group_index" not in columns:
                conn.execute(
                    "ALTER TABLE spider_plugin_playback_history ADD COLUMN source_group_index INTEGER NOT NULL DEFAULT 0"
                )
            if "source_index" not in columns:
                conn.execute(
                    "ALTER TABLE spider_plugin_playback_history ADD COLUMN source_index INTEGER NOT NULL DEFAULT 0"
                )

    def add_plugin(
        self,
        source_type: str,
        source_value: str,
        display_name: str,
        *,
        enabled: bool = True,
        plugin_version: int = 1,
        manifest_id: str = "",
    ) -> SpiderPluginConfig:
        with self._connect() as conn:
            next_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM spider_plugins"
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO spider_plugins (
                    source_type, source_value, display_name, enabled, sort_order,
                    cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
                    category_overrides_json, manifest_id
                )
                VALUES (?, ?, ?, ?, ?, '', 0, '', '', ?, '', ?)
                """,
                (source_type, source_value, display_name, int(enabled), next_order, int(plugin_version), manifest_id),
            )
        return self.get_plugin(_require_lastrowid(cursor))

    def get_plugin(self, plugin_id: int) -> SpiderPluginConfig:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_type, source_value, display_name, enabled, sort_order,
                       cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
                       category_overrides_json, manifest_id
                FROM spider_plugins
                WHERE id = ?
                """,
                (plugin_id,),
            ).fetchone()
        assert row is not None
        values = list(row)
        values[4] = bool(values[4])
        values[10] = int(values[10])
        return SpiderPluginConfig(*values)

    def list_plugins(self) -> list[SpiderPluginConfig]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_type, source_value, display_name, enabled, sort_order,
                       cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
                       category_overrides_json, manifest_id
                FROM spider_plugins
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()
        plugins: list[SpiderPluginConfig] = []
        for row in rows:
            values = list(row)
            values[4] = bool(values[4])
            values[10] = int(values[10])
            plugins.append(SpiderPluginConfig(*values))
        return plugins

    def update_plugin(
        self,
        plugin_id: int,
        *,
        display_name: str,
        enabled: bool,
        cached_file_path: str,
        last_loaded_at: int,
        last_error: str,
        config_text: str,
        plugin_version: int = 1,
        category_overrides_json: str | None = None,
        source_type: str | None = None,
        source_value: str | None = None,
        manifest_id: str | None = None,
    ) -> None:
        current = None
        if (
            category_overrides_json is None
            or source_type is None
            or source_value is None
            or manifest_id is None
        ):
            current = self.get_plugin(plugin_id)
        if category_overrides_json is None:
            assert current is not None
            category_overrides_json = current.category_overrides_json
        if source_type is None:
            assert current is not None
            source_type = current.source_type
        if source_value is None:
            assert current is not None
            source_value = current.source_value
        if manifest_id is None:
            assert current is not None
            manifest_id = current.manifest_id
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE spider_plugins
                SET source_type = ?, source_value = ?, display_name = ?, enabled = ?, cached_file_path = ?,
                    last_loaded_at = ?, last_error = ?, config_text = ?, plugin_version = ?,
                    category_overrides_json = ?, manifest_id = ?
                WHERE id = ?
                """,
                (
                    source_type,
                    source_value,
                    display_name,
                    int(enabled),
                    cached_file_path,
                    last_loaded_at,
                    last_error,
                    config_text,
                    int(plugin_version),
                    category_overrides_json,
                    manifest_id,
                    plugin_id,
                ),
            )

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE spider_plugins SET display_name = ? WHERE id = ?",
                (display_name, plugin_id),
            )

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE spider_plugins SET enabled = ? WHERE id = ?",
                (int(enabled), plugin_id),
            )

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE spider_plugins SET config_text = ? WHERE id = ?",
                (config_text, plugin_id),
            )

    def set_plugin_category_overrides(self, plugin_id: int, category_overrides_json: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE spider_plugins SET category_overrides_json = ? WHERE id = ?",
                (category_overrides_json, plugin_id),
            )

    def find_plugin_by_source_value(self, source_value: str) -> SpiderPluginConfig | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_type, source_value, display_name, enabled, sort_order,
                       cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
                       category_overrides_json, manifest_id
                FROM spider_plugins
                WHERE source_value = ?
                """,
                (source_value,),
            ).fetchone()
        if row is None:
            return None
        values = list(row)
        values[4] = bool(values[4])
        values[10] = int(values[10])
        return SpiderPluginConfig(*values)

    def find_plugin_by_manifest_id(self, manifest_id: str) -> SpiderPluginConfig | None:
        if not manifest_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_type, source_value, display_name, enabled, sort_order,
                       cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
                       category_overrides_json, manifest_id
                FROM spider_plugins
                WHERE manifest_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (manifest_id,),
            ).fetchone()
        if row is None:
            return None
        values = list(row)
        values[4] = bool(values[4])
        values[10] = int(values[10])
        return SpiderPluginConfig(*values)

    def move_plugin(self, plugin_id: int, direction: int) -> None:
        plugins = self.list_plugins()
        index = next(i for i, item in enumerate(plugins) if item.id == plugin_id)
        target = index + direction
        if not (0 <= target < len(plugins)):
            return
        plugins[index], plugins[target] = plugins[target], plugins[index]
        with self._connect() as conn:
            for order, item in enumerate(plugins):
                conn.execute(
                    "UPDATE spider_plugins SET sort_order = ? WHERE id = ?",
                    (order, item.id),
                )

    def reorder_plugins(self, plugin_ids_in_order: list[int]) -> None:
        plugins = self.list_plugins()
        current_ids = [item.id for item in plugins]
        if sorted(plugin_ids_in_order) != sorted(current_ids):
            raise ValueError("插件列表已变化，请重新打开排序窗口")
        ordered_plugins = {item.id: item for item in plugins}
        with self._connect() as conn:
            for order, plugin_id in enumerate(plugin_ids_in_order):
                conn.execute(
                    "UPDATE spider_plugins SET sort_order = ? WHERE id = ?",
                    (order, ordered_plugins[plugin_id].id),
                )

    def delete_plugin(self, plugin_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM spider_plugin_playback_history WHERE plugin_id = ?", (plugin_id,))
            conn.execute("DELETE FROM spider_plugin_logs WHERE plugin_id = ?", (plugin_id,))
            conn.execute("DELETE FROM spider_plugins WHERE id = ?", (plugin_id,))

    def get_playback_history(self, plugin_id: int, vod_id: str) -> HistoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT vod_id, vod_name, vod_pic, vod_remarks, episode, episode_url,
                       position, opening, ending, speed, playlist_index,
                       source_group_index, source_index, updated_at
                FROM spider_plugin_playback_history
                WHERE plugin_id = ? AND vod_id = ?
                """,
                (plugin_id, vod_id),
            ).fetchone()
        if row is None:
            return None
        return HistoryRecord(
            id=0,
            key=row[0],
            vod_name=row[1],
            vod_pic=row[2],
            vod_remarks=row[3],
            episode=int(row[4]),
            episode_url=row[5],
            position=int(row[6]),
            opening=int(row[7]),
            ending=int(row[8]),
            speed=float(row[9]),
            playlist_index=int(row[10]),
            source_group_index=int(row[11]),
            source_index=int(row[12]),
            create_time=int(row[13]),
        )

    def list_playback_histories(self) -> list[HistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT history.vod_id, history.vod_name, history.vod_pic, history.vod_remarks,
                       history.episode, history.episode_url, history.position, history.opening,
                       history.ending, history.speed, history.playlist_index,
                       history.source_group_index, history.source_index, history.updated_at,
                       plugin.id, plugin.display_name
                FROM spider_plugin_playback_history AS history
                JOIN spider_plugins AS plugin ON plugin.id = history.plugin_id
                """
            ).fetchall()
        return [
            HistoryRecord(
                id=0,
                key=row[0],
                vod_name=row[1],
                vod_pic=row[2],
                vod_remarks=row[3],
                episode=int(row[4]),
                episode_url=row[5],
                position=int(row[6]),
                opening=int(row[7]),
                ending=int(row[8]),
                speed=float(row[9]),
                playlist_index=int(row[10]),
                source_group_index=int(row[11]),
                source_index=int(row[12]),
                create_time=int(row[13]),
                source_kind="spider_plugin",
                source_plugin_id=int(row[14]),
                source_plugin_name=str(row[15] or ""),
            )
            for row in rows
        ]

    def delete_playback_history(self, plugin_id: int, vod_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM spider_plugin_playback_history WHERE plugin_id = ? AND vod_id = ?",
                (plugin_id, vod_id),
            )

    def save_playback_history(self, plugin_id: int, vod_id: str, payload: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO spider_plugin_playback_history (
                    plugin_id, vod_id, vod_name, vod_pic, vod_remarks,
                    episode, episode_url, position, opening, ending, speed, playlist_index,
                    source_group_index, source_index, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plugin_id, vod_id) DO UPDATE SET
                    vod_name = excluded.vod_name,
                    vod_pic = excluded.vod_pic,
                    vod_remarks = excluded.vod_remarks,
                    episode = excluded.episode,
                    episode_url = excluded.episode_url,
                    position = excluded.position,
                    opening = excluded.opening,
                    ending = excluded.ending,
                    speed = excluded.speed,
                    playlist_index = excluded.playlist_index,
                    source_group_index = excluded.source_group_index,
                    source_index = excluded.source_index,
                    updated_at = excluded.updated_at
                """,
                (
                    plugin_id,
                    vod_id,
                    str(payload.get("vodName", "")),
                    str(payload.get("vodPic", "")),
                    str(payload.get("vodRemarks", "")),
                    int(payload.get("episode", 0)),
                    str(payload.get("episodeUrl", "")),
                    int(payload.get("position", 0)),
                    int(payload.get("opening", 0)),
                    int(payload.get("ending", 0)),
                    float(payload.get("speed", 1.0)),
                    int(payload.get("playlistIndex", 0)),
                    int(payload.get("sourceGroupIndex", 0)),
                    int(payload.get("sourceIndex", 0)),
                    int(payload.get("createTime", 0)),
                ),
            )

    def append_log(self, plugin_id: int, level: str, message: str, created_at: int | None = None) -> None:
        timestamp = int(time.time()) if created_at is None else created_at
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO spider_plugin_logs (plugin_id, level, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (plugin_id, level, message, timestamp),
            )

    def list_logs(self, plugin_id: int) -> list[SpiderPluginLogEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, plugin_id, level, message, created_at
                FROM spider_plugin_logs
                WHERE plugin_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (plugin_id,),
            ).fetchall()
        return [SpiderPluginLogEntry(*row) for row in rows]
