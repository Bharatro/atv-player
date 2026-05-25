from atv_player.following_models import FollowingCardItem, FollowingRecord
from atv_player.ui.following_page import FollowingPage


class FakeFollowingController:
    def __init__(self) -> None:
        self.check_all_calls = 0
        self.only_updates_seen: list[bool] = []

    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        del page, size, keyword
        self.only_updates_seen.append(only_updates)
        record = FollowingRecord(
            id=1,
            title="凡人修仙传",
            provider="bangumi",
            provider_id="subject:1",
            current_episode=127,
            latest_episode=128,
            total_episodes=156,
            has_update=True,
        )
        return [
            FollowingCardItem(
                record=record,
                display_title=record.title,
                subtitle="Bangumi",
                progress_text="看到 127 · 最新 128 / 总 156",
                update_text="有 1 集更新",
                updated_hint=True,
            )
        ], 1

    def check_all_due(self) -> None:
        self.check_all_calls += 1


def test_following_page_renders_update_card_and_emits_detail(qtbot) -> None:
    controller = FakeFollowingController()
    page = FollowingPage(controller)
    qtbot.addWidget(page)
    opened: list[int] = []
    page.open_detail_requested.connect(opened.append)

    page.ensure_loaded()
    page.card_widgets[0].double_clicked.emit(page.records[0].record.id)

    assert page.records[0].display_title == "凡人修仙传"
    assert page.records[0].updated_hint is True
    assert opened == [1]


def test_following_page_filters_updates_and_runs_manual_check(qtbot) -> None:
    controller = FakeFollowingController()
    page = FollowingPage(controller)
    qtbot.addWidget(page)

    page.only_updates_checkbox.setChecked(True)
    page.load_page()
    page.check_updates_button.click()

    assert controller.only_updates_seen[-1] is True
    assert controller.check_all_calls == 1
