# Spider Plugin Player Detail Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add spider-plugin custom detail fields so `detailContent().ext` shows collection-level rows in the player sidebar and `playerContent().ext` can override them per current play item.

**Architecture:** Keep custom detail fields as explicit structured data instead of concatenating them into the existing metadata text block. Store collection-level rows on `VodItem`, item-level rows on `PlayItem`, normalize both payload sources in `SpiderPluginController`, and render a dedicated read-only block in `PlayerWindow` with whole-list override semantics.

**Tech Stack:** Python, dataclasses, PySide6, pytest

---

## File Map

- `src/atv_player/models.py`
  - Add the shared `PlaybackDetailField` dataclass.
  - Extend `VodItem` and `PlayItem` with `detail_fields`.
- `src/atv_player/plugins/controller.py`
  - Add `ext` normalization helpers.
  - Map collection-level fields from `detailContent()`.
  - Map item-level fields from `playerContent()`.
- `src/atv_player/ui/player_window.py`
  - Add a dedicated custom-detail-fields widget to the sidebar.
  - Refresh it during session open, episode switches, async item resolution, and resolved-vod replacement.
- `tests/test_spider_plugin_controller.py`
  - Add controller coverage for `ext` normalization, fallback, and overwrite behavior.
- `tests/test_player_window_ui.py`
  - Add UI coverage for initial render, hide behavior, item override, and fallback.
- `docs/python-spider-plugin-development-guide.md`
  - Document `detailContent().ext`, `playerContent().ext`, and override behavior.

### Task 1: Add failing controller tests for `ext` normalization

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing collection-level and item-level controller tests**

Add the following spider fixture near `ActionPayloadSpider` in `tests/test_spider_plugin_controller.py`:

```python
class DetailFieldPayloadSpider(FakeSpider):
    def detailContent(self, ids):
        return {
            "list": [
                {
                    "vod_id": ids[0],
                    "vod_name": "红果短剧",
                    "vod_play_from": "默认线$$$备用线",
                    "vod_play_url": "第1集$/play/1#第2集$/play/2",
                    "ext": [
                        {"label": "播放", "value": "12万"},
                        {"label": "更新", "value": "2026-05-08"},
                        {"label": "", "value": "bad"},
                        {"label": "空值", "value": ""},
                    ],
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        payload = {
            "parse": 0,
            "url": f"https://stream.example{id}.m3u8",
        }
        if id == "/play/1":
            payload["ext"] = [
                {"label": "播放", "value": "18万"},
                {"label": "热度", "value": "95"},
            ]
        elif id == "/play/2":
            payload["ext"] = [
                {"label": "播放", "value": " "},
                {"label": "", "value": "ignored"},
            ]
        return payload
```

Add the following tests after the existing detail-action tests:

```python
def test_spider_controller_maps_detailcontent_ext_to_vod_detail_fields() -> None:
    controller = SpiderPluginController(DetailFieldPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.vod.detail_fields == [
        PlaybackDetailField(label="播放", value="12万"),
        PlaybackDetailField(label="更新", value="2026-05-08"),
    ]
    assert request.playlist[0].detail_fields == []


def test_spider_controller_maps_playercontent_ext_to_current_play_item_detail_fields() -> None:
    controller = SpiderPluginController(DetailFieldPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")
    session = PlayerController(type("Api", (), {"get_history": lambda self, _key: None})()).create_session(
        request.vod,
        request.playlist,
        request.clicked_index,
        playlists=request.playlists,
        playlist_index=request.playlist_index,
        playback_loader=request.playback_loader,
        async_playback_loader=request.async_playback_loader,
        detail_action_runner=request.detail_action_runner,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])

    assert session.playlist[0].detail_fields == [
        PlaybackDetailField(label="播放", value="18万"),
        PlaybackDetailField(label="热度", value="95"),
    ]


def test_spider_controller_clears_stale_item_detail_fields_when_playercontent_ext_is_invalid() -> None:
    controller = SpiderPluginController(DetailFieldPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")
    session = PlayerController(type("Api", (), {"get_history": lambda self, _key: None})()).create_session(
        request.vod,
        request.playlist,
        request.clicked_index,
        playlists=request.playlists,
        playlist_index=request.playlist_index,
        playback_loader=request.playback_loader,
        async_playback_loader=request.async_playback_loader,
        detail_action_runner=request.detail_action_runner,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])
    assert session.playlist[0].detail_fields == [
        PlaybackDetailField(label="播放", value="18万"),
        PlaybackDetailField(label="热度", value="95"),
    ]

    second_item = session.playlist[1]
    second_item.detail_fields = [PlaybackDetailField(label="旧值", value="stale")]
    session.playback_loader(second_item)

    assert second_item.detail_fields == []
```

- [ ] **Step 2: Run the focused controller tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "detail_fields or detailcontent_ext or playercontent_ext" -v
```

Expected:

```text
FAIL tests/test_spider_plugin_controller.py::test_spider_controller_maps_detailcontent_ext_to_vod_detail_fields
FAIL tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_ext_to_current_play_item_detail_fields
FAIL tests/test_spider_plugin_controller.py::test_spider_controller_clears_stale_item_detail_fields_when_playercontent_ext_is_invalid
E   NameError: name 'PlaybackDetailField' is not defined
```

- [ ] **Step 3: Commit the failing test additions**

Run:

```bash
git add tests/test_spider_plugin_controller.py
git commit -m "test: cover spider plugin detail field payloads"
```

Expected:

```text
[branch-name ...] test: cover spider plugin detail field payloads
```

### Task 2: Implement shared detail-field models and controller normalization

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Add the shared dataclass and storage fields**

In `src/atv_player/models.py`, add the new dataclass after `PlaybackDetailAction`:

```python
@dataclass(slots=True)
class PlaybackDetailField:
    label: str
    value: str
```

Extend `PlayItem`:

```python
    detail_actions: list[PlaybackDetailAction] = field(default_factory=list)
    detail_fields: list[PlaybackDetailField] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
```

Extend `VodItem`:

```python
    dbid: int = 0
    type: int = 0
    detail_fields: list[PlaybackDetailField] = field(default_factory=list)
    items: list[PlayItem] = field(default_factory=list)
```

Update the import list in `tests/test_spider_plugin_controller.py`:

```python
from atv_player.models import CategoryFilter, CategoryFilterOption, PlayItem, PlaybackDetailAction, PlaybackDetailField
```

- [ ] **Step 2: Add the normalization helper in the spider controller**

In `src/atv_player/plugins/controller.py`, import the new model:

```python
from atv_player.models import (
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    ExternalSubtitleOption,
    OpenPlayerRequest,
    PlayItem,
    PlaybackDetailAction,
    PlaybackDetailField,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)
```

Add the helper directly below `_map_playback_detail_actions()`:

```python
def _map_playback_detail_fields(payload: object) -> list[PlaybackDetailField]:
    if not isinstance(payload, list):
        return []
    fields: list[PlaybackDetailField] = []
    for raw_field in payload:
        if not isinstance(raw_field, Mapping):
            continue
        label = str(raw_field.get("label") or "").strip()
        value = str(raw_field.get("value") or "").strip()
        if not label or not value:
            continue
        fields.append(PlaybackDetailField(label=label, value=value))
    return fields
```

- [ ] **Step 3: Map collection-level and item-level `ext` fields**

In `SpiderPluginController.build_request()`, set the collection-level fields immediately after `detail = _map_vod_item(raw_detail)`:

```python
        detail.detail_fields = _map_playback_detail_fields(raw_detail.get("ext") if isinstance(raw_detail, Mapping) else None)
```

In the direct-play branch of the playback loader, overwrite item-level fields alongside the existing action merge:

```python
        item.headers = _normalize_headers(payload.get("header"))
        item.detail_fields = _map_playback_detail_fields(payload.get("ext"))
        item.detail_actions = _merge_playback_detail_actions(
            item.detail_actions,
            _map_playback_detail_actions(payload.get("actions")),
        )
```

Keep the overwrite exact. Do not merge the new item-level fields with stale previous values.

- [ ] **Step 4: Run the focused controller tests to verify they pass**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "detail_fields or detailcontent_ext or playercontent_ext" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_detailcontent_ext_to_vod_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_ext_to_current_play_item_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_clears_stale_item_detail_fields_when_playercontent_ext_is_invalid
```

- [ ] **Step 5: Commit the model and controller implementation**

Run:

```bash
git add src/atv_player/models.py src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: map spider plugin player detail fields"
```

Expected:

```text
[branch-name ...] feat: map spider plugin player detail fields
```

### Task 3: Add failing player-window tests for rendering, override, and fallback

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing sidebar rendering tests**

In `tests/test_player_window_ui.py`, update the models import to include `PlaybackDetailField`:

```python
from atv_player.models import (
    AppConfig,
    ExternalSubtitleOption,
    ExternalSubtitleSelection,
    PlayItem,
    PlaybackDetailAction,
    PlaybackDetailField,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)
```

Add the following tests near the existing detail-sidebar tests around `detail_actions_widget` and metadata rendering:

```python
def test_player_window_shows_collection_level_detail_fields_on_open_session(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
    )

    window.open_session(session)

    assert window.detail_fields_widget.isHidden() is False
    assert window.detail_fields_view.toPlainText() == "播放: 12万"


def test_player_window_hides_detail_fields_widget_when_no_fields_exist(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(make_player_session(start_index=0))

    assert window.detail_fields_widget.isHidden() is True
    assert window.detail_fields_view.toPlainText() == ""


def test_player_window_prefers_current_item_detail_fields_over_vod_fields(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="series-1",
            vod_name="Series",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
        ),
        playlist=[
            PlayItem(
                title="Episode 1",
                url="http://m/1.m3u8",
                detail_fields=[PlaybackDetailField(label="播放", value="18万")],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
    )

    window.open_session(session)

    assert window.detail_fields_view.toPlainText() == "播放: 18万"


def test_player_window_falls_back_to_vod_detail_fields_when_switching_to_item_without_override(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="series-1",
            vod_name="Series",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
        ),
        playlist=[
            PlayItem(
                title="Episode 1",
                url="http://m/1.m3u8",
                detail_fields=[PlaybackDetailField(label="播放", value="18万")],
            ),
            PlayItem(title="Episode 2", url="http://m/2.m3u8"),
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
    )

    window.open_session(session)
    window._play_item_at_index(1)

    assert window.detail_fields_view.toPlainText() == "播放: 12万"
```

- [ ] **Step 2: Run the focused player-window tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "detail_fields_widget or collection_level_detail_fields or prefers_current_item_detail_fields" -v
```

Expected:

```text
FAIL tests/test_player_window_ui.py::test_player_window_shows_collection_level_detail_fields_on_open_session
FAIL tests/test_player_window_ui.py::test_player_window_hides_detail_fields_widget_when_no_fields_exist
FAIL tests/test_player_window_ui.py::test_player_window_prefers_current_item_detail_fields_over_vod_fields
FAIL tests/test_player_window_ui.py::test_player_window_falls_back_to_vod_detail_fields_when_switching_to_item_without_override
E   AttributeError: 'PlayerWindow' object has no attribute 'detail_fields_widget'
```

- [ ] **Step 3: Commit the failing player-window tests**

Run:

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover player sidebar detail field rendering"
```

Expected:

```text
[branch-name ...] test: cover player sidebar detail field rendering
```

### Task 4: Implement the player sidebar detail-field widget and refresh paths

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add the sidebar widget and render helpers**

In `src/atv_player/ui/player_window.py`, import the new model:

```python
from atv_player.models import (
    ExternalSubtitleOption,
    ExternalSubtitleSelection,
    PlayItem,
    PlaybackDetailAction,
    PlaybackDetailField,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)
```

Inside `__init__`, create the widget between `detail_actions_widget` and the `"影片详情"` label:

```python
        self.detail_fields_widget = QWidget()
        detail_fields_layout = QVBoxLayout(self.detail_fields_widget)
        detail_fields_layout.setContentsMargins(0, 0, 0, 0)
        detail_fields_layout.setSpacing(4)
        self.detail_fields_view = QTextEdit()
        self.detail_fields_view.setReadOnly(True)
        self.detail_fields_view.setMaximumHeight(96)
        self.detail_fields_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_fields_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_fields_layout.addWidget(self.detail_fields_view)
        details_layout.addWidget(self.detail_fields_widget)
```

Add these helpers near `_current_detail_actions()` and `_render_detail_actions()`:

```python
    def _current_detail_fields(self) -> list[PlaybackDetailField]:
        if self.session is None:
            return []
        if 0 <= self.current_index < len(self.session.playlist):
            item_fields = self.session.playlist[self.current_index].detail_fields
            if item_fields:
                return item_fields
        return self.session.vod.detail_fields

    def _format_detail_fields_text(self, fields: list[PlaybackDetailField]) -> str:
        return "\n".join(f"{field.label}: {field.value}" for field in fields)

    def _render_detail_fields(self) -> None:
        fields = self._current_detail_fields()
        self.detail_fields_widget.setHidden(not fields)
        self.detail_fields_view.setPlainText(self._format_detail_fields_text(fields) if fields else "")
```

- [ ] **Step 2: Refresh the widget in all required sidebar update paths**

Call `_render_detail_fields()` in these places:

```python
    def open_session(self, session, start_paused: bool = False) -> None:
        ...
        self._render_metadata()
        self._render_detail_fields()
        self._reset_log()
        ...
        self._render_detail_actions()
```

```python
    def _apply_resolved_vod(self, resolved_vod: VodItem) -> None:
        if self.session is None:
            return
        self.session.vod = resolved_vod
        self._render_poster()
        self._render_metadata()
        self._render_detail_fields()
```

```python
    def _play_item_at_index(...):
        ...
        self.playlist.setCurrentRow(self.current_index)
        self._refresh_danmaku_source_entry_points()
        self._render_detail_fields()
        self._render_detail_actions()
        self._load_current_item(...)
```

If the player has a handler that updates the current item after async playback resolution, call `_render_detail_fields()` there immediately after item-level `detail_fields` can change.

- [ ] **Step 3: Add a focused async override test if the helper call is missing**

If the existing tests do not already cover the post-resolution refresh, add this test:

```python
def test_player_window_rerenders_detail_fields_after_current_item_resolution(qtbot) -> None:
    controller = RecordingPlayerController()
    window = PlayerWindow(controller)
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="series-1",
            vod_name="Series",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
        ),
        playlist=[PlayItem(title="Episode 1", url="", vod_id="ep-1")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        detail_resolver=lambda _item: VodItem(
            vod_id="ep-1",
            vod_name="Series",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
            items=[
                PlayItem(
                    title="Episode 1",
                    url="http://m/1.m3u8",
                    vod_id="ep-1",
                    detail_fields=[PlaybackDetailField(label="播放", value="18万")],
                )
            ],
        ),
    )

    window.open_session(session)

    qtbot.waitUntil(lambda: window.detail_fields_view.toPlainText() == "播放: 18万")
```

Use this test only if the previous four tests do not force the needed refresh path.

- [ ] **Step 4: Run the focused player-window tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "detail_fields_widget or collection_level_detail_fields or prefers_current_item_detail_fields" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_shows_collection_level_detail_fields_on_open_session
PASSED tests/test_player_window_ui.py::test_player_window_hides_detail_fields_widget_when_no_fields_exist
PASSED tests/test_player_window_ui.py::test_player_window_prefers_current_item_detail_fields_over_vod_fields
PASSED tests/test_player_window_ui.py::test_player_window_falls_back_to_vod_detail_fields_when_switching_to_item_without_override
```

- [ ] **Step 5: Commit the player-window implementation**

Run:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: show spider plugin detail fields in player sidebar"
```

Expected:

```text
[branch-name ...] feat: show spider plugin detail fields in player sidebar
```

### Task 5: Document the new plugin payload and run final verification

**Files:**
- Modify: `docs/python-spider-plugin-development-guide.md`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Update the plugin-facing documentation**

Add this section to `docs/python-spider-plugin-development-guide.md` after the action-model overview:

```markdown
## Custom Detail Fields

Python spider plugins can also provide read-only custom detail rows in the player sidebar.

Supported payload shape:

```python
"ext": [
    {"label": "播放", "value": "12万"},
    {"label": "更新", "value": "2026-05-08"},
]
```
```

Add these rules below that snippet:

```markdown
- `detailContent(...).list[0].ext` sets collection-level fields for the whole detail page
- `playerContent(...).ext` sets current-item fields for the active episode or track
- if the current play item has non-empty `playerContent().ext`, those rows replace the collection-level rows
- if the current play item has no valid rows, the player falls back to `detailContent().ext`
- each row must provide non-blank `label` and `value`
- rows are display-only and are rendered as `label: value`
```

- [ ] **Step 2: Run the two focused test files together**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -k "detail_fields or detailcontent_ext or playercontent_ext" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_detailcontent_ext_to_vod_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_ext_to_current_play_item_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_clears_stale_item_detail_fields_when_playercontent_ext_is_invalid
PASSED tests/test_player_window_ui.py::test_player_window_shows_collection_level_detail_fields_on_open_session
PASSED tests/test_player_window_ui.py::test_player_window_hides_detail_fields_widget_when_no_fields_exist
PASSED tests/test_player_window_ui.py::test_player_window_prefers_current_item_detail_fields_over_vod_fields
PASSED tests/test_player_window_ui.py::test_player_window_falls_back_to_vod_detail_fields_when_switching_to_item_without_override
```

- [ ] **Step 3: Run a broader regression slice for the sidebar**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -k "detail_actions or metadata_view or detail_fields" -v
```

Expected:

```text
... existing detail action and metadata tests remain PASS ...
... new detail field tests remain PASS ...
```

- [ ] **Step 4: Commit the documentation and final verification state**

Run:

```bash
git add docs/python-spider-plugin-development-guide.md
git commit -m "docs: describe spider plugin player detail fields"
```

Expected:

```text
[branch-name ...] docs: describe spider plugin player detail fields
```

## Self-Review

- Spec coverage check:
  - collection-level `detailContent().ext`: covered by Tasks 1 and 2
  - item-level `playerContent().ext`: covered by Tasks 1 and 2
  - player override and fallback behavior: covered by Tasks 3 and 4
  - dedicated sidebar rendering block: covered by Task 4
  - plugin-facing docs update: covered by Task 5
- Placeholder scan:
  - no `TODO`, `TBD`, or deferred implementation notes remain
  - commands, code snippets, and expected failures/passes are concrete
- Type consistency:
  - the shared type name is `PlaybackDetailField`
  - model storage names are `VodItem.detail_fields` and `PlayItem.detail_fields`
  - player helpers use `detail_fields_widget`, `detail_fields_view`, `_current_detail_fields()`, and `_render_detail_fields()`
