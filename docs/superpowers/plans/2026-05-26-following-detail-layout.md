# Following Detail Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace following-detail episode display modes with a persistent 1/2/3-column layout, add a season header inside the episode area, narrow the season rail, shrink cast cards, and increase episode-section prominence.

**Architecture:** Keep the existing following data flow, season grouping, season loading, and episode preview behavior. Migrate config from a string display-mode preference to a numeric grid-column preference, then refit `FollowingEpisodeBrowser` around column-count state and a grid-oriented episode surface, and finally update `FollowingDetailPage` layout and tests to consume that new browser contract.

**Tech Stack:** Python 3.12, PySide6 widgets, pytest, pytest-qt, sqlite-backed `SettingsRepository`, existing poster-loading helpers.

---

## File Map

- Modify: `src/atv_player/models.py`
  - Replace the following-detail episode preference field on `AppConfig`.
- Modify: `src/atv_player/storage.py`
  - Add config column migration, normalization, load/save wiring, and legacy compatibility mapping.
- Modify: `src/atv_player/ui/following_episode_browser.py`
  - Remove mode tabs, add grid-column state, add season-header payload support, and replace the single-column episode list rendering contract.
- Modify: `src/atv_player/ui/following_detail_page.py`
  - Rebuild the episode section around a narrow season rail, season header, column switcher, taller episode area, and smaller cast rail.
- Modify: `tests/test_storage.py`
  - Replace display-mode persistence coverage with grid-column persistence coverage.
- Modify: `tests/test_following_episode_browser.py`
  - Replace display-mode behavior coverage with grid-column behavior coverage.
- Modify: `tests/test_following_detail_page_ui.py`
  - Replace mode-tab assertions with season-header/column-switch/layout assertions.

### Task 1: Migrate Config From Display Mode To Grid Columns

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
def test_settings_repository_persists_following_episode_grid_columns(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "config.db")
    config = repo.load_config()
    config.following_episode_grid_columns = 3

    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.following_episode_grid_columns == 3


def test_settings_repository_normalizes_invalid_following_episode_grid_columns(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "config.db")
    config = repo.load_config()
    config.following_episode_grid_columns = 99

    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.following_episode_grid_columns == 1
```

- [ ] **Step 2: Run the focused storage tests and verify RED**

Run: `uv run pytest tests/test_storage.py -k "following_episode_grid_columns" -q`

Expected: FAIL because `AppConfig` and `SettingsRepository` do not expose `following_episode_grid_columns`.

- [ ] **Step 3: Implement the config field, normalization, and persistence**

```python
# src/atv_player/models.py
@dataclass(slots=True)
class AppConfig:
    ...
    following_episode_grid_columns: int = 1


# src/atv_player/storage.py
def _normalize_following_episode_grid_columns(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 1
    return normalized if normalized in {1, 2, 3} else 1


def _grid_columns_from_legacy_mode(value: object) -> int:
    normalized = str(value or "").strip()
    if normalized == "full":
        return 1
    if normalized == "poster":
        return 1
    if normalized == "compact":
        return 2
    return 1
```

```python
# inside CREATE TABLE app_config
following_episode_display_mode TEXT NOT NULL DEFAULT 'poster',
following_episode_grid_columns INTEGER NOT NULL DEFAULT 1
```

```python
# inside migration block
if "following_episode_grid_columns" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN following_episode_grid_columns INTEGER NOT NULL DEFAULT 1"
    )
```

```python
# inside load_config()
following_episode_grid_columns = _normalize_following_episode_grid_columns(
    following_episode_grid_columns
    if following_episode_grid_columns is not None
    else _grid_columns_from_legacy_mode(following_episode_display_mode)
)
```

```python
# inside AppConfig(...) return
following_episode_grid_columns=following_episode_grid_columns,
```

```python
# inside save_config()
_normalize_following_episode_grid_columns(config.following_episode_grid_columns),
```

- [ ] **Step 4: Run storage tests and verify GREEN**

Run: `uv run pytest tests/test_storage.py -k "following_episode_grid_columns or following_episode_display_mode" -q`

Expected: PASS. Legacy display-mode tests should be removed or replaced in the same edit so the suite asserts only the new canonical field.

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist following episode grid columns"
```

### Task 2: Replace Browser Mode Tabs With Grid-Column State

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write failing browser tests for column state**

```python
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
```

- [ ] **Step 2: Run browser tests and verify RED**

Run: `uv run pytest tests/test_following_episode_browser.py -k "grid_columns" -q`

Expected: FAIL because `FollowingEpisodeBrowser` still requires `initial_display_mode`, still exposes mode tabs, and has no grid-column API.

- [ ] **Step 3: Refactor browser state from display mode to grid columns**

```python
class FollowingEpisodeBrowser(QWidget):
    episode_activated = Signal(object)
    grid_columns_changed = Signal(int)
    season_changed = Signal(int)

    def __init__(self, *, initial_grid_columns: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid_columns = self._normalize_grid_columns(initial_grid_columns)
        ...

    def grid_columns(self) -> int:
        return self._grid_columns

    def set_grid_columns(self, columns: int) -> None:
        normalized = self._normalize_grid_columns(columns)
        if normalized == self._grid_columns:
            return
        self._grid_columns = normalized
        self._relayout_episode_cards()
        self.grid_columns_changed.emit(normalized)

    @staticmethod
    def _normalize_grid_columns(columns: int) -> int:
        return columns if columns in {1, 2, 3} else 1
```

```python
# delete the QTabBar mode-tabs setup and mode-tab signal wiring
# keep season selection and episode activation wiring
```

```python
# any old EpisodeDisplayMode- or DISPLAY_MODE_ROLE-specific paths
# should be removed or collapsed into a single rich-card presentation path
```

- [ ] **Step 4: Run browser tests and verify GREEN**

Run: `uv run pytest tests/test_following_episode_browser.py -k "grid_columns or season" -q`

Expected: PASS. Existing season selection and watched-state tests should still pass after constructor and API updates are adjusted.

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "refactor: replace following episode mode tabs with grid columns"
```

### Task 3: Add Season Header Data And Grid Rendering To The Browser

**Files:**
- Modify: `tests/test_following_episode_browser.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Write failing tests for season header payload and rich-card density behavior**

```python
def test_following_episode_browser_exposes_selected_season_summary(qtbot) -> None:
    browser = FollowingEpisodeBrowser(initial_grid_columns=1)
    qtbot.addWidget(browser)
    groups = build_episode_season_groups(
        [FollowingEpisode(episode_number=1, season_number=2, title="S2E1", overview="剧情", still="still")],
        seasons=[FollowingSeason(season_number=2, title="第二季", overview="本季简介", poster="poster", episode_count=8)],
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
```

```python
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
```

- [ ] **Step 2: Run browser tests and verify RED**

Run: `uv run pytest tests/test_following_episode_browser.py -k "current_season_summary or keeps_episode_overview_in_multi_column_modes" -q`

Expected: FAIL because the browser does not yet build a season-summary object or render widget-based episode cards.

- [ ] **Step 3: Implement browser season-summary and grid-card rendering**

```python
@dataclass(frozen=True, slots=True)
class EpisodeSeasonSummary:
    season_number: int
    title: str
    overview: str
    poster: str
    air_date: str
    episode_count: int
```

```python
class FollowingEpisodeCard(QFrame):
    def __init__(self, episode: FollowingEpisode, *, overview_lines: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_label = QLabel(format_episode_title(episode), self)
        self.meta_label = QLabel(_episode_meta_text(episode), self)
        self.overview_label = QLabel(episode.overview or "", self)
        self.overview_label.setWordWrap(True)
        self.overview_label.setProperty("overview_lines", overview_lines)
        ...
```

```python
class FollowingEpisodeBrowser(QWidget):
    def current_season_summary(self) -> EpisodeSeasonSummary:
        return self._current_season_summary

    def _apply_group(self, group: EpisodeSeasonGroup, *, restore_state: bool) -> None:
        ...
        self._current_season_summary = self._build_season_summary(group)
        self._rebuild_episode_cards(group.episodes)
```

```python
def _overview_lines_for_columns(columns: int) -> int:
    if columns == 1:
        return 5
    if columns == 2:
        return 3
    return 2
```

```python
def _rebuild_episode_cards(self, episodes: list[FollowingEpisode]) -> None:
    _clear_layout(self._episode_grid_layout)
    self.episode_cards = []
    for index, episode in enumerate(episodes):
        card = FollowingEpisodeCard(
            episode,
            overview_lines=_overview_lines_for_columns(self._grid_columns),
            parent=self._episode_grid_container,
        )
        row = index // self._grid_columns
        column = index % self._grid_columns
        self._episode_grid_layout.addWidget(card, row, column)
        self.episode_cards.append(card)
```

- [ ] **Step 4: Run browser tests and verify GREEN**

Run: `uv run pytest tests/test_following_episode_browser.py -q`

Expected: PASS. The browser test file should now fully cover season selection, watched-state behavior, season summaries, and grid-column rendering.

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_episode_browser.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: add following episode season header and grid cards"
```

### Task 4: Update Following Detail Page Tests For The New Layout Contract

**Files:**
- Modify: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write failing detail-page tests for the new layout**

```python
def test_following_detail_page_uses_single_column_episode_layout_by_default(qtbot) -> None:
    page = FollowingDetailPage(
        FakeController(),
        config=AppConfig(following_episode_grid_columns=1),
    )
    qtbot.addWidget(page)
    page.load_record(1)

    assert page.episode_browser.grid_columns() == 1
    assert page.episode_column_buttons[1].isChecked() is True
```

```python
def test_following_detail_page_switches_and_persists_episode_grid_columns(qtbot) -> None:
    config = AppConfig(following_episode_grid_columns=1)
    saved: list[int] = []

    def save_config() -> None:
        saved.append(config.following_episode_grid_columns)

    page = FollowingDetailPage(FakeController(), config=config, save_config=save_config)
    qtbot.addWidget(page)
    page.load_record(1)

    page.episode_column_buttons[3].click()

    assert config.following_episode_grid_columns == 3
    assert saved == [3]
```

```python
def test_following_detail_page_renders_selected_season_header(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    assert page.season_header_title_label.text() == "第一季"
    assert "长篇简介" in page.season_header_overview_label.text()
```

```python
def test_following_detail_page_uses_smaller_cast_cards_and_taller_episode_section(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    card = page.cast_widgets[0]
    assert card.avatar_label.width() < 144
    assert card.minimumHeight() < 292
    assert page.episodes_section.minimumHeight() > 400
    assert page.cast_scroll.maximumHeight() < 360
```

- [ ] **Step 2: Run focused detail-page tests and verify RED**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "grid_columns or season_header or smaller_cast_cards" -q`

Expected: FAIL because the detail page still expects `following_episode_display_mode`, exposes no column buttons, and has no season-header widgets.

- [ ] **Step 3: Replace old mode-tab assertions with new layout assertions**

```python
def test_following_detail_page_uses_top_split_and_two_bottom_rows(qtbot) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.top_section.objectName() == "followingDetailTopSection"
    assert page.episodes_section.objectName() == "followingDetailEpisodesSection"
    assert page.episode_browser.grid_columns() == 1
    assert hasattr(page, "season_header_title_label")
    assert len(page.episode_column_buttons) == 3
```

```python
# remove or rewrite tests that assert:
# - page.episode_browser.mode_tabs.count() == 3
# - AppConfig(following_episode_display_mode=...)
# - page.episode_browser.display_mode() == ...
```

- [ ] **Step 4: Run the full detail-page UI file and verify GREEN**

Run: `uv run pytest tests/test_following_detail_page_ui.py -q`

Expected: PASS. Existing manual-check, metadata refresh, season loading, and episode-preview tests should stay green after the constructor/config API updates.

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_detail_page_ui.py
git commit -m "test: cover following detail season header and grid layout"
```

### Task 5: Implement The New Following Detail Page Layout

**Files:**
- Modify: `src/atv_player/ui/following_detail_page.py`
- Modify: `src/atv_player/ui/following_episode_browser.py`

- [ ] **Step 1: Run the focused failing detail-page tests before implementing**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "grid_columns or season_header or smaller_cast_cards" -q`

Expected: FAIL with missing column-button, season-header, and sizing assertions.

- [ ] **Step 2: Rebuild the detail-page episode section around season header + column controls**

```python
self.episode_browser = FollowingEpisodeBrowser(
    initial_grid_columns=self._config.following_episode_grid_columns,
    parent=self,
)

self.season_header_poster_label = QLabel("季封面")
self.season_header_title_label = QLabel()
self.season_header_meta_label = QLabel()
self.season_header_overview_label = QLabel()

self.episode_column_buttons = {
    1: self._create_episode_column_button("1", "单列"),
    2: self._create_episode_column_button("2", "双列"),
    3: self._create_episode_column_button("3", "三列"),
}
```

```python
season_header_layout = QHBoxLayout()
season_header_layout.addWidget(self.season_header_poster_label)

season_text_layout = QVBoxLayout()
season_text_layout.addWidget(self.season_header_title_label)
season_text_layout.addWidget(self.season_header_meta_label)
season_text_layout.addWidget(self.season_header_overview_label)
season_header_layout.addLayout(season_text_layout, 1)

column_button_layout = QHBoxLayout()
column_button_layout.addStretch(1)
for columns in (1, 2, 3):
    column_button_layout.addWidget(self.episode_column_buttons[columns])
season_text_layout.addLayout(column_button_layout)
```

```python
browser_layout = QHBoxLayout(self.episodes_section)
browser_layout.addWidget(self.episode_browser.season_list, 0)
browser_layout.addWidget(self._episode_right_panel, 1)
```

- [ ] **Step 3: Wire season-header refresh, config persistence, and smaller/taller sizing**

```python
def _refresh_season_header(self) -> None:
    summary = self.episode_browser.current_season_summary()
    self.season_header_title_label.setText(summary.title or "未命名季")
    self.season_header_meta_label.setText(_season_header_meta_text(summary, self.current_view.record))
    self.season_header_overview_label.setText(summary.overview or self.current_view.snapshot.overview or "暂无本季简介")
    poster_source = summary.poster or self.current_view.record.poster
    self._start_image_load(self.season_header_poster_label, poster_source)
```

```python
def _handle_episode_grid_columns_changed(self, columns: int) -> None:
    if self._config.following_episode_grid_columns == columns:
        return
    self._config.following_episode_grid_columns = columns
    self._sync_episode_column_buttons(columns)
    if callable(self._save_config):
        self._save_config()
```

```python
self.episodes_section.setMinimumHeight(480)
self.cast_scroll.setMinimumHeight(250)
self.cast_scroll.setMaximumHeight(300)
```

```python
# FollowingPersonCard
self.setMinimumSize(142, 248)
self.avatar_label.setFixedSize(120, 180)
layout.setContentsMargins(8, 8, 8, 8)
layout.setSpacing(6)
```

- [ ] **Step 4: Run the focused and aggregate verification commands**

Run: `uv run pytest tests/test_following_detail_page_ui.py tests/test_following_episode_browser.py tests/test_storage.py -q`

Expected: PASS.

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "preview or manual_check or metadata_refresh or season" -q`

Expected: PASS, confirming the new layout did not break existing detail-page behavior.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/following_detail_page.py src/atv_player/ui/following_episode_browser.py
git commit -m "feat: redesign following detail episode layout"
```

## Self-Review

- Spec coverage:
  - remove mode tabs: Task 2 and Task 4
  - add persistent 1/2/3 columns: Tasks 1, 2, 4, 5
  - add season header with poster/overview: Tasks 3, 4, 5
  - narrow season rail / taller episode area / smaller cast cards: Tasks 4 and 5
  - preserve episode preview and season loading behavior: Tasks 2, 3, 4, 5
- Placeholder scan:
  - no `TODO`, `TBD`, “appropriate handling”, or “similar to above” placeholders remain
- Type consistency:
  - canonical config field: `following_episode_grid_columns`
  - canonical browser signal/API: `grid_columns_changed`, `grid_columns()`, `set_grid_columns()`
  - canonical season header accessor: `current_season_summary()`

## Verification Commands

- `uv run pytest tests/test_storage.py -k "following_episode_grid_columns" -q`
- `uv run pytest tests/test_following_episode_browser.py -q`
- `uv run pytest tests/test_following_detail_page_ui.py -q`
- `uv run pytest tests/test_following_detail_page_ui.py tests/test_following_episode_browser.py tests/test_storage.py -q`
