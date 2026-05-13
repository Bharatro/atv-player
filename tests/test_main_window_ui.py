import threading
import time

import pytest

from atv_player.models import AppConfig, OpenPlayerRequest, PlayItem, PlaybackDetailFieldAction, VodItem
import atv_player.danmaku.direct_parse as direct_parse_danmaku_module
import atv_player.ui.main_window as main_window_module
from atv_player.ui.main_window import MainWindow


class FakeStaticController:
    def load_categories(self):
        return []

    def load_items(self, category_id: str, page: int, filters=None):
        return [], 0


class FakeSpiderController:
    def __init__(self, name: str) -> None:
        self.name = name
        self.open_calls: list[str] = []

    def load_categories(self):
        return []

    def load_items(self, category_id: str, page: int):
        return [], 0

    def build_request(self, vod_id: str):
        self.open_calls.append(vod_id)
        return OpenPlayerRequest(
            vod=VodItem(vod_id=vod_id, vod_name=self.name),
            playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
            clicked_index=0,
            source_mode="detail",
            source_vod_id=vod_id,
        )


class FakePluginManager:
    def __init__(self) -> None:
        self.dialog_opened = 0


class WidthAwarePluginManager(FakePluginManager):
    pass


class CountingSpiderController(FakeSpiderController):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.load_calls = 0

    def load_categories(self):
        self.load_calls += 1
        return []


class FakePlayerController:
    def create_session(
        self,
        vod,
        playlist,
        clicked_index: int,
        playlists=None,
        playlist_index: int = 0,
        detail_resolver=None,
        resolved_vod_by_id=None,
        use_local_history=True,
        restore_history=False,
        playback_loader=None,
        async_playback_loader=False,
        detail_action_runner=None,
        detail_field_runner=None,
        danmaku_controller=None,
        playback_progress_reporter=None,
        playback_stopper=None,
        playback_history_loader=None,
        playback_history_saver=None,
        initial_log_message="",
        is_placeholder=False,
    ):
        return {
            "vod": vod,
            "playlist": playlist,
            "clicked_index": clicked_index,
            "playlists": playlists,
            "playlist_index": playlist_index,
            "restore_history": restore_history,
            "async_playback_loader": async_playback_loader,
            "detail_action_runner": detail_action_runner,
            "detail_field_runner": detail_field_runner,
            "danmaku_controller": danmaku_controller,
            "playback_history_loader": playback_history_loader,
            "playback_history_saver": playback_history_saver,
            "initial_log_message": initial_log_message,
            "is_placeholder": is_placeholder,
        }


class AsyncOpenController(FakeStaticController):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._event = threading.Event()

    def build_request(self, vod_id: str):
        self.calls.append(vod_id)
        assert self._event.wait(timeout=5), "open request was never released"
        return OpenPlayerRequest(
            vod=VodItem(vod_id=vod_id, vod_name="Movie"),
            playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
            clicked_index=0,
            source_mode="detail",
            source_vod_id=vod_id,
        )

    def release(self) -> None:
        self._event.set()


class AsyncMediaController(FakeStaticController):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._event = threading.Event()

    def load_folder_items(self, vod_id: str):
        self.calls.append(vod_id)
        assert self._event.wait(timeout=5), "media load was never released"
        return [VodItem(vod_id="m1", vod_name="Movie")], 1

    def release(self) -> None:
        self._event.set()


class AsyncRestoreController(FakeStaticController):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._event = threading.Event()

    def build_request_from_detail(self, vod_id: str):
        self.calls.append(vod_id)
        assert self._event.wait(timeout=5), "restore request was never released"
        return OpenPlayerRequest(
            vod=VodItem(vod_id=vod_id, vod_name="Movie"),
            playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
            clicked_index=0,
            source_mode="detail",
            source_vod_id=vod_id,
        )

    def release(self) -> None:
        self._event.set()


class SearchableController(FakeStaticController):
    def __init__(self, items: list[VodItem], total: int | None = None) -> None:
        self.items = list(items)
        self.total = len(items) if total is None else total
        self.search_calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        return list(self.items), self.total


class PagedSearchableController(FakeStaticController):
    def __init__(self, results_by_page: dict[int, tuple[list[VodItem], int]]) -> None:
        self.results_by_page = {
            page: (list(items), total) for page, (items, total) in results_by_page.items()
        }
        self.search_calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        return self.results_by_page.get(page, ([], 0))


class VariablePageSizeSearchableController(FakeStaticController):
    uses_result_length_for_pagination = True

    def __init__(self, results_by_page: dict[int, tuple[list[VodItem], int]]) -> None:
        self.results_by_page = {page: (list(items), total) for page, (items, total) in results_by_page.items()}
        self.search_calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        return self.results_by_page[page]


class SearchableCategoryController(SearchableController):
    def __init__(self, category_item: VodItem, search_items: list[VodItem], total: int | None = None) -> None:
        super().__init__(search_items, total=total)
        self.load_categories_calls = 0
        self.load_items_calls: list[tuple[str, int]] = []
        self.category_item = category_item

    def load_categories(self):
        self.load_categories_calls += 1
        return [type("Category", (), {"type_id": "movie", "type_name": "电影", "filters": []})()]

    def load_items(self, category_id: str, page: int):
        self.load_items_calls.append((category_id, page))
        return [self.category_item], 1


class KeywordSearchableController(FakeStaticController):
    def __init__(self, results_by_keyword: dict[str, tuple[list[VodItem], int]]) -> None:
        self.results_by_keyword = {
            keyword: (list(items), total) for keyword, (items, total) in results_by_keyword.items()
        }
        self.search_calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        return self.results_by_keyword.get(keyword, ([], 0))


class AsyncKeywordSearchController(FakeStaticController):
    def __init__(self, results_by_keyword: dict[str, tuple[list[VodItem], int]]) -> None:
        self.results_by_keyword = {
            keyword: (list(items), total) for keyword, (items, total) in results_by_keyword.items()
        }
        self.search_calls: list[tuple[str, int]] = []
        self._events: dict[str, threading.Event] = {}

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        event = self._events.setdefault(keyword, threading.Event())
        assert event.wait(timeout=5), f"search for {keyword} was never released"
        return self.results_by_keyword.get(keyword, ([], 0))

    def release(self, keyword: str) -> None:
        self._events.setdefault(keyword, threading.Event()).set()


class SearchableResolveController(SearchableController):
    def __init__(self, items: list[VodItem], resolved_path: str, total: int | None = None) -> None:
        super().__init__(items, total=total)
        self.resolved_path = resolved_path
        self.resolve_calls: list[str] = []

    def resolve_search_result(self, item: VodItem) -> str:
        self.resolve_calls.append(item.vod_id)
        return self.resolved_path


def _vod(name: str, vod_id: str | None = None, remarks: str = "") -> VodItem:
    return VodItem(vod_id=vod_id or name, vod_name=name, vod_pic="", vod_remarks=remarks)


def test_main_window_inserts_dynamic_spider_tabs_before_browse(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True},
            {"title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": False},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    assert [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
        "豆瓣电影",
        "电报影视",
        "网络直播",
        "Emby",
        "Jellyfin",
        "飞牛影视",
        "红果短剧",
        "短剧二号",
        "文件浏览",
        "播放记录",
    ]
    assert window.plugin_manager_button.text() == "插件管理"


def test_main_window_hides_pansou_tab_until_global_search_has_results(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        feiniu_controller=FakeStaticController(),
        pansou_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    assert [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
        "豆瓣电影",
        "电报影视",
        "网络直播",
        "Emby",
        "Jellyfin",
        "飞牛影视",
        "文件浏览",
        "播放记录",
    ]


def test_main_window_shows_startup_plugin_loading_placeholder_tab(qtbot) -> None:
    load_started = threading.Event()
    release_load = threading.Event()

    def plugin_loader_task():
        load_started.set()
        assert release_load.wait(timeout=5), "plugin load was never released"
        return []

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert load_started.wait(timeout=1)
    assert "插件加载中" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]

    release_load.set()


def test_main_window_replaces_loading_placeholder_with_loaded_plugin_tabs(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [
            {"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True},
            {"id": "plugin-2", "title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": False},
        ]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    release_load.set()

    qtbot.waitUntil(
        lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "豆瓣电影",
            "电报影视",
            "网络直播",
            "Emby",
            "Jellyfin",
            "飞牛影视",
            "红果短剧",
            "短剧二号",
            "文件浏览",
            "播放记录",
        ]
    )


def test_main_window_shows_incrementally_loaded_plugin_tabs_before_startup_load_finishes(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        yield {
            "id": "plugin-2",
            "title": "短剧二号",
            "controller": FakeSpiderController("短剧二号"),
            "search_enabled": False,
            "sort_order": 0,
        }
        assert release_load.wait(timeout=5), "plugin load was never released"
        yield {
            "id": "plugin-1",
            "title": "红果短剧",
            "controller": FakeSpiderController("红果短剧"),
            "search_enabled": True,
            "sort_order": 1,
        }

    config = AppConfig(last_selected_tab="plugin:plugin-2")
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    qtbot.waitUntil(
        lambda: len(window._plugin_pages) == 1
        and [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "豆瓣电影",
            "电报影视",
            "网络直播",
            "Emby",
            "Jellyfin",
            "飞牛影视",
            "短剧二号",
            "文件浏览",
            "播放记录",
        ]
    )
    assert window._startup_plugin_load_state == "loading"
    assert window.nav_tabs.currentWidget() is window._plugin_pages[0][0]

    release_load.set()

    qtbot.waitUntil(
        lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "豆瓣电影",
            "电报影视",
            "网络直播",
            "Emby",
            "Jellyfin",
            "飞牛影视",
            "短剧二号",
            "红果短剧",
            "文件浏览",
            "播放记录",
        ]
    )


def test_main_window_restores_last_selected_plugin_tab_after_async_startup_load(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [
            {"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True},
            {"id": "plugin-2", "title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": False},
        ]

    config = AppConfig(last_selected_tab="plugin:plugin-2")
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    assert config.last_selected_tab == "plugin:plugin-2"
    release_load.set()

    qtbot.waitUntil(
        lambda: len(window._plugin_pages) > 1 and window.nav_tabs.currentWidget() is window._plugin_pages[1][0]
    )
    assert config.last_selected_tab == "plugin:plugin-2"


def test_main_window_restores_plugin_player_as_soon_as_target_plugin_arrives_during_startup_load(
    qtbot, monkeypatch,
) -> None:
    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RestorePluginController:
        def __init__(self, vod_name: str) -> None:
            self.vod_name = vod_name

        def load_categories(self):
            return []

        def load_items(self, category_id: str, page: int):
            return [], 0

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name=self.vod_name),
                playlist=[PlayItem(title="第2集", url="https://media.example/2.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    release_load = threading.Event()

    def plugin_loader_task():
        yield {
            "id": "plugin-1",
            "title": "插件一",
            "controller": RestorePluginController("插件电影"),
            "search_enabled": False,
            "sort_order": 0,
        }
        assert release_load.wait(timeout=5), "plugin load was never released"
        yield {
            "id": "plugin-2",
            "title": "插件二",
            "controller": RestorePluginController("插件二电影"),
            "search_enabled": False,
            "sort_order": 1,
        }

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    config = AppConfig(
        last_active_window="player",
        last_playback_source="plugin",
        last_playback_source_key="plugin-1",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
        last_player_paused=True,
    )
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    window._start_restore_last_player()

    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) >= 2)
    assert window._startup_plugin_load_state == "loading"
    assert window.player_window.opened[0][0]["is_placeholder"] is True
    assert window.player_window.opened[1][1] is True
    assert window.player_window.opened[1][0]["vod"].vod_name == "插件电影"

    release_load.set()
    qtbot.waitUntil(lambda: len(window._plugin_pages) == 2)
    assert len(window.player_window.opened) >= 2


def test_main_window_plugin_restore_opens_placeholder_player_while_restore_request_loads(
    qtbot, monkeypatch,
) -> None:
    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.session = None
            self.opened: list[tuple[object, bool]] = []
            self.logs: list[str] = []

        def open_session(self, session, start_paused: bool = False) -> None:
            self.session = session
            self.opened.append((session, start_paused))
            message = session.get("initial_log_message", "")
            if message:
                self.logs.append(message)

        def append_status_log(self, message: str) -> None:
            self.logs.append(message)

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class SlowRestorePluginController:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self._event = threading.Event()

        def load_categories(self):
            return []

        def load_items(self, category_id: str, page: int):
            return [], 0

        def build_request(self, vod_id: str):
            self.calls.append(vod_id)
            assert self._event.wait(timeout=5), "restore request was never released"
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="插件电影"),
                playlist=[PlayItem(title="第2集", url="https://media.example/2.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_mode="detail",
                source_vod_id=vod_id,
            )

        def release(self) -> None:
            self._event.set()

    controller = SlowRestorePluginController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    config = AppConfig(
        last_active_window="player",
        last_playback_source="plugin",
        last_playback_source_key="plugin-1",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
        last_player_paused=True,
    )
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        spider_plugins=[{"id": "plugin-1", "title": "插件一", "controller": controller, "search_enabled": False}],
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    window._start_restore_last_player()

    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)
    assert window.isHidden() is True
    assert window.player_window.opened[0][0]["is_placeholder"] is True
    assert window.player_window.logs == ["正在恢复播放..."]
    assert controller.calls == ["vod-1"]

    controller.release()

    qtbot.waitUntil(lambda: len(window.player_window.opened) == 2)
    assert window.player_window.opened[1][0]["is_placeholder"] is False
    assert window.player_window.opened[1][0]["vod"].vod_name == "插件电影"
    assert window.player_window.opened[1][1] is True


def test_main_window_defers_plugin_player_restore_until_async_startup_load_finishes(qtbot, monkeypatch) -> None:
    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RestorePluginController:
        def load_categories(self):
            return []

        def load_items(self, category_id: str, page: int):
            return [], 0

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="插件电影"),
                playlist=[PlayItem(title="第2集", url="https://media.example/2.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [
            {"id": "plugin-1", "title": "插件一", "controller": RestorePluginController(), "search_enabled": False},
        ]

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    config = AppConfig(
        last_active_window="player",
        last_playback_source="plugin",
        last_playback_source_key="plugin-1",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
        last_player_paused=True,
    )
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    window._start_restore_last_player()

    assert window.player_window is None
    release_load.set()

    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) >= 2)
    assert window.player_window.opened[0][0]["is_placeholder"] is True
    assert window.player_window.opened[1][1] is True


def test_main_window_shows_retry_after_startup_plugin_load_failure(qtbot) -> None:
    attempts = {"count": 0}

    def plugin_loader_task():
        attempts["count"] += 1
        raise RuntimeError("boom")

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    qtbot.waitUntil(lambda: window.startup_plugin_retry_button.isVisible())
    assert "插件加载失败" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]


def test_main_window_retry_restarts_startup_plugin_loading(qtbot) -> None:
    attempts = {"count": 0}

    def plugin_loader_task():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("boom")
        return [{"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True}]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    qtbot.waitUntil(lambda: window.startup_plugin_retry_button.isVisible())
    window.startup_plugin_retry_button.click()

    qtbot.waitUntil(lambda: "红果短剧" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())])
    assert attempts["count"] == 2


def test_main_window_ignores_late_startup_plugin_results_after_close(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [{"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True}]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    window.close()
    release_load.set()

    qtbot.wait(100)


def test_main_window_applies_plugin_overflow_after_async_startup_load(qtbot, monkeypatch) -> None:
    def plugin_loader_task():
        return [
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": FakeSpiderController(f"插件{index}"), "search_enabled": True}
            for index in range(1, 6)
        ]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 220)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()

    qtbot.waitUntil(lambda: window.plugin_overflow_button.text() == "更多(3)")
    assert [definition.title for definition in window._hidden_plugin_tab_definitions] == ["插件3", "插件4", "插件5"]


def test_main_window_hides_overflow_plugin_tabs_behind_more_button(qtbot, monkeypatch) -> None:
    controllers = [FakeSpiderController(f"插件{i}") for i in range(1, 6)]
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 220)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()

    assert [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
        "豆瓣电影",
        "电报影视",
        "网络直播",
        "Emby",
        "Jellyfin",
        "飞牛影视",
        "插件1",
        "插件2",
        "文件浏览",
        "播放记录",
    ]
    assert window.plugin_overflow_button.isVisible() is True
    assert window.plugin_overflow_button.text() == "更多(3)"
    assert [definition.title for definition in window._hidden_plugin_tab_definitions] == ["插件3", "插件4", "插件5"]


def test_main_window_hides_more_button_when_all_plugin_tabs_fit(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "插件1", "controller": FakeSpiderController("插件1"), "search_enabled": True},
            {"id": "plugin-2", "title": "插件2", "controller": FakeSpiderController("插件2"), "search_enabled": True},
        ],
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 600)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()

    assert window.plugin_overflow_button.isVisible() is False
    assert window._hidden_plugin_tab_definitions == []


def test_main_window_hides_all_plugin_tabs_when_fixed_tabs_exhaust_width(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "插件1", "controller": FakeSpiderController("插件1"), "search_enabled": True},
            {"id": "plugin-2", "title": "插件2", "controller": FakeSpiderController("插件2"), "search_enabled": True},
            {"id": "plugin-3", "title": "插件3", "controller": FakeSpiderController("插件3"), "search_enabled": True},
        ],
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 0)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()

    assert "插件1" not in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]
    assert [definition.title for definition in window._hidden_plugin_tab_definitions] == ["插件1", "插件2", "插件3"]
    assert window.plugin_overflow_button.text() == "更多(3)"


def test_main_window_does_not_lock_width_to_all_visible_plugin_tabs(qtbot) -> None:
    baseline_window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=WidthAwarePluginManager(),
    )
    qtbot.addWidget(baseline_window)
    baseline_window.resize(640, 480)
    baseline_window.show()
    baseline_width = baseline_window.width()
    baseline_window.close()

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": FakeSpiderController(f"插件{index}"), "search_enabled": True}
            for index in range(1, 31)
        ],
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()

    assert window.width() == baseline_width
    assert len(window._hidden_plugin_tab_definitions) > 0


def test_main_window_plugin_overflow_drawer_filters_hidden_plugins(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-1", "title": "短剧一号", "controller": FakeSpiderController("短剧一号"), "search_enabled": True},
            {"id": "plugin-2", "title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": True},
            {"id": "plugin-3", "title": "音乐插件", "controller": FakeSpiderController("音乐插件"), "search_enabled": True},
        ],
        plugin_manager=WidthAwarePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()

    assert [item.text() for item in window._plugin_overflow_drawer.visible_items()] == ["短剧二号", "音乐插件"]

    window._plugin_overflow_drawer.search_edit.setText("音乐")

    assert [item.text() for item in window._plugin_overflow_drawer.visible_items()] == ["音乐插件"]


def test_main_window_selecting_hidden_plugin_from_drawer_switches_content_without_rebuilding_pages(
    qtbot, monkeypatch,
) -> None:
    controllers = [CountingSpiderController(f"插件{i}") for i in range(1, 4)]
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=WidthAwarePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 100)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    original_pages = [page for page, _controller, _plugin_id in window._plugin_pages]
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()

    window._plugin_overflow_drawer.select_plugin_by_title("插件3")

    assert window._active_widget is original_pages[2]
    assert window.nav_tabs.currentWidget() is original_pages[2]
    assert window._plugin_pages[2][0] is original_pages[2]
    assert controllers[2].load_calls <= 1


def test_main_window_resize_keeps_active_hidden_plugin_page_instance(qtbot, monkeypatch) -> None:
    controllers = [CountingSpiderController(f"插件{i}") for i in range(1, 4)]
    available_width = {"value": 100}
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": controller, "search_enabled": True}
            for index, controller in enumerate(controllers, start=1)
        ],
        plugin_manager=WidthAwarePluginManager(),
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: available_width["value"])
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()
    original_pages = [page for page, _controller, _plugin_id in window._plugin_pages]
    window._refresh_navigation_tabs()
    window._open_plugin_overflow_drawer()
    window._plugin_overflow_drawer.select_plugin_by_title("插件3")

    available_width["value"] = 600
    window._refresh_navigation_tabs()

    assert window.nav_tabs.currentWidget() is original_pages[2]
    assert window._plugin_pages[2][0] is original_pages[2]
    assert controllers[2].load_calls <= 1


def test_main_window_uses_centered_rounded_search_box_with_icon_controls(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert window.global_search_edit.parentWidget() is not None
    assert window.global_search_container.width() == 400
    assert window.global_search_container.minimumWidth() == 400
    assert window.global_search_container.maximumWidth() == 400
    assert window.global_search_edit.placeholderText() == "搜索"
    assert window.global_search_edit.isClearButtonEnabled() is True
    assert window.global_search_edit.styleSheet()
    assert "border-radius: 18px;" in window.global_search_edit.styleSheet()
    assert window.global_search_button.text() == ""
    assert window.global_search_button.icon().isNull() is False
    assert window.global_search_clear_button.isHidden() is True
    assert window.header_layout.indexOf(window.global_search_container) < window.header_layout.indexOf(window.plugin_manager_button)


def test_main_window_global_search_shows_only_tabs_with_results_and_count_titles(qtbot) -> None:
    telegram = SearchableController([_vod("Telegram One")], total=12)
    emby = SearchableController([])
    jellyfin = SearchableController([_vod("Jellyfin One")], total=3)
    feiniu = SearchableController([])
    plugin_controller = SearchableController([_vod("Plugin One"), _vod("Plugin Two")], total=2)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=jellyfin,
        feiniu_controller=feiniu,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": False},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(
        lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "电报影视(12)",
            "Jellyfin(3)",
            "红果短剧(2)",
        ]
    )
    assert telegram.search_calls == [("庆余年", 1)]
    assert emby.search_calls == [("庆余年", 1)]
    assert jellyfin.search_calls == [("庆余年", 1)]
    assert feiniu.search_calls == [("庆余年", 1)]
    assert plugin_controller.search_calls == [("庆余年", 1)]


def test_main_window_global_search_hides_all_tabs_then_shows_results_incrementally(qtbot) -> None:
    telegram = AsyncKeywordSearchController({"庆余年": ([_vod("Telegram One")], 12)})
    plugin_controller = AsyncKeywordSearchController({"庆余年": ([_vod("Plugin One")], 1)})

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": False},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: telegram.search_calls == [("庆余年", 1)])
    assert window.nav_tabs.count() == 0

    telegram.release("庆余年")
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(12)"])

    plugin_controller.release("庆余年")
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(12)", "红果短剧(1)"])


def test_main_window_switching_result_tabs_keeps_global_search_results(qtbot) -> None:
    telegram = SearchableCategoryController(
        category_item=_vod("分类视频"),
        search_items=[_vod("Telegram Result", remarks="搜索结果")],
        total=1,
    )
    emby = SearchableCategoryController(
        category_item=_vod("Emby 分类视频"),
        search_items=[_vod("Emby Result", remarks="搜索结果")],
        total=1,
    )

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(1)", "Emby(1)"])
    assert [button.text() for button in window.telegram_page.card_buttons] == ["Telegram Result\n搜索结果"]
    assert [button.text() for button in window.emby_page.card_buttons] == ["Emby Result\n搜索结果"]

    window.nav_tabs.setCurrentIndex(1)
    qtbot.wait(100)

    assert [button.text() for button in window.emby_page.card_buttons] == ["Emby Result\n搜索结果"]
    assert window.emby_page.category_list.isHidden() is True
    assert emby.load_categories_calls == 0
    assert emby.load_items_calls == []


def test_main_window_global_search_results_can_paginate_current_source_only(qtbot) -> None:
    telegram = PagedSearchableController(
        {
            1: ([_vod(f"Telegram Page 1-{index}") for index in range(30)], 61),
            2: ([_vod(f"Telegram Page 2-{index}") for index in range(30)], 61),
        }
    )
    emby = SearchableController([_vod("Emby Result")], total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(61)", "Emby(1)"])
    assert [button.text() for button in window.telegram_page.card_buttons] == [f"Telegram Page 1-{index}" for index in range(30)]
    assert telegram.search_calls == [("庆余年", 1)]
    assert emby.search_calls == [("庆余年", 1)]

    window.telegram_page.next_page()

    qtbot.waitUntil(lambda: [button.text() for button in window.telegram_page.card_buttons] == [f"Telegram Page 2-{index}" for index in range(30)])
    assert telegram.search_calls == [("庆余年", 1), ("庆余年", 2)]
    assert emby.search_calls == [("庆余年", 1)]
    assert window.telegram_page.page_label.text() == "第 2 / 3 页"


def test_main_window_global_search_prefers_inferred_page_size(qtbot) -> None:
    telegram = VariablePageSizeSearchableController(
        {
            1: ([ _vod(f"Telegram Page 1-{index}") for index in range(20) ], 41),
            2: ([ _vod("Telegram Page 2-last") ], 41),
        }
    )

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(41)"])
    assert window.telegram_page.page_label.text() == "第 1 / 3 页"
    assert window.telegram_page.next_page_button.isEnabled() is True

    window.telegram_page.next_page()

    qtbot.waitUntil(lambda: [button.text() for button in window.telegram_page.card_buttons] == ["Telegram Page 2-last"])
    assert window.telegram_page.page_label.text() == "第 2 / 3 页"


def test_main_window_global_search_includes_pansou_when_enabled(qtbot) -> None:
    pansou = SearchableController([_vod("盘搜结果", vod_id="pan-1")], total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        pansou_controller=pansou,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["盘搜(1)"])
    assert pansou.search_calls == [("庆余年", 1)]


def test_main_window_global_search_treats_drive_url_as_direct_detail_open(qtbot, monkeypatch) -> None:
    telegram = SearchableController([])
    emby = SearchableController([])
    jellyfin = SearchableController([])
    feiniu = SearchableController([])
    drive_calls: list[str] = []
    opened: list[OpenPlayerRequest] = []

    def load_drive_detail(link: str) -> dict:
        drive_calls.append(link)
        return {
            "list": [
                {
                    "vod_id": "1$91792$1",
                    "vod_name": "夸克资源",
                    "vod_play_url": "第1集$https://media.example/quark-1.m3u8#第2集$https://media.example/quark-2.m3u8",
                }
            ]
        }

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=jellyfin,
        feiniu_controller=feiniu,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        drive_detail_loader=load_drive_detail,
        plugin_manager=FakePluginManager(),
    )
    monkeypatch.setattr(window, "open_player", lambda request, restore_paused_state=False: opened.append(request))

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("https://pan.quark.cn/s/demo")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: len(opened) == 1)

    assert drive_calls == ["https://pan.quark.cn/s/demo"]
    assert telegram.search_calls == []
    assert emby.search_calls == []
    assert jellyfin.search_calls == []
    assert feiniu.search_calls == []
    assert opened[0].vod.vod_name == "夸克资源"
    assert [item.title for item in opened[0].playlist] == ["第1集", "第2集"]
    assert opened[0].source_vod_id == "https://pan.quark.cn/s/demo"


def test_main_window_global_search_treats_non_drive_url_as_direct_parse(qtbot, monkeypatch) -> None:
    class FakeParserService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def resolve(self, flag: str, url: str, preferred_key: str = ""):
            self.calls.append((flag, url, preferred_key))
            return type(
                "Result",
                (),
                {
                    "parser_key": "jx1",
                    "url": "https://media.example/parsed.m3u8",
                    "headers": {"Referer": "https://site.example"},
                },
            )()

    telegram = SearchableController([])
    emby = SearchableController([])
    jellyfin = SearchableController([])
    feiniu = SearchableController([])
    parser_service = FakeParserService()
    opened: list[OpenPlayerRequest] = []

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=jellyfin,
        feiniu_controller=feiniu,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(preferred_parse_key="jx1"),
        plugin_manager=FakePluginManager(),
        playback_parser_service=parser_service,
        direct_parse_detail_loader=lambda _url: {},
    )
    monkeypatch.setattr(window, "open_player", lambda request, restore_paused_state=False: opened.append(request))

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("https://v.qq.com/x/cover/demo.html")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: len(opened) == 1)

    assert telegram.search_calls == []
    assert emby.search_calls == []
    assert jellyfin.search_calls == []
    assert feiniu.search_calls == []
    assert opened[0].source_kind == "direct_parse"
    assert opened[0].source_mode == "parse"
    assert opened[0].source_vod_id == "https://v.qq.com/x/cover/demo.html"
    assert opened[0].use_local_history is False
    assert opened[0].playlist[0].parse_required is True
    assert opened[0].playlist[0].url == ""

    opened[0].playback_loader(opened[0].playlist[0])

    assert parser_service.calls == [("", "https://v.qq.com/x/cover/demo.html", "jx1")]
    assert opened[0].playlist[0].url == "https://media.example/parsed.m3u8"
    assert opened[0].playlist[0].headers == {"Referer": "https://site.example"}


def test_main_window_global_search_treats_magnet_as_offline_download(qtbot, monkeypatch) -> None:
    telegram = SearchableController([])
    emby = SearchableController([])
    jellyfin = SearchableController([])
    feiniu = SearchableController([])
    offline_calls: list[str] = []
    opened: list[OpenPlayerRequest] = []

    def load_offline_detail(link: str) -> dict:
        offline_calls.append(link)
        return {
            "list": [
                {
                    "vod_id": "1$107919$1",
                    "vod_name": "离线下载结果",
                    "vod_play_from": "丫仙女",
                    "vod_play_url": "离线文件.mp4(6.11 GB)$1@107920@0@0",
                    "path": "/我的115云盘/alist-tvbox-offline/离线文件/~playlist",
                }
            ]
        }

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=jellyfin,
        feiniu_controller=feiniu,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
        offline_download_detail_loader=load_offline_detail,
    )
    monkeypatch.setattr(window, "open_player", lambda request, restore_paused_state=False: opened.append(request))

    qtbot.addWidget(window)
    window.show()

    magnet = "magnet:?xt=urn:btih:8a06396e03acb19d72eb2d779a22b2dc00f66a33"
    window.global_search_edit.setText(magnet)
    window.global_search_button.click()

    qtbot.waitUntil(lambda: len(opened) == 1)

    assert offline_calls == [magnet]
    assert telegram.search_calls == []
    assert emby.search_calls == []
    assert jellyfin.search_calls == []
    assert feiniu.search_calls == []
    assert opened[0].vod.vod_name == "离线下载结果"
    assert [item.title for item in opened[0].playlist] == ["离线文件.mp4(6.11 GB)"]
    assert opened[0].source_vod_id == magnet


def test_main_window_global_search_builds_episode_playlist_from_direct_parse_detail(qtbot, monkeypatch) -> None:
    class FakeParserService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def resolve(self, flag: str, url: str, preferred_key: str = ""):
            self.calls.append((flag, url, preferred_key))
            return type(
                "Result",
                (),
                {
                    "parser_key": "jx1",
                    "url": f"https://media.example/{url.rsplit('/', 1)[-1]}.m3u8",
                    "headers": {"Referer": "https://site.example"},
                },
            )()

    def load_detail(url: str) -> dict:
        assert url == "https://v.qq.com/x/cover/mzc00200xxpsogl/h4101bl5ftq.html"
        return {
            "vod_code": 200,
            "vod_type": "动漫",
            "vod_title": "剑来 第二季",
            "vod_year": "2025",
            "vod_updateTo": "VIP · 全27集 · 21621",
            "vod_pic": "https://image.example/poster.jpg",
            "vod_form": "https://v.qq.com/x/cover/mzc00200xxpsogl/h4101bl5ftq.html",
            "vod_desc": "desc",
            "vod_episodes": [
                {
                    "name": "第09话",
                    "url": "https://v.qq.com/x/cover/mzc00200xxpsogl/y4101fhe180.html",
                },
                {
                    "name": "第10话",
                    "url": "https://v.qq.com/x/cover/mzc00200xxpsogl/h4101bl5ftq.html",
                },
                {
                    "name": "第11话",
                    "url": "https://v.qq.com/x/cover/mzc00200xxpsogl/a4101bma2qf.html",
                },
            ],
        }

    parser_service = FakeParserService()
    danmaku_calls: list[str] = []

    def load_danmaku(url: str) -> dict:
        danmaku_calls.append(url)
        return {
            "code": 23,
            "name": "demo",
            "danmuku": [
                [42.741, "right", "#00CD00", "1205421", "666", "03-15 15:47", "25px"],
            ],
        }

    opened: list[OpenPlayerRequest] = []

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(preferred_parse_key="jx1"),
        plugin_manager=FakePluginManager(),
        playback_parser_service=parser_service,
        direct_parse_detail_loader=load_detail,
        direct_parse_danmaku_loader=load_danmaku,
    )
    monkeypatch.setattr(direct_parse_danmaku_module, "load_cached_danmaku_xml", lambda name, reg_src: "")
    monkeypatch.setattr(direct_parse_danmaku_module, "save_cached_danmaku_xml", lambda name, reg_src, xml_text: None)
    monkeypatch.setattr(window, "open_player", lambda request, restore_paused_state=False: opened.append(request))

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("https://v.qq.com/x/cover/mzc00200xxpsogl/h4101bl5ftq.html")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: len(opened) == 1)

    assert opened[0].vod.vod_name == "剑来 第二季"
    assert opened[0].source_kind == "direct_parse"
    assert opened[0].vod.type_name == "动漫"
    assert opened[0].vod.vod_year == "2025"
    assert opened[0].vod.vod_remarks == "VIP · 全27集 · 21621"
    assert [item.title for item in opened[0].playlist] == ["第09话", "第10话", "第11话"]
    assert opened[0].clicked_index == 1
    assert opened[0].use_local_history is False
    assert opened[0].danmaku_controller is not None
    assert all(item.parse_required for item in opened[0].playlist)
    assert opened[0].playlist[1].original_url == "https://v.qq.com/x/cover/mzc00200xxpsogl/h4101bl5ftq.html"
    assert opened[0].playlist[2].url == ""

    opened[0].playback_loader(opened[0].playlist[2])

    assert parser_service.calls == [
        ("", "https://v.qq.com/x/cover/mzc00200xxpsogl/a4101bma2qf.html", "jx1")
    ]
    assert opened[0].playlist[2].url == "https://media.example/a4101bma2qf.html.m3u8"
    assert opened[0].playlist[2].headers == {"Referer": "https://site.example"}
    qtbot.waitUntil(lambda: bool(opened[0].playlist[2].danmaku_xml), timeout=1000)
    assert danmaku_calls == ["https://v.qq.com/x/cover/mzc00200xxpsogl/a4101bma2qf.html"]
    assert "666" in opened[0].playlist[2].danmaku_xml


def test_main_window_opening_pansou_result_restores_browse_tab_and_path(qtbot, monkeypatch) -> None:
    pansou = SearchableResolveController([_vod("盘搜结果", vod_id="pan-1")], resolved_path="/Movies/Resolved", total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        pansou_controller=pansou,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    shown_paths: list[str] = []
    monkeypatch.setattr(window, "show_browse_path", lambda path: shown_paths.append(path))

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["盘搜(1)"])

    item = _vod("盘搜结果", vod_id="pan-1")
    window._handle_pansou_item_open_requested(item)

    qtbot.waitUntil(lambda: shown_paths == ["/Movies/Resolved"])
    assert pansou.resolve_calls == ["pan-1"]
    assert "文件浏览" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]


def test_main_window_ignores_stale_global_search_results(qtbot) -> None:
    telegram = AsyncKeywordSearchController(
        {
            "旧关键词": ([_vod("旧结果")], 1),
            "新关键词": ([], 0),
        }
    )
    emby = KeywordSearchableController(
        {
            "旧关键词": ([], 0),
            "新关键词": ([_vod("新结果")], 1),
        }
    )

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("旧关键词")
    window.global_search_button.click()
    qtbot.waitUntil(lambda: telegram.search_calls == [("旧关键词", 1)])

    window.global_search_edit.setText("新关键词")
    window.global_search_button.click()
    qtbot.waitUntil(lambda: telegram.search_calls == [("旧关键词", 1), ("新关键词", 1)])

    telegram.release("新关键词")
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["Emby(1)"])

    telegram.release("旧关键词")
    qtbot.wait(100)

    assert [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["Emby(1)"]
    assert emby.search_calls == [("旧关键词", 1), ("新关键词", 1)]


def test_main_window_clear_global_search_restores_original_tabs_and_titles(qtbot) -> None:
    telegram = SearchableController([_vod("Telegram One")], total=4)
    plugin_controller = SearchableController([_vod("Plugin One")], total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": False},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    original_titles = [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()
    qtbot.waitUntil(
        lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "电报影视(4)",
            "红果短剧(1)",
        ]
    )

    window.global_search_clear_button.click()
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == original_titles)


def test_main_window_clearing_search_text_during_in_progress_search_restores_main_tabs(qtbot) -> None:
    telegram = AsyncKeywordSearchController({"庆余年": ([_vod("Telegram One")], 12)})
    plugin_controller = AsyncKeywordSearchController({"庆余年": ([_vod("Plugin One")], 1)})

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[
            {"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": False},
        ],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    original_titles = [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()
    qtbot.waitUntil(lambda: telegram.search_calls == [("庆余年", 1)])
    assert window.nav_tabs.count() == 0

    window.global_search_edit.clear()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == original_titles)
    assert window.global_search_status_label.text() == ""

    telegram.release("庆余年")
    plugin_controller.release("庆余年")
    qtbot.wait(100)

    assert [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == original_titles


def test_main_window_shows_live_source_manager_button_after_plugin_manager(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        live_source_manager=object(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert window.plugin_manager_button.text() == "插件管理"
    assert window.live_source_manager_button.text() == "直播源管理"


def test_main_window_keeps_existing_header_buttons_without_parse_manager(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert window.plugin_manager_button.text() == "插件管理"
    assert window.live_source_manager_button.text() == "直播源管理"
    assert not hasattr(window, "parse_manager_button")


def test_main_window_open_player_creates_session_without_blocking_ui(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class SlowPlayerController(FakePlayerController):
        def create_session(
            self,
            vod,
            playlist,
            clicked_index: int,
            playlists=None,
            playlist_index: int = 0,
            detail_resolver=None,
            resolved_vod_by_id=None,
            use_local_history=True,
        restore_history=False,
        playback_loader=None,
        async_playback_loader=False,
        detail_action_runner=None,
        detail_field_runner=None,
        danmaku_controller=None,
        playback_progress_reporter=None,
        playback_stopper=None,
            playback_history_loader=None,
            playback_history_saver=None,
            initial_log_message="",
            is_placeholder=False,
        ):
            time.sleep(0.15)
            return super().create_session(
                vod,
                playlist,
                clicked_index,
                playlists=playlists,
                playlist_index=playlist_index,
                detail_resolver=detail_resolver,
                resolved_vod_by_id=resolved_vod_by_id,
                use_local_history=use_local_history,
                restore_history=restore_history,
                playback_loader=playback_loader,
                async_playback_loader=async_playback_loader,
                detail_action_runner=detail_action_runner,
                detail_field_runner=detail_field_runner,
                danmaku_controller=danmaku_controller,
                playback_progress_reporter=playback_progress_reporter,
                playback_stopper=playback_stopper,
                playback_history_loader=playback_history_loader,
                playback_history_saver=playback_history_saver,
                initial_log_message=initial_log_message,
                is_placeholder=is_placeholder,
            )

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.show_calls = 0
            self.raise_calls = 0
            self.activate_calls = 0
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            self.show_calls += 1

        def raise_(self) -> None:
            self.raise_calls += 1

        def activateWindow(self) -> None:
            self.activate_calls += 1

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    config = AppConfig()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=SlowPlayerController(),
        config=config,
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.show()
    request = OpenPlayerRequest(
        vod=VodItem(vod_id="vod-1", vod_name="Movie"),
        playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
        clicked_index=0,
        source_mode="detail",
        source_vod_id="vod-1",
    )

    started_at = time.perf_counter()
    window.open_player(request)
    elapsed_seconds = time.perf_counter() - started_at

    assert elapsed_seconds < 0.1
    assert window.isHidden() is False
    assert window.player_window is None

    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)
    assert window.isHidden() is True
    assert config.last_active_window == "player"
    assert config.last_playback_mode == "detail"
    assert config.last_playback_vod_id == "vod-1"
    assert config.last_player_paused is False


def test_main_window_passes_default_video_cover_loader_to_player_window(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    captured: dict[str, object] = {}

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            captured["loader"] = kwargs.get("default_video_cover_loader")
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)

    def load_video_cover() -> str:
        return "https://img.example/fallback.jpg"

    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        default_video_cover_loader=load_video_cover,
    )
    qtbot.addWidget(window)

    request = OpenPlayerRequest(
        vod=VodItem(vod_id="vod-1", vod_name="Movie"),
        playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
        clicked_index=0,
    )
    window.open_player(request)

    qtbot.waitUntil(lambda: "loader" in captured)
    assert captured["loader"] is load_video_cover


def test_main_window_passes_detail_action_runner_to_player_controller(qtbot) -> None:
    detail_action_runner = lambda item, action_id: [item, action_id]
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    request = OpenPlayerRequest(
        vod=VodItem(vod_id="vod-1", vod_name="Movie"),
        playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
        clicked_index=0,
        detail_action_runner=detail_action_runner,
    )

    session = window._create_player_session(request)

    assert session["detail_action_runner"] is detail_action_runner


def test_main_window_detail_field_category_click_loads_plugin_results(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedPluginController(FakeStaticController):
        def __init__(self) -> None:
            self.category_calls: list[tuple[str, int]] = []
            self.search_calls: list[tuple[str, int]] = []
            self.build_request_calls: list[str] = []

        def load_categories(self):
            return [type("Category", (), {"type_id": "movie", "type_name": "电影", "filters": []})()]

        def load_items(self, category_id: str, page: int, filters=None):
            self.category_calls.append((category_id, page))
            return [VodItem(vod_id="cat-1", vod_name="分类结果")], 1

        def search_items(self, keyword: str, page: int):
            self.search_calls.append((keyword, page))
            return [VodItem(vod_id="search-1", vod_name="搜索结果")], 1

        def build_request(self, vod_id: str):
            self.build_request_calls.append(vod_id)
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="详情结果"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_key="plugin-1",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    controller = RoutedPluginController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-1", "title": "插件1", "controller": controller, "search_enabled": True}],
    )
    qtbot.addWidget(window)
    request = controller.build_request("detail-1")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    runner(session["playlist"][0], PlaybackDetailFieldAction(type="category", value="movie"))

    qtbot.waitUntil(lambda: controller.category_calls == [("movie", 1)])
    plugin_page = window._plugin_pages[0][0]
    qtbot.waitUntil(lambda: bool(plugin_page.items) and plugin_page.items[0].vod_name == "分类结果")
    assert window.nav_tabs.currentWidget() is plugin_page


def test_main_window_detail_field_search_click_loads_plugin_results(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedPluginController(FakeStaticController):
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        def load_categories(self):
            return []

        def search_items(self, keyword: str, page: int):
            self.search_calls.append((keyword, page))
            return [VodItem(vod_id="search-1", vod_name="搜索结果")], 1

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="详情结果"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_key="plugin-1",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    controller = RoutedPluginController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-1", "title": "插件1", "controller": controller, "search_enabled": True}],
    )
    qtbot.addWidget(window)
    request = controller.build_request("detail-1")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    runner(session["playlist"][0], PlaybackDetailFieldAction(type="search", value="演员1"))

    qtbot.waitUntil(lambda: controller.search_calls == [("演员1", 1)])
    plugin_page = window._plugin_pages[0][0]
    qtbot.waitUntil(lambda: bool(plugin_page.items) and plugin_page.items[0].vod_name == "搜索结果")
    assert window.nav_tabs.currentWidget() is plugin_page


def test_main_window_detail_field_detail_click_opens_new_plugin_request(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedPluginController(FakeStaticController):
        def __init__(self) -> None:
            self.build_request_calls: list[str] = []

        def load_categories(self):
            return []

        def build_request(self, vod_id: str):
            self.build_request_calls.append(vod_id)
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name=f"详情:{vod_id}"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_key="plugin-1",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    controller = RoutedPluginController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-1", "title": "插件1", "controller": controller, "search_enabled": True}],
    )
    qtbot.addWidget(window)
    request = controller.build_request("detail-1")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    runner(session["playlist"][0], PlaybackDetailFieldAction(type="detail", value="detail-2"))

    qtbot.waitUntil(lambda: controller.build_request_calls == ["detail-1", "detail-2"])
    qtbot.waitUntil(lambda: len(window.player_window.opened) == 2)
    assert window.player_window.opened[-1][0]["vod"].vod_id == "detail-2"


def test_main_window_detail_field_link_click_opens_browser(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedPluginController(FakeStaticController):
        def load_categories(self):
            return []

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="详情结果"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="plugin",
                source_key="plugin-1",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    opened: list[str] = []
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    monkeypatch.setattr(main_window_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    controller = RoutedPluginController()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-1", "title": "插件1", "controller": controller, "search_enabled": True}],
    )
    qtbot.addWidget(window)
    request = controller.build_request("detail-1")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    runner(session["playlist"][0], PlaybackDetailFieldAction(type="link", value="https://example.com"))

    assert opened == ["https://example.com"]


def test_main_window_bilibili_metadata_category_click_loads_builtin_bilibili_results(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedBilibiliController(FakeStaticController):
        def __init__(self) -> None:
            self.category_calls: list[tuple[str, int]] = []

        def load_categories(self):
            return [type("Category", (), {"type_id": "recommend", "type_name": "推荐", "filters": []})()]

        def load_items(self, category_id: str, page: int, filters=None):
            self.category_calls.append((category_id, page))
            return [VodItem(vod_id="bili-1", vod_name="UP视频")], 1

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="B站详情"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="bilibili",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    controller = RoutedBilibiliController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        bilibili_controller=controller,
        config=AppConfig(),
        show_bilibili_tab=True,
    )
    qtbot.addWidget(window)
    request = controller.build_request("BV1xx411c7mD")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    assert callable(runner)

    runner(
        session["playlist"][0],
        PlaybackDetailFieldAction(target="bilibili", type="category", value="up:378885845"),
    )

    qtbot.waitUntil(lambda: controller.category_calls == [("up:378885845", 1)])
    assert window.bilibili_page is not None
    qtbot.waitUntil(lambda: bool(window.bilibili_page.items) and window.bilibili_page.items[0].vod_name == "UP视频")
    assert window.nav_tabs.currentWidget() is window.bilibili_page


def test_main_window_async_restore_failure_resets_last_active_window(qtbot) -> None:
    class FailingBrowseController(FakeStaticController):
        def build_request_from_detail(self, vod_id: str):
            raise RuntimeError(f"failed to restore {vod_id}")

    saved = {"count": 0}
    config = AppConfig(
        last_active_window="player",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
    )
    window = MainWindow(
        browse_controller=FailingBrowseController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("count", saved["count"] + 1),
    )
    qtbot.addWidget(window)

    window._start_restore_last_player()

    qtbot.waitUntil(lambda: config.last_active_window == "main")
    assert saved["count"] >= 1


def test_main_window_restore_last_player_routes_custom_live_to_live_controller(qtbot, monkeypatch) -> None:
    class RestoreBrowseController:
        def build_request_from_detail(self, vod_id: str):
            raise AssertionError(f"browse restore should not be used for {vod_id}")

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config) -> None:
            self.opened: list[tuple[object, bool]] = []

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RestoreLiveController(FakeStaticController):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def build_request(self, vod_id: str):
            self.calls.append(vod_id)
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="自定义频道"),
                playlist=[PlayItem(title="直播线路", url="https://live.example/custom.m3u8")],
                clicked_index=0,
                source_kind="live",
                source_mode="custom",
                source_vod_id=vod_id,
                use_local_history=False,
            )

    controller = RestoreLiveController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    config = AppConfig(
        last_active_window="player",
        last_playback_source="live",
        last_playback_mode="custom",
        last_playback_vod_id="custom-channel:9:channel-0",
        last_player_paused=True,
    )
    window = MainWindow(
        browse_controller=RestoreBrowseController(),
        live_controller=controller,
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: None,
    )
    qtbot.addWidget(window)

    restored = window.restore_last_player()

    assert restored is window.player_window
    assert controller.calls == ["custom-channel:9:channel-0"]
    assert window.player_window.opened[0][0]["vod"].vod_name == "自定义频道"
    assert window.player_window.opened[0][1] is True


def test_main_window_async_restore_without_saved_request_resets_last_active_window(qtbot) -> None:
    saved = {"count": 0}
    config = AppConfig(last_active_window="player")
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("count", saved["count"] + 1),
    )
    qtbot.addWidget(window)

    window._start_restore_last_player()

    qtbot.waitUntil(lambda: config.last_active_window == "main")
    assert saved["count"] >= 1


def test_main_window_async_restore_session_creation_failure_resets_last_active_window(qtbot) -> None:
    class RestoreBrowseController(FakeStaticController):
        def build_request_from_detail(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="Movie"),
                playlist=[PlayItem(title="Episode 1", url="1.m3u8")],
                clicked_index=0,
                source_mode="detail",
                source_vod_id=vod_id,
            )

    class FailingPlayerController(FakePlayerController):
        def create_session(
            self,
            vod,
            playlist,
            clicked_index: int,
            playlists=None,
            playlist_index: int = 0,
            detail_resolver=None,
            resolved_vod_by_id=None,
            use_local_history=True,
            restore_history=False,
            playback_loader=None,
            async_playback_loader=False,
            detail_action_runner=None,
            detail_field_runner=None,
            danmaku_controller=None,
            playback_progress_reporter=None,
            playback_stopper=None,
            playback_history_loader=None,
            playback_history_saver=None,
            initial_log_message="",
            is_placeholder=False,
        ):
            del (
                vod,
                playlist,
                clicked_index,
                playlists,
                playlist_index,
                detail_resolver,
                resolved_vod_by_id,
                use_local_history,
                restore_history,
                playback_loader,
                async_playback_loader,
                detail_action_runner,
                detail_field_runner,
                danmaku_controller,
                playback_progress_reporter,
                playback_stopper,
                playback_history_loader,
                playback_history_saver,
                initial_log_message,
                is_placeholder,
            )
            raise RuntimeError("session failed")

    saved = {"count": 0}
    errors: list[str] = []
    config = AppConfig(
        last_active_window="player",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
    )
    window = MainWindow(
        browse_controller=RestoreBrowseController(),
        history_controller=FakeStaticController(),
        player_controller=FailingPlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("count", saved["count"] + 1),
    )
    qtbot.addWidget(window)
    window.show_error = errors.append

    window._start_restore_last_player()

    qtbot.waitUntil(lambda: config.last_active_window == "main")
    assert errors == ["session failed"]
    assert saved["count"] >= 1


def test_main_window_drops_closed_player_window_reference_when_returning_to_main(qtbot) -> None:
    class ClosedPlayerWindow:
        def __init__(self) -> None:
            self.session = None

    config = AppConfig(last_active_window="player")
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.player_window = ClosedPlayerWindow()

    window._show_main_again()

    assert window.player_window is None
    assert config.last_active_window == "main"


def test_main_window_remaximizes_when_returning_from_player(qtbot, monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    config = AppConfig(last_active_window="player", main_window_geometry=b"saved-geometry")
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window._main_window_was_maximized_before_player = True

    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda _delay, callback: calls.append(("singleShot", callback)))
    monkeypatch.setattr(window, "showMaximized", lambda: calls.append(("showMaximized", None)))
    monkeypatch.setattr(window, "show", lambda: calls.append(("show", None)))
    monkeypatch.setattr(window, "restoreGeometry", lambda _geometry: calls.append(("restoreGeometry", None)) or True)

    window._show_main_again()

    assert ("restoreGeometry", None) in calls
    assert ("show", None) in calls
    assert ("showMaximized", None) in calls
    assert calls.index(("show", None)) < calls.index(("showMaximized", None))


def test_main_window_reapplies_saved_geometry_when_no_player_return_state(qtbot, monkeypatch) -> None:
    restore_calls: list[bytes] = []

    def fake_restore_geometry(self, geometry) -> bool:
        restore_calls.append(bytes(geometry.data()))
        return True

    monkeypatch.setattr(MainWindow, "restoreGeometry", fake_restore_geometry)
    config = AppConfig(last_active_window="player", main_window_geometry=b"saved-geometry")
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    restore_calls.clear()

    window._show_main_again()

    assert restore_calls == [b"saved-geometry"]


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_main_window_ignores_async_open_request_after_window_deletion(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config) -> None:
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            return None

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    controller = AsyncOpenController()
    window = MainWindow(
        telegram_controller=controller,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
    )
    destroyed = {"count": 0}
    window.destroyed.connect(lambda *_args: destroyed.__setitem__("count", destroyed["count"] + 1))

    item = VodItem(vod_id="vod-1", vod_name="Movie")
    window._handle_telegram_item_open_requested(item)
    qtbot.waitUntil(lambda: controller.calls == ["vod-1"], timeout=1000)

    window.deleteLater()
    qtbot.waitUntil(lambda: destroyed["count"] == 1, timeout=1000)

    controller.release()
    qtbot.wait(100)

    assert destroyed["count"] == 1


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_main_window_ignores_async_media_load_after_window_deletion(qtbot) -> None:
    controller = AsyncMediaController()
    window = MainWindow(
        live_controller=controller,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
    )
    destroyed = {"count": 0}
    window.destroyed.connect(lambda *_args: destroyed.__setitem__("count", destroyed["count"] + 1))

    item = type("Item", (), {"vod_id": "folder-1", "vod_name": "Folder", "vod_tag": "folder"})()
    window._open_media_folder(window.live_page, controller, item)
    qtbot.waitUntil(lambda: controller.calls == ["folder-1"], timeout=1000)

    window.deleteLater()
    qtbot.waitUntil(lambda: destroyed["count"] == 1, timeout=1000)

    controller.release()
    qtbot.wait(100)

    assert destroyed["count"] == 1


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_main_window_ignores_async_restore_after_window_deletion(qtbot) -> None:
    controller = AsyncRestoreController()
    config = AppConfig(
        last_active_window="player",
        last_playback_mode="detail",
        last_playback_vod_id="vod-1",
    )
    window = MainWindow(
        browse_controller=controller,
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=config,
    )
    destroyed = {"count": 0}
    window.destroyed.connect(lambda *_args: destroyed.__setitem__("count", destroyed["count"] + 1))

    window._start_restore_last_player()
    qtbot.waitUntil(lambda: controller.calls == ["vod-1"], timeout=1000)

    window.deleteLater()
    qtbot.waitUntil(lambda: destroyed["count"] == 1, timeout=1000)

    controller.release()
    qtbot.wait(100)

    assert destroyed["count"] == 1
