# Player Context Menu Exit Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `退出播放` action to the player video right-click menu that returns to the main window without quitting the application.

**Architecture:** Keep the change inside `PlayerWindow`. Reuse the existing `_return_to_main()` flow as the single source of truth for leaving the playback window, and extend the current context-menu tests so both menu structure and menu-triggered behavior stay covered.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Structure

- `src/atv_player/ui/player_window.py`
  Responsibility: append the new top-level `退出播放` action to the existing video context menu and bind it to `_return_to_main()`.
- `tests/test_player_window_ui.py`
  Responsibility: prove the new action appears in the menu, returns to the main window, does not quit the app, and updates the two existing top-level menu-order assertions.

### Task 1: Wire `退出播放` To The Existing Return Path

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing behavior test**

Add this test near the existing `_return_to_main()` and quit-path tests in `tests/test_player_window_ui.py`:

```python
def test_player_window_context_menu_exit_playback_returns_to_main(qtbot, monkeypatch) -> None:
    quit_calls = {"count": 0}
    emitted = {"count": 0}
    shutdowns = {"count": 0}
    controller = RecordingPlayerController()
    config = AppConfig(last_active_window="player")
    window = PlayerWindow(controller, config=config, save_config=lambda: None)
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window.open_session(make_player_session(start_index=1))
    controller.progress_calls.clear()
    controller.stop_calls.clear()
    window.closed_to_main.connect(lambda: emitted.__setitem__("count", emitted["count"] + 1))

    monkeypatch.setattr(
        window.video_widget,
        "shutdown",
        lambda: shutdowns.__setitem__("count", shutdowns["count"] + 1),
    )
    monkeypatch.setattr(
        QApplication,
        "quit",
        lambda *args, **kwargs: quit_calls.__setitem__("count", quit_calls["count"] + 1),
    )

    menu = window._build_video_context_menu()
    exit_action = next(action for action in menu.actions() if action.text() == "退出播放")

    window.show()
    exit_action.trigger()

    assert quit_calls["count"] == 0
    assert emitted["count"] == 1
    assert window.isHidden() is True
    assert config.last_active_window == "main"
    assert shutdowns["count"] == 1
    assert window.video.pause_calls == 1
    qtbot.waitUntil(
        lambda: controller.progress_calls == [(1, 30, 1.0, 0, 0, True)] and controller.stop_calls == [1]
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "context_menu_exit_playback_returns_to_main" -q
```

Expected:

- FAIL because the menu does not yet contain a `退出播放` action, so the `next(...)` lookup raises `StopIteration`

- [ ] **Step 3: Write the minimal implementation**

Append the new action at the end of `_build_video_context_menu()` in `src/atv_player/ui/player_window.py`:

```python
    def _build_video_context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addMenu(self._build_primary_subtitle_menu(menu))
        menu.addMenu(self._build_secondary_subtitle_menu(menu))
        menu.addMenu(self._build_subtitle_position_menu(menu, title="主字幕位置", secondary=False))
        menu.addMenu(self._build_subtitle_position_menu(menu, title="次字幕位置", secondary=True))
        menu.addMenu(self._build_subtitle_scale_menu(menu, title="主字幕大小", secondary=False))
        menu.addMenu(self._build_subtitle_scale_menu(menu, title="次字幕大小", secondary=True))
        menu.addMenu(self._build_audio_menu(menu))
        if self._video_quality_options:
            menu.addMenu(self._build_video_quality_menu(menu))
        menu.addMenu(self._build_danmaku_menu(menu))
        menu.addAction("刮削", self._open_metadata_scrape_dialog)
        menu.addAction("弹幕源", self._open_danmaku_source_dialog)
        menu.addAction("弹幕设置", self._open_danmaku_settings_dialog)
        menu.addAction("视频信息", self._toggle_video_info_from_menu)
        menu.addAction("退出播放", self._return_to_main)
        return menu
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "context_menu_exit_playback_returns_to_main" -q
```

Expected:

- PASS

- [ ] **Step 5: Commit the behavior change**

Run:

```bash
git add tests/test_player_window_ui.py src/atv_player/ui/player_window.py
git commit -m "feat: add player context menu exit playback action"
```

### Task 2: Update Menu-Order Regression Coverage

**Files:**
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Update the two existing top-level action-list assertions**

Adjust the expected menu action lists near the existing context-menu structure tests so both now end with `退出播放`:

```python
    assert [action.text() for action in menu.actions()] == [
        "主字幕",
        "次字幕",
        "主字幕位置",
        "次字幕位置",
        "主字幕大小",
        "次字幕大小",
        "音轨",
        "弹幕配置",
        "刮削",
        "弹幕源",
        "弹幕设置",
        "视频信息",
        "退出播放",
    ]
```

Apply that same expected suffix in both existing assertions in `tests/test_player_window_ui.py`.

- [ ] **Step 2: Run the menu-structure tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "builds_full_video_context_menu" -q
```

Expected:

- PASS

- [ ] **Step 3: Run focused regression coverage**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "video_context_menu or context_menu_exit_playback_returns_to_main or return_to_main or quit_application" -q
```

Expected:

- PASS for the new menu action test
- PASS for the existing menu-structure tests
- PASS for the existing `_return_to_main()` and quit-path tests, proving the new action reuses the right path and does not disturb quit behavior

- [ ] **Step 4: Review the diff for scope**

Run:

```bash
git diff -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected:

- Only the right-click menu wiring and the related player-window UI tests changed
