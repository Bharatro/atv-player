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
    LiveSourceConfig,
    LiveSourceChannelView,
    PlayItem,
    PlaybackSource,
    PlaybackSourceGroup,
    OpenPlayerRequest,
    VodItem,
)
from atv_player.controllers.player_controller import PlayerSession
from atv_player.ui.main_window import MainWindow
from atv_player.ui.player_window import PlayerWindow

from tests.test_main_window_ui import (
    FakeStaticController,
    DummyHistoryController,
    FakePlayerController,
    FakePluginManager,
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


class TvLiveSourceManager:
    def __init__(
        self,
        sources: list[LiveSourceConfig],
        channel_views: dict[int, list[LiveSourceChannelView]] | None = None,
    ) -> None:
        self.sources = sources
        self.channel_views = dict(channel_views or {})

    def list_sources(self):
        return list(self.sources)

    def load_channel_views(self, source_id: int):
        return list(self.channel_views.get(source_id, []))

    def load_cached_channel_views(self, source_id: int):
        return list(self.channel_views.get(source_id, []))


class TvLiveController:
    def __init__(self) -> None:
        self.item_calls: list[tuple[str, int]] = []
        self.folder_calls: list[str] = []
        self.request_calls: list[str] = []

    def load_categories(self):
        return []

    def load_items(self, category_id: str, page: int, filters=None):
        del filters
        self.item_calls.append((category_id, page))
        if category_id == "custom:2":
            return [
                VodItem(vod_id="custom-folder:2:cctv", vod_name="央视", vod_tag="folder"),
            ], 1
        if category_id == "custom:1":
            return [
                VodItem(vod_id="custom-channel:1:backup", vod_name="备用卫视", vod_tag="file"),
            ], 1
        return [], 0

    def load_folder_items(self, vod_id: str):
        self.folder_calls.append(vod_id)
        if vod_id == "custom-folder:2:cctv":
            return [
                VodItem(vod_id="notice", vod_name="公告", vod_tag="file"),
                VodItem(vod_id="custom-channel:2:cctv1", vod_name="CCTV-1", vod_tag="file"),
                VodItem(vod_id="custom-channel:2:cctv2", vod_name="CCTV-2", vod_tag="file"),
            ], 3
        return [], 0

    def build_request(self, vod_id: str):
        self.request_calls.append(vod_id)
        if vod_id == "notice":
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="公告", detail_style="live"),
                playlist=[PlayItem(title="公告", url="请在直播源管理中配置频道")],
                clicked_index=0,
                source_kind="live",
                source_mode="custom",
                source_vod_id=vod_id,
                use_local_history=False,
            )
        title = {
            "custom-channel:2:cctv1": "CCTV-1",
            "custom-channel:2:cctv2": "CCTV-2",
            "custom-channel:1:backup": "备用卫视",
        }.get(vod_id, vod_id)
        if vod_id == "custom-channel:2:cctv2":
            return OpenPlayerRequest(
                vod=VodItem(
                    vod_id=vod_id,
                    vod_name=title,
                    vod_pic=f"{title}.png",
                    detail_style="live",
                    epg_current="09:00-10:00 新闻",
                    epg_schedule="10:00-11:00 纪录片",
                ),
                playlist=[
                    PlayItem(
                        title=f"{title} 1",
                        url="https://live.example/cctv2-main.m3u8",
                        headers={"User-Agent": "UA-1"},
                    ),
                    PlayItem(
                        title=f"{title} 2",
                        url="https://live.example/cctv2-backup.m3u8",
                        headers={"User-Agent": "UA-2"},
                    ),
                ],
                clicked_index=0,
                source_kind="live",
                source_mode="custom",
                source_vod_id=vod_id,
                use_local_history=False,
            )
        return OpenPlayerRequest(
            vod=VodItem(vod_id=vod_id, vod_name=title, vod_pic=f"{title}.png", detail_style="live"),
            playlist=[PlayItem(title=title, url=f"https://live.example/{vod_id}.m3u8")],
            clicked_index=0,
            source_kind="live",
            source_mode="custom",
            source_vod_id=vod_id,
            use_local_history=False,
        )


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


def test_main_window_tv_home_builds_default_live_source_request(qtbot) -> None:
    live_controller = TvLiveController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="browse"),
        live_controller=live_controller,
        live_source_manager=TvLiveSourceManager(
            [
                LiveSourceConfig(id=1, display_name="备用源", enabled=True, sort_order=0, is_default=False),
                LiveSourceConfig(id=2, display_name="默认源", enabled=True, sort_order=9, is_default=True),
            ],
            channel_views={
                2: [
                    LiveSourceChannelView(
                        source_id=2,
                        channel_id="cctv1",
                        group_key="",
                        channel_name="CCTV-1",
                        stream_url="https://live.example/cctv1.m3u8",
                    ),
                    LiveSourceChannelView(
                        source_id=2,
                        channel_id="cctv2",
                        group_key="",
                        channel_name="CCTV-2",
                        stream_url="https://live.example/cctv2.m3u8",
                    ),
                ]
            },
        ),
    )
    qtbot.addWidget(window)

    request = window._build_tv_live_player_request()

    assert request.source_kind == "live"
    assert request.source_key == "tv"
    assert request.source_mode == "tv"
    assert request.use_local_history is False
    assert request.vod.vod_name == "CCTV-1"
    assert request.playlist[0].title == "CCTV-1"
    assert [source.label for source in request.source_groups[0].sources] == ["默认源", "备用源"]
    assert [item.title for item in request.source_groups[0].sources[0].playlist] == ["CCTV-1", "CCTV-2"]
    assert [item.title for item in request.source_groups[0].sources[1].playlist] == ["备用卫视"]
    assert live_controller.folder_calls == []
    assert live_controller.request_calls == ["custom-channel:1:backup"]


def test_main_window_tv_home_restores_last_live_channel_with_epg_and_lines(qtbot) -> None:
    save_calls: list[str] = []
    config = AppConfig(
        home_mode="browse",
        last_playback_source="live",
        last_playback_source_key="tv",
        last_playback_mode="tv",
        last_playback_vod_id="custom-channel:2:cctv2",
    )
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
        save_config=lambda: save_calls.append(config.last_playback_vod_id),
        live_controller=TvLiveController(),
        live_source_manager=TvLiveSourceManager(
            [LiveSourceConfig(id=2, display_name="默认源", enabled=True, sort_order=0, is_default=True)],
        ),
    )
    qtbot.addWidget(window)

    request = window._build_tv_live_player_request()

    assert request.clicked_index == 1
    assert request.vod.vod_name == "CCTV-2"
    assert request.vod.epg_current == "09:00-10:00 新闻"
    assert request.vod.epg_schedule == "10:00-11:00 纪录片"
    assert request.playlist[1].selected_playback_quality_id == "line-1"
    assert [quality.label for quality in request.playlist[1].playback_qualities] == ["线路 1", "线路 2"]
    assert [quality.headers for quality in request.playlist[1].playback_qualities] == [
        {"User-Agent": "UA-1"},
        {"User-Agent": "UA-2"},
    ]

    request.playback_progress_reporter(request.playlist[1], 0, False)

    assert config.last_playback_vod_id == "custom-channel:2:cctv2"
    assert config.last_playback_clicked_vod_id == "custom-channel:2:cctv2"
    assert save_calls[-1] == "custom-channel:2:cctv2"


def test_main_window_tv_playlist_enrichment_updates_player_source_and_channel_lists(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="browse"),
    )
    qtbot.addWidget(window)

    current_item = PlayItem(
        title="CCTV-2",
        url="https://live.example/cctv2.m3u8",
        vod_id="custom-channel:2:cctv2",
    )
    session = PlayerSession(
        vod=VodItem(vod_id="custom-channel:2:cctv2", vod_name="CCTV-2", detail_style="live"),
        playlist=[current_item],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        playlists=[[current_item]],
        source_groups=[
            PlaybackSourceGroup(
                label="直播源",
                sources=[PlaybackSource(label="默认源", playlist=[current_item])],
            )
        ],
        source_kind="live",
        source_key="tv",
    )
    full_groups = [
        PlaybackSourceGroup(
            label="直播源",
            sources=[
                PlaybackSource(
                    label="默认源",
                    playlist=[
                        PlayItem(
                            title="CCTV-1",
                            url="https://live.example/cctv1.m3u8",
                            vod_id="custom-channel:2:cctv1",
                        ),
                        PlayItem(
                            title="CCTV-2",
                            url="https://live.example/cctv2.m3u8",
                            vod_id="custom-channel:2:cctv2",
                        ),
                    ],
                ),
                PlaybackSource(
                    label="备用源",
                    playlist=[
                        PlayItem(
                            title="备用卫视",
                            url="https://live.example/backup.m3u8",
                            vod_id="custom-channel:1:backup",
                        )
                    ],
                ),
            ],
        )
    ]
    render_calls: list[str] = []
    fake_player = SimpleNamespace(
        session=session,
        current_index=0,
        _flatten_source_groups=lambda groups: (
            [source.playlist for group in groups for source in group.sources],
            {(0, 0): 0, (0, 1): 1},
        ),
        _render_playlist_source_combos=lambda: render_calls.append("sources"),
        _render_playlist_title_tabs=lambda: render_calls.append("tabs"),
        _render_playlist_items=lambda: render_calls.append("items"),
        _render_bilibili_playlist_tree=lambda: render_calls.append("tree"),
        _sync_playlist_panel_mode=lambda: render_calls.append("mode"),
        append_status_log=lambda message: render_calls.append(message),
    )
    window.player_window = fake_player
    window._tv_playlist_request_id = 3

    window._handle_tv_playlist_enrichment_succeeded(
        3,
        {
            "active_vod_id": "custom-channel:2:cctv2",
            "source_groups": full_groups,
            "resolved_vod_by_id": {
                "custom-channel:2:cctv2": VodItem(
                    vod_id="custom-channel:2:cctv2",
                    vod_name="CCTV-2",
                    detail_style="live",
                    epg_current="09:00-10:00 新闻",
                )
            },
        },
    )

    assert [source.label for source in session.source_groups[0].sources] == ["默认源", "备用源"]
    assert [item.title for item in session.playlist] == ["CCTV-1", "CCTV-2"]
    assert session.source_group_index == 0
    assert session.source_index == 0
    assert session.playlist_index == 0
    assert fake_player.current_index == 1
    assert session.detail_resolver(session.playlist[1]).epg_current == "09:00-10:00 新闻"
    assert "items" in render_calls


def test_main_window_tv_home_fallback_shows_live_page(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(home_mode="browse"),
    )
    qtbot.addWidget(window)

    window._show_tv_home_mode_fallback("启用的直播源没有可播放频道")

    assert window._home_stack.currentWidget() is window.nav_tabs
    assert window.nav_tabs.currentWidget() is window.live_page
    assert not window.nav_tabs.isHidden()
    assert "没有可播放频道" in window.global_search_status_label.text()


def test_player_window_tv_source_switch_starts_at_first_channel() -> None:
    source_groups = [
        PlaybackSourceGroup(
            label="直播源",
            sources=[
                PlaybackSource(
                    label="源一",
                    playlist=[
                        PlayItem(title="源一-1", url="https://live.example/a1.m3u8"),
                        PlayItem(title="源一-2", url="https://live.example/a2.m3u8"),
                    ],
                ),
                PlaybackSource(
                    label="源二",
                    playlist=[
                        PlayItem(title="源二-1", url="https://live.example/b1.m3u8"),
                        PlayItem(title="源二-2", url="https://live.example/b2.m3u8"),
                    ],
                ),
            ],
        )
    ]
    fake_window = SimpleNamespace(
        session=PlayerSession(
            vod=VodItem(vod_id="live", vod_name="直播", detail_style="live"),
            playlist=source_groups[0].sources[0].playlist,
            start_index=1,
            start_position_seconds=0,
            speed=1.0,
            playlists=[source.playlist for source in source_groups[0].sources],
            source_groups=source_groups,
            source_kind="live",
            source_key="tv",
        ),
        current_index=1,
        controller=SimpleNamespace(),
        playlist_title_mode="episode",
        _session_source_groups=lambda: source_groups,
        _flatten_source_groups=lambda groups: (
            [source.playlist for group in groups for source in group.sources],
            {(0, 0): 0, (0, 1): 1},
        ),
        report_progress=lambda **kwargs: None,
        _stop_current_playback=lambda: None,
        _invalidate_play_item_resolution=lambda: None,
        _reset_auto_switched_failure_sources=lambda: None,
        _render_playlist_source_combos=lambda: None,
        _render_playlist_title_tabs=lambda: None,
        _render_playlist_items=lambda: None,
        _render_bilibili_playlist_tree=lambda: None,
        _sync_playlist_panel_mode=lambda: None,
        _start_episode_title_enhancement=lambda: None,
        _load_current_item=lambda **kwargs: None,
        _refresh_window_title=lambda: None,
        _append_log=lambda message: None,
    )

    PlayerWindow._switch_active_source(fake_window, 0, 1)

    assert fake_window.current_index == 0
    assert fake_window.session.playlist[0].title == "源二-1"


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
    assert window.global_search_container.isHidden()
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
    window.browse_button.click()
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert window.nav_tabs.currentWidget() is window.browse_page

    window.home_button.click()

    assert window._home_stack.currentWidget() is window._media_home_page
    assert window.nav_tabs.isHidden()


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


def test_main_window_tv_mode_does_not_load_startup_plugins_until_browse(qtbot) -> None:
    config = AppConfig(home_mode="tv")
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
        live_source_manager=TvLiveSourceManager([]),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)

    assert load_calls == []
    assert window._startup_plugin_load_state == "idle"

    config.home_mode = "browse"
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
