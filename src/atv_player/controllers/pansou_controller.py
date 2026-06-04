from __future__ import annotations

from atv_player.controllers.pagination import page_count_from_total
from atv_player.models import VodItem


class PansouController:
    uses_page_count_for_pagination = True

    def __init__(self, browse_controller) -> None:
        self._browse_controller = browse_controller

    def search_items(self, keyword: str, page: int, category_id: str = "") -> tuple[list[VodItem], int]:
        if page != 1:
            return [], 0
        items = list(self._browse_controller.search(keyword))
        return items, page_count_from_total(len(items))

    def resolve_search_result(self, item: VodItem) -> str:
        return self._browse_controller.resolve_search_result(item)
