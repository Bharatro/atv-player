# Clickable Player Detail Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clickable spider-plugin player detail fields that can open plugin category/search/detail routes or external browser links from the player sidebar.

**Architecture:** Keep spider plugin payload parsing in `src/atv_player/plugins/controller.py`, add normalized clickable field models in `src/atv_player/models.py`, and render them in a dedicated interactive block inside `src/atv_player/ui/player_window.py`. Navigation stays outside the player: `MainWindow` supplies a new session callback that handles `category`, `search`, `detail`, and `link` actions using existing plugin-tab loading and player-open flows.

**Tech Stack:** Python 3, dataclasses, PySide6 widgets/signals, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/models.py`
  - add normalized detail-field action/value-part models
  - extend player request/session callback wiring
- Modify: `src/atv_player/controllers/player_controller.py`
  - copy new detail-field callback from request to session
- Modify: `src/atv_player/plugins/controller.py`
  - normalize legacy/plain/clickable `ext` payloads into shared models
- Modify: `src/atv_player/ui/player_window.py`
  - render clickable detail-field values
  - dispatch clicks through the new session callback
- Modify: `src/atv_player/ui/main_window.py`
  - provide spider-plugin detail-field navigation callback
  - route `category`/`search` into plugin tabs, `detail` into player open, `link` into browser open
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_main_window_ui.py`
- Modify: `docs/python-spider-plugin-development-guide.md`
  - document clickable detail fields after code is working

### Task 1: Normalize Clickable Detail Field Payloads

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/plugins/controller.py`

- [ ] **Step 1: Write the failing controller tests**

```python
def test_spider_controller_maps_clickable_detailcontent_ext_value_objects() -> None:
    controller = SpiderPluginController(ClickableDetailFieldSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.vod.detail_fields == [
        PlaybackDetailField(
            label="演员",
            value_parts=[
                PlaybackDetailValuePart(
                    label="演员1",
                    action=PlaybackDetailFieldAction(type="search", value="演员1"),
                ),
                PlaybackDetailValuePart(
                    label="演员2",
                    action=PlaybackDetailFieldAction(type="detail", value="actor-2"),
                ),
            ],
        ),
        PlaybackDetailField(
            label="标签",
            value_parts=[
                PlaybackDetailValuePart(label="动作"),
                PlaybackDetailValuePart(label="冒险"),
            ],
        ),
    ]


def test_spider_controller_downgrades_invalid_detail_field_actions_to_plain_text() -> None:
    controller = SpiderPluginController(InvalidClickableDetailFieldSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.vod.detail_fields == [
        PlaybackDetailField(
            label="导演",
            value_parts=[PlaybackDetailValuePart(label="导演1")],
        )
    ]
```

- [ ] **Step 2: Run controller tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "clickable_detailcontent_ext or invalid_detail_field_actions" -v`

Expected: FAIL because `PlaybackDetailFieldAction` / `PlaybackDetailValuePart` do not exist and the controller still normalizes `value` as a plain string only.

- [ ] **Step 3: Write the minimal model changes**

```python
@dataclass(slots=True)
class PlaybackDetailFieldAction:
    type: str
    value: str


@dataclass(slots=True)
class PlaybackDetailValuePart:
    label: str
    action: PlaybackDetailFieldAction | None = None


@dataclass(slots=True)
class PlaybackDetailField:
    label: str
    value_parts: list[PlaybackDetailValuePart] = field(default_factory=list)
```

- [ ] **Step 4: Write the minimal controller normalization**

```python
def _map_playback_detail_field_action(payload: object) -> PlaybackDetailFieldAction | None:
    if not isinstance(payload, Mapping):
        return None
    action_type = str(payload.get("type") or "").strip()
    value = str(payload.get("value") or "").strip()
    if action_type not in {"category", "detail", "search", "link"} or not value:
        return None
    return PlaybackDetailFieldAction(type=action_type, value=value)


def _map_playback_detail_field_value_parts(payload: object) -> list[PlaybackDetailValuePart]:
    if isinstance(payload, list):
        parts: list[PlaybackDetailValuePart] = []
        for raw_item in payload:
            if isinstance(raw_item, Mapping):
                label = str(raw_item.get("label") or "").strip()
                if not label:
                    continue
                parts.append(
                    PlaybackDetailValuePart(
                        label=label,
                        action=_map_playback_detail_field_action(raw_item.get("action")),
                    )
                )
                continue
            text = str(raw_item or "").strip()
            if text:
                parts.append(PlaybackDetailValuePart(label=text))
        return parts
    text = str(payload or "").strip()
    return [PlaybackDetailValuePart(label=text)] if text else []


def _map_playback_detail_fields(payload: object) -> list[PlaybackDetailField]:
    ...
    parts = _map_playback_detail_field_value_parts(raw_field.get("value"))
    if not label or not parts:
        continue
    fields.append(PlaybackDetailField(label=label, value_parts=parts))
```

- [ ] **Step 5: Run controller tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "clickable_detailcontent_ext or invalid_detail_field_actions" -v`

Expected: PASS

- [ ] **Step 6: Commit the normalization slice**

```bash
git add tests/test_spider_plugin_controller.py src/atv_player/models.py src/atv_player/plugins/controller.py
git commit -m "feat: normalize clickable player detail fields"
```

### Task 2: Render and Dispatch Clickable Detail Fields in PlayerWindow

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/models.py`

- [ ] **Step 1: Write the failing player-window tests**

```python
def test_player_window_renders_clickable_detail_field_value_parts(qtbot) -> None:
    clicked: list[PlaybackDetailFieldAction] = []
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            detail_fields=[
                PlaybackDetailField(
                    label="演员",
                    value_parts=[
                        PlaybackDetailValuePart(
                            label="演员1",
                            action=PlaybackDetailFieldAction(type="search", value="演员1"),
                        ),
                        PlaybackDetailValuePart(label="演员2"),
                    ],
                )
            ],
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        detail_field_runner=lambda _item, action: clicked.append(action),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    buttons = window.detail_fields_widget.findChildren(QPushButton)
    assert [button.text() for button in buttons] == ["演员1"]
    buttons[0].click()
    assert clicked == [PlaybackDetailFieldAction(type="search", value="演员1")]


def test_player_window_renders_plain_multi_value_detail_fields_as_text(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(
            vod_id="movie-1",
            vod_name="Movie",
            detail_fields=[
                PlaybackDetailField(
                    label="标签",
                    value_parts=[PlaybackDetailValuePart(label="动作"), PlaybackDetailValuePart(label="冒险")],
                )
            ],
        ),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    assert "标签" in window.detail_fields_widget.findChildren(QLabel)[0].text()
    assert "动作" in window.detail_fields_widget.findChildren(QLabel)[1].text()
    assert "冒险" in window.detail_fields_widget.findChildren(QLabel)[3].text()
```

- [ ] **Step 2: Run player-window tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "clickable_detail_field_value_parts or plain_multi_value_detail_fields" -v`

Expected: FAIL because the session has no `detail_field_runner` and the player still formats detail fields only as inline plain text.

- [ ] **Step 3: Wire the new callback through request/session models**

```python
class PlayerSession:
    ...
    detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None


class OpenPlayerRequest:
    ...
    detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None


def create_session(..., detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None, ...):
    ...
    session = PlayerSession(..., detail_field_runner=detail_field_runner, ...)
```

- [ ] **Step 4: Render interactive detail-field rows in the player**

```python
def _current_detail_fields(self) -> list[PlaybackDetailField]:
    ...


def _render_detail_fields(self) -> None:
    self._clear_detail_field_rows()
    fields = self._current_detail_fields()
    self.detail_fields_widget.setHidden(not fields)
    for field in fields:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.addWidget(QLabel(f"{field.label}:"))
        for index, part in enumerate(field.value_parts):
            if index > 0:
                layout.addWidget(QLabel("/"))
            if part.action is not None:
                button = QPushButton(part.label)
                button.clicked.connect(
                    lambda _checked=False, action=part.action: self._run_detail_field_action(action)
                )
                layout.addWidget(button)
            else:
                layout.addWidget(QLabel(part.label))
        self.detail_fields_layout.addWidget(row)
```

- [ ] **Step 5: Dispatch clicks through the session callback**

```python
def _run_detail_field_action(self, action: PlaybackDetailFieldAction) -> None:
    if self.session is None or self.session.detail_field_runner is None:
        return
    if not (0 <= self.current_index < len(self.session.playlist)):
        return
    current_item = self.session.playlist[self.current_index]
    try:
        self.session.detail_field_runner(current_item, action)
    except Exception as exc:
        self._append_log(f"详情跳转失败[{action.type}]: {exc}")
```

- [ ] **Step 6: Run player-window tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "clickable_detail_field_value_parts or plain_multi_value_detail_fields" -v`

Expected: PASS

- [ ] **Step 7: Commit the player-window slice**

```bash
git add tests/test_player_window_ui.py src/atv_player/models.py src/atv_player/controllers/player_controller.py src/atv_player/ui/player_window.py
git commit -m "feat: render clickable player detail fields"
```

### Task 3: Route Detail Field Clicks Through MainWindow

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/models.py`
- Modify: `docs/python-spider-plugin-development-guide.md`

- [ ] **Step 1: Write the failing main-window tests**

```python
def test_main_window_detail_field_search_click_loads_plugin_results(monkeypatch, qtbot) -> None:
    controller = FakeSpiderPluginController()
    window = make_main_window_with_plugin(qtbot, controller=controller)
    request = controller.build_request("detail-1")

    window.open_player(request)
    assert window.player_window is not None

    runner = window.player_window.session.detail_field_runner
    runner(
        window.player_window.session.playlist[0],
        PlaybackDetailFieldAction(type="search", value="演员1"),
    )

    assert controller.search_calls == [("演员1", 1, "")]
    assert window.tabs.currentWidget() is controller.page


def test_main_window_detail_field_link_click_opens_browser(monkeypatch, qtbot) -> None:
    opened: list[str] = []
    monkeypatch.setattr(main_window_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    window = make_main_window_with_plugin(qtbot)
    request = build_plugin_request_with_detail_field_action()

    window.open_player(request)
    runner = window.player_window.session.detail_field_runner
    runner(
        window.player_window.session.playlist[0],
        PlaybackDetailFieldAction(type="link", value="https://example.com"),
    )

    assert opened == ["https://example.com"]
```

- [ ] **Step 2: Run main-window tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "detail_field_search_click or detail_field_link_click" -v`

Expected: FAIL because plugin requests do not yet include `detail_field_runner` and the main window has no routing helper for these actions.

- [ ] **Step 3: Add the main-window routing helper**

```python
def _run_plugin_detail_field_action(self, controller, page: PosterGridPage, item: PlayItem, action: PlaybackDetailFieldAction) -> None:
    if action.type == "detail":
        self._start_plugin_open_request(controller, action.value)
        return
    if action.type == "category":
        self._show_main_again()
        self._start_media_load(page, lambda: controller.load_items(action.value, 1), empty_message="暂无内容")
        return
    if action.type == "search":
        self._show_main_again()
        self._start_media_load(page, lambda: controller.search_items(action.value, 1), empty_message="未找到相关内容")
        return
    if action.type == "link":
        if not QDesktopServices.openUrl(QUrl(action.value)):
            self._append_player_status_log(f"详情跳转失败[link]: 无法打开链接 {action.value}")
```

- [ ] **Step 4: Attach the callback when opening plugin requests**

```python
def _build_spider_plugin_request(...):
    request = controller.build_request(vod_id)
    request.detail_field_runner = lambda item, action, controller=controller, page=page: self._run_plugin_detail_field_action(
        controller,
        page,
        item,
        action,
    )
    return request
```

- [ ] **Step 5: Document clickable detail fields**

```markdown
## Clickable Detail Fields

`ext` rows may now use:

```python
{"label": "演员", "value": [{"label": "演员1", "action": {"type": "search", "value": "演员1"}}]}
```

Supported action types:

- `category`
- `detail`
- `search`
- `link`
```

- [ ] **Step 6: Run main-window tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "detail_field_search_click or detail_field_link_click" -v`

Expected: PASS

- [ ] **Step 7: Run the focused regression suite**

Run: `uv run pytest tests/test_spider_plugin_controller.py tests/test_player_window_ui.py tests/test_main_window_ui.py -k "detail_field or detail_fields or clickable_detail" -v`

Expected: PASS with the new clickable-detail coverage and existing detail-field behavior remaining green.

- [ ] **Step 8: Commit the routing and docs slice**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/main_window.py docs/python-spider-plugin-development-guide.md
git commit -m "feat: route clickable player detail fields"
```

## Self-Review

- Spec coverage:
  - clickable payload parsing is covered by Task 1
  - player rendering and dispatch are covered by Task 2
  - main-window routing and external browser open are covered by Task 3
  - docs follow-up is covered by Task 3
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to above” placeholders remain
- Type consistency:
  - shared names are `PlaybackDetailFieldAction`, `PlaybackDetailValuePart`, and `detail_field_runner` across tasks
