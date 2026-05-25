from types import SimpleNamespace
import threading

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
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

    qtbot.waitUntil(lambda: dialog.group_list.count() == 1)
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert dialog.group_list.count() == 1
    assert dialog.result_list.count() == 1
    assert "找到 1 个结果" in dialog.status_label.text()

    dialog.result_list.setCurrentRow(0)
    dialog.current_episode_spin.setValue(12)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: controller.added == [candidate])
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted)

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
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    dialog.current_episode_spin.setValue(12)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: controller.added == [(candidate, 12)])
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

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert dialog.result_list.count() == 1
    assert dialog.result_list.item(0).text() == "名侦探柯南 · 1996 · 剧集"


def test_following_search_dialog_runs_search_off_main_thread(qtbot) -> None:
    candidate = SimpleNamespace(title="凡人修仙传", year="2026", subtitle="Bangumi")
    main_thread = threading.get_ident()
    search_threads: list[int] = []

    class Controller:
        def search_media(self, _keyword: str):
            search_threads.append(threading.get_ident())
            return [
                SimpleNamespace(
                    provider="bangumi",
                    provider_label="Bangumi",
                    items=[candidate],
                    error_text="",
                )
            ]

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("凡人")
    dialog.run_search()

    qtbot.waitUntil(lambda: len(search_threads) == 1)
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert search_threads == [search_threads[0]]
    assert search_threads[0] != main_thread


def test_following_search_dialog_adds_candidate_off_main_thread(qtbot) -> None:
    candidate = SimpleNamespace(title="凡人修仙传", year="2026", subtitle="Bangumi")
    main_thread = threading.get_ident()
    add_threads: list[int] = []

    class Controller:
        def search_media(self, _keyword: str):
            return [
                SimpleNamespace(
                    provider="bangumi",
                    provider_label="Bangumi",
                    items=[candidate],
                    error_text="",
                )
            ]

        def add_candidate(self, selected, *, current_episode: int = 0) -> None:
            assert selected is candidate
            assert current_episode == 12
            add_threads.append(threading.get_ident())

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("凡人")
    dialog.run_search()
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    dialog.result_list.setCurrentRow(0)
    dialog.current_episode_spin.setValue(12)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: len(add_threads) == 1)
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted)

    assert add_threads == [add_threads[0]]
    assert add_threads[0] != main_thread


def test_following_search_dialog_pressing_return_in_search_edit_runs_search_without_closing(qtbot) -> None:
    candidate = SimpleNamespace(title="凡人修仙传", year="2026", subtitle="Bangumi")
    search_calls: list[str] = []

    class Controller:
        def search_media(self, keyword: str):
            search_calls.append(keyword)
            return [
                SimpleNamespace(
                    provider="bangumi",
                    provider_label="Bangumi",
                    items=[candidate],
                    error_text="",
                )
            ]

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.search_edit.setFocus()
    dialog.search_edit.setText("凡人")

    QTest.keyClick(dialog.search_edit, Qt.Key.Key_Return)

    qtbot.waitUntil(lambda: search_calls == ["凡人"])
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert dialog.result() == 0


def test_following_search_dialog_action_buttons_are_not_default_submit_targets(qtbot) -> None:
    dialog = FollowingSearchDialog(object())
    qtbot.addWidget(dialog)

    assert dialog.search_button.autoDefault() is False
    assert dialog.search_button.isDefault() is False
    assert dialog.add_button.autoDefault() is False
    assert dialog.add_button.isDefault() is False
    assert dialog.close_button.autoDefault() is False
    assert dialog.close_button.isDefault() is False
