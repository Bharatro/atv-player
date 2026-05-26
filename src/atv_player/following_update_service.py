# ruff: noqa: E501
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from atv_player.following_metadata import compute_episode_counts
from atv_player.following_models import (
    FollowingRecord,
    FollowingUpdateResult,
    progress_at_or_beyond,
    resolve_following_completion_state,
    resolve_progress_season,
)
from atv_player.time_utils import beijing_timezone

BEIJING_TZ = beijing_timezone()
NORMAL_INTERVAL_SECONDS = 6 * 3600
WINDOW_INTERVAL_SECONDS = 5 * 60


def is_common_update_window(timestamp: int) -> bool:
    now = datetime.fromtimestamp(timestamp, BEIJING_TZ)
    minutes = now.hour * 60 + now.minute
    return (0 <= minutes < 120) or (600 <= minutes < 780) or (1080 <= minutes < 1410)


class FollowingUpdateService(QObject):
    update_finished = Signal(object)

    def __init__(self, repository, *, metadata_gateway, now: Callable[[], int] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._metadata_gateway = metadata_gateway
        self._now = now or (lambda: int(time.time()))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_due_records)

    def next_interval_seconds(self) -> int:
        return WINDOW_INTERVAL_SECONDS if is_common_update_window(self._now()) else NORMAL_INTERVAL_SECONDS

    def start(self) -> None:
        QTimer.singleShot(60_000, self.check_due_records)
        self._timer.start(self.next_interval_seconds() * 1000)

    def check_due_records(self, limit: int = 3) -> list[FollowingUpdateResult]:
        now = self._now()
        results = [self._check_one(record, now=now) for record in self._repository.load_due_records(now=now, limit=limit)]
        if results:
            self.update_finished.emit(results)
        if self._timer.isActive():
            self._timer.start(self.next_interval_seconds() * 1000)
        return results

    def check_record(self, record_id: int) -> FollowingUpdateResult | None:
        record = self._repository.get(record_id)
        if record is None:
            return None
        result = self._check_one(record, now=self._now())
        self.update_finished.emit([result])
        return result

    def _check_one(self, record: FollowingRecord, *, now: int) -> FollowingUpdateResult:
        last_error = ""
        for provider in self._provider_order(record):
            if not provider:
                continue
            try:
                refreshed_record, snapshot = self._metadata_gateway.refresh(record, provider)
            except Exception as exc:
                last_error = str(exc)
                continue
            raw_episodes = [
                {
                    "episode_number": episode.episode_number,
                    "type": 1 if episode.is_special else 0,
                    "air_date": episode.air_date,
                }
                for episode in snapshot.episodes
            ]
            latest_from_snapshot, total_from_snapshot = compute_episode_counts(raw_episodes, now=now)
            latest = (
                refreshed_record.latest_episode
                or latest_from_snapshot
                or record.latest_episode
            )
            total = (
                refreshed_record.total_episodes
                or total_from_snapshot
                or record.total_episodes
            )
            snapshot_seasons = [
                episode.season_number
                for episode in snapshot.episodes
                if episode.season_number > 0 and not episode.is_special
            ]
            latest_season_number = (
                refreshed_record.season_number
                or (max(snapshot_seasons) if snapshot_seasons else 0)
                or record.season_number
            )
            current_season_number = resolve_progress_season(
                record.current_season_number,
                record.current_episode,
                fallback_season=record.season_number,
            )
            has_update = not progress_at_or_beyond(
                current_season_number,
                record.current_episode,
                latest_season_number,
                latest,
                current_fallback_season=record.season_number,
                latest_fallback_season=latest_season_number,
            )
            if has_update and latest_season_number == current_season_number:
                new_count = max(latest - max(record.current_episode, 0), 0)
            else:
                new_count = latest if has_update else 0
            caught_up = record.watched_latest_episode or progress_at_or_beyond(
                current_season_number,
                record.current_episode,
                record.season_number,
                record.latest_episode,
                current_fallback_season=record.season_number,
                latest_fallback_season=record.season_number,
            )
            homepage_prompt = bool(has_update and caught_up and record.prompt_snoozed_until <= now)
            if self._has_metadata_update(refreshed_record):
                self._repository.update_metadata(record.id, refreshed_record)
            self._repository.update_check_state(
                record.id,
                latest_episode=latest,
                total_episodes=total,
                checked_at=now,
                next_check_after=now + self.next_interval_seconds(),
                has_update=has_update,
                new_episode_count=new_count,
                homepage_prompt_pending=homepage_prompt,
                last_error="",
            )
            if snapshot.episodes or snapshot.overview:
                snapshot.following_id = record.id
                self._repository.save_detail_snapshot(record.id, snapshot)
            completion_state = resolve_following_completion_state(
                episodes=snapshot.episodes,
                next_episode=snapshot.next_episode,
                today=datetime.fromtimestamp(now, BEIJING_TZ).date(),
            )
            return FollowingUpdateResult(
                record_id=record.id,
                checked=True,
                latest_episode=latest,
                total_episodes=total,
                has_update=has_update,
                homepage_prompt_pending=homepage_prompt,
                completion_state=completion_state,
            )
        self._repository.update_check_state(
            record.id,
            latest_episode=record.latest_episode,
            total_episodes=record.total_episodes,
            checked_at=now,
            next_check_after=now + self.next_interval_seconds(),
            has_update=record.has_update,
            new_episode_count=record.new_episode_count,
            homepage_prompt_pending=record.homepage_prompt_pending,
            last_error=last_error,
        )
        return FollowingUpdateResult(record_id=record.id, checked=False, error=last_error)

    def _provider_order(self, record: FollowingRecord) -> list[str]:
        providers: list[str] = []
        for provider in [*list(record.provider_priority or []), record.provider]:
            if provider and provider not in providers:
                providers.append(provider)
        if record.provider == "tmdb" or record.external_ids.get("tmdb"):
            return ["tmdb", *[provider for provider in providers if provider != "tmdb"]]
        media_kind = str(record.media_kind or "").strip().lower()
        should_try_bangumi_first = (
            record.provider == "bangumi"
            or "bangumi" in record.external_ids
            or any(marker in media_kind for marker in ("anime", "动漫", "动画", "番剧", "国创"))
            or (media_kind != "movie" and "bangumi" in providers)
        )
        if should_try_bangumi_first:
            providers = ["bangumi", *[provider for provider in providers if provider != "bangumi"]]
        return providers or [record.provider]

    def _has_metadata_update(self, record: FollowingRecord) -> bool:
        return any(
            (
                record.title,
                record.original_title,
                record.media_kind,
                record.poster,
                record.backdrop,
                record.rating,
                record.provider,
                record.provider_id,
                record.provider_priority,
                record.external_ids,
            )
        )
