# Startup Plugin Async Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the main window immediately on startup, then load spider plugins in the background and replace a placeholder plugin tab with real plugin tabs when loading completes.

**Architecture:** Keep plugin loading responsibility in `AppCoordinator`, but pass a callable loader task into `MainWindow` instead of synchronously materializing `spider_plugins` before window creation. `MainWindow` owns startup plugin loading UI state, starts a background thread once, renders a lightweight placeholder tab while loading, and swaps in real plugin definitions through the existing `_rebuild_spider_plugin_tabs()` path when results arrive.

**Tech Stack:** Python 3.14, PySide6, pytest-qt, existing `AppCoordinator`/`MainWindow` async signal patterns, current plugin overflow navigation

---

## File Structure

- Modify: `src/atv_player/app.py`
  Add a reusable plugin loader wrapper in `AppCoordinator` and pass it into `MainWindow` instead of blocking on `load_enabled_plugins()` during startup.
- Modify: `src/atv_player/ui/main_window.py`
  Add startup plugin loading state, a placeholder plugin tab definition, background-thread kickoff, success/failure signals, retry handling, and late-result guards.
- Modify: `tests/test_app.py`
  Cover that startup no longer blocks on plugin loading and that `AppCoordinator` passes a plugin loader task instead of eagerly loading plugins.
- Modify: `tests/test_main_window_ui.py`
  Cover placeholder tab behavior, async success replacement, async failure/retry, and close-safety.

## Task 1: Lock Startup Behavior With Failing AppCoordinator Tests

**Files:**
- Modify: `tests/test_app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write a failing test proving `_show_main()` no longer waits for plugin loading**

Add this test near `test_app_coordinator_passes_loaded_spider_plugins_into_main_window` in `tests/test_app.py`:

```python
def test_app_coordinator_shows_main_window_before_startup_plugins_finish_loading(qtbot, monkeypatch, tmp_path) -> None:
    repo = app_module.SettingsRepository(tmp_path / "app.db")
    repo.save_config(
        AppConfig(
            base_url="http://127.0.0.1:4567",
            username="alice",
            token="token-123",
            vod_token="vod-123",
        )
    )

    load_started = threading.Event()
    release_load = threading.Event()

    class FakePluginManager:
        def load_enabled_plugins(self, drive_detail_loader=None, offline_download_detail_loader=None):
            load_started.set()
            assert release_load.wait(timeout=5), "plugin load was never released"
            return [{"id": "plugin-1", "title": "红果短剧", "controller": object(), "search_enabled": True}]

    def api_factory(*args, **kwargs):
        return ApiClient(
            "http://127.0.0.1:4567",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"token": "vod-123"})),
        )

    monkeypatch.setattr(app_module, "ApiClient", api_factory)
    monkeypatch.setattr(
        app_module,
        "SpiderPluginManager",
        lambda repository, loader, playback_history_repository: FakePluginManager(),
    )
    monkeypatch.setattr(app_module, "SpiderPluginRepository", lambda db_path: object())
    monkeypatch.setattr(app_module, "SpiderPluginLoader", lambda cache_dir: object())

    coordinator = AppCoordinator(repo)
    widget = coordinator._show_main()
    qtbot.addWidget(widget)
    widget.show()

    assert load_started.wait(timeout=1)
    assert widget is coordinator.main_window
    assert "插件加载中" in [widget.nav_tabs.tabText(i) for i in range(widget.nav_tabs.count())]

    release_load.set()
```

- [ ] **Step 2: Write a failing test proving `AppCoordinator` passes a loader task into `MainWindow`**

Add this test near the existing parser-service wiring test:

```python
def test_app_coordinator_passes_startup_plugin_loader_task_into_main_window(monkeypatch, tmp_path) -> None:
    repo = app_module.SettingsRepository(tmp_path / "app.db")
    repo.save_config(AppConfig(base_url="http://127.0.0.1:4567", token="token-123", vod_token="vod-123"))
    captured = {"plugin_loader_task": None}

    class FakeSignal:
        def connect(self, callback) -> None:
            return None

    class FakeMainWindow:
        def __init__(self, *args, **kwargs) -> None:
            captured["plugin_loader_task"] = kwargs.get("plugin_loader_task")
            self.logout_requested = FakeSignal()

    class FakePluginManager:
        def load_enabled_plugins(self, drive_detail_loader=None, offline_download_detail_loader=None):
            return []

    def api_factory(*args, **kwargs):
        return ApiClient(
            "http://127.0.0.1:4567",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"token": "vod-123"})),
        )

    monkeypatch.setattr(app_module, "MainWindow", FakeMainWindow)
    monkeypatch.setattr(app_module, "ApiClient", api_factory)
    monkeypatch.setattr(
        app_module,
        "SpiderPluginManager",
        lambda repository, loader, playback_history_repository: FakePluginManager(),
    )
    monkeypatch.setattr(app_module, "SpiderPluginRepository", lambda db_path: object())
    monkeypatch.setattr(app_module, "SpiderPluginLoader", lambda cache_dir: object())
    monkeypatch.setattr(app_module, "LocalPlaybackHistoryRepository", lambda db_path: object())

    coordinator = AppCoordinator(repo)
    coordinator._show_main()

    assert callable(captured["plugin_loader_task"])
```

- [ ] **Step 3: Run the two targeted tests and verify they fail for the right reason**

Run:

```bash
uv run pytest tests/test_app.py -k "startup_plugins_finish_loading or startup_plugin_loader_task" -q
```

Expected: FAIL because `_show_main()` still blocks on `load_enabled_plugins()` and `MainWindow` does not accept `plugin_loader_task`.

- [ ] **Step 4: Implement the minimal coordinator changes**

In `src/atv_player/app.py`, add a helper that preserves the current compatibility branching in one place:

```python
    def _load_startup_spider_plugins(self, drive_detail_loader, offline_download_detail_loader):
        try:
            return self._plugin_manager.load_enabled_plugins(
                drive_detail_loader=drive_detail_loader,
                offline_download_detail_loader=offline_download_detail_loader,
            )
        except TypeError as exc:
            if "offline_download_detail_loader" not in str(exc):
                if "drive_detail_loader" not in str(exc):
                    raise
                return self._plugin_manager.load_enabled_plugins(
                    drive_detail_loader=drive_detail_loader,
                )
            try:
                return self._plugin_manager.load_enabled_plugins(
                    drive_detail_loader=drive_detail_loader,
                )
            except TypeError as drive_exc:
                if "drive_detail_loader" not in str(drive_exc):
                    raise
                return self._plugin_manager.load_enabled_plugins()
```

Then replace the eager startup load in `_show_main()` with:

```python
        plugin_loader_task = lambda: self._load_startup_spider_plugins(
            drive_detail_loader,
            offline_download_detail_loader,
        )

        self.main_window = MainWindow(
            ...
            spider_plugins=[],
            plugin_loader_task=plugin_loader_task,
            ...
        )
```

Do **not** remove the existing plugin-manager-close refresh path; it still needs to reload real plugins synchronously after dialog changes.

- [ ] **Step 5: Run the targeted tests and verify they pass**

Run:

```bash
uv run pytest tests/test_app.py -k "startup_plugins_finish_loading or startup_plugin_loader_task" -q
```

Expected: PASS

- [ ] **Step 6: Commit the coordinator slice**

Run:

```bash
git add tests/test_app.py src/atv_player/app.py
git commit -m "feat: defer startup plugin loading"
```

## Task 2: Add Placeholder Plugin Tab And Async Startup Load In MainWindow

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write a failing test for the placeholder plugin tab**

Add this test near the plugin-tab startup tests in `tests/test_main_window_ui.py`:

```python
def test_main_window_shows_startup_plugin_loading_placeholder_tab(qtbot) -> None:
    load_started = threading.Event()
    release_load = threading.Event()

    def plugin_loader_task():
        load_started.set()
        assert release_load.wait(timeout=5), "plugin load was never released"
        return []

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    assert load_started.wait(timeout=1)
    assert "插件加载中" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]

    release_load.set()
```

- [ ] **Step 2: Write a failing test for async success replacement**

Add this test below the placeholder test:

```python
def test_main_window_replaces_loading_placeholder_with_loaded_plugin_tabs(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [
            {"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True},
            {"id": "plugin-2", "title": "短剧二号", "controller": FakeSpiderController("短剧二号"), "search_enabled": False},
        ]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    release_load.set()

    qtbot.waitUntil(
        lambda: [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())] == [
            "豆瓣电影",
            "电报影视",
            "网络直播",
            "Emby",
            "Jellyfin",
            "飞牛影视",
            "红果短剧",
            "短剧二号",
            "文件浏览",
            "播放记录",
        ]
    )
```

- [ ] **Step 3: Run the targeted main-window tests and verify they fail**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "startup_plugin_loading_placeholder or replaces_loading_placeholder" -q
```

Expected: FAIL because `MainWindow` neither accepts `plugin_loader_task` nor renders startup plugin placeholder state.

- [ ] **Step 4: Add startup plugin loading fields and signals in `MainWindow`**

In `src/atv_player/ui/main_window.py`, extend the constructor signature:

```python
            plugin_loader_task=None,
```

Store startup state:

```python
        self._plugin_loader_task = plugin_loader_task
        self._startup_plugin_load_started = False
        self._startup_plugin_load_request_id = 0
        self._startup_plugin_load_state = "loading" if callable(plugin_loader_task) else "idle"
        self._startup_plugin_load_error = ""
```

Add a signal carrier near the other async signals:

```python
class _StartupPluginLoadSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)
```

Wire it in `__init__`:

```python
        self._startup_plugin_load_signals = _StartupPluginLoadSignals()
        self._connect_async_signal(
            self._startup_plugin_load_signals.succeeded,
            self._handle_startup_plugin_load_succeeded,
        )
        self._connect_async_signal(
            self._startup_plugin_load_signals.failed,
            self._handle_startup_plugin_load_failed,
        )
```

- [ ] **Step 5: Add a placeholder tab definition path**

Add a helper alongside `_visible_tab_definitions()`:

```python
    def _startup_plugin_placeholder_definition(self) -> _TabDefinition | None:
        if self._global_search_active or self._startup_plugin_load_state == "idle":
            return None
        title = "插件加载中" if self._startup_plugin_load_state == "loading" else "插件加载失败"
        return _TabDefinition("plugin:startup-placeholder", title, QWidget(self))
```

Create and store a single placeholder page in `__init__` instead of constructing a new `QWidget` per refresh:

```python
        self._startup_plugin_placeholder_page = QWidget(self)
```

Use it in the helper:

```python
        return _TabDefinition("plugin:startup-placeholder", title, self._startup_plugin_placeholder_page)
```

Update `_refresh_navigation_tabs()` so the visible plugin portion is:

```python
            placeholder_definition = self._startup_plugin_placeholder_definition()
            plugin_definitions = visible_plugins
            if placeholder_definition is not None:
                plugin_definitions = [placeholder_definition]
                self._hidden_plugin_tab_definitions = []
                self.plugin_overflow_button.hide()
            definitions = [*self._static_tab_definitions, *plugin_definitions, *self._trailing_tab_definitions]
```

- [ ] **Step 6: Start the background load exactly once**

Add:

```python
    def _start_startup_plugin_load(self) -> None:
        if self._startup_plugin_load_started or not callable(self._plugin_loader_task):
            return
        self._startup_plugin_load_started = True
        self._startup_plugin_load_request_id += 1
        request_id = self._startup_plugin_load_request_id

        def run() -> None:
            try:
                plugins = self._plugin_loader_task()
            except Exception as exc:
                if self._is_window_alive():
                    self._startup_plugin_load_signals.failed.emit(request_id, str(exc))
                return
            if self._is_window_alive():
                self._startup_plugin_load_signals.succeeded.emit(request_id, list(plugins))

        threading.Thread(target=run, daemon=True).start()
```

Trigger it from `showEvent()` after `super().showEvent(event)`:

```python
        self._start_startup_plugin_load()
```

- [ ] **Step 7: Apply success results through the existing rebuild path**

Add:

```python
    def _handle_startup_plugin_load_succeeded(self, request_id: int, plugins) -> None:
        if request_id != self._startup_plugin_load_request_id:
            return
        self._startup_plugin_load_state = "idle"
        self._startup_plugin_load_error = ""
        self._plugin_definitions = list(plugins)
        self._rebuild_spider_plugin_tabs()
```

This reuses the existing page construction path and keeps overflow behavior centralized.

- [ ] **Step 8: Run the targeted tests and verify they pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "startup_plugin_loading_placeholder or replaces_loading_placeholder" -q
```

Expected: PASS

- [ ] **Step 9: Commit the placeholder/loading slice**

Run:

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/main_window.py
git commit -m "feat: show startup plugin loading placeholder"
```

## Task 3: Add Failure, Retry, And Close-Safety

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write a failing test for startup plugin load failure**

Add this test below the success case:

```python
def test_main_window_shows_retry_after_startup_plugin_load_failure(qtbot) -> None:
    attempts = {"count": 0}

    def plugin_loader_task():
        attempts["count"] += 1
        raise RuntimeError("boom")

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()

    qtbot.waitUntil(lambda: window.startup_plugin_retry_button.isVisible())
    assert "插件加载失败" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())]
```

- [ ] **Step 2: Write a failing test for retry**

Add:

```python
def test_main_window_retry_restarts_startup_plugin_loading(qtbot) -> None:
    attempts = {"count": 0}

    def plugin_loader_task():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("boom")
        return [{"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True}]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.resize(920, 520)
    window.show()

    qtbot.waitUntil(lambda: window.startup_plugin_retry_button.isVisible())
    window.startup_plugin_retry_button.click()

    qtbot.waitUntil(lambda: "红果短剧" in [window.nav_tabs.tabText(i) for i in range(window.nav_tabs.count())])
    assert attempts["count"] == 2
```

- [ ] **Step 3: Write a failing test for close safety**

Add:

```python
def test_main_window_ignores_late_startup_plugin_results_after_close(qtbot) -> None:
    release_load = threading.Event()

    def plugin_loader_task():
        assert release_load.wait(timeout=5), "plugin load was never released"
        return [{"id": "plugin-1", "title": "红果短剧", "controller": FakeSpiderController("红果短剧"), "search_enabled": True}]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    window.show()
    window.close()
    release_load.set()

    qtbot.wait(100)
```

- [ ] **Step 4: Run the targeted failure/retry tests and verify they fail**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "startup_plugin_load_failure or retry_restarts_startup_plugin_loading or ignores_late_startup_plugin_results" -q
```

Expected: FAIL because failure state, retry controls, and close-safe handlers do not exist yet.

- [ ] **Step 5: Add failure UI and retry control**

In `MainWindow.__init__`, add:

```python
        self.startup_plugin_status_label = QLabel("")
        self.startup_plugin_retry_button = QPushButton("重试加载插件")
        self.startup_plugin_retry_button.hide()
        self.startup_plugin_retry_button.clicked.connect(self._retry_startup_plugin_load)
```

Place them in the header area near the existing status widgets:

```python
        self.header_layout.addWidget(self.startup_plugin_status_label)
        self.header_layout.addWidget(self.startup_plugin_retry_button)
```

Add a sync helper:

```python
    def _sync_startup_plugin_loading_ui(self) -> None:
        if self._startup_plugin_load_state == "failed":
            self.startup_plugin_status_label.setText(self._startup_plugin_load_error or "插件加载失败")
            self.startup_plugin_retry_button.show()
            return
        self.startup_plugin_status_label.setText("")
        self.startup_plugin_retry_button.hide()
```

- [ ] **Step 6: Add failure and retry handlers**

Add:

```python
    def _handle_startup_plugin_load_failed(self, request_id: int, message: str) -> None:
        if request_id != self._startup_plugin_load_request_id:
            return
        self._startup_plugin_load_state = "failed"
        self._startup_plugin_load_error = message or "插件加载失败"
        self._sync_startup_plugin_loading_ui()
        self._refresh_navigation_tabs()

    def _retry_startup_plugin_load(self) -> None:
        if self._startup_plugin_load_state == "loading":
            return
        self._startup_plugin_load_state = "loading"
        self._startup_plugin_load_error = ""
        self._startup_plugin_load_started = False
        self._sync_startup_plugin_loading_ui()
        self._refresh_navigation_tabs()
        self._start_startup_plugin_load()
```

Also call `_sync_startup_plugin_loading_ui()` in:

```python
        self._handle_startup_plugin_load_succeeded(...)
        self._handle_startup_plugin_load_failed(...)
        self.__init__(...) after layout setup
```

- [ ] **Step 7: Guard against late results after close**

In `closeEvent()`, invalidate outstanding plugin-load results:

```python
        self._startup_plugin_load_request_id += 1
```

Keep `_deactivate_async_guard()` in place so `_is_window_alive()` prevents new signal emission after teardown.

- [ ] **Step 8: Run the targeted tests and verify they pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "startup_plugin_load_failure or retry_restarts_startup_plugin_loading or ignores_late_startup_plugin_results" -q
```

Expected: PASS

- [ ] **Step 9: Commit the failure/retry slice**

Run:

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/main_window.py
git commit -m "feat: handle startup plugin load failures"
```

## Task 4: Verify Startup Regression Surface

**Files:**
- Modify: `tests/test_app.py`
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_app.py`, `tests/test_main_window_ui.py`

- [ ] **Step 1: Add a focused regression test for plugin overflow after async startup load**

Add this test near the overflow tests in `tests/test_main_window_ui.py`:

```python
def test_main_window_applies_plugin_overflow_after_async_startup_load(qtbot, monkeypatch) -> None:
    def plugin_loader_task():
        return [
            {"id": f"plugin-{index}", "title": f"插件{index}", "controller": FakeSpiderController(f"插件{index}"), "search_enabled": True}
            for index in range(1, 6)
        ]

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=[],
        plugin_loader_task=plugin_loader_task,
        plugin_manager=WidthAwarePluginManager(),
    )

    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 220)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)

    window.show()

    qtbot.waitUntil(lambda: window.plugin_overflow_button.text() == "更多(3)")
    assert [definition.title for definition in window._hidden_plugin_tab_definitions] == ["插件3", "插件4", "插件5"]
```

- [ ] **Step 2: Run the focused regression suites**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -q
uv run pytest tests/test_app.py -k "startup_plugin or loads_plugin_tabs or plugin_manager or live_source_manager" -q
```

Expected: PASS

- [ ] **Step 3: Run the plugin-manager regression suite**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py tests/test_spider_plugin_manager.py -q
```

Expected: PASS

- [ ] **Step 4: Commit the finished async-startup feature**

Run:

```bash
git add tests/test_main_window_ui.py tests/test_app.py src/atv_player/app.py src/atv_player/ui/main_window.py
git commit -m "feat: load startup plugins asynchronously"
```
