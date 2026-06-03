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


# --- ClassicHomePage tests ---


class FakePluginController:
    def load_categories(self):
        return [
            DoubanCategory(type_id="1", type_name="电影"),
            DoubanCategory(type_id="2", type_name="电视剧"),
        ]

    def load_items(self, category_id, page, filters=None):
        return [], 0


def _make_source_entries():
    from atv_player.ui.classic_home_page import SourceEntry
    return [
        SourceEntry(key="plugin:1", title="源A", controller=FakePluginController()),
        SourceEntry(key="plugin:2", title="源B", controller=FakePluginController()),
    ]


def test_classic_home_page_shows_source_picker_and_category_tabs(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    assert page.source_combo.count() == 2
    assert page.source_combo.currentData() == "plugin:1"
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)
    assert page.category_tab_bar.count() == 2
    assert page.category_tab_bar.tabText(0) == "电影"
    assert page.category_tab_bar.tabText(1) == "电视剧"


def test_classic_home_page_switches_source(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)

    page.source_combo.setCurrentIndex(1)
    assert page.source_combo.currentData() == "plugin:2"
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)
    assert page.category_tab_bar.tabText(0) == "电影"


def test_classic_home_page_click_category_emits_signal(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)

    emitted = []
    page.category_selected.connect(lambda cat_id: emitted.append(cat_id))
    page.category_tab_bar.setCurrentIndex(1)
    qtbot.wait(50)
    assert len(emitted) >= 1
