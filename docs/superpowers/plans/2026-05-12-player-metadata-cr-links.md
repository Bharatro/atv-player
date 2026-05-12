# Player Metadata CR Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let player metadata strings embed `[a=cr:...][/a]` clickable segments, including built-in Bilibili UP-owner links that open the Bilibili tab's `up:<mid>` video list.

**Architecture:** Extend the existing `PlaybackDetailFieldAction` contract with an optional `target`, then reuse the current `metadata_view` anchor-click path to normalize inline metadata links into the same action object the player already dispatches. Keep rendering in `PlayerWindow`, add built-in Bilibili routing in `MainWindow`, and preserve current plugin `category/detail/search/link` behavior when `target` is omitted.

**Tech Stack:** Python, dataclasses, PySide6, pytest

---

## File Map

- `src/atv_player/models.py`
  - Add optional `target` to `PlaybackDetailFieldAction` so inline metadata links and existing detail-field links share one action type.
- `src/atv_player/ui/player_window.py`
  - Parse `[a=cr:<json>/]label[/a]` inside metadata string values.
  - Convert valid segments into internal `atv-player://detail-field?...` anchors.
  - Decode `action_target` during metadata-link clicks and dispatch it through `detail_field_runner`.
- `src/atv_player/ui/main_window.py`
  - Attach a `detail_field_runner` for built-in Bilibili player sessions.
  - Route `target="bilibili"` plus `type="category"` back to the Bilibili tab and page-1 item load.
  - Preserve existing plugin and external-link behavior.
- `tests/test_player_window_ui.py`
  - Add inline metadata rendering and dispatch coverage.
- `tests/test_main_window_ui.py`
  - Add built-in Bilibili metadata-route coverage.
- `docs/python-spider-player-actions.md`
  - Document the new inline metadata markup contract and `target="bilibili"` usage.

Files intentionally unchanged:

- `src/atv_player/controllers/bilibili_controller.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/plugins/controller.py`
- `tests/test_spider_plugin_controller.py`

The feature is a player metadata rendering and main-window routing change, not a controller payload-shape change.

### Task 1: Write failing player-window tests for inline metadata CR links

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add failing inline metadata rendering and dispatch tests**

Append these tests near the existing metadata-link coverage in `tests/test_player_window_ui.py`:

```python
def test_player_window_renders_bilibili_cr_link_inside_metadata_value(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            vod_director='[a=cr:{"target":"bilibili","type":"category","value":"up:378885845"}/]Harold[/a]',
            vod_content="简介文本",
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    html = window.metadata_view.toHtml()
    plain_text = window.metadata_view.toPlainText()
    assert "导演: Harold" in plain_text
    assert "action_target=bilibili" in html
    assert "action_type=category" in html
    assert "action_value=up%3A378885845" in html


def test_player_window_renders_multiple_cr_links_with_plain_separators(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            vod_actor=(
                '[a=cr:{"type":"search","value":"演员1"}/]演员1[/a]'
                " / "
                '[a=cr:{"type":"search","value":"演员2"}/]演员2[/a]'
            ),
            vod_content="简介文本",
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    html = window.metadata_view.toHtml()
    plain_text = window.metadata_view.toPlainText()
    assert "演员: 演员1 / 演员2" in plain_text
    assert html.count("action_type=search") == 2


def test_player_window_degrades_invalid_cr_markup_to_plain_text(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            vod_director='[a=cr:{"target":"bilibili","type":"category"}/]Harold[/a]',
            vod_content="简介文本",
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    html = window.metadata_view.toHtml()
    plain_text = window.metadata_view.toPlainText()
    assert '[a=cr:{"target":"bilibili","type":"category"}/]Harold[/a]' in plain_text
    assert "action_target=bilibili" not in html


def test_player_window_metadata_link_dispatches_action_target(qtbot) -> None:
    clicked: list[PlaybackDetailFieldAction] = []
    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="Movie"),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        detail_field_runner=lambda _item, action: clicked.append(action),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)
    window._handle_metadata_link(
        QUrl(
            "atv-player://detail-field?"
            "action_target=bilibili&action_type=category&action_value=up%3A378885845"
        )
    )

    assert clicked == [
        PlaybackDetailFieldAction(target="bilibili", type="category", value="up:378885845")
    ]
```

- [ ] **Step 2: Run the new player-window tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_cr_link_inside_metadata_value or multiple_cr_links_with_plain_separators or degrades_invalid_cr_markup_to_plain_text or metadata_link_dispatches_action_target" -v
```

Expected:

```text
FAIL tests/test_player_window_ui.py::test_player_window_renders_bilibili_cr_link_inside_metadata_value
FAIL tests/test_player_window_ui.py::test_player_window_renders_multiple_cr_links_with_plain_separators
FAIL tests/test_player_window_ui.py::test_player_window_degrades_invalid_cr_markup_to_plain_text
FAIL tests/test_player_window_ui.py::test_player_window_metadata_link_dispatches_action_target
```

The likely failures are:

- metadata HTML still escapes the literal `[a=cr:...]` string instead of emitting anchors
- `PlaybackDetailFieldAction` does not yet accept `target`
- `_handle_metadata_link()` ignores `action_target`

- [ ] **Step 3: Commit the failing player-window tests**

Run:

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover inline metadata cr links"
```

Expected:

```text
[branch-name ...] test: cover inline metadata cr links
```

### Task 2: Implement inline metadata CR-link parsing and dispatch in the player window

**Files:**
- Modify: `src/atv_player/models.py:75-109,324-350`
- Modify: `src/atv_player/ui/player_window.py:855-882,1296-1336`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Extend the shared detail-field action model with an optional target**

In `src/atv_player/models.py`, change `PlaybackDetailFieldAction` to:

```python
@dataclass(slots=True)
class PlaybackDetailFieldAction:
    type: str
    value: str
    target: str = ""
```

No other data model changes are required because every current caller can keep constructing the action with only `type` and `value`.

- [ ] **Step 2: Add player-window helpers for internal URLs and inline metadata parsing**

In `src/atv_player/ui/player_window.py`, add `import json` and `import re`, then replace the single-purpose detail-field URL helper with a target-aware version plus inline metadata helpers:

```python
_INLINE_METADATA_CR_RE = re.compile(r"\[a=cr:(?P<payload>\{.*?\})/\](?P<label>.*?)\[/a\]", re.DOTALL)


def _metadata_action_url(self, action: PlaybackDetailFieldAction) -> QUrl:
    url = QUrl("atv-player://detail-field")
    query = QUrlQuery()
    if action.target:
        query.addQueryItem("action_target", action.target)
    query.addQueryItem("action_type", action.type)
    query.addQueryItem("action_value", action.value)
    url.setQuery(query)
    return url


def _metadata_action_from_payload(self, payload: object) -> PlaybackDetailFieldAction | None:
    if not isinstance(payload, dict):
        return None
    action_type = str(payload.get("type") or "").strip()
    action_value = str(payload.get("value") or "").strip()
    action_target = str(payload.get("target") or "").strip()
    if not action_type or not action_value:
        return None
    if action_target not in {"", "bilibili"}:
        return None
    return PlaybackDetailFieldAction(type=action_type, value=action_value, target=action_target)


def _render_metadata_value_html(self, value: object) -> str:
    text = str(value or "")
    if not text:
        return ""

    parts: list[str] = []
    start = 0
    for match in _INLINE_METADATA_CR_RE.finditer(text):
        plain_chunk = text[start:match.start()]
        if plain_chunk:
            parts.append(html.escape(plain_chunk).replace("\n", "<br>"))

        action = None
        try:
            payload = json.loads(match.group("payload"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            action = self._metadata_action_from_payload(payload)

        label = match.group("label")
        if action is None:
            parts.append(html.escape(match.group(0)).replace("\n", "<br>"))
        else:
            href = html.escape(self._metadata_action_url(action).toString())
            parts.append(f'<a href="{href}">{html.escape(label)}</a>')
        start = match.end()

    tail = text[start:]
    if tail:
        parts.append(html.escape(tail).replace("\n", "<br>"))
    return "".join(parts)


def _metadata_row_html(self, label: str, value: object) -> str:
    rendered_value = self._render_metadata_value_html(value)
    return f"{html.escape(label)}: {rendered_value}".rstrip()
```

Keep `_detail_field_html()` for structured `detail_fields`, but change it to use `_metadata_action_url(part.action)` instead of the old `_detail_field_action_url(...)`.

- [ ] **Step 3: Decode `action_target` during metadata clicks and route all row values through the new renderer**

Still in `src/atv_player/ui/player_window.py`, update `_handle_metadata_link()` and `_format_metadata_html()`:

```python
def _handle_metadata_link(self, url: QUrl) -> None:
    if url.scheme() != "atv-player" or url.host() != "detail-field":
        return
    query = QUrlQuery(url)
    action_type = query.queryItemValue("action_type").strip()
    action_value = query.queryItemValue("action_value").strip()
    action_target = query.queryItemValue("action_target").strip()
    if not action_type or not action_value:
        return
    if action_target not in {"", "bilibili"}:
        return
    self._run_detail_field_action(
        PlaybackDetailFieldAction(type=action_type, value=action_value, target=action_target)
    )
```

```python
parts = [self._metadata_row_html(label, value) for label, value in rows]
parts.extend(self._detail_field_html(field) for field in self._current_detail_fields())
parts.append("")
parts.append(html.escape("简介:"))
parts.append(self._render_metadata_value_html(vod.vod_content))
return "<br>".join(parts)
```

Make the same row-rendering substitution in both live branches so every value already assembled by `_format_metadata_html()` gets the same inline-link capability.

- [ ] **Step 4: Run the player-window tests and the existing metadata-link regression tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "bilibili_cr_link_inside_metadata_value or multiple_cr_links_with_plain_separators or degrades_invalid_cr_markup_to_plain_text or metadata_link_dispatches_action_target or clickable_detail_field_value_parts_inside_metadata" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_renders_bilibili_cr_link_inside_metadata_value
PASSED tests/test_player_window_ui.py::test_player_window_renders_multiple_cr_links_with_plain_separators
PASSED tests/test_player_window_ui.py::test_player_window_degrades_invalid_cr_markup_to_plain_text
PASSED tests/test_player_window_ui.py::test_player_window_metadata_link_dispatches_action_target
PASSED tests/test_player_window_ui.py::test_player_window_renders_clickable_detail_field_value_parts_inside_metadata
```

- [ ] **Step 5: Commit the player-window implementation**

Run:

```bash
git add src/atv_player/models.py src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: support inline metadata cr links"
```

Expected:

```text
[branch-name ...] feat: support inline metadata cr links
```

### Task 3: Write a failing main-window test for built-in Bilibili metadata routing

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add a failing built-in Bilibili metadata-route test**

In `tests/test_main_window_ui.py`, add this test near the existing detail-field routing tests:

```python
def test_main_window_bilibili_metadata_category_click_loads_builtin_bilibili_results(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class RecordingPlayerWindow:
        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    class RoutedBilibiliController(FakeStaticController):
        def __init__(self) -> None:
            self.category_calls: list[tuple[str, int]] = []

        def load_categories(self):
            return [type("Category", (), {"type_id": "recommend", "type_name": "推荐", "filters": []})()]

        def load_items(self, category_id: str, page: int, filters=None):
            self.category_calls.append((category_id, page))
            return [VodItem(vod_id="bili-1", vod_name="UP视频")], 1

        def build_request(self, vod_id: str):
            return OpenPlayerRequest(
                vod=VodItem(vod_id=vod_id, vod_name="B站详情"),
                playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
                clicked_index=0,
                source_kind="bilibili",
                source_mode="detail",
                source_vod_id=vod_id,
            )

    controller = RoutedBilibiliController()
    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        bilibili_controller=controller,
        config=AppConfig(),
        show_bilibili_tab=True,
    )
    qtbot.addWidget(window)
    request = controller.build_request("BV1xx411c7mD")

    window.open_player(request)
    qtbot.waitUntil(lambda: window.player_window is not None and len(window.player_window.opened) == 1)

    session = window.player_window.opened[0][0]
    runner = session["detail_field_runner"]
    assert callable(runner)

    runner(
        session["playlist"][0],
        PlaybackDetailFieldAction(target="bilibili", type="category", value="up:378885845"),
    )

    qtbot.waitUntil(lambda: controller.category_calls == [("up:378885845", 1)])
    assert window.bilibili_page is not None
    qtbot.waitUntil(lambda: bool(window.bilibili_page.items) and window.bilibili_page.items[0].vod_name == "UP视频")
    assert window.nav_tabs.currentWidget() is window.bilibili_page
```

- [ ] **Step 2: Run the new main-window test to verify it fails**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "bilibili_metadata_category_click_loads_builtin_bilibili_results" -v
```

Expected:

```text
FAIL tests/test_main_window_ui.py::test_main_window_bilibili_metadata_category_click_loads_builtin_bilibili_results
```

The likely failure is that `session["detail_field_runner"]` is `None` for `source_kind="bilibili"` requests because `_prepare_request_for_open()` only wires plugin sessions today.

- [ ] **Step 3: Commit the failing main-window test**

Run:

```bash
git add tests/test_main_window_ui.py
git commit -m "test: cover bilibili metadata route"
```

Expected:

```text
[branch-name ...] test: cover bilibili metadata route
```

### Task 4: Implement built-in Bilibili metadata routing, update docs, and run targeted regressions

**Files:**
- Modify: `src/atv_player/ui/main_window.py:1494-1548`
- Modify: `docs/python-spider-player-actions.md`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add a built-in Bilibili route handler and wire it into player-session preparation**

In `src/atv_player/ui/main_window.py`, add a Bilibili-specific detail-field runner and make `_prepare_request_for_open()` attach it for Bilibili sessions:

```python
def _prepare_request_for_open(self, request: OpenPlayerRequest) -> OpenPlayerRequest:
    if request.detail_field_runner is not None:
        return request
    if request.source_kind == "plugin" and request.source_key:
        context = self._plugin_page_context_by_id(request.source_key)
        if context is None:
            return request
        page, controller = context
        request.detail_field_runner = (
            lambda item, action, page=page, controller=controller, plugin_id=request.source_key: self._run_plugin_detail_field_action(
                controller,
                page,
                plugin_id,
                item,
                action,
            )
        )
        return request
    if request.source_kind == "bilibili" and self.bilibili_page is not None:
        request.detail_field_runner = (
            lambda item, action, page=self.bilibili_page: self._run_bilibili_detail_field_action(page, item, action)
        )
    return request


def _run_bilibili_detail_field_action(
    self,
    page: PosterGridPage,
    item: PlayItem,
    action: PlaybackDetailFieldAction,
) -> None:
    if action.type == "link":
        if not QDesktopServices.openUrl(QUrl(action.value)):
            self._append_player_status_log(f"详情跳转失败[link]: 无法打开链接 {action.value}")
        return
    if action.target != "bilibili" or action.type != "category":
        return
    self._show_main_again()
    page.selected_category_id = action.value
    self.nav_tabs.setCurrentWidget(page)
    self._start_media_load(page, lambda: self.bilibili_controller.load_items(action.value, 1), empty_message="当前分类暂无内容")
```

This keeps the first release intentionally narrow: built-in Bilibili metadata links only need `target="bilibili"` plus `type="category"` for `up:<mid>` routes.

- [ ] **Step 2: Keep plugin routing unchanged for omitted targets**

Do not change the plugin-path semantics in `_run_plugin_detail_field_action()` beyond tolerating the new `target` field on the dataclass. The existing plugin tests already cover:

- `type="category"`
- `type="search"`
- `type="detail"`
- `type="link"`

The implementation should continue to treat omitted `target` as the current plugin flow.

- [ ] **Step 3: Document the inline metadata markup contract**

In `docs/python-spider-player-actions.md`, add a short section after `## Clickable Detail Fields`:

```markdown
## Inline Metadata CR Links

Backends that populate plain string metadata fields such as `vod_director`, `vod_actor`, or `vod_content` can embed clickable segments with:

    [a=cr:{"target":"bilibili","type":"category","value":"up:378885845"}/]Harold[/a]

Rules:

- `label` is the visible text between `[a=cr:...]` and `[/a]`
- `type` and `value` are required
- `target` is optional
- `target="bilibili"` routes through the built-in Bilibili tab instead of any spider-plugin `categoryContent(...)`
- multiple clickable segments may appear in one string field, separated by ordinary text such as ` / ` or `、`
```

- [ ] **Step 4: Run the new main-window test plus the existing detail-field regression tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "detail_field or bilibili_metadata_category_click_loads_builtin_bilibili_results" -v
```

Expected:

```text
PASSED tests/test_main_window_ui.py::test_main_window_detail_field_category_click_loads_plugin_results
PASSED tests/test_main_window_ui.py::test_main_window_detail_field_search_click_loads_plugin_results
PASSED tests/test_main_window_ui.py::test_main_window_detail_field_detail_click_opens_new_plugin_request
PASSED tests/test_main_window_ui.py::test_main_window_detail_field_link_click_opens_browser
PASSED tests/test_main_window_ui.py::test_main_window_bilibili_metadata_category_click_loads_builtin_bilibili_results
```

- [ ] **Step 5: Run the combined player-window and main-window targeted regression suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py tests/test_main_window_ui.py -k "metadata or detail_field or bilibili_metadata_category_click_loads_builtin_bilibili_results" -v
```

Expected:

```text
... PASSED
```

The suite should show the new inline metadata tests passing alongside the pre-existing clickable-detail-field regressions.

- [ ] **Step 6: Commit the main-window routing and docs update**

Run:

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py docs/python-spider-player-actions.md
git commit -m "feat: route bilibili metadata cr links"
```

Expected:

```text
[branch-name ...] feat: route bilibili metadata cr links
```

## Self-Review

- Spec coverage:
  - inline `[a=cr:...][/a]` parsing is covered by Tasks 1-2
  - `target/type/value` dispatch is covered by Tasks 1-2
  - built-in Bilibili `up:<mid>` routing is covered by Tasks 3-4
  - malformed-markup downgrade is covered by Task 1 and verified in Task 2
  - documentation follow-up is covered by Task 4
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” placeholders remain
  - every test and implementation step includes exact code or commands
- Type consistency:
  - all tasks use `PlaybackDetailFieldAction(target, type, value)`
  - all internal URLs use `action_target`, `action_type`, and `action_value`
  - built-in Bilibili routing consistently uses `target="bilibili"` and `type="category"`
