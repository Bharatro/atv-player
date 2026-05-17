# Playback Resolving Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `正在解析播放地址` to the player playback log when the window enters the resolving startup state, without duplicating the same status line repeatedly.

**Architecture:** Keep the change inside `PlayerWindow` so startup-state rendering remains the single source of truth. Extend `_set_startup_state(...)` to mirror only the resolving message into the log view through a small dedupe helper, leaving existing explicit log lines like `正在加载播放地址: <title>` unchanged.

**Tech Stack:** Python 3, PySide6 widgets, pytest, pytest-qt

---

## File Map

- Modify: `src/atv_player/ui/player_window.py`
  - sync resolving startup messages into the playback log
  - dedupe repeated resolving messages
- Modify: `tests/test_player_window_ui.py`
  - cover resolving-state log sync and duplicate suppression

### Task 1: Add the Resolving Log Contract

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_logs_resolving_startup_message(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window._set_startup_state(window._startup_coordinator.resolving())

    assert "正在解析播放地址" in window.log_view.toPlainText()


def test_player_window_does_not_duplicate_same_resolving_startup_message(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    state = window._startup_coordinator.resolving()
    window._set_startup_state(state)
    window._set_startup_state(state)

    assert window.log_view.toPlainText().splitlines() == ["正在解析播放地址"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "logs_resolving_startup_message or does_not_duplicate_same_resolving_startup_message" -v`
Expected: FAIL because `_set_startup_state(...)` only updates the startup widget and does not append resolving messages to the playback log.

- [ ] **Step 3: Add the minimal resolving-log sync**

```python
def _set_startup_state(self, state: PlaybackStartupState) -> None:
    self._startup_state = state
    self.playback_startup_status_label.setText(state.message)
    self._append_startup_state_log(state)
    ...


def _append_startup_state_log(self, state: PlaybackStartupState) -> None:
    if state.stage is not PlaybackStartupStage.RESOLVING:
        return
    self._append_log(state.message, dedupe=True)
```

- [ ] **Step 4: Add the dedupe-aware append helper**

```python
def _append_log(self, message: str, *, dedupe: bool = False) -> None:
    if not message:
        return
    existing_lines = self.log_view.toPlainText().splitlines()
    if dedupe and existing_lines and existing_lines[-1] == message:
        return
    ...
```

- [ ] **Step 5: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "logs_resolving_startup_message or does_not_duplicate_same_resolving_startup_message" -v`
Expected: PASS
