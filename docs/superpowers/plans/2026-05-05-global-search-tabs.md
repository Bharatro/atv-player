# Global Search Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a main-window global search box that concurrently searches Telegram, Emby, Jellyfin, Feiniu, and all enabled spider plugins, then shows only result-bearing tabs with count badges until the search is cleared.

**Architecture:** Keep orchestration in `MainWindow` and keep rendering in `PosterGridPage`. `MainWindow` owns the header controls, request ids, threaded fan-out, result collection, and temporary tab rebuilding; `PosterGridPage` gains a narrow external-result mode so the main window can inject first-page search results without mutating scattered internal state.

**Tech Stack:** Python 3, PySide6 widgets/signals, `threading.Thread`, `pytest` with `pytest-qt`

---

## File Structure

### Existing Files To Modify

- `src/atv_player/ui/main_window.py`
  Owns tab construction, dynamic spider plugin tab insertion, header widgets, and all main-window async orchestration. This is where the global search widgets, request signals, searchable-tab definitions, and temporary result-only tab mode should live.
- `src/atv_player/ui/poster_grid_page.py`
  Already renders cards, page labels, status text, folder breadcrumbs, and page-local search mode. This is the right place to add a small external-result mode API for injected first-page global search results.
- `tests/test_main_window_ui.py`
  Already verifies dynamic tab ordering and header buttons. Extend it with global-search fan-out, result-only tabs, count-bearing titles, stale-request dropping, and clear-to-restore coverage.
- `tests/test_poster_grid_page_ui.py`
  Already verifies `PosterGridPage` rendering, page-local search, and async behavior. Extend it with focused tests around externally injected result state.

### No New Runtime Modules

This feature can stay inside the existing UI modules. Do not create a new controller, dialog, or page.

## Task 1: Add Failing Main Window Global Search Tests

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Verify with: `uv run pytest tests/test_main_window_ui.py -v`

- [ ] **Step 1: Write the failing header-layout and result-tab tests**

Add new test doubles near the existing `FakeStaticController` helpers so the tests can observe search fan-out and delay completion:

```python
class SearchableController(FakeStaticController):
    def __init__(self, title: str, items: list[VodItem], total: int | None = None) -> None:
        self.title = title
        self.items = list(items)
        self.total = len(items) if total is None else total
        self.search_calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        return list(self.items), self.total


class AsyncSearchableController(FakeStaticController):
    def __init__(self, items: list[VodItem], total: int | None = None) -> None:
        self.items = list(items)
        self.total = len(items) if total is None else total
        self.search_calls: list[tuple[str, int]] = []
        self._events: dict[str, threading.Event] = {}

    def search_items(self, keyword: str, page: int):
        self.search_calls.append((keyword, page))
        event = self._events.setdefault(keyword, threading.Event())
        assert event.wait(timeout=5), f"search for {keyword} was never released"
        return list(self.items), self.total

    def release(self, keyword: str) -> None:
        self._events.setdefault(keyword, threading.Event()).set()
```

Add a helper item factory and the first two tests:

```python
def _vod(name: str, vod_id: str | None = None) -> VodItem:
    return VodItem(vod_id=vod_id or name, vod_name=name, vod_pic="", vod_remarks="")


def test_main_window_places_global_search_controls_before_plugin_manager(qtbot) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController("telegram", []),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController("emby", []),
        jellyfin_controller=SearchableController("jellyfin", []),
        feiniu_controller=SearchableController("feiniu", []),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert window.global_search_edit.parentWidget() is not None
    assert window.global_search_button.text() == "搜索"
    assert window.global_search_clear_button.text() == "清空"
    assert window.header_layout.indexOf(window.global_search_edit) < window.header_layout.indexOf(window.plugin_manager_button)


def test_main_window_global_search_shows_only_tabs_with_results_and_count_titles(qtbot) -> None:
    telegram = SearchableController("telegram", [_vod("Telegram One")], total=12)
    emby = SearchableController("emby", [])
    jellyfin = SearchableController("jellyfin", [_vod("Jellyfin One")], total=3)
    feiniu = SearchableController("feiniu", [])
    plugin_controller = SearchableController("plugin", [_vod("Plugin One"), _vod("Plugin Two")], total=2)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=jellyfin,
        feiniu_controller=feiniu,
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": True}],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()

    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
        "电报影视(12)",
        "Jellyfin(3)",
        "红果短剧(2)",
    ])
    assert telegram.search_calls == [("庆余年", 1)]
    assert emby.search_calls == [("庆余年", 1)]
    assert jellyfin.search_calls == [("庆余年", 1)]
    assert feiniu.search_calls == [("庆余年", 1)]
    assert plugin_controller.search_calls == [("庆余年", 1)]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_main_window_ui.py::test_main_window_places_global_search_controls_before_plugin_manager \
  tests/test_main_window_ui.py::test_main_window_global_search_shows_only_tabs_with_results_and_count_titles \
  -v
```

Expected:

- `AttributeError` or `AssertionError` because `MainWindow` does not yet expose `global_search_edit`, `global_search_button`, `global_search_clear_button`, or `header_layout`
- no production code changes yet

- [ ] **Step 3: Write the failing stale-request and clear-to-restore tests**

Append two more tests using the async search double:

```python
def test_main_window_ignores_stale_global_search_results(qtbot) -> None:
    telegram = AsyncSearchableController([_vod("旧结果")], total=1)
    emby = AsyncSearchableController([_vod("新结果")], total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=emby,
        jellyfin_controller=SearchableController("jellyfin", []),
        feiniu_controller=SearchableController("feiniu", []),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("旧关键词")
    window.global_search_button.click()
    window.global_search_edit.setText("新关键词")
    window.global_search_button.click()

    telegram.release("旧关键词")
    emby.release("新关键词")
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["Emby(1)"])

    assert telegram.search_calls == [("旧关键词", 1), ("新关键词", 1)]
    assert emby.search_calls == [("旧关键词", 1), ("新关键词", 1)]


def test_main_window_clear_global_search_restores_original_tabs_and_titles(qtbot) -> None:
    telegram = SearchableController("telegram", [_vod("Telegram One")], total=4)
    plugin_controller = SearchableController("plugin", [_vod("Plugin One")], total=1)

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=telegram,
        live_controller=FakeStaticController(),
        emby_controller=SearchableController("emby", []),
        jellyfin_controller=SearchableController("jellyfin", []),
        feiniu_controller=SearchableController("feiniu", []),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[{"id": "plugin-a", "title": "红果短剧", "controller": plugin_controller, "search_enabled": True}],
        plugin_manager=FakePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    original_titles = [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]

    window.global_search_edit.setText("庆余年")
    window.global_search_button.click()
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == ["电报影视(4)", "红果短剧(1)"])

    window.global_search_clear_button.click()
    qtbot.waitUntil(lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == original_titles)
```

- [ ] **Step 4: Run the stale-request and clear-to-restore tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_main_window_ui.py::test_main_window_ignores_stale_global_search_results \
  tests/test_main_window_ui.py::test_main_window_clear_global_search_restores_original_tabs_and_titles \
  -v
```

Expected:

- failures because the main window does not yet start global searches or rebuild tabs
- the stale-request test should fail on missing methods or unchanged tab list, not on fixture setup

- [ ] **Step 5: Commit the test-only red state**

```bash
git add tests/test_main_window_ui.py
git commit -m "test: cover main window global search tabs"
```

## Task 2: Add Failing Poster Grid External Result Tests

**Files:**
- Modify: `tests/test_poster_grid_page_ui.py`
- Verify with: `uv run pytest tests/test_poster_grid_page_ui.py -v`

- [ ] **Step 1: Write the failing external-result tests**

Add a controller that can tell whether normal `load_items` gets called:

```python
class ExternalResultController(FakeDoubanController):
    def __init__(self) -> None:
        super().__init__()
        self.load_items_calls = 0

    def load_items(self, category_id: str, page: int, filters: dict[str, str] | None = None):
        self.load_items_calls += 1
        return super().load_items(category_id, page, filters)
```

Add the tests:

```python
def test_poster_grid_page_can_render_external_results_without_controller_reload(qtbot) -> None:
    controller = ExternalResultController()
    page = show_loaded_page(qtbot, PosterGridPage(controller, click_action="open", search_enabled=True))
    qtbot.waitUntil(lambda: page.category_list.count() == 2)

    baseline_calls = controller.load_items_calls
    page.show_external_results(
        items=[VodItem(vod_id="s1", vod_name="全局搜索结果", vod_pic="", vod_remarks="HD")],
        total=9,
        page=1,
        empty_message="无搜索结果",
    )

    assert controller.load_items_calls == baseline_calls
    assert [button.text() for button in page.card_buttons] == ["全局搜索结果\nHD"]
    assert page.page_label.text() == "第 1 / 1 页"
    assert page.status_label.text() == ""


def test_poster_grid_page_can_render_external_empty_state(qtbot) -> None:
    page = show_loaded_page(qtbot, PosterGridPage(ExternalResultController(), click_action="open", search_enabled=True))
    qtbot.waitUntil(lambda: page.category_list.count() == 2)

    page.show_external_results(items=[], total=0, page=1, empty_message="无搜索结果")

    assert page.card_buttons == []
    assert page.status_label.text() == "无搜索结果"


def test_poster_grid_page_can_leave_external_result_mode_and_return_to_category_state(qtbot) -> None:
    controller = ExternalResultController()
    page = show_loaded_page(qtbot, PosterGridPage(controller, click_action="open", search_enabled=True))
    qtbot.waitUntil(lambda: len(page.card_buttons) == 1)

    page.show_external_results(items=[VodItem(vod_id="s1", vod_name="全局搜索结果")], total=1, page=1)
    page.clear_external_results()

    qtbot.waitUntil(lambda: controller.load_items_calls >= 2)
    assert page.card_buttons[0].text() == "霸王别姬\n9.6"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_render_external_results_without_controller_reload \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_render_external_empty_state \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_leave_external_result_mode_and_return_to_category_state \
  -v
```

Expected:

- failures because `PosterGridPage` does not yet expose `show_external_results` or `clear_external_results`

- [ ] **Step 3: Commit the page-level red state**

```bash
git add tests/test_poster_grid_page_ui.py
git commit -m "test: cover poster grid external results"
```

## Task 3: Implement Poster Grid External Result Mode

**Files:**
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Verify with: `uv run pytest tests/test_poster_grid_page_ui.py -v`

- [ ] **Step 1: Add the smallest external-result state needed**

Introduce explicit state fields in `PosterGridPage.__init__` so the page can tell whether it is currently rendering controller-managed results or main-window-injected results:

```python
        self._external_results_active = False
        self._external_empty_message = "暂无内容"
```

Add the new public methods near `show_items`:

```python
    def show_external_results(
        self,
        items,
        total: int,
        page: int = 1,
        empty_message: str = "无搜索结果",
    ) -> None:
        self._external_results_active = True
        self._external_empty_message = empty_message
        self.show_items(items, total, page=page, empty_message=empty_message)

    def clear_external_results(self) -> None:
        if not self._external_results_active:
            return
        self._external_results_active = False
        self._external_empty_message = "暂无内容"
        if self.selected_category_id:
            self.current_page = 1
            self.load_items(self.selected_category_id, self.current_page)
```

- [ ] **Step 2: Guard existing page actions so injected mode does not trigger local paging/search loads**

Update `previous_page`, `next_page`, and `_refresh_current_view` so external-result mode does not call `search_items` or `load_items`:

```python
    def previous_page(self) -> None:
        if self.current_page <= 1:
            return
        self.current_page -= 1
        if self._external_results_active:
            self._update_pagination()
            return
        ...

    def _refresh_current_view(self) -> None:
        if self._external_results_active:
            self.show_items(self.items, self.total_items, page=self.current_page, empty_message=self._external_empty_message)
            return
        ...
```

Also clear external mode when the page resumes local behavior:

```python
    def load_items(self, category_id: str, page: int) -> None:
        self._external_results_active = False
        ...

    def search(self) -> None:
        self._external_results_active = False
        ...

    def clear_search(self) -> None:
        self._external_results_active = False
        ...
```

- [ ] **Step 3: Run the focused poster-grid tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_render_external_results_without_controller_reload \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_render_external_empty_state \
  tests/test_poster_grid_page_ui.py::test_poster_grid_page_can_leave_external_result_mode_and_return_to_category_state \
  -v
```

Expected:

- all three tests pass
- no regressions in page construction or card rendering

- [ ] **Step 4: Refactor only if needed, then commit**

If the state-reset logic duplicates existing code, extract a tiny helper such as `_exit_external_results_mode()`; otherwise keep the implementation inline.

```bash
git add src/atv_player/ui/poster_grid_page.py tests/test_poster_grid_page_ui.py
git commit -m "feat: support injected poster grid results"
```

## Task 4: Implement Main Window Global Search Orchestration

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Verify with: `uv run pytest tests/test_main_window_ui.py -v`

- [ ] **Step 1: Add explicit searchable-tab metadata and header widgets**

Add small dataclasses near `_MediaLoadResult` so `MainWindow` can rebuild tab visibility deterministically:

```python
@dataclass(slots=True)
class _TabDefinition:
    key: str
    title: str
    page: QWidget
    searchable: bool = False
    controller: Any | None = None


@dataclass(slots=True)
class _GlobalSearchResult:
    key: str
    title: str
    page: PosterGridPage
    items: list[Any]
    total: int
```

In `__init__`, add and store the new header controls and state:

```python
        self.global_search_edit = QLineEdit()
        self.global_search_button = QPushButton("搜索")
        self.global_search_clear_button = QPushButton("清空")
        self.global_search_status_label = QLabel("")
        self.header_layout = QHBoxLayout()
        self._tab_definitions: list[_TabDefinition] = []
        self._global_search_request_id = 0
        self._global_search_pending = 0
        self._global_search_results: dict[str, _GlobalSearchResult] = {}
        self._global_search_active = False
```

Wire the header row in this order:

```python
        self.header_layout.addWidget(self.global_search_edit, 1)
        self.header_layout.addWidget(self.global_search_button)
        self.header_layout.addWidget(self.global_search_clear_button)
        self.header_layout.addWidget(self.global_search_status_label)
        self.header_layout.addStretch(1)
        self.header_layout.addWidget(self.plugin_manager_button)
```

Connect the new signals:

```python
        self.global_search_button.clicked.connect(self._start_global_search)
        self.global_search_clear_button.clicked.connect(self._clear_global_search)
        self.global_search_edit.returnPressed.connect(self._start_global_search)
        self.global_search_edit.textChanged.connect(self._handle_global_search_text_changed)
```

- [ ] **Step 2: Teach tab construction to preserve original definitions**

Replace one-off `addTab` calls with a helper that records definitions:

```python
    def _register_tab(
        self,
        key: str,
        page: QWidget,
        title: str,
        *,
        searchable: bool = False,
        controller: Any | None = None,
    ) -> None:
        self._tab_definitions.append(
            _TabDefinition(
                key=key,
                title=title,
                page=page,
                searchable=searchable,
                controller=controller,
            )
        )
```

Use it for the fixed tabs:

```python
        self._register_tab("douban", self.douban_page, "豆瓣电影")
        self._register_tab("telegram", self.telegram_page, "电报影视", searchable=True, controller=self.telegram_controller)
        self._register_tab("live", self.live_page, "网络直播")
        ...
        self._register_tab("browse", self.browse_page, "文件浏览")
        self._register_tab("history", self.history_page, "播放记录")
```

Update `_rebuild_spider_plugin_tabs()` so each plugin gets a stable `key` such as `plugin:{plugin_id}` and is always marked searchable under the new spec assumption:

```python
            definition = _TabDefinition(
                key=f"plugin:{plugin_id}",
                title=str(_plugin_value(definition, "title") or "插件"),
                page=page,
                searchable=True,
                controller=controller,
            )
```

After all definitions are registered, add a helper to rebuild the visible `QTabWidget` from either the full definition list or a filtered subset:

```python
    def _show_tab_definitions(self, definitions: list[_TabDefinition], title_overrides: dict[str, str] | None = None) -> None:
        current = self.nav_tabs.currentWidget()
        self.nav_tabs.clear()
        for definition in definitions:
            self.nav_tabs.addTab(definition.page, (title_overrides or {}).get(definition.key, definition.title))
        if current is not None:
            index = self.nav_tabs.indexOf(current)
            if index >= 0:
                self.nav_tabs.setCurrentIndex(index)
```

- [ ] **Step 3: Implement threaded fan-out, stale-request dropping, and result-only tab rebuilding**

Add a small signal carrier:

```python
class _GlobalSearchSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)
```

Add the startup, worker, and completion logic:

```python
    def _start_global_search(self) -> None:
        keyword = self.global_search_edit.text().strip()
        if not keyword:
            return
        self._global_search_request_id += 1
        request_id = self._global_search_request_id
        searchable = [definition for definition in self._tab_definitions if definition.searchable and definition.controller is not None]
        self._global_search_active = True
        self._global_search_pending = len(searchable)
        self._global_search_results = {}
        self.global_search_button.setEnabled(False)
        self.global_search_status_label.setText("搜索中...")
        for definition in searchable:
            threading.Thread(
                target=self._run_global_search,
                args=(request_id, definition, keyword),
                daemon=True,
            ).start()

    def _run_global_search(self, request_id: int, definition: _TabDefinition, keyword: str) -> None:
        try:
            items, total = definition.controller.search_items(keyword, 1)
        except Exception as exc:
            if self._is_window_alive():
                self._global_search_signals.failed.emit(request_id, definition.key)
            return
        if self._is_window_alive():
            self._global_search_signals.succeeded.emit(
                request_id,
                _GlobalSearchResult(
                    key=definition.key,
                    title=definition.title,
                    page=cast(PosterGridPage, definition.page),
                    items=list(items),
                    total=total,
                ),
            )
```

Handle completions only for the active request id and decrement pending once per source:

```python
    def _handle_global_search_succeeded(self, request_id: int, result: _GlobalSearchResult) -> None:
        if request_id != self._global_search_request_id:
            return
        if result.items:
            result.page.show_external_results(result.items, result.total, page=1, empty_message="无搜索结果")
            self._global_search_results[result.key] = result
        self._finish_one_global_search_result()

    def _handle_global_search_failed(self, request_id: int, key: str) -> None:
        if request_id != self._global_search_request_id:
            return
        self._global_search_results.pop(key, None)
        self._finish_one_global_search_result()
```

Finish the round by rebuilding result tabs in original order:

```python
    def _finish_one_global_search_result(self) -> None:
        self._global_search_pending -= 1
        if self._global_search_pending > 0:
            return
        visible = [definition for definition in self._tab_definitions if definition.key in self._global_search_results]
        title_overrides = {
            key: f"{result.title}({result.total})"
            for key, result in self._global_search_results.items()
        }
        self._show_tab_definitions(visible, title_overrides=title_overrides)
        self.global_search_button.setEnabled(True)
        self.global_search_clear_button.setEnabled(True)
        self.global_search_status_label.setText("" if visible else "无搜索结果")
        if visible:
            self.nav_tabs.setCurrentIndex(0)
```

- [ ] **Step 4: Implement clear-to-restore behavior and keep plugin-tab rebuild compatible**

Add a main-window clear path:

```python
    def _clear_global_search(self) -> None:
        if not self._global_search_active and not self.global_search_edit.text().strip():
            return
        self.global_search_edit.clear()
        self._global_search_active = False
        self._global_search_results = {}
        self._global_search_pending = 0
        self.global_search_status_label.setText("")
        self.global_search_button.setEnabled(True)
        self.global_search_clear_button.setEnabled(False)
        for definition in self._tab_definitions:
            if isinstance(definition.page, PosterGridPage):
                definition.page.clear_external_results()
        self._show_tab_definitions(self._tab_definitions)
```

Keep `_rebuild_spider_plugin_tabs()` compatible by:

- rebuilding the plugin portion of `_tab_definitions`
- re-applying the current global-search filter if `_global_search_active` is still true after plugin-manager dialog closes
- otherwise restoring the full definition list

Use a helper such as:

```python
    def _refresh_visible_tabs(self) -> None:
        if self._global_search_active:
            visible = [definition for definition in self._tab_definitions if definition.key in self._global_search_results]
            overrides = {key: f"{result.title}({result.total})" for key, result in self._global_search_results.items()}
            self._show_tab_definitions(visible, title_overrides=overrides)
            return
        self._show_tab_definitions(self._tab_definitions)
```

- [ ] **Step 5: Run the focused main-window tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_main_window_ui.py::test_main_window_places_global_search_controls_before_plugin_manager \
  tests/test_main_window_ui.py::test_main_window_global_search_shows_only_tabs_with_results_and_count_titles \
  tests/test_main_window_ui.py::test_main_window_ignores_stale_global_search_results \
  tests/test_main_window_ui.py::test_main_window_clear_global_search_restores_original_tabs_and_titles \
  -v
```

Expected:

- all four targeted tests pass
- the visible tab list reflects only result-bearing sources
- stale completions from older request ids do not alter the visible result tabs

- [ ] **Step 6: Run the broader UI safety suite, then commit**

Run:

```bash
uv run pytest \
  tests/test_main_window_ui.py \
  tests/test_poster_grid_page_ui.py \
  -v
```

Expected:

- all tests in both files pass
- no regressions in existing dynamic tab ordering, local page search, or folder navigation behavior

Commit:

```bash
git add src/atv_player/ui/main_window.py src/atv_player/ui/poster_grid_page.py tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py
git commit -m "feat: add global search result tabs"
```

## Plan Self-Review

- Spec coverage: covered header controls, parallel source fan-out, result-only tabs, title counts, stale-request dropping, all-enabled-plugin assumption, and clear-to-restore behavior in Tasks 1 through 4.
- Placeholder scan: no `TODO`, `TBD`, or “write tests later” placeholders remain.
- Type consistency: the plan consistently uses `show_external_results`, `clear_external_results`, `_TabDefinition`, `_GlobalSearchResult`, and request-id guarded completion handlers.
