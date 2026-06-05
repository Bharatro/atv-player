from __future__ import annotations

from PySide6.QtCore import Qt

from atv_player.controllers.media_detail_controller import MediaDetailEpisode
from atv_player.controllers.media_detail_controller import MediaDetailIdentity
from atv_player.controllers.media_detail_controller import MediaDetailPerson
from atv_player.controllers.media_detail_controller import MediaDetailRecommendation
from atv_player.controllers.media_detail_controller import MediaDetailView
from atv_player.ui.media_detail_page import MediaDetailPage


def _sample_view() -> MediaDetailView:
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
            MediaDetailPerson(name="Emilia Clarke", role="Daenerys Targaryen"),
            MediaDetailPerson(name="David Benioff", role="Creator", kind="crew"),
        ],
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
    assert "2011" in page.meta_label.text()
    assert "剧情 / 科幻奇幻" in page.meta_label.text()
    assert "8.4" in page.rating_label.text()
    assert "九大家族" in page.overview_label.text()
    assert page.episode_buttons[0].text() == "S1E1 凛冬将至\n2011-04-17"
    assert page.person_labels[0].text() == "Emilia Clarke\nDaenerys Targaryen"
    assert page.person_labels[1].text() == "David Benioff\nCreator"
    assert page.related_buttons[0].text() == "绿箭侠\n2012 · 6.8"
    assert page.search_play_button.text() == "搜索播放"
    assert page.add_following_button.text() == "加入追更"
    assert page.refresh_metadata_button.text() == "更新元数据"


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
        qtbot.mouseClick(page.related_buttons[0], Qt.MouseButton.LeftButton)

    assert related_signal.args == [MediaDetailIdentity(media_type="tv", tmdb_id="1412", title="绿箭侠")]
