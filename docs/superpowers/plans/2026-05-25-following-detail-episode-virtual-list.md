# Following Detail Episode Virtual List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the following-detail episode card strip with a season-aware virtual list that supports 23-season shows, 1200-episode single seasons, and compact/poster/full display modes without creating per-episode widgets.

**Architecture:** Keep `FollowingDetailPage` as the page shell for metadata, backdrop, actions, and cast, but move episode browsing into a focused `following_episode_browser.py` unit. Persist the selected episode display mode through `AppConfig` and `SettingsRepository`, and use `QListView + QAbstractListModel + QStyledItemDelegate` so episode rows are painted virtually and can switch density without rebuilding the page.

**Tech Stack:** Python, PySide6 model/view, existing `AppConfig` + SQLite settings persistence, pytest-qt, existing poster loader helpers.

---

## File Structure

- Create: `src/atv_player/ui/following_episode_browser.py`
  - Owns episode display modes, season grouping helpers, season list model, episode list model, thumbnail cache/loader bridge, delegate, and a small composite browser widget that emits episode activation.
- Create: `tests/test_following_episode_browser.py`
  - Unit-tests season grouping, mode switching state, row data shaping, and thumbnail-refresh plumbing without needing the whole detail page.
- Modify: `src/atv_player/models.py`
  - Add the persisted following-episode display mode field to `AppConfig`.
- Modify: `src/atv_player/storage.py`
  - Add schema default, migration, normalization, load, and save support for the new config field.
- Modify: `tests/test_storage.py`
  - Add round-trip and normalization coverage for the new config field.
- Modify: `src/atv_player/ui/following_detail_page.py`
  - Remove the legacy episode card batch-render path and embed the new browser widget while keeping preview dialog, cast cards, top metadata panel, and action wiring intact.
- Modify: `src/atv_player/ui/main_window.py`
  - Pass `config` and `_save_config` into `FollowingDetailPage` so the page can persist display-mode changes through the existing settings flow.
- Modify: `tests/test_following_detail_page_ui.py`
  - Replace card-strip assertions with season navigation, mode switcher, activation, and state-restoration assertions.

## Task 1: Persist Episode Display Mode

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing settings tests**

```python
def test_settings_repository_persists_following_episode_display_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.following_episode_display_mode = "full"

    repo.save_config(config)
    loaded = SettingsRepository(tmp_path / "app.db").load_config()

    assert loaded.following_episode_display_mode == "full"


def test_settings_repository_normalizes_invalid_following_episode_display_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.following_episode_display_mode = "giant-cards"

    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.following_episode_display_mode == "poster"
```

- [ ] **Step 2: Run the targeted storage tests to confirm failure**

Run: `uv run pytest tests/test_storage.py -k "following_episode_display_mode" -q`

Expected: FAIL with `AttributeError` on `following_episode_display_mode` or missing-column assertions.

- [ ] **Step 3: Add the config field, normalization, migration, and round-trip support**

```python
# src/atv_player/models.py
@dataclass(slots=True)
class AppConfig:
    global_search_history: list[str] = field(default_factory=list)
    global_search_hot_source: str = "360"
    following_episode_display_mode: str = "poster"
```

```python
# src/atv_player/storage.py
_VALID_FOLLOWING_EPISODE_DISPLAY_MODES = {"compact", "poster", "full"}


def _normalize_following_episode_display_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_FOLLOWING_EPISODE_DISPLAY_MODES else "poster"
```

```python
# src/atv_player/storage.py inside CREATE TABLE app_config
following_episode_display_mode TEXT NOT NULL DEFAULT 'poster',
```

```python
# src/atv_player/storage.py inside migration block
if "following_episode_display_mode" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN following_episode_display_mode TEXT NOT NULL DEFAULT 'poster'"
    )
```

```python
# src/atv_player/storage.py inside load_config()
following_episode_display_mode=_normalize_following_episode_display_mode(
    following_episode_display_mode
),
```

```python
# src/atv_player/storage.py inside save_config()
str(_normalize_following_episode_display_mode(config.following_episode_display_mode)),
```

- [ ] **Step 4: Re-run the storage tests**

Run: `uv run pytest tests/test_storage.py -k "following_episode_display_mode" -q`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist following episode display mode"
```

## Task 2: Add Season Grouping and Episode Browser Models

**Files:**
- Create: `src/atv_player/ui/following_episode_browser.py`
- Create: `tests/test_following_episode_browser.py`

- [ ] **Step 1: Write the failing browser unit tests**

```python
from atv_player.following_models import FollowingEpisode
from atv_player.ui.following_episode_browser import (
    EpisodeListModel,
    EpisodeDisplayMode,
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


def test_episode_list_model_replaces_rows_for_current_season(qtbot) -> None:
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
```

- [ ] **Step 2: Run the new browser tests to verify failure**

Run: `uv run pytest tests/test_following_episode_browser.py -q`

Expected: FAIL with `ModuleNotFoundError` for `following_episode_browser` or missing attributes.

- [ ] **Step 3: Create the browser module with grouping types and models**

```python
# src/atv_player/ui/following_episode_browser.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from atv_player.following_models import FollowingEpisode


class EpisodeDisplayMode:
    COMPACT = "compact"
    POSTER = "poster"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class EpisodeSeasonGroup:
    season_number: int
    display_title: str
    episodes: list[FollowingEpisode]

    @property
    def episode_count(self) -> int:
        return len(self.episodes)


def build_episode_season_groups(
    episodes: list[FollowingEpisode],
    *,
    fallback_season: int,
) -> list[EpisodeSeasonGroup]:
    buckets: dict[int, list[FollowingEpisode]] = {}
    fallback = fallback_season if fallback_season > 0 else 1
    for episode in episodes:
        season_number = episode.season_number if episode.season_number > 0 else fallback
        buckets.setdefault(season_number, []).append(episode)
    if not buckets:
        buckets[fallback] = []
    return [
        EpisodeSeasonGroup(
            season_number=season_number,
            display_title=f"第 {season_number} 季",
            episodes=sorted(items, key=lambda item: item.episode_number),
        )
        for season_number, items in sorted(buckets.items())
    ]


class EpisodeListModel(QAbstractListModel):
    def __init__(self, *, display_mode: str = EpisodeDisplayMode.POSTER, parent=None) -> None:
        super().__init__(parent)
        self._episodes: list[FollowingEpisode] = []
        self._current_episode = 0
        self.display_mode = display_mode

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._episodes)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        episode = self._episodes[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            title = episode.title.strip() or f"第 {episode.episode_number} 集"
            return f"{episode.episode_number}. {title}"
        if role == Qt.ItemDataRole.UserRole:
            return episode
        if role == Qt.ItemDataRole.UserRole + 1:
            return episode.episode_number <= self._current_episode
        return None

    def set_episodes(self, episodes: list[FollowingEpisode], *, current_episode: int) -> None:
        self.beginResetModel()
        self._episodes = list(episodes)
        self._current_episode = max(0, current_episode)
        self.endResetModel()

    def set_display_mode(self, display_mode: str) -> None:
        if self.display_mode == display_mode:
            return
        self.display_mode = display_mode
        if self.rowCount():
            top = self.index(0, 0)
            bottom = self.index(self.rowCount() - 1, 0)
            self.dataChanged.emit(top, bottom)


class SeasonListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups: list[EpisodeSeasonGroup] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._groups)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        group = self._groups[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{group.display_title} · {group.episode_count} 集"
        if role == Qt.ItemDataRole.UserRole:
            return group
        return None

    def set_groups(self, groups: list[EpisodeSeasonGroup]) -> None:
        self.beginResetModel()
        self._groups = list(groups)
        self.endResetModel()
```

- [ ] **Step 4: Re-run the browser tests**

Run: `uv run pytest tests/test_following_episode_browser.py -q`

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit the browser-model slice**

```bash
git add src/atv_player/ui/following_episode_browser.py tests/test_following_episode_browser.py
git commit -m "feat: add following episode browser models"
```

## Task 3: Embed the Browser in FollowingDetailPage

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing page-layout and season-navigation tests**

```python
def test_following_detail_page_uses_two_column_episode_browser(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.episodes_section.objectName() == "followingDetailEpisodesSection"
    assert page.episode_browser.mode_tabs.count() == 3
    assert page.episode_browser.season_list.model().rowCount() == 1
    assert page.episode_browser.episode_list.model().rowCount() == 1


def test_following_detail_page_groups_multiple_seasons_and_switches_current_season(qtbot) -> None:
    class MultiSeasonController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.snapshot.episodes = [
                FollowingEpisode(episode_number=1, season_number=1, title="S1E1"),
                FollowingEpisode(episode_number=2, season_number=1, title="S1E2"),
                FollowingEpisode(episode_number=1, season_number=2, title="S2E1"),
            ]
            return view

    page = FollowingDetailPage(MultiSeasonController())
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    episode_model = page.episode_browser.episode_list.model()
    assert season_model.rowCount() == 2
    assert episode_model.rowCount() == 2

    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert episode_model.rowCount() == 1
    assert "S2E1" in episode_model.data(episode_model.index(0, 0), Qt.ItemDataRole.DisplayRole)


def test_following_detail_page_uses_configured_initial_display_mode(qtbot) -> None:
    config = AppConfig(following_episode_display_mode="full")
    page = FollowingDetailPage(FakeController(), config=config)
    qtbot.addWidget(page)
    page.load_record(1)

    assert page.episode_browser.display_mode() == "full"
```

- [ ] **Step 2: Run the following-detail tests to confirm failure**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "episode_browser or multiple_seasons" -q`

Expected: FAIL because `episode_browser` does not exist and `MainWindow` still constructs `FollowingDetailPage` with only the controller.

- [ ] **Step 3: Add a focused browser widget and replace the old strip wiring**

```python
# src/atv_player/ui/following_episode_browser.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListView, QHBoxLayout, QTabBar, QVBoxLayout, QWidget


class FollowingEpisodeBrowser(QWidget):
    episode_activated = Signal(object)
    display_mode_changed = Signal(str)

    def __init__(self, *, initial_display_mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode_tabs = QTabBar(self)
        self.mode_tabs.addTab("简洁")
        self.mode_tabs.addTab("封面")
        self.mode_tabs.addTab("完整")
        self.season_list = QListView(self)
        self.episode_list = QListView(self)
        self.season_model = SeasonListModel(self)
        self.episode_model = EpisodeListModel(display_mode=initial_display_mode, parent=self)
        self.season_list.setModel(self.season_model)
        self.episode_list.setModel(self.episode_model)
        self.mode_tabs.currentChanged.connect(self._handle_mode_tab_changed)
        self.season_list.clicked.connect(self._handle_season_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        body = QHBoxLayout()
        body.addWidget(self.season_list, 1)
        body.addWidget(self.episode_list, 4)
        layout.addWidget(self.mode_tabs)
        layout.addLayout(body)

    def set_content(self, *, groups: list[EpisodeSeasonGroup], current_episode: int) -> None:
        self.season_model.set_groups(groups)
        current_group = groups[0] if groups else EpisodeSeasonGroup(1, "第 1 季", [])
        self.episode_model.set_episodes(current_group.episodes, current_episode=current_episode)
```

```python
# src/atv_player/ui/following_detail_page.py
class FollowingDetailPage(QWidget, AsyncGuardMixin):
    def __init__(self, controller, *, config: AppConfig | None = None, save_config=None) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self._config = config or AppConfig()
        self._save_config = save_config
        self.episode_browser = FollowingEpisodeBrowser(
            initial_display_mode=self._config.following_episode_display_mode,
            parent=self,
        )
        self.episode_browser.episode_activated.connect(self._open_episode_preview)
        self.episode_browser.display_mode_changed.connect(self._handle_episode_display_mode_changed)
```

```python
# src/atv_player/ui/following_detail_page.py inside _render()
groups = build_episode_season_groups(snapshot.episodes, fallback_season=record.season_number)
self.episode_browser.set_content(
    groups=groups,
    current_episode=record.current_episode,
)
```

```python
# src/atv_player/ui/main_window.py
self.following_detail_page = FollowingDetailPage(
    self._following_controller,
    config=self.config,
    save_config=self._save_config,
)
```

- [ ] **Step 4: Re-run the updated page tests**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "episode_browser or multiple_seasons" -q`

Expected: PASS with the new browser layout tests green.

- [ ] **Step 5: Commit the page-shell integration**

```bash
git add src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py src/atv_player/ui/main_window.py tests/test_following_detail_page_ui.py
git commit -m "feat: embed season-aware episode browser"
```

## Task 4: Add Delegate Rendering, Poster/Full Modes, and Mode Persistence

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_episode_browser.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing mode-switch and thumbnail-refresh tests**

```python
def test_episode_list_model_emits_data_changed_when_display_mode_changes(qtbot) -> None:
    model = EpisodeListModel(display_mode=EpisodeDisplayMode.COMPACT)
    model.set_episodes([FollowingEpisode(episode_number=1, title="第一集")], current_episode=0)
    changed = []
    model.dataChanged.connect(lambda top, bottom, roles=None: changed.append((top.row(), bottom.row())))

    model.set_display_mode(EpisodeDisplayMode.FULL)

    assert model.display_mode == EpisodeDisplayMode.FULL
    assert changed == [(0, 0)]


def test_following_detail_page_switches_and_persists_episode_display_mode(qtbot) -> None:
    config = AppConfig(following_episode_display_mode="poster")
    saved: list[str] = []

    def save_config() -> None:
        saved.append(config.following_episode_display_mode)

    page = FollowingDetailPage(FakeController(), config=config, save_config=save_config)
    qtbot.addWidget(page)
    page.load_record(1)

    page.episode_browser.set_display_mode("full")

    assert config.following_episode_display_mode == "full"
    assert saved == ["full"]


def test_episode_thumbnail_store_refreshes_only_matching_rows(qtbot) -> None:
    store = EpisodeThumbnailStore()
    model = EpisodeListModel()
    model.set_episodes(
        [
            FollowingEpisode(episode_number=1, title="第一集", still="same"),
            FollowingEpisode(episode_number=2, title="第二集", still="other"),
        ],
        current_episode=0,
    )
    changed = []
    model.dataChanged.connect(lambda top, bottom, roles=None: changed.append((top.row(), bottom.row())))

    model.attach_thumbnail_store(store)
    store._handle_thumbnail_ready("same", object())

    assert changed == [(0, 0)]
```

- [ ] **Step 2: Run the browser and page tests to confirm failure**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -k "display_mode or thumbnail" -q`

Expected: FAIL because display-mode persistence and thumbnail refresh plumbing are not implemented yet.

- [ ] **Step 3: Add the delegate, thumbnail store, and persisted mode change path**

```python
# src/atv_player/ui/following_episode_browser.py
class EpisodeThumbnailStore(QObject):
    thumbnail_ready = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cache: dict[str, object] = {}

    def image_for(self, source: str):
        return self._cache.get(str(source or "").strip())

    def _handle_thumbnail_ready(self, source: str, image) -> None:
        key = str(source or "").strip()
        if not key:
            return
        self._cache[key] = image
        self.thumbnail_ready.emit(key)
```

```python
# src/atv_player/ui/following_episode_browser.py
class EpisodeItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        mode = index.data(Qt.ItemDataRole.UserRole + 3)
        if mode == EpisodeDisplayMode.COMPACT:
            return QSize(option.rect.width(), 58)
        if mode == EpisodeDisplayMode.POSTER:
            return QSize(option.rect.width(), 84)
        return QSize(option.rect.width(), 118)


class EpisodeListModel(QAbstractListModel):
    def __init__(self, *, display_mode: str = EpisodeDisplayMode.POSTER, parent=None) -> None:
        super().__init__(parent)
        self._episodes: list[FollowingEpisode] = []
        self._current_episode = 0
        self._thumbnail_store: EpisodeThumbnailStore | None = None
        self.display_mode = display_mode

    def attach_thumbnail_store(self, store: EpisodeThumbnailStore) -> None:
        self._thumbnail_store = store
        store.thumbnail_ready.connect(self._handle_thumbnail_ready)

    def _handle_thumbnail_ready(self, source: str) -> None:
        matches = [
            row for row, episode in enumerate(self._episodes)
            if str(episode.still or "").strip() == source
        ]
        for row in matches:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
```

```python
# src/atv_player/ui/following_detail_page.py
def _handle_episode_display_mode_changed(self, display_mode: str) -> None:
    normalized = str(display_mode or "").strip() or "poster"
    if self._config.following_episode_display_mode == normalized:
        return
    self._config.following_episode_display_mode = normalized
    if callable(self._save_config):
        self._save_config()
```

- [ ] **Step 4: Re-run the mode-switch and thumbnail tests**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -k "display_mode or thumbnail" -q`

Expected: PASS with mode persistence and targeted row refreshes green.

- [ ] **Step 5: Commit the rendering slice**

```bash
git add src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py
git commit -m "feat: add episode browser display modes"
```

## Task 5: Add Activation, Current-Episode Positioning, Per-Season State Restore, and Remove Legacy Episode Cards

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_episode_browser.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing activation and state-restore tests**

```python
def test_following_detail_page_opens_preview_dialog_from_episode_activation(qtbot, monkeypatch) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)
    opened: list[int] = []

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        lambda self_dialog: opened.append(self_dialog.episode.episode_number) or 1,
    )

    model = page.episode_browser.episode_list.model()
    page.episode_browser._handle_episode_activated(model.index(0, 0))

    assert opened == [128]


def test_following_detail_page_restores_selection_when_switching_back_to_a_season(qtbot) -> None:
    page = FollowingDetailPage(MultiSeasonController())
    qtbot.addWidget(page)
    page.load_record(1)

    season_model = page.episode_browser.season_list.model()
    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))
    page.episode_browser.episode_list.setCurrentIndex(page.episode_browser.episode_list.model().index(0, 0))
    page.episode_browser.season_list.setCurrentIndex(season_model.index(0, 0))
    page.episode_browser.season_list.setCurrentIndex(season_model.index(1, 0))

    assert page.episode_browser.episode_list.currentIndex().row() == 0


def test_following_detail_page_no_longer_uses_following_episode_card_widgets(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    assert not hasattr(page, "_episodes_container")
    assert not hasattr(page, "_batch_timer")
```

- [ ] **Step 2: Run the activation and cleanup tests to confirm failure**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "preview_dialog or restores_selection or no_longer_uses_following_episode_card" -q`

Expected: FAIL because activation routing, season-state restoration, and legacy member removal are not finished.

- [ ] **Step 3: Finish browser state handling and delete the old card-strip path**

```python
# src/atv_player/ui/following_episode_browser.py
class FollowingEpisodeBrowser(QWidget):
    def __init__(self, *, initial_display_mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._season_state: dict[int, tuple[int, int]] = {}
        self.episode_list.activated.connect(self._handle_episode_activated)
        self.episode_list.doubleClicked.connect(self._handle_episode_activated)

    def _remember_current_season_state(self) -> None:
        season_number = self.current_season_number()
        current_row = self.episode_list.currentIndex().row()
        scroll_value = self.episode_list.verticalScrollBar().value()
        self._season_state[season_number] = (current_row, scroll_value)

    def _restore_current_season_state(self) -> None:
        season_number = self.current_season_number()
        current_row, scroll_value = self._season_state.get(season_number, (-1, 0))
        if current_row >= 0:
            self.episode_list.setCurrentIndex(self.episode_model.index(current_row, 0))
        self.episode_list.verticalScrollBar().setValue(scroll_value)

    def scroll_to_episode(self, episode_number: int) -> None:
        row = self.episode_model.row_for_episode_number(episode_number)
        if row >= 0:
            self.episode_list.scrollTo(self.episode_model.index(row, 0), QListView.ScrollHint.PositionAtCenter)

    def _handle_episode_activated(self, index: QModelIndex) -> None:
        episode = index.data(Qt.ItemDataRole.UserRole)
        if episode is not None:
            self.episode_activated.emit(episode)
```

```python
# src/atv_player/ui/following_detail_page.py
def _open_episode_preview(self, episode: FollowingEpisode) -> None:
    FollowingEpisodePreviewDialog(episode, self).exec()
```

```python
# src/atv_player/ui/following_detail_page.py
# Delete:
# - class FollowingEpisodeCard
# - self.episode_widgets
# - self._pending_episodes
# - self._batch_timer
# - self._episodes_container / self._episodes_layout
# - self._render_next_batch()
# - legacy season_tabs widget path
```

- [ ] **Step 4: Run the focused suite, then the full following-detail suite**

Run: `uv run pytest tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -q`

Expected: PASS with all browser and following-detail tests green.

- [ ] **Step 5: Commit the final slice**

```bash
git add src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py
git commit -m "feat: virtualize following detail episode list"
```

## Final Verification

- [ ] Run the full targeted verification set

Run: `uv run pytest tests/test_storage.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py -q`

Expected: PASS with all storage, browser, and following-detail tests green.

- [ ] Smoke-check the page manually after tests

Run:

```bash
uv run pytest tests/test_following_detail_page_ui.py -k "renders_reference_layout_and_actions or groups_multiple_seasons_and_switches_current_season" -v
```

Expected:

- existing top metadata, cast, and action tests still pass
- multi-season switching works
- no assertion references remain for `FollowingEpisodeCard`
