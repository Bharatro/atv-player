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


class ManyCategoryController:
    def load_categories(self):
        return [
            DoubanCategory(type_id=str(index), type_name=f"分类{index}")
            for index in range(1, 7)
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

    assert len(page.source_popup.source_buttons) == 2
    assert page.source_button.text() == "源A"
    assert page.current_source_key() == "plugin:1"
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)
    assert page.category_tab_bar.count() == 2
    assert page.category_tab_bar.tabText(0) == "电影"
    assert page.category_tab_bar.tabText(1) == "电视剧"


def test_classic_home_page_category_tabs_use_pointing_hand_cursor(qtbot) -> None:
    from PySide6.QtCore import Qt

    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    assert page.category_tab_bar.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_classic_home_page_category_tabs_use_navigation_tabbar_style(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage
    from atv_player.ui.theme import build_navigation_tabbar_qss, current_tokens

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    assert page.category_tab_bar.styleSheet() == build_navigation_tabbar_qss(current_tokens())


def test_classic_home_page_category_tabs_overflow_to_more_button(qtbot, monkeypatch) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage, SourceEntry

    entries = [
        SourceEntry(key="plugin:many", title="多分类源", controller=ManyCategoryController()),
    ]
    page = ClassicHomePage(entries, initial_source_key="plugin:many")
    qtbot.addWidget(page)
    monkeypatch.setattr(page, "_category_tab_title_width", lambda title: 50)
    monkeypatch.setattr(page.category_tab_bar, "width", lambda: 160)
    monkeypatch.setattr(page, "width", lambda: 160)

    page._refresh_category_tabs()

    assert page.category_more_button.isHidden() is False
    assert page.category_more_button.text() == "更多(5)"
    assert [page.category_tab_bar.tabText(index) for index in range(page.category_tab_bar.count())] == ["分类1"]
    assert [page._categories[index].type_name for index in page._hidden_category_indices] == [
        "分类2",
        "分类3",
        "分类4",
        "分类5",
        "分类6",
    ]

    page._select_category_index(3)

    assert page.current_category_id() == "4"
    assert page.grid_page.selected_category_id == "4"
    assert page.category_tab_bar.property("hiddenTabActive") is True
    assert page.category_more_button.isChecked() is True
    assert page.category_more_button.toolTip() == "分类4"


def test_classic_home_page_switches_source(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)

    page.source_popup.source_button("plugin:2").click()
    assert page.current_source_key() == "plugin:2"
    assert page.source_button.text() == "源B"
    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)
    assert page.category_tab_bar.tabText(0) == "电影"


def test_classic_home_page_restores_initial_category_tab(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1", initial_category_id="2")
    qtbot.addWidget(page)

    qtbot.waitUntil(lambda: page.category_tab_bar.count() > 0, timeout=2000)

    assert page.category_tab_bar.currentIndex() == 1
    assert page.current_category_id() == "2"
    assert page.grid_page.selected_category_id == "2"


def test_classic_home_page_source_popup_uses_four_columns(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage, SourceEntry

    entries = [
        SourceEntry(key=f"plugin:{index}", title=f"源{index}", controller=FakePluginController())
        for index in range(1, 9)
    ]
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    for index, entry in enumerate(entries):
        row, column, _row_span, _column_span = page.source_popup._grid_layout.getItemPosition(index)
        assert row == index // 4
        assert column == index % 4
        assert page.source_popup.source_button(entry.key).text() == entry.title


def test_classic_home_page_source_popup_separates_builtin_and_plugin_sources(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    from atv_player.ui.classic_home_page import ClassicHomePage, SourceEntry

    entries = [
        SourceEntry(key="douban", title="豆瓣", controller=FakePluginController(), source_kind="builtin"),
        SourceEntry(key="telegram", title="电报", controller=FakePluginController(), source_kind="builtin"),
        SourceEntry(key="plugin:1", title="插件一", controller=FakePluginController(), source_kind="plugin"),
    ]
    page = ClassicHomePage(entries, initial_source_key="douban")
    qtbot.addWidget(page)

    section_titles = [
        label.text()
        for label in page.source_popup.findChildren(QLabel)
        if label.objectName() == "classicSourcePopupSectionTitle"
    ]

    assert section_titles == ["内置源", "插件源"]
    assert list(page.source_popup.source_buttons) == ["douban", "telegram", "plugin:1"]


def test_classic_home_page_source_popup_expands_for_long_source_names(qtbot) -> None:
    from atv_player.ui.classic_home_page import ClassicHomePage, SourceEntry

    long_title = "这是一个很长很长的资源站名称"
    entries = [
        SourceEntry(key="plugin:1", title=long_title, controller=FakePluginController()),
        SourceEntry(key="plugin:2", title="短源", controller=FakePluginController()),
        SourceEntry(key="plugin:3", title="源三", controller=FakePluginController()),
        SourceEntry(key="plugin:4", title="源四", controller=FakePluginController()),
    ]
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)

    button = page.source_popup.source_button("plugin:1")
    assert button.minimumWidth() >= button.fontMetrics().horizontalAdvance(long_title) + 32
    assert page.source_popup._preferred_popup_width() >= button.minimumWidth() * 4


def test_classic_home_page_source_popup_hides_on_outside_click(qtbot) -> None:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)
    page.show()

    page.source_button.click()
    qtbot.waitUntil(lambda: page.source_popup.isVisible(), timeout=1000)

    outside_pos = page.mapToGlobal(page.rect().bottomRight()) + page.rect().bottomRight()
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(page.rect().bottomRight()),
        QPointF(outside_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    page.eventFilter(page, event)

    assert not page.source_popup.isVisible()


def test_classic_home_page_source_popup_hides_when_application_inactive(qtbot) -> None:
    from PySide6.QtCore import Qt

    from atv_player.ui.classic_home_page import ClassicHomePage

    entries = _make_source_entries()
    page = ClassicHomePage(entries, initial_source_key="plugin:1")
    qtbot.addWidget(page)
    page.show()

    page.source_button.click()
    qtbot.waitUntil(lambda: page.source_popup.isVisible(), timeout=1000)

    page._handle_application_state_changed(Qt.ApplicationState.ApplicationInactive)

    assert not page.source_popup.isVisible()


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
