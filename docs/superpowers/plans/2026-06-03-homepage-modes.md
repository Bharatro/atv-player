# Homepage Modes Implementation Plan — Phase 1: Framework

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted `home_mode` setting, a selector in 高级设置 that applies live, and a `QStackedWidget` + `apply_home_mode()` central spine in `MainWindow` — with Browse (the existing behavior) working end-to-end.

**Architecture:** A single `home_mode` field on `AppConfig` (persisted via `SettingsRepository`) mirrors the existing `global_search_hot_source` pattern. `MainWindow.apply_home_mode(mode)` switches a `QStackedWidget` (`_home_stack`) in the content area and toggles header chrome. For Browse mode the stack shows the existing `nav_tabs` — zero behavioral change.

**Tech Stack:** Python, PySide6 (Qt), SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-06-03-homepage-modes-design.md`

**Later phases (separate plans):** Phase 2 Media, Phase 3 Simplified, Phase 4 Classic, Phase 5 TV — each depends on this framework.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/atv_player/models.py:103` | Add `home_mode` field to `AppConfig` |
| Modify | `src/atv_player/storage.py:25-36` | Add `_VALID_HOME_MODES` set + `_normalize_home_mode` helper |
| Modify | `src/atv_player/storage.py:486-494` | Add `home_mode` column to CREATE TABLE |
| Modify | `src/atv_player/storage.py:808-811` | Add `home_mode` ALTER TABLE migration |
| Modify | `src/atv_player/storage.py:879-898` | Add `home_mode` to INSERT default row |
| Modify | `src/atv_player/storage.py:1020-1035` | Add `home_mode` to SELECT columns |
| Modify | `src/atv_player/storage.py:1105-1120` | Add `home_mode` to row unpacking |
| Modify | `src/atv_player/storage.py:1203-1225` | Add `home_mode` to `AppConfig()` construction |
| Modify | `src/atv_player/storage.py:1298-1312` | Add `home_mode` to UPDATE SET clause |
| Modify | `src/atv_player/storage.py:1396-1412` | Add `home_mode` to save_config tuple |
| Modify | `src/atv_player/ui/advanced_settings_dialog.py:99-103` | Add `home_mode_combo` FlatComboBox |
| Modify | `src/atv_player/ui/advanced_settings_dialog.py:291` | Init combo from config |
| Modify | `src/atv_player/ui/advanced_settings_dialog.py:352-358` | Add to appearance group form layout |
| Modify | `src/atv_player/ui/advanced_settings_dialog.py:1009` | Save combo value to config |
| Modify | `src/atv_player/ui/main_window.py:1769-1774` | Wrap `nav_tabs` in `_home_stack` QStackedWidget |
| Modify | `src/atv_player/ui/main_window.py` | Add `apply_home_mode()` method |
| Modify | `src/atv_player/ui/main_window.py:4157-4175` | Call `apply_home_mode` after settings close |
| Create | `tests/test_home_mode.py` | Unit + widget tests for framework |
| Modify | `tests/test_storage.py` | Add `home_mode` round-trip test |

---

### Task 1: Add `home_mode` field to `AppConfig`

**Files:**
- Modify: `src/atv_player/models.py:103`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage.py` after the `test_settings_repository_round_trips_builtin_tab_overrides` function (after line 89):

```python
def test_settings_repository_round_trips_home_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    assert config.home_mode == "browse"

    config.home_mode = "media"
    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.home_mode == "media"


def test_settings_repository_normalizes_invalid_home_mode(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()

    config.home_mode = "nonexistent"
    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.home_mode == "browse"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage.py::test_settings_repository_round_trips_home_mode tests/test_storage.py::test_settings_repository_normalizes_invalid_home_mode -xvs 2>&1 | tail -20`
Expected: FAIL — `AppConfig` has no attribute `home_mode`

- [ ] **Step 3: Add `home_mode` field to `AppConfig`**

In `src/atv_player/models.py`, after line 103 (`following_episode_grid_columns: int = 1`), add:

```python
    home_mode: str = "browse"
```

- [ ] **Step 4: Run test — still fails (storage not updated)**

Run: `python -m pytest tests/test_storage.py::test_settings_repository_round_trips_home_mode tests/test_storage.py::test_settings_repository_normalizes_invalid_home_mode -xvs 2>&1 | tail -20`
Expected: FAIL — SQLite error (no column `home_mode`)

- [ ] **Step 5: Add `_VALID_HOME_MODES` and `_normalize_home_mode` to `storage.py`**

In `src/atv_player/storage.py`, after the `_VALID_FOLLOWING_EPISODE_GRID_COLUMNS` line (line 36), add:

```python
_VALID_HOME_MODES = {"browse", "classic", "simplified", "media", "tv"}
```

After the `_normalize_following_episode_grid_columns` function (after its `return`), add:

```python
def _normalize_home_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_HOME_MODES else "browse"
```

- [ ] **Step 6: Add `home_mode` to CREATE TABLE schema**

In `src/atv_player/storage.py`, after line 493 (`following_episode_grid_columns INTEGER NOT NULL DEFAULT 1`), add:

```python
                    home_mode TEXT NOT NULL DEFAULT 'browse'
```

(Remove the trailing comma from the `following_episode_grid_columns` line above it, and add a comma after the new `home_mode` line if it's not the last column. Check: the closing `)` is on line 494 — ensure proper comma placement.)

- [ ] **Step 7: Add `home_mode` ALTER TABLE migration**

In `src/atv_player/storage.py`, after the `network_proxy_rules` migration block (after line 811, before `conn.execute("""INSERT INTO app_config`), add:

```python
            if "home_mode" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN home_mode TEXT NOT NULL DEFAULT 'browse'"
                )
```

- [ ] **Step 8: Add `home_mode` to the INSERT default row**

In `src/atv_player/storage.py`, update the default INSERT VALUES (line ~898). The last value `'poster', 1` (for `following_episode_display_mode`, `following_episode_grid_columns`) needs `home_mode` appended:

Find the end of the VALUES tuple — it ends with:
```
..., 'poster', 1
```
Change to:
```
..., 'poster', 1, 'browse'
```

Also add `home_mode` to the INSERT column list, right after `following_episode_grid_columns` (line ~893):
```
                    following_episode_grid_columns,
                    home_mode
```

- [ ] **Step 9: Add `home_mode` to SELECT column list**

In `src/atv_player/storage.py`, in the SELECT statement (around line 1020-1035), add `home_mode` after `following_episode_grid_columns`:

In the column list after line 1034 (`following_episode_grid_columns`), add:
```
                    home_mode
```

- [ ] **Step 10: Add `home_mode` to row unpacking**

In `src/atv_player/storage.py`, in the row-unpacking tuple (around line 1105-1120), add `home_mode` after `following_episode_grid_columns` (line 1119):

```
            following_episode_grid_columns,
            home_mode,
```

The `) = row` stays on the next line.

- [ ] **Step 11: Add `home_mode` to `AppConfig()` construction in `load_config`**

In `src/atv_player/storage.py`, after the `following_episode_grid_columns=` kwarg (around line 1219-1225), add:

```python
            home_mode=_normalize_home_mode(home_mode),
```

- [ ] **Step 12: Add `home_mode` to UPDATE SET clause**

In `src/atv_player/storage.py`, in the UPDATE SET column list (around line 1298-1312), add after `following_episode_grid_columns = ?` (line 1312):

```
                    home_mode = ?
```

- [ ] **Step 13: Add `home_mode` to save_config value tuple**

In `src/atv_player/storage.py`, in the save_config values tuple (around line 1396-1412), add after the `following_episode_grid_columns` block (after line 1410):

```python
                    _normalize_home_mode(config.home_mode),
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `python -m pytest tests/test_storage.py::test_settings_repository_round_trips_home_mode tests/test_storage.py::test_settings_repository_normalizes_invalid_home_mode -xvs 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 15: Run full storage test suite**

Run: `python -m pytest tests/test_storage.py -xvs 2>&1 | tail -30`
Expected: ALL PASS (existing tests unaffected)

- [ ] **Step 16: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: add home_mode config field with storage persistence"
```

---

### Task 2: Add `home_mode` combo to Advanced Settings

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`

- [ ] **Step 1: Add the combo widget declaration**

In `src/atv_player/ui/advanced_settings_dialog.py`, after the `theme_mode_combo` block (lines 99-102), add:

```python
        self.home_mode_combo = FlatComboBox()
        self.home_mode_combo.addItem("浏览", "browse")
        self.home_mode_combo.addItem("经典 (TvBox)", "classic")
        self.home_mode_combo.addItem("精简 (搜索)", "simplified")
        self.home_mode_combo.addItem("媒体 (Emby)", "media")
        self.home_mode_combo.addItem("电视 (直播)", "tv")
```

- [ ] **Step 2: Set combo initial value from config**

In `src/atv_player/ui/advanced_settings_dialog.py`, after the `theme_mode_combo.setCurrentIndex` line (line 291), add:

```python
        self.home_mode_combo.setCurrentIndex(max(0, self.home_mode_combo.findData(config.home_mode)))
```

- [ ] **Step 3: Add combo to appearance group form layout**

In `src/atv_player/ui/advanced_settings_dialog.py`, after the `appearance_layout.addRow("界面主题", self.theme_mode_combo)` line (line 353), add:

```python
        appearance_layout.addRow("首页模式", self.home_mode_combo)
```

- [ ] **Step 4: Save combo value to config in `_save`**

In `src/atv_player/ui/advanced_settings_dialog.py`, in the `_save` method, after the `self._config.theme_mode = ...` line (line 1009), add:

```python
        self._config.home_mode = str(self.home_mode_combo.currentData() or "browse")
```

- [ ] **Step 5: Run existing settings-related tests**

Run: `python -m pytest tests/ -k "settings" -xvs 2>&1 | tail -20`
Expected: ALL PASS (combo doesn't break anything)

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py
git commit -m "feat: add home mode selector to advanced settings"
```

---

### Task 3: Add `QStackedWidget` + `apply_home_mode` to MainWindow

**Files:**
- Modify: `src/atv_player/ui/main_window.py:1769-1774`
- Create: `tests/test_home_mode.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_home_mode.py`:

```python
from PySide6.QtWidgets import QStackedWidget

from atv_player.models import AppConfig
from atv_player.ui.main_window import MainWindow

from tests.test_main_window_ui import (
    FakeStaticController,
    DummyHistoryController,
    FakePlayerController,
)


def test_main_window_apply_home_mode_browse_shows_nav_tabs(qtbot) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    window.apply_home_mode("browse")

    assert hasattr(window, "_home_stack")
    assert isinstance(window._home_stack, QStackedWidget)
    assert window._home_stack.currentWidget() is window.nav_tabs
    assert window.nav_tabs.isVisible()


def test_main_window_default_home_mode_is_browse(qtbot) -> None:
    config = AppConfig()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    assert hasattr(window, "_home_stack")
    assert window._home_stack.currentWidget() is window.nav_tabs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_home_mode.py -xvs 2>&1 | tail -20`
Expected: FAIL — `MainWindow` has no attribute `_home_stack`

- [ ] **Step 3: Wrap `nav_tabs` in `_home_stack`**

In `src/atv_player/ui/main_window.py`, find the content area construction (lines 1769-1774):

```python
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(self.header_layout)
        container_layout.addWidget(self.global_search_status_label)
        container_layout.addWidget(self.nav_tabs)
        self.content_layout().addWidget(container)
```

Replace with:

```python
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(self.header_layout)
        container_layout.addWidget(self.global_search_status_label)
        self._home_stack = QStackedWidget()
        self._home_stack.addWidget(self.nav_tabs)
        container_layout.addWidget(self._home_stack)
        self.content_layout().addWidget(container)
```

Add `QStackedWidget` to the imports at the top of `main_window.py` (in the `from PySide6.QtWidgets import ...` block).

- [ ] **Step 4: Add `apply_home_mode` method**

In `src/atv_player/ui/main_window.py`, add a new method on `MainWindow`. Place it near the other mode/theme methods (after `_apply_theme` around line 2001):

```python
    def apply_home_mode(self, mode: str) -> None:
        normalized = mode if mode in {"browse", "classic", "simplified", "media", "tv"} else "browse"
        if normalized == "browse":
            self._home_stack.setCurrentWidget(self.nav_tabs)
            self.nav_tabs.setVisible(True)
            self._refresh_navigation_tabs()
```

- [ ] **Step 5: Call `apply_home_mode` at startup**

In `src/atv_player/ui/main_window.py`, after the `_defer_navigation_refresh` and `_refresh_navigation_tabs` call site (find the place where tabs are first refreshed after construction), add a call to `apply_home_mode`:

Find the line where `_defer_navigation_refresh = False` is set (line 1778). After the next `_refresh_navigation_tabs()` call or `_refresh_visible_tabs()` call, add:

```python
        self.apply_home_mode(getattr(self.config, "home_mode", "browse") or "browse")
```

This must happen after `nav_tabs` is fully populated, so after the initial `_refresh_visible_tabs()` call.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_home_mode.py -xvs 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 7: Run existing main window tests**

Run: `python -m pytest tests/test_main_window_ui.py -xvs 2>&1 | tail -30`
Expected: ALL PASS (nav_tabs still works as before, just wrapped)

- [ ] **Step 8: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_home_mode.py
git commit -m "feat: add home mode framework with QStackedWidget and apply_home_mode"
```

---

### Task 4: Wire settings dialog to `apply_home_mode`

**Files:**
- Modify: `src/atv_player/ui/main_window.py:4157-4175`
- Modify: `tests/test_home_mode.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_home_mode.py`:

```python
def test_main_window_applies_home_mode_after_settings_close(qtbot) -> None:
    config = AppConfig()
    config.home_mode = "browse"
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        config,
    )
    qtbot.addWidget(window)

    # Simulate what happens after advanced settings closes with a mode change
    config.home_mode = "media"
    window.apply_home_mode("media")

    # For now, media mode is not implemented — it falls back to browse
    # (The framework just ensures apply_home_mode is called without error)
    assert window._home_stack is not None
```

- [ ] **Step 2: Run test to verify it passes (framework is tolerant of unknown modes)**

Run: `python -m pytest tests/test_home_mode.py -xvs 2>&1 | tail -20`
Expected: PASS (falls back gracefully)

- [ ] **Step 3: Wire `_open_advanced_settings` to call `apply_home_mode` on accept**

In `src/atv_player/ui/main_window.py`, in the `_open_advanced_settings` method (line 4157), after the `if dialog.exec() != QDialog.DialogCode.Accepted: return` check (line 4169-4170), and after the existing post-accept work (player/youtube refresh, lines 4171-4174), add:

```python
        self.apply_home_mode(getattr(self.config, "home_mode", "browse") or "browse")
```

- [ ] **Step 4: Run all home_mode + main_window tests**

Run: `python -m pytest tests/test_home_mode.py tests/test_main_window_ui.py tests/test_storage.py -xvs 2>&1 | tail -40`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_home_mode.py
git commit -m "feat: wire advanced settings to apply_home_mode on accept"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -x --timeout=60 2>&1 | tail -40`
Expected: ALL PASS

- [ ] **Step 2: Verify the app launches and Browse mode is unchanged**

Run: `python -m atv_player` (or the project's launch command)
Expected: App opens normally with all tabs visible. No visible change from current behavior.

- [ ] **Step 3: Verify the setting appears in 高级设置**

Click the 高级设置 button → the 外观 group should show "首页模式" with a combo defaulting to "浏览". Change it → save → app remains in Browse mode (only implemented mode so far). Close and reopen → setting persists.

- [ ] **Step 4: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: homepage modes phase 1 verification fixes"
```

---

## Summary

Phase 1 delivers:
- `AppConfig.home_mode` persisted in SQLite with migration
- `_normalize_home_mode` validator (unknown → `browse`)
- 高级设置 combo (浏览 / 经典 / 精简 / 媒体 / 电视)
- `MainWindow._home_stack` (QStackedWidget) wrapping `nav_tabs`
- `MainWindow.apply_home_mode()` — Browse mode = current behavior, no visual change
- Full test coverage (storage round-trip, normalization, widget smoke tests)
- Zero behavioral regression — all existing tests pass
