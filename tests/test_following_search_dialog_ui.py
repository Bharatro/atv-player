from types import SimpleNamespace

from PySide6.QtWidgets import QDialog

from atv_player.controllers.following_controller import FollowingController
from atv_player.following_repository import FollowingRepository
from atv_player.metadata.models import MetadataRecord
from atv_player.ui.following_search_dialog import FollowingSearchDialog


def test_following_search_dialog_matches_scrape_dialog_shell_and_adds_selection(qtbot) -> None:
    candidate = SimpleNamespace(title="凡人修仙传", year="2026", subtitle="Bangumi")

    class Controller:
        def __init__(self) -> None:
            self.added = []

        def search_media(self, keyword: str):
            assert keyword == "凡人"
            return [
                SimpleNamespace(
                    provider="bangumi",
                    provider_label="Bangumi",
                    items=[candidate],
                    error_text="",
                )
            ]

        def add_candidate(self, selected) -> None:
            self.added.append(selected)

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)

    assert dialog.title_bar().title_label.text() == "添加追更"
    assert dialog.title_bar().maximize_button.isHidden() is True

    dialog.search_edit.setText("凡人")
    dialog.run_search()

    assert dialog.group_list.count() == 1
    assert dialog.result_list.count() == 1
    assert "找到 1 个结果" in dialog.status_label.text()

    dialog.result_list.setCurrentRow(0)
    dialog.current_episode_spin.setValue(12)
    dialog.add_button.click()

    assert controller.added == [candidate]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_following_search_dialog_passes_manual_current_episode_when_supported(qtbot) -> None:
    candidate = SimpleNamespace(title="凡人修仙传", year="2026", subtitle="Bangumi")

    class Controller:
        def __init__(self) -> None:
            self.added = []

        def search_media(self, _keyword: str):
            return [SimpleNamespace(provider="bangumi", provider_label="Bangumi", items=[candidate], error_text="")]

        def add_candidate(self, selected, *, current_episode: int = 0) -> None:
            self.added.append((selected, current_episode))

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("凡人")
    dialog.run_search()
    dialog.current_episode_spin.setValue(12)
    dialog.add_button.click()

    assert controller.added == [(candidate, 12)]


def test_following_search_dialog_renders_tmdb_url_candidate_details(qtbot, tmp_path) -> None:
    class SearchService:
        def detail_record(self, candidate):
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="名侦探柯南",
                year="1996",
                tmdb_id="30983",
            )

    controller = FollowingController(
        FollowingRepository(tmp_path / "app.db"),
        metadata_search_service=SearchService(),
    )
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("https://www.themoviedb.org/tv/30983-case-closed")
    dialog.run_search()

    assert dialog.result_list.count() == 1
    assert dialog.result_list.item(0).text() == "名侦探柯南 · 1996 · 剧集"
