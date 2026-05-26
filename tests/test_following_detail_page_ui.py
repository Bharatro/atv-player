from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from atv_player.controllers.following_controller import FollowingDetailView
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    FollowingSeason,
)
from atv_player.models import AppConfig
from atv_player.ui.following_detail_page import (
    FollowingDetailPage,
    FollowingEpisodePreviewDialog,
    FollowingPersonCard,
    QDesktopServices,
    _person_avatar,
)


class FakeController:
    def __init__(self) -> None:
        self.manual_checks: list[int] = []
        self.metadata_refreshes: list[int] = []
        self.progress_updates: list[tuple[int, int, int]] = []
        self.loaded_seasons: list[int] = []

    def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
        del refresh_if_empty
        return FollowingDetailView(
            record=FollowingRecord(
                id=following_id,
                title="凡人修仙传",
                poster="poster",
                backdrop="backdrop",
                rating="8.2",
                provider="bangumi",
                provider_id="subject:1",
                season_number=1,
                current_season_number=1,
                current_episode=127,
                latest_episode=128,
                total_episodes=156,
                has_update=True,
            ),
            snapshot=FollowingDetailSnapshot(
                following_id=following_id,
                overview="长篇简介",
                metadata_fields=[
                    {"label": "类型", "value": "喜剧 / 悬疑 / 犯罪"},
                    {"label": "年代", "value": "2026"},
                    {"label": "地区", "value": "内地"},
                    {"label": "语言", "value": "普通话"},
                    {"label": "导演", "value": "刘海波"},
                    {"label": "演员", "value": "王骁,田曦薇,王传君,朱云峰"},
                    {"label": "别名", "value": "擒贼记 / Low IQ Crime / Born with Luck"},
                    {"label": "豆瓣ID", "value": "35517044"},
                    {"label": "IMDb ID", "value": "tt32592348"},
                    {"label": "TMDB ID", "value": "272432"},
                    {"label": "更新时间", "value": "2026-05-25"},
                    {"label": "更新状态", "value": "更新至第128集"},
                ],
                cast=[{"name": "韩立", "role": "主角", "avatar": "avatar"}],
                crew=[{"name": "导演", "job": "Director", "avatar": "/director.jpg"}],
                seasons=[FollowingSeason(season_number=1, title="第一季", episode_count=156)],
                episodes=[
                    FollowingEpisode(
                        episode_number=128,
                        title="新章",
                        overview="完整剧情",
                        still="still",
                    )
                ],
                backdrops=["backdrop"],
            ),
        )

    def check_one(self, following_id: int) -> None:
        self.manual_checks.append(following_id)

    def refresh_metadata(self, following_id: int):
        self.metadata_refreshes.append(following_id)
        return self.load_detail(following_id, refresh_if_empty=False)

    def load_detail_season(self, following_id: int, *, season_number: int):
        self.loaded_seasons.append(season_number)
        view = self.load_detail(following_id, refresh_if_empty=False)
        view.snapshot.seasons = [
            FollowingSeason(season_number=1, title="第一季", episode_count=2),
            FollowingSeason(season_number=2, title="第二季", episode_count=1),
        ]
        if season_number == 2:
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1")
            ]
        return view

    def record_playback_progress(
        self,
        following_id: int,
        *,
        current_season_number: int,
        current_episode: int,
        position_seconds: int,
    ) -> None:
        del position_seconds
        self.progress_updates.append((following_id, current_season_number, current_episode))


def test_following_detail_page_renders_reference_layout_and_actions(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    search_play: list[int] = []
    unfollow: list[int] = []
    page.search_play_requested.connect(search_play.append)
    page.unfollow_requested.connect(unfollow.append)

    page.load_record(1)
    page.search_play_button.click()
    page.manual_check_button.click()
    qtbot.waitUntil(lambda: page.status_label.text() == "已完成检查更新", timeout=1000)
    assert page.status_label.text() == "已完成检查更新"
    page.refresh_metadata_button.click()
    qtbot.waitUntil(lambda: page.status_label.text() == "元数据已更新", timeout=1000)
    assert page.status_label.text() == "元数据已更新"

    from unittest.mock import patch
    from atv_player.ui.following_detail_page import FollowingProgressDialog

    original_exec = FollowingProgressDialog.exec

    def fake_exec(self_dialog):
        self_dialog.accepted_season_number = 1
        self_dialog.accepted_episode = 128
        return 1

    with patch.object(FollowingProgressDialog, "exec", fake_exec):
        page.set_progress_button.click()

    page.unfollow_button.click()

    assert page.title_label.text() == "凡人修仙传"
    assert "看到 S1E127" in page.meta_label.text()
    assert "最新 S1E128 / 总 156" in page.meta_label.text()
    assert "类型: 喜剧 / 悬疑 / 犯罪" in page.overview_label.text()
    assert "导演: 刘海波" in page.overview_label.text()
    assert "演员: 王骁,田曦薇,王传君,朱云峰" in page.overview_label.text()
    assert "豆瓣ID: 35517044" in page.overview_label.text()
    assert "IMDb ID: tt32592348" in page.overview_label.text()
    assert "TMDB ID: 272432" in page.overview_label.text()
    assert "更新时间:" not in page.overview_label.text()
    assert "更新状态:" not in page.overview_label.text()
    assert "简介:\n长篇简介" in page.overview_label.text()
    assert page.page_scroll.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"
    episode_model = page.episode_browser.episode_list.model()
    assert episode_model.data(
        episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole
    ).startswith("128")
    assert page.cast_widgets[0].name_label.text() == "韩立"
    assert search_play == [1]
    assert unfollow == [1]
    assert controller.manual_checks == [1]
    assert controller.metadata_refreshes == [1]
    assert controller.progress_updates == [(1, 1, 128)]


def test_following_detail_page_uses_top_split_and_two_bottom_rows(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.show()

    page.load_record(1)

    assert page.top_section.objectName() == "followingDetailTopSection"
    assert page.metadata_panel.objectName() == "followingDetailMetadataPanel"
    assert page.poster_carousel_panel.objectName() == "followingDetailPosterCarousel"
    assert page.poster_carousel_panel.layout().indexOf(page.poster_label) == -1
    assert page.episodes_section.objectName() == "followingDetailEpisodesSection"
    assert page.cast_section.objectName() == "followingDetailCastSection"
    assert page.episode_browser.grid_columns() == 1
    assert page.episode_browser.season_detail_panel.isVisible() is True
    assert page.episode_browser.episode_list_panel.isVisible() is True
    assert page.episode_browser.season_list.model().rowCount() == 1
    assert page.episode_browser.episode_list.model().rowCount() == 1
    assert page.cast_scroll.verticalScrollBarPolicy().name == "ScrollBarAlwaysOff"


def test_following_detail_page_groups_multiple_seasons_and_switches_current_season(qtbot) -> None:
    class MultiSeasonController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.snapshot.seasons = [
                FollowingSeason(season_number=1, title="第一季", episode_count=2),
                FollowingSeason(season_number=2, title="第二季", episode_count=1),
            ]
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1"),
            ]
            return view

    page = FollowingDetailPage(MultiSeasonController())
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    episode_model = page.episode_browser.episode_list.model()
    assert season_model.rowCount() == 2
    assert episode_model.rowCount() == 2

    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert episode_model.rowCount() == 1
    assert "S2E1" in episode_model.data(
        episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole
    )


def test_following_detail_page_loads_unloaded_season_on_selection(qtbot) -> None:
    class LazySeasonController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.snapshot.seasons = [
                FollowingSeason(season_number=1, title="第一季", episode_count=2),
                FollowingSeason(season_number=2, title="第二季", episode_count=1),
            ]
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
            ]
            return view

    controller = LazySeasonController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))

    qtbot.waitUntil(lambda: controller.loaded_seasons == [2], timeout=1000)
    qtbot.waitUntil(
        lambda: page.episode_browser.episode_list.model().rowCount() == 1,
        timeout=1000,
    )

    episode_model = page.episode_browser.episode_list.model()
    assert controller.loaded_seasons == [2]
    assert "S2E1" in episode_model.data(episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole)


def test_following_detail_page_loads_initial_selected_season_when_snapshot_has_only_season_summaries(qtbot) -> None:
    class SummaryOnlyController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.season_number = 1
            view.snapshot.seasons = [
                FollowingSeason(season_number=1, title="第一季", episode_count=2),
                FollowingSeason(season_number=2, title="第二季", episode_count=1),
            ]
            view.snapshot.episodes = []
            return view

        def load_detail_season(self, following_id: int, *, season_number: int):
            self.loaded_seasons.append(season_number)
            view = self.load_detail(following_id, refresh_if_empty=False)
            if season_number == 1:
                view.snapshot.episodes = [
                    FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                    FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                ]
            return view

    controller = SummaryOnlyController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    qtbot.waitUntil(lambda: controller.loaded_seasons == [1], timeout=1000)
    qtbot.waitUntil(
        lambda: page.episode_browser.episode_list.model().rowCount() == 2,
        timeout=1000,
    )

    episode_model = page.episode_browser.episode_list.model()
    assert controller.loaded_seasons == [1]
    assert "S1E1" in episode_model.data(episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole)


def test_following_detail_page_prefers_provider_id_season_over_specials_on_initial_load(qtbot) -> None:
    class SpecialsFirstController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.provider = "tmdb"
            view.record.provider_id = "tv:76479:season:1"
            view.record.season_number = 0
            view.snapshot.seasons = [
                FollowingSeason(season_number=0, title="特别篇", episode_count=0),
                FollowingSeason(season_number=1, title="第一季", episode_count=8),
            ]
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
            ]
            return view

    page = FollowingDetailPage(SpecialsFirstController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.episode_browser.current_season_number() == 1
    assert page.episode_browser.episode_list.model().rowCount() == 1


def test_following_detail_page_uses_configured_initial_grid_columns(qtbot) -> None:
    page = FollowingDetailPage(
        FakeController(),
        config=AppConfig(following_episode_grid_columns=1),
    )
    qtbot.addWidget(page)
    page.load_record(1)

    assert page.episode_browser.grid_columns() == 1
    assert page.episode_browser.grid_cycle_button.toolTip() == "单列"


def test_following_detail_page_persists_grid_columns_after_cycle_click(qtbot) -> None:
    config = AppConfig(following_episode_grid_columns=1)
    saved: list[int] = []

    def save_config() -> None:
        saved.append(config.following_episode_grid_columns)

    page = FollowingDetailPage(FakeController(), config=config, save_config=save_config)
    qtbot.addWidget(page)
    page.load_record(1)

    page.episode_browser.grid_cycle_button.click()

    assert config.following_episode_grid_columns == 2
    assert saved == [2]


def test_following_detail_page_uses_browser_owned_three_pane_workspace(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.show()
    page.load_record(1)

    assert not hasattr(page, "season_header_title_label")
    assert page.episode_browser.season_detail_panel.isVisible() is True
    assert page.episode_browser.episode_list_panel.isVisible() is True


def test_following_detail_page_updates_middle_pane_when_switching_season(qtbot) -> None:
    class MultiSeasonController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.snapshot.seasons = [
                FollowingSeason(season_number=1, title="第一季", overview="第一季简介", episode_count=2),
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    overview="第二季简介",
                    air_date="2026-05-13",
                    episode_count=1,
                ),
            ]
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1"),
            ]
            return view

    page = FollowingDetailPage(MultiSeasonController())
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert page.episode_browser.season_detail_title_label.text() == "第二季"
    assert page.episode_browser.season_detail_air_date_label.text() == "2026-05-13"
    assert page.episode_browser.season_detail_episode_count_label.text() == "共 1 集"
    assert "第二季简介" in page.episode_browser.season_detail_overview_label.text()


def test_following_detail_page_opens_preview_dialog_from_episode_activation(
    qtbot, monkeypatch
) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)
    opened: list[int] = []

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.episode.episode_number) or 1,
    )

    model = page.episode_browser.episode_list.model()
    page.episode_browser._handle_episode_activated(model.index(0, 0))

    assert opened == [128]


def test_following_episode_preview_dialog_shows_air_date_and_runtime_on_same_line(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=24,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13 · 24m"


def test_following_episode_preview_dialog_omits_runtime_separator_when_runtime_missing(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=0,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13"


def test_following_episode_preview_dialog_includes_status_text(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=24,
        ),
        status_text="已更新",
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13 · 24m · 已更新"
    assert dialog.mark_watched_button.text() == "标记本集已看"


def test_following_detail_page_preview_dialog_marks_episode_as_watched(qtbot, monkeypatch) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    def fake_exec(self_dialog):
        self_dialog.mark_watched_requested = True
        return 1

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        fake_exec,
    )

    model = page.episode_browser.episode_list.model()
    page.episode_browser._handle_episode_activated(model.index(0, 0))

    assert page.controller.progress_updates[-1] == (1, 1, 128)
    assert page.status_label.text() == "已标记本集为已看"


def test_following_detail_title_and_metadata_text_are_selectable(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)

    page.load_record(1)

    selectable = Qt.TextInteractionFlag.TextSelectableByMouse
    assert page.title_label.textInteractionFlags() & selectable
    assert page.meta_label.textInteractionFlags() & selectable
    assert page.overview_label.textInteractionFlags() & selectable


def test_following_person_card_inner_labels_have_no_borders(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)

    page.load_record(1)

    card = page.cast_widgets[0]
    assert card.avatar_label.width() < 144
    assert card.avatar_label.height() < 216
    assert card.minimumHeight() < 292
    assert page.episodes_section.minimumHeight() > 400
    assert page.cast_scroll.minimumHeight() < 334
    assert page.cast_scroll.maximumHeight() < 360
    assert "border: 0" in card.avatar_label.styleSheet()
    assert "border: 0" in card.name_label.styleSheet()
    assert "border: 0" in card.role_label.styleSheet()


def test_following_person_card_uses_name_initial_when_avatar_missing(qtbot) -> None:
    card = FollowingPersonCard({"name": "王少雄", "job": "Screenplay"})
    qtbot.addWidget(card)

    assert card.avatar_label.text() == "王"
    assert "border: 0" in card.avatar_label.styleSheet()


def test_following_person_avatar_uses_tmdb_face_image_size() -> None:
    assert (
        _person_avatar({"avatar": "/sLnMwjp8kX423aCXScG1IOacS1r.jpg"})
        == "https://media.themoviedb.org/t/p/w300_and_h450_face/sLnMwjp8kX423aCXScG1IOacS1r.jpg"
    )


def test_following_person_card_clears_fallback_background_after_avatar_load(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)
    card = page.cast_widgets[0]

    page._handle_image_loaded(card.avatar_label, QImage(32, 32, QImage.Format.Format_RGB32))

    assert card.avatar_label.text() == ""
    assert "background: transparent" in card.avatar_label.styleSheet()


def test_following_person_card_opens_tmdb_person_link_on_click(qtbot, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    card = FollowingPersonCard(
        {
            "name": "王骁",
            "role": "Zhang Yi'ang",
            "url": "https://www.themoviedb.org/person/2027615",
        }
    )
    qtbot.addWidget(card)

    assert card.toolTip() == ""
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)

    assert opened == ["https://www.themoviedb.org/person/2027615"]


def test_following_detail_page_omits_unknown_episode_counts(qtbot) -> None:
    class UnknownCountsController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.latest_episode = 0
            view.record.total_episodes = 0
            return view

    page = FollowingDetailPage(UnknownCountsController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "最新 0" not in page.meta_label.text()
    assert "总 0" not in page.meta_label.text()
    assert "看到 S1E127" in page.meta_label.text()


def test_following_detail_page_shows_manual_check_error(qtbot) -> None:
    class BrokenCheckController(FakeController):
        def check_one(self, following_id: int) -> None:
            super().check_one(following_id)
            raise RuntimeError("网络错误")

    page = FollowingDetailPage(BrokenCheckController())
    qtbot.addWidget(page)

    page.load_record(1)
    page.manual_check_button.click()

    qtbot.waitUntil(lambda: page.manual_check_button.isEnabled(), timeout=1000)
    assert page.manual_check_button.isEnabled() is True
    assert "网络错误" in page.status_label.text()


def test_following_detail_page_does_not_auto_check_empty_detail_on_open(qtbot) -> None:
    class EmptyDetailController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            assert refresh_if_empty is False
            return FollowingDetailView(
                record=FollowingRecord(id=following_id, title="空详情", provider="tmdb"),
                snapshot=FollowingDetailSnapshot(following_id=following_id),
            )

    controller = EmptyDetailController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    assert controller.manual_checks == []
    assert "可手动检查更新" in page.status_label.text()


def test_following_detail_page_renders_completed_progress_text(qtbot) -> None:
    class CompletedController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.current_episode = 24
            view.record.latest_episode = 24
            view.record.total_episodes = 24
            return view

    page = FollowingDetailPage(CompletedController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "已看完 · S1共 24 集 · 已完结" in page.meta_label.text()
    assert "最新 24 / 总 24" not in page.meta_label.text()


def test_following_detail_page_does_not_auto_refresh_when_people_missing_avatars(qtbot) -> None:
    class NoAvatarController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.refreshed = False

        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            cast = [
                {"name": "王骁", "role": "Zhang Yi'ang"},
                {"name": "田曦薇", "role": "Li Qian"},
            ]
            if self.refreshed:
                cast[0]["avatar"] = "/wang.jpg"
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="低智商犯罪",
                    provider="tmdb",
                    provider_id="tv:272432:season:1",
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    overview="简介",
                    cast=cast,
                    crew=[{"name": "刘海波", "job": "Director"}],
                ),
            )

        def refresh_metadata(self, following_id: int):
            self.refreshed = True
            return super().refresh_metadata(following_id)

    controller = NoAvatarController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    qtbot.wait(100)

    assert controller.metadata_refreshes == []
    assert "avatar" not in page.cast_widgets[0].person


def test_following_detail_page_does_not_auto_refresh_when_only_crew_missing_avatars(qtbot) -> None:
    class CrewOnlyMissingAvatarController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.refreshed = False

        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            crew = [{"name": "刘海波", "job": "Director"}]
            if self.refreshed:
                crew[0]["avatar"] = "/liuhb.jpg"
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="低智商犯罪",
                    provider="tmdb",
                    provider_id="tv:272432:season:1",
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    overview="简介",
                    cast=[{"name": "王骁", "role": "Zhang Yi'ang", "avatar": "/wang.jpg"}],
                    crew=crew,
                ),
            )

        def refresh_metadata(self, following_id: int):
            self.metadata_refreshes.append(following_id)
            self.refreshed = True
            return self.load_detail(following_id, refresh_if_empty=False)

    controller = CrewOnlyMissingAvatarController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    qtbot.wait(100)

    assert controller.metadata_refreshes == []
    assert "avatar" not in page.cast_widgets[1].person


def test_following_detail_page_detaches_stale_person_cards_after_metadata_refresh(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)
    old_card = page.cast_widgets[0]

    refreshed_view = FollowingDetailView(
        record=FollowingRecord(id=1, title="凡人修仙传", provider="tmdb"),
        snapshot=FollowingDetailSnapshot(
            following_id=1,
            overview="刷新简介",
            cast=[{"name": "韩立", "role": "主角", "avatar": "/hanli.jpg"}],
        ),
    )

    page._handle_metadata_refresh_finished(1, refreshed_view, "")

    assert old_card.parent() is None
    assert old_card.isVisible() is False
    assert page.cast_widgets[0] is not old_card
    assert page.cast_widgets[0].person["avatar"] == "/hanli.jpg"
