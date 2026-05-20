# Danmaku Source Clear Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `清除弹幕` button to the player window's danmaku source dialog so users can remove the currently loaded danmaku without losing search results or the selected source.

**Architecture:** Keep the feature entirely inside `PlayerWindow`. Reuse the existing `_clear_active_danmaku()` playback cleanup path, add one dialog button plus a small current-item helper, and cover the new behavior with a focused UI regression test.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

## File Map

- `src/atv_player/ui/player_window.py`
  Owns the danmaku source dialog UI, button enablement, current play item state, and active danmaku cleanup.
- `tests/test_player_window_ui.py`
  Holds dialog-level player window UI regressions and fake playback/controller helpers.

### Task 1: Add the Failing UI Regression Test

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Verify: `tests/test_player_window_ui.py::test_player_window_clear_danmaku_button_removes_loaded_danmaku_and_keeps_source_selection`

- [ ] **Step 1: Write the failing test**

Add this test near the existing danmaku source dialog tests:

```python
def test_player_window_clear_danmaku_button_removes_loaded_danmaku_and_keeps_source_selection(qtbot) -> None:
    item = PlayItem(
        title="第1集",
        url="https://stream.example/1.m3u8",
        media_title="红果短剧",
        danmaku_xml='<?xml version="1.0" encoding="UTF-8"?><i><d p="1.0,1,25,16777215">ok</d></i>',
        danmaku_candidates=[
            DanmakuSourceGroup(
                provider="tencent",
                provider_label="腾讯",
                options=[DanmakuSourceOption(provider="tencent", name="红果短剧 第1集", url="https://v.qq.com/demo")],
            )
        ],
        selected_danmaku_provider="tencent",
        selected_danmaku_url="https://v.qq.com/demo",
        selected_danmaku_title="红果短剧 第1集",
        danmaku_search_query="红果短剧 1集",
    )
    session = PlayerSession(
        vod=VodItem(vod_id="1", vod_name="红果短剧"),
        playlist=[item],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    window._danmaku_track_id = 7
    window._danmaku_active = True

    window.open_session(session)
    window._open_danmaku_source_dialog()

    assert window._danmaku_source_clear_button is not None
    assert window._danmaku_source_clear_button.isEnabled() is True

    window._clear_current_item_danmaku_source()

    assert item.danmaku_xml == ""
    assert item.selected_danmaku_url == "https://v.qq.com/demo"
    assert item.selected_danmaku_provider == "tencent"
    assert item.selected_danmaku_title == "红果短剧 第1集"
    assert window.video.removed_subtitle_tracks == [7]
    assert window._danmaku_source_clear_button.isEnabled() is False
    assert window._danmaku_source_switch_button is not None
    assert window._danmaku_source_switch_button.isEnabled() is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_clear_danmaku_button_removes_loaded_danmaku_and_keeps_source_selection -v
```

Expected: FAIL because `PlayerWindow` does not yet define `_danmaku_source_clear_button` or `_clear_current_item_danmaku_source`.

### Task 2: Implement the Button and Clear Handler

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Verify: `tests/test_player_window_ui.py::test_player_window_clear_danmaku_button_removes_loaded_danmaku_and_keeps_source_selection`

- [ ] **Step 1: Add the new dialog button field**

Extend the danmaku source dialog state attributes alongside the existing rerun/switch button fields:

```python
self._danmaku_source_rerun_button: QPushButton | None = None
self._danmaku_source_clear_button: QPushButton | None = None
self._danmaku_source_switch_button: QPushButton | None = None
```

- [ ] **Step 2: Add the clear button to the dialog layout**

In `_ensure_danmaku_source_dialog()`, create the new button between `恢复默认` and `加载弹幕`, store it on `self`, and connect it to the new handler:

```python
clear_button = QPushButton("清除弹幕", host)
self._danmaku_source_clear_button = clear_button
clear_button.clicked.connect(self._clear_current_item_danmaku_source)
actions.addWidget(clear_button)
```

The final button order in the action row must be:

```python
actions.addWidget(rerun_button)
actions.addWidget(reset_button)
actions.addWidget(clear_button)
actions.addWidget(switch_button)
```

- [ ] **Step 3: Add the current-item clear helper**

Implement a small helper near the other danmaku source dialog actions:

```python
def _clear_current_item_danmaku_source(self) -> None:
    current_item = self._current_play_item()
    if current_item is None or not current_item.danmaku_xml:
        return
    self._clear_active_danmaku()
    current_item.danmaku_xml = ""
    self._refresh_danmaku_source_dialog_actions(current_item)
```

- [ ] **Step 4: Update dialog action enablement**

Extend `_refresh_danmaku_source_dialog_actions()` so the new button is only enabled when the current item exists, no danmaku source task is active, and `current_item.danmaku_xml` is non-empty:

```python
if self._danmaku_source_clear_button is not None:
    self._danmaku_source_clear_button.setEnabled(
        bool(
            current_item is not None
            and not self._has_active_danmaku_source_task(current_item)
            and current_item.danmaku_xml
        )
    )
```

- [ ] **Step 5: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_player_window_ui.py::test_player_window_clear_danmaku_button_removes_loaded_danmaku_and_keeps_source_selection -v
```

Expected: PASS

### Task 3: Run the Danmaku Dialog Regression Subset

**Files:**
- Verify only: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the related danmaku source UI subset**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "danmaku and source" -v
```

Expected: PASS for the new clear-button test and the existing danmaku source dialog tests.

- [ ] **Step 2: Commit the implementation**

Run:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py docs/superpowers/plans/2026-05-20-danmaku-source-clear-button.md
git commit -m "feat: add clear button to danmaku source dialog"
```

Expected: commit succeeds with only the intended UI/test/plan changes staged.
