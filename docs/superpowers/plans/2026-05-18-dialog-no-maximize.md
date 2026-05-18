# Dialog No Maximize Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the maximize button from every application-owned `ThemedDialogBase` dialog while keeping top-level windows unchanged.

**Architecture:** Keep `ThemedDialogBase` as-is because it already defaults to hiding the maximize button. The implementation is just removing the remaining `allow_maximize=True` opt-ins from dialog call sites and extending existing UI tests to assert that static dialogs and player runtime dialogs all hide the maximize button.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Lock the dialog behavior with failing UI tests

**Files:**
- Create: `tests/test_help_dialog.py`
- Modify: `tests/test_plugin_manager_dialog.py`
- Modify: `tests/test_live_source_manager_dialog.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_help_dialog.py`
- Test: `tests/test_plugin_manager_dialog.py`
- Test: `tests/test_live_source_manager_dialog.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
from PySide6.QtGui import QKeySequence

from atv_player.ui.help_dialog import ShortcutHelpDialog, shortcut_entries_for


def test_shortcut_help_dialog_hides_maximize_button(qtbot) -> None:
    dialog = ShortcutHelpDialog(shortcut_entries_for("main_window", QKeySequence("Ctrl+Q")))
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
```

```python
def test_plugin_manager_dialog_hides_maximize_button(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
```

```python
def test_live_source_manager_dialog_hides_maximize_button(qtbot) -> None:
    dialog = LiveSourceManagerDialog(FakeLiveSourceManager())
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True


def test_manual_live_source_dialog_hides_maximize_button(qtbot) -> None:
    dialog = ManualLiveSourceDialog(FakeLiveSourceManager(), source_id=2)
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
```

```python
def test_player_window_runtime_dialogs_hide_maximize_buttons(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    danmaku_settings = window._ensure_danmaku_settings_dialog()
    metadata_scrape = window._ensure_metadata_scrape_dialog()
    danmaku_source = window._ensure_danmaku_source_dialog()

    assert danmaku_settings.title_bar().maximize_button.isHidden() is True
    assert metadata_scrape.title_bar().maximize_button.isHidden() is True
    assert danmaku_source.title_bar().maximize_button.isHidden() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py -k "maximize_button or hide_maximize" -q`
Expected: FAIL because `ShortcutHelpDialog`, `PluginManagerDialog`, `LiveSourceManagerDialog`, `ManualLiveSourceDialog`, and `_PlayerToolDialog` still opt into `allow_maximize=True`.

- [ ] **Step 3: Remove maximize opt-ins from dialog constructors**

```python
class PluginManagerDialog(ThemedDialogBase, AsyncGuardMixin):
    def __init__(self, plugin_manager, parent=None) -> None:
        super().__init__(title="插件管理", parent=parent)
```

```python
class ShortcutHelpDialog(ThemedDialogBase):
    def __init__(
        self,
        entries: Sequence[ShortcutEntry],
        parent: QWidget | None = None,
        *,
        system_info_rows: Sequence[tuple[str, str]] | None = None,
        diagnostics_text: str = "",
    ) -> None:
        super().__init__(title="帮助", parent=parent)
```

```python
class LiveSourceManagerDialog(ThemedDialogBase):
    def __init__(self, manager, parent=None) -> None:
        super().__init__(title="直播源管理", parent=parent)
```

```python
class ManualLiveSourceDialog(ThemedDialogBase):
    def __init__(self, manager, source_id: int, parent=None) -> None:
        super().__init__(title="管理频道", parent=parent)
```

```python
class _PlayerToolDialog(ThemedDialogBase):
    def __init__(self, *, title: str, parent: QWidget, size: tuple[int, int]) -> None:
        super().__init__(title=title, parent=parent)
        self.resize(*size)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py -k "maximize_button or hide_maximize" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/help_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/manual_live_source_dialog.py src/atv_player/ui/player_window.py
git commit -m "feat: remove maximize buttons from app dialogs"
```

### Task 2: Run focused regression verification for dialog title bars

**Files:**
- Modify: none
- Test: `tests/test_window_chrome.py`
- Test: `tests/test_help_dialog.py`
- Test: `tests/test_plugin_manager_dialog.py`
- Test: `tests/test_live_source_manager_dialog.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Verify base dialog behavior still passes**

Run: `uv run pytest tests/test_window_chrome.py -q`
Expected: PASS, including `test_themed_dialog_hides_maximize_button_by_default`.

- [ ] **Step 2: Verify all dialog-specific tests pass together**

Run: `uv run pytest tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py -k "custom_title_bar or maximize_button or hide_maximize or runtime_dialogs" -q`
Expected: PASS

- [ ] **Step 3: Sanity-check the diff scope**

Run: `git diff --stat HEAD~1..HEAD -- src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/help_dialog.py src/atv_player/ui/live_source_manager_dialog.py src/atv_player/ui/manual_live_source_dialog.py src/atv_player/ui/player_window.py tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py`
Expected: only the five dialog call sites and the four dialog-oriented test files appear.

- [ ] **Step 4: Record verification output**

```text
Verified:
- uv run pytest tests/test_window_chrome.py -q
- uv run pytest tests/test_help_dialog.py tests/test_plugin_manager_dialog.py tests/test_live_source_manager_dialog.py tests/test_player_window_ui.py -k "custom_title_bar or maximize_button or hide_maximize or runtime_dialogs" -q
```
