# Metadata Multi Poster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve poster artwork from multiple metadata providers and let the player detail panel switch posters manually without changing the existing primary-poster behavior.

**Architecture:** Keep `vod_pic` as the primary poster field and add `VodItem.poster_candidates` as the ordered, deduplicated poster list. Update metadata merge helpers so primary-poster priority stays unchanged while old and lower-priority posters remain available. In the player window, add lightweight previous/next poster controls, read poster candidates from the currently displayed metadata view, and reset the selected poster index whenever the active metadata snapshot changes.

**Tech Stack:** Python 3, dataclasses, PySide6 widgets/signals, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/models.py`
  - Add `VodItem.poster_candidates` so metadata and UI can share one ordered poster list.
- Modify: `src/atv_player/metadata/merge.py`
  - Centralize poster-candidate normalization, deduplication, and primary-poster promotion across merge paths.
- Modify: `src/atv_player/controllers/player_controller.py`
  - Store the current detail-poster index on `PlayerSession` alongside existing metadata-view session state.
- Modify: `src/atv_player/ui/player_window.py`
  - Add poster navigation buttons, derive poster lists from the active metadata view, and reset the selected index during session/metadata transitions.
- Modify: `tests/test_metadata_merge.py`
  - Lock down poster-candidate ordering, deduplication, and primary-poster consistency.
- Modify: `tests/test_player_window_ui.py`
  - Cover poster navigation visibility, manual switching, looping, and reset behavior for original/enhanced metadata transitions.

### Task 1: Preserve Multi-Source Poster Candidates In Metadata Merge

**Files:**
- Modify: `tests/test_metadata_merge.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/metadata/merge.py`

- [ ] **Step 1: Write the failing tests**

Add focused merge coverage near the existing poster-priority tests in `tests/test_metadata_merge.py`:

```python
def test_merge_metadata_promotes_higher_priority_poster_and_keeps_previous_candidate() -> None:
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_pic="https://img.site/poster.jpg")
    record = MetadataRecord(
        provider="tmdb",
        provider_id="movie:42",
        poster="https://img.tmdb/poster.jpg",
    )

    merge_metadata_record(vod, record, provider_priority=["tmdb"])

    assert vod.vod_pic == "https://img.tmdb/poster.jpg"
    assert vod.poster_candidates == [
        "https://img.tmdb/poster.jpg",
        "https://img.site/poster.jpg",
    ]


def test_merge_metadata_appends_lower_priority_poster_without_overriding_primary() -> None:
    vod = VodItem(vod_id="v1", vod_name="旧标题", vod_pic="https://img.tmdb/poster.jpg")
    vod.metadata_field_sources["poster"] = "tmdb"
    record = MetadataRecord(
        provider="bangumi",
        provider_id="subject:1",
        poster="https://img.bgm/poster.jpg",
    )

    merge_metadata_record(vod, record, provider_priority=["bangumi", "tmdb"])

    assert vod.vod_pic == "https://img.tmdb/poster.jpg"
    assert vod.poster_candidates == [
        "https://img.tmdb/poster.jpg",
        "https://img.bgm/poster.jpg",
    ]
```

- [ ] **Step 2: Run the targeted merge tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metadata_merge.py -k "poster and candidate" -v
```

Expected:

```text
FAILED tests/test_metadata_merge.py::test_merge_metadata_promotes_higher_priority_poster_and_keeps_previous_candidate
FAILED tests/test_metadata_merge.py::test_merge_metadata_appends_lower_priority_poster_without_overriding_primary
```

The failure should be because `VodItem` does not yet expose `poster_candidates` and merge helpers do not preserve older posters.

- [ ] **Step 3: Write the minimal implementation**

In `src/atv_player/models.py`, add the new field directly next to `vod_pic`:

```python
@dataclass(slots=True)
class VodItem:
    vod_id: str
    vod_name: str
    detail_style: str = ""
    path: str = ""
    share_type: str = ""
    vod_pic: str = ""
    poster_candidates: list[str] = field(default_factory=list)
    vod_tag: str = ""
```

In `src/atv_player/metadata/merge.py`, add one helper that keeps `vod_pic` and `poster_candidates` consistent, then reuse it from all poster-writing paths:

```python
def _normalize_poster_source(value: object) -> str:
    return str(value or "").strip()


def _sync_poster_candidates(vod: VodItem, *, primary: str, candidate: str = "") -> None:
    ordered: list[str] = []
    seen: set[str] = set()
    for source in (primary, *vod.poster_candidates, vod.vod_pic, candidate):
        normalized = _normalize_poster_source(source)
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    vod.vod_pic = ordered[0] if ordered else ""
    vod.poster_candidates = ordered
```

Update poster writes in the merge helpers so promotion and append behavior is explicit:

```python
def merge_metadata_record(vod: VodItem, record: MetadataRecord, provider_priority: list[str]) -> VodItem:
    del provider_priority
    poster = _normalize_poster_source(record.poster)
    if poster:
        if not vod.vod_pic or _can_override(vod, "poster", record.provider):
            _sync_poster_candidates(vod, primary=poster)
            _set_field_source(vod, "poster", record.provider)
        else:
            _sync_poster_candidates(vod, primary=vod.vod_pic, candidate=poster)
```

Apply the same helper in `fill_missing_metadata_record(...)`, `override_visual_metadata_record(...)`, and `replace_metadata_record(...)` so manual scrape replacement and visual overrides do not silently drop the candidate list:

```python
if not vod.vod_pic and record.poster:
    _sync_poster_candidates(vod, primary=record.poster)
```

```python
if record.poster and (not vod.vod_pic or _can_override(vod, "poster", record.provider)):
    _sync_poster_candidates(vod, primary=record.poster)
```

```python
_sync_poster_candidates(vod, primary=record.poster)
```

- [ ] **Step 4: Run the merge tests and verify they pass**

Run:

```bash
uv run pytest tests/test_metadata_merge.py -k "poster and candidate" -v
```

Expected:

```text
PASSED tests/test_metadata_merge.py::test_merge_metadata_promotes_higher_priority_poster_and_keeps_previous_candidate
PASSED tests/test_metadata_merge.py::test_merge_metadata_appends_lower_priority_poster_without_overriding_primary
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_merge.py src/atv_player/models.py src/atv_player/metadata/merge.py
git commit -m "feat: preserve metadata poster candidates"
```

### Task 2: Add Manual Poster Navigation To The Player Detail Panel

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing UI tests**

Add focused player-window tests near the existing poster tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_shows_poster_navigation_for_multiple_candidates(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str, on_loaded=None) -> None:
        if target == "detail":
            detail_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            vod_pic="https://img.example/main.jpg",
            poster_candidates=[
                "https://img.example/main.jpg",
                "https://img.example/alt.jpg",
            ],
        ),
        playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert window._poster_previous_button.isHidden() is False
    assert window._poster_next_button.isHidden() is False
    qtbot.mouseClick(window._poster_next_button, Qt.MouseButton.LeftButton)
    assert detail_started[-1] == "https://img.example/alt.jpg"


def test_player_window_hides_poster_navigation_for_single_candidate(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="https://img.example/main.jpg"),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )

    assert window._poster_previous_button.isHidden() is True
    assert window._poster_next_button.isHidden() is True


def test_player_window_poster_navigation_loops_at_boundaries(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str, on_loaded=None) -> None:
        if target == "detail":
            detail_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(
        PlayerSession(
            vod=VodItem(
                vod_id="movie-1",
                vod_name="Movie",
                vod_pic="https://img.example/main.jpg",
                poster_candidates=[
                    "https://img.example/main.jpg",
                    "https://img.example/alt.jpg",
                ],
            ),
            playlist=[PlayItem(title="正片", url="http://m/1.m3u8")],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
        )
    )

    qtbot.mouseClick(window._poster_previous_button, Qt.MouseButton.LeftButton)
    assert detail_started[-1] == "https://img.example/alt.jpg"
```

- [ ] **Step 2: Run the targeted UI tests and verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "poster_navigation" -v
```

Expected:

```text
FAILED tests/test_player_window_ui.py::test_player_window_shows_poster_navigation_for_multiple_candidates
FAILED tests/test_player_window_ui.py::test_player_window_hides_poster_navigation_for_single_candidate
FAILED tests/test_player_window_ui.py::test_player_window_poster_navigation_loops_at_boundaries
```

The failure should show that the player window has no poster navigation controls and always reads the detail poster from `vod_pic`.

- [ ] **Step 3: Write the minimal implementation**

In `src/atv_player/controllers/player_controller.py`, store the detail-poster selection with the rest of the session-scoped metadata UI state:

```python
@dataclass(slots=True)
class PlayerSession:
    ...
    original_vod: VodItem | None = None
    show_original_metadata: bool = False
    current_metadata_poster_index: int = 0
    original_item_detail_fields_by_key: dict[tuple[str, str, str, str, str], list[PlaybackDetailField]] = field(
        default_factory=dict
    )
```

In `src/atv_player/ui/player_window.py`, replace the bare poster widget slot with a navigation row that reuses the existing `previous.svg` and `next.svg` icons:

```python
self._poster_previous_button = self._create_icon_button("previous.svg", "上一张海报", role="secondary")
self._poster_next_button = self._create_icon_button("next.svg", "下一张海报", role="secondary")
self._poster_navigation_row = QHBoxLayout()
self._poster_navigation_row.setContentsMargins(0, 0, 0, 0)
self._poster_navigation_row.setSpacing(8)
self._poster_navigation_row.addStretch(1)
self._poster_navigation_row.addWidget(self._poster_previous_button)
self._poster_navigation_row.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignHCenter)
self._poster_navigation_row.addWidget(self._poster_next_button)
self._poster_navigation_row.addStretch(1)
metadata_layout.addLayout(self._poster_navigation_row)
```

Add helpers so the detail poster uses the active metadata view instead of always reading `session.vod.vod_pic`:

```python
def _current_metadata_poster_sources(self) -> list[str]:
    vod = self._current_metadata_vod()
    if vod is None:
        return []
    candidates = [str(source or "").strip() for source in vod.poster_candidates if str(source or "").strip()]
    if candidates:
        return candidates
    return [str(vod.vod_pic or "").strip()] if str(vod.vod_pic or "").strip() else []


def _preferred_detail_poster_source(self) -> str:
    sources = self._current_metadata_poster_sources()
    if self.session is None or not sources:
        return ""
    index = self.session.current_metadata_poster_index % len(sources)
    return sources[index]


def _refresh_poster_navigation(self) -> None:
    visible = len(self._current_metadata_poster_sources()) > 1
    self._poster_previous_button.setHidden(not visible)
    self._poster_next_button.setHidden(not visible)
```

Wire up manual switching and loop at the boundaries:

```python
def _step_metadata_poster(self, offset: int) -> None:
    if self.session is None:
        return
    sources = self._current_metadata_poster_sources()
    if len(sources) <= 1:
        self.session.current_metadata_poster_index = 0
        self._refresh_poster_navigation()
        return
    self.session.current_metadata_poster_index = (self.session.current_metadata_poster_index + offset) % len(sources)
    self._refresh_poster_navigation()
    self._render_detail_poster()
```

Hook the buttons after widget construction and refresh visibility whenever posters rerender:

```python
self._poster_previous_button.clicked.connect(lambda: self._step_metadata_poster(-1))
self._poster_next_button.clicked.connect(lambda: self._step_metadata_poster(1))
```

```python
def _render_poster(self) -> None:
    self._refresh_poster_navigation()
    self._render_detail_poster()
    self._render_video_poster()
```

- [ ] **Step 4: Run the UI tests and verify they pass**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "poster_navigation" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_shows_poster_navigation_for_multiple_candidates
PASSED tests/test_player_window_ui.py::test_player_window_hides_poster_navigation_for_single_candidate
PASSED tests/test_player_window_ui.py::test_player_window_poster_navigation_loops_at_boundaries
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/controllers/player_controller.py src/atv_player/ui/player_window.py
git commit -m "feat: add player detail poster navigation"
```

### Task 3: Reset Poster Selection When Metadata View Changes

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing lifecycle tests**

Add regression coverage for original/enhanced toggles and metadata refreshes in `tests/test_player_window_ui.py`:

```python
def test_player_window_toggling_original_metadata_resets_detail_poster_to_first_candidate(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str, on_loaded=None) -> None:
        if target == "detail":
            detail_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    session = PlayerSession(
        vod=VodItem(
            vod_id="v1",
            vod_name="原始标题",
            vod_pic="https://img.example/original-1.jpg",
            poster_candidates=[
                "https://img.example/original-1.jpg",
                "https://img.example/original-2.jpg",
            ],
            vod_content="原始简介",
        ),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(
            vod_id="v1",
            vod_name="增强标题",
            vod_pic="https://img.example/enhanced-1.jpg",
            poster_candidates=[
                "https://img.example/enhanced-1.jpg",
                "https://img.example/enhanced-2.jpg",
            ],
            vod_content="增强简介",
        ),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    qtbot.waitUntil(lambda: "增强简介" in window.metadata_view.toPlainText(), timeout=1000)

    qtbot.mouseClick(window._poster_next_button, Qt.MouseButton.LeftButton)
    assert detail_started[-1] == "https://img.example/enhanced-2.jpg"

    qtbot.mouseClick(window._metadata_original_toggle, Qt.MouseButton.LeftButton)
    assert detail_started[-1] == "https://img.example/original-1.jpg"
    assert window.session.current_metadata_poster_index == 0


def test_player_window_metadata_scrape_apply_resets_detail_poster_index(qtbot, monkeypatch) -> None:
    detail_started: list[str] = []

    def fake_start(self, source: str, request_id: int, *, target: str, on_loaded=None) -> None:
        if target == "detail":
            detail_started.append(source)

    monkeypatch.setattr(PlayerWindow, "_start_poster_load", fake_start)

    service = FakeMetadataScrapeService()
    session = PlayerSession(
        vod=VodItem(
            vod_id="v1",
            vod_name="深空彼岸",
            vod_pic="https://img.example/original-1.jpg",
            poster_candidates=[
                "https://img.example/original-1.jpg",
                "https://img.example/original-2.jpg",
            ],
            vod_content="原始简介",
        ),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=service,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    qtbot.mouseClick(window._poster_next_button, Qt.MouseButton.LeftButton)
    assert window.session.current_metadata_poster_index == 1

    window._open_metadata_scrape_dialog()
    window._rerun_metadata_scrape_search()
    qtbot.waitUntil(lambda: window._metadata_scrape_result_list.count() == 1, timeout=1000)
    window._apply_selected_metadata_scrape_result()

    qtbot.waitUntil(lambda: window.session.current_metadata_poster_index == 0, timeout=1000)
```

- [ ] **Step 2: Run the lifecycle tests and verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "resets_detail_poster" -v
```

Expected:

```text
FAILED tests/test_player_window_ui.py::test_player_window_toggling_original_metadata_resets_detail_poster_to_first_candidate
FAILED tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_resets_detail_poster_index
```

The failures should show that the player keeps the old poster index across metadata-view changes and does not force the detail poster back to the new list's first item.

- [ ] **Step 3: Write the minimal implementation**

In `src/atv_player/ui/player_window.py`, add one reset helper and call it from every metadata-view transition that can replace the candidate list:

```python
def _reset_metadata_poster_index(self) -> None:
    if self.session is None:
        return
    self.session.current_metadata_poster_index = 0
    self._refresh_poster_navigation()
```

Reset on session open and on any non-user metadata replacement path:

```python
def open_session(self, session, start_paused: bool = False) -> None:
    ...
    session.show_original_metadata = False
    session.current_metadata_poster_index = 0
```

```python
def _toggle_original_metadata_view(self, checked: bool) -> None:
    ...
    self.session.show_original_metadata = checked
    self._reset_metadata_poster_index()
    self._render_metadata()
    self._render_detail_fields()
    self._render_poster()
```

```python
def _apply_resolved_vod(self, resolved_vod: VodItem) -> None:
    ...
    self._reset_metadata_poster_index()
    self._render_poster()
```

```python
def _handle_metadata_hydration_succeeded(self, request_id: int, updated_vod: VodItem | None) -> None:
    ...
    self.session.vod = updated_vod
    self._reset_metadata_poster_index()
    self._render_poster()
```

```python
def _handle_metadata_scrape_apply_succeeded(self, request_id: int, updated_vod: VodItem, candidate) -> None:
    ...
    self.session.vod = updated_vod
    self._reset_metadata_poster_index()
    self._render_poster()
```

Keep `_preferred_video_poster_source()` unchanged so only the detail-panel poster reacts to manual selection.

- [ ] **Step 4: Run the lifecycle regressions and one combined poster suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "poster_navigation or resets_detail_poster or renders_poster" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_toggling_original_metadata_resets_detail_poster_to_first_candidate
PASSED tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_resets_detail_poster_index
PASSED tests/test_player_window_ui.py::test_player_window_shows_poster_navigation_for_multiple_candidates
PASSED tests/test_player_window_ui.py::test_player_window_hides_poster_navigation_for_single_candidate
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "fix: reset detail poster selection on metadata changes"
```

## Coverage Check

- Spec section `Data model` is covered by Task 1 through `VodItem.poster_candidates`.
- Spec section `Merge behavior` is covered by Task 1 through `_sync_poster_candidates(...)` and merge-path updates.
- Spec section `Player detail poster UI` is covered by Task 2 through previous/next controls and detail-only poster selection.
- Spec section `Original vs enhanced metadata compatibility` is covered by Task 3 through toggle-reset tests and reset calls.
- Spec section `Session and refresh lifecycle` is covered by Task 3 through `open_session(...)`, `_apply_resolved_vod(...)`, hydration success, and scrape-apply success resets.

## Placeholder Scan

- No `TODO`, `TBD`, or “similar to above” placeholders remain.
- Every code-changing task includes exact files, example code, commands, and expected outcomes.
- No task depends on undefined helper names outside earlier steps in this document.
