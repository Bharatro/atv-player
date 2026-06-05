from __future__ import annotations

from atv_player.controllers.pagination import page_count_from_payload
from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory, VodItem


def _coerce_category_id(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _map_filter_option(payload: object) -> CategoryFilterOption | None:
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("n") or "").strip()
    value = str(payload.get("v") or "").strip()
    if not name:
        return None
    return CategoryFilterOption(name=name, value=value)


def _map_category_filters(payload: object) -> list[CategoryFilter]:
    if not isinstance(payload, list):
        return []
    groups: list[CategoryFilter] = []
    for raw_group in payload:
        if not isinstance(raw_group, dict):
            continue
        key = str(raw_group.get("key") or "").strip()
        name = str(raw_group.get("name") or "").strip()
        if not key or not name:
            continue
        options = [
            option
            for option in (_map_filter_option(raw_option) for raw_option in raw_group.get("value") or [])
            if option is not None
        ]
        if not options:
            continue
        groups.append(CategoryFilter(key=key, name=name, options=options))
    return groups


def _map_categories(payload: dict) -> list[DoubanCategory]:
    raw_filters = payload.get("filters") or {}
    return [
        DoubanCategory(
            type_id=_coerce_category_id(item.get("type_id")),
            type_name=str(item.get("type_name") or ""),
            filters=_map_category_filters(raw_filters.get(_coerce_category_id(item.get("type_id")))),
        )
        for item in payload.get("class", [])
    ]


def _map_category(payload: dict) -> DoubanCategory:
    return DoubanCategory(
        type_id=_coerce_category_id(payload.get("type_id")),
        type_name=str(payload.get("type_name") or ""),
    )


def _map_item(payload: dict) -> VodItem:
    return VodItem(
        vod_id=str(payload.get("vod_id") or ""),
        vod_name=str(payload.get("vod_name") or ""),
        vod_pic=str(payload.get("vod_pic") or ""),
        vod_tag=str(payload.get("vod_tag") or ""),
        vod_remarks=str(payload.get("vod_remarks") or ""),
        vod_year=str(payload.get("vod_year") or ""),
        dbid=int(payload.get("dbid") or 0),
        type_name=str(payload.get("type_name") or ""),
        vod_content=str(payload.get("vod_content") or ""),
    )


class DoubanController:
    _PAGE_SIZE = 30
    uses_page_count_for_pagination = True

    def __init__(self, api_client) -> None:
        self._api_client = api_client

    def load_categories(self) -> list[DoubanCategory]:
        payload = self._api_client.list_douban_categories()
        return _map_categories(payload)

    def load_items(
        self,
        category_id: str,
        page: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[VodItem], int]:
        payload = self._api_client.list_douban_items(category_id, page=page, size=self._PAGE_SIZE, filters=filters)
        items = [_map_item(item) for item in payload.get("list", [])]
        page_count = page_count_from_payload(payload, fallback_total=len(items), page_size=self._PAGE_SIZE)
        return items, page_count
