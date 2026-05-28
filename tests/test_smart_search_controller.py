from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.models import FavoriteCardItem, FavoriteRecord, HistoryRecord
from atv_player.search.controller import SmartSearchController


class Parser:
    def __init__(self, intent: SmartSearchIntent | Exception) -> None:
        self.intent = intent

    def parse(self, keyword: str) -> SmartSearchIntent:
        if isinstance(self.intent, Exception):
            raise self.intent
        return self.intent


class Favorites:
    def search_items(self, keyword: str, page: int):
        record = FavoriteRecord(
            source_kind="telegram",
            source_key="",
            source_name="电报影视",
            vod_id="fav-1",
            vod_name_snapshot="黑镜",
            latest_vod_name="黑镜",
            vod_pic="",
            vod_remarks="8.8 科幻",
            title_changed=False,
            created_at=1,
            updated_at=2,
        )
        return [
            FavoriteCardItem(
                record=record,
                display_title="黑镜",
                source_label="我的收藏",
                updated_hint=False,
                secondary_text="",
            )
        ], 1


class EmptyFollowing:
    def search_items(self, keyword: str, page: int):
        return [], 0


class EmptyHistory:
    def load_page(self, page: int, size: int, keyword: str):
        return [], 0


def test_smart_search_controller_returns_ranked_vod_items() -> None:
    controller = SmartSearchController(
        intent_parser=Parser(
            SmartSearchIntent(
                query_text="类似黑镜的高分科幻",
                keywords=["科幻"],
                genres=["科幻"],
                rating_min=8.0,
                sort_preference="rating",
            )
        ),
        favorites_controller=Favorites(),
        following_controller=EmptyFollowing(),
        history_controller=EmptyHistory(),
    )

    items, total = controller.search_items("类似黑镜的高分科幻", 1)

    assert total == 1
    assert items[0].vod_name == "黑镜"
    assert items[0].type_name == "智能匹配"
    assert "来自我的收藏" in items[0].vod_remarks


def test_smart_search_controller_returns_empty_when_parser_fails() -> None:
    controller = SmartSearchController(
        intent_parser=Parser(RuntimeError("boom")),
        favorites_controller=Favorites(),
        following_controller=EmptyFollowing(),
        history_controller=EmptyHistory(),
    )

    items, total = controller.search_items("类似黑镜", 1)

    assert items == []
    assert total == 0
