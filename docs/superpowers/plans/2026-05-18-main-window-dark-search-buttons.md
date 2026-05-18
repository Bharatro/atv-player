# Main Window Dark Search Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main window's dark-theme search and hot-search icon buttons visibly stronger without changing layout, behavior, or button count.

**Architecture:** Keep the current main-window search layout intact, but separate the problem into two reusable pieces: path-based runtime icon tinting in `icon_cache.py`, and a more configurable round-icon button QSS helper in `theme.py`. Then apply both to the two search buttons in `MainWindow`, including the theme-refresh path so theme switches keep the icons and surfaces in sync.

**Tech Stack:** PySide6, Qt QSS, SVG icons, pytest, pytest-qt

---

## File Structure

- `src/atv_player/ui/icon_cache.py`
  Adds a small `load_tinted_icon(...)` helper so callers can tint SVG icons from a file path without reimplementing cache plumbing.
- `src/atv_player/ui/theme.py`
  Extends `build_round_icon_button_qss(...)` with optional surface overrides while preserving the existing disabled-state contract.
- `src/atv_player/ui/main_window.py`
  Applies the stronger button surface and tinted icons to `global_search_button` and `global_search_popup_button` in both initialization and `_apply_theme()`.
- `tests/test_theme.py`
  Covers the new round-icon helper surface overrides and ensures disabled styling still remains explicit.
- `tests/test_main_window_ui.py`
  Adds a dark-theme regression test proving the two main-window search buttons use the stronger surface tokens and non-raw tinted icons.

### Task 1: Add Failing Tests For The Dark Search Button Treatment

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing helper and main-window tests**

```python
# tests/test_theme.py
def test_build_round_icon_button_qss_accepts_surface_overrides() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_round_icon_button_qss(
        tokens,
        background=tokens.button_bg,
        border_color=tokens.input_hover_border,
        text_color=tokens.text_primary,
        hover_background=tokens.panel_alt_bg,
        hover_border_color=tokens.accent_hover,
    )

    assert f"background: {tokens.button_bg};" in qss
    assert f"border: 1px solid {tokens.input_hover_border};" in qss
    assert f"color: {tokens.text_primary};" in qss
    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"border-color: {tokens.accent_hover};" in qss
    assert "QPushButton:disabled" in qss
```

```python
# tests/test_main_window_ui.py
def test_main_window_global_search_icon_buttons_use_dark_theme_contrast_treatment(qtbot) -> None:
    from atv_player.ui.icon_cache import load_icon
    from atv_player.ui.theme import ThemeManager, install_theme

    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    install_theme(app, manager, "dark")

    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=SearchableController([]),
        live_controller=FakeStaticController(),
        emby_controller=SearchableController([]),
        jellyfin_controller=SearchableController([]),
        feiniu_controller=SearchableController([]),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        plugin_manager=FakePluginManager(),
    )
    qtbot.addWidget(window)
    window.show()

    tokens = manager.tokens_for("dark")
    button_qss = window.global_search_button.styleSheet()

    assert f"background: {tokens.button_bg};" in button_qss
    assert f"border: 1px solid {tokens.input_hover_border};" in button_qss
    assert f"border-color: {tokens.accent_hover};" in button_qss

    raw_search = load_icon(window._SEARCH_ICON_PATH).pixmap(24, 24).toImage()
    raw_hot = load_icon(window._SEARCH_POPUP_ICON_PATH).pixmap(24, 24).toImage()

    assert window.global_search_button.icon().pixmap(24, 24).toImage() != raw_search
    assert window.global_search_popup_button.icon().pixmap(24, 24).toImage() != raw_hot
    assert window.global_search_button.width() == 36
    assert window.global_search_popup_button.width() == 36
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py -k "round_icon_button_qss_accepts_surface_overrides or global_search_icon_buttons_use_dark_theme_contrast_treatment" -q`

Expected: FAIL because `build_round_icon_button_qss(...)` does not yet accept override arguments, and `MainWindow` still uses raw `load_icon(...)` plus the weaker input-like button surface.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_theme.py tests/test_main_window_ui.py
git commit -m "test: cover dark global search button treatment"
```

### Task 2: Add Reusable Tinting And Stronger Round-Button Surface Controls

**Files:**
- Modify: `src/atv_player/ui/icon_cache.py`
- Modify: `src/atv_player/ui/theme.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Add a path-based tinted icon helper**

```python
# src/atv_player/ui/icon_cache.py
def load_tinted_icon(path: str | Path, color: str, *, size: int | QSize = 24) -> QIcon:
    return tint_icon(load_icon(path), color, size=size)
```

- [ ] **Step 2: Extend the round-icon button helper with surface overrides**

```python
# src/atv_player/ui/theme.py
def build_round_icon_button_qss(
    tokens: ThemeTokens,
    *,
    border_radius: int = 18,
    background: str | None = None,
    border_color: str | None = None,
    text_color: str | None = None,
    hover_background: str | None = None,
    hover_border_color: str | None = None,
) -> str:
    resolved_background = background or tokens.input_bg
    resolved_border_color = border_color or tokens.input_border
    resolved_text_color = text_color or tokens.text_primary
    resolved_hover_background = hover_background or tokens.panel_alt_bg
    resolved_hover_border_color = hover_border_color or tokens.accent_hover
    return f"""
    QPushButton {{
        border: 1px solid {resolved_border_color};
        border-radius: {border_radius}px;
        background: {resolved_background};
        color: {resolved_text_color};
        padding: 0;
    }}
    QPushButton:hover {{
        background: {resolved_hover_background};
        border-color: {resolved_hover_border_color};
    }}
    QPushButton:disabled {{
        background: {tokens.button_disabled_bg};
        border: 1px solid {tokens.button_disabled_border};
        color: {tokens.button_disabled_text};
    }}
    """
```

- [ ] **Step 3: Run the helper tests to verify they pass**

Run: `uv run pytest tests/test_theme.py -k "round_icon_button_qss" -q`

Expected: PASS with both the new override test and the existing disabled-state helper test green.

- [ ] **Step 4: Commit the shared helper changes**

```bash
git add src/atv_player/ui/icon_cache.py src/atv_player/ui/theme.py tests/test_theme.py
git commit -m "feat: add tinted round icon button helpers"
```

### Task 3: Apply The Dark Contrast Treatment To MainWindow And Verify It

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`
- Verify: `tests/test_theme.py`

- [ ] **Step 1: Route both search buttons through a single themed helper path**

```python
# src/atv_player/ui/main_window.py
from atv_player.ui.icon_cache import load_icon, load_tinted_icon
```

```python
# src/atv_player/ui/main_window.py
def _apply_global_search_button_theme(self) -> None:
    tokens = current_tokens()
    button_qss = build_round_icon_button_qss(
        tokens,
        background=tokens.button_bg,
        border_color=tokens.input_hover_border,
        text_color=tokens.text_primary,
        hover_background=tokens.panel_alt_bg,
        hover_border_color=tokens.accent_hover,
    )
    self.global_search_button.setStyleSheet(button_qss)
    self.global_search_popup_button.setStyleSheet(button_qss)
    self.global_search_button.setIcon(load_tinted_icon(self._SEARCH_ICON_PATH, tokens.text_primary))
    self.global_search_popup_button.setIcon(load_tinted_icon(self._SEARCH_POPUP_ICON_PATH, tokens.text_primary))
```

```python
# src/atv_player/ui/main_window.py
self.global_search_button.setFixedSize(36, 36)
self.global_search_popup_button.setFixedSize(36, 36)
self._apply_global_search_button_theme()
```

```python
# src/atv_player/ui/main_window.py
def _apply_theme(self) -> None:
    tokens = current_tokens()
    self.global_search_edit.setStyleSheet(build_search_line_edit_qss(tokens, border_radius=18, min_height=36))
    self._apply_global_search_button_theme()
    self._global_search_popup._apply_theme()
    ...
```

- [ ] **Step 2: Run the focused main-window tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "global_search_button_styles_include_disabled_tokens or global_search_icon_buttons_use_dark_theme_contrast_treatment or centered_rounded_search_box_with_icon_controls" -q`

Expected: PASS with the existing layout assertions intact and the new dark-theme contrast test green.

- [ ] **Step 3: Run the broader theme and main-window regression slice**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py -q`

Expected: PASS with no regressions in shared theme helpers or main-window UI behavior.

- [ ] **Step 4: Commit the main-window integration**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: strengthen dark global search buttons"
```

## Self-Review

- Spec coverage: the plan covers runtime icon tinting, stronger dark button surfaces, no layout change, and focused regression coverage for the two search buttons.
- Placeholder scan: no `TODO`/`TBD` markers or implicit “write tests later” steps remain.
- Type consistency: the plan uses one helper name, `_apply_global_search_button_theme()`, and one new icon helper, `load_tinted_icon(...)`, consistently across all tasks.
