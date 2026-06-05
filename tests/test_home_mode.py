from types import SimpleNamespace

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QSizePolicy, QStackedWidget

from atv_player.following_models import FollowingCardItem, FollowingRecord
from atv_player.models import (
    AppConfig,
    DoubanCategory,
    FavoriteCardItem,
    FavoriteRecord,
    HistoryRecord,
    PlayItem,
    VodItem,
)
from atv_player.ui.main_window import MainWindow

from tests.test_main_window_ui import (
    FakeStaticController,
    DummyHistoryController,
    FakePlayerController,
    FakePluginManager,
    SearchableController,
    _vod,
)


class ClassicCategoryController:
    def __init__(self) -> None:
        self.item_calls: list[tuple[str, int]] = []

    def load_categories(self):
        return [
            DoubanCategory(type_id="movie", type_name="电影"),
            DoubanCategory(type_id="tv", type_name="电视剧"),
        ]

    def load_items(self, category_id: str, page: int, filters=None):
        del filters
        self.item_calls.append((category_id, page))
        return [], 0


class SimplifiedRecommendationController:
    def __init__(self) -> None:
        self.item_calls: list[tuple[str, int]] = []

    def load_categories(self):
        return [
            DoubanCategory(type_id="movie", type_name="电影"),
            DoubanCategory(type_id="hot", type_name="热门推荐"),
        ]

    def load_items(self, category_id: str, page: int, filters=None):
        del filters
        self.item_calls.append((category_id, page))
        return [
            VodItem(
                vod_id="hot-1",
                vod_name="漫长的季节",
                vod_pic="",
                vod_remarks="9.4",
            ),
        ], 1


class MediaHistoryController(DummyHistoryController):
    def load_page(self, page: int, size: int, **kwargs):
        del page, size, kwargs
        return [
            HistoryRecord(
                id=1,
                key="history-1",
                vod_name="边水往事",
                vod_pic="",
                vod_remarks="第 2 集",
                episode=1,
                episode_url="https://media.example/2.m3u8",
                position=120,
                opening=0,
                ending=0,
                speed=1.0,
                create_time=1,
                source_kind="telegram",
            )
        ], 1


class MediaFollowingController:
    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        del page, size, keyword, only_updates
        record = FollowingRecord(
            id=7,
            title="凡人修仙传",
            poster="",
            current_episode=128,
        )
        return [
            FollowingCardItem(
                record=record,
                display_title="凡人修仙传",
                subtitle="动画",
                progress_text="看到第 128 集",
                update_text="更新 1 集",
                updated_hint=True,
            )
        ], 1

    def load_homepage_prompts(self):
        return []

    def clear_homepage_prompt(self, following_id: int) -> None:
        del following_id


class MediaFavoritesController:
    def load_page(self, *, page: int, size: int, keyword: str):
        del page, size, keyword
        record = FavoriteRecord(
            source_kind="emby",
            source_key="",
            source_name="Emby",
            vod_id="favorite-1",
            vod_name_snapshot="繁花",
            latest_vod_name="繁花",
            vod_pic="",
            vod_remarks="收藏",
            title_changed=False,
            created_at=1,
            updated_at=1,
        )
        return [
            FavoriteCardItem(
                record=record,
                display_title="繁花",
                source_label="Emby",
                updated_hint=False,
                secondary_text="",
            )
        ], 1

    def is_favorited(self, *, source_kind: str, source_key: str, vod_id: str) -> bool:
        del source_kind, source_key, vod_id
        return False

    def add_favorite(self, payload: dict[str, object]) -> None:
        del payload

    def remove_favorite(self, records: list[FavoriteRecord]) -> None:
        del records

    def clear_filtered(self, *, keyword: str) -> None:
        del keyword


def test_main_window_apply_home_mode_browse_shows_nav_tabs(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    window.apply_home_mode("browse")

    assert hasattr(window, "_home_stack")
    assert isinstance(window._home_stack, QStackedWidget)
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.home_button.isHidden()


def test_main_window_browse_mode_header_browse_keeps_nav_tabs_visible(qtbot) -> None:
    config = AppConfig(home_mode="browse")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.douban_page.setFocus()
    window.browse_button.click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert not window.nav_tabs.nav_row_widget.isHidden()
    assert window.nav_tabs.currentWidget() is window.browse_page


def test_main_window_default_home_mode_is_browse(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    assert hasattr(window, "_home_stack")
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert window.home_button.isHidden()


def test_main_window_applies_home_mode_after_config_change(qtbot) -> None:
    config = AppConfig()
    config.home_mode = "browse"
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    # Simulate what happens after advanced settings closes with a mode change
    config.home_mode = "media"
    window.apply_home_mode("media")

    # Media mode shows the media-center style home page (not nav_tabs)
    assert window._home_stack is not None
    assert hasattr(window, "_media_home_page")
    assert window._home_stack.currentWidget() is window._media_home_page
    assert window.nav_tabs.isHidden()
    # Switching back to browse restores nav_tabs
    window.apply_home_mode("browse")
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert not hasattr(window, "_classic_home_page") or window.header_layout.indexOf(
        window._classic_home_page.source_button
    ) < 0


def test_main_window_apply_home_mode_media_shows_local_media_sections(qtbot, tmp_path) -> None:
    poster_path = tmp_path / "current-poster.png"
    image = QImage(80, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#3d8bff"))
    assert image.save(str(poster_path))
    window = MainWindow(
        FakeStaticController(),
        MediaHistoryController(),
        FakePlayerController(),
        AppConfig(),
        favorites_controller=MediaFavoritesController(),
        following_controller=MediaFollowingController(),
    )
    qtbot.addWidget(window)
    window.player_window = SimpleNamespace(
        session=SimpleNamespace(
            vod=VodItem(
                vod_id="playing-1",
                vod_name="正在看的剧",
                vod_pic=str(poster_path),
            ),
            playlist=[PlayItem(title="第 3 集", url="https://media.example/3.m3u8")],
        ),
        current_index=0,
    )

    window.apply_home_mode("media")

    assert hasattr(window, "_media_home_page")
    page = window._media_home_page
    assert window._home_stack.currentWidget() is page
    assert window.nav_tabs.isHidden()
    assert not window.global_search_container.isHidden()
    assert page.content_container.maximumWidth() > 100000
    qtbot.waitUntil(lambda: page.current_playing_button is not None)
    qtbot.waitUntil(lambda: len(page.continue_buttons) == 1)
    qtbot.waitUntil(lambda: len(page.following_buttons) == 1)
    qtbot.waitUntil(lambda: len(page.favorite_buttons) == 1)
    assert "正在看的剧" in page.current_playing_button.text()
    qtbot.waitUntil(lambda: not page.current_playing_button.icon().isNull())
    assert "边水往事" in page.continue_buttons[0].toolTip()
    assert "第 2 集" in page.continue_buttons[0].toolTip()
    assert "第 2 集" in page.continue_buttons[0].text()
    assert "凡人修仙传" in page.following_buttons[0].toolTip()
    assert "繁花" in page.favorite_buttons[0].toolTip()


def test_main_window_media_home_following_card_opens_visible_detail(
    qtbot,
    monkeypatch,
) -> None:
    window = MainWindow(
        FakeStaticController(),
        MediaHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="media"),
        favorites_controller=MediaFavoritesController(),
        following_controller=MediaFollowingController(),
    )
    qtbot.addWidget(window)
    page = window._media_home_page
    qtbot.waitUntil(lambda: len(page.following_buttons) == 1)

    loaded_ids: list[int] = []
    monkeypatch.setattr(
        window.following_detail_page,
        "load_record",
        lambda following_id: loaded_ids.append(following_id),
    )

    page.following_buttons[0].click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.currentWidget() is window.following_detail_page
    qtbot.waitUntil(lambda: loaded_ids == [7])


def test_main_window_pansou_resolve_keeps_browse_path_visible_in_media_mode(
    qtbot,
    monkeypatch,
) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="media"),
    )
    qtbot.addWidget(window)

    loaded_paths: list[str] = []
    monkeypatch.setattr(
        window.browse_page,
        "load_path",
        lambda path: loaded_paths.append(path),
    )
    window._global_search_active = True
    window._pansou_resolve_request_id = 3

    window._handle_pansou_resolve_succeeded(3, "/Movies/Resolved")

    assert loaded_paths == ["/Movies/Resolved"]
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.currentWidget() is window.browse_page


def test_main_window_media_home_global_search_opens_results_and_clears_back(
    qtbot,
) -> None:
    telegram = SearchableController([_vod("Telegram One")], total=1)
    config = AppConfig(home_mode="media")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        telegram_controller=telegram,
    )
    qtbot.addWidget(window)

    page = window._media_home_page
    assert window._home_stack.currentWidget() is page
    assert not window.global_search_container.isHidden()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: window.nav_tabs.count() == 1)
    assert telegram.search_calls == [("庆余年", 1)]
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()

    window.global_search_edit.clear()

    assert window._home_stack.currentWidget() is page
    assert window.nav_tabs.isHidden()
    assert not window.global_search_container.isHidden()


def test_main_window_media_home_refreshes_current_playing_after_player_returns(
    qtbot,
    monkeypatch,
) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="media"),
    )
    qtbot.addWidget(window)
    page = window._media_home_page
    qtbot.waitUntil(lambda: page.status_label.text() == "暂无媒体内容")

    monkeypatch.setattr(window, "_restore_main_window_after_player", lambda: None)
    window.player_window = SimpleNamespace(
        session=SimpleNamespace(
            vod=VodItem(vod_id="playing-2", vod_name="回来的剧", vod_pic=""),
            playlist=[
                PlayItem(title="第 1 集", url="https://media.example/1.m3u8"),
                PlayItem(title="第 2 集", url="https://media.example/2.m3u8"),
            ],
            initial_vod_name="",
        ),
        current_index=1,
    )

    window._show_main_again()

    qtbot.waitUntil(lambda: page.current_playing_button is not None)
    assert "回来的剧" in page.current_playing_button.text()
    assert "第 2 集" in page.current_playing_button.text()
    assert "2/2" in page.current_playing_button.text()


def test_main_window_media_home_shows_restorable_playback_as_current(qtbot) -> None:
    config = AppConfig(
        home_mode="media",
        last_playback_source="telegram",
        last_playback_mode="detail",
        last_playback_vod_id="history-1",
    )
    window = MainWindow(
        FakeStaticController(),
        MediaHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    page = window._media_home_page

    qtbot.waitUntil(lambda: page.current_playing_button is not None)

    assert "边水往事" in page.current_playing_button.text()
    assert "第 2 集" in page.current_playing_button.text()
    assert "可恢复播放" not in page.current_playing_button.text()


def test_main_window_home_button_returns_from_builtin_page_to_media_home(qtbot) -> None:
    config = AppConfig(home_mode="media")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    assert not window.home_button.icon().isNull()
    assert window.home_button.iconSize().width() == 22
    assert not window.home_button.isHidden()
    window.browse_button.click()
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert window.nav_tabs.currentWidget() is window.browse_page

    window.home_button.click()

    assert window._home_stack.currentWidget() is window._media_home_page
    assert window.nav_tabs.isHidden()


def test_main_window_media_mode_header_browse_hides_nav_tabs(qtbot) -> None:
    config = AppConfig(home_mode="media")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.browse_button.click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.nav_row_widget.isHidden()
    assert window.nav_tabs.currentWidget() is window.browse_page


def test_main_window_apply_home_mode_simplified_shows_search_home(qtbot) -> None:
    douban_controller = SimplifiedRecommendationController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        douban_controller=douban_controller,
        global_search_hotkey_loader=lambda source, hot_type: [
            {"title": f"{source}-{hot_type}-热搜", "query": "热搜查询"},
        ],
    )
    qtbot.addWidget(window)

    window.apply_home_mode("simplified")

    assert hasattr(window, "_simplified_home_page")
    assert window._home_stack.currentWidget() is window._simplified_home_page
    assert window.nav_tabs.isHidden()
    assert window.global_search_container.isHidden()
    qtbot.waitUntil(lambda: len(window._simplified_home_page.hotword_buttons) == 1)
    qtbot.waitUntil(
        lambda: len(window._simplified_home_page.recommendation_buttons) == 1
    )
    assert ("hot", 1) in douban_controller.item_calls


def test_main_window_simplified_search_box_starts_global_search(
    qtbot,
    monkeypatch,
) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        global_search_hotkey_loader=lambda source, hot_type: [],
    )
    qtbot.addWidget(window)
    window.apply_home_mode("simplified")
    started_keywords: list[str] = []
    monkeypatch.setattr(
        window,
        "_start_global_search",
        lambda: started_keywords.append(window.global_search_edit.text()),
    )

    window._simplified_home_page.search_edit.setText("庆余年")
    window._simplified_home_page.search_button.click()

    assert started_keywords == ["庆余年"]
    assert window.global_search_edit.text() == "庆余年"
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert not window.global_search_container.isHidden()


def test_main_window_simplified_clear_search_returns_to_search_home(
    qtbot,
    monkeypatch,
) -> None:
    config = AppConfig(home_mode="simplified")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        global_search_hotkey_loader=lambda source, hot_type: [],
    )
    qtbot.addWidget(window)
    window.apply_home_mode("simplified")

    def mark_search_active() -> None:
        window._global_search_active = True

    monkeypatch.setattr(window, "_start_global_search", mark_search_active)
    window._simplified_home_page.search_edit.setText("庆余年")
    window._simplified_home_page.search_button.click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.global_search_container.isHidden()

    window.global_search_edit.clear()

    assert window._home_stack.currentWidget() is window._simplified_home_page
    assert window.nav_tabs.isHidden()
    assert window.global_search_container.isHidden()
    assert window.global_search_edit.text() == ""
    assert window._simplified_home_page.search_edit.text() == ""


def test_main_window_simplified_hotword_and_recommendation_start_global_search(
    qtbot,
    monkeypatch,
) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        global_search_hotkey_loader=lambda source, hot_type: [],
    )
    qtbot.addWidget(window)
    window.apply_home_mode("simplified")
    page = window._simplified_home_page
    page.set_hotwords([{"title": "热搜一", "query": "热搜查询"}])
    page.set_recommendations(
        [VodItem(vod_id="rec-1", vod_name="繁花", vod_pic="", vod_remarks="热门")]
    )
    started_keywords: list[str] = []
    monkeypatch.setattr(
        window,
        "_start_global_search",
        lambda: started_keywords.append(window.global_search_edit.text()),
    )

    page.hotword_buttons[0].click()
    window.apply_home_mode("simplified")
    page.set_recommendations(
        [VodItem(vod_id="rec-1", vod_name="繁花", vod_pic="", vod_remarks="热门")]
    )
    page.recommendation_buttons[0].click()

    assert started_keywords == ["热搜查询", "繁花"]


def test_main_window_simplified_recommendation_shows_poster_cover(
    qtbot,
    tmp_path,
) -> None:
    poster_path = tmp_path / "poster.png"
    image = QImage(80, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#ff6a3d"))
    assert image.save(str(poster_path))

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="simplified"),
        global_search_hotkey_loader=lambda source, hot_type: [],
    )
    qtbot.addWidget(window)
    window.apply_home_mode("simplified")
    qtbot.waitUntil(
        lambda: window._simplified_home_page.recommendations_status_label.text()
        == "暂无热门推荐"
    )

    window._simplified_home_page.set_recommendations(
        [
            VodItem(
                vod_id="rec-1",
                vod_name="繁花",
                vod_pic=str(poster_path),
                vod_remarks="热门",
            )
        ]
    )

    qtbot.waitUntil(
        lambda: not window._simplified_home_page.recommendation_buttons[0]
        .icon()
        .isNull()
    )


def test_main_window_switching_from_classic_to_browse_starts_deferred_plugin_load(qtbot) -> None:
    config = AppConfig(home_mode="classic")
    load_calls = []

    def plugin_loader_task():
        load_calls.append("load")
        yield {
            "id": "plugin-1",
            "title": "插件一",
            "controller": FakeStaticController(),
            "search_enabled": True,
            "sort_order": 0,
        }

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)

    assert load_calls == []
    assert window._startup_plugin_load_state == "idle"

    window.apply_home_mode("browse")
    qtbot.waitUntil(lambda: window._startup_plugin_load_state == "idle")

    assert load_calls == ["load"]
    assert any(definition.key == "plugin:plugin-1" for definition in window._plugin_tab_definitions)


def test_main_window_apply_home_mode_classic_shows_classic_page(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    # Inject a fake plugin tab definition so _build_plugin_source_entries finds one
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    assert hasattr(window, "_classic_home_page")
    assert window._home_stack.currentWidget() is window._classic_home_page
    assert window.nav_tabs.isHidden()
    assert window.home_button.isHidden()
    assert (
        window.header_layout.indexOf(window._classic_home_page.source_button)
        < window.header_layout.indexOf(window.global_search_container)
    )
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0


def test_main_window_classic_keeps_global_search_centered(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    search_index = window.header_layout.indexOf(window.global_search_container)
    leading_spacer = window.header_layout.itemAt(search_index - 1).spacerItem()
    center_spacer = window.header_layout.itemAt(search_index + 1).spacerItem()
    assert leading_spacer is not None
    assert center_spacer is not None
    assert leading_spacer.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert center_spacer.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_main_window_classic_source_picker_includes_builtin_and_plugin_sources(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "douban" in keys
    assert "telegram" in keys
    assert "live" in keys
    assert "browse" in keys
    assert "favorites" in keys
    assert "following" in keys
    assert "history" in keys
    assert "plugin:1" in keys


def test_main_window_classic_selecting_builtin_non_grid_source_opens_builtin_page(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("favorites").click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.nav_row_widget.isHidden()
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0
    assert window.nav_tabs.currentWidget() is window.favorites_page
    assert config.last_selected_tab == "favorites"


def test_main_window_classic_douban_card_starts_global_search(qtbot) -> None:
    config = AppConfig(home_mode="classic", last_selected_tab="douban")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.item_open_requested.emit(VodItem(vod_id="douban-1", vod_name="漫长的季节"))

    assert window.global_search_edit.text() == "漫长的季节"


def test_main_window_classic_live_folder_card_opens_folder(qtbot) -> None:
    class LiveFolderController(FakeStaticController):
        def __init__(self) -> None:
            self.folder_calls: list[str] = []

        def load_folder_items(self, vod_id: str):
            self.folder_calls.append(vod_id)
            return [VodItem(vod_id="live-child", vod_name="直播子频道")], 1

    controller = LiveFolderController()
    config = AppConfig(home_mode="classic", last_selected_tab="live")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        live_controller=controller,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.item_open_requested.emit(
        VodItem(vod_id="folder-1", vod_name="央视频道", vod_tag="folder")
    )

    qtbot.waitUntil(lambda: controller.folder_calls == ["folder-1"], timeout=2000)


def test_main_window_classic_header_builtin_shortcut_opens_builtin_page(qtbot) -> None:
    config = AppConfig()
    save_calls = []
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        save_config=lambda: save_calls.append(config.last_selected_tab),
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window.following_button.click()

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert not window.nav_tabs.isHidden()
    assert window.nav_tabs.nav_row_widget.isHidden()
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0
    assert window.nav_tabs.currentWidget() is window.following_page
    assert window._classic_home_page.current_source_key() == "following"
    assert window._classic_home_page.source_button.text() == "我的追更"
    assert window._classic_home_page.source_popup.source_button("following").isChecked()
    assert config.last_selected_tab == "following"
    assert save_calls[-1] == "following"


def test_main_window_classic_source_picker_uses_builtin_source_overrides(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig(
        builtin_tab_overrides_json=(
            '{"order":["telegram","douban"],"hidden":["douban"],"renames":{"telegram":"纸飞机"}}'
        )
    )
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]

    window.apply_home_mode("classic")

    buttons = window._classic_home_page.source_popup.source_buttons
    keys = list(buttons)
    assert "douban" not in keys
    assert keys[0] == "telegram"
    assert keys.index("plugin:1") > keys.index("telegram")
    assert buttons["telegram"].text() == "纸飞机"


def test_main_window_classic_source_picker_refreshes_after_builtin_overrides_saved(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")
    window._handle_builtin_tab_overrides_saved(
        '{"order":["telegram","douban"],"hidden":["douban"],"renames":{"telegram":"纸飞机"}}'
    )

    buttons = window._classic_home_page.source_popup.source_buttons
    assert "douban" not in buttons
    assert list(buttons)[0] == "telegram"
    assert buttons["telegram"].text() == "纸飞机"


def test_main_window_classic_source_picker_refreshes_when_plugins_load_later(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition

    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", None, FakeStaticController()),
    ]
    window._refresh_classic_source_entries_if_active()

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "plugin:1" in keys


def test_main_window_classic_source_picker_lists_enabled_plugins_without_loading(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    keys = list(window._classic_home_page.source_popup.source_buttons)
    assert "plugin:1" in keys
    assert "plugin:2" in keys
    assert manager.load_plugins_calls == []


def test_main_window_classic_source_picker_loads_selected_plugin_on_demand(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("plugin:2").click()

    assert manager.load_plugins_calls == [["2"]]
    assert window._classic_home_page.current_source_key() == "plugin:2"


def test_main_window_classic_global_search_loads_and_searches_all_enabled_plugins(qtbot) -> None:
    class SearchablePluginManager(FakePluginManager):
        def __init__(self) -> None:
            super().__init__()
            self.controllers: dict[str, SearchableController] = {}

        def load_plugins(self, plugin_ids, drive_detail_loader=None, offline_download_detail_loader=None):
            del drive_detail_loader, offline_download_detail_loader
            requested = {str(plugin_id) for plugin_id in plugin_ids}
            self.load_plugins_calls.append(sorted(requested))
            definitions = []
            for plugin in self.plugins:
                plugin_id = str(plugin.id)
                if not plugin.enabled or plugin_id not in requested:
                    continue
                controller = SearchableController([_vod(f"{plugin.display_name}结果")], total=1)
                self.controllers[plugin_id] = controller
                definitions.append(
                    {
                        "id": plugin_id,
                        "title": plugin.display_name,
                        "controller": controller,
                        "search_enabled": True,
                    }
                )
            return definitions

    config = AppConfig(home_mode="classic")
    manager = SearchablePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        telegram_controller=SearchableController([]),
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: manager.load_plugins_calls == [["1", "2", "3"]])
    qtbot.waitUntil(
        lambda: sorted(definition.key for definition in window._plugin_tab_definitions)
        == ["plugin:1", "plugin:2", "plugin:3"]
    )
    qtbot.waitUntil(
        lambda: all(
            controller.search_calls == [("庆余年", 1)]
            for controller in manager.controllers.values()
        )
    )


def test_main_window_classic_clear_global_search_returns_to_classic_home(qtbot) -> None:
    config = AppConfig(home_mode="classic", last_selected_tab="douban")
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        telegram_controller=SearchableController([_vod("Telegram One")], total=1),
    )
    qtbot.addWidget(window)

    assert window._home_stack.currentWidget() is window._classic_home_page

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: window._home_stack.currentWidget() is window.nav_tabs)
    assert not window.nav_tabs.isHidden()

    window.global_search_edit.clear()

    assert window._home_stack.currentWidget() is window._classic_home_page
    assert window.nav_tabs.isHidden()
    assert not window.global_search_container.isHidden()
    assert window.header_layout.indexOf(window._classic_home_page.source_button) == 0


def test_main_window_classic_source_picker_persists_selected_source(qtbot) -> None:
    config = AppConfig()
    manager = FakePluginManager()
    save_calls = []
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
        save_config=lambda: save_calls.append(config.last_selected_tab),
    )
    qtbot.addWidget(window)
    window.apply_home_mode("classic")

    window._classic_home_page.source_popup.source_button("plugin:2").click()

    assert config.last_selected_tab == "plugin:2"
    assert save_calls[-1] == "plugin:2"


def test_main_window_classic_source_picker_refreshes_after_plugin_added(qtbot) -> None:
    config = AppConfig(home_mode="classic")
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    manager.plugins.append(
        SimpleNamespace(
            id=4,
            display_name="插件4",
            enabled=True,
            config_text="token=4\n",
            sort_order=3,
        )
    )

    assert window._reload_changed_plugin_tabs(["4"]) is True

    assert "plugin:4" in window._classic_home_page.source_popup.source_buttons
    assert window._classic_home_page.source_popup.source_button("plugin:4").text() == "插件4"


def test_main_window_classic_source_picker_refreshes_after_plugin_deleted(qtbot) -> None:
    config = AppConfig(home_mode="classic")
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    manager.plugins = [plugin for plugin in manager.plugins if plugin.id != 2]

    assert window._reload_changed_plugin_tabs(["2"]) is True

    assert "plugin:2" not in window._classic_home_page.source_popup.source_buttons


def test_main_window_classic_restores_last_selected_source(qtbot) -> None:
    config = AppConfig()
    config.home_mode = "classic"
    config.last_selected_tab = "plugin:2"
    manager = FakePluginManager()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        plugin_manager=manager,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    assert window._classic_home_page.current_source_title() == "插件2"
    assert window._classic_home_page.current_source_key() == "plugin:2"


def test_main_window_classic_restores_last_selected_category_tab(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition
    from atv_player.ui.poster_grid_page import PosterGridPage

    config = AppConfig(
        home_mode="classic",
        last_selected_tab="plugin:1",
        last_selected_category_tab="plugin:1",
        last_selected_category_id="tv",
    )
    controller = ClassicCategoryController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", PosterGridPage(controller), controller),
    ]
    config.last_selected_tab = "plugin:1"

    window.apply_home_mode("classic")

    assert window._classic_home_page.current_source_key() == "plugin:1"
    assert window._classic_home_page.current_category_id() == "tv"
    assert controller.item_calls == [("tv", 1)]


def test_main_window_classic_persists_selected_category_tab(qtbot) -> None:
    from atv_player.ui.main_window import _TabDefinition
    from atv_player.ui.poster_grid_page import PosterGridPage

    config = AppConfig(home_mode="classic", last_selected_tab="plugin:1")
    save_calls = []
    controller = ClassicCategoryController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        save_config=lambda: save_calls.append((config.last_selected_category_tab, config.last_selected_category_id)),
    )
    qtbot.addWidget(window)
    window._plugin_tab_definitions = [
        _TabDefinition("plugin:1", "测试源", PosterGridPage(controller), controller),
    ]
    config.last_selected_tab = "plugin:1"
    window.apply_home_mode("classic")

    window._classic_home_page.category_tab_bar.setCurrentIndex(1)

    assert config.last_selected_category_tab == "plugin:1"
    assert config.last_selected_category_id == "tv"
    assert ("plugin:1", "tv") in save_calls


def test_main_window_classic_source_picker_has_limited_width(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    window.apply_home_mode("classic")

    assert window._classic_home_page.source_button.maximumWidth() <= 180
