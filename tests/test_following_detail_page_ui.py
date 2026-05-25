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

    def load_detail(self, following_id: int):
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
    page.search_play_requested.connect(search_play.append)

    page.load_record(1)
    page.search_play_button.click()
    page.manual_check_button.click()
    page.mark_latest_button.click()

    assert page.title_label.text() == "凡人修仙传"
    assert "最新 128 / 总 156" in page.meta_label.text()
    assert page.episode_widgets[0].title_label.text().startswith("128")
    assert page.cast_widgets[0].name_label.text() == "韩立"
    assert search_play == [1]
    assert controller.manual_checks == [1]
    assert controller.mark_latest == [1]
