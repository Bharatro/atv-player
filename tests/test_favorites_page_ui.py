from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import atv_player.ui.favorites_page as favorites_page_module
from atv_player.models import FavoriteCardItem, FavoriteRecord
from atv_player.ui.favorites_page import FavoritesPage
from atv_player.ui.theme import ThemeManager, current_tokens, install_theme


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


def test_favorites_page_card_uses_theme_colors_for_readable_text(qtbot) -> None:
    app = QApplication.instance() or QApplication([])
    install_theme(app, ThemeManager(system_theme_getter=lambda: "dark"), "dark")

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
    card = page.card_widgets[0]
    tokens = current_tokens()
    assert tokens.panel_bg in card.styleSheet()
    assert tokens.text_primary in card.title_label.styleSheet()
    assert tokens.text_secondary in card.source_label.styleSheet()
    assert tokens.text_secondary in card.secondary_label.styleSheet()
    assert tokens.text_secondary in card.time_label.styleSheet()


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


def test_favorites_page_clicks_card_to_open_record(qtbot) -> None:
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

    opened = []
    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.open_detail_requested.connect(opened.append)
    page.ensure_loaded()

    qtbot.waitUntil(lambda: len(page.card_widgets) == 1)
    page.card_widgets[0].click()

    assert [record.vod_id for record in opened] == ["detail-1"]


def test_favorites_page_loads_card_poster(qtbot, monkeypatch) -> None:
    loaded_sources = []

    def fake_load_local_poster_image(source, target_size):
        loaded_sources.append((source, target_size.width(), target_size.height()))
        return None

    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="庆余年",
                latest_vod_name="庆余年",
                vod_pic="/tmp/poster.jpg",
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

    monkeypatch.setattr(favorites_page_module, "load_local_poster_image", fake_load_local_poster_image)
    monkeypatch.setattr(favorites_page_module, "load_remote_poster_image", lambda *_args, **_kwargs: None)
    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.ensure_loaded()

    qtbot.waitUntil(lambda: loaded_sources == [("/tmp/poster.jpg", 196, 220)])


def test_favorites_page_displays_loaded_card_poster(qtbot, monkeypatch) -> None:
    image = QImage(24, 36, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))

    class Controller:
        def load_page(self, *, page: int, size: int, keyword: str):
            record = FavoriteRecord(
                source_kind="browse",
                source_key="",
                source_name="文件浏览",
                vod_id="detail-1",
                vod_name_snapshot="庆余年",
                latest_vod_name="庆余年",
                vod_pic="/tmp/poster.jpg",
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

    monkeypatch.setattr(favorites_page_module, "load_local_poster_image", lambda *_args, **_kwargs: image)
    page = FavoritesPage(Controller())
    qtbot.addWidget(page)
    page.ensure_loaded()

    qtbot.waitUntil(
        lambda: len(page.card_widgets) == 1
        and page.card_widgets[0].poster_label.text() == ""
        and page.card_widgets[0].poster_label.pixmap() is not None
    )
    assert page.card_widgets[0].poster_label.text() == ""
