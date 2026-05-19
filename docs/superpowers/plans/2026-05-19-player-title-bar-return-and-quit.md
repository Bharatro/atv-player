# Player Title Bar Return And Quit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated player title-bar `返回主窗口` action while changing the player title-bar `关闭` button to quit the entire application.

**Architecture:** Extend `CustomTitleBar` with an opt-in extra-action slot that preserves the default chrome layout for every existing window. Then wire `PlayerWindow` to register one extra return button and override the title-bar close signal to call the existing quit path instead of the return path.

**Tech Stack:** Python, PySide6, pytest-qt

---

## File Structure

- Modify: `src/atv_player/ui/window_chrome.py`
  Add a minimal extension point for optional title-bar action buttons.
- Modify: `src/atv_player/ui/player_window.py`
  Register the player-only return button and reroute the title-bar close button to application quit.
- Modify: `tests/test_window_chrome.py`
  Cover the generic title-bar extension point without depending on player behavior.
- Modify: `tests/test_player_window_ui.py`
  Cover the player-specific return button and quit semantics.

### Task 1: Extend The Title Bar For Optional Extra Actions

**Files:**
- Modify: `tests/test_window_chrome.py`
- Modify: `src/atv_player/ui/window_chrome.py`

- [ ] **Step 1: Write the failing title-bar extension test**

```python
def test_themed_widget_window_title_bar_can_insert_extra_action_buttons(qtbot) -> None:
    class ActionWindow(ThemedWidgetWindowBase):
        def __init__(self) -> None:
            super().__init__(title="Action Window", allow_minimize=True, allow_maximize=True, resizable=True)
            button = QPushButton("返回", self.title_bar())
            button.setObjectName("returnToMainButton")
            self.title_bar().set_extra_action_buttons([button])

    window = ActionWindow()
    qtbot.addWidget(window)

    buttons = [button.text() for button in window.title_bar().action_buttons()]

    assert buttons == ["返回", "—", "□", "✕"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_window_chrome.py -k "insert_extra_action_buttons" -q`
Expected: FAIL because `CustomTitleBar` does not yet expose `set_extra_action_buttons()` or `action_buttons()`.

- [ ] **Step 3: Write the minimal title-bar extension**

```python
class CustomTitleBar(QWidget):
    ...
    def __init__(...):
        ...
        self._extra_action_buttons: list[QPushButton] = []
        self._buttons_layout = QHBoxLayout()
        self._buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._buttons_layout.setSpacing(8)
        layout.addLayout(self._buttons_layout)
        self._rebuild_action_buttons()

    def set_extra_action_buttons(self, buttons: list[QPushButton]) -> None:
        self._extra_action_buttons = list(buttons)
        self._rebuild_action_buttons()

    def action_buttons(self) -> list[QPushButton]:
        return [
            *self._extra_action_buttons,
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ]
```
Keep button sizing consistent by applying the same `30x30` fixed size to any extra action button during rebuild.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_window_chrome.py -k "insert_extra_action_buttons" -q`
Expected: PASS

### Task 2: Add The Player Return Button First

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing player return-button tests**

```python
def test_player_window_title_bar_exposes_return_to_main_button(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.title_bar_return_button.text() == "返回"
    assert window.title_bar_return_button.toolTip() == "返回主窗口 (Ctrl+P)"


def test_player_window_title_bar_return_button_returns_to_main(qtbot) -> None:
    emitted = {"count": 0}
    config = AppConfig(last_active_window="player")
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(window)
    window.session = object()
    window.closed_to_main.connect(lambda: emitted.__setitem__("count", emitted["count"] + 1))

    window.title_bar_return_button.click()

    assert emitted["count"] == 1
    assert config.last_active_window == "main"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "title_bar_return_button" -q`
Expected: FAIL because `PlayerWindow` does not yet create `title_bar_return_button`.

- [ ] **Step 3: Write the minimal player return-button wiring**

```python
self.title_bar_return_button = QPushButton("返回", self.title_bar())
self.title_bar_return_button.setToolTip(self._format_tooltip("返回主窗口", "Ctrl+P"))
self.title_bar_return_button.clicked.connect(self._return_to_main)
self.title_bar().set_extra_action_buttons([self.title_bar_return_button])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "title_bar_return_button" -q`
Expected: PASS

### Task 3: Make Player Title-Bar Close Quit The App

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Write the failing quit-routing test**

```python
def test_player_window_title_bar_close_button_quits_application(qtbot, monkeypatch) -> None:
    quit_calls = {"count": 0}
    emitted = {"count": 0}
    config = AppConfig(last_active_window="player")
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None)
    qtbot.addWidget(window)
    window.closed_to_main.connect(lambda: emitted.__setitem__("count", emitted["count"] + 1))

    monkeypatch.setattr(QApplication, "quit", lambda *args, **kwargs: quit_calls.__setitem__("count", quit_calls["count"] + 1))

    window.title_bar().close_button.click()

    assert quit_calls["count"] == 1
    assert emitted["count"] == 0
    assert config.last_active_window == "player"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "title_bar_close_button_quits_application" -q`
Expected: FAIL because the player title-bar close button still routes through the generic `close()` signal wiring.

- [ ] **Step 3: Write the minimal quit routing**

```python
disconnect_close = getattr(self.title_bar().close_requested, "disconnect", None)
if callable(disconnect_close):
    self.title_bar().close_requested.disconnect()
self.title_bar().close_requested.connect(self._quit_application)
```

Keep the existing `closeEvent()` behavior for non-quit closes that originate elsewhere.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py -k "title_bar_close_button_quits_application" -q`
Expected: PASS

### Task 4: Run Regression Coverage

**Files:**
- Test: `tests/test_window_chrome.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run focused chrome and player regressions**

Run:

```bash
uv run pytest tests/test_window_chrome.py -q
uv run pytest tests/test_player_window_ui.py -k "title_bar or close_button or return_to_main or ctrl_q_quits_application or escape_shortcut_returns_to_main_when_not_fullscreen" -q
```

Expected: PASS for both commands.

- [ ] **Step 2: Review diff for scope**

Run: `git diff -- src/atv_player/ui/window_chrome.py src/atv_player/ui/player_window.py tests/test_window_chrome.py tests/test_player_window_ui.py`
Expected: Only title-bar extension, player wiring, and related tests changed.
