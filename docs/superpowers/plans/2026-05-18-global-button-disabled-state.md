# Global Button Disabled State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make disabled buttons read clearly across the app by unifying default buttons, round icon buttons, pill buttons, and local lightweight action buttons under one low-contrast disabled state system.

**Architecture:** Extend `ThemeTokens` with dedicated disabled-button colors, then thread those tokens through the global `QPushButton` stylesheet and the two shared button helpers in `theme.py`. After the shared theme layer is green, tighten the one remaining local override in `GlobalSearchPopup._action_button_qss()` and add focused regression coverage for widget call sites that already consume the shared helpers.

**Tech Stack:** Python 3.14, PySide6, pytest, Qt stylesheet helpers in `src/atv_player/ui/theme.py`

---

## File Structure

- Modify: `src/atv_player/ui/theme.py`
  - Owns `ThemeTokens`, concrete token sets, the application stylesheet, and shared button QSS helpers.
- Modify: `src/atv_player/ui/main_window.py`
  - Owns `GlobalSearchPopup._action_button_qss()`, the remaining handwritten local disabled button rule called out by the spec.
- Modify: `tests/test_theme.py`
  - Theme-level QSS regression coverage for tokens and shared helpers.
- Modify: `tests/test_main_window_ui.py`
  - Widget-level regression coverage for the round icon button path and the popup action-button override.
- Modify: `tests/test_poster_grid_page_ui.py`
  - Widget-level regression coverage for the pill-button helper as used by filter buttons.

### Task 1: Add theme-level failing tests for disabled button tokens and helper QSS

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `src/atv_player/ui/theme.py`

- [ ] **Step 1: Write the failing tests**

Add these tests near the existing stylesheet helper assertions in `tests/test_theme.py`:

```python
def test_theme_tokens_expose_button_disabled_colors() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    assert tokens.button_disabled_bg.startswith("#")
    assert tokens.button_disabled_border.startswith("#")
    assert tokens.button_disabled_text.startswith("#")


def test_build_application_stylesheet_uses_dedicated_disabled_button_tokens() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = manager.build_application_stylesheet("dark")

    assert "QPushButton:disabled" in qss
    assert f"background-color: {tokens.button_disabled_bg};" in qss
    assert f"border: 1px solid {tokens.button_disabled_border};" in qss
    assert f"color: {tokens.button_disabled_text};" in qss


def test_button_helpers_emit_disabled_rules_without_opacity() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    round_qss = theme_module.build_round_icon_button_qss(tokens)
    pill_qss = theme_module.build_pill_button_qss(tokens, checked_accent=True)

    for qss in (round_qss, pill_qss):
        assert "QPushButton:disabled" in qss
        assert tokens.button_disabled_bg in qss
        assert tokens.button_disabled_border in qss
        assert tokens.button_disabled_text in qss
        assert "opacity" not in qss
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_theme.py -k "theme_tokens_expose_button_disabled_colors or build_application_stylesheet_uses_dedicated_disabled_button_tokens or button_helpers_emit_disabled_rules_without_opacity" -v
```

Expected: FAIL because `ThemeTokens` does not expose `button_disabled_*` yet and the generated button QSS currently has no explicit `QPushButton:disabled` block in the helper functions.

- [ ] **Step 3: Write the minimal implementation in `theme.py`**

Update `ThemeTokens` and the three concrete token sets in `src/atv_player/ui/theme.py`:

```python
class ThemeTokens:
    window_bg: str
    panel_bg: str
    panel_alt_bg: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    input_bg: str
    input_border: str
    input_hover_border: str
    input_focus_ring: str
    button_bg: str
    button_primary_bg: str
    button_primary_text: str
    button_disabled_bg: str
    button_disabled_border: str
    button_disabled_text: str
    menu_bg: str
    menu_hover_bg: str
    menu_selected_bg: str
    ...
```

```python
LIGHT_TOKENS = ThemeTokens(
    ...
    button_bg="#fffaf5",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    button_disabled_bg="#f3ebe1",
    button_disabled_border="#d8cabc",
    button_disabled_text="#9d8f80",
    ...
)

DARK_TOKENS = ThemeTokens(
    ...
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    button_disabled_bg="#222836",
    button_disabled_border="#343c4d",
    button_disabled_text="#7f8898",
    ...
)

PLAYER_IMMERSIVE_TOKENS = ThemeTokens(
    ...
    button_bg="#232937",
    button_primary_bg="#ff6a3d",
    button_primary_text="#ffffff",
    button_disabled_bg="#222836",
    button_disabled_border="#343c4d",
    button_disabled_text="#7f8898",
    ...
)
```

Then thread those tokens into the three shared QSS builders:

```python
def build_application_stylesheet(self, theme: ResolvedTheme) -> str:
    tokens = self.tokens_for(theme)
    return f"""
    ...
    QPushButton {{
        background-color: {tokens.button_bg};
        border: 1px solid {tokens.border_subtle};
        border-radius: 12px;
        color: {tokens.text_primary};
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        border-color: {tokens.accent_hover};
    }}
    QPushButton:disabled {{
        background-color: {tokens.button_disabled_bg};
        border: 1px solid {tokens.button_disabled_border};
        color: {tokens.button_disabled_text};
    }}
    ...
    """
```

```python
def build_round_icon_button_qss(tokens: ThemeTokens, *, border_radius: int = 18) -> str:
    return f"""
    QPushButton {{
        border: 1px solid {tokens.input_border};
        border-radius: {border_radius}px;
        background: {tokens.input_bg};
        color: {tokens.text_primary};
        padding: 0;
    }}
    QPushButton:hover {{
        background: {tokens.panel_alt_bg};
        border-color: {tokens.accent_hover};
    }}
    QPushButton:disabled {{
        background: {tokens.button_disabled_bg};
        border: 1px solid {tokens.button_disabled_border};
        color: {tokens.button_disabled_text};
    }}
    """
```

```python
def build_pill_button_qss(tokens: ThemeTokens, *, checked_accent: bool = False) -> str:
    checked_block = ""
    if checked_accent:
        checked_block = f"""
        QPushButton:checked {{
            background-color: {tokens.input_bg};
            color: {tokens.accent};
            border: 1px solid {tokens.accent};
        }}
        QPushButton:checked:hover {{
            color: {tokens.accent_hover};
            border: 1px solid {tokens.accent_hover};
        }}
        """
    return f"""
    QPushButton {{
        background-color: {tokens.input_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.input_border};
        border-radius: 14px;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        background-color: {tokens.panel_alt_bg};
        border-color: {tokens.accent_hover};
    }}
    {checked_block}
    QPushButton:disabled,
    QPushButton:checked:disabled {{
        background-color: {tokens.button_disabled_bg};
        color: {tokens.button_disabled_text};
        border: 1px solid {tokens.button_disabled_border};
    }}
    """
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_theme.py -k "theme_tokens_expose_button_disabled_colors or build_application_stylesheet_uses_dedicated_disabled_button_tokens or button_helpers_emit_disabled_rules_without_opacity" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_theme.py src/atv_player/ui/theme.py
git commit -m "feat: unify shared button disabled styles"
```

### Task 2: Add widget-level failing tests for helper call sites and the local popup override

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_poster_grid_page_ui.py`
- Modify: `src/atv_player/ui/main_window.py`

- [ ] **Step 1: Write the failing regression tests**

Add one focused popup override test to `tests/test_main_window_ui.py` and extend the existing widget helper assertions:

```python
def test_main_window_global_search_button_styles_include_disabled_tokens(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from atv_player.ui.theme import ThemeManager, install_theme

    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "light")
    install_theme(app, manager, "light")

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
    )
    qtbot.addWidget(window)

    tokens = manager.tokens_for("light")
    stylesheet = window.global_search_button.styleSheet()

    assert "QPushButton:disabled" in stylesheet
    assert f"background: {tokens.button_disabled_bg};" in stylesheet
    assert f"border: 1px solid {tokens.button_disabled_border};" in stylesheet
    assert f"color: {tokens.button_disabled_text};" in stylesheet


def test_global_search_popup_action_button_qss_uses_disabled_button_text_token() -> None:
    from PySide6.QtWidgets import QApplication

    from atv_player.ui.theme import ThemeManager, current_tokens, install_theme

    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    install_theme(app, manager, "dark")

    qss = main_window_module.GlobalSearchPopup._action_button_qss()
    tokens = current_tokens()

    assert "QPushButton:disabled" in qss
    assert f"color: {tokens.button_disabled_text};" in qss
```

Extend the existing `test_history_page_search_styles_follow_resolved_dark_theme` in `tests/test_main_window_ui.py`:

```python
    assert tokens.button_disabled_bg in page.continue_button.styleSheet()
    assert tokens.button_disabled_border in page.continue_button.styleSheet()
    assert tokens.button_disabled_text in page.continue_button.styleSheet()
```

Extend `test_poster_grid_page_filter_buttons_use_light_theme_stylesheet` in `tests/test_poster_grid_page_ui.py`:

```python
    assert "QPushButton:disabled" in stylesheet
    assert tokens.button_disabled_bg in stylesheet
    assert tokens.button_disabled_border in stylesheet
    assert tokens.button_disabled_text in stylesheet
```

- [ ] **Step 2: Run the tests to verify the suite is red**

Run:

```bash
uv run pytest tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py -k "global_search_button_styles_include_disabled_tokens or global_search_popup_action_button_qss_uses_disabled_button_text_token or history_page_search_styles_follow_resolved_dark_theme or filter_buttons_use_light_theme_stylesheet" -v
```

Expected: FAIL because `GlobalSearchPopup._action_button_qss()` still uses `tokens.border_subtle` for disabled text, even though the shared helper-backed buttons now emit the new disabled token set.

- [ ] **Step 3: Write the minimal implementation in `main_window.py`**

Update the local override in `src/atv_player/ui/main_window.py`:

```python
@staticmethod
def _action_button_qss() -> str:
    tokens = current_tokens()
    return f"""
    QPushButton {{
        color: {tokens.text_secondary};
        font-size: 12px;
        border: none;
        background: transparent;
        padding: 0 4px;
    }}
    QPushButton:hover {{
        color: {tokens.accent_hover};
    }}
    QPushButton:disabled {{
        color: {tokens.button_disabled_text};
    }}
    """
```

Do not add background or border here. This override is intentionally lightweight; only the disabled text semantic needs to align with the shared token system.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py -k "global_search_button_styles_include_disabled_tokens or global_search_popup_action_button_qss_uses_disabled_button_text_token or history_page_search_styles_follow_resolved_dark_theme or filter_buttons_use_light_theme_stylesheet" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py src/atv_player/ui/main_window.py
git commit -m "feat: align local disabled button styling"
```

### Task 3: Run the narrow integration verification for the full change set

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_poster_grid_page_ui.py`
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/main_window.py`

- [ ] **Step 1: Run the combined verification slice**

Run:

```bash
uv run pytest tests/test_theme.py tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py -k "disabled_button or global_search_button_styles_include_disabled_tokens or global_search_popup_action_button_qss_uses_disabled_button_text_token or history_page_search_styles_follow_resolved_dark_theme or filter_buttons_use_light_theme_stylesheet" -v
```

Expected: PASS, covering token definitions, shared helper QSS, the round icon button path in `MainWindow`, the pill button path in `PosterGridPage` and `HistoryPage`, and the one remaining handwritten popup action-button override.

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff -- src/atv_player/ui/theme.py src/atv_player/ui/main_window.py tests/test_theme.py tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py
```

Expected: only the five planned files change, with no unrelated behavior or layout edits.

- [ ] **Step 3: Commit the verification if Task 1 and Task 2 were squashed locally**

If the worker kept the earlier commits separate, skip this step. If they implemented everything in one pass, use a single commit instead:

```bash
git add src/atv_player/ui/theme.py src/atv_player/ui/main_window.py tests/test_theme.py tests/test_main_window_ui.py tests/test_poster_grid_page_ui.py
git commit -m "feat: make disabled button states more visible"
```
