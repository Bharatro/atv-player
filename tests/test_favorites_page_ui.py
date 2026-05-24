from atv_player.models import FavoriteCardItem, FavoriteRecord
from atv_player.ui.favorites_page import FavoritesPage


def test_favorites_page_renders_cards_and_update_hint(qtbot) -> None:
    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="旧标题",
                latest_vod_name="新标题",
                vod_pic="",
                vod_remarks="完结",
                title_changed=True,
                created_at=10,
                updated_at=10,
            )
            return [
                FavoriteCardItem(
                    record=record,
                    display_title="新标题",
                    source_label="文件浏览",
                    updated_hint=True,
                    secondary_text="原收藏标题: 旧标题",
                )
            ], 1

    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.ensure_loaded()

    qtbot.waitUntil(lambda: len(page.card_widgets) == 1)
    assert page.card_widgets[0].title_label.text() == "新标题"
    assert page.card_widgets[0].property("title_changed") is True


def test_favorites_page_delete_selected_calls_controller(qtbot, monkeypatch) -> None:
    deleted = []

    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="庆余年",
                latest_vod_name="庆余年",
                vod_pic="",
                vod_remarks="",
                title_changed=False,
                created_at=10,
                updated_at=10,
            )
            return [
                FavoriteCardItem(
                    record=record,
                    display_title="庆余年",
                    source_label="文件浏览",
                    updated_hint=False,
                    secondary_text="",
                )
            ], 1

        def remove_favorite(self, records):
            deleted.extend(records)

    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    monkeypatch.setattr(page, "_confirm_delete_selected", lambda count: True)
    page.ensure_loaded()
    qtbot.waitUntil(lambda: len(page.card_widgets) == 1)
    page.card_widgets[0].setChecked(True)
    page.delete_selected()

    assert [record.vod_id for record in deleted] == ["detail-1"]
