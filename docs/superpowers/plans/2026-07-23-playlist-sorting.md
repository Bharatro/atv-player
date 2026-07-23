# Playlist Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-scoped sorting to ordinary player playlists, with options derived from the `PlayItem` fields actually available and full metadata mapping for browse playlists.

**Architecture:** Put comparison, option discovery, original-order snapshots, and current-item relocation in a new pure-Python `playlist_sorting` module. Keep `PlayerWindow` responsible for the combo box and lifecycle hooks, while browse controllers populate generic `PlayItem` metadata so every source can opt in without source-specific UI branches.

**Tech Stack:** Python 3.12, dataclasses, PySide6, pytest, pytest-qt

---

## File map

- Create `src/atv_player/playlist_sorting.py`: sort modes, natural comparison, metadata validation, original-order snapshots, and item relocation.
- Create `tests/test_playlist_sorting.py`: pure unit tests for sorting, options, invalid fields, and snapshots.
- Modify `src/atv_player/models.py`: add generic `rating` and `time` metadata to `PlayItem`.
- Modify `src/atv_player/controllers/browse_controller.py`: map detail and folder metadata into the generic fields.
- Modify `tests/test_browse_controller.py`: verify mapping and invalid-input tolerance.
- Modify `src/atv_player/ui/player_window.py`: render and apply the sort combo across session, source, replacement, and title-enhancement lifecycle events.
- Modify `tests/test_player_window_ui.py`: verify UI visibility, selection preservation, navigation order, lifecycle behavior, and Bilibili tree exclusion.

### Task 1: Pure playlist sorting state

**Files:**
- Create: `tests/test_playlist_sorting.py`
- Create: `src/atv_player/playlist_sorting.py`

- [ ] **Step 1: Write failing tests for options, comparison, missing values, restore, inheritance, and item relocation**

```python
from atv_player.models import PlayItem
from atv_player.playlist_sorting import (
    ORIGINAL,
    NAME_ASC,
    NAME_DESC,
    RATING_ASC,
    RATING_DESC,
    SIZE_ASC,
    SIZE_DESC,
    TIME_ASC,
    TIME_DESC,
    PlaylistSortState,
    find_playlist_item_index,
)


def _item(name: str, **kwargs) -> PlayItem:
    return PlayItem(title=name, original_title=name, url=f"https://media/{name}", **kwargs)


def test_playlist_sort_options_follow_available_fields() -> None:
    playlist = [
        _item("Episode 10.mkv", size=100, rating=8.0, time="2026-07-23T10:00:00+08:00"),
        _item("Episode 2.mkv", size=50, rating=9.0, time="2026-07-22T10:00:00+08:00"),
    ]
    state = PlaylistSortState()

    assert [option.value for option in state.options_for(playlist)] == [
        ORIGINAL,
        NAME_ASC,
        NAME_DESC,
        "size,asc",
        "size,desc",
        "rating,asc",
        "rating,desc",
        "time,asc",
        "time,desc",
    ]


def test_playlist_name_sort_is_natural_and_uses_original_filename() -> None:
    playlist = [
        PlayItem(title="第10集", original_title="Episode 10.mkv", url="10"),
        PlayItem(title="第2集", original_title="Episode 2.mkv", url="2"),
        PlayItem(title="第1集", original_title="episode 1.mkv", url="1"),
    ]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, NAME_ASC)
    assert [item.url for item in playlist] == ["1", "2", "10"]

    state.apply(playlist, NAME_DESC)
    assert [item.url for item in playlist] == ["10", "2", "1"]


def test_playlist_numeric_sort_keeps_missing_values_last_and_ties_stable() -> None:
    first = _item("first", rating=8.0)
    missing = _item("missing")
    second = _item("second", rating=8.0)
    high = _item("high", rating=9.0)
    playlist = [first, missing, second, high]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, RATING_ASC)
    assert playlist == [first, second, high, missing]

    state.apply(playlist, RATING_DESC)
    assert playlist == [high, first, second, missing]


def test_playlist_size_and_time_sort_in_both_directions() -> None:
    old_large = _item("old-large", size=300, time="2026-07-21T10:00:00+08:00")
    new_small = _item("new-small", size=100, time="2026-07-23T10:00:00+08:00")
    middle = _item("middle", size=200, time="2026-07-22T10:00:00+08:00")
    playlist = [old_large, new_small, middle]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, SIZE_ASC)
    assert playlist == [new_small, middle, old_large]
    state.apply(playlist, SIZE_DESC)
    assert playlist == [old_large, middle, new_small]
    state.apply(playlist, TIME_ASC)
    assert playlist == [old_large, middle, new_small]
    state.apply(playlist, TIME_DESC)
    assert playlist == [new_small, middle, old_large]


def test_playlist_sort_restores_each_lists_original_order() -> None:
    first = [_item("b"), _item("a")]
    second = [_item("d"), _item("c")]
    state = PlaylistSortState()
    state.reset([first, second])

    state.apply(first, NAME_ASC)
    state.apply(second, NAME_ASC)
    state.apply(first, ORIGINAL)
    state.apply(second, ORIGINAL)

    assert [item.original_title for item in first] == ["b", "a"]
    assert [item.original_title for item in second] == ["d", "c"]


def test_playlist_sort_inherits_original_order_after_item_preserving_rebuild() -> None:
    first = _item("Episode 2.mkv")
    second = _item("Episode 1.mkv")
    playlist = [first, second]
    rebuilt = [second, first]
    state = PlaylistSortState()
    state.reset([playlist])

    state.inherit_original_order(playlist, rebuilt)
    state.apply(rebuilt, ORIGINAL)

    assert rebuilt == [first, second]


def test_find_playlist_item_index_prefers_object_then_stable_fields() -> None:
    current = PlayItem(title="Episode", url="https://media/2", vod_id="v2", path="/2.mkv")
    playlist = [_item("one"), current]
    assert find_playlist_item_index(playlist, current, 0) == 1

    replacement = PlayItem(title="Renamed", url="https://new/2", vod_id="v2", path="/new.mkv")
    assert find_playlist_item_index([_item("one"), replacement], current, 0) == 1
```

- [ ] **Step 2: Run the new test file and confirm RED**

Run: `uv run pytest tests/test_playlist_sorting.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'atv_player.playlist_sorting'`.

- [ ] **Step 3: Implement the pure sorting module**

Create `src/atv_player/playlist_sorting.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key
import math
import re

from atv_player.models import PlayItem

ORIGINAL = "index"
NAME_ASC = "name,asc"
NAME_DESC = "name,desc"
SIZE_ASC = "size,asc"
SIZE_DESC = "size,desc"
RATING_ASC = "rating,asc"
RATING_DESC = "rating,desc"
TIME_ASC = "time,asc"
TIME_DESC = "time,desc"


@dataclass(frozen=True, slots=True)
class PlaylistSortOption:
    value: str
    label: str


_OPTIONS = (
    PlaylistSortOption(ORIGINAL, "原始顺序"),
    PlaylistSortOption(NAME_ASC, "名称升序"),
    PlaylistSortOption(NAME_DESC, "名称降序"),
    PlaylistSortOption(SIZE_ASC, "大小升序"),
    PlaylistSortOption(SIZE_DESC, "大小降序"),
    PlaylistSortOption(RATING_ASC, "评分升序"),
    PlaylistSortOption(RATING_DESC, "评分降序"),
    PlaylistSortOption(TIME_ASC, "时间升序"),
    PlaylistSortOption(TIME_DESC, "时间降序"),
)


def parse_size_bytes(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)\b", str(value or ""), re.IGNORECASE)
    if match is None:
        return 0
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return max(0, int(float(match.group(1)) * units[match.group(2).upper()]))


def _natural_key(value: str):
    cleaned = str(value or "").strip().casefold()
    if not cleaned:
        return None
    return tuple((0, int(token)) if token.isdigit() else (1, token) for token in re.split(r"(\d+)", cleaned) if token)


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _time_value(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = 0.0
    if number > 0:
        return number / 1000 if number >= 1_000_000_000_000 else number
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _sort_value(item: PlayItem, field: str):
    if field == "name":
        return _natural_key(item.original_title)
    if field == "size":
        return _positive_number(item.size)
    if field == "rating":
        return _positive_number(item.rating)
    if field == "time":
        return _time_value(item.time)
    return None


def _mode_field(mode: str) -> str:
    return mode.split(",", 1)[0] if "," in mode else ""


def find_playlist_item_index(playlist: list[PlayItem], current: PlayItem | None, fallback: int) -> int:
    if not playlist:
        return 0
    safe_fallback = max(0, min(fallback, len(playlist) - 1))
    if current is None:
        return safe_fallback
    for index, candidate in enumerate(playlist):
        if candidate is current:
            return index
    for field in ("vod_id", "url", "path"):
        value = str(getattr(current, field, "") or "").strip()
        if not value:
            continue
        for index, candidate in enumerate(playlist):
            if str(getattr(candidate, field, "") or "").strip() == value:
                return index
    return safe_fallback


class PlaylistSortState:
    def __init__(self) -> None:
        self.mode = ORIGINAL
        self._original_orders: dict[int, tuple[list[PlayItem], tuple[PlayItem, ...]]] = {}

    def reset(self, playlists: list[list[PlayItem]] | None = None) -> None:
        self.mode = ORIGINAL
        self._original_orders.clear()
        for playlist in playlists or []:
            self.remember(playlist)

    def remember(self, playlist: list[PlayItem]) -> None:
        self._original_orders.setdefault(id(playlist), (playlist, tuple(playlist)))

    def inherit_original_order(self, previous: list[PlayItem], updated: list[PlayItem]) -> None:
        self.remember(previous)
        previous_order = self._original_orders[id(previous)][1]
        updated_by_id = {id(item): item for item in updated}
        inherited = [updated_by_id[id(item)] for item in previous_order if id(item) in updated_by_id]
        inherited_ids = {id(item) for item in inherited}
        inherited.extend(item for item in updated if id(item) not in inherited_ids)
        self._original_orders[id(updated)] = (updated, tuple(inherited))

    def options_for(self, playlist: list[PlayItem]) -> tuple[PlaylistSortOption, ...]:
        fields = {
            field
            for field in ("name", "size", "rating", "time")
            if any(_sort_value(item, field) is not None for item in playlist)
        }
        return tuple(option for option in _OPTIONS if option.value == ORIGINAL or _mode_field(option.value) in fields)

    def apply(self, playlist: list[PlayItem], mode: str | None = None) -> str:
        self.remember(playlist)
        requested = self.mode if mode is None else mode
        supported = {option.value for option in self.options_for(playlist)}
        self.mode = requested if requested in supported else ORIGINAL
        original = self._original_orders[id(playlist)][1]
        current_by_id = {id(item): item for item in playlist}
        ordered = [current_by_id[id(item)] for item in original if id(item) in current_by_id]
        ordered_ids = {id(item) for item in ordered}
        ordered.extend(item for item in playlist if id(item) not in ordered_ids)
        playlist[:] = ordered
        if self.mode == ORIGINAL:
            return self.mode

        field, direction = self.mode.split(",", 1)
        descending = direction == "desc"
        original_rank = {id(item): index for index, item in enumerate(playlist)}

        def compare(left: PlayItem, right: PlayItem) -> int:
            left_value = _sort_value(left, field)
            right_value = _sort_value(right, field)
            if left_value is None or right_value is None:
                if left_value is None and right_value is None:
                    return original_rank[id(left)] - original_rank[id(right)]
                return 1 if left_value is None else -1
            if left_value != right_value:
                result = -1 if left_value < right_value else 1
                return -result if descending else result
            return original_rank[id(left)] - original_rank[id(right)]

        playlist.sort(key=cmp_to_key(compare))
        return self.mode
```

- [ ] **Step 4: Run the sorting tests and confirm GREEN**

Run: `uv run pytest tests/test_playlist_sorting.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the pure sorting unit**

```bash
git add src/atv_player/playlist_sorting.py tests/test_playlist_sorting.py
git commit -m "feat: add playlist sorting state"
```

### Task 2: Browse playlist metadata mapping

**Files:**
- Modify: `src/atv_player/models.py:183-230`
- Modify: `src/atv_player/controllers/browse_controller.py:1-35,143-170`
- Modify: `tests/test_browse_controller.py`

- [ ] **Step 1: Write failing controller tests for detail and folder metadata**

Append to `tests/test_browse_controller.py`:

```python
def test_build_request_from_detail_maps_playlist_sort_metadata() -> None:
    api = FakeApiClient()
    api.detail_payload = {
        "list": [{
            "vod_id": "detail-1",
            "vod_name": "Series",
            "items": [{
                "name": "Episode 2.mkv",
                "title": "第2集",
                "url": "http://m/2.m3u8",
                "size": 2048,
                "rating": "8.5",
                "time": "2026-07-23T10:00:00+08:00",
            }],
        }]
    }

    item = BrowseController(api).build_request_from_detail("detail-1").playlist[0]

    assert item.original_title == "Episode 2.mkv"
    assert item.size == 2048
    assert item.rating == 8.5
    assert item.time == "2026-07-23T10:00:00+08:00"


def test_build_request_from_detail_tolerates_invalid_sort_metadata() -> None:
    api = FakeApiClient()
    api.detail_payload = {
        "list": [{
            "vod_id": "detail-1",
            "vod_name": "Series",
            "items": [{"title": "Episode", "url": "1", "size": "bad", "rating": "bad", "time": None}],
        }]
    }

    item = BrowseController(api).build_request_from_detail("detail-1").playlist[0]

    assert item.size == 0
    assert item.rating == 0.0
    assert item.time == ""


def test_build_playlist_from_folder_maps_reliable_sort_metadata() -> None:
    controller = BrowseController(FakeApiClient())
    folder_items = [
        VodItem(
            vod_id="v1",
            vod_name="Episode 1.mkv",
            path="/TV/Episode 1.mkv",
            type=2,
            vod_tag="file",
            vod_remarks="1.5 GB",
            vod_time="2026-07-23 10:00:00",
        )
    ]

    playlist, _ = controller.build_playlist_from_folder(folder_items, "v1")

    assert playlist[0].original_title == "Episode 1.mkv"
    assert playlist[0].size == int(1.5 * 1024**3)
    assert playlist[0].rating == 0.0
    assert playlist[0].time == "2026-07-23 10:00:00"
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `uv run pytest tests/test_browse_controller.py -k 'playlist_sort_metadata or reliable_sort_metadata' -q`

Expected: failures show missing `PlayItem.rating`, `PlayItem.time`, and unmapped folder metadata.

- [ ] **Step 3: Add generic fields and safe browse mapping**

In `src/atv_player/models.py`, add these fields immediately after `size`:

```python
    rating: float = 0.0
    time: str = ""
```

In `src/atv_player/controllers/browse_controller.py`, import `math` plus `parse_size_bytes`, and add the safe number helper:

```python
import math

from atv_player.playlist_sorting import parse_size_bytes


def _safe_rating(value: object) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    return rating if math.isfinite(rating) and rating > 0 else 0.0
```

Replace `_map_play_item` with:

```python
def _map_play_item(payload: dict, index: int) -> PlayItem:
    title = str(payload.get("title") or payload.get("name") or "")
    original_title = str(payload.get("name") or payload.get("title") or "")
    return PlayItem(
        title=title,
        original_title=original_title,
        url=str(payload.get("url") or ""),
        path=str(payload.get("path") or ""),
        index=index,
        size=parse_size_bytes(payload.get("size")),
        rating=_safe_rating(payload.get("rating")),
        time=str(payload.get("time") or ""),
        vod_id=str(payload.get("vod_id") or ""),
    )
```

Replace the `PlayItem(...)` construction inside `build_playlist_from_folder` with:

```python
            playlist_item = PlayItem(
                title=item.vod_name,
                original_title=item.vod_name,
                url=item.vod_play_url,
                path=item.path,
                index=index,
                size=parse_size_bytes(item.vod_remarks) if item.vod_tag == "file" else 0,
                rating=0.0,
                time=str(item.vod_time or ""),
                vod_id=item.vod_id,
            )
```

- [ ] **Step 4: Run browse and sorting tests and confirm GREEN**

Run: `uv run pytest tests/test_browse_controller.py tests/test_playlist_sorting.py -q`

Expected: both files pass.

- [ ] **Step 5: Commit metadata mapping**

```bash
git add src/atv_player/models.py src/atv_player/controllers/browse_controller.py tests/test_browse_controller.py
git commit -m "feat: map browse playlist sort metadata"
```

### Task 3: Player sort control and current-item preservation

**Files:**
- Modify: `src/atv_player/ui/player_window.py:1-140,939-955,1030-1040,1278-1288,1330-1342,2090-2110,3030-3150,9378-9415`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing UI tests for dynamic options, sorting, restore, navigation, and session reset**

Append to `tests/test_player_window_ui.py`:

```python
def _sortable_player_session() -> PlayerSession:
    return PlayerSession(
        vod=VodItem(vod_id="series", vod_name="Series"),
        playlist=[
            PlayItem(title="第10集", original_title="Episode 10.mkv", url="10", size=100),
            PlayItem(title="第2集", original_title="Episode 2.mkv", url="2", size=20),
            PlayItem(title="第1集", original_title="Episode 1.mkv", url="1", size=10),
        ],
        start_index=1,
        start_position_seconds=0,
        speed=1.0,
    )


def test_player_window_playlist_sort_combo_uses_available_fields(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(_sortable_player_session())

    assert not window.playlist_sort_combo.isHidden()
    assert [window.playlist_sort_combo.itemData(i) for i in range(window.playlist_sort_combo.count())] == [
        "index", "name,asc", "name,desc", "size,asc", "size,desc"
    ]


def test_player_window_playlist_sort_keeps_current_item_and_does_not_reload(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    video = RecordingVideo()
    window.video = video
    window.open_session(_sortable_player_session())
    current = window.session.playlist[window.current_index]
    load_count = len(video.load_calls)

    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,asc"))

    assert [item.url for item in window.session.playlist] == ["1", "2", "10"]
    assert window.session.playlist[window.current_index] is current
    assert window.playlist.currentRow() == window.current_index
    assert len(video.load_calls) == load_count

    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("index"))
    assert [item.url for item in window.session.playlist] == ["10", "2", "1"]
    assert window.session.playlist[window.current_index] is current


def test_player_window_next_uses_sorted_playlist_order(qtbot, monkeypatch) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(_sortable_player_session())
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,asc"))
    played: list[int] = []
    monkeypatch.setattr(window, "_play_item_at_index", lambda index, **_kwargs: played.append(index))

    window.play_next()

    assert played == [2]
    assert window.session.playlist[played[0]].url == "10"


def test_player_window_hides_playlist_sort_without_metadata_and_resets_new_session(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(_sortable_player_session())
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,desc"))

    window.open_session(make_player_session(start_index=0))

    assert window.playlist_sort_combo.currentData() == "index"
    assert window.playlist_sort_combo.isHidden()
```

- [ ] **Step 2: Run the focused UI tests and confirm RED**

Run: `/bin/bash -lc 'QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playlist_sort" -q'`

Expected: failures show `PlayerWindow` has no `playlist_sort_combo`.

- [ ] **Step 3: Add the combo, render helpers, and sort handler**

Import the sorting API in `src/atv_player/ui/player_window.py`:

```python
from atv_player.playlist_sorting import ORIGINAL, PlaylistSortState, find_playlist_item_index
```

After `playlist_source_combo` creation, add:

```python
        self.playlist_sort_combo = FlatComboBox()
        self.playlist_sort_combo.setHidden(True)
        self._playlist_sort_state = PlaylistSortState()
```

Configure, lay out, and connect it alongside the other playlist controls:

```python
        self._configure_control_combo(self.playlist_sort_combo, minimum_contents_length=10)
```

```python
        sidebar_layout.addWidget(self.playlist_sort_combo)
```

```python
        self.playlist_sort_combo.currentIndexChanged.connect(self._change_playlist_sort)
```

Add these complete methods near `_render_playlist_title_tabs`:

```python
    def _render_playlist_sort_combo(self) -> None:
        playlist = self.session.playlist if self.session is not None else []
        options = self._playlist_sort_state.options_for(playlist)
        supported = {option.value for option in options}
        if self._playlist_sort_state.mode not in supported:
            self._playlist_sort_state.mode = ORIGINAL
        self.playlist_sort_combo.blockSignals(True)
        self.playlist_sort_combo.clear()
        for option in options:
            self.playlist_sort_combo.addItem(option.label, option.value)
        selected = self.playlist_sort_combo.findData(self._playlist_sort_state.mode)
        self.playlist_sort_combo.setCurrentIndex(max(0, selected))
        self.playlist_sort_combo.blockSignals(False)
        visible = (
            self._playlist_panel_visible()
            and not self._bilibili_grouped_playlist_tree_enabled()
            and len(options) > 1
        )
        self.playlist_sort_combo.setHidden(not visible)

    def _apply_playlist_sort(self, current_item: PlayItem | None = None) -> None:
        if self.session is None:
            return
        fallback = self.current_index
        if current_item is None and 0 <= fallback < len(self.session.playlist):
            current_item = self.session.playlist[fallback]
        self._playlist_sort_state.apply(self.session.playlist)
        self.current_index = find_playlist_item_index(self.session.playlist, current_item, fallback)
        self.session.start_index = self.current_index
        self._render_playlist_sort_combo()
        self._render_playlist_items()

    def _change_playlist_sort(self, _index: int) -> None:
        if self.session is None:
            return
        mode = str(self.playlist_sort_combo.currentData() or ORIGINAL)
        current_item = self.session.playlist[self.current_index] if 0 <= self.current_index < len(self.session.playlist) else None
        self._playlist_sort_state.mode = mode
        self._apply_playlist_sort(current_item)
```

In `open_session`, after playlist/source normalization and before playlist rendering, reset state without changing order:

```python
        self._playlist_sort_state.reset(session.playlists)
```

Call `_render_playlist_sort_combo()` immediately after every existing `_render_playlist_source_combos()` call in the initial `open_session` render path. In `_apply_visibility_state`, call it after group/source visibility is updated:

```python
        self._render_playlist_sort_combo()
        self._render_playlist_title_tabs()
```

- [ ] **Step 4: Run the focused UI tests and confirm GREEN**

Run: `/bin/bash -lc 'QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playlist_sort" -q'`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the base player interaction**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player playlist sort control"
```

### Task 4: Source, replacement, enhancement, and tree lifecycle integration

**Files:**
- Modify: `src/atv_player/ui/player_window.py:3256-3310,4996-5020,5250-5300,9378-9415`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing lifecycle tests**

Append to `tests/test_player_window_ui.py`:

```python
def test_player_window_playlist_sort_follows_source_and_preserves_target_episode(qtbot, monkeypatch) -> None:
    first = [
        PlayItem(title="A2", original_title="Episode 2.mkv", url="a2"),
        PlayItem(title="A1", original_title="Episode 1.mkv", url="a1"),
    ]
    second = [
        PlayItem(title="B2", original_title="Episode 2.mkv", url="b2"),
        PlayItem(title="B1", original_title="Episode 1.mkv", url="b1"),
    ]
    session = PlayerSession(
        vod=VodItem(vod_id="series", vod_name="Series"),
        playlist=first,
        playlists=[first, second],
        source_groups=[PlaybackSourceGroup(label="线路", sources=[
            PlaybackSource(label="线路1", playlist=first),
            PlaybackSource(label="线路2", playlist=second),
        ])],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,asc"))
    monkeypatch.setattr(window, "_load_current_item", lambda **_kwargs: None)

    window._switch_active_source(0, 1)

    assert [item.url for item in window.session.playlist] == ["b1", "b2"]
    assert window.session.playlist[window.current_index].url == "b2"


def test_player_window_playlist_sort_falls_back_when_target_source_lacks_field(qtbot, monkeypatch) -> None:
    first = [PlayItem(title="A", original_title="A.mkv", url="a")]
    second = [PlayItem(title="B", url="b")]
    session = PlayerSession(
        vod=VodItem(vod_id="series", vod_name="Series"),
        playlist=first,
        playlists=[first, second],
        source_groups=[PlaybackSourceGroup(label="线路", sources=[
            PlaybackSource(label="线路1", playlist=first),
            PlaybackSource(label="线路2", playlist=second),
        ])],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,desc"))
    monkeypatch.setattr(window, "_load_current_item", lambda **_kwargs: None)

    window._switch_active_source(0, 1)

    assert window._playlist_sort_state.mode == "index"
    assert window.playlist_sort_combo.isHidden()


def test_player_window_playlist_sort_applies_to_replacement_and_keeps_requested_item(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(_sortable_player_session())
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,asc"))
    replacement = [
        PlayItem(title="第3集", original_title="Episode 3.mkv", url="3"),
        PlayItem(title="第1集", original_title="Episode 1.mkv", url="1-new"),
    ]

    window._apply_playback_loader_result(PlaybackLoadResult(replacement_playlist=replacement, replacement_start_index=0))

    assert [item.url for item in window.session.playlist] == ["1-new", "3"]
    assert window.session.playlist[window.current_index].url == "3"


def test_player_window_playlist_sort_survives_episode_title_enhancement(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = _sortable_player_session()
    window.open_session(session)
    window.playlist_sort_combo.setCurrentIndex(window.playlist_sort_combo.findData("name,asc"))
    current = window.session.playlist[window.current_index]
    window._pending_episode_title_session = session
    window._episode_title_request_id = 7
    updated = [
        PlayItem(title="第10集", original_title="Episode 10.mkv", episode_display_title="新标题10", url="10"),
        PlayItem(title="第2集", original_title="Episode 2.mkv", episode_display_title="新标题2", url="2"),
        PlayItem(title="第1集", original_title="Episode 1.mkv", episode_display_title="新标题1", url="1"),
    ]

    window._handle_episode_title_enhancement_succeeded(7, updated)

    assert [item.original_title for item in window.session.playlist] == ["Episode 1.mkv", "Episode 2.mkv", "Episode 10.mkv"]
    assert window.session.playlist[window.current_index] is current


def test_player_window_hides_playlist_sort_in_bilibili_tree_mode(qtbot) -> None:
    config = AppConfig(bilibili_grouped_playlist_tree_enabled=True)
    session = make_bilibili_grouped_session()
    for group in session.playlists:
        for index, item in enumerate(group):
            item.original_title = f"Episode {index + 1}.mp4"
    window = PlayerWindow(FakePlayerController(), config=config)
    qtbot.addWidget(window)

    window.open_session(session)

    assert window._bilibili_grouped_playlist_tree_enabled()
    assert window.playlist_sort_combo.isHidden()
```

- [ ] **Step 2: Run the lifecycle tests and confirm RED**

Run: `/bin/bash -lc 'QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playlist_sort_follows_source or playlist_sort_falls_back or playlist_sort_applies_to_replacement or playlist_sort_survives_episode or hides_playlist_sort_in_bilibili" -q'`

Expected: source and replacement lists remain unsorted, and enhancement loses the active sort.

- [ ] **Step 3: Integrate sort state at each lifecycle boundary**

In `_switch_active_source`, apply the current mode to the target list before selecting the same visible episode index, then render the combo before loading:

```python
        self.session.playlist = target_playlist
        self._playlist_sort_state.apply(target_playlist)
        target_index = min(previous_index, len(target_playlist) - 1)
        self.current_index = target_index
        self.session.start_index = self.current_index
        self.playlist_title_mode = "episode"
        self._render_playlist_source_combos()
        self._render_playlist_sort_combo()
```

In `_apply_playback_loader_result`, register and sort the replacement after selecting `replacement_start_index` and before rendering:

```python
        self.session.playlist = replacement
        self.current_index = max(0, min(load_result.replacement_start_index, len(replacement) - 1))
        replacement_item = replacement[self.current_index]
        self._playlist_sort_state.remember(replacement)
        self._playlist_sort_state.apply(replacement)
        self.current_index = find_playlist_item_index(replacement, replacement_item, self.current_index)
        self.session.start_index = self.current_index
```

Keep `active_source.playlist`, `session.playlists[playlist_index]`, and `session.playlist` pointing at the same mutated replacement list. Add `_render_playlist_sort_combo()` after `_render_playlist_source_combos()`.

In `_handle_episode_title_enhancement_succeeded`, preserve the old list snapshot, inherit it into the merged list, reapply the active mode, and relocate the current item:

```python
        current_item = self.session.playlist[self.current_index] if 0 <= self.current_index < len(self.session.playlist) else None
        previous_playlist = self.session.playlist
        merged_playlist = self._merge_episode_title_enhancement_playlist(updated_playlist)
        self._playlist_sort_state.inherit_original_order(previous_playlist, merged_playlist)
        self.session.playlist = merged_playlist
        self._playlist_sort_state.apply(self.session.playlist)
        self.current_index = find_playlist_item_index(self.session.playlist, current_item, self.current_index)
        self.session.start_index = self.current_index
```

After updating `session.playlists` and the active source reference, call:

```python
        self._render_playlist_sort_combo()
        self._render_playlist_title_tabs()
        self._render_playlist_items()
```

Ensure `_apply_visibility_state` always calls `_render_playlist_sort_combo()` so Bilibili tree mode and playlist-hidden mode suppress the combo.

- [ ] **Step 4: Run focused lifecycle and existing neighboring tests**

Run: `/bin/bash -lc 'QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "playlist_sort or switches_leaf_source or replacement or episode_title_enhancer or bilibili_grouped_playlist_tree" -q'`

Expected: all selected tests pass.

- [ ] **Step 5: Commit lifecycle integration**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: preserve playlist sorting across player updates"
```

### Task 5: Full verification and documentation alignment

**Files:**
- Modify if needed: `README.md`
- Verify: all files changed by Tasks 1-4

- [ ] **Step 1: Add the player capability to README if it is not already explicit**

Update the player feature list entry to include the completed behavior:

```markdown
- 播放器播放列表根据可用字段支持原始顺序、名称、大小、评分和时间排序，并在排序后保持当前播放项
```

- [ ] **Step 2: Run formatting and static checks**

Run: `uv run ruff check src/atv_player/playlist_sorting.py src/atv_player/models.py src/atv_player/controllers/browse_controller.py src/atv_player/ui/player_window.py tests/test_playlist_sorting.py tests/test_browse_controller.py tests/test_player_window_ui.py`

Expected: exit code 0 with no diagnostics.

- [ ] **Step 3: Run focused controller and pure unit suites**

Run: `uv run pytest tests/test_playlist_sorting.py tests/test_browse_controller.py -q`

Expected: all tests pass.

- [ ] **Step 4: Run the full player UI test file offscreen**

Run: `/bin/bash -lc 'QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -q'`

Expected: all tests pass with no failures or Qt warnings introduced by this feature.

- [ ] **Step 5: Run the full project suite**

Run: `uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 6: Inspect final diff and commit verification/docs**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended feature files are modified.

```bash
git add README.md
git commit -m "docs: document playlist sorting"
```

If README already states the exact player sorting capability and no documentation change is required, skip this final commit rather than creating an empty commit.
