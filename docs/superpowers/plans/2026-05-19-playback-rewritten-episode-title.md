# Playback Rewritten Episode Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save and display rewritten episode titles for playback history and current playback when available.

**Architecture:** Reuse the existing playlist title display fallback helper so playback persistence and player logging resolve titles the same way. Keep the implementation limited to `PlayerController` and `PlayerWindow`, with focused tests covering each entry point.

**Tech Stack:** Python, pytest, PySide6

---

### Task 1: Cover Rewritten Titles In Playback Persistence And Logging

**Files:**
- Modify: `tests/test_player_controller.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_controller_reports_rewritten_episode_title_in_history_payload() -> None:
    ...
    assert saved_payloads[0]["vodRemarks"] == "第1集 星门初启"


def test_player_window_logs_rewritten_episode_title_for_current_playback(qtbot) -> None:
    ...
    assert "当前播放: 第2集 星火初燃" in window.log_view.toPlainText()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_reports_rewritten_episode_title_in_history_payload tests/test_player_window_ui.py::test_player_window_logs_rewritten_episode_title_for_current_playback -q`
Expected: FAIL because both paths still use `PlayItem.title`.

- [ ] **Step 3: Write the minimal implementation**

```python
payload["vodRemarks"] = playlist_item_display_title(current_item, "episode")
...
self._append_log(f"当前播放: {playlist_item_display_title(current_item, 'episode')}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_reports_rewritten_episode_title_in_history_payload tests/test_player_window_ui.py::test_player_window_logs_rewritten_episode_title_for_current_playback -q`
Expected: PASS

- [ ] **Step 5: Run a small regression slice**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_reports_progress_to_plugin_local_saver_without_api_history tests/test_player_window_ui.py::test_player_window_switches_danmaku_when_switching_playlist_items -q`
Expected: PASS and existing non-rewritten title behavior remains intact.
