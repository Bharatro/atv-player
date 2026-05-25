# Player Detail Name Global Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal player details `名称` value clickable, close the player, and route it to global search.

**Architecture:** Add a `global_search_requested` signal on `PlayerWindow`, encode normal `名称` rows as `atv-player://global-search?keyword=...`, emit the signal and run `_return_to_main()` when the link is clicked, and connect the signal in `MainWindow` to the existing `_handle_favorite_global_search()` helper. Keep YouTube and live detail titles as plain text.

**Tech Stack:** Python, PySide6, pytest-qt.

---

## File Structure

- Modify `src/atv_player/ui/player_window.py`: render the normal `名称` row as an internal search link, emit a signal when clicked, and leave YouTube/live detail styles unchanged.
- Modify `src/atv_player/ui/main_window.py`: connect `PlayerWindow.global_search_requested` to the existing global search helper.
- Modify `tests/test_player_window_ui.py`: cover signal emission and unsupported styles.
- Modify `tests/test_main_window_ui.py`: cover MainWindow wiring.

### Task 1: PlayerWindow Link Rendering And Signal

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write failing PlayerWindow tests**

Add tests near the existing metadata-link tests:

```python
def test_player_window_clicking_normal_detail_name_requests_global_search(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="刮削后的标题", vod_content="简介文本"),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    searched: list[str] = []
    window.global_search_requested.connect(searched.append)

    window.open_session(session)

    assert "名称: 刮削后的标题" in window.metadata_view.toPlainText()
    assert "atv-player://global-search" in window.metadata_view.toHtml()
    window._handle_metadata_link(QUrl("atv-player://global-search?keyword=%E5%88%AE%E5%89%8A%E5%90%8E%E7%9A%84%E6%A0%87%E9%A2%98"))
    assert searched == ["刮削后的标题"]


@pytest.mark.parametrize("detail_style", ["youtube", "live"])
def test_player_window_does_not_make_youtube_or_live_title_global_search_link(qtbot, detail_style: str) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="movie-1", vod_name="标题文本", vod_content="简介文本", detail_style=detail_style),
        playlist=[PlayItem(title="Episode 1", url="http://m/1.m3u8")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.open_session(session)

    assert "atv-player://global-search" not in window.metadata_view.toHtml()
```

- [ ] **Step 2: Run PlayerWindow tests and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "normal_detail_name_requests_global_search or youtube_or_live_title_global_search" -q`

Expected: FAIL because `PlayerWindow` has no `global_search_requested` signal and no global-search link rendering.

- [ ] **Step 3: Implement PlayerWindow signal and link handling**

In `PlayerWindow`, add `global_search_requested = Signal(str)` next to `closed_to_main`.

Add helpers:

```python
def _global_search_url(self, keyword: str) -> QUrl:
    url = QUrl("atv-player://global-search")
    query = QUrlQuery()
    query.addQueryItem("keyword", keyword)
    url.setQuery(query)
    return url

def _global_search_link_html(self, keyword: object) -> str:
    text = str(keyword or "").strip()
    if not text:
        return ""
    href = html.escape(self._global_search_url(text).toString())
    return f'<a href="{href}">{html.escape(text)}</a>'
```

Change `_metadata_row_html()` so only the normal `名称` row gets this internal link before external metadata-link handling:

```python
if label == "名称":
    search_html = self._global_search_link_html(value)
    if search_html:
        return f"{html.escape(label)}: {search_html}".rstrip()
```

Update `_handle_metadata_link()` before detail-field handling:

```python
if url.scheme() == "atv-player" and url.host() == "global-search":
    keyword = QUrlQuery(url).queryItemValue("keyword", QUrl.ComponentFormattingOption.FullyDecoded).strip()
    if keyword:
        self.global_search_requested.emit(keyword)
    return
```

- [ ] **Step 4: Run PlayerWindow tests and verify pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "normal_detail_name_requests_global_search or youtube_or_live_title_global_search" -q`

Expected: PASS.

### Task 2: MainWindow Wiring

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `src/atv_player/ui/main_window.py`

- [ ] **Step 1: Write failing MainWindow test**

Add a test near other global-search routing tests:

```python
def test_main_window_player_detail_name_global_search_signal_starts_global_search(qtbot, monkeypatch) -> None:
    class FakeSignal:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in list(self.callbacks):
                callback(*args)

    class RecordingPlayerWindow:
        last_instance = None

        def __init__(self, controller, config, save_config, **kwargs) -> None:
            self.opened: list[tuple[object, bool]] = []
            self.closed_to_main = FakeSignal()
            self.global_search_requested = FakeSignal()
            RecordingPlayerWindow.last_instance = self

        def open_session(self, session, start_paused: bool = False) -> None:
            self.opened.append((session, start_paused))

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

    monkeypatch.setattr(main_window_module, "PlayerWindow", RecordingPlayerWindow)
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
    )
    qtbot.addWidget(window)
    started_keywords: list[str] = []
    monkeypatch.setattr(window, "_start_global_search", lambda: started_keywords.append(window.global_search_edit.text()))
    request = OpenPlayerRequest(
        vod=VodItem(vod_id="movie-1", vod_name="播放详情"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.m3u8")],
        clicked_index=0,
        source_kind="browse",
        source_vod_id="movie-1",
    )

    window.open_player(request)
    qtbot.waitUntil(lambda: RecordingPlayerWindow.last_instance is not None)
    RecordingPlayerWindow.last_instance.global_search_requested.emit("刮削后的标题")

    assert window.global_search_edit.text() == "刮削后的标题"
    assert started_keywords == ["刮削后的标题"]
```

- [ ] **Step 2: Run MainWindow test and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "player_detail_name_global_search_signal" -q`

Expected: FAIL because `MainWindow` does not connect the new signal.

- [ ] **Step 3: Implement MainWindow connection**

In `_apply_open_player()`, after connecting `closed_to_main`, add:

```python
if hasattr(self.player_window, "global_search_requested"):
    self.player_window.global_search_requested.connect(self._handle_favorite_global_search)
```

- [ ] **Step 4: Run MainWindow test and verify pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "player_detail_name_global_search_signal" -q`

Expected: PASS.

### Task 3: Regression Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run targeted combined tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "metadata_link or normal_detail_name_requests_global_search or youtube_or_live_title_global_search" tests/test_main_window_ui.py -k "detail_field_search_click_loads_plugin_results or player_detail_name_global_search_signal" -q`

Expected: PASS.

- [ ] **Step 2: Review diff**

Run: `git diff -- src/atv_player/ui/player_window.py src/atv_player/ui/main_window.py tests/test_player_window_ui.py tests/test_main_window_ui.py`

Expected: Diff only contains signal, link rendering, routing tests, and the MainWindow signal connection plus any pre-existing unrelated changes.
