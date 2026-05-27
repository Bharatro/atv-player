from types import SimpleNamespace
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLabel, QWidget

import atv_player.ui.following_search_dialog as following_search_dialog_module
from atv_player.controllers.following_controller import FollowingController
from atv_player.following_repository import FollowingRepository
from atv_player.metadata.discovery import DiscoveryItem, DiscoveryResult
from atv_player.metadata.models import MetadataRecord
from atv_player.ui.following_search_dialog import FollowingSearchDialog


def test_following_search_dialog_matches_scrape_dialog_shell_and_adds_selection(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="tv:1:season:1",
        title="凡人修仙传",
        year="2026",
        raw={"rating": "8.8", "overview": "修仙剧情"},
    )

    class Controller:
        def __init__(self) -> None:
            self.added = []

        def search_media(self, keyword: str, *, year: str = ""):
            assert keyword == "凡人"
            assert year == ""
            return [
                SimpleNamespace(
                    provider="tmdb",
                    provider_label="TMDB",
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

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert dialog.result_list.count() == 1
    assert "找到 1 个结果" in dialog.status_label.text()
    assert hasattr(dialog, "group_list") is False

    card = dialog.result_list.itemWidget(dialog.result_list.item(0))
    assert card.title_label.text() == "凡人修仙传"
    assert card.meta_label.text() == "2026 · 电视"
    assert card.rating_label.text() == "8.8"
    assert card.overview_label.text() == "修仙剧情"
    assert hasattr(dialog, "current_episode_spin") is False

    dialog.result_list.setCurrentRow(0)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: controller.added == [candidate])
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted)

    assert controller.added == [candidate]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_following_search_dialog_adds_without_manual_current_episode_input(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="tv:1:season:1",
        title="凡人修仙传",
        year="2026",
        raw={},
    )

    class Controller:
        def __init__(self) -> None:
            self.added = []

        def search_media(self, _keyword: str, *, year: str = ""):
            assert year == ""
            return [SimpleNamespace(provider="tmdb", provider_label="TMDB", items=[candidate], error_text="")]

        def add_candidate(self, selected, **kwargs) -> None:
            self.added.append((selected, kwargs))

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("凡人")
    dialog.run_search()
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: controller.added == [(candidate, {})])
    assert controller.added == [(candidate, {})]


def test_following_search_dialog_renders_tmdb_url_candidate_details(qtbot, tmp_path) -> None:
    class SearchService:
        def detail_record(self, candidate):
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="名侦探柯南",
                year="1996",
                poster="https://img.test/conan.jpg",
                overview="高中生侦探化身小学生继续破案。",
                rating="8.9",
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
    card = dialog.result_list.itemWidget(dialog.result_list.item(0))
    assert card.title_label.text() == "名侦探柯南"
    assert card.meta_label.text() == "1996 · 电视"
    assert card.rating_label.text() == "8.9"
    assert card.overview_label.text().replace("\n", "") == "高中生侦探化身小学生继续破案。"


def test_following_search_dialog_runs_search_off_main_thread(qtbot) -> None:
    candidate = SimpleNamespace(provider_id="tv:1:season:1", title="凡人修仙传", year="2026", raw={})
    main_thread = threading.get_ident()
    search_threads: list[int] = []

    class Controller:
        def search_media(self, _keyword: str, *, year: str = ""):
            assert year == ""
            search_threads.append(threading.get_ident())
            return [
                SimpleNamespace(
                    provider="tmdb",
                    provider_label="TMDB",
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
    candidate = SimpleNamespace(provider_id="tv:1:season:1", title="凡人修仙传", year="2026", raw={})
    main_thread = threading.get_ident()
    add_threads: list[int] = []

    class Controller:
        def search_media(self, _keyword: str, *, year: str = ""):
            assert year == ""
            return [
                SimpleNamespace(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[candidate],
                    error_text="",
                )
            ]

        def add_candidate(self, selected, **kwargs) -> None:
            assert selected is candidate
            assert kwargs == {}
            add_threads.append(threading.get_ident())

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("凡人")
    dialog.run_search()
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    dialog.result_list.setCurrentRow(0)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: len(add_threads) == 1)
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted)

    assert add_threads == [add_threads[0]]
    assert add_threads[0] != main_thread


def test_following_search_dialog_pressing_return_in_search_edit_runs_search_without_closing(qtbot) -> None:
    candidate = SimpleNamespace(provider_id="tv:1:season:1", title="凡人修仙传", year="2026", raw={})
    search_calls: list[str] = []

    class Controller:
        def search_media(self, keyword: str, *, year: str = ""):
            search_calls.append(f"{keyword}|{year}")
            return [
                SimpleNamespace(
                    provider="tmdb",
                    provider_label="TMDB",
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

    qtbot.waitUntil(lambda: search_calls == ["凡人|"])
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


def test_following_search_dialog_blocks_invalid_search_year(qtbot) -> None:
    class Controller:
        def search_media(self, keyword: str, *, year: str = ""):
            raise AssertionError("search_media should not be called for invalid year input")

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("柯南")
    dialog.search_year_edit.setText("202")
    dialog.run_search()

    assert dialog.status_label.text() == "请输入 4 位年份"


def test_following_search_dialog_defaults_to_search_tab_and_preloads_discovery_tabs(qtbot) -> None:
    trending = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:100",
        tmdb_id="100",
        media_type="tv",
        title="Gen V",
        year="2023",
        source_label="本周趋势",
    )

    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append(tab_key)
            assert kwargs["page"] == 1
            if tab_key == "trending":
                return DiscoveryResult(items=[trending], total=1, source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            raise AssertionError(f"unexpected tab: {tab_key}")

        def add_candidate(self, selected, **kwargs) -> None:
            assert selected.provider_id == "tv:100"
            assert kwargs == {}

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.active_tab_button() is not None
    assert dialog.active_tab_button().text() == "搜索"
    assert dialog.search_edit.isHidden() is False
    assert dialog.result_list.count() == 0

    qtbot.waitUntil(lambda: {"trending", "recommendation"}.issubset(set(controller.calls)))

    dialog._activate_tab("trending")

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert controller.calls.count("trending") == 1


def test_following_search_dialog_renders_all_discovery_results_as_lightweight_items(qtbot) -> None:
    items = [
        DiscoveryItem(
            provider="tmdb",
            provider_id=f"tv:{index}",
            tmdb_id=str(index),
            media_type="tv",
            title=f"热门 {index}",
            year="2024",
            source_label="本周趋势",
        )
        for index in range(45)
    ]

    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "trending":
                return DiscoveryResult(items=items, total=len(items), source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            raise AssertionError(f"unexpected tab: {tab_key}")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("trending")
    qtbot.waitUntil(lambda: dialog.result_list.count() == 45)

    assert dialog.status_label.text() == "本周趋势 · 找到 45 个结果"
    assert dialog.result_list.itemWidget(dialog.result_list.item(0)) is None


def test_following_search_dialog_search_year_field_is_only_visible_on_search_tab(qtbot) -> None:
    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            return DiscoveryResult(items=[], total=0, source_label=tab_key)

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.search_year_edit.isHidden() is False

    dialog._activate_tab("trending")

    assert dialog.search_year_edit.isHidden() is True

    dialog._activate_tab("search")

    assert dialog.search_year_edit.isHidden() is False


def test_following_search_dialog_search_field_labels_only_visible_on_search_tab(qtbot) -> None:
    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            return DiscoveryResult(items=[], total=0, source_label=tab_key)

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    field_labels = [label for label in dialog.findChildren(QLabel) if label.text() in {"标题", "年份"}]

    assert {label.text() for label in field_labels} == {"标题", "年份"}
    assert all(not label.isHidden() for label in field_labels)

    dialog._activate_tab("trending")

    assert all(label.isHidden() for label in field_labels)

    dialog._activate_tab("search")

    assert all(not label.isHidden() for label in field_labels)


def test_following_search_dialog_switching_to_search_preserves_url_direct_path(qtbot) -> None:
    candidate = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:30983",
        tmdb_id="30983",
        media_type="tv",
        title="名侦探柯南",
        year="1996",
        source_label="搜索",
    )

    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append((tab_key, kwargs))
            if tab_key == "search":
                assert kwargs["query"] == "https://www.themoviedb.org/tv/30983-case-closed"
                return DiscoveryResult(items=[candidate], total=1, source_label="搜索")
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            return DiscoveryResult(items=[], total=0, source_label="推荐")

        def add_candidate(self, selected, **kwargs) -> None:
            assert selected is candidate
            assert kwargs == {}

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog._activate_tab("search")
    dialog.search_edit.setText("https://www.themoviedb.org/tv/30983-case-closed")
    dialog.run_search()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert dialog.result_list.itemWidget(dialog.result_list.item(0)).title_label.text() == "名侦探柯南"
    assert any(call[0] == "search" for call in controller.calls)


def test_following_search_dialog_search_tab_passes_year_filter_and_cache_key_uses_it(qtbot) -> None:
    candidate = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:30983",
        tmdb_id="30983",
        media_type="tv",
        title="名侦探柯南",
        year="1996",
        source_label="搜索",
    )

    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append((tab_key, kwargs))
            if tab_key == "search":
                return DiscoveryResult(items=[candidate], total=1, source_label="搜索")
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            return DiscoveryResult(items=[], total=0, source_label="推荐")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("search")
    dialog.search_edit.setText("柯南")
    dialog.search_year_edit.setText("1996")
    dialog.run_search()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    assert controller.calls[-1][0] == "search"
    assert controller.calls[-1][1]["filters"]["year"] == "1996"
    assert '"year":"1996"' in dialog._state_key("search")


def test_following_search_dialog_uses_four_tab_buttons_instead_of_combo(qtbot) -> None:
    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            return DiscoveryResult(items=[], total=0, source_label=tab_key)

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "tab_bar") is False
    assert [button.text() for button in dialog.tab_buttons] == ["推荐", "热门", "筛选", "搜索"]
    assert dialog.active_tab_button().text() == "搜索"


def test_following_search_dialog_can_switch_to_search_while_recommendation_request_is_in_flight(qtbot) -> None:
    candidate = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:30983",
        tmdb_id="30983",
        media_type="tv",
        title="名侦探柯南",
        year="1996",
        source_label="搜索",
    )
    release_recommendation = threading.Event()

    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "recommendation":
                release_recommendation.wait(timeout=2)
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            assert tab_key == "search"
            return DiscoveryResult(items=[candidate], total=1, source_label="搜索")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("recommendation")
    dialog._activate_tab("search")
    dialog.search_edit.setText("柯南")
    dialog.run_search()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert dialog.active_tab_button().text() == "搜索"
    release_recommendation.set()


def test_following_search_dialog_switching_back_to_loaded_tab_reuses_cached_results_immediately(qtbot) -> None:
    recommendation = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:100",
        tmdb_id="100",
        media_type="tv",
        title="Gen V",
        year="2023",
        source_label="推荐",
    )
    search_item = DiscoveryItem(
        provider="tmdb",
        provider_id="tv:30983",
        tmdb_id="30983",
        media_type="tv",
        title="名侦探柯南",
        year="1996",
        source_label="搜索",
    )

    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append(tab_key)
            if tab_key == "search":
                return DiscoveryResult(items=[search_item], total=1, source_label="搜索")
            if tab_key == "trending":
                return DiscoveryResult(items=[], total=0, source_label="本周趋势")
            return DiscoveryResult(items=[recommendation], total=1, source_label="推荐")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("recommendation")
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert dialog.result_list.item(0).data(Qt.ItemDataRole.UserRole).title == "Gen V"

    dialog._activate_tab("search")
    dialog.search_edit.setText("柯南")
    dialog.run_search()
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    qtbot.waitUntil(
        lambda: dialog.result_list.itemWidget(dialog.result_list.item(0)) is not None
        and dialog.result_list.itemWidget(dialog.result_list.item(0)).title_label.text() == "名侦探柯南"
    )

    dialog._activate_tab("recommendation")

    assert dialog.result_list.item(0).data(Qt.ItemDataRole.UserRole).title == "Gen V"


def test_following_search_dialog_discovery_results_do_not_create_card_widgets(qtbot, monkeypatch) -> None:
    recommendation_items = [
        DiscoveryItem(
            provider="tmdb",
            provider_id=f"tv:recommendation-{index}",
            tmdb_id=f"recommendation-{index}",
            media_type="tv",
            title=f"推荐 {index}",
            year="2024",
            source_label="推荐",
        )
        for index in range(2)
    ]
    trending_items = [
        DiscoveryItem(
            provider="tmdb",
            provider_id=f"tv:trending-{index}",
            tmdb_id=f"trending-{index}",
            media_type="tv",
            title=f"热门 {index}",
            year="2024",
            source_label="热门",
        )
        for index in range(2)
    ]
    created_cards: list[str] = []

    class CountingCard(QWidget):
        def __init__(self, candidate, parent=None) -> None:
            super().__init__(parent)
            self.candidate = candidate
            self.selected = False
            created_cards.append(candidate.provider_id)

        def set_selected(self, selected: bool) -> None:
            self.selected = selected

    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "trending":
                return DiscoveryResult(items=trending_items, total=2, source_label="热门")
            if tab_key == "recommendation":
                return DiscoveryResult(items=recommendation_items, total=2, source_label="推荐")
            return DiscoveryResult(items=recommendation_items, total=2, source_label="推荐")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    monkeypatch.setattr(following_search_dialog_module, "FollowingSearchResultCard", CountingCard)
    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("recommendation")
    qtbot.waitUntil(lambda: dialog.result_list.count() == 2)
    assert created_cards == []
    assert dialog.result_list.itemWidget(dialog.result_list.item(0)) is None

    dialog._activate_tab("trending")
    qtbot.waitUntil(lambda: dialog.result_list.item(0).data(Qt.ItemDataRole.UserRole).provider_id == "tv:trending-0")
    assert created_cards == []

    dialog._activate_tab("recommendation")

    assert dialog.result_list.item(0).data(Qt.ItemDataRole.UserRole).provider_id == "tv:recommendation-0"
    assert created_cards == []


def test_following_search_dialog_discovery_delegate_loads_posters(qtbot, monkeypatch) -> None:
    poster_url = "https://img.test/poster.jpg"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0x00FF00)

    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            if tab_key == "trending":
                return DiscoveryResult(
                    items=[
                        DiscoveryItem(
                            provider="tmdb",
                            provider_id="tv:100",
                            tmdb_id="100",
                            media_type="tv",
                            title="Gen V",
                            poster=poster_url,
                        )
                    ],
                    total=1,
                    source_label="本周趋势",
                )
            return DiscoveryResult(items=[], total=0, source_label="推荐")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    monkeypatch.setattr(following_search_dialog_module, "load_local_poster_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(following_search_dialog_module, "load_remote_poster_image", lambda *_args, **_kwargs: image)

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._activate_tab("trending")
    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)

    delegate = dialog.result_list.itemDelegate()
    candidate = dialog.result_list.item(0).data(Qt.ItemDataRole.UserRole)
    delegate._ensure_poster_load(candidate, dialog.result_list)

    qtbot.waitUntil(lambda: poster_url in delegate._poster_cache)

    assert delegate._poster_cache[poster_url].isNull() is False


def test_following_search_dialog_trending_filters_change_request_parameters(qtbot) -> None:
    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append((tab_key, dict(kwargs.get("filters") or {})))
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            source_label = str((kwargs.get("filters") or {}).get("list_key") or "trending_week")
            return DiscoveryResult(items=[], total=0, source_label=source_label)

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("trending")
    qtbot.waitUntil(lambda: any(call[0] == "trending" for call in controller.calls))

    list_index = dialog.trending_list_combo.findData("trending_day")
    media_index = dialog.trending_media_combo.findData("movie")
    dialog.trending_list_combo.setCurrentIndex(list_index)
    dialog.trending_media_combo.setCurrentIndex(media_index)

    qtbot.waitUntil(
        lambda: any(
            call[0] == "trending"
            and call[1].get("list_key") == "trending_day"
            and call[1].get("media_type") == "movie"
            for call in controller.calls
        )
    )


def test_following_search_dialog_discover_filters_change_request_parameters(qtbot) -> None:
    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append((tab_key, dict(kwargs.get("filters") or {})))
            if tab_key == "recommendation":
                return DiscoveryResult(items=[], total=0, source_label="推荐")
            return DiscoveryResult(items=[], total=0, source_label="筛选结果")

        def add_candidate(self, selected, **kwargs) -> None:
            pass

    controller = Controller()
    dialog = FollowingSearchDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._activate_tab("discover")
    qtbot.waitUntil(lambda: any(call[0] == "discover" for call in controller.calls))

    media_index = dialog.discover_media_combo.findData("movie")
    sort_index = dialog.discover_sort_combo.findData("vote_average.desc")
    year_index = dialog.discover_year_combo.findData("2024")
    dialog.discover_media_combo.setCurrentIndex(media_index)
    dialog.discover_sort_combo.setCurrentIndex(sort_index)
    dialog.discover_year_combo.setCurrentIndex(year_index)

    qtbot.waitUntil(
        lambda: any(
            call[0] == "discover"
            and call[1].get("media_type") == "movie"
            and call[1].get("sort_by") == "vote_average.desc"
            and call[1].get("year") == "2024"
            for call in controller.calls
        )
    )
