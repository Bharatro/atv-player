from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from atv_player.following_models import FollowingEpisode, FollowingSeason
from atv_player.ui.following_episode_browser import (
    EpisodeDisplayMode,
    EpisodeListModel,
    EpisodeThumbnailStore,
    FollowingEpisodeBrowser,
    SeasonListModel,
    WATCHED_ROLE,
    build_episode_season_groups,
)


def test_build_episode_season_groups_sorts_and_falls_back_to_single_season() -> None:
    episodes = [
        FollowingEpisode(episode_number=12, season_number=0, title="十二"),
        FollowingEpisode(episode_number=2, season_number=0, title="二"),
    ]

    groups = build_episode_season_groups(episodes, fallback_season=0)

    assert [group.season_number for group in groups] == [1]
    assert [episode.episode_number for episode in groups[0].episodes] == [2, 12]


def test_build_episode_season_groups_keeps_multiple_seasons_separate() -> None:
    episodes = [
        FollowingEpisode(episode_number=3, season_number=2, title="S2E3"),
        FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
    ]

    groups = build_episode_season_groups(episodes, fallback_season=0)

    assert [group.season_number for group in groups] == [1, 2]
    assert groups[0].display_title == "第 1 季"
    assert groups[1].display_title == "第 2 季"


def test_season_list_model_exposes_group_labels() -> None:
    model = SeasonListModel()
    model.set_groups(build_episode_season_groups([], fallback_season=3))

    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "第 3 季 · 0 集"


def test_episode_list_model_replaces_rows_for_current_season() -> None:
    model = EpisodeListModel()
    season_one = [FollowingEpisode(episode_number=1, title="第一集")]
    season_two = [FollowingEpisode(episode_number=20, title="第二十集")]

    model.set_episodes(season_one, current_episode=0)
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole).startswith("1.")

    model.set_episodes(season_two, current_episode=0)
    assert model.rowCount() == 1
    assert "20." in model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)


def test_episode_list_model_tracks_display_mode() -> None:
    model = EpisodeListModel(display_mode=EpisodeDisplayMode.POSTER)

    assert model.display_mode == EpisodeDisplayMode.POSTER
    model.set_display_mode(EpisodeDisplayMode.FULL)
    assert model.display_mode == EpisodeDisplayMode.FULL


def test_episode_list_model_marks_watched_rows() -> None:
    model = EpisodeListModel()
    model.set_episodes(
        [
            FollowingEpisode(episode_number=1, title="第一集"),
            FollowingEpisode(episode_number=3, title="第三集"),
        ],
        current_episode=1,
    )

    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole + 1) is True
    assert model.data(model.index(1, 0), Qt.ItemDataRole.UserRole + 1) is False


def test_episode_list_model_emits_data_changed_when_display_mode_changes() -> None:
    model = EpisodeListModel(display_mode=EpisodeDisplayMode.COMPACT)
    model.set_episodes([FollowingEpisode(episode_number=1, title="第一集")], current_episode=0)
    changed: list[tuple[int, int]] = []
    model.dataChanged.connect(
        lambda top, bottom, _roles=None: changed.append((top.row(), bottom.row()))
    )

    model.set_display_mode(EpisodeDisplayMode.FULL)

    assert model.display_mode == EpisodeDisplayMode.FULL
    assert changed == [(0, 0)]


def test_episode_thumbnail_store_refreshes_only_matching_rows() -> None:
    store = EpisodeThumbnailStore()
    model = EpisodeListModel()
    model.set_episodes(
        [
            FollowingEpisode(episode_number=1, title="第一集", still="same"),
            FollowingEpisode(episode_number=2, title="第二集", still="other"),
        ],
        current_episode=0,
    )
    changed: list[tuple[int, int]] = []
    model.dataChanged.connect(
        lambda top, bottom, _roles=None: changed.append((top.row(), bottom.row()))
    )

    model.attach_thumbnail_store(store)
    store._handle_thumbnail_ready(
        "same",
        QImage(8, 8, QImage.Format.Format_RGB32),
    )

    assert changed == [(0, 0)]


def test_following_episode_browser_uses_configured_initial_grid_columns(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=3)
    qtbot.addWidget(browser)

    assert browser.grid_columns() == 3


def test_following_episode_browser_normalizes_invalid_initial_grid_columns(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=99)
    qtbot.addWidget(browser)

    assert browser.grid_columns() == 1


def test_following_episode_browser_emits_grid_columns_changed(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    changed: list[int] = []
    browser.grid_columns_changed.connect(changed.append)

    browser.set_grid_columns(2)

    assert browser.grid_columns() == 2
    assert changed == [2]


def test_following_episode_browser_exposes_three_workspace_panes(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)

    assert browser.season_list.parent() is browser.browser_frame
    assert browser.season_detail_panel.parent() is browser.browser_frame
    assert browser.episode_list_panel.parent() is browser.browser_frame


def test_following_episode_browser_cycles_grid_columns_with_single_button(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    changed: list[int] = []
    browser.grid_columns_changed.connect(changed.append)

    assert browser.grid_cycle_button.text() == "▭"

    browser.grid_cycle_button.click()
    browser.grid_cycle_button.click()
    browser.grid_cycle_button.click()

    assert changed == [2, 3, 1]
    assert browser.grid_columns() == 1


def test_following_episode_browser_updates_season_detail_panel_on_selection(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1", overview="剧情")],
            seasons=[
                FollowingSeason(
                    season_number=1,
                    title="第一季",
                    overview="第一季简介",
                    poster="poster-1",
                    episode_count=8,
                ),
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    overview="第二季简介",
                    poster="poster-2",
                    episode_count=6,
                ),
            ],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=1,
    )

    season_model = browser.season_list.model()
    browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert browser.season_detail_title_label.text() == "第二季"
    assert "第二季简介" in browser.season_detail_overview_label.text()


def test_following_episode_browser_exposes_selected_season_summary(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    groups = build_episode_season_groups(
        [FollowingEpisode(episode_number=1, season_number=2, title="S2E1", overview="剧情", still="still")],
        seasons=[
            FollowingSeason(
                season_number=2,
                title="第二季",
                overview="本季简介",
                poster="poster",
                episode_count=8,
            )
        ],
        fallback_season=0,
    )

    browser.set_content(
        groups=groups,
        current_episode=0,
        current_season_number=0,
        selected_season_number=2,
    )

    summary = browser.current_season_summary()
    assert summary.title == "第二季"
    assert summary.overview == "本季简介"
    assert summary.poster == "poster"
    assert summary.episode_count == 8


def test_following_episode_browser_keeps_episode_overview_in_multi_column_modes(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=1, title="冒险开始", overview="完整剧情", still="still")],
            fallback_season=1,
        ),
        current_episode=0,
    )

    browser.set_grid_columns(3)

    card = browser.episode_cards[0]
    assert "完整剧情" in card.overview_label.text()
    assert card.overview_label.maximumHeight() > 0


def test_following_episode_browser_restores_selection_when_switching_back_to_season(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1"),
            ],
            fallback_season=0,
        ),
        current_episode=0,
    )

    season_model = browser.season_list.model()
    browser.season_list.setCurrentIndex(season_model.index(1, 0))
    browser.episode_list.setCurrentIndex(browser.episode_model.index(0, 0))
    browser.season_list.setCurrentIndex(season_model.index(0, 0))
    browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert browser.episode_list.currentIndex().row() == 0


def test_following_episode_browser_marks_watched_only_in_current_season(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1"),
            ],
            fallback_season=0,
        ),
        current_episode=1,
        current_season_number=2,
        selected_season_number=1,
    )

    assert browser.episode_model.data(browser.episode_model.index(0, 0), WATCHED_ROLE) is False

    season_model = browser.season_list.model()
    browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert browser.episode_model.data(browser.episode_model.index(0, 0), WATCHED_ROLE) is True
