from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    FollowingSourceBinding,
)
from atv_player.sqlite_utils import managed_connection


def _json_loads(value: object, fallback: Any) -> Any:
    try:
        loaded = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return loaded if loaded is not None else fallback


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _binding_to_dict(binding: FollowingSourceBinding) -> dict[str, str]:
    return {
        "source_kind": binding.source_kind,
        "source_key": binding.source_key,
        "source_name": binding.source_name,
        "vod_id": binding.vod_id,
        "provider": binding.provider,
        "provider_id": binding.provider_id,
    }


def _binding_from_dict(value: object) -> FollowingSourceBinding:
    data = value if isinstance(value, dict) else {}
    return FollowingSourceBinding(
        source_kind=str(data.get("source_kind") or ""),
        source_key=str(data.get("source_key") or ""),
        source_name=str(data.get("source_name") or ""),
        vod_id=str(data.get("vod_id") or ""),
        provider=str(data.get("provider") or ""),
        provider_id=str(data.get("provider_id") or ""),
    )


def _episode_to_dict(episode: FollowingEpisode) -> dict[str, object]:
    return {
        "episode_number": episode.episode_number,
        "season_number": episode.season_number,
        "title": episode.title,
        "overview": episode.overview,
        "air_date": episode.air_date,
        "still": episode.still,
        "runtime": episode.runtime,
        "is_special": episode.is_special,
    }


def _episode_from_dict(value: object) -> FollowingEpisode:
    data = value if isinstance(value, dict) else {}
    return FollowingEpisode(
        episode_number=int(data.get("episode_number") or 0),
        season_number=int(data.get("season_number") or 0),
        title=str(data.get("title") or ""),
        overview=str(data.get("overview") or ""),
        air_date=str(data.get("air_date") or ""),
        still=str(data.get("still") or ""),
        runtime=int(data.get("runtime") or 0),
        is_special=bool(data.get("is_special", False)),
    )


class FollowingRepository:
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
                CREATE TABLE IF NOT EXISTS following (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    original_title TEXT NOT NULL DEFAULT '',
                    media_kind TEXT NOT NULL DEFAULT '',
                    season_number INTEGER NOT NULL DEFAULT 0,
                    poster TEXT NOT NULL DEFAULT '',
                    backdrop TEXT NOT NULL DEFAULT '',
                    rating TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT '',
                    provider_id TEXT NOT NULL DEFAULT '',
                    provider_priority_json TEXT NOT NULL DEFAULT '[]',
                    external_ids_json TEXT NOT NULL DEFAULT '{}',
                    source_bindings_json TEXT NOT NULL DEFAULT '[]',
                    current_episode INTEGER NOT NULL DEFAULT 0,
                    position_seconds INTEGER NOT NULL DEFAULT 0,
                    watched_latest_episode INTEGER NOT NULL DEFAULT 0,
                    latest_episode INTEGER NOT NULL DEFAULT 0,
                    previous_latest_episode INTEGER NOT NULL DEFAULT 0,
                    total_episodes INTEGER NOT NULL DEFAULT 0,
                    has_update INTEGER NOT NULL DEFAULT 0,
                    new_episode_count INTEGER NOT NULL DEFAULT 0,
                    homepage_prompt_pending INTEGER NOT NULL DEFAULT 0,
                    prompt_snoozed_until INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    last_played_at INTEGER NOT NULL DEFAULT 0,
                    last_checked_at INTEGER NOT NULL DEFAULT 0,
                    next_check_after INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    UNIQUE(provider, provider_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS following_detail_snapshots (
                    following_id INTEGER PRIMARY KEY,
                    overview TEXT NOT NULL DEFAULT '',
                    cast_json TEXT NOT NULL DEFAULT '[]',
                    crew_json TEXT NOT NULL DEFAULT '[]',
                    episodes_json TEXT NOT NULL DEFAULT '[]',
                    posters_json TEXT NOT NULL DEFAULT '[]',
                    backdrops_json TEXT NOT NULL DEFAULT '[]',
                    refreshed_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def upsert(self, record: FollowingRecord) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO following (
                    title, original_title, media_kind, season_number, poster, backdrop, rating,
                    provider, provider_id, provider_priority_json, external_ids_json, source_bindings_json,
                    current_episode, position_seconds, watched_latest_episode, latest_episode,
                    previous_latest_episode, total_episodes, has_update, new_episode_count,
                    homepage_prompt_pending, prompt_snoozed_until, created_at, updated_at,
                    last_played_at, last_checked_at, next_check_after, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_id) DO UPDATE SET
                    title = excluded.title,
                    original_title = excluded.original_title,
                    media_kind = excluded.media_kind,
                    season_number = excluded.season_number,
                    poster = excluded.poster,
                    backdrop = excluded.backdrop,
                    rating = excluded.rating,
                    provider_priority_json = excluded.provider_priority_json,
                    external_ids_json = excluded.external_ids_json,
                    source_bindings_json = excluded.source_bindings_json,
                    current_episode = excluded.current_episode,
                    position_seconds = excluded.position_seconds,
                    watched_latest_episode = excluded.watched_latest_episode,
                    latest_episode = excluded.latest_episode,
                    previous_latest_episode = excluded.previous_latest_episode,
                    total_episodes = excluded.total_episodes,
                    has_update = excluded.has_update,
                    new_episode_count = excluded.new_episode_count,
                    homepage_prompt_pending = excluded.homepage_prompt_pending,
                    prompt_snoozed_until = excluded.prompt_snoozed_until,
                    updated_at = excluded.updated_at,
                    last_played_at = excluded.last_played_at,
                    last_checked_at = excluded.last_checked_at,
                    next_check_after = excluded.next_check_after,
                    last_error = excluded.last_error
                """,
                self._record_params(record),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            row = conn.execute(
                "SELECT id FROM following WHERE provider = ? AND provider_id = ?",
                (record.provider, record.provider_id),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def get(self, record_id: int) -> FollowingRecord | None:
        with self._connect() as conn:
            row = conn.execute(f"{self._select_sql()} WHERE id = ?", (record_id,)).fetchone()
        return self._record_from_row(row) if row is not None else None

    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool) -> tuple[list[FollowingRecord], int]:
        clauses: list[str] = []
        params: list[object] = []
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            clauses.append("(title LIKE ? OR original_title LIKE ?)")
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        if only_updates:
            clauses.append("has_update = 1")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = max(page - 1, 0) * size
        with self._connect() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM following {where_sql}", params).fetchone()[0])
            rows = conn.execute(
                f"""
                {self._select_sql()}
                {where_sql}
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, size, offset],
            ).fetchall()
        return [self._record_from_row(row) for row in rows], total

    def delete(self, record_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM following_detail_snapshots WHERE following_id = ?", (record_id,))
            conn.execute("DELETE FROM following WHERE id = ?", (record_id,))

    def save_detail_snapshot(self, following_id: int, snapshot: FollowingDetailSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO following_detail_snapshots (
                    following_id, overview, cast_json, crew_json, episodes_json,
                    posters_json, backdrops_json, refreshed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(following_id) DO UPDATE SET
                    overview = excluded.overview,
                    cast_json = excluded.cast_json,
                    crew_json = excluded.crew_json,
                    episodes_json = excluded.episodes_json,
                    posters_json = excluded.posters_json,
                    backdrops_json = excluded.backdrops_json,
                    refreshed_at = excluded.refreshed_at
                """,
                (
                    following_id,
                    snapshot.overview,
                    _json_dumps(snapshot.cast),
                    _json_dumps(snapshot.crew),
                    _json_dumps([_episode_to_dict(episode) for episode in snapshot.episodes]),
                    _json_dumps(snapshot.posters),
                    _json_dumps(snapshot.backdrops),
                    snapshot.refreshed_at,
                ),
            )

    def get_detail_snapshot(self, following_id: int) -> FollowingDetailSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT following_id, overview, cast_json, crew_json, episodes_json,
                       posters_json, backdrops_json, refreshed_at
                FROM following_detail_snapshots
                WHERE following_id = ?
                """,
                (following_id,),
            ).fetchone()
        if row is None:
            return None
        return FollowingDetailSnapshot(
            following_id=int(row[0]),
            overview=str(row[1]),
            cast=list(_json_loads(row[2], [])),
            crew=list(_json_loads(row[3], [])),
            episodes=[_episode_from_dict(item) for item in _json_loads(row[4], [])],
            posters=[str(item) for item in _json_loads(row[5], [])],
            backdrops=[str(item) for item in _json_loads(row[6], [])],
            refreshed_at=int(row[7]),
        )

    def update_progress(
        self,
        following_id: int,
        *,
        current_episode: int,
        position_seconds: int,
        last_played_at: int,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT latest_episode FROM following WHERE id = ?", (following_id,)).fetchone()
            if row is None:
                return
            latest_episode = int(row[0] or 0)
            watched_latest = latest_episode > 0 and current_episode >= latest_episode
            conn.execute(
                """
                UPDATE following
                SET current_episode = ?, position_seconds = ?, last_played_at = ?,
                    watched_latest_episode = ?, homepage_prompt_pending = CASE WHEN ? THEN 0 ELSE homepage_prompt_pending END
                WHERE id = ?
                """,
                (
                    current_episode,
                    position_seconds,
                    last_played_at,
                    1 if watched_latest else 0,
                    1 if watched_latest else 0,
                    following_id,
                ),
            )

    def update_check_state(
        self,
        following_id: int,
        *,
        latest_episode: int,
        total_episodes: int,
        checked_at: int,
        next_check_after: int,
        has_update: bool,
        new_episode_count: int,
        homepage_prompt_pending: bool,
        last_error: str,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT latest_episode FROM following WHERE id = ?", (following_id,)).fetchone()
            if row is None:
                return
            previous = int(row[0] or 0)
            conn.execute(
                """
                UPDATE following
                SET previous_latest_episode = ?, latest_episode = ?, total_episodes = ?,
                    last_checked_at = ?, next_check_after = ?, has_update = ?, new_episode_count = ?,
                    homepage_prompt_pending = ?, last_error = ?
                WHERE id = ?
                """,
                (
                    previous,
                    latest_episode,
                    total_episodes,
                    checked_at,
                    next_check_after,
                    1 if has_update else 0,
                    new_episode_count,
                    1 if homepage_prompt_pending else 0,
                    last_error,
                    following_id,
                ),
            )

    def load_due_records(self, *, now: int, limit: int) -> list[FollowingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                {self._select_sql()}
                WHERE next_check_after <= ?
                ORDER BY next_check_after ASC, updated_at DESC, id ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def load_homepage_prompt_records(self, *, now: int) -> list[FollowingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                {self._select_sql()}
                WHERE homepage_prompt_pending = 1 AND prompt_snoozed_until <= ?
                ORDER BY updated_at DESC, id ASC
                """,
                (now,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def clear_homepage_prompt(self, following_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE following SET homepage_prompt_pending = 0 WHERE id = ?", (following_id,))

    def snooze_prompt(self, following_id: int, *, until: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE following SET homepage_prompt_pending = 0, prompt_snoozed_until = ? WHERE id = ?",
                (until, following_id),
            )

    def _record_params(self, record: FollowingRecord) -> tuple[object, ...]:
        return (
            record.title,
            record.original_title,
            record.media_kind,
            record.season_number,
            record.poster,
            record.backdrop,
            record.rating,
            record.provider,
            record.provider_id,
            _json_dumps(record.provider_priority),
            _json_dumps(record.external_ids),
            _json_dumps([_binding_to_dict(binding) for binding in record.source_bindings]),
            record.current_episode,
            record.position_seconds,
            1 if record.watched_latest_episode else 0,
            record.latest_episode,
            record.previous_latest_episode,
            record.total_episodes,
            1 if record.has_update else 0,
            record.new_episode_count,
            1 if record.homepage_prompt_pending else 0,
            record.prompt_snoozed_until,
            record.created_at,
            record.updated_at,
            record.last_played_at,
            record.last_checked_at,
            record.next_check_after,
            record.last_error,
        )

    def _record_from_row(self, row) -> FollowingRecord:
        return FollowingRecord(
            id=int(row[0]),
            title=str(row[1]),
            original_title=str(row[2]),
            media_kind=str(row[3]),
            season_number=int(row[4]),
            poster=str(row[5]),
            backdrop=str(row[6]),
            rating=str(row[7]),
            provider=str(row[8]),
            provider_id=str(row[9]),
            provider_priority=[str(item) for item in _json_loads(row[10], [])],
            external_ids={str(key): str(value) for key, value in dict(_json_loads(row[11], {})).items()},
            source_bindings=[_binding_from_dict(item) for item in _json_loads(row[12], [])],
            current_episode=int(row[13]),
            position_seconds=int(row[14]),
            watched_latest_episode=bool(row[15]),
            latest_episode=int(row[16]),
            previous_latest_episode=int(row[17]),
            total_episodes=int(row[18]),
            has_update=bool(row[19]),
            new_episode_count=int(row[20]),
            homepage_prompt_pending=bool(row[21]),
            prompt_snoozed_until=int(row[22]),
            created_at=int(row[23]),
            updated_at=int(row[24]),
            last_played_at=int(row[25]),
            last_checked_at=int(row[26]),
            next_check_after=int(row[27]),
            last_error=str(row[28]),
        )

    def _select_sql(self) -> str:
        return """
            SELECT id, title, original_title, media_kind, season_number, poster, backdrop,
                   rating, provider, provider_id, provider_priority_json, external_ids_json,
                   source_bindings_json, current_episode, position_seconds, watched_latest_episode,
                   latest_episode, previous_latest_episode, total_episodes, has_update,
                   new_episode_count, homepage_prompt_pending, prompt_snoozed_until,
                   created_at, updated_at, last_played_at, last_checked_at, next_check_after,
                   last_error
            FROM following
        """
