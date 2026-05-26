# Following Episode Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-episode `已看 / 已更新 / 即将更新 / 未更新` states to the following detail page, show the same state in the episode preview dialog, and let the preview dialog mark the current episode as watched.

**Architecture:** Keep TMDB payload parsing and schedule awareness in `following_metadata.py`, keep the symbolic episode-state resolver in `following_models.py`, and make `following_episode_browser.py` and `following_detail_page.py` consume that symbolic state instead of re-deriving status in widgets. Reuse the existing `record_playback_progress(...)` path so the preview dialog action and the existing progress dialog update the same persistence flow.

**Tech Stack:** Python 3, PySide6, pytest, qtbot, uv

---

### Task 1: Capture `next_episode_to_air` In Following Snapshots

**Files:**
- Modify: `src/atv_player/following_models.py`
- Modify: `src/atv_player/following_metadata.py`
- Modify: `src/atv_player/metadata/providers/tmdb.py`
- Test: `tests/test_following_metadata.py`

- [ ] **Step 1: Write the failing metadata test**

Add this test near the existing `last_episode_to_air` coverage in `tests/test_following_metadata.py`:

```python
def test_build_snapshot_from_record_keeps_next_episode_to_air_as_typed_episode() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:233295:season:1",
        title="仙剑奇侠传叁",
        tmdb_id="233295",
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 23, "season_number": 1, "name": "第 23 集"},
                ],
            },
            {
                "label": "next_episode_to_air",
                "value": {
                    "episode_number": 24,
                    "season_number": 1,
                    "name": "第 24 集",
                    "air_date": "2026-05-26",
                    "overview": "",
                    "runtime": None,
                    "still_path": None,
                },
            },
        ],
    )

    _following, snapshot = build_snapshot_from_record(record, now=300, media_kind="live_action")

    assert snapshot.next_episode is not None
    assert snapshot.next_episode.season_number == 1
    assert snapshot.next_episode.episode_number == 24
    assert snapshot.next_episode.title == "第 24 集"
    assert snapshot.next_episode.air_date == "2026-05-26"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_following_metadata.py::test_build_snapshot_from_record_keeps_next_episode_to_air_as_typed_episode -v`

Expected: FAIL with `AttributeError` or an assertion failure because `FollowingDetailSnapshot` does not expose `next_episode` yet.

- [ ] **Step 3: Add the typed snapshot field and parsing helper**

Update `src/atv_player/following_models.py` so the snapshot can carry the typed scheduled episode:

```python
@dataclass(slots=True)
class FollowingDetailSnapshot:
    following_id: int = 0
    overview: str = ""
    metadata_fields: list[dict[str, str]] = field(default_factory=list)
    cast: list[dict[str, object]] = field(default_factory=list)
    crew: list[dict[str, object]] = field(default_factory=list)
    seasons: list[FollowingSeason] = field(default_factory=list)
    episodes: list[FollowingEpisode] = field(default_factory=list)
    next_episode: FollowingEpisode | None = None
    posters: list[str] = field(default_factory=list)
    backdrops: list[str] = field(default_factory=list)
    refreshed_at: int = 0
```

Add the parsing helper and thread it through `src/atv_player/following_metadata.py`:

```python
def _next_episode_to_air_from_detail_fields(
    detail_fields: list[dict[str, object]],
) -> FollowingEpisode | None:
    for field in detail_fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("label") or "").strip() != "next_episode_to_air":
            continue
        value = field.get("value")
        if not isinstance(value, dict):
            continue
        episode = _episode_from_raw(value)
        return episode if episode.episode_number > 0 else None
    return None
```

Then update `build_snapshot_from_record(...)`, `build_following_from_candidate(...)`, and `merge_following_snapshot(...)` to preserve the typed field:

```python
next_episode = _next_episode_to_air_from_detail_fields(detail_fields)

snapshot = FollowingDetailSnapshot(
    overview=str(getattr(record, "overview", "") or "").strip(),
    metadata_fields=_metadata_fields_from_record(record),
    cast=_people_details(
        list(getattr(record, "cast_details", []) or []),
        list(getattr(record, "actors", []) or []),
    ),
    crew=_people_details(
        list(getattr(record, "crew_details", []) or []),
        list(getattr(record, "directors", []) or []),
        fallback_job="Director",
    ),
    seasons=[_season_from_raw(item) for item in raw_seasons],
    episodes=[_episode_from_raw(item) for item in raw_episodes],
    next_episode=next_episode,
    posters=[following.poster] if following.poster else [],
    backdrops=list(getattr(record, "backdrops", []) or [])
    or ([following.backdrop] if following.backdrop else []),
    refreshed_at=now,
)
```

```python
return replace(
    snapshot,
    overview=detail.overview or snapshot.overview,
    metadata_fields=detail.metadata_fields or snapshot.metadata_fields,
    cast=detail.cast or snapshot.cast,
    crew=detail.crew or snapshot.crew,
    seasons=detail.seasons or snapshot.seasons,
    episodes=detail.episodes or snapshot.episodes,
    next_episode=detail.next_episode or snapshot.next_episode,
    posters=detail.posters or snapshot.posters,
    backdrops=detail.backdrops or snapshot.backdrops,
    refreshed_at=detail.refreshed_at or snapshot.refreshed_at,
)
```

Finally, make the TMDB provider include the raw field in both detail loaders in `src/atv_player/metadata/providers/tmdb.py`:

```python
next_ep = payload.get("next_episode_to_air")
if isinstance(next_ep, dict):
    detail_fields.append({"label": "next_episode_to_air", "value": next_ep})
```

Place that block beside the existing `last_episode_to_air` handling in both `get_detail(...)` and `get_detail_full(...)`.

- [ ] **Step 4: Run the metadata tests to verify they pass**

Run: `uv run pytest tests/test_following_metadata.py -k "next_episode_to_air or last_episode_to_air" -v`

Expected: PASS for the new `next_episode_to_air` test and the existing `last_episode_to_air` regression coverage.

- [ ] **Step 5: Commit the metadata change**

```bash
git add src/atv_player/following_models.py src/atv_player/following_metadata.py src/atv_player/metadata/providers/tmdb.py tests/test_following_metadata.py
git commit -m "feat: carry tmdb next episode into following snapshots"
```

### Task 2: Add A Symbolic Episode-State Resolver In The Following Domain Layer

**Files:**
- Modify: `src/atv_player/following_models.py`
- Test: `tests/test_following_episode_browser.py`

- [ ] **Step 1: Write the failing resolver tests**

Add these focused tests near the `WATCHED_ROLE` model coverage in `tests/test_following_episode_browser.py`:

```python
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
```

Make sure the test file imports:

```python
from datetime import date

from atv_player.following_models import (
    FollowingEpisode,
    FollowingEpisodeState,
    FollowingSeason,
    resolve_following_episode_state,
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_following_episode_browser.py -k "same_day_next_episode or other_season_as_released" -v`

Expected: FAIL because `FollowingEpisodeState` and `resolve_following_episode_state(...)` do not exist yet.

- [ ] **Step 3: Add the symbolic state constants and resolver**

Add this block to `src/atv_player/following_models.py` below the existing progress helpers:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class FollowingEpisodeState:
    WATCHED = "watched"
    RELEASED = "released"
    UPCOMING = "upcoming"
    PENDING = "pending"


def _episode_air_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_following_episode_state(
    *,
    episode: FollowingEpisode,
    current_season_number: int,
    current_episode: int,
    latest_season_number: int,
    latest_episode: int,
    visible_season_number: int,
    next_episode: FollowingEpisode | None,
    today: date | None = None,
) -> str:
    resolved_today = today or datetime.now(BEIJING_TZ).date()
    episode_season = resolve_progress_season(
        episode.season_number,
        episode.episode_number,
        fallback_season=visible_season_number,
    )
    current_season = resolve_progress_season(
        current_season_number,
        current_episode,
        fallback_season=visible_season_number,
    )
    latest_season = resolve_progress_season(
        latest_season_number,
        latest_episode,
        fallback_season=visible_season_number,
    )
    if (
        episode_season == current_season
        and episode.episode_number > 0
        and episode.episode_number <= max(0, int(current_episode or 0))
    ):
        return FollowingEpisodeState.WATCHED
    if (
        next_episode is not None
        and episode_season
        == resolve_progress_season(
            next_episode.season_number,
            next_episode.episode_number,
            fallback_season=visible_season_number,
        )
        and episode.episode_number == next_episode.episode_number
    ):
        return FollowingEpisodeState.UPCOMING
    air_date = _episode_air_date(episode.air_date)
    if air_date is not None and air_date > resolved_today:
        return FollowingEpisodeState.UPCOMING
    if (
        episode_season == latest_season
        and episode.episode_number > 0
        and episode.episode_number <= max(0, int(latest_episode or 0))
    ):
        return FollowingEpisodeState.RELEASED
    return FollowingEpisodeState.PENDING
```

- [ ] **Step 4: Run the resolver tests to verify they pass**

Run: `uv run pytest tests/test_following_episode_browser.py -k "same_day_next_episode or other_season_as_released" -v`

Expected: PASS for both precedence tests.

- [ ] **Step 5: Commit the domain resolver**

```bash
git add src/atv_player/following_models.py tests/test_following_episode_browser.py
git commit -m "feat: add following episode state resolver"
```

### Task 3: Thread Episode Status Through The Browser Model And Card Renderers

**Files:**
- Modify: `src/atv_player/ui/following_episode_browser.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_episode_browser.py`

- [ ] **Step 1: Write the failing browser/UI tests**

Add these tests to `tests/test_following_episode_browser.py`:

```python
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

    card = browser.episode_cards[0]
    assert card.title_label.text() == "128. 新章"
    assert card.status_badge_label.text() == "已更新"
    assert card.property("episode_status") == FollowingEpisodeState.RELEASED
```

- [ ] **Step 2: Run the browser tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_episode_browser.py -k "upcoming_status_for_same_day_next_episode or inline_status_badge_on_card" -v`

Expected: FAIL because the model does not expose status roles and the card does not render a badge.

- [ ] **Step 3: Add browser roles, context, and inline badge rendering**

In `src/atv_player/ui/following_episode_browser.py`, add status roles and model state:

```python
STATUS_ROLE = Qt.ItemDataRole.UserRole + 7
STATUS_TEXT_ROLE = Qt.ItemDataRole.UserRole + 8
```

```python
def _episode_status_text(state: str) -> str:
    return {
        FollowingEpisodeState.WATCHED: "已看",
        FollowingEpisodeState.RELEASED: "已更新",
        FollowingEpisodeState.UPCOMING: "即将更新",
        FollowingEpisodeState.PENDING: "未更新",
    }[state]
```

```python
class EpisodeListModel(QAbstractListModel):
    def __init__(self, *, display_mode: str = EpisodeDisplayMode.POSTER, parent=None) -> None:
        super().__init__(parent)
        self._episodes: list[FollowingEpisode] = []
        self._current_episode = 0
        self._current_season_number = 0
        self._visible_season_number = 0
        self._latest_episode = 0
        self._latest_season_number = 0
        self._next_episode: FollowingEpisode | None = None
        self.display_mode = display_mode
        self._thumbnail_store: EpisodeThumbnailStore | None = None

    def _episode_state(self, episode: FollowingEpisode) -> str:
        return resolve_following_episode_state(
            episode=episode,
            current_season_number=self._current_season_number,
            current_episode=self._current_episode,
            latest_season_number=self._latest_season_number,
            latest_episode=self._latest_episode,
            visible_season_number=self._visible_season_number,
            next_episode=self._next_episode,
        )
```

Update `data(...)` and `set_episodes(...)`:

```python
if role == STATUS_ROLE:
    return self._episode_state(episode)
if role == STATUS_TEXT_ROLE:
    return _episode_status_text(self._episode_state(episode))
```

```python
def set_episodes(
    self,
    episodes: list[FollowingEpisode],
    *,
    current_episode: int,
    current_season_number: int = 0,
    visible_season_number: int = 0,
    latest_episode: int = 0,
    latest_season_number: int = 0,
    next_episode: FollowingEpisode | None = None,
) -> None:
    self.beginResetModel()
    self._episodes = list(episodes)
    self._current_episode = max(0, int(current_episode))
    self._current_season_number = max(0, int(current_season_number))
    self._visible_season_number = max(0, int(visible_season_number))
    self._latest_episode = max(0, int(latest_episode))
    self._latest_season_number = max(0, int(latest_season_number))
    self._next_episode = next_episode
    self.endResetModel()
```

Thread the same context through `FollowingEpisodeBrowser`:

```python
class FollowingEpisodeBrowser(QWidget):
    def __init__(self, *, initial_grid_columns: int, parent: QWidget | None = None) -> None:
        ...
        self._latest_episode = 0
        self._latest_season_number = 0
        self._next_episode: FollowingEpisode | None = None

    def set_content(
        self,
        *,
        groups: list[EpisodeSeasonGroup],
        current_episode: int,
        current_season_number: int = 0,
        selected_season_number: int = 0,
        latest_episode: int = 0,
        latest_season_number: int = 0,
        next_episode: FollowingEpisode | None = None,
    ) -> None:
        self._groups = list(groups)
        self._current_episode = max(0, int(current_episode))
        self._current_season_number = max(0, int(current_season_number))
        self._latest_episode = max(0, int(latest_episode))
        self._latest_season_number = max(0, int(latest_season_number))
        self._next_episode = next_episode
        ...
```

Use that state in `_apply_group(...)` and when rebuilding cards:

```python
self.episode_model.set_episodes(
    group.episodes,
    current_episode=self._current_episode,
    current_season_number=self._current_season_number,
    visible_season_number=group.season_number,
    latest_episode=self._latest_episode,
    latest_season_number=self._latest_season_number,
    next_episode=self._next_episode,
)
```

```python
def status_for_episode(self, episode: FollowingEpisode) -> str:
    visible_season_number = self._current_group.season_number if self._current_group is not None else 0
    return resolve_following_episode_state(
        episode=episode,
        current_season_number=self._current_season_number,
        current_episode=self._current_episode,
        latest_season_number=self._latest_season_number,
        latest_episode=self._latest_episode,
        visible_season_number=visible_season_number,
        next_episode=self._next_episode,
    )
```

```python
def status_text_for_episode(self, episode: FollowingEpisode) -> str:
    return _episode_status_text(self.status_for_episode(episode))
```

Render the grid-card title row as a title plus badge:

```python
class FollowingEpisodeCard(QFrame):
    def __init__(
        self,
        episode: FollowingEpisode,
        *,
        summary_columns: int,
        thumbnail_store: EpisodeThumbnailStore,
        status: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("episode_status", status)
        ...
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.title_label = QLabel(format_episode_title(episode), self)
        self.status_badge_label = QLabel(_episode_status_text(status), self)
        self.status_badge_label.setObjectName("followingEpisodeStatusBadge")
        self.status_badge_label.setProperty("episode_status", status)
        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.status_badge_label, 0, Qt.AlignmentFlag.AlignVCenter)
        text_layout.addLayout(title_row)
```

In `_rebuild_episode_cards(...)`, pass the symbolic state:

```python
status = self.status_for_episode(episode)
card = FollowingEpisodeCard(
    episode,
    summary_columns=self._grid_columns,
    thumbnail_store=self.thumbnail_store,
    status=status,
    parent=self.episode_grid_container,
)
```

Also update `EpisodeItemDelegate.paint(...)` so the delegate border color and title row use `STATUS_ROLE` and `STATUS_TEXT_ROLE` instead of appending `已看` to the metadata line.

Finally, update `src/atv_player/ui/following_detail_page.py` so `_render(...)` passes the extra context:

```python
latest_season_number = resolve_progress_season(
    record.season_number,
    record.latest_episode,
    fallback_season=record.season_number or self._selected_season_number,
)
self.episode_browser.set_content(
    groups=groups,
    current_season_number=record.current_season_number,
    current_episode=record.current_episode,
    selected_season_number=self._selected_season_number,
    latest_episode=record.latest_episode,
    latest_season_number=latest_season_number,
    next_episode=snapshot.next_episode,
)
```

- [ ] **Step 4: Run the browser/UI tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_episode_browser.py -k "upcoming_status_for_same_day_next_episode or inline_status_badge_on_card or watched_rows" -v`

Expected: PASS for the new status tests and the existing watched-row regression.

- [ ] **Step 5: Commit the browser rendering change**

```bash
git add src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py tests/test_following_episode_browser.py
git commit -m "feat: render following episode status badges"
```

### Task 4: Show Status In The Preview Dialog And Add “Mark This Episode Watched”

**Files:**
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing preview-dialog tests**

Add these tests in `tests/test_following_detail_page_ui.py` beside the existing preview-dialog coverage:

```python
def test_following_episode_preview_dialog_includes_status_text(qtbot) -> None:
    dialog = FollowingEpisodePreviewDialog(
        FollowingEpisode(
            episode_number=3,
            title="第三集",
            air_date="2026-05-13",
            runtime=24,
        ),
        status_text="已更新",
    )
    qtbot.addWidget(dialog)

    assert dialog.meta_label.text() == "2026-05-13 · 24m · 已更新"
    assert dialog.mark_watched_button.text() == "标记本集已看"


def test_following_detail_page_preview_dialog_marks_episode_as_watched(qtbot, monkeypatch) -> None:
    page = FollowingDetailPage(FakeController())
    qtbot.addWidget(page)
    page.load_record(1)

    def fake_exec(self_dialog):
        self_dialog.mark_watched_requested = True
        return 1

    monkeypatch.setattr(
        "atv_player.ui.following_detail_page.FollowingEpisodePreviewDialog.exec",
        fake_exec,
    )

    model = page.episode_browser.episode_list.model()
    page.episode_browser._handle_episode_activated(model.index(0, 0))

    assert page.controller.progress_updates[-1] == (1, 1, 128)
    assert page.status_label.text() == "已标记本集为已看"
```

- [ ] **Step 2: Run the preview-dialog tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "preview_dialog_includes_status_text or preview_dialog_marks_episode_as_watched" -v`

Expected: FAIL because the dialog does not accept `status_text`, has no mark-watched button, and the page does not handle a dialog-triggered progress update.

- [ ] **Step 3: Reuse the existing progress write path from the preview dialog**

First, extend the dialog constructor in `src/atv_player/ui/following_detail_page.py`:

```python
class FollowingEpisodePreviewDialog(ThemedDialogBase):
    def __init__(
        self,
        episode: FollowingEpisode,
        *,
        status_text: str = "",
        can_mark_watched: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        title = _episode_title(episode)
        super().__init__(title=title, parent=parent, resizable=True)
        self.episode = episode
        self.status_text = str(status_text or "").strip()
        self.mark_watched_requested = False
        ...
        self.meta_label = QLabel(_episode_preview_meta_text(episode, self.status_text), self)
        ...
        self.mark_watched_button = QPushButton("标记本集已看", self)
        self.mark_watched_button.setVisible(can_mark_watched)
        self.mark_watched_button.clicked.connect(self._mark_watched_and_accept)
        layout.addWidget(self.mark_watched_button, 0, Qt.AlignmentFlag.AlignRight)

    def _mark_watched_and_accept(self) -> None:
        self.mark_watched_requested = True
        self.accept()
```

Update the preview metadata formatter:

```python
def _episode_preview_meta_text(episode: FollowingEpisode, status_text: str = "") -> str:
    parts = []
    if episode.air_date:
        parts.append(episode.air_date)
    if episode.runtime > 0:
        parts.append(f"{episode.runtime}m")
    if status_text:
        parts.append(status_text)
    return " · ".join(parts)
```

Then extract a shared save helper in `FollowingDetailPage` and use it from both progress entry points:

```python
def _save_following_progress(
    self,
    *,
    season_number: int,
    episode_number: int,
    message: str,
) -> None:
    self.controller.record_playback_progress(
        self.current_following_id,
        current_season_number=season_number,
        current_episode=episode_number,
        position_seconds=0,
    )
    self.load_record(self.current_following_id)
    self.status_label.setText(message)
```

Replace the existing direct write in `_open_progress_dialog(...)`:

```python
self._save_following_progress(
    season_number=dialog.accepted_season_number,
    episode_number=dialog.accepted_episode,
    message="已保存追更进度",
)
```

And update `_open_episode_preview(...)` so it passes the browser-resolved status and uses the same helper when the dialog requests a mark-watched action:

```python
def _open_episode_preview(self, episode: FollowingEpisode) -> None:
    status = self.episode_browser.status_for_episode(episode)
    status_text = self.episode_browser.status_text_for_episode(episode)
    dialog = FollowingEpisodePreviewDialog(
        episode,
        status_text=status_text,
        can_mark_watched=status != FollowingEpisodeState.WATCHED,
        parent=self,
    )
    if dialog.exec() != 1 or not dialog.mark_watched_requested:
        return
    season_number = resolve_progress_season(
        episode.season_number,
        episode.episode_number,
        fallback_season=self.episode_browser.current_season_number() or self.current_view.record.season_number,
    )
    self._save_following_progress(
        season_number=season_number,
        episode_number=episode.episode_number,
        message="已标记本集为已看",
    )
```

- [ ] **Step 4: Run the preview-dialog tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "preview_dialog" -v`

Expected: PASS for the new status and mark-watched behavior, plus the existing preview-dialog regressions.

- [ ] **Step 5: Commit the preview-dialog action**

```bash
git add src/atv_player/ui/following_detail_page.py tests/test_following_detail_page_ui.py
git commit -m "feat: mark following episode watched from preview dialog"
```

### Task 5: Run The Focused End-To-End Regression Set

**Files:**
- Test: `tests/test_following_metadata.py`
- Test: `tests/test_following_episode_browser.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_following_metadata.py \
  tests/test_following_episode_browser.py \
  tests/test_following_detail_page_ui.py -v
```

Expected: PASS with the new schedule/status/preview coverage and no regressions in the existing following-detail UI behavior.

- [ ] **Step 2: If any regression fails, fix it before broadening scope**

Focus first on:

```python
# Browser/model regressions usually mean status context was not threaded
# through `set_content(...)` and `_apply_group(...)`.

self.episode_model.set_episodes(
    group.episodes,
    current_episode=self._current_episode,
    current_season_number=self._current_season_number,
    visible_season_number=group.season_number,
    latest_episode=self._latest_episode,
    latest_season_number=self._latest_season_number,
    next_episode=self._next_episode,
)
```

```python
# Snapshot merge regressions usually mean `next_episode` got dropped.

next_episode=detail.next_episode or snapshot.next_episode,
```

Only proceed once the focused suite is green.

- [ ] **Step 3: Commit the green test state**

```bash
git add tests/test_following_metadata.py tests/test_following_episode_browser.py tests/test_following_detail_page_ui.py src/atv_player/following_models.py src/atv_player/following_metadata.py src/atv_player/metadata/providers/tmdb.py src/atv_player/ui/following_episode_browser.py src/atv_player/ui/following_detail_page.py
git commit -m "test: verify following episode status flow"
```
