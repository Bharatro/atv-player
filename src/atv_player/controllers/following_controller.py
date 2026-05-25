# ruff: noqa: E501
from __future__ import annotations

import re
import time
import ast
from dataclasses import dataclass, replace

from atv_player.danmaku.utils import infer_playlist_episode_number
from atv_player.episode_titles import extract_season_number
from atv_player.following_metadata import (
    build_snapshot_from_record,
    build_following_from_metadata_candidate,
    compute_episode_counts,
    following_candidate_from_url,
    load_candidate_detail_record,
    load_candidate_detail_record_full,
    merge_following_snapshot,
)
from atv_player.following_models import (
    FollowingCardItem,
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    FollowingSourceBinding,
    provider_priority_for_media_kind,
)
from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.scrape import MetadataScrapeCandidate
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
        url_candidate = self.candidate_from_url(keyword)
        if url_candidate is not None:
            from atv_player.metadata.scrape import MetadataScrapeGroup

            url_candidate = self._hydrate_url_candidate(url_candidate)
            return [
                MetadataScrapeGroup(
                    provider=url_candidate.provider,
                    provider_label=url_candidate.provider_label,
                    items=[url_candidate],
                )
            ]
        query = MetadataQuery(title=keyword.strip())
        search_fn = getattr(self._metadata_search_service, "search_following", None)
        if callable(search_fn):
            return search_fn(query)
        return self._metadata_search_service.search(query)

    def candidate_from_url(self, url: str):
        provider_options = getattr(self._metadata_search_service, "provider_options", None)
        available = set()
        if callable(provider_options):
            try:
                available = {str(provider) for provider, _label in provider_options()}
            except Exception:
                available = set()
        return following_candidate_from_url(url, available_providers=available)

    def _hydrate_url_candidate(self, candidate):
        detail_record, _detail_error = load_candidate_detail_record(self._metadata_search_service, candidate)
        if detail_record is None:
            return candidate
        raw = dict(getattr(candidate, "raw", {}) or {})
        detail_fields = list(getattr(detail_record, "detail_fields", []) or [])
        if detail_fields:
            raw["detail_fields"] = detail_fields
        tmdb_id = str(getattr(detail_record, "tmdb_id", "") or "").strip()
        if tmdb_id:
            raw["tmdb_id"] = tmdb_id
        overview = str(getattr(detail_record, "overview", "") or "").strip()
        if overview:
            raw["overview"] = overview
        poster = str(getattr(detail_record, "poster", "") or "").strip()
        if poster:
            raw["poster"] = poster
        backdrop = str(getattr(detail_record, "backdrop", "") or "").strip()
        if backdrop:
            raw["backdrop"] = backdrop
        return replace(
            candidate,
            title=str(getattr(detail_record, "title", "") or getattr(candidate, "title", "") or "").strip(),
            year=str(getattr(detail_record, "year", "") or getattr(candidate, "year", "") or "").strip(),
            raw=raw,
        )

    def add_candidate(self, candidate, *, current_episode: int = 0) -> FollowingRecord:
        now = self._now()
        record, snapshot = build_following_from_metadata_candidate(
            candidate,
            metadata_search_service=self._metadata_search_service,
            now=now,
        )
        existing = self._repository.get_by_identity(record.provider, record.provider_id)
        if existing is not None:
            record = self._merge_existing_candidate_state(
                record,
                existing,
                current_episode=current_episode,
            )
        if current_episode > 0:
            watched_latest = record.latest_episode > 0 and current_episode >= record.latest_episode
            record.current_episode = current_episode
            record.watched_latest_episode = watched_latest
            if watched_latest:
                record.has_update = False
                record.new_episode_count = 0
                record.homepage_prompt_pending = False
        record_id = self._repository.upsert(record)
        saved = self._repository.get(record_id)
        if saved is None:
            raise RuntimeError("追更保存失败")
        snapshot.following_id = record_id
        self._repository.save_detail_snapshot(record_id, snapshot)
        return saved

    def _merge_existing_candidate_state(
        self,
        record: FollowingRecord,
        existing: FollowingRecord,
        *,
        current_episode: int,
    ) -> FollowingRecord:
        target_episode = current_episode if current_episode > 0 else existing.current_episode
        keep_position = existing.current_episode > 0 and target_episode == existing.current_episode
        watched_latest = record.latest_episode > 0 and target_episode >= record.latest_episode
        return replace(
            record,
            source_bindings=list(existing.source_bindings or record.source_bindings),
            current_episode=target_episode,
            position_seconds=existing.position_seconds if keep_position else 0,
            watched_latest_episode=watched_latest,
            has_update=False if watched_latest else existing.has_update,
            new_episode_count=0 if watched_latest else existing.new_episode_count,
            homepage_prompt_pending=False if watched_latest else existing.homepage_prompt_pending,
            prompt_snoozed_until=existing.prompt_snoozed_until,
            created_at=existing.created_at or record.created_at,
            last_played_at=existing.last_played_at if keep_position else 0,
            last_checked_at=existing.last_checked_at,
            next_check_after=existing.next_check_after or record.next_check_after,
        )

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

    def search_items(self, keyword: str, page: int) -> tuple[list[FollowingCardItem], int]:
        return self.load_page(page=page, size=20, keyword=keyword, only_updates=False)

    def load_detail(self, following_id: int, *, refresh_if_empty: bool = True) -> FollowingDetailView:
        record = self._repository.get(following_id)
        if record is None:
            raise KeyError(f"following not found: {following_id}")
        snapshot = self._repository.get_detail_snapshot(following_id) or FollowingDetailSnapshot(
            following_id=following_id
        )
        if refresh_if_empty and self._snapshot_needs_refresh(snapshot) and self._update_service is not None:
            self._update_service.check_record(following_id)
            record = self._repository.get(following_id) or record
            snapshot = self._repository.get_detail_snapshot(following_id) or snapshot
        return FollowingDetailView(record=record, snapshot=snapshot)

    def load_detail_season(self, following_id: int, *, season_number: int) -> FollowingDetailView:
        record = self._repository.get(following_id)
        if record is None:
            raise KeyError(f"following not found: {following_id}")
        snapshot = self._repository.get_detail_snapshot(following_id) or FollowingDetailSnapshot(
            following_id=following_id
        )
        candidate = self._tmdb_detail_candidate_for_season(record, season_number=season_number)
        if candidate is None:
            return FollowingDetailView(record=record, snapshot=snapshot)
        detail_record, detail_error = load_candidate_detail_record_full(
            self._metadata_search_service,
            candidate,
        )
        if detail_record is None:
            raise RuntimeError(detail_error or "没有找到该季元数据")
        _detail_following, detail_snapshot = build_snapshot_from_record(
            detail_record,
            now=self._now(),
            media_kind=record.media_kind,
        )
        merged_snapshot = merge_following_snapshot(
            snapshot,
            detail_snapshot,
            fill_missing=True,
            prefer_episodes=True,
        )
        merged_snapshot.following_id = following_id
        self._repository.save_detail_snapshot(following_id, merged_snapshot)
        return FollowingDetailView(record=record, snapshot=merged_snapshot)

    def add_from_player(
        self,
        *,
        vod: VodItem,
        item: PlayItem,
        source_kind: str,
        source_key: str,
        position_seconds: int,
        playlist: list[PlayItem] | None = None,
    ) -> FollowingRecord:
        now = self._now()
        playlist_items = list(playlist or [item])
        playlist_numbers = self._playlist_episode_numbers(playlist_items)
        episode_number = self._playlist_position(item, playlist_items) or infer_playlist_episode_number(item, playlist_items) or 0
        provider_id = f"{source_kind}:{source_key}:{vod.vod_id or item.vod_id or item.media_title or item.title}"
        external_ids = self._external_ids_from_vod(vod, item)
        metadata_raw_episodes = self._metadata_raw_episodes_from_vod(vod)
        metadata_latest, metadata_total = compute_episode_counts(metadata_raw_episodes, now=now)
        playlist_latest = max(playlist_numbers) if playlist_numbers else 0
        latest_episode = max(playlist_latest, min(metadata_latest, playlist_latest) if playlist_latest else metadata_latest)
        total_episodes = max(metadata_total, self._metadata_total_episodes_from_vod(vod), len(playlist_numbers))
        media_kind = str(vod.category_name or vod.type_name or item.category_name or item.type_name or "").strip()
        season_number = (
            extract_season_number(vod.vod_name)
            or extract_season_number(item.media_title)
            or extract_season_number(item.original_title)
            or 0
        )
        record = FollowingRecord(
            id=0,
            title=str(vod.vod_name or item.media_title or item.title or "").strip(),
            original_title=str(item.original_title or "").strip(),
            media_kind=media_kind,
            season_number=season_number,
            poster=str(vod.vod_pic or item.video_cover_override or "").strip(),
            rating=str(vod.vod_remarks or "").strip(),
            provider="player",
            provider_id=provider_id,
            provider_priority=provider_priority_for_media_kind("anime" if "动漫" in media_kind or "动画" in media_kind else "live_action"),
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
            latest_episode=latest_episode,
            previous_latest_episode=latest_episode,
            total_episodes=total_episodes,
            watched_latest_episode=bool(latest_episode > 0 and episode_number >= latest_episode),
            created_at=now,
            updated_at=now,
            last_played_at=now,
            next_check_after=now,
        )
        if record.watched_latest_episode:
            record.has_update = False
            record.new_episode_count = 0
            record.homepage_prompt_pending = False
        record_id = self._repository.upsert(record)
        saved = self._repository.get(record_id)
        if saved is None:
            raise RuntimeError("追更保存失败")
        snapshot = self._snapshot_from_vod(vod, playlist_items, metadata_raw_episodes=metadata_raw_episodes, refreshed_at=now)
        if self._snapshot_has_data(snapshot):
            snapshot.following_id = record_id
            self._repository.save_detail_snapshot(record_id, snapshot)
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

    def refresh_metadata(self, following_id: int) -> FollowingDetailView:
        record = self._repository.get(following_id)
        if record is None:
            raise KeyError(f"following not found: {following_id}")
        existing_snapshot = self._repository.get_detail_snapshot(following_id)
        candidate = self._tmdb_refresh_candidate_from_record(record)
        include_related = True
        if candidate is None:
            candidate = self._metadata_refresh_candidate(record)
        if candidate is None:
            raise RuntimeError("没有找到可用于更新元数据的匹配结果")
        refreshed_record, snapshot = build_following_from_metadata_candidate(
            candidate,
            metadata_search_service=self._metadata_search_service,
            now=self._now(),
            media_kind=record.media_kind,
            include_related=include_related,
            use_full_detail=True,
        )
        refreshed_record.current_episode = record.current_episode
        refreshed_record.position_seconds = record.position_seconds
        new_latest = max(refreshed_record.latest_episode, record.latest_episode)
        new_total = max(refreshed_record.total_episodes, record.total_episodes)
        refreshed_record.latest_episode = new_latest
        refreshed_record.previous_latest_episode = record.previous_latest_episode
        refreshed_record.total_episodes = new_total
        has_update = new_latest > 0 and new_latest > max(record.current_episode, 0)
        new_episode_count = max(new_latest - max(record.current_episode, 0), 0) if has_update else 0
        homepage_prompt_pending = record.homepage_prompt_pending and has_update
        refreshed_record.has_update = has_update
        refreshed_record.new_episode_count = new_episode_count
        refreshed_record.homepage_prompt_pending = homepage_prompt_pending
        refreshed_record.watched_latest_episode = new_latest > 0 and record.current_episode >= new_latest
        self._repository.update_metadata(following_id, refreshed_record)
        self._repository.update_check_state(
            following_id,
            latest_episode=new_latest,
            total_episodes=new_total,
            checked_at=record.last_checked_at,
            next_check_after=record.next_check_after,
            has_update=has_update,
            new_episode_count=new_episode_count,
            homepage_prompt_pending=homepage_prompt_pending,
            last_error=record.last_error,
        )
        if existing_snapshot is not None:
            snapshot = self._merge_refreshed_snapshot(existing_snapshot, snapshot)
        snapshot.following_id = following_id
        self._repository.save_detail_snapshot(following_id, snapshot)
        return self.load_detail(following_id, refresh_if_empty=False)

    def check_all_due(self):
        if self._update_service is None:
            return []
        return self._update_service.check_due_records()

    def delete(self, following_id: int) -> None:
        self._repository.delete(following_id)

    def _metadata_refresh_candidate(self, record: FollowingRecord):
        query = MetadataQuery(
            title=record.title,
            category_name="动漫" if record.media_kind == "anime" else record.media_kind,
        )
        groups = self._metadata_search_service.search(query)
        candidates = [item for group in groups for item in list(getattr(group, "items", []) or [])]
        if not candidates:
            return None
        tmdb_external_id = str(record.external_ids.get("tmdb") or "").strip()
        if tmdb_external_id:
            for candidate in candidates:
                if str(getattr(candidate, "provider", "") or "") != "tmdb":
                    continue
                if tmdb_external_id in str(getattr(candidate, "provider_id", "") or ""):
                    return candidate
        for candidate in candidates:
            if str(getattr(candidate, "provider", "") or "") == "tmdb":
                return candidate
        identity = (record.provider, record.provider_id)
        for candidate in candidates:
            if (
                str(getattr(candidate, "provider", "") or ""),
                str(getattr(candidate, "provider_id", "") or ""),
            ) == identity:
                return candidate
        for provider, external_id in record.external_ids.items():
            for candidate in candidates:
                if str(getattr(candidate, "provider", "") or "") != provider:
                    continue
                if str(external_id) in str(getattr(candidate, "provider_id", "") or ""):
                    return candidate
        provider_order = ["tmdb", record.provider, *list(record.provider_priority or []), "bangumi", "douban"]
        for provider in provider_order:
            for candidate in candidates:
                if str(getattr(candidate, "provider", "") or "") == provider:
                    return candidate
        return candidates[0]

    def _tmdb_refresh_candidate_from_record(self, record: FollowingRecord):
        normalized, season_number = self._normalized_tmdb_provider_id_and_season(
            record,
            season_number=record.season_number,
        )
        if not normalized:
            return None
        raw = {"season_number": season_number} if season_number > 0 and normalized.startswith("tv:") else {}
        return MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id=normalized,
            title=record.title,
            subtitle="电影" if normalized.startswith("movie:") else "剧集",
            raw=raw,
        )

    def _tmdb_detail_candidate_for_season(
        self,
        record: FollowingRecord,
        *,
        season_number: int,
    ) -> MetadataScrapeCandidate | None:
        normalized, normalized_season = self._normalized_tmdb_provider_id_and_season(
            record,
            season_number=season_number,
        )
        if not normalized or not normalized.startswith("tv:") or normalized_season <= 0:
            return None
        return MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id=normalized,
            title=record.title,
            subtitle="剧集",
            raw={"season_number": normalized_season},
        )

    def _normalized_tmdb_provider_id_and_season(
        self,
        record: FollowingRecord,
        *,
        season_number: int,
    ) -> tuple[str, int]:
        provider_id = ""
        if record.provider == "tmdb":
            provider_id = record.provider_id
        if not provider_id:
            provider_id = str(record.external_ids.get("tmdb") or "").strip()
        normalized, season_number = self._normalize_tmdb_refresh_provider_id(
            provider_id,
            media_kind=record.media_kind,
            season_number=season_number,
        )
        return normalized, season_number

    def _normalize_tmdb_refresh_provider_id(
        self,
        provider_id: str,
        *,
        media_kind: str,
        season_number: int,
    ) -> tuple[str, int]:
        text = str(provider_id or "").strip()
        if not text:
            return "", 0
        normalized_kind = str(media_kind or "").strip().lower()
        if text.startswith("movie:"):
            return text, 0
        if text.startswith("tv:"):
            parts = text.split(":")
            if len(parts) >= 4 and parts[2] == "season":
                resolved_season = season_number if season_number > 0 else self._to_int(parts[3]) or 1
                return f"tv:{parts[1]}:season:{resolved_season}", resolved_season
            if season_number <= 0:
                return "", 0
            return f"{text}:season:{season_number}", season_number
        if not text.isdigit():
            return "", 0
        if normalized_kind == "movie" or "电影" in normalized_kind:
            return f"movie:{text}", 0
        if season_number <= 0:
            return "", 0
        return f"tv:{text}:season:{season_number}", season_number

    def _merge_refreshed_snapshot(
        self,
        existing: FollowingDetailSnapshot,
        refreshed: FollowingDetailSnapshot,
    ) -> FollowingDetailSnapshot:
        merged = merge_following_snapshot(existing, refreshed)
        if not merged.episodes:
            return merged
        existing_by_key = {
            (episode.season_number, episode.episode_number): episode
            for episode in existing.episodes
        }
        ordered_keys: list[tuple[int, int]] = []
        refreshed_by_key: dict[tuple[int, int], FollowingEpisode] = {}
        for episode in merged.episodes:
            key = (episode.season_number, episode.episode_number)
            ordered_keys.append(key)
            refreshed_by_key[key] = episode
        for episode in existing.episodes:
            key = (episode.season_number, episode.episode_number)
            fallback_key = (0, episode.episode_number)
            if key in refreshed_by_key or fallback_key in refreshed_by_key:
                continue
            ordered_keys.append(key)

        episodes: list[FollowingEpisode] = []
        for key in ordered_keys:
            episode = refreshed_by_key.get(key)
            if episode is None and key[0] != 0:
                episode = refreshed_by_key.get((0, key[1]))
            existing_episode = existing_by_key.get(key) or existing_by_key.get((0, key[1]))
            if episode is None:
                if existing_episode is not None:
                    episodes.append(existing_episode)
                continue
            if existing_episode is None:
                episodes.append(episode)
                continue
            episodes.append(
                replace(
                    episode,
                    season_number=episode.season_number or existing_episode.season_number,
                    title=episode.title or existing_episode.title,
                    overview=episode.overview or existing_episode.overview,
                    air_date=episode.air_date or existing_episode.air_date,
                    still=episode.still or existing_episode.still,
                    runtime=episode.runtime or existing_episode.runtime,
                    is_special=episode.is_special or existing_episode.is_special,
                )
            )
        return replace(merged, episodes=episodes)

    def _progress_text(self, record: FollowingRecord) -> str:
        parts = []
        if (
            record.total_episodes > 0
            and record.latest_episode >= record.total_episodes
            and record.current_episode >= record.total_episodes
        ):
            return f"已看完 · {record.total_episodes}集 · 已完结"
        elif record.current_episode > 0:
            parts.append(f"看到 {record.current_episode}")
        if record.latest_episode > 0 and record.total_episodes > 0:
            parts.append(f"最新 {record.latest_episode} / 总 {record.total_episodes}")
        elif record.latest_episode > 0:
            parts.append(f"最新 {record.latest_episode}")
        elif record.total_episodes > 0:
            parts.append(f"总 {record.total_episodes}")
        return " · ".join(parts) if parts else "进度未知"

    def _snapshot_needs_refresh(self, snapshot: FollowingDetailSnapshot) -> bool:
        return not any(
            (
                snapshot.overview,
                snapshot.cast,
                snapshot.crew,
                snapshot.episodes,
                snapshot.posters,
                snapshot.backdrops,
            )
        )

    def _snapshot_from_vod(
        self,
        vod: VodItem,
        playlist: list[PlayItem],
        *,
        metadata_raw_episodes: list[dict[str, object]] | None = None,
        refreshed_at: int,
    ) -> FollowingDetailSnapshot:
        metadata_episodes = [self._episode_from_raw(item) for item in metadata_raw_episodes or []]
        return FollowingDetailSnapshot(
            overview=str(vod.vod_content or "").strip(),
            cast=[{"name": name} for name in self._split_people(vod.vod_actor)],
            crew=[{"name": name, "job": "Director"} for name in self._split_people(vod.vod_director)],
            episodes=metadata_episodes or [
                FollowingEpisode(
                    episode_number=number,
                    title=str(
                        playlist_item.episode_display_title
                        or playlist_item.media_title
                        or playlist_item.original_title
                        or playlist_item.title
                        or ""
                    ).strip(),
                    still=str(playlist_item.video_cover_override or "").strip(),
                )
                for number, playlist_item in zip(self._playlist_episode_numbers(playlist), playlist, strict=False)
            ],
            posters=[source for source in [str(vod.vod_pic or "").strip(), *list(vod.poster_candidates or [])] if source],
            refreshed_at=refreshed_at,
        )

    def _snapshot_has_data(self, snapshot: FollowingDetailSnapshot) -> bool:
        return not self._snapshot_needs_refresh(snapshot)

    def _split_people(self, value: object) -> list[str]:
        return [part.strip() for part in re.split(r"[,/、]", str(value or "")) if part.strip()]

    def _playlist_episode_numbers(self, playlist: list[PlayItem]) -> list[int]:
        if len(playlist) > 1:
            return list(range(1, len(playlist) + 1))
        return [
            number
            for playlist_item in playlist
            if (number := infer_playlist_episode_number(playlist_item, playlist) or 0) > 0
        ]

    def _playlist_position(self, item: PlayItem, playlist: list[PlayItem]) -> int:
        if len(playlist) <= 1:
            return 0
        for index, playlist_item in enumerate(playlist, start=1):
            if playlist_item is item:
                return index
        for index, playlist_item in enumerate(playlist, start=1):
            if playlist_item.url == item.url and playlist_item.title == item.title:
                return index
        item_index = int(getattr(item, "index", 0) or 0)
        return item_index + 1 if 0 <= item_index < len(playlist) else 0

    def _metadata_raw_episodes_from_vod(self, vod: VodItem) -> list[dict[str, object]]:
        for field in list(vod.detail_fields or []):
            if str(getattr(field, "label", "") or "").strip().lower() != "episodes":
                continue
            value = getattr(field, "value", "")
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            text = str(value or "").strip()
            if not text:
                continue
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                continue
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        return []

    def _metadata_total_episodes_from_vod(self, vod: VodItem) -> int:
        for field in list(vod.detail_fields or []):
            label = str(getattr(field, "label", "") or "").strip().lower()
            if label not in {"话数", "集数", "总集数", "episodes_total", "total episodes"}:
                continue
            match = re.search(r"\d+", str(getattr(field, "value", "") or ""))
            if match:
                return int(match.group(0))
        return 0

    def _episode_from_raw(self, raw: dict[str, object]) -> FollowingEpisode:
        number = self._to_int(raw.get("episode_number") or raw.get("sort") or raw.get("ep"))
        return FollowingEpisode(
            episode_number=number,
            season_number=self._to_int(raw.get("season_number")),
            title=str(raw.get("name_cn") or raw.get("name") or raw.get("long_title") or raw.get("title") or "").strip(),
            overview=str(raw.get("overview") or raw.get("desc") or raw.get("summary") or "").strip(),
            air_date=str(raw.get("air_date") or raw.get("airdate") or raw.get("date") or "").strip(),
            still=str(raw.get("still_url") or raw.get("still") or raw.get("cover") or raw.get("image") or "").strip(),
            runtime=self._to_int(raw.get("runtime") or raw.get("duration")),
            is_special=number <= 0 or self._to_int(raw.get("type")) != 0,
        )

    def _to_int(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _external_ids_from_vod(self, vod: VodItem, item: PlayItem) -> dict[str, str]:
        external_ids = {"douban": str(vod.dbid)} if int(vod.dbid or 0) else {}
        for field in [*list(vod.detail_fields or []), *list(item.detail_fields or [])]:
            label = str(getattr(field, "label", "") or "").strip().lower()
            value = str(getattr(field, "value", "") or "").strip()
            if not value:
                continue
            if "tmdb" in label:
                external_ids["tmdb"] = value
            elif "bangumi" in label:
                external_ids["bangumi"] = value
            elif "豆瓣" in label or "douban" in label:
                external_ids["douban"] = value
        return external_ids
