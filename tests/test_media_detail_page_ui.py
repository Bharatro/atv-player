from __future__ import annotations

from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtCore import Qt

from atv_player.following_models import FollowingMetadataBundle
from atv_player.following_models import FollowingMetadataSourceSnapshot
from atv_player.following_models import FollowingRatingEntry
from atv_player.controllers.media_detail_controller import MediaDetailEpisode
from atv_player.controllers.media_detail_controller import MediaDetailIdentity
from atv_player.controllers.media_detail_controller import MediaDetailPerson
from atv_player.controllers.media_detail_controller import MediaDetailRecommendation
from atv_player.controllers.media_detail_controller import MediaDetailView
from atv_player.models import AppConfig
from atv_player.ui.detail_scaffold import MediaDetailScaffold
from atv_player.ui.following_detail_page import _carousel_image_qss
from atv_player.ui.following_detail_page import FollowingPersonCard
from atv_player.ui.following_detail_page import FollowingRelatedRecommendationCard
from atv_player.ui.following_episode_browser import FollowingEpisodeBrowser
from atv_player.ui.following_episode_browser import EPISODE_ROLE
from atv_player.ui.media_detail_page import MediaDetailPage


def _sample_view() -> MediaDetailView:
    tmdb_source = FollowingMetadataSourceSnapshot(
        source_key="tmdb",
        provider="tmdb",
        provider_label="TMDB",
        provider_id="tv:1399:season:1",
        overview="TMDB 简介。",
        metadata_fields=[
            {"label": "类型", "value": "剧情 / 科幻奇幻"},
            {"label": "首播", "value": "2011-04-17"},
            {"label": "豆瓣ID", "value": "3016187"},
            {"label": "IMDb ID", "value": "tt0944947"},
            {"label": "TMDB ID", "value": "1399"},
        ],
        ratings=[FollowingRatingEntry(provider="tmdb", label="TMDB", value="8.4")],
    )
    return MediaDetailView(
        identity=MediaDetailIdentity(media_type="tv", tmdb_id="1399", title="权力的游戏"),
        title="权力的游戏",
        media_type="tv",
        year="2011",
        release_date="2011-04-17",
        overview="九大家族争夺铁王座。",
        poster_url="",
        backdrop_url="",
        rating="8.4",
        genres=["剧情", "科幻奇幻"],
        episodes=[
            MediaDetailEpisode(
                season_number=1,
                episode_number=1,
                title="凛冬将至",
                air_date="2011-04-17",
            )
        ],
        people=[
            MediaDetailPerson(
                name="Emilia Clarke",
                role="Daenerys Targaryen",
                url="https://www.themoviedb.org/person/1223786",
            ),
            MediaDetailPerson(name="David Benioff", role="Creator", kind="crew"),
        ],
        metadata_bundle=FollowingMetadataBundle(
            merged_snapshot=tmdb_source,
            source_snapshots={"merged": tmdb_source, "tmdb": tmdb_source},
            available_source_keys=["merged", "tmdb"],
            default_source_key="merged",
        ),
        related=[
            MediaDetailRecommendation(
                identity=MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠"),
                year="2012",
                rating="6.8",
            )
        ],
    )


def test_media_detail_page_renders_sections_and_actions(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)

    page.load_view(_sample_view())

    assert page.title_label.text() == "权力的游戏"
    assert isinstance(page.detail_scaffold, MediaDetailScaffold)
    assert "2011" in page.meta_label.text()
    assert "剧情 / 科幻奇幻" in page.meta_label.text()
    assert "8.4" in page.rating_strip.text()
    assert "类型:" in page.overview_label.text()
    assert "TMDB 简介" in page.overview_label.text()
    assert page.metadata_panel.objectName() == "followingDetailMetadataPanel"
    assert page.poster_carousel_panel.objectName() == "followingDetailPosterCarousel"
    assert page.top_section.objectName() == "followingDetailTopSection"
    assert page.episodes_section.objectName() == "followingDetailEpisodesSection"
    assert page.related_recommendation_section.objectName() == "followingRelatedRecommendationSection"
    assert page.cast_section.objectName() == "followingDetailCastSection"
    assert isinstance(page.episode_browser, FollowingEpisodeBrowser)
    assert [button.text() for button in page.metadata_source_buttons] == ["媒体信息", "TMDB"]
    episode_index = page.episode_browser.episode_model.index(0, 0)
    assert episode_index.data(EPISODE_ROLE).title == "凛冬将至"
    assert isinstance(page.person_cards[0], FollowingPersonCard)
    assert page.person_cards[0].name_label.text() == "Emilia Clarke"
    assert page.person_cards[0].role_label.text() == "Daenerys Targaryen"
    assert isinstance(page.related_cards[0], FollowingRelatedRecommendationCard)
    assert page.related_cards[0].title_label.text() == "绿箭侠"
    assert page.search_play_button.text() == "搜索播放"
    assert page.add_following_button.text() == "加入追更"
    assert page.refresh_metadata_button.text() == "更新元数据"
    assert not hasattr(page, "continue_play_button")
    assert not hasattr(page, "manual_check_button")
    assert not hasattr(page, "set_progress_button")
    assert not hasattr(page, "unfollow_button")


def test_media_detail_page_uses_configured_initial_grid_columns(qtbot) -> None:
    page = MediaDetailPage(config=AppConfig(following_episode_grid_columns=3))
    qtbot.addWidget(page)

    assert page.episode_browser.grid_columns() == 3


def test_media_detail_page_persists_grid_columns_after_cycle_click(qtbot) -> None:
    config = AppConfig(following_episode_grid_columns=1)
    saved: list[int] = []
    page = MediaDetailPage(config=config, save_config=lambda: saved.append(config.following_episode_grid_columns))
    qtbot.addWidget(page)

    qtbot.mouseClick(page.episode_browser.grid_cycle_button, Qt.MouseButton.LeftButton)

    assert page.episode_browser.grid_columns() == 2
    assert config.following_episode_grid_columns == 2
    assert saved == [2]


def test_media_detail_page_uses_following_metadata_source_tabs(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(_sample_view())

    qtbot.mouseClick(page.metadata_source_buttons[1], Qt.MouseButton.LeftButton)

    assert page.metadata_source_buttons[1].isChecked()
    assert "TMDB ID:" in page.overview_label.text()
    assert "1399" in page.overview_label.text()


def test_media_detail_page_metadata_external_ids_are_links(qtbot, monkeypatch) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)

    page.load_view(_sample_view())

    text = page.overview_label.text()
    assert 'href="https://movie.douban.com/subject/3016187/"' in text
    assert 'href="https://www.imdb.com/title/tt0944947"' in text
    assert 'href="https://www.themoviedb.org/tv/1399"' in text

    page.overview_label.linkActivated.emit("https://www.themoviedb.org/tv/1399")

    assert opened == ["https://www.themoviedb.org/tv/1399"]


def test_media_detail_page_emits_action_signals(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    view = _sample_view()
    page.load_view(view)

    with qtbot.waitSignal(page.search_play_requested) as search_signal:
        qtbot.mouseClick(page.search_play_button, Qt.MouseButton.LeftButton)
    assert search_signal.args == [view]

    with qtbot.waitSignal(page.add_following_requested) as add_signal:
        qtbot.mouseClick(page.add_following_button, Qt.MouseButton.LeftButton)
    assert add_signal.args == [view]

    with qtbot.waitSignal(page.refresh_metadata_requested) as refresh_signal:
        qtbot.mouseClick(page.refresh_metadata_button, Qt.MouseButton.LeftButton)
    assert refresh_signal.args == [view]


def test_media_detail_page_related_click_emits_identity(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(_sample_view())

    with qtbot.waitSignal(page.related_open_requested) as related_signal:
        qtbot.mouseClick(page.related_cards[0], Qt.MouseButton.LeftButton)

    assert related_signal.args == [MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠")]


def test_media_detail_page_person_card_opens_tmdb_person_url(qtbot, monkeypatch) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    opened: list[str] = []
    page.load_view(_sample_view())
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)

    qtbot.mouseClick(page.person_cards[0], Qt.MouseButton.LeftButton)

    assert opened == ["https://www.themoviedb.org/person/1223786"]


def test_media_detail_page_related_context_menu_searches_resource(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(_sample_view())

    with qtbot.waitSignal(page.search_play_requested) as signal:
        page._handle_related_recommendation_menu_action(_sample_view().related[0], "search")

    view = signal.args[0]
    assert view.identity == MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠")
    assert view.title == "绿箭侠"


def test_media_detail_page_related_context_menu_adds_following(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(_sample_view())

    with qtbot.waitSignal(page.add_following_requested) as signal:
        page._handle_related_recommendation_menu_action(_sample_view().related[0], "follow")

    view = signal.args[0]
    assert view.identity == MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠")
    assert view.year == "2012"


def test_media_detail_page_loads_detail_images_from_cache_pipeline(qtbot, monkeypatch) -> None:
    import atv_player.ui.media_detail_page as media_detail_page_module

    loaded_sources: list[str] = []

    def fake_local_poster_image(source, _target_size):
        loaded_sources.append(str(source))
        return QImage(16, 16, QImage.Format.Format_RGB32)

    monkeypatch.setattr(media_detail_page_module, "load_local_poster_image", fake_local_poster_image)
    monkeypatch.setattr(media_detail_page_module, "load_remote_poster_image", lambda *_args, **_kwargs: None)

    view = _sample_view()
    view.poster_url = "poster-source"
    view.backdrop_url = "backdrop-source"
    view.people[0].profile_url = "avatar-source"
    view.related[0].poster_url = "related-source"
    page = MediaDetailPage()
    qtbot.addWidget(page)

    page.load_view(view)

    qtbot.waitUntil(lambda: page.poster_carousel_label.pixmap() is not None, timeout=1000)
    qtbot.waitUntil(lambda: page.person_cards[0].avatar_label.pixmap() is not None, timeout=1000)
    qtbot.waitUntil(lambda: page.related_cards[0].poster_label.pixmap() is not None, timeout=1000)
    assert loaded_sources == ["backdrop-source", "avatar-source", "related-source"]


def test_media_detail_page_requests_selected_season_when_switching_season(qtbot) -> None:
    view = _sample_view()
    view.seasons = [
        {"season_number": 1, "name": "第 1 季", "episode_count": 1},
        {"season_number": 2, "name": "第 2 季", "episode_count": 1},
    ]
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(view)

    with qtbot.waitSignal(page.season_requested) as signal:
        page.episode_browser.season_list.setCurrentIndex(
            page.episode_browser.season_model.index(1, 0)
        )

    assert signal.args == [view, 2]


def test_media_detail_page_updates_selected_season_episodes(qtbot) -> None:
    view = _sample_view()
    view.seasons = [
        {"season_number": 1, "name": "第 1 季", "episode_count": 1},
        {"season_number": 2, "name": "第 2 季", "episode_count": 1},
    ]
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(view)

    updated = _sample_view()
    updated.seasons = list(view.seasons)
    updated.episodes = [
        MediaDetailEpisode(season_number=2, episode_number=1, title="北境之王")
    ]

    page.load_season_view(updated, season_number=2)

    assert page.episode_browser.current_season_number() == 2
    assert page.episode_browser.episode_model.rowCount() == 1
    assert page.episode_browser.episode_model.index(0, 0).data(EPISODE_ROLE).title == "北境之王"


def test_media_detail_page_opens_episode_preview_on_episode_click(qtbot, monkeypatch) -> None:
    import atv_player.ui.media_detail_page as media_detail_page_module

    opened: list[tuple[str, bool]] = []

    class FakeEpisodePreviewDialog:
        def __init__(self, episode, *, status_text="", can_mark_watched=True, parent=None):
            del status_text, parent
            opened.append((episode.title, can_mark_watched))

        def exec(self):
            return 0

    monkeypatch.setattr(
        media_detail_page_module,
        "FollowingEpisodePreviewDialog",
        FakeEpisodePreviewDialog,
    )
    page = MediaDetailPage()
    qtbot.addWidget(page)
    page.load_view(_sample_view())

    page.episode_browser._handle_episode_activated(page.episode_browser.episode_model.index(0, 0))

    assert opened == [("凛冬将至", False)]


def test_media_detail_page_uses_following_carousel_style(qtbot) -> None:
    page = MediaDetailPage()
    qtbot.addWidget(page)

    assert page.poster_carousel_label.styleSheet() == _carousel_image_qss()
