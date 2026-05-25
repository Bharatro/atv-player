from atv_player.controllers.following_controller import FollowingDetailView
from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
)
from atv_player.ui.following_detail_page import FollowingDetailPage


class FakeController:
    def __init__(self) -> None:
        self.manual_checks: list[int] = []
        self.mark_latest: list[int] = []

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
                current_episode=127,
                latest_episode=128,
                total_episodes=156,
                has_update=True,
            ),
            snapshot=FollowingDetailSnapshot(
                following_id=following_id,
                overview="长篇简介",
                cast=[{"name": "韩立", "role": "主角", "avatar": ""}],
                crew=[{"name": "导演", "job": "Director"}],
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

    def mark_watched_latest(self, following_id: int) -> None:
        self.mark_latest.append(following_id)


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
    qtbot.waitUntil(lambda: page.status_label.text() == "已完成手动检查", timeout=1000)
    assert page.status_label.text() == "已完成手动检查"
    page.mark_latest_button.click()
    page.unfollow_button.click()

    assert page.title_label.text() == "凡人修仙传"
    assert "最新 128 / 总 156" in page.meta_label.text()
    assert page.page_scroll.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"
    assert page.episode_widgets[0].title_label.text().startswith("128")
    assert page.cast_widgets[0].name_label.text() == "韩立"
    assert search_play == [1]
    assert unfollow == [1]
    assert controller.manual_checks == [1]
    assert controller.mark_latest == [1]


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
    assert "看到 127" in page.meta_label.text()


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

    assert "已看完 · 24集 · 已完结" in page.meta_label.text()
    assert "最新 24 / 总 24" not in page.meta_label.text()
