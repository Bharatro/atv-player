# List Page Video Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a right-click context menu to poster-grid video cards with source-aware visibility rules for `打开播放`、`全局搜索`、`加入收藏`.

**Architecture:** Keep `PosterGridPage` generic by only emitting a card-level context-menu request signal. Let `MainWindow` own all source-aware menu construction and action routing, including the placeholder `加入收藏` entry and special handling for `豆瓣电影`、`网络直播`、全局搜索结果页。

**Tech Stack:** Python, PySide6, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/poster_grid_page.py`
  Responsibility: add card-level custom-context-menu support and emit a generic request signal with the target item and global position.
- Modify: `src/atv_player/ui/main_window.py`
  Responsibility: connect poster-grid context-menu signals, compute source/state-specific action visibility, build the `QMenu`, and route actions to existing open/global-search flows plus a placeholder favorite handler.
- Modify: `tests/test_poster_grid_page_ui.py`
  Responsibility: verify card right-click emits the new context-menu signal with the correct `VodItem`.
- Modify: `tests/test_main_window_ui.py`
  Responsibility: verify source-aware menu composition for normal sources, 豆瓣电影, 网络直播, and global-search result mode.

### Task 1: Add poster-grid card context-menu signal

**Files:**
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Test: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_poster_grid_page_card_context_menu_emits_item(qtbot) -> None:
    page = show_loaded_page(qtbot, PosterGridPage(FakeDoubanController(), click_action="open"))

    qtbot.waitUntil(lambda: len(page.card_buttons) == 1)

    with qtbot.waitSignal(page.card_context_menu_requested, timeout=1000) as signal:
        page.card_buttons[0].customContextMenuRequested.emit(page.card_buttons[0].rect().center())

    assert signal.args[0].vod_id == "m1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_poster_grid_page_ui.py::test_poster_grid_page_card_context_menu_emits_item -v`

Expected: FAIL because `PosterGridPage` does not expose `card_context_menu_requested` and card buttons are not configured for custom context menus.

- [ ] **Step 3: Write minimal implementation**

```python
class PosterGridPage(QWidget, AsyncGuardMixin):
    card_context_menu_requested = Signal(object, object)

    def _build_card_button(self, item) -> QToolButton:
        button = QToolButton()
        button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        button.customContextMenuRequested.connect(
            lambda pos, current_item=item, current_button=button: self._handle_card_context_menu_requested(
                current_item,
                current_button,
                pos,
            )
        )
        ...
        return button

    def _handle_card_context_menu_requested(self, item, button: QToolButton, pos) -> None:
        self.card_context_menu_requested.emit(item, button.mapToGlobal(pos))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_poster_grid_page_ui.py::test_poster_grid_page_card_context_menu_emits_item -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/poster_grid_page.py tests/test_poster_grid_page_ui.py
git commit -m "feat: emit poster card context menu requests"
```

### Task 2: Add source-aware context-menu composition in the main window

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_main_window_video_context_menu_shows_all_actions_for_normal_source(qtbot, monkeypatch) -> None:
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    captured_actions: list[str] = []

    class FakeMenu:
        def __init__(self, parent=None) -> None:
            del parent
            self.actions = []
        def addAction(self, text: str):
            captured_actions.append(text)
            action = object()
            self.actions.append(action)
            return action
        def exec(self, global_pos):
            del global_pos
            return None

    monkeypatch.setattr(main_window_module, "QMenu", FakeMenu)

    window._open_video_item_context_menu(
        window.telegram_page,
        VodItem(vod_id="vod-1", vod_name="测试影片"),
        window.mapToGlobal(window.rect().center()),
    )

    assert captured_actions == ["打开播放", "全局搜索", "加入收藏"]
```

```python
def test_main_window_video_context_menu_shows_only_global_search_for_douban(qtbot, monkeypatch) -> None:
    ...
    window._open_video_item_context_menu(window.douban_page, VodItem(vod_id="db-1", vod_name="豆瓣条目"), ...)
    assert captured_actions == ["全局搜索"]
```

```python
def test_main_window_video_context_menu_hides_global_search_for_live(qtbot, monkeypatch) -> None:
    ...
    window._open_video_item_context_menu(window.live_page, VodItem(vod_id="live-1", vod_name="直播间"), ...)
    assert captured_actions == ["打开播放", "加入收藏"]
```

```python
def test_main_window_video_context_menu_hides_global_search_in_external_results_mode(qtbot, monkeypatch) -> None:
    ...
    window.telegram_page.show_external_results([VodItem(vod_id="vod-1", vod_name="搜索结果")], total=1, page=1)
    window._open_video_item_context_menu(window.telegram_page, VodItem(vod_id="vod-1", vod_name="搜索结果"), ...)
    assert captured_actions == ["打开播放", "加入收藏"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "video_context_menu_shows_all_actions_for_normal_source or video_context_menu_shows_only_global_search_for_douban or video_context_menu_hides_global_search_for_live or video_context_menu_hides_global_search_in_external_results_mode" -v`

Expected: FAIL because `MainWindow` does not yet expose `_open_video_item_context_menu(...)` or connect any poster-grid context-menu signal.

- [ ] **Step 3: Write minimal implementation**

```python
class MainWindow(...):
    def _connect_poster_grid_context_menu(self, page: PosterGridPage) -> None:
        page.card_context_menu_requested.connect(
            lambda item, global_pos, current_page=page: self._open_video_item_context_menu(current_page, item, global_pos)
        )

    def _open_video_item_context_menu(self, page: PosterGridPage, item: VodItem, global_pos: QPoint) -> None:
        self._dismiss_visible_global_search_popup()
        actions = self._video_item_context_menu_actions(page)
        if not actions:
            return
        menu = QMenu(self)
        open_action = menu.addAction("打开播放") if "open" in actions else None
        search_action = menu.addAction("全局搜索") if "search" in actions else None
        favorite_action = menu.addAction("加入收藏") if "favorite" in actions else None
        chosen = menu.exec(global_pos)
        if chosen is open_action:
            self._handle_video_item_context_open(page, item)
        elif chosen is search_action:
            self._handle_video_item_context_global_search(item)
        elif chosen is favorite_action:
            self._handle_video_item_context_favorite(page, item)

    def _video_item_context_menu_actions(self, page: PosterGridPage) -> list[str]:
        is_douban = page is self.douban_page
        is_live = page is self.live_page
        is_external_results = bool(getattr(page, "_external_results_active", False))
        actions: list[str] = []
        if not is_douban:
            actions.append("open")
        if not is_live and not is_external_results:
            actions.append("search")
        if not is_douban:
            actions.append("favorite")
        return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "video_context_menu_shows_all_actions_for_normal_source or video_context_menu_shows_only_global_search_for_douban or video_context_menu_hides_global_search_for_live or video_context_menu_hides_global_search_in_external_results_mode" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: add source-aware list page video context menus"
```

### Task 3: Route actions through existing open/search flows and keep favorite as a placeholder

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_main_window_video_context_menu_global_search_uses_item_title(qtbot, monkeypatch) -> None:
    window = MainWindow(...)
    qtbot.addWidget(window)
    started_keywords: list[str] = []
    monkeypatch.setattr(window, "_start_global_search", lambda: started_keywords.append(window.global_search_edit.text()))

    window._handle_video_item_context_global_search(VodItem(vod_id="vod-1", vod_name="成何体统"))

    assert window.global_search_edit.text() == "成何体统"
    assert started_keywords == ["成何体统"]
```

```python
def test_main_window_video_context_menu_favorite_placeholder_keeps_state_unchanged(qtbot) -> None:
    window = MainWindow(...)
    qtbot.addWidget(window)
    window.global_search_edit.setText("原值")

    window._handle_video_item_context_favorite(window.telegram_page, VodItem(vod_id="vod-1", vod_name="测试影片"))

    assert window.global_search_edit.text() == "原值"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "video_context_menu_global_search_uses_item_title or video_context_menu_favorite_placeholder_keeps_state_unchanged" -v`

Expected: FAIL because the handlers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _handle_video_item_context_open(self, page: PosterGridPage, item: VodItem) -> None:
    page.item_open_requested.emit(item)

def _handle_video_item_context_global_search(self, item: VodItem) -> None:
    keyword = str(item.vod_name or "").strip()
    if not keyword:
        return
    self.global_search_edit.setText(keyword)
    self._start_global_search()

def _handle_video_item_context_favorite(self, page: PosterGridPage, item: VodItem) -> None:
    del page, item
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "video_context_menu_global_search_uses_item_title or video_context_menu_favorite_placeholder_keeps_state_unchanged" -v`

Expected: PASS

- [ ] **Step 5: Run focused regression suite**

Run: `uv run pytest tests/test_poster_grid_page_ui.py tests/test_main_window_ui.py -k "context_menu or global_search_uses_item_title or favorite_placeholder_keeps_state_unchanged" -v`

Expected: PASS for the new focused coverage with no regressions in the touched area.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/main_window.py src/atv_player/ui/poster_grid_page.py tests/test_poster_grid_page_ui.py tests/test_main_window_ui.py
git commit -m "feat: wire list page video context menu actions"
```

## Self-Review

- Spec coverage:
  - Card-level right-click support: Task 1
  - Source-aware visibility rules: Task 2
  - Placeholder favorite action: Task 3
  - Existing open/global-search flow reuse: Task 3
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every code-changing task includes concrete snippets and commands
- Type consistency:
  - `card_context_menu_requested`
  - `_open_video_item_context_menu`
  - `_video_item_context_menu_actions`
  - `_handle_video_item_context_open`
  - `_handle_video_item_context_global_search`
  - `_handle_video_item_context_favorite`
