# Main Window Navigation Tab Contrast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main window's top navigation tabs remain readable under Windows dark theme by applying explicit tab text and state styling.

**Architecture:** Add a dedicated main-window navigation tabbar QSS helper in `theme.py`, then apply it only from `MainWindow` so the fix stays scoped to the affected surface. Cover the behavior with a UI regression test that proves the dark-theme tab bar no longer relies on native text colors.

**Tech Stack:** Python 3, PySide6, pytest, pytest-qt, existing `ThemeManager` token system

---

### Task 1: Add the failing navigation theme regression test

**Files:**
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_window_navigation_tabs_use_explicit_dark_theme_text_colors(qtbot) -> None:
    from atv_player.ui.theme import ThemeManager, install_theme

    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    install_theme(app, manager, "dark")

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    tokens = manager.tokens_for("dark")
    stylesheet = window.nav_tabs.tab_bar.styleSheet()

    assert f"color: {tokens.text_primary};" in stylesheet
    assert f"color: {tokens.accent};" in stylesheet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main_window_ui.py -k "navigation_tabs_use_explicit_dark_theme_text_colors" -q`
Expected: FAIL because the main window does not yet assign a dedicated stylesheet to `nav_tabs.tab_bar`.

- [ ] **Step 3: Write minimal implementation**

```python
def _apply_navigation_tab_theme(self) -> None:
    tokens = current_tokens()
    self.nav_tabs.tab_bar.setStyleSheet(build_navigation_tabbar_qss(tokens))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main_window_ui.py -k "navigation_tabs_use_explicit_dark_theme_text_colors" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/theme.py src/atv_player/ui/main_window.py
git commit -m "fix: style main window navigation tabs"
```

### Task 2: Cover the new theme helper directly

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `src/atv_player/ui/theme.py`

- [ ] **Step 1: Write the failing helper test**

```python
def test_build_navigation_tabbar_qss_uses_explicit_dark_theme_text_colors() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_navigation_tabbar_qss(tokens)

    assert f"color: {tokens.text_primary};" in qss
    assert f"color: {tokens.accent};" in qss
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_theme.py -k "build_navigation_tabbar_qss_uses_explicit_dark_theme_text_colors" -q`
Expected: FAIL because `build_navigation_tabbar_qss` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_navigation_tabbar_qss(tokens: ThemeTokens) -> str:
    return f"""
    QTabBar::tab {{
        color: {tokens.text_primary};
    }}
    QTabBar::tab:selected {{
        color: {tokens.accent};
    }}
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_theme.py -k "build_navigation_tabbar_qss_uses_explicit_dark_theme_text_colors" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_theme.py src/atv_player/ui/theme.py
git commit -m "test: cover navigation tab theme helper"
```

### Task 3: Run the focused regression slice

**Files:**
- Verify: `tests/test_theme.py`
- Verify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Run the focused regression commands**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py -k "navigation_tabbar or navigation_tabs_use_explicit_dark_theme_text_colors" -q`
Expected: PASS

- [ ] **Step 2: Run a broader main-window/theme regression slice**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py -q`
Expected: PASS with no regressions in shared theme helpers or main-window UI behavior.
