from __future__ import annotations

from collections.abc import Callable

from atv_player.models import FavoriteCardItem, FavoriteRecord, VodItem


class FavoritesController:
    def __init__(
        self,
        repository,
        *,
        detail_loader_by_source: dict[str, Callable[[FavoriteRecord], VodItem | None]],
    ) -> None:
        self._repository = repository
        self._detail_loader_by_source = dict(detail_loader_by_source)

    def load_page(self, *, page: int, size: int, keyword: str) -> tuple[list[FavoriteCardItem], int]:
        records, total = self._repository.load_page(page=page, size=size, keyword=keyword)
        refreshed_items: list[FavoriteCardItem] = []
        for record in records:
            latest_record = record
            loader = self._detail_loader_by_source.get(record.source_kind)
            if loader is not None:
                try:
                    latest_vod = loader(record)
                except Exception:
                    latest_vod = None
                if latest_vod is not None:
                    latest_title = str(latest_vod.vod_name or record.latest_vod_name or record.vod_name_snapshot)
                    latest_pic = str(latest_vod.vod_pic or record.vod_pic)
                    latest_remarks = str(latest_vod.vod_remarks or record.vod_remarks)
                    self._repository.update_refresh_state(
                        record.source_kind,
                        record.source_key,
                        record.vod_id,
                        latest_vod_name=latest_title,
                        vod_pic=latest_pic,
                        vod_remarks=latest_remarks,
                    )
                    latest_record = FavoriteRecord(
                        source_kind=record.source_kind,
                        source_key=record.source_key,
                        source_name=record.source_name,
                        vod_id=record.vod_id,
                        vod_name_snapshot=record.vod_name_snapshot,
                        latest_vod_name=latest_title,
                        vod_pic=latest_pic,
                        vod_remarks=latest_remarks,
                        title_changed=latest_title != record.vod_name_snapshot,
                        created_at=record.created_at,
                        updated_at=record.updated_at,
                    )
            refreshed_items.append(
                FavoriteCardItem(
                    record=latest_record,
                    display_title=latest_record.latest_vod_name or latest_record.vod_name_snapshot,
                    source_label=latest_record.source_name or latest_record.source_kind,
                    updated_hint=latest_record.title_changed,
                    secondary_text=(
                        f"原收藏标题: {latest_record.vod_name_snapshot}"
                        if latest_record.title_changed and latest_record.vod_name_snapshot
                        else ""
                    ),
                )
            )
        return refreshed_items, total

    def is_favorited(self, *, source_kind: str, source_key: str, vod_id: str) -> bool:
        return self._repository.is_favorited(source_kind, source_key, vod_id)

    def add_favorite(self, payload: dict[str, object]) -> None:
        self._repository.save_favorite(payload)

    def remove_favorite(self, records: list[FavoriteRecord]) -> None:
        self._repository.delete_favorites(records)

    def clear_filtered(self, *, keyword: str) -> None:
        self._repository.delete_filtered(keyword=keyword)
