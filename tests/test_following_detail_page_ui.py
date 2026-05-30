from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel

from atv_player.controllers.following_controller import FollowingDetailView
from atv_player.following_models import (
    FollowingAISummary,
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingEpisodeState,
    FollowingMetadataBundle,
    FollowingMetadataSourceSnapshot,
    FollowingPlaybackPlatformEntry,
    FollowingRatingEntry,
    FollowingRecord,
    FollowingSeason,
    FollowingSourceBinding,
)
from atv_player.models import AppConfig
from atv_player.ui.following_detail_page import (
    FollowingDetailPage,
    FollowingEpisodePreviewDialog,
    FollowingPersonCard,
    FollowingProgressDialog,
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
                overview="TMDB简介",
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
                metadata_bundle=FollowingMetadataBundle(
                    merged_snapshot=FollowingMetadataSourceSnapshot(
                        source_key="merged",
                        provider="merged",
                        provider_label="合并",
                        overview="TMDB简介",
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
                            {"label": "最近更新", "value": "2026-05-24"},
                            {"label": "更新时间", "value": "连载中, 每周日 11:00更新"},
                            {"label": "更新状态", "value": "连载中"},
                            {"label": "开播", "value": "2024年10月27日11:00"},
                            {"label": "播放", "value": "18.0亿"},
                            {"label": "追番", "value": "653.8万追番"},
                            {"label": "点赞", "value": "17.8万"},
                            {"label": "投币", "value": "647.5万"},
                            {"label": "收藏", "value": "145.3万"},
                            {"label": "回复", "value": "33.5万"},
                            {"label": "弹幕", "value": "348.9万"},
                            {"label": "分享", "value": "14.5万"},
                        ],
                        ratings=[
                            FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1"),
                            FollowingRatingEntry(provider="douban", label="豆瓣", value="7.9"),
                            FollowingRatingEntry(provider="bangumi", label="Bangumi", value="8.4"),
                        ],
                        playback_platforms=[
                            FollowingPlaybackPlatformEntry(
                                provider="iqiyi",
                                label="爱奇艺",
                                url="https://www.iqiyi.com/a_1.html",
                                latest_episode=128,
                                update_time_text="2026-05-25",
                                status_text="更新至第128集",
                            ),
                            FollowingPlaybackPlatformEntry(
                                provider="tencent",
                                label="腾讯",
                                url="https://v.qq.com/x/cover/mzc002006dzzunf/h4102lz1osw.html",
                            )
                        ],
                    ),
                    source_snapshots={
                        "merged": FollowingMetadataSourceSnapshot(
                            source_key="merged",
                            provider="merged",
                            provider_label="合并",
                            overview="TMDB简介",
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
                                {"label": "最近更新", "value": "2026-05-24"},
                                {"label": "更新时间", "value": "连载中, 每周日 11:00更新"},
                                {"label": "更新状态", "value": "连载中"},
                                {"label": "开播", "value": "2024年10月27日11:00"},
                                {"label": "播放", "value": "18.0亿"},
                                {"label": "追番", "value": "653.8万追番"},
                            ],
                            ratings=[
                                FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1"),
                                FollowingRatingEntry(provider="douban", label="豆瓣", value="7.9"),
                                FollowingRatingEntry(provider="bangumi", label="Bangumi", value="8.4"),
                            ],
                            playback_platforms=[
                                FollowingPlaybackPlatformEntry(
                                    provider="iqiyi",
                                    label="爱奇艺",
                                    url="https://www.iqiyi.com/a_1.html",
                                    latest_episode=128,
                                    update_time_text="2026-05-25",
                                    status_text="更新至第128集",
                                ),
                                FollowingPlaybackPlatformEntry(
                                    provider="tencent",
                                    label="腾讯",
                                    url="https://v.qq.com/x/cover/mzc002006dzzunf/h4102lz1osw.html",
                                )
                            ],
                        ),
                        "tmdb": FollowingMetadataSourceSnapshot(
                            source_key="tmdb",
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:272432:season:1",
                            confidence=1.0,
                            overview="TMDB简介",
                            metadata_fields=[
                                {"label": "类型", "value": "喜剧 / 悬疑 / 犯罪"},
                                {"label": "TMDB ID", "value": "272432"},
                            ],
                            ratings=[FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.1")],
                        ),
                        "douban": FollowingMetadataSourceSnapshot(
                            source_key="douban",
                            provider="douban",
                            provider_label="豆瓣",
                            provider_id="35517044",
                            confidence=0.92,
                            overview="豆瓣简介",
                            metadata_fields=[
                                {"label": "导演", "value": "刘海波"},
                                {"label": "豆瓣ID", "value": "35517044"},
                            ],
                            ratings=[FollowingRatingEntry(provider="douban", label="豆瓣", value="7.9")],
                        ),
                        "bangumi": FollowingMetadataSourceSnapshot(
                            source_key="bangumi",
                            provider="bangumi",
                            provider_label="Bangumi",
                            provider_id="subject:1",
                            confidence=0.94,
                            overview="Bangumi简介",
                            metadata_fields=[
                                {"label": "别名", "value": "凡人修仙传 动画版"},
                                {"label": "Bangumi ID", "value": "1"},
                            ],
                            ratings=[FollowingRatingEntry(provider="bangumi", label="Bangumi", value="8.4")],
                        ),
                        "iqiyi": FollowingMetadataSourceSnapshot(
                            source_key="iqiyi",
                            provider="iqiyi",
                            provider_label="爱奇艺",
                            provider_id="iqiyi:album:1",
                            confidence=0.98,
                            overview="爱奇艺简介",
                            metadata_fields=[
                                {"label": "播放链接", "value": "https://www.iqiyi.com/a_1.html"},
                                {"label": "更新时间", "value": "2026-05-25"},
                                {"label": "更新状态", "value": "更新至第128集"},
                            ],
                            playback_platforms=[
                                FollowingPlaybackPlatformEntry(
                                    provider="iqiyi",
                                    label="爱奇艺",
                                    url="https://www.iqiyi.com/a_1.html",
                                    latest_episode=128,
                                    update_time_text="2026-05-25",
                                    status_text="更新至第128集",
                                )
                            ],
                        ),
                    },
                    available_source_keys=["merged", "tmdb", "douban", "bangumi", "iqiyi"],
                    default_source_key="merged",
                ),
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
        allow_regression: bool = False,
    ) -> None:
        del position_seconds
        self.progress_updates.append((following_id, current_season_number, current_episode))
        self.allow_regression = allow_regression


def test_following_detail_page_shows_rating_strip_source_switcher_and_playback_platforms(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.rating_strip.text() == "TMDB 8.1  ·  豆瓣 7.9  ·  Bangumi 8.4"
    assert "评分" not in page.meta_label.text()
    assert "bangumi" not in page.meta_label.text()
    assert [button.text() for button in page.metadata_source_buttons] == ["媒体信息", "TMDB", "豆瓣", "Bangumi", "爱奇艺"]
    assert "类型: 喜剧 / 悬疑 / 犯罪" in page.overview_label.text()
    assert "TMDB ID:" in page.overview_label.text()
    assert 'href="https://www.themoviedb.org/tv/272432"' in page.overview_label.text()
    assert "最近更新:" not in page.overview_label.text()
    assert "更新时间:" not in page.overview_label.text()
    assert "更新状态:" not in page.overview_label.text()
    assert "开播:" not in page.overview_label.text()
    assert "播放:" not in page.overview_label.text()
    assert "追番:" not in page.overview_label.text()
    assert page.playback_platform_layout.count() == 1
    assert len(page.playback_platform_widgets) == 1
    assert page.playback_platform_buttons == []
    platform_html = page.playback_platform_widgets[0].text()
    assert 'href="https://www.iqiyi.com/a_1.html"' in platform_html
    assert 'href="https://v.qq.com/x/cover/mzc002006dzzunf/h4102lz1osw.html"' in platform_html
    assert "爱奇艺" in platform_html
    assert "腾讯" in platform_html
    assert "更新至第128集" in platform_html
    assert platform_html.index("爱奇艺") < platform_html.index("腾讯")


def test_following_detail_page_renders_ai_summary_panel(qtbot) -> None:
    class AISummaryController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(id=following_id, title="黑镜"),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    ai_summary=FollowingAISummary(
                        summary="AI 摘要",
                        highlights=["看点一", "看点二"],
                        next_hint="明晚更新",
                    ),
                ),
            )

    page = FollowingDetailPage(AISummaryController())
    qtbot.addWidget(page)
    page.show()

    page.load_record(1)

    assert page.ai_summary_panel.isVisible()
    assert "AI 摘要" in page.ai_summary_label.text()
    assert "看点一" in page.ai_summary_label.text()
    assert "明晚更新" in page.ai_summary_label.text()


def test_following_detail_page_skips_ai_summary_on_initial_open(qtbot) -> None:
    class RecordingController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.include_ai_summary_values: list[object] = []

        def load_detail(
            self,
            following_id: int,
            *,
            refresh_if_empty: bool = True,
            include_ai_summary: bool = True,
        ):
            self.include_ai_summary_values.append(include_ai_summary)
            return super().load_detail(
                following_id,
                refresh_if_empty=refresh_if_empty,
            )

    controller = RecordingController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    assert controller.include_ai_summary_values == [False]


def test_following_detail_page_switches_between_merged_and_provider_raw_views(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)
    page.metadata_source_buttons[2].click()

    assert "豆瓣简介" in page.overview_label.text()
    assert "TMDB简介" not in page.overview_label.text()

    page.metadata_source_buttons[4].click()

    assert "播放链接:" in page.overview_label.text()
    assert 'href="https://www.iqiyi.com/a_1.html"' in page.overview_label.text()
    assert "更新时间: 2026-05-25" in page.overview_label.text()
    assert "更新状态: 更新至第128集" in page.overview_label.text()

    page.metadata_source_buttons[0].click()

    assert "TMDB简介" in page.overview_label.text()
    assert "爱奇艺" in page.playback_platform_widgets[0].text()


def test_following_detail_page_opens_inline_playback_platform_link(qtbot, monkeypatch) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    opened: list[str] = []

    page.load_record(1)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    page.playback_platform_widgets[0].linkActivated.emit("https://www.iqiyi.com/a_1.html")

    assert opened == ["https://www.iqiyi.com/a_1.html"]


def test_following_detail_page_links_metadata_ids_like_player_detail(qtbot, monkeypatch) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    opened: list[str] = []

    page.load_record(1)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)

    html = page.overview_label.text()
    assert 'href="https://movie.douban.com/subject/35517044/"' in html
    assert 'href="https://www.imdb.com/title/tt32592348"' in html
    assert 'href="https://www.themoviedb.org/tv/272432"' in html

    page.overview_label.linkActivated.emit("https://www.themoviedb.org/tv/272432")

    assert opened == ["https://www.themoviedb.org/tv/272432"]


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
    assert "豆瓣ID:" in page.overview_label.text()
    assert "IMDb ID:" in page.overview_label.text()
    assert "TMDB ID:" in page.overview_label.text()
    assert 'href="https://movie.douban.com/subject/35517044/"' in page.overview_label.text()
    assert 'href="https://www.imdb.com/title/tt32592348"' in page.overview_label.text()
    assert 'href="https://www.themoviedb.org/tv/272432"' in page.overview_label.text()
    assert "更新时间:" not in page.overview_label.text()
    assert "更新状态:" not in page.overview_label.text()
    assert "简介:<br>TMDB简介" in page.overview_label.text()
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


def test_following_detail_page_emits_continue_play_and_keeps_search_play(qtbot) -> None:
    class BoundSourceController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True, include_ai_summary: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.source_bindings = [
                FollowingSourceBinding(source_kind="telegram", source_key="", vod_id="tg-vod-1")
            ]
            return view

    controller = BoundSourceController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    continued: list[int] = []
    searched: list[int] = []
    page.continue_play_requested.connect(continued.append)
    page.search_play_requested.connect(searched.append)

    page.load_record(1)
    page.continue_play_button.click()
    page.search_play_button.click()

    assert page.continue_play_button.isEnabled() is True
    assert continued == [1]
    assert searched == [1]


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


def test_following_detail_page_marks_stale_current_season_aired_episode_as_released(qtbot) -> None:
    class LongRunningSeriesController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="海贼王",
                    provider="tmdb",
                    provider_id="tv:1:season:14",
                    season_number=14,
                    current_season_number=14,
                    current_episode=580,
                    latest_episode=580,
                    total_episodes=1129,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(season_number=14, title="第十四季", episode_count=100),
                        FollowingSeason(season_number=21, title="第二十一季", episode_count=200),
                    ],
                    episodes=[
                        FollowingEpisode(
                            episode_number=581,
                            season_number=14,
                            title="一伙惊愕！令人震惊的独头武士登场",
                            air_date="2013-07-14",
                        ),
                        FollowingEpisode(
                            episode_number=1129,
                            season_number=21,
                            title="最新集",
                            air_date="2026-05-25",
                        ),
                    ],
                ),
            )

    page = FollowingDetailPage(LongRunningSeriesController())
    qtbot.addWidget(page)

    page.load_record(1)

    episode = page.current_view.snapshot.episodes[0]
    assert page.episode_browser.status_text_for_episode(episode) == "已更新"


def test_following_detail_page_progress_dialog_uses_snapshot_latest_season(qtbot, monkeypatch) -> None:
    class LongRunningSeriesController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="海贼王",
                    provider="tmdb",
                    provider_id="tv:1:season:1",
                    season_number=1,
                    current_season_number=15,
                    current_episode=62,
                    latest_episode=1163,
                    total_episodes=1163,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(season_number=1, title="第一季", episode_count=61),
                        FollowingSeason(season_number=15, title="第十五季", episode_count=100),
                        FollowingSeason(season_number=23, title="第二十三季", episode_count=100),
                    ],
                    episodes=[
                        FollowingEpisode(episode_number=62, season_number=15, title="S15E62"),
                    ],
                ),
            )

    captured: dict[str, object] = {}

    def fake_exec(self_dialog):
        captured["latest_season_number"] = self_dialog._latest_season_number
        captured["latest_episode"] = self_dialog._latest_episode
        captured["season_maximum"] = self_dialog.season_spin.maximum()
        captured["set_latest_text"] = self_dialog.content_layout().itemAt(2).widget().text()
        return 0

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingProgressDialog.exec",
        fake_exec,
    )

    page = FollowingDetailPage(LongRunningSeriesController())
    qtbot.addWidget(page)
    page.load_record(1)

    page.set_progress_button.click()

    assert captured == {
        "latest_season_number": 15,
        "latest_episode": 100,
        "season_maximum": 23,
        "set_latest_text": "设为最新 (S15E100)",
    }


def test_following_progress_dialog_normalizes_global_latest_to_loaded_season_episode(
    qtbot,
) -> None:
    dialog = FollowingProgressDialog(
        current_season_number=0,
        current_episode=0,
        latest_season_number=2,
        latest_episode=112,
        total_episodes=24,
        seasons=[FollowingSeason(season_number=2, title="第二季", episode_count=24)],
        episodes=[
            FollowingEpisode(episode_number=index, season_number=2)
            for index in range(1, 25)
        ],
    )
    qtbot.addWidget(dialog)

    label_text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert "最新 S2E24 / 总 24" in label_text
    assert dialog._latest_episode == 24
    dialog._set_to_latest()
    assert dialog.episode_spin.value() == 24


def test_following_progress_dialog_uses_selected_completed_season_latest(qtbot) -> None:
    dialog = FollowingProgressDialog(
        current_season_number=1,
        current_episode=0,
        latest_season_number=2,
        latest_episode=20,
        total_episodes=24,
        seasons=[
            FollowingSeason(season_number=1, title="第一季", episode_count=24),
            FollowingSeason(season_number=2, title="第二季", episode_count=20),
        ],
        episodes=[
            FollowingEpisode(episode_number=index, season_number=1)
            for index in range(1, 25)
        ],
        selected_season_number=1,
    )
    qtbot.addWidget(dialog)

    label_text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert dialog.season_spin.text() == "1"
    assert "最新 S1E24 / 总 24" in label_text
    dialog._set_to_latest()
    assert dialog.season_spin.value() == 1
    assert dialog.episode_spin.value() == 24


def test_following_progress_dialog_can_mark_global_latest_when_future_season_selected(qtbot) -> None:
    dialog = FollowingProgressDialog(
        current_season_number=0,
        current_episode=0,
        latest_season_number=1,
        latest_episode=26,
        total_episodes=26,
        seasons=[
            FollowingSeason(season_number=1, title="第一季", episode_count=26),
            FollowingSeason(season_number=2, title="第二季", episode_count=27),
        ],
        episodes=[
            FollowingEpisode(episode_number=index, season_number=1)
            for index in range(1, 27)
        ],
        selected_season_number=2,
    )
    qtbot.addWidget(dialog)

    assert dialog.season_spin.value() == 2
    assert dialog.mark_latest_button.text() == "设为最新 (S1E26)"

    dialog._set_to_latest()

    assert dialog.season_spin.value() == 1
    assert dialog.episode_spin.value() == 26


def test_following_detail_page_progress_dialog_keeps_record_latest_season_when_selected_season_has_same_episode_number(
    qtbot,
    monkeypatch,
) -> None:
    class CurrentSeasonOnlyController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="成何体统 第二季",
                    provider="tmdb",
                    provider_id="tv:256783",
                    season_number=2,
                    current_season_number=0,
                    current_episode=0,
                    latest_episode=20,
                    total_episodes=24,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(season_number=1, title="第一季", episode_count=24),
                        FollowingSeason(season_number=2, title="第二季", episode_count=20),
                    ],
                    episodes=[
                        FollowingEpisode(episode_number=index, season_number=1)
                        for index in range(1, 25)
                    ],
                ),
            )

    captured: dict[str, object] = {}

    def fake_exec(self_dialog):
        captured["latest_season_number"] = self_dialog._latest_season_number
        captured["latest_episode"] = self_dialog._latest_episode
        captured["info_text"] = self_dialog.info_label.text()
        captured["set_latest_text"] = self_dialog.mark_latest_button.text()
        return 0

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingProgressDialog.exec",
        fake_exec,
    )

    page = FollowingDetailPage(CurrentSeasonOnlyController())
    qtbot.addWidget(page)
    page.load_record(1)

    page.set_progress_button.click()

    assert captured == {
        "latest_season_number": 1,
        "latest_episode": 24,
        "info_text": "最新 S1E24 / 总 24",
        "set_latest_text": "设为最新 (S1E24)",
    }


def test_following_progress_dialog_normalizes_global_current_to_unwatched(
    qtbot,
) -> None:
    dialog = FollowingProgressDialog(
        current_season_number=2,
        current_episode=112,
        latest_season_number=2,
        latest_episode=24,
        total_episodes=24,
        seasons=[FollowingSeason(season_number=2, title="第二季", episode_count=24)],
        episodes=[
            FollowingEpisode(episode_number=index, season_number=2)
            for index in range(1, 25)
        ],
    )
    qtbot.addWidget(dialog)

    assert dialog.episode_spin.value() == 0
    dialog.episode_spin.setValue(12)
    dialog._accept()

    assert dialog.accepted_season_number == 2
    assert dialog.accepted_episode == 12


def test_following_detail_page_manual_progress_save_allows_regression(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    page.load_record(1)

    page._save_following_progress(
        season_number=1,
        episode_number=12,
        message="已保存追更进度",
    )

    assert controller.progress_updates[-1] == (1, 1, 12)
    assert controller.allow_regression is True


def test_following_detail_page_normalizes_global_current_episode_in_meta(qtbot) -> None:
    class SeasonLocalController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="成何体统 第二季",
                    provider="tmdb",
                    provider_id="tv:256783:season:2",
                    season_number=2,
                    current_season_number=2,
                    current_episode=112,
                    latest_episode=112,
                    total_episodes=24,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(
                            season_number=2,
                            title="第二季",
                            episode_count=24,
                        ),
                    ],
                    episodes=[
                        FollowingEpisode(episode_number=index, season_number=2)
                        for index in range(1, 25)
                    ],
                ),
            )

    page = FollowingDetailPage(SeasonLocalController())
    qtbot.addWidget(page)
    page.load_record(1)

    assert "S2E112" not in page.meta_label.text()
    assert "看到 S2E24" not in page.meta_label.text()
    assert "最新 S2E24" in page.meta_label.text()


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


def test_following_detail_page_keeps_specials_selected_after_loading(qtbot) -> None:
    class SpecialsController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.season_number = 1
            view.snapshot.seasons = [
                FollowingSeason(season_number=0, title="特别篇", episode_count=1),
                FollowingSeason(season_number=1, title="第一季", episode_count=1),
            ]
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
            ]
            return view

        def load_detail_season(self, following_id: int, *, season_number: int):
            self.loaded_seasons.append(season_number)
            view = self.load_detail(following_id, refresh_if_empty=False)
            if season_number == 0:
                view.snapshot.episodes = [
                    FollowingEpisode(
                        episode_number=1,
                        season_number=0,
                        title="Special 1",
                        is_special=True,
                    )
                ]
            return view

    controller = SpecialsController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    assert page.episode_browser.current_season_number() == 1

    page.episode_browser.season_list.setCurrentIndex(season_model.index(0, 0))

    qtbot.waitUntil(lambda: controller.loaded_seasons == [0], timeout=1000)
    qtbot.waitUntil(
        lambda: page.episode_browser.episode_list.model().rowCount() == 1,
        timeout=1000,
    )

    episode_model = page.episode_browser.episode_list.model()
    assert page.episode_browser.current_season_number() == 0
    assert "Special 1" in episode_model.data(
        episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole
    )


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


def test_following_detail_page_uses_browser_owned_virtual_card_grid(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    assert page.episode_browser.episode_list.isHidden() is False
    assert page.episode_browser.episode_scroll.isHidden() is True
    assert page.episode_browser.episode_cards == []


def test_following_detail_page_clicking_virtual_card_opens_preview_dialog(
    qtbot, monkeypatch
) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.resize(1280, 900)
    page.show()
    page.load_record(1)
    opened: list[int] = []

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.episode.episode_number) or 1,
    )

    model = page.episode_browser.episode_list.model()
    index = model.index(0, 0)
    rect = page.episode_browser.episode_list.visualRect(index)
    qtbot.mouseClick(
        page.episode_browser.episode_list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )

    assert opened == [128]


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
    assert dialog.mark_watched_button.isHidden() is False


def test_following_episode_preview_dialog_hides_mark_watched_button_for_non_released_status(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=4,
            title="第四集",
            air_date="2026-05-20",
            runtime=24,
        ),
        status_text="未更新",
        can_mark_watched=False,
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-20 · 24m · 未更新"
    assert dialog.mark_watched_button.isHidden() is True


def test_following_detail_page_preview_dialog_shows_mark_watched_only_for_released_episode(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)
    episode = page.current_view.snapshot.episodes[0]

    assert page.episode_browser.status_for_episode(episode) == FollowingEpisodeState.RELEASED

    released_dialog = FollowingEpisodePreviewDialog(
        episode,
        status_text=page.episode_browser.status_text_for_episode(episode),
        can_mark_watched=page.episode_browser.status_for_episode(episode) == FollowingEpisodeState.RELEASED,
    )
    qtbot.addWidget(released_dialog)
    assert released_dialog.mark_watched_button.isHidden() is False

    pending_dialog = FollowingEpisodePreviewDialog(
        episode,
        status_text="未更新",
        can_mark_watched=FollowingEpisodeState.PENDING == FollowingEpisodeState.RELEASED,
    )
    qtbot.addWidget(pending_dialog)
    assert pending_dialog.mark_watched_button.isHidden() is True


def test_following_detail_page_passes_non_released_episodes_as_not_markable(qtbot, monkeypatch) -> None:
    class PendingEpisodeController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.current_episode = 127
            view.record.latest_episode = 127
            view.snapshot.episodes = [
                FollowingEpisode(
                    episode_number=128,
                    title="下一集",
                    overview="未更新分集",
                )
            ]
            return view

    captured: list[bool] = []

    def fake_init(self_dialog, episode, *, status_text="", can_mark_watched=True, parent=None):
        del episode, status_text, parent
        captured.append(can_mark_watched)
        self_dialog.mark_watched_requested = False

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.__init__",
        fake_init,
    )
    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        lambda self_dialog: 0,
    )

    page = FollowingDetailPage(PendingEpisodeController())
    qtbot.addWidget(page)
    page.load_record(1)

    model = page.episode_browser.episode_list.model()
    page.episode_browser._handle_episode_activated(model.index(0, 0))

    assert captured == [False]


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


def test_following_detail_page_does_not_mark_cross_season_ongoing_series_completed(
    qtbot,
) -> None:
    class OngoingController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="航海王",
                    provider="tmdb",
                    provider_id="tv:37854",
                    season_number=1,
                    current_season_number=15,
                    current_episode=581,
                    latest_episode=1163,
                    total_episodes=1163,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[FollowingSeason(season_number=23, title="第23季")],
                    episodes=[
                        FollowingEpisode(
                            season_number=23,
                            episode_number=1178,
                            air_date="2026-09-06",
                        )
                    ],
                ),
            )

    page = FollowingDetailPage(OngoingController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "看到 S15E581" in page.meta_label.text()
    assert "最新 S23E1163" in page.meta_label.text()
    assert "总 1163" not in page.meta_label.text()
    assert "已看完" not in page.meta_label.text()
    assert "已完结" not in page.meta_label.text()


def test_following_detail_page_counts_unwatched_local_episode_updates_across_seasons(
    qtbot,
) -> None:
    class VarietyController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="五十公里桃花坞",
                    media_kind="variety",
                    provider="tmdb",
                    provider_id="tv:12345",
                    season_number=1,
                    current_season_number=0,
                    current_episode=0,
                    latest_episode=10,
                    has_update=True,
                    new_episode_count=10,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(season_number=1, episode_count=60),
                        FollowingSeason(season_number=2, episode_count=60),
                        FollowingSeason(season_number=3, episode_count=60),
                        FollowingSeason(season_number=4, episode_count=60),
                        FollowingSeason(season_number=5, episode_count=60),
                        FollowingSeason(season_number=6, episode_count=10),
                    ],
                    episodes=[FollowingEpisode(season_number=6, episode_number=10)],
                ),
            )

    page = FollowingDetailPage(VarietyController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "最新 S6E10" in page.meta_label.text()
    assert "最新 S1E10" not in page.meta_label.text()
    assert "有 310 集更新" in page.meta_label.text()


def test_following_detail_page_uses_series_total_for_unwatched_update_count(
    qtbot,
) -> None:
    class MythbustersController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="流言终结者",
                    media_kind="documentary",
                    provider="tmdb",
                    provider_id="tv:1428",
                    season_number=1,
                    current_season_number=0,
                    current_episode=0,
                    latest_episode=8,
                    total_episodes=272,
                    has_update=True,
                    new_episode_count=11,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[FollowingSeason(season_number=16, episode_count=11)],
                    episodes=[FollowingEpisode(season_number=16, episode_number=8)],
                ),
            )

    page = FollowingDetailPage(MythbustersController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "最新 S16E8 / 总 272" in page.meta_label.text()
    assert "有 272 集更新" in page.meta_label.text()


def test_following_detail_page_infers_latest_season_for_unwatched_unseasoned_episodes(
    qtbot,
) -> None:
    class MythbustersController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            del refresh_if_empty
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="流言终结者",
                    media_kind="documentary",
                    provider="tmdb",
                    provider_id="tv:1428",
                    season_number=1,
                    current_season_number=0,
                    current_episode=0,
                    latest_episode=8,
                    total_episodes=272,
                    has_update=True,
                    new_episode_count=272,
                ),
                snapshot=FollowingDetailSnapshot(
                    following_id=following_id,
                    seasons=[
                        FollowingSeason(season_number=1, episode_count=11),
                        FollowingSeason(season_number=16, episode_count=11),
                    ],
                    episodes=[
                        FollowingEpisode(episode_number=index)
                        for index in range(1, 12)
                    ],
                ),
            )

    page = FollowingDetailPage(MythbustersController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert "最新 S16E8 / 总 272" in page.meta_label.text()
    assert "最新 S1E11" not in page.meta_label.text()
    assert "有 272 集更新" in page.meta_label.text()


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
