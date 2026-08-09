# ruff: noqa: E501
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from time import time
from typing import Any

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)

# 多端播放记录同步:周期性 PUSH 本地 Tier-B 记录 + PULL 服务端变更。
# Tier-A(browse/douban/pansou)已由 /api/history 同步,本服务只覆盖 Tier-B
# (spider_plugin/telegram/bilibili/youtube/emby/jellyfin/feiniu/direct_parse)。
# 鉴权复用 ApiClient 的 session 令牌(Authorization),服务端 resolveUid 解析为 uid。
INITIAL_DELAY_MS = 30_000
PERIOD_MS = 30_000
SYNC_SOURCE_KINDS = frozenset(
    {
        "telegram",
        "telegram_channel",
        "bilibili",
        "youtube",
        "emby",
        "jellyfin",
        "feiniu",
        "direct_parse",
        "spider_plugin",
    }
)
SYNC_NAMESPACE_VERSION = "v4-playurl-selection-context"
SYNC_LIMIT = 100
SourceKeyResolver = Callable[[str, str], str | None]


class PlaybackHistorySyncService(QObject):
    def __init__(
        self,
        api_client,
        repository,
        *,
        installation_id: str = "",
        to_sync_source_key: SourceKeyResolver | None = None,
        to_local_source_key: SourceKeyResolver | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._api = api_client
        self._repo = repository
        self._client_key = installation_id
        identity = str(getattr(api_client, "playback_sync_identity", "") or "default")
        self._namespace = f"{identity}:{SYNC_NAMESPACE_VERSION}"
        self._sync_key_resolver = to_sync_source_key or self._default_source_key_resolver
        self._local_key_resolver = to_local_source_key or self._default_source_key_resolver
        self._unmapped_plugins: set[tuple[str, str]] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sync)
        load_snapshot = getattr(self._repo, "load_sync_snapshot", lambda _namespace: {})
        load_cursor = getattr(self._repo, "get_sync_cursor", lambda _namespace: 0)
        self._pushed_versions: dict[tuple[str, str, str], int] = load_snapshot(self._namespace)
        self._pull_cursor = load_cursor(self._namespace)
        self._sync_lock = threading.Lock()
        self._sync_in_progress = False
        self._started = False

    def start(self) -> None:
        self._started = True
        QTimer.singleShot(INITIAL_DELAY_MS, self.sync)
        self._timer.start(PERIOD_MS)
        logger.info(
            "playback sync started: initial_delay_ms=%d period_ms=%d cursor=%s snapshot=%d",
            INITIAL_DELAY_MS,
            PERIOD_MS,
            self._pull_cursor,
            len(self._pushed_versions),
        )

    def stop(self) -> None:
        self._started = False
        self._timer.stop()

    def sync(self) -> None:
        """Schedule one sync without blocking the Qt event loop.

        The repository opens a SQLite connection per operation, and ApiClient's
        HTTP client is safe to use from this worker thread.  Keeping the whole
        sync sequence in one worker also keeps its cursors and version snapshots
        single-threaded.
        """
        if not self._started:
            return
        with self._sync_lock:
            if self._sync_in_progress:
                return
            self._sync_in_progress = True
        threading.Thread(
            target=self._run_sync,
            name="playback-history-sync",
            daemon=True,
        ).start()

    def _run_sync(self) -> None:
        try:
            push_succeeded = True
            try:
                self._push()
            except Exception as exc:  # noqa: BLE001 - 后台同步不能让异常冒泡到 Qt
                push_succeeded = False
                logger.warning("playback sync push failed: %s", exc)
            if self._started and push_succeeded:
                try:
                    self._pull()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("playback sync pull failed: %s", exc)
        finally:
            with self._sync_lock:
                self._sync_in_progress = False

    # ── PUSH:本地 Tier-B → 服务端 ──────────────────────────────────────────

    def _push(self) -> None:
        all_records = sorted(
            [
                record
                for record in self._repo.list_histories()
                if record.source_kind in SYNC_SOURCE_KINDS
            ],
            key=lambda record: int(record.create_time or 0),
            reverse=True,
        )
        records = all_records[:SYNC_LIMIT]
        present_identities: set[tuple[str, str, str]] = set()
        for record in all_records:
            record_key = self._resolved_identity(
                record.source_kind, record.source_key, record.key, self._sync_key_resolver
            )
            if record_key is not None:
                present_identities.add(record_key)
        current_versions: dict[tuple[str, str, str], int] = {}
        changed: list[tuple[tuple[str, str, str], int, dict[str, Any]]] = []
        for record in records:
            record_key = self._resolved_identity(
                record.source_kind, record.source_key, record.key, self._sync_key_resolver
            )
            if record_key is None:
                self._warn_unmapped_plugin("push", record.source_key)
                continue
            payload = self._to_payload(record, record_key[1])
            updated_at = int(payload.get("updatedAt", 0) or 0)
            current_versions[record_key] = updated_at
            if updated_at > self._pushed_versions.get(record_key, -1):
                changed.append((record_key, updated_at, payload))
        deleted_at = int(time() * 1000)
        deleted = [
            {
                "event": "playback.deleted",
                "scope": "item",
                "sourceKind": source_kind,
                "sourceKey": source_key,
                "vodId": vod_id,
                "deletedAt": deleted_at,
            }
            for source_kind, source_key, vod_id in self._pushed_versions.keys() - present_identities
        ]
        logger.info(
            "playback sync scan: local=%d latest=%d snapshot=%d updates=%d deletes=%d",
            len(all_records),
            len(records),
            len(self._pushed_versions),
            len(changed),
            len(deleted),
        )
        if not changed and not deleted:
            if current_versions != self._pushed_versions:
                self._repo.replace_sync_snapshot(self._namespace, current_versions)
                self._pushed_versions = current_versions
            return
        self._api.push_playback_events([payload for _, _, payload in changed] + deleted)
        logger.info(
            "playback sync push succeeded: updates=%d deletes=%d",
            len(changed),
            len(deleted),
        )
        self._repo.replace_sync_snapshot(self._namespace, current_versions)
        self._pushed_versions = current_versions

    @staticmethod
    def _record_key(source_kind: str, source_key: str, vod_id: str) -> tuple[str, str, str]:
        return source_kind, source_key, vod_id

    def _to_payload(self, record, sync_source_key: str) -> dict[str, Any]:
        return {
            "sourceKind": record.source_kind,
            "sourceKey": sync_source_key,
            "sourceName": record.source_name,
            "vodId": record.key,
            "vodName": record.vod_name,
            "vodPic": record.vod_pic,
            "episodeName": record.vod_remarks,
            "episode": record.episode,
            "episodeUrl": record.episode_url,
            "positionMs": record.position,
            "updatedAt": record.create_time,
            "speed": record.speed,
            "clientKey": self._client_key,
            "playlistIndex": record.playlist_index,
            "sourceGroupIndex": record.source_group_index,
            "sourceIndex": record.source_index,
            "sourceSubgroupIndex": record.source_subgroup_index,
            "sourceSubgroupName": record.source_subgroup_name,
            "driveDirId": record.drive_dir_id,
        }

    # ── PULL:服务端 → 本地 Tier-B(LWW by updated_at) ──────────────────────

    def _pull(self) -> None:
        page = self._api.pull_playback_records(self._pull_cursor)
        deleted = page.get("deleted") or []
        items = page.get("items") or []
        logger.info(
            "playback sync pull: since=%s items=%d deleted=%d next=%s",
            self._pull_cursor,
            len(items),
            len(deleted),
            page.get("nextSince"),
        )

        # Process tombstones first: an item in the same page may be a newer
        # re-created record and should therefore be allowed to save afterwards.
        for tombstone in deleted:
            if not isinstance(tombstone, dict):
                continue
            scope = str(tombstone.get("scope") or "item").strip().lower()
            deleted_at = int(
                tombstone.get("deletedAt")
                or tombstone.get("deleted_at")
                or tombstone.get("timestamp")
                or 0
            )
            removed: list[tuple[str, str, str]] = []
            if scope == "all":
                removed = self._repo.delete_all_histories(deleted_at)
                removed.extend(
                    identity
                    for identity, updated_at in self._pushed_versions.items()
                    if deleted_at <= 0 or updated_at <= deleted_at
                )
            elif scope == "site":
                source_kind = str(tombstone.get("sourceKind") or tombstone.get("source_kind") or "site")
                sync_source_key = str(tombstone.get("sourceKey") or tombstone.get("source_key") or "")
                local_source_key = self._resolve_source_key(
                    source_kind, sync_source_key, self._local_key_resolver
                )
                if source_kind in SYNC_SOURCE_KINDS and local_source_key is not None:
                    removed = self._repo.delete_site_history(source_kind, local_source_key, deleted_at)
                    removed = [
                        self._record_key(source_kind, sync_source_key, identity[2])
                        for identity in removed
                    ]
                    removed.extend(
                        identity
                        for identity, updated_at in self._pushed_versions.items()
                        if identity[0] == source_kind
                        and identity[1] == sync_source_key
                        and (deleted_at <= 0 or updated_at <= deleted_at)
                    )
            else:
                sync_identity = self._item_identity(tombstone)
                if sync_identity is None or sync_identity[0] not in SYNC_SOURCE_KINDS:
                    continue
                local_identity = self._resolved_identity(*sync_identity, self._local_key_resolver)
                if local_identity is None:
                    self._warn_unmapped_plugin("pull delete", sync_identity[1])
                    continue
                source_kind, source_key, vod_id = local_identity
                existing = self._repo.get_history(source_kind, vod_id, source_key)
                if existing is not None and deleted_at > 0 and existing.create_time > deleted_at:
                    continue
                self._repo.delete_history(source_kind, vod_id, source_key)
                removed = [sync_identity]
            for identity in set(removed):
                self._repo.remove_sync_snapshot(self._namespace, identity)
                self._pushed_versions.pop(identity, None)

        for item in items:
            sync_identity = self._item_identity(item)
            if sync_identity is None or sync_identity[0] not in SYNC_SOURCE_KINDS:
                continue
            local_identity = self._resolved_identity(*sync_identity, self._local_key_resolver)
            if local_identity is None:
                self._warn_unmapped_plugin("pull", sync_identity[1])
                continue
            source_kind, source_key, vod_id = local_identity
            updated_at = int(item.get("updatedAt") or item.get("updated_at") or item.get("timestamp") or 0)
            existing = self._repo.get_history(source_kind, vod_id, source_key)
            if existing is not None and existing.create_time >= updated_at:
                continue  # 本地不旧于远端,跳过
            payload = {
                "vodName": item.get("vodName") or item.get("vod_name") or "",
                "vodPic": item.get("vodPic") or item.get("vod_pic") or "",
                "vodRemarks": item.get("episodeName") or item.get("vodRemarks") or "",
                "episode": int(item.get("episode") or 0),
                "episodeUrl": item.get("episodeUrl") or item.get("episode_url") or "",
                "position": int(item.get("positionMs") or item.get("position") or 0),
                "speed": float(item.get("speed") or 1.0),
                "createTime": updated_at,
                "playlistIndex": int(item.get("playlistIndex") or item.get("playlist_index") or 0),
                "sourceGroupIndex": int(item.get("sourceGroupIndex") or item.get("source_group_index") or 0),
                "sourceIndex": int(item.get("sourceIndex") or item.get("source_index") or 0),
                "sourceSubgroupIndex": int(
                    item.get("sourceSubgroupIndex") or item.get("source_subgroup_index") or 0
                ),
                "sourceSubgroupName": item.get("sourceSubgroupName")
                or item.get("source_subgroup_name")
                or "",
                "driveDirId": item.get("driveDirId") or item.get("drive_dir_id") or "",
            }
            source_name = str(item.get("sourceName") or item.get("source_name") or "")
            self._repo.save_history(source_kind, vod_id, payload, source_key=source_key, source_name=source_name)
            self._repo.set_sync_snapshot_version(self._namespace, sync_identity, updated_at)
            self._pushed_versions[sync_identity] = updated_at
        next_since = page.get("nextSince")
        if next_since is not None:
            try:
                self._pull_cursor = int(next_since)
                self._repo.set_sync_cursor(self._namespace, self._pull_cursor)
            except (TypeError, ValueError):
                pass

    @staticmethod
    def _item_identity(item: Any) -> tuple[str, str, str] | None:
        if not isinstance(item, dict):
            return None
        source_kind = str(item.get("sourceKind") or item.get("source_kind") or "")
        source_key = str(item.get("sourceKey") or item.get("source_key") or "")
        vod_id = str(item.get("vodId") or item.get("vod_id") or "")
        if not vod_id:
            return None
        return PlaybackHistorySyncService._record_key(source_kind, source_key, vod_id)

    @staticmethod
    def _default_source_key_resolver(source_kind: str, source_key: str) -> str | None:
        if source_kind == "spider_plugin":
            return None
        return source_key

    @staticmethod
    def _resolve_source_key(
        source_kind: str, source_key: str, resolver: SourceKeyResolver
    ) -> str | None:
        resolved = resolver(source_kind, source_key)
        if resolved is None:
            return None
        value = str(resolved)
        if source_kind == "spider_plugin" and not value:
            return None
        return value

    @classmethod
    def _resolved_identity(
        cls,
        source_kind: str,
        source_key: str,
        vod_id: str,
        resolver: SourceKeyResolver,
    ) -> tuple[str, str, str] | None:
        resolved = cls._resolve_source_key(source_kind, source_key, resolver)
        if resolved is None:
            return None
        return cls._record_key(source_kind, resolved, vod_id)

    def _warn_unmapped_plugin(self, direction: str, source_key: str) -> None:
        marker = direction, source_key
        if marker in self._unmapped_plugins:
            return
        self._unmapped_plugins.add(marker)
        logger.warning(
            "playback sync skips spider plugin without stable manifest id: direction=%s source_key=%s",
            direction,
            source_key,
        )
