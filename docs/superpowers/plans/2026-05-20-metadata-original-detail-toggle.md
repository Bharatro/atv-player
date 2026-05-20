# Metadata Original Detail Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve pre-enhancement detail data for the active player session and add a small no-text toggle in the player details pane to switch between enhanced and original detail views.

**Architecture:** Extend `PlayerSession` with original-detail session state, including an original `VodItem` snapshot and a per-play-item cache for original detail fields so current-item field overrides can also be restored. Keep the implementation concentrated in `PlayerWindow`: render from a computed “current metadata view” source, update original snapshots only on non-metadata detail updates, and leave metadata hydration / scrape apply as enhanced-only writes.

**Tech Stack:** Python, pytest, PySide6

---

### Task 1: Add Session State And A No-Text Metadata Toggle

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window tests for toggle rendering and content switching**

```python
def test_player_window_metadata_original_toggle_switches_between_enhanced_and_original_content(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
            return None

        def set_speed(self, value: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 0

    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(
            vod_id="v1",
            vod_name="增强标题",
            vod_year="2024",
            vod_content="增强简介",
            detail_fields=[PlaybackDetailField(label="TMDB ID", value="1")],
        ),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    qtbot.waitUntil(lambda: "增强简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert window._metadata_original_toggle.isHidden() is False
    assert window._metadata_original_toggle.isChecked() is False

    window._metadata_original_toggle.click()

    qtbot.waitUntil(lambda: "原始简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert "增强简介" not in window.metadata_view.toPlainText()
    assert "TMDB ID: 1" not in window.metadata_view.toPlainText()

    window._metadata_original_toggle.click()

    qtbot.waitUntil(lambda: "增强简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert "原始简介" not in window.metadata_view.toPlainText()


def test_player_window_hides_metadata_original_toggle_when_metadata_matches_original(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
            return None

        def set_speed(self, value: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 0

    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(
            vod_id="v1",
            vod_name="原始标题",
            vod_year="2026",
            vod_content="原始简介",
        ),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)

    qtbot.waitUntil(lambda: window._pending_metadata_session is None, timeout=1000)
    assert window._metadata_original_toggle.isHidden() is True
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_metadata_original_toggle_switches_between_enhanced_and_original_content tests/test_player_window_ui.py::test_player_window_hides_metadata_original_toggle_when_metadata_matches_original -q`

Expected: FAIL because `PlayerSession` has no original-detail state and `PlayerWindow` has no `_metadata_original_toggle` or original/enhanced view switching.

- [ ] **Step 3: Write the minimal session and UI implementation**

```python
# src/atv_player/controllers/player_controller.py
@dataclass(slots=True)
class PlayerSession:
    ...
    original_vod: VodItem | None = None
    show_original_metadata: bool = False
    original_item_detail_fields_by_key: dict[tuple[str, str, str, str, str], list[PlaybackDetailField]] = field(
        default_factory=dict
    )
```

```python
# src/atv_player/ui/player_window.py
from copy import deepcopy
...
from PySide6.QtWidgets import ..., QCheckBox, ...
...
self._metadata_original_toggle = QCheckBox()
self._metadata_original_toggle.setText("")
self._metadata_original_toggle.setTristate(False)
self._metadata_original_toggle.setHidden(True)
self._metadata_original_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
...
heading_row = QHBoxLayout()
heading_row.setContentsMargins(0, 0, 0, 0)
heading_row.addWidget(self.metadata_heading)
heading_row.addStretch(1)
heading_row.addWidget(self._metadata_original_toggle, 0, Qt.AlignmentFlag.AlignRight)
metadata_layout.addLayout(heading_row)
...
self._metadata_original_toggle.toggled.connect(self._toggle_original_metadata_view)
...
def _clone_metadata_snapshot(self, vod: VodItem) -> VodItem:
    return deepcopy(vod)

def _current_metadata_vod(self) -> VodItem | None:
    if self.session is None:
        return None
    if self.session.show_original_metadata and self.session.original_vod is not None:
        return self.session.original_vod
    return self.session.vod

def _toggle_original_metadata_view(self, checked: bool) -> None:
    if self.session is None:
        return
    self.session.show_original_metadata = checked
    self._refresh_metadata_original_toggle()
    self._render_metadata()
    self._render_detail_fields()

def _metadata_values_differ(self) -> bool:
    if self.session is None or self.session.original_vod is None:
        return False
    original = self.session.original_vod
    current = self.session.vod
    return (
        original.vod_name != current.vod_name
        or original.type_name != current.type_name
        or original.vod_year != current.vod_year
        or original.vod_area != current.vod_area
        or original.vod_lang != current.vod_lang
        or original.vod_remarks != current.vod_remarks
        or original.vod_director != current.vod_director
        or original.vod_actor != current.vod_actor
        or original.vod_content != current.vod_content
        or original.dbid != current.dbid
        or original.detail_fields != current.detail_fields
    )

def _refresh_metadata_original_toggle(self) -> None:
    visible = (
        self.session is not None
        and not self.details.isHidden()
        and self._metadata_values_differ()
    )
    if self.session is not None and not visible:
        self.session.show_original_metadata = False
    self._metadata_original_toggle.blockSignals(True)
    self._metadata_original_toggle.setChecked(bool(self.session and self.session.show_original_metadata))
    self._metadata_original_toggle.setToolTip(
        "显示增强后详情" if self.session and self.session.show_original_metadata else "显示原始详情"
    )
    self._metadata_original_toggle.blockSignals(False)
    self._metadata_original_toggle.setHidden(not visible)

def _render_metadata(self) -> None:
    vod = self._current_metadata_vod()
    if vod is None:
        self.metadata_view.clear()
        return
    self.metadata_view.setHtml(self._format_metadata_html(vod))
```

- [ ] **Step 4: Run the tests again to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_metadata_original_toggle_switches_between_enhanced_and_original_content tests/test_player_window_ui.py::test_player_window_hides_metadata_original_toggle_when_metadata_matches_original -q`

Expected: PASS

- [ ] **Step 5: Commit the session state and toggle scaffold**

```bash
git add src/atv_player/controllers/player_controller.py src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add original metadata detail toggle scaffold"
```

### Task 2: Preserve Original Detail Snapshots Across Hydration, Scrape Apply, And Current-Item Field Overrides

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests for scrape-apply restoration and late non-metadata detail preservation**

```python
def test_player_window_metadata_scrape_apply_original_toggle_restores_original_item_detail_fields(qtbot) -> None:
    service = FakeMetadataScrapeService()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026", vod_content="原始简介"),
        playlist=[
            PlayItem(
                title="第1集",
                url="https://media.example/1.mp4",
                detail_fields=[PlaybackDetailField(label="站内热度", value="99")],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=service,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window._open_metadata_scrape_dialog()
    window._rerun_metadata_scrape_search()
    qtbot.waitUntil(lambda: window._metadata_scrape_result_list.count() == 1, timeout=1000)

    window._apply_selected_metadata_scrape_result()

    qtbot.waitUntil(lambda: "TMDB ID: 1" in window.metadata_view.toPlainText(), timeout=1000)
    window._metadata_original_toggle.click()
    qtbot.waitUntil(lambda: "站内热度: 99" in window.metadata_view.toPlainText(), timeout=1000)
    assert "TMDB ID: 1" not in window.metadata_view.toPlainText()
    assert "原始简介" in window.metadata_view.toPlainText()


def test_player_window_metadata_original_toggle_uses_late_resolved_detail_as_original_snapshot(qtbot) -> None:
    class DetailResolvingController(FakePlayerController):
        def resolve_play_item_detail(self, session, play_item):
            if not play_item.vod_id or session.detail_resolver is None:
                return None
            resolved_vod = session.detail_resolver(play_item)
            session.resolved_vod_by_id[play_item.vod_id] = resolved_vod
            play_item.url = resolved_vod.items[0].url if resolved_vod.items else resolved_vod.vod_play_url
            return resolved_vod

    release_detail_resolution = threading.Event()

    def detail_resolver(item: PlayItem) -> VodItem:
        assert release_detail_resolution.wait(timeout=1)
        return VodItem(
            vod_id=item.vod_id,
            vod_name="站内标题",
            vod_content="站内简介",
            items=[PlayItem(title=item.title, url=item.url, vod_id=item.vod_id)],
        )

    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="原始标题", vod_content="原始简介"),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8", vod_id="ep-1")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        detail_resolver=detail_resolver,
        metadata_hydrator=lambda _session: VodItem(
            vod_id="movie-1",
            vod_name="刮削后的标题",
            vod_year="2026",
            vod_content="刮削后的简介",
        ),
    )
    window = PlayerWindow(DetailResolvingController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    qtbot.waitUntil(lambda: "刮削后的简介" in window.metadata_view.toPlainText(), timeout=1000)

    release_detail_resolution.set()
    qtbot.waitUntil(lambda: "ep-1" in window.session.resolved_vod_by_id, timeout=1000)
    window._metadata_original_toggle.click()

    qtbot.waitUntil(lambda: "站内简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert "刮削后的简介" not in window.metadata_view.toPlainText()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_original_toggle_restores_original_item_detail_fields tests/test_player_window_ui.py::test_player_window_metadata_original_toggle_uses_late_resolved_detail_as_original_snapshot -q`

Expected: FAIL because the original snapshot is not updated on non-metadata detail resolution and current-item `detail_fields` are overwritten without any original-value cache.

- [ ] **Step 3: Write the minimal snapshot/update implementation**

```python
# src/atv_player/ui/player_window.py
def _snapshot_item_detail_fields(self, item: PlayItem) -> None:
    if self.session is None:
        return
    key = self._playlist_identity_key(item)
    if key not in self.session.original_item_detail_fields_by_key:
        self.session.original_item_detail_fields_by_key[key] = deepcopy(item.detail_fields)

def _build_original_metadata_snapshot(self, vod: VodItem) -> VodItem:
    snapshot = self._clone_metadata_snapshot(vod)
    current_item = self._current_play_item()
    if self.session is not None and current_item is not None:
        key = self._playlist_identity_key(current_item)
        cached_fields = self.session.original_item_detail_fields_by_key.get(key)
        if cached_fields:
            snapshot.detail_fields = deepcopy(cached_fields)
    return snapshot

def _update_original_metadata_snapshot(self, vod: VodItem) -> None:
    if self.session is None:
        return
    self.session.original_vod = self._build_original_metadata_snapshot(vod)
    self._refresh_metadata_original_toggle()

def _current_detail_fields(self) -> list[PlaybackDetailField]:
    if self.session is None:
        return []
    if self.session.show_original_metadata and self.session.original_vod is not None:
        return list(self.session.original_vod.detail_fields)
    if 0 <= self.current_index < len(self.session.playlist):
        item_fields = self.session.playlist[self.current_index].detail_fields
        if item_fields:
            return list(item_fields)
    return list(self.session.vod.detail_fields)

def _apply_resolved_vod(self, resolved_vod: VodItem) -> None:
    if self.session is None:
        return
    self.session.vod = resolved_vod
    self._update_original_metadata_snapshot(resolved_vod)
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()
```

```python
# src/atv_player/ui/player_window.py
def open_session(self, session, start_paused: bool = False) -> None:
    ...
    current_item = session.playlist[session.start_index] if 0 <= session.start_index < len(session.playlist) else None
    if current_item is not None:
        self._snapshot_item_detail_fields(current_item)
    session.original_vod = self._build_original_metadata_snapshot(session.vod)
    session.show_original_metadata = False
    ...

def _handle_metadata_hydration_succeeded(self, request_id: int, updated_vod: VodItem | None) -> None:
    ...
    self.session.vod = updated_vod
    self._refresh_metadata_original_toggle()
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()

def _handle_metadata_scrape_apply_succeeded(self, request_id: int, updated_vod: VodItem, candidate) -> None:
    ...
    if 0 <= self.current_index < len(self.session.playlist):
        current_item = self.session.playlist[self.current_index]
        self._snapshot_item_detail_fields(current_item)
        current_item.detail_fields = list(updated_vod.detail_fields)
    self.session.vod = updated_vod
    self._refresh_metadata_original_toggle()
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()
```

- [ ] **Step 4: Run the tests again to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_original_toggle_restores_original_item_detail_fields tests/test_player_window_ui.py::test_player_window_metadata_original_toggle_uses_late_resolved_detail_as_original_snapshot -q`

Expected: PASS

- [ ] **Step 5: Run the existing metadata regression slice**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_metadata_hydration_survives_late_detail_resolution_overwrite tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_replaces_current_item_detail_fields tests/test_player_window_ui.py::test_player_window_metadata_scrape_dialog_reuses_cached_auto_hydration_results -q`

Expected: PASS and existing enhanced-detail behavior stays intact while original-view restoration is added.

- [ ] **Step 6: Commit the snapshot-preservation changes**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: preserve original metadata details in player"
```

### Task 3: Finalize Toggle Lifecycle, Visibility, And Session Reset Behavior

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing lifecycle tests**

```python
def test_player_window_hides_metadata_original_toggle_when_detail_panel_is_closed(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
            return None

        def set_speed(self, value: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 0

    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(vod_id="v1", vod_name="增强标题", vod_year="2024", vod_content="增强简介"),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(session)
    qtbot.waitUntil(lambda: window._metadata_original_toggle.isHidden() is False, timeout=1000)

    window.toggle_details_button.click()

    assert window._metadata_original_toggle.isHidden() is True

    window.toggle_details_button.click()

    assert window._metadata_original_toggle.isHidden() is False


def test_player_window_open_session_resets_metadata_original_toggle_to_enhanced_view(qtbot) -> None:
    class FakeVideo:
        def load(self, url: str, pause: bool = False, start_seconds: int = 0, headers: dict[str, str] | None = None) -> None:
            return None

        def set_speed(self, value: float) -> None:
            return None

        def set_volume(self, value: int) -> None:
            return None

        def position_seconds(self) -> int:
            return 0

    first = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(vod_id="v1", vod_name="增强标题", vod_year="2024", vod_content="增强简介"),
    )
    second = PlayerSession(
        vod=VodItem(vod_id="v2", vod_name="第二个标题", vod_year="2025", vod_content="第二个简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/2.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda _session: VodItem(vod_id="v2", vod_name="第二个增强标题", vod_year="2025", vod_content="第二个增强简介"),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()

    window.open_session(first)
    qtbot.waitUntil(lambda: "增强简介" in window.metadata_view.toPlainText(), timeout=1000)
    window._metadata_original_toggle.click()
    qtbot.waitUntil(lambda: "原始简介" in window.metadata_view.toPlainText(), timeout=1000)

    window.open_session(second)

    qtbot.waitUntil(lambda: "第二个增强简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert window._metadata_original_toggle.isChecked() is False
    assert "第二个简介" not in window.metadata_view.toPlainText()
```

- [ ] **Step 2: Run the lifecycle tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_metadata_original_toggle_when_detail_panel_is_closed tests/test_player_window_ui.py::test_player_window_open_session_resets_metadata_original_toggle_to_enhanced_view -q`

Expected: FAIL because the toggle visibility is not recomputed from detail-panel visibility and session open does not fully reset the original-view state.

- [ ] **Step 3: Write the minimal lifecycle implementation**

```python
# src/atv_player/ui/player_window.py
def _apply_visibility_state(self) -> None:
    ...
    self.details.setHidden(is_fullscreen or not metadata_visible)
    self.metadata_section.setHidden(is_fullscreen or not metadata_visible)
    self.log_section.setHidden(is_fullscreen or not log_visible)
    self._refresh_metadata_original_toggle()
    self._update_log_section_max_height()

def open_session(self, session, start_paused: bool = False) -> None:
    ...
    session.show_original_metadata = False
    ...
    self._render_metadata()
    self._render_detail_fields()
    ...
    self._render_playlist_source_combos()
    self._render_playlist_title_tabs()
    self._render_playlist_items()
    self._render_detail_actions()
    self._refresh_metadata_original_toggle()
```

- [ ] **Step 4: Run the lifecycle tests again to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_metadata_original_toggle_when_detail_panel_is_closed tests/test_player_window_ui.py::test_player_window_open_session_resets_metadata_original_toggle_to_enhanced_view -q`

Expected: PASS

- [ ] **Step 5: Run the full focused verification slice**

Run: `uv run pytest tests/test_player_window_ui.py -k \"metadata_original_toggle or metadata_hydration_survives_late_detail_resolution_overwrite or metadata_scrape_apply_replaces_current_item_detail_fields\" -q`

Expected: PASS with the new toggle coverage plus the existing metadata/player regressions staying green.

- [ ] **Step 6: Commit the lifecycle polish**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "test: cover player original metadata toggle lifecycle"
```
