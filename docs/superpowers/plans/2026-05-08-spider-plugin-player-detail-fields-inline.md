# Spider Plugin Inline Player Detail Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render spider-plugin `ext` detail fields inside the existing player metadata text block, immediately after the fixed metadata rows and before `简介`, while keeping item-level override and collection-level fallback behavior.

**Architecture:** Keep the existing `PlaybackDetailField`, `VodItem.detail_fields`, and `PlayItem.detail_fields` data flow untouched. Replace the standalone `detail_fields_widget` UI path with inline string generation inside `PlayerWindow._format_metadata_text()`, then update tests and documentation to assert metadata text ordering instead of separate widget behavior.

**Tech Stack:** Python, dataclasses, PySide6, pytest

---

## File Map

- `src/atv_player/ui/player_window.py`
  - Remove the dedicated custom-detail widget and helper methods.
  - Inline `detail_fields` rendering into `_format_metadata_text()`.
  - Reuse existing metadata refresh paths.
- `tests/test_player_window_ui.py`
  - Replace standalone-widget assertions with `metadata_view` text assertions.
  - Keep override and fallback coverage.
- `docs/python-spider-plugin-development-guide.md`
  - Update the rendering description from standalone widget language to inline metadata language.

Files intentionally unchanged:

- `src/atv_player/models.py`
- `src/atv_player/plugins/controller.py`
- `tests/test_spider_plugin_controller.py`

Those already implement the desired `ext` normalization and storage behavior.

### Task 1: Replace player-window widget tests with failing metadata-text tests

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Rewrite the detail-field UI tests to assert `metadata_view` text**

In `tests/test_player_window_ui.py`, replace these existing tests:

- `test_player_window_shows_collection_level_detail_fields_on_open_session`
- `test_player_window_hides_detail_fields_widget_when_no_fields_exist`
- `test_player_window_prefers_current_item_detail_fields_over_vod_fields`
- `test_player_window_falls_back_to_vod_detail_fields_when_switching_to_item_without_override`
- `test_player_window_replaces_collection_detail_fields_after_spider_playback_loader_resolves_item_fields`

with these metadata-based versions:

```python
def test_player_window_inlines_collection_level_detail_fields_into_metadata_text(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            type_name="剧情",
            vod_content="简介文本",
            detail_fields=[PlaybackDetailField(label="播放", value="12万")],
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window.open_session(session)

    assert window.metadata_view.toPlainText() == (
        "名称: Movie\n"
        "类型: 剧情\n"
        "年代:\n"
        "地区:\n"
        "语言:\n"
        "评分:\n"
        "导演:\n"
        "演员:\n"
        "豆瓣ID:\n"
        "播放: 12万\n"
        "\n"
        "简介:\n"
        "简介文本"
    )


def test_player_window_omits_inline_detail_field_lines_when_no_fields_exist(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie", type_name="剧情", vod_content="简介"),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window.open_session(session)

    assert "播放:" not in window.metadata_view.toPlainText()
    assert window.metadata_view.toPlainText().endswith("简介:\n简介")


def test_player_window_prefers_current_item_detail_fields_inside_metadata_text(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="series-1",
            vod_name="Series",
            type_name="剧情",
            vod_content="简介文本",
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
    )

    window.open_session(session)

    assert "播放: 18万" in window.metadata_view.toPlainText()
    assert "播放: 12万" not in window.metadata_view.toPlainText()


def test_player_window_falls_back_to_vod_detail_fields_inside_metadata_text(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    session = PlayerSession(
        vod=VodItem(
            vod_id="series-1",
            vod_name="Series",
            type_name="剧情",
            vod_content="简介文本",
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
    )

    window.open_session(session)
    window._play_item_at_index(1)

    assert "播放: 12万" in window.metadata_view.toPlainText()
    assert "播放: 18万" not in window.metadata_view.toPlainText()


def test_player_window_replaces_collection_detail_fields_inside_metadata_after_spider_playback_loader(qtbot) -> None:
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
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    assert "播放: 12万" in window.metadata_view.toPlainText()
    assert "更新: 2026-05-08" in window.metadata_view.toPlainText()

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])
    window._render_metadata()

    assert "播放: 18万" in window.metadata_view.toPlainText()
    assert "热度: 95" in window.metadata_view.toPlainText()
    assert "更新: 2026-05-08" not in window.metadata_view.toPlainText()
```

- [ ] **Step 2: Run the rewritten player-window tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "inline_collection_level_detail_fields or omits_inline_detail_field_lines or prefers_current_item_detail_fields_inside_metadata_text or falls_back_to_vod_detail_fields_inside_metadata_text or replaces_collection_detail_fields_inside_metadata_after_spider_playback_loader" -v
```

Expected:

```text
FAIL ... test_player_window_inlines_collection_level_detail_fields_into_metadata_text
FAIL ... test_player_window_omits_inline_detail_field_lines_when_no_fields_exist
FAIL ... test_player_window_prefers_current_item_detail_fields_inside_metadata_text
FAIL ... test_player_window_falls_back_to_vod_detail_fields_inside_metadata_text
FAIL ... test_player_window_replaces_collection_detail_fields_inside_metadata_after_spider_playback_loader
```

The failure should show that `metadata_view` still lacks the inline `播放: ...` rows because rendering still uses the standalone widget path.

- [ ] **Step 3: Commit the failing test rewrite**

Run:

```bash
git add tests/test_player_window_ui.py
git commit -m "test: expect inline spider detail fields in metadata"
```

Expected:

```text
[branch-name ...] test: expect inline spider detail fields in metadata
```

### Task 2: Remove the standalone widget and inline `detail_fields` into metadata text

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Remove the standalone widget creation and helper methods**

In `src/atv_player/ui/player_window.py`, remove:

- the `PlaybackDetailField` import if it becomes unused outside helper signatures
- `self.detail_fields_widget`
- `self.detail_fields_view`
- `_current_detail_fields()`
- `_format_detail_fields_text()`
- `_render_detail_fields()`

Delete the widget construction block:

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

Delete all calls to:

```python
self._render_detail_fields()
```

The metadata block will become the single rendering surface.

- [ ] **Step 2: Add inline field selection and rendering helpers**

Still in `src/atv_player/ui/player_window.py`, add these helpers near `_format_metadata_text()`:

```python
    def _current_metadata_detail_fields(self) -> list[tuple[str, str]]:
        if self.session is None:
            return []
        if 0 <= self.current_index < len(self.session.playlist):
            item_fields = self.session.playlist[self.current_index].detail_fields
            if item_fields:
                return [(field.label, field.value) for field in item_fields]
        return [(field.label, field.value) for field in self.session.vod.detail_fields]

    def _inline_detail_field_lines(self) -> list[str]:
        return [f"{label}: {value}" for label, value in self._current_metadata_detail_fields()]
```

- [ ] **Step 3: Inline the field lines inside `_format_metadata_text()`**

Update `_format_metadata_text()` to insert custom lines before `简介`.

For the normal-detail branch, change the tail of the function to:

```python
        lines = [f"{label}: {value}".rstrip() for label, value in rows]
        lines.extend(self._inline_detail_field_lines())
        lines.append("")
        lines.append("简介:")
        lines.append(vod.vod_content)
        return "\n".join(lines)
```

For the bilibili branch, keep the existing row filtering, then use the same `lines.extend(self._inline_detail_field_lines())` insertion before `简介`.

For the live branch that returns row-based metadata, use:

```python
            lines = [f"{label}: {value}".rstrip() for label, value in rows]
            lines.extend(self._inline_detail_field_lines())
            return "\n".join(lines)
```

Do not add inline fields to the EPG-specialized live layout in this change.

- [ ] **Step 4: Reuse existing metadata refresh paths**

Do not add new refresh methods. Ensure metadata rerenders still happen through existing calls:

- `open_session()`
- `_apply_resolved_vod()`
- `_play_item_at_index()`

In `_play_item_at_index()`, add a metadata rerender immediately after changing `self.current_index`:

```python
            self.playlist.setCurrentRow(self.current_index)
            self._refresh_danmaku_source_entry_points()
            self._render_metadata()
            self._render_detail_actions()
```

In the playback-loader test path where item-level fields change after `playerContent()`, continue using the existing explicit metadata refresh from the test. No extra async hook is required for this plan beyond the current metadata rerender points.

- [ ] **Step 5: Run the rewritten player-window tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "inline_collection_level_detail_fields or omits_inline_detail_field_lines or prefers_current_item_detail_fields_inside_metadata_text or falls_back_to_vod_detail_fields_inside_metadata_text or replaces_collection_detail_fields_inside_metadata_after_spider_playback_loader" -v
```

Expected:

```text
PASSED ... test_player_window_inlines_collection_level_detail_fields_into_metadata_text
PASSED ... test_player_window_omits_inline_detail_field_lines_when_no_fields_exist
PASSED ... test_player_window_prefers_current_item_detail_fields_inside_metadata_text
PASSED ... test_player_window_falls_back_to_vod_detail_fields_inside_metadata_text
PASSED ... test_player_window_replaces_collection_detail_fields_inside_metadata_after_spider_playback_loader
```

- [ ] **Step 6: Commit the player-window implementation**

Run:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: inline spider detail fields in metadata"
```

Expected:

```text
[branch-name ...] feat: inline spider detail fields in metadata
```

### Task 3: Update docs and run focused regressions

**Files:**
- Modify: `docs/python-spider-plugin-development-guide.md`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Update the plugin-facing documentation to describe inline rendering**

In `docs/python-spider-plugin-development-guide.md`, replace the existing custom-detail-fields rendering bullets:

```markdown
- rows are display-only and are rendered as `label: value`
```

with:

```markdown
- rows are display-only and are rendered as `label: value`
- these rows are inserted into the existing player metadata text block
- on normal detail pages, they appear after `豆瓣ID` and before `简介`
```

If the document currently mentions a sidebar widget or separate block for custom fields, delete that wording.

- [ ] **Step 2: Run focused controller + player regressions**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py -k "detail_actions or metadata_view or detail_fields or detailcontent_ext or playercontent_ext" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_detailcontent_ext_to_vod_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_ext_to_current_play_item_detail_fields
PASSED tests/test_spider_plugin_controller.py::test_spider_controller_clears_stale_item_detail_fields_when_playercontent_ext_is_invalid
PASSED ... the rewritten metadata-based player-window tests
PASSED ... existing metadata/detail-action coverage selected by the filter
```

- [ ] **Step 3: Run one broader metadata regression slice**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "metadata or detail_actions" -v
```

Expected:

```text
... existing metadata tests remain PASS ...
... existing detail action tests remain PASS ...
... new inline detail field tests remain PASS ...
```

- [ ] **Step 4: Commit the documentation update**

Run:

```bash
git add docs/python-spider-plugin-development-guide.md
git commit -m "docs: describe inline spider detail fields"
```

Expected:

```text
[branch-name ...] docs: describe inline spider detail fields
```

## Self-Review

- Spec coverage:
  - keep controller normalization as-is: covered by File Map and Task 3 regressions
  - remove standalone widget: covered by Task 2
  - inline after `豆瓣ID` and before `简介`: covered by Task 2
  - item override and collection fallback: covered by Task 1 and Task 2
  - docs reflect inline rendering: covered by Task 3
- Placeholder scan:
  - no `TODO`, `TBD`, or deferred implementation markers remain
  - commands, failure expectations, and code snippets are concrete
- Type consistency:
  - shared type remains `PlaybackDetailField`
  - storage fields remain `VodItem.detail_fields` and `PlayItem.detail_fields`
  - new helper names are `_current_metadata_detail_fields()` and `_inline_detail_field_lines()`
