from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from atv_player.following_models import (
    FollowingEpisode,
    FollowingEpisodeState,
    FollowingSeason,
    resolve_following_episode_state,
)
from atv_player.ui.following_episode_browser import (
    EpisodeDisplayMode,
    EpisodeListModel,
    EpisodeThumbnailStore,
    FollowingEpisodeBrowser,
    FollowingSeasonPosterPreviewDialog,
    SeasonListModel,
    STATUS_ROLE,
    STATUS_TEXT_ROLE,
    WATCHED_ROLE,
    _card_metrics_for_columns,
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


def test_resolve_following_episode_state_prioritizes_same_day_next_episode() -> None:
    episode = FollowingEpisode(episode_number=24, season_number=1, air_date="2026-05-26")
    next_episode = FollowingEpisode(episode_number=24, season_number=1, air_date="2026-05-26")

    state = resolve_following_episode_state(
        episode=episode,
        current_season_number=1,
        current_episode=23,
        latest_season_number=1,
        latest_episode=24,
        visible_season_number=1,
        next_episode=next_episode,
        today=date(2026, 5, 26),
    )

    assert state == FollowingEpisodeState.UPCOMING


def test_resolve_following_episode_state_does_not_mark_other_season_as_released() -> None:
    episode = FollowingEpisode(episode_number=1, season_number=2, air_date="2026-05-26")

    state = resolve_following_episode_state(
        episode=episode,
        current_season_number=1,
        current_episode=23,
        latest_season_number=1,
        latest_episode=24,
        visible_season_number=2,
        next_episode=None,
        today=date(2026, 5, 26),
    )

    assert state == FollowingEpisodeState.PENDING


def test_resolve_following_episode_state_marks_aired_older_season_episode_as_released() -> None:
    episode = FollowingEpisode(episode_number=581, season_number=14, air_date="2013-07-14")

    state = resolve_following_episode_state(
        episode=episode,
        current_season_number=14,
        current_episode=580,
        latest_season_number=21,
        latest_episode=1129,
        visible_season_number=14,
        next_episode=None,
        today=date(2026, 5, 26),
    )

    assert state == FollowingEpisodeState.RELEASED


def test_resolve_following_episode_state_marks_aired_current_season_episode_as_released_when_latest_is_stale() -> None:
    episode = FollowingEpisode(episode_number=581, season_number=14, air_date="2013-07-14")

    state = resolve_following_episode_state(
        episode=episode,
        current_season_number=14,
        current_episode=580,
        latest_season_number=14,
        latest_episode=580,
        visible_season_number=14,
        next_episode=None,
        today=date(2026, 5, 26),
    )

    assert state == FollowingEpisodeState.RELEASED


def test_resolve_following_episode_state_limits_upcoming_to_nearest_future_air_date() -> None:
    nearest = FollowingEpisode(episode_number=24, season_number=1, air_date="2026-05-31")
    later = FollowingEpisode(episode_number=25, season_number=1, air_date="2026-06-07")

    nearest_state = resolve_following_episode_state(
        episode=nearest,
        current_season_number=1,
        current_episode=23,
        latest_season_number=1,
        latest_episode=23,
        visible_season_number=1,
        next_episode=nearest,
        today=date(2026, 5, 26),
    )
    later_state = resolve_following_episode_state(
        episode=later,
        current_season_number=1,
        current_episode=23,
        latest_season_number=1,
        latest_episode=23,
        visible_season_number=1,
        next_episode=nearest,
        today=date(2026, 5, 26),
    )

    assert nearest_state == FollowingEpisodeState.UPCOMING
    assert later_state == FollowingEpisodeState.PENDING


def test_resolve_following_episode_state_marks_same_next_air_date_batch_as_upcoming() -> None:
    next_episode = FollowingEpisode(episode_number=24, season_number=1, air_date="2026-05-31")
    same_day_batch_episode = FollowingEpisode(episode_number=25, season_number=1, air_date="2026-05-31")

    state = resolve_following_episode_state(
        episode=same_day_batch_episode,
        current_season_number=1,
        current_episode=23,
        latest_season_number=1,
        latest_episode=23,
        visible_season_number=1,
        next_episode=next_episode,
        today=date(2026, 5, 26),
    )

    assert state == FollowingEpisodeState.UPCOMING


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


def test_episode_list_model_exposes_upcoming_status_for_same_day_next_episode() -> None:
    model = EpisodeListModel()
    model.set_episodes(
        [FollowingEpisode(episode_number=24, season_number=1, title="第 24 集", air_date="2026-05-26")],
        current_episode=23,
        current_season_number=1,
        visible_season_number=1,
        latest_episode=24,
        latest_season_number=1,
        next_episode=FollowingEpisode(episode_number=24, season_number=1, air_date="2026-05-26"),
    )

    assert model.data(model.index(0, 0), STATUS_ROLE) == FollowingEpisodeState.UPCOMING
    assert model.data(model.index(0, 0), STATUS_TEXT_ROLE) == "即将更新"


def test_episode_list_model_falls_back_to_nearest_future_air_date_when_next_episode_missing() -> None:
    model = EpisodeListModel()
    model.set_episodes(
        [
            FollowingEpisode(episode_number=24, season_number=1, title="第 24 集", air_date="2026-05-31"),
            FollowingEpisode(episode_number=25, season_number=1, title="第 25 集", air_date="2026-06-07"),
        ],
        current_episode=23,
        current_season_number=1,
        visible_season_number=1,
        latest_episode=23,
        latest_season_number=1,
        next_episode=None,
    )

    assert model.data(model.index(0, 0), STATUS_ROLE) == FollowingEpisodeState.UPCOMING
    assert model.data(model.index(1, 0), STATUS_ROLE) == FollowingEpisodeState.PENDING


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


def test_following_episode_browser_uses_pointing_hand_cursor_for_episode_cards(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)

    assert browser.episode_list.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert browser.episode_list.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor


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


def test_following_episode_browser_uses_official_style_season_detail_layout(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    overview="第二季简介",
                    poster="poster-2",
                    air_date="2026-05-13",
                    episode_count=24,
                )
            ],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )

    assert browser.season_detail_poster_label.minimumWidth() > 96
    assert browser.season_detail_top_row.parent() is browser.season_detail_panel
    assert browser.season_detail_info_layout.count() == 4
    assert browser.season_detail_air_date_label.text() == "2026-05-13"
    assert browser.season_detail_episode_count_label.text() == "共 24 集"
    assert browser.season_detail_overview_label.text() == "第二季简介"


def test_following_episode_browser_season_detail_text_is_selectable(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)

    selectable = Qt.TextInteractionFlag.TextSelectableByMouse
    assert browser.season_detail_title_label.textInteractionFlags() & selectable
    assert browser.season_detail_air_date_label.textInteractionFlags() & selectable
    assert browser.season_detail_episode_count_label.textInteractionFlags() & selectable
    assert browser.season_detail_overview_label.textInteractionFlags() & selectable


def test_following_episode_browser_places_title_count_and_air_date_at_top(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)

    assert browser.season_detail_info_layout.itemAt(0).widget() is browser.season_detail_title_label
    assert browser.season_detail_info_layout.itemAt(1).widget() is browser.season_detail_episode_count_label
    assert browser.season_detail_info_layout.itemAt(2).widget() is browser.season_detail_air_date_label
    assert browser.season_detail_info_layout.itemAt(3).spacerItem() is not None


def test_following_episode_browser_uses_virtual_list_instead_of_card_grid(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                FollowingEpisode(episode_number=3, season_number=1, title="S1E3"),
            ],
            fallback_season=1,
        ),
        current_episode=0,
    )

    assert browser.episode_list.isHidden() is False
    assert browser.episode_scroll.isHidden() is True
    assert browser.episode_cards == []


def test_following_episode_browser_clears_unused_grid_column_stretch_when_reducing_columns(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.resize(960, 720)
    browser.show()
    browser.set_content(
        groups=build_episode_season_groups(
            [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                FollowingEpisode(episode_number=3, season_number=1, title="S1E3"),
            ],
            fallback_season=1,
        ),
        current_episode=0,
    )
    qtbot.waitUntil(lambda: browser.episode_list.gridSize().width() > 0, timeout=1000)

    viewport_width = browser.episode_list.viewport().width()
    spacing = browser.episode_list.spacing()
    rect_width_one = browser.episode_list.visualRect(browser.episode_model.index(0, 0)).width()
    browser.set_grid_columns(3)
    rect_width_three = browser.episode_list.visualRect(browser.episode_model.index(0, 0)).width()
    browser.set_grid_columns(2)
    rect_width_two = browser.episode_list.visualRect(browser.episode_model.index(0, 0)).width()

    assert rect_width_one == viewport_width
    assert rect_width_two == (viewport_width - spacing) // 2
    assert rect_width_three == (viewport_width - (spacing * 2)) // 3


def test_following_episode_browser_switches_virtual_list_display_mode(qtbot) -> None:
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

    assert browser.episode_model.display_mode == EpisodeDisplayMode.COMPACT


def test_following_episode_browser_keeps_thumbnail_size_constant_across_columns() -> None:
    full = _card_metrics_for_columns(1)
    poster = _card_metrics_for_columns(2)
    compact = _card_metrics_for_columns(3)

    assert (full.thumbnail_width, full.thumbnail_height) == (poster.thumbnail_width, poster.thumbnail_height)
    assert (poster.thumbnail_width, poster.thumbnail_height) == (compact.thumbnail_width, compact.thumbnail_height)


def test_following_episode_browser_clicking_card_emits_episode_activated(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.resize(960, 720)
    browser.show()
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=1, title="冒险开始", overview="完整剧情", still="still")],
            fallback_season=1,
        ),
        current_episode=0,
    )
    activated: list[int] = []
    browser.episode_activated.connect(lambda episode: activated.append(episode.episode_number))
    index = browser.episode_model.index(0, 0)
    rect = browser.episode_list.visualRect(index)

    qtbot.mouseClick(
        browser.episode_list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )

    assert activated == [1]


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
                    air_date="2026-05-13",
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
    assert browser.season_detail_air_date_label.text() == "2026-05-13"
    assert browser.season_detail_episode_count_label.text() == "共 6 集"
    assert "第二季简介" in browser.season_detail_overview_label.text()


def test_following_episode_browser_opens_large_preview_from_season_poster_click(
    qtbot, monkeypatch
) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[
                FollowingSeason(
                    season_number=2,
                    title="第二季",
                    poster="poster-2",
                    episode_count=8,
                )
            ],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "atv_player.ui.following_episode_browser.FollowingSeasonPosterPreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.windowTitle()) or 1,
    )

    browser._open_current_season_poster_preview()

    assert opened == ["第二季"]


def test_following_season_poster_preview_dialog_uses_taller_portrait_friendly_canvas(
    qtbot,
) -> None:
    dialog = FollowingSeasonPosterPreviewDialog("第二季", "poster")
    qtbot.addWidget(dialog)

    assert dialog.poster_label.minimumWidth() >= 640
    assert dialog.poster_label.minimumHeight() > 360


def test_following_season_poster_preview_dialog_scales_loaded_image_to_fit_label_height(
    qtbot,
) -> None:
    dialog = FollowingSeasonPosterPreviewDialog("第二季", "poster")
    qtbot.addWidget(dialog)

    image = QImage(600, 900, QImage.Format.Format_RGB32)
    dialog._handle_image_loaded(dialog.poster_label, image)

    pixmap = dialog.poster_label.pixmap()
    assert pixmap is not None
    assert pixmap.height() <= dialog.poster_label.minimumHeight()


def test_following_episode_browser_skips_poster_preview_when_no_poster_available(
    qtbot, monkeypatch
) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=1, season_number=2, title="S2E1")],
            seasons=[FollowingSeason(season_number=2, title="第二季", episode_count=8)],
            fallback_season=1,
        ),
        current_episode=0,
        selected_season_number=2,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "atv_player.ui.following_episode_browser.FollowingSeasonPosterPreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.windowTitle()) or 1,
    )

    browser._open_current_season_poster_preview()

    assert opened == []


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


def test_following_episode_browser_renders_inline_status_badge_on_card(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [FollowingEpisode(episode_number=128, season_number=1, title="新章", air_date="2026-05-19")],
            fallback_season=1,
        ),
        current_episode=127,
        current_season_number=1,
        latest_episode=128,
        latest_season_number=1,
        next_episode=None,
    )

    index = browser.episode_model.index(0, 0)
    assert browser.episode_model.data(index, Qt.ItemDataRole.DisplayRole) == "128. 新章"
    assert browser.episode_model.data(index, STATUS_TEXT_ROLE) == "已更新"
    assert browser.episode_model.data(index, STATUS_ROLE) == FollowingEpisodeState.RELEASED


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

    assert browser.episode_model.display_mode == EpisodeDisplayMode.COMPACT
    assert browser.episode_model.data(browser.episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "1. 冒险开始"


def test_following_episode_browser_does_not_build_card_widgets_for_large_season(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    browser.set_content(
        groups=build_episode_season_groups(
            [
                FollowingEpisode(episode_number=episode_number, season_number=1, title=f"第{episode_number}集")
                for episode_number in range(1, 1201)
            ],
            fallback_season=1,
        ),
        current_episode=0,
    )

    assert browser.episode_model.rowCount() == 1200
    assert browser.episode_cards == []
    assert browser.episode_list.isHidden() is False


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


def test_following_episode_browser_marks_previous_seasons_as_watched(qtbot) -> None:
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

    assert browser.episode_model.data(browser.episode_model.index(0, 0), WATCHED_ROLE) is True

    season_model = browser.season_list.model()
    browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert browser.episode_model.data(browser.episode_model.index(0, 0), WATCHED_ROLE) is True
