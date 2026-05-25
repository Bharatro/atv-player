from __future__ import annotations

from dataclasses import dataclass
import time

from atv_player.danmaku.utils import infer_playlist_episode_number
from atv_player.following_metadata import build_following_from_candidate
from atv_player.following_models import (
    FollowingCardItem,
    FollowingDetailSnapshot,
    FollowingRecord,
    FollowingSourceBinding,
    provider_priority_for_media_kind,
)
from atv_player.metadata.models import MetadataQuery
from atv_player.models import PlayItem, VodItem


@dataclass(slots=True)
class FollowingDetailView:
    record: FollowingRecord
    snapshot: FollowingDetailSnapshot


class FollowingController:
    def __init__(self, repository, *, metadata_search_service, update_service=None, now=None) -> None:
        self._repository = repository
        self._metadata_search_service = metadata_search_service
        self._update_service = update_service
        self._now = now or (lambda: int(time.time()))

    def search_media(self, keyword: str):
        query = MetadataQuery(title=keyword.strip())
        return self._metadata_search_service.search(query)

    def add_candidate(self, candidate) -> FollowingRecord:
        record, snapshot = build_following_from_candidate(candidate, now=self._now())
        record_id = self._repository.upsert(record)
        saved = self._repository.get(record_id)
        if saved is None:
            raise RuntimeError("追更保存失败")
        snapshot.following_id = record_id
        self._repository.save_detail_snapshot(record_id, snapshot)
        return saved

    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        records, total = self._repository.load_page(page=page, size=size, keyword=keyword, only_updates=only_updates)
        cards = [
            FollowingCardItem(
                record=record,
                display_title=record.title,
                subtitle=record.provider or record.media_kind,
                progress_text=self._progress_text(record),
                update_text=f"有 {record.new_episode_count} 集更新" if record.has_update else "暂无更新",
                updated_hint=record.has_update,
                error_text=record.last_error,
            )
            for record in records
        ]
        return cards, total

    def load_detail(self, following_id: int) -> FollowingDetailView:
        record = self._repository.get(following_id)
        if record is None:
            raise KeyError(f"following not found: {following_id}")
        snapshot = self._repository.get_detail_snapshot(following_id) or FollowingDetailSnapshot(
            following_id=following_id
        )
        return FollowingDetailView(record=record, snapshot=snapshot)

    def add_from_player(
        self,
        *,
        vod: VodItem,
        item: PlayItem,
        source_kind: str,
        source_key: str,
        position_seconds: int,
    ) -> FollowingRecord:
        now = self._now()
        episode_number = infer_playlist_episode_number(item, [item]) or 0
        provider_id = f"{source_kind}:{source_key}:{vod.vod_id or item.vod_id or item.media_title or item.title}"
        external_ids = {"douban": str(vod.dbid)} if int(vod.dbid or 0) else {}
        record = FollowingRecord(
            id=0,
            title=str(vod.vod_name or item.media_title or item.title or "").strip(),
            original_title=str(item.original_title or "").strip(),
            media_kind=str(vod.category_name or vod.type_name or item.category_name or item.type_name or "").strip(),
            poster=str(vod.vod_pic or item.video_cover_override or "").strip(),
            rating=str(vod.vod_remarks or "").strip(),
            provider="player",
            provider_id=provider_id,
            provider_priority=provider_priority_for_media_kind("anime" if "动漫" in vod.category_name else "live_action"),
            external_ids=external_ids,
            source_bindings=[
                FollowingSourceBinding(
                    source_kind=source_kind,
                    source_key=source_key,
                    vod_id=str(vod.vod_id or item.vod_id or "").strip(),
                    provider="player",
                    provider_id=provider_id,
                )
            ],
            current_episode=episode_number,
            position_seconds=position_seconds,
            created_at=now,
            updated_at=now,
            last_played_at=now,
            next_check_after=now,
        )
        record_id = self._repository.upsert(record)
        saved = self._repository.get(record_id)
        if saved is None:
            raise RuntimeError("追更保存失败")
        return saved

    def mark_watched_latest(self, following_id: int) -> None:
        record = self._repository.get(following_id)
        if record is None:
            return
        self._repository.update_progress(
            following_id,
            current_episode=record.latest_episode,
            position_seconds=0,
            last_played_at=self._now(),
        )
        self._repository.clear_homepage_prompt(following_id)

    def record_playback_progress(self, following_id: int, *, current_episode: int, position_seconds: int) -> None:
        self._repository.update_progress(
            following_id,
            current_episode=current_episode,
            position_seconds=position_seconds,
            last_played_at=self._now(),
        )

    def clear_homepage_prompt(self, following_id: int) -> None:
        self._repository.clear_homepage_prompt(following_id)

    def snooze_prompt(self, following_id: int) -> None:
        self._repository.snooze_prompt(following_id, until=self._now() + 24 * 3600)

    def load_homepage_prompts(self) -> list[FollowingRecord]:
        return self._repository.load_homepage_prompt_records(now=self._now())

    def check_one(self, following_id: int):
        if self._update_service is None:
            return None
        return self._update_service.check_record(following_id)

    def check_all_due(self):
        if self._update_service is None:
            return []
        return self._update_service.check_due_records()

    def delete(self, following_id: int) -> None:
        self._repository.delete(following_id)

    def _progress_text(self, record: FollowingRecord) -> str:
        return f"看到 {record.current_episode} · 最新 {record.latest_episode} / 总 {record.total_episodes}"
