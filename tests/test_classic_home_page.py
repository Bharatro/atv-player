from atv_player.models import DoubanCategory
from atv_player.ui.poster_grid_page import PosterGridPage


class FakeCategoryController:
    def load_categories(self):
        return [
            DoubanCategory(type_id="1", type_name="电影"),
            DoubanCategory(type_id="2", type_name="电视剧"),
            DoubanCategory(type_id="3", type_name="综艺"),
        ]

    def load_items(self, category_id, page, filters=None):
        return [], 0


def test_poster_grid_page_category_layout_tabs_hides_list(qtbot) -> None:
    page = PosterGridPage(FakeCategoryController(), category_layout="tabs")
    qtbot.addWidget(page)

    page.reload_categories()
    qtbot.waitUntil(lambda: len(page.categories) > 0, timeout=2000)

    assert page.category_list.isHidden()
    assert len(page.categories) == 3
    assert page.categories[0].type_name == "电影"


def test_poster_grid_page_default_category_layout_shows_list(qtbot) -> None:
    page = PosterGridPage(FakeCategoryController())
    qtbot.addWidget(page)

    page.reload_categories()
    qtbot.waitUntil(lambda: len(page.categories) > 0, timeout=2000)

    assert not page.category_list.isHidden()
