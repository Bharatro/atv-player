# Player Log Timestamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add millisecond timestamps to the player window's `播放日志` entries without breaking existing dedupe behavior.

**Architecture:** Keep the change local to `PlayerWindow` by formatting log lines at the single `_append_log(...)` entry point. Preserve dedupe by comparing the last raw message before timestamp formatting, and update the focused player-window tests to assert timestamped output instead of plain text lines.

**Tech Stack:** Python 3, PySide6, pytest, pytest-qt, stdlib `datetime`, stdlib `re`

---

## File Map

- `src/atv_player/ui/player_window.py`
  - inject timestamp formatting for playback-log lines
  - track the last raw log message for dedupe
  - reset dedupe state when the log is cleared
- `tests/test_player_window_ui.py`
  - add a small regex helper for timestamped log assertions
  - update existing resolving-log tests to expect timestamped lines
  - add focused regression coverage for timestamp formatting and dedupe

## Repo State Note

This repository already has local modifications in `src/atv_player/ui/player_window.py` and `tests/test_player_window_ui.py`. Execute the plan by layering the timestamp change on top of those edits. Do not revert unrelated hunks, and do not make a commit unless the diff has been reviewed and isolated.

### Task 1: Add Timestamped Playback Log Coverage

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing tests**

Add `import re` near the top of `tests/test_player_window_ui.py`, then add a helper plus two new tests and update the existing resolving-log assertions.

```python
import re
import threading
import time
from pathlib import Path
```

```python
def assert_timestamped_log_line(line: str, message: str) -> None:
    pattern = rf"\[\d{{2}}:\d{{2}}:\d{{2}}\.\d{{3}}\] {re.escape(message)}"
    assert re.fullmatch(pattern, line), line


def test_player_window_appends_timestamp_to_playback_logs(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window._append_log("播放失败: boom")

    assert_timestamped_log_line(window.log_view.toPlainText(), "播放失败: boom")


def test_player_window_does_not_duplicate_same_message_when_dedupe_enabled(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window._append_log("正在解析播放地址", dedupe=True)
    window._append_log("正在解析播放地址", dedupe=True)
    window._append_log("正在加载播放地址: Episode 1", dedupe=True)

    lines = window.log_view.toPlainText().splitlines()
    assert len(lines) == 2
    assert_timestamped_log_line(lines[0], "正在解析播放地址")
    assert_timestamped_log_line(lines[1], "正在加载播放地址: Episode 1")
```

Update the existing resolving-log assertions in the same file:

```python
def test_player_window_keeps_resolving_state_plain_and_logs_source_address_in_playback_log(qtbot) -> None:
    ...
    log_lines = window.log_view.toPlainText().splitlines()
    assert_timestamped_log_line(log_lines[0], "正在解析播放地址: https://pan.baidu.com/s/demo")
    assert_timestamped_log_line(log_lines[1], "正在加载播放地址: 网盘剧集")
    ready.set()


def test_player_window_logs_resolving_startup_message(qtbot) -> None:
    ...
    assert_timestamped_log_line(window.log_view.toPlainText(), "正在解析播放地址")


def test_player_window_does_not_duplicate_same_resolving_startup_message(qtbot) -> None:
    ...
    lines = window.log_view.toPlainText().splitlines()
    assert len(lines) == 1
    assert_timestamped_log_line(lines[0], "正在解析播放地址")
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "appends_timestamp_to_playback_logs or does_not_duplicate_same_message_when_dedupe_enabled or keeps_resolving_state_plain_and_logs_source_address_in_playback_log or logs_resolving_startup_message or does_not_duplicate_same_resolving_startup_message" -v
```

Expected:

- `test_player_window_appends_timestamp_to_playback_logs` fails because `_append_log(...)` still writes plain messages without a `[HH:MM:SS.mmm]` prefix.
- `test_player_window_keeps_resolving_state_plain_and_logs_source_address_in_playback_log` fails because the first line is still `正在解析播放地址: https://pan.baidu.com/s/demo` with no timestamp.
- `test_player_window_does_not_duplicate_same_message_when_dedupe_enabled` will keep passing only after the implementation compares raw messages before formatting; until then it either does not exist or fails once timestamps are added.

- [ ] **Step 3: Write the minimal implementation**

In `src/atv_player/ui/player_window.py`, add a timestamp formatter, store the last raw message, and reset that state when clearing the log.

```python
from datetime import datetime
```

Inside `PlayerWindow.__init__`, initialize the dedupe state near `self.log_view`:

```python
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self._last_log_message: str | None = None
```

Update the log helpers:

```python
    def _reset_log(self) -> None:
        self.log_view.clear()
        self._last_log_message = None

    def _format_log_line(self, message: str) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        return f"[{timestamp}] {message}"

    def _append_log(self, message: str, *, dedupe: bool = False) -> None:
        if not message:
            return
        if dedupe and self._last_log_message == message:
            return

        formatted_message = self._format_log_line(message)
        existing_text = self.log_view.toPlainText()
        if existing_text:
            self.log_view.append(formatted_message)
        else:
            self.log_view.setPlainText(formatted_message)
        self._last_log_message = message
```

This keeps all existing call sites unchanged while preserving dedupe semantics on the original message text.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "appends_timestamp_to_playback_logs or does_not_duplicate_same_message_when_dedupe_enabled or keeps_resolving_state_plain_and_logs_source_address_in_playback_log or logs_resolving_startup_message or does_not_duplicate_same_resolving_startup_message" -v
```

Expected:

- All selected tests pass.
- The resolving-log tests now see timestamped lines.
- The dedupe tests confirm that identical raw messages are still collapsed to a single line.

- [ ] **Step 5: Run one broader regression slice**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "正在加载播放地址 or 播放失败 or resolving" -v
```

If `-k` matching with Chinese substrings proves unreliable in this environment, run this broader targeted slice instead:

```bash
uv run pytest tests/test_player_window_ui.py -k "open_session or resolving or playback_log" -v
```

Expected:

- Existing player-log tests that only assert substring presence continue to pass.
- No additional failures appear from the timestamp prefix being added.

- [ ] **Step 6: Review the diff instead of committing automatically**

Run:

```bash
git diff -- src/atv_player/ui/player_window.py tests/test_player_window_ui.py
```

Expected:

- The diff is limited to timestamp formatting, dedupe state tracking, and the focused test updates above.
- No unrelated user changes are reverted or reformatted.

Because these files already contain local edits, stop after diff review unless the user explicitly asks for a commit or the timestamp change has been isolated from unrelated work.
