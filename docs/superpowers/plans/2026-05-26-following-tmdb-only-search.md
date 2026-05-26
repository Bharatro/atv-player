# Following TMDB-Only Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the add-following dialog search TMDB only for manual title searches, keep URL recognition intact, and render TV-first poster cards with rich metadata in a single-column result list.

**Architecture:** Keep provider-selection and candidate hydration in `FollowingController`, where URL handling already lives. Split the new result-row presentation into a focused UI widget module, then integrate that widget into `FollowingSearchDialog` while preserving its existing async search/add flow and current-episode handling.

**Tech Stack:** Python, PySide6, pytest

---

## File Map

- `src/atv_player/controllers/following_controller.py`
  Keeps add-following search routing, URL candidate hydration, and result ordering rules.
- `src/atv_player/ui/following_search_result_card.py`
  New focused widget module for one add-following result card, including poster loading, fallbacks, and media-type display helpers.
- `src/atv_player/ui/following_search_dialog.py`
  Keeps dialog lifecycle, async search/add threads, and selection behavior, but drops the provider sidebar and mounts card widgets into the result list.
- `tests/test_following_controller.py`
  Covers TMDB-only keyword routing, TV-first ordering, and non-TMDB URL passthrough.
- `tests/test_following_search_result_card.py`
  Covers card text rendering, fallback behavior, and media-type labels without dialog noise.
- `tests/test_following_search_dialog_ui.py`
  Covers the single-column dialog structure, result-card rendering, and retained add behavior.

### Task 1: TMDB-Only Search Routing and TV-First Ordering

**Files:**
- Modify: `tests/test_following_controller.py`
- Modify: `src/atv_player/controllers/following_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_following_controller_keyword_search_uses_tmdb_only_and_sorts_tv_before_movie(tmp_path: Path) -> None:
    class SearchService:
        def __init__(self) -> None:
            self.search_following_calls: list[tuple[str, str]] = []

        def search_following(self, query, provider_filter=""):
            self.search_following_calls.append((query.title, provider_filter))
            return [
                MetadataScrapeGroup(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="movie:12",
                            title="Movie First",
                            year="2024",
                            subtitle="电影",
                        ),
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:34:season:1",
                            title="TV Second",
                            year="2025",
                            subtitle="剧集",
                        ),
                    ],
                )
            ]

    controller = FollowingController(
        FollowingRepository(tmp_path / "app.db"),
        metadata_search_service=SearchService(),
    )

    groups = controller.search_media("星际")

    assert groups[0].provider == "tmdb"
    assert [item.provider_id for item in groups[0].items] == ["tv:34:season:1", "movie:12"]
    assert controller._metadata_search_service.search_following_calls == [("星际", "tmdb")]


def test_following_controller_non_tmdb_url_passthrough_still_works(tmp_path: Path) -> None:
    controller = FollowingController(
        FollowingRepository(tmp_path / "app.db"),
        metadata_search_service=FakeSearchService(),
    )

    groups = controller.search_media("https://bgm.tv/subject/123")

    assert len(groups) == 1
    assert groups[0].provider == "bangumi"
    assert groups[0].items[0].provider_id == "subject:123"


def test_following_controller_douban_url_passthrough_still_works(tmp_path: Path) -> None:
    controller = FollowingController(
        FollowingRepository(tmp_path / "app.db"),
        metadata_search_service=FakeSearchService(),
    )

    groups = controller.search_media("https://movie.douban.com/subject/1292052/")

    assert len(groups) == 1
    assert groups[0].provider in {"official_douban", "local_douban", "douban"}
    assert groups[0].items[0].provider_id == "1292052"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_keyword_search_uses_tmdb_only_and_sorts_tv_before_movie tests/test_following_controller.py::test_following_controller_non_tmdb_url_passthrough_still_works tests/test_following_controller.py::test_following_controller_douban_url_passthrough_still_works -q`

Expected: FAIL because `search_media()` currently fans keyword searches out through the default service path and does not reorder TMDB items to put TV ahead of movie.

- [ ] **Step 3: Write minimal implementation**

In `src/atv_player/controllers/following_controller.py`, update the search path to keep URL detection first, but force manual keyword searches to TMDB and sort TMDB items locally:

```python
    def search_media(self, keyword: str):
        url_candidate = self.candidate_from_url(keyword)
        if url_candidate is not None:
            from atv_player.metadata.scrape import MetadataScrapeGroup

            url_candidate = self._hydrate_url_candidate(url_candidate)
            return [
                MetadataScrapeGroup(
                    provider=url_candidate.provider,
                    provider_label=url_candidate.provider_label,
                    items=[url_candidate],
                )
            ]
        query = MetadataQuery(title=keyword.strip())
        groups = self._search_tmdb_following(query)
        return [self._sort_following_group_items(group) for group in groups]

    def _search_tmdb_following(self, query: MetadataQuery):
        search_following = getattr(self._metadata_search_service, "search_following", None)
        if callable(search_following):
            return search_following(query, provider_filter="tmdb")
        return self._metadata_search_service.search(query, provider_filter="tmdb")

    def _sort_following_group_items(self, group):
        items = list(getattr(group, "items", []) or [])
        if str(getattr(group, "provider", "") or "").strip() != "tmdb":
            return group
        items.sort(key=self._following_candidate_sort_key)
        return replace(group, items=items)

    def _following_candidate_sort_key(self, candidate) -> tuple[int, str]:
        provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
        if provider_id.startswith("tv:"):
            return (0, provider_id)
        if provider_id.startswith("movie:"):
            return (1, provider_id)
        return (2, provider_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_keyword_search_uses_tmdb_only_and_sorts_tv_before_movie tests/test_following_controller.py::test_following_controller_non_tmdb_url_passthrough_still_works tests/test_following_controller.py::test_following_controller_douban_url_passthrough_still_works -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_controller.py src/atv_player/controllers/following_controller.py
git commit -m "feat: limit following search to tmdb"
```

### Task 2: Add a Focused Following Search Result Card Widget

**Files:**
- Create: `src/atv_player/ui/following_search_result_card.py`
- Create: `tests/test_following_search_result_card.py`

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace

from atv_player.ui.following_search_result_card import (
    FollowingSearchResultCard,
    following_search_candidate_media_type,
)


def test_following_search_candidate_media_type_prefers_tv_and_movie_prefixes() -> None:
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="tv:76479:season:1")) == "电视"
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="movie:550")) == "电影"
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="subject:1")) == ""


def test_following_search_result_card_renders_rating_title_year_and_overview(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="tv:76479:season:1",
        title="The Boys",
        year="2019",
        raw={
            "poster": "https://img.test/poster.jpg",
            "rating": "8.7",
            "overview": "A long overview for the TV result.",
        },
    )

    card = FollowingSearchResultCard(candidate)
    qtbot.addWidget(card)

    assert card.title_label.text() == "The Boys"
    assert card.meta_label.text() == "2019 · 电视"
    assert card.rating_label.text() == "8.7"
    assert card.overview_label.text() == "A long overview for the TV result."


def test_following_search_result_card_uses_fallback_overview_and_hides_empty_rating(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="movie:12",
        title="Movie",
        year="2024",
        raw={},
    )

    card = FollowingSearchResultCard(candidate)
    qtbot.addWidget(card)

    assert card.overview_label.text() == "暂无简介"
    assert card.rating_label.isHidden() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_following_search_result_card.py -q`

Expected: FAIL with `ModuleNotFoundError` because the focused result-card widget file does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `src/atv_player/ui/following_search_result_card.py`:

```python
from __future__ import annotations

import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from atv_player.ui.poster_loader import load_local_poster_image, load_remote_poster_image, normalize_poster_url
from atv_player.ui.theme import current_tokens


def following_search_candidate_media_type(candidate) -> str:
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    if provider_id.startswith("tv:"):
        return "电视"
    if provider_id.startswith("movie:"):
        return "电影"
    return ""


class FollowingSearchResultCard(QFrame):
    image_loaded = Signal(object)

    def __init__(self, candidate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.poster_label = QLabel("封面", self)
        self.title_label = QLabel(str(getattr(candidate, "title", "") or "未命名条目"), self)
        self.rating_label = QLabel(self._rating_text(), self)
        self.meta_label = QLabel(self._meta_text(), self)
        self.overview_label = QLabel(self._overview_text(), self)
        self._build_ui()
        self.image_loaded.connect(self._handle_image_loaded)
        self._start_poster_load()

    def _build_ui(self) -> None:
        tokens = current_tokens()
        self.setObjectName("followingSearchResultCard")
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setFixedSize(92, 132)
        self.poster_label.setStyleSheet(
            f"background: {tokens.surface_alt}; border: 1px solid {tokens.border}; border-radius: 12px;"
        )
        self.overview_label.setWordWrap(True)
        self.overview_label.setProperty("clamped", True)
        self.rating_label.setHidden(not self.rating_label.text().strip())

        text_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.rating_label, 0, Qt.AlignmentFlag.AlignTop)
        text_layout.addLayout(title_row)
        text_layout.addWidget(self.meta_label)
        text_layout.addWidget(self.overview_label, 1)

        layout = QHBoxLayout(self)
        layout.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)

    def _poster_source(self) -> str:
        raw = dict(getattr(self.candidate, "raw", {}) or {})
        return str(raw.get("poster") or raw.get("poster_url") or "").strip()

    def _rating_text(self) -> str:
        raw = dict(getattr(self.candidate, "raw", {}) or {})
        return str(raw.get("rating") or "").strip()

    def _meta_text(self) -> str:
        year = str(getattr(self.candidate, "year", "") or "").strip()
        media_type = following_search_candidate_media_type(self.candidate)
        return " · ".join(part for part in (year, media_type) if part)

    def _overview_text(self) -> str:
        raw = dict(getattr(self.candidate, "raw", {}) or {})
        return str(raw.get("overview") or "").strip() or "暂无简介"

    def _start_poster_load(self) -> None:
        source = self._poster_source()
        if not source:
            return
        target_size = QSize(self.poster_label.width(), self.poster_label.height())

        def load() -> None:
            image = load_local_poster_image(source, target_size)
            if image is None:
                image = load_remote_poster_image(normalize_poster_url(source), target_size)
            if image is not None:
                self.image_loaded.emit(image)

        threading.Thread(target=load, daemon=True).start()

    def _handle_image_loaded(self, image) -> None:
        self.poster_label.setText("")
        self.poster_label.setPixmap(QPixmap.fromImage(image))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_following_search_result_card.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/following_search_result_card.py tests/test_following_search_result_card.py
git commit -m "feat: add following search result cards"
```

### Task 3: Replace Grouped Text Rows with a Single Card List

**Files:**
- Modify: `tests/test_following_search_dialog_ui.py`
- Modify: `src/atv_player/ui/following_search_dialog.py`
- Modify: `src/atv_player/ui/following_search_result_card.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_following_search_dialog_uses_single_result_column_without_group_list(qtbot) -> None:
    dialog = FollowingSearchDialog(object())
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "group_list") is False
    assert dialog.result_list is not None


def test_following_search_dialog_mounts_result_cards_and_keeps_add_behavior(qtbot) -> None:
    candidate = SimpleNamespace(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="tv:76479:season:1",
        title="The Boys",
        year="2019",
        raw={
            "poster": "poster",
            "rating": "8.7",
            "overview": "TV overview",
        },
    )

    class Controller:
        def __init__(self) -> None:
            self.added = []

        def search_media(self, keyword: str):
            assert keyword == "黑袍纠察队"
            return [
                SimpleNamespace(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[candidate],
                    error_text="",
                )
            ]

        def add_candidate(self, selected, *, current_episode: int = 0) -> None:
            self.added.append((selected, current_episode))

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)

    dialog.search_edit.setText("黑袍纠察队")
    dialog.run_search()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    widget = dialog.result_list.itemWidget(dialog.result_list.item(0))

    assert widget.title_label.text() == "The Boys"
    assert widget.meta_label.text() == "2019 · 电视"
    assert widget.overview_label.text() == "TV overview"

    dialog.result_list.setCurrentRow(0)
    dialog.current_episode_spin.setValue(9)
    dialog.add_button.click()

    qtbot.waitUntil(lambda: dialog.controller.added == [(candidate, 9)])


def test_following_search_dialog_renders_tmdb_url_candidate_card_details(qtbot, tmp_path) -> None:
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
    widget = dialog.result_list.itemWidget(dialog.result_list.item(0))

    assert widget.title_label.text() == "名侦探柯南"
    assert widget.meta_label.text() == "1996 · 电视"
    assert widget.rating_label.text() == "8.9"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_uses_single_result_column_without_group_list tests/test_following_search_dialog_ui.py::test_following_search_dialog_mounts_result_cards_and_keeps_add_behavior tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_card_details -q`

Expected: FAIL because the dialog still creates `group_list`, still renders plain text items, and does not attach custom card widgets.

- [ ] **Step 3: Write minimal implementation**

In `src/atv_player/ui/following_search_dialog.py`, remove the sidebar and populate `result_list` directly with card widgets:

```python
from atv_player.ui.following_search_result_card import FollowingSearchResultCard


class FollowingSearchDialog(ThemedDialogBase, AsyncGuardMixin):
    def __init__(self, controller, parent=None) -> None:
        ...
        columns = QHBoxLayout()
        self.result_list = QListWidget(host)
        columns.addWidget(self.result_list, 1)
        layout.addLayout(columns)
        ...

    def _render_groups(self, groups) -> None:
        self.groups = list(groups or [])
        self.result_list.clear()
        total = 0
        for group in self.groups:
            total += len(list(getattr(group, "items", []) or []))
        for candidate in self._flatten_candidates(self.groups):
            self._append_candidate_item(candidate)
        if self.result_list.count():
            self.result_list.setCurrentRow(0)
        self._sync_action_state()
        self.status_label.setText(f"找到 {total} 个结果" if total else "没有找到可加入追更的结果")

    def _flatten_candidates(self, groups):
        for group in groups:
            error_text = str(getattr(group, "error_text", "") or "").strip()
            if error_text:
                continue
            for candidate in list(getattr(group, "items", []) or []):
                yield candidate

    def _append_candidate_item(self, candidate) -> None:
        item = QListWidgetItem(self.result_list)
        item.setData(Qt.ItemDataRole.UserRole, candidate)
        card = FollowingSearchResultCard(candidate, self.result_list)
        item.setSizeHint(card.sizeHint())
        self.result_list.addItem(item)
        self.result_list.setItemWidget(item, card)
```

Add 3-line overview clamping and card-level selected/hover styling in `src/atv_player/ui/following_search_result_card.py`:

```python
        self.overview_label.setStyleSheet(
            """
            QLabel[clamped="true"] {
                min-height: 60px;
                max-height: 60px;
            }
            """
        )
```

Also remove the old group-list wiring:

```python
        self.result_list.currentRowChanged.connect(lambda _row: self._sync_action_state())
        self.result_list.itemDoubleClicked.connect(lambda _item: self._add_selected_candidate())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_uses_single_result_column_without_group_list tests/test_following_search_dialog_ui.py::test_following_search_dialog_mounts_result_cards_and_keeps_add_behavior tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_card_details -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_search_dialog_ui.py src/atv_player/ui/following_search_dialog.py src/atv_player/ui/following_search_result_card.py
git commit -m "feat: show following search results as cards"
```

### Task 4: Focused Regression Verification

**Files:**
- Test: `tests/test_following_controller.py`
- Test: `tests/test_following_search_result_card.py`
- Test: `tests/test_following_search_dialog_ui.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_keyword_search_uses_tmdb_only_and_sorts_tv_before_movie tests/test_following_controller.py::test_following_controller_non_tmdb_url_passthrough_still_works tests/test_following_controller.py::test_following_controller_douban_url_passthrough_still_works tests/test_following_search_result_card.py tests/test_following_search_dialog_ui.py::test_following_search_dialog_uses_single_result_column_without_group_list tests/test_following_search_dialog_ui.py::test_following_search_dialog_mounts_result_cards_and_keeps_add_behavior tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_card_details tests/test_following_search_dialog_ui.py::test_following_search_dialog_runs_search_off_main_thread tests/test_following_search_dialog_ui.py::test_following_search_dialog_adds_candidate_off_main_thread tests/test_following_search_dialog_ui.py::test_following_search_dialog_pressing_return_in_search_edit_runs_search_without_closing tests/test_following_search_dialog_ui.py::test_following_search_dialog_action_buttons_are_not_default_submit_targets -q`

Expected: PASS

- [ ] **Step 2: Run a broader following regression slice**

Run: `uv run pytest tests/test_following_controller.py tests/test_following_search_dialog_ui.py tests/test_following_detail_page_ui.py -q`

Expected: PASS

- [ ] **Step 3: Commit the verification checkpoint**

```bash
git add tests/test_following_controller.py tests/test_following_search_result_card.py tests/test_following_search_dialog_ui.py src/atv_player/controllers/following_controller.py src/atv_player/ui/following_search_dialog.py src/atv_player/ui/following_search_result_card.py
git commit -m "test: verify following tmdb-only search flow"
```
