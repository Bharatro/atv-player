# Combobox Visual Softening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make global comboboxes use a fill-first resting state with no visible top-edge emphasis, and make player control bar comboboxes blend into the dark playback controls while disabled states read more like labels.

**Architecture:** Keep `src/atv_player/ui/theme.py` as the single combobox QSS generator, but extend it so callers can override field surfaces, dropdown surfaces, and disabled-state treatment without inventing a second combobox helper. `PlayerWindow` continues to apply a dedicated combobox stylesheet in `_apply_theme()`, but switches from light app tokens to explicit player-surface overrides built from the same helper.

**Tech Stack:** PySide6, Qt QSS, pytest, pytest-qt

---

### Task 1: Add failing global combobox theme tests

**Files:**
- Modify: `tests/test_theme.py`
- Test: `src/atv_player/ui/theme.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_combobox_qss_uses_fill_first_default_state() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_combobox_qss(tokens)

    assert "QComboBox {\n        min-height: 34px;\n        padding: 0 40px 0 12px;\n        border: 1px solid transparent;" in qss
    assert f"background: {tokens.input_bg};" in qss
    assert f"border-color: {tokens.input_hover_border};" in qss
    assert f"border: 1px solid {tokens.input_focus_ring};" in qss
    assert "border-left: 1px solid transparent;" in qss
    assert "QComboBox:disabled" in qss
    assert "QComboBox:disabled::drop-down" in qss


def test_build_combobox_qss_accepts_surface_overrides() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "dark")
    tokens = manager.tokens_for("dark")

    qss = theme_module.build_combobox_qss(
        tokens,
        min_height=30,
        field_bg="#202734",
        drop_down_bg="#202734",
        text_color="#f5f7fb",
        disabled_field_bg="#212734",
        disabled_drop_down_bg="#212734",
        disabled_text_color="#b0b8c7",
    )

    assert "min-height: 30px" in qss
    assert "background: #202734;" in qss
    assert "color: #f5f7fb;" in qss
    assert "background: #212734;" in qss
    assert "color: #b0b8c7;" in qss
```

- [ ] **Step 2: Run the focused theme tests to verify they fail**

Run: `uv run pytest tests/test_theme.py -k "fill_first_default_state or accepts_surface_overrides" -q`
Expected: FAIL because `build_combobox_qss(...)` still emits `border: 1px solid {tokens.input_border}` by default and does not accept surface override keyword arguments.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_theme.py
git commit -m "test: cover fill-first combobox theme states"
```

### Task 2: Implement the fill-first global combobox stylesheet

**Files:**
- Modify: `src/atv_player/ui/theme.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Update `build_combobox_qss(...)` to support fill-based resting states**

```python
def build_combobox_qss(
    tokens: ThemeTokens,
    *,
    border_radius: int = 14,
    min_height: int = 34,
    field_bg: str | None = None,
    drop_down_bg: str | None = None,
    text_color: str | None = None,
    disabled_field_bg: str | None = None,
    disabled_drop_down_bg: str | None = None,
    disabled_text_color: str | None = None,
    border_color: str = "transparent",
    hover_border_color: str | None = None,
    focus_border_color: str | None = None,
    disabled_border_color: str = "transparent",
    drop_down_border_left_color: str = "transparent",
    disabled_drop_down_border_left_color: str = "transparent",
) -> str:
    resolved_field_bg = field_bg or tokens.input_bg
    resolved_drop_down_bg = drop_down_bg or resolved_field_bg
    resolved_text_color = text_color or tokens.text_primary
    resolved_disabled_field_bg = disabled_field_bg or tokens.panel_alt_bg
    resolved_disabled_drop_down_bg = disabled_drop_down_bg or resolved_disabled_field_bg
    resolved_disabled_text_color = disabled_text_color or tokens.text_secondary
    resolved_hover_border_color = hover_border_color or tokens.input_hover_border
    resolved_focus_border_color = focus_border_color or tokens.input_focus_ring

    return f"""
    QComboBox {{
        min-height: {min_height}px;
        padding: 0 40px 0 12px;
        border: 1px solid {border_color};
        border-radius: {border_radius}px;
        background: {resolved_field_bg};
        color: {resolved_text_color};
    }}
    QComboBox:hover {{
        border-color: {resolved_hover_border_color};
    }}
    QComboBox:focus {{
        border: 1px solid {resolved_focus_border_color};
    }}
    QComboBox:disabled {{
        border-color: {disabled_border_color};
        background: {resolved_disabled_field_bg};
        color: {resolved_disabled_text_color};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border: none;
        border-left: 1px solid {drop_down_border_left_color};
        background: {resolved_drop_down_bg};
        border-top-right-radius: {max(0, border_radius - 1)}px;
        border-bottom-right-radius: {max(0, border_radius - 1)}px;
    }}
    QComboBox::down-arrow {{
        width: 0px;
        height: 0px;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {tokens.text_secondary};
    }}
    QComboBox:disabled::drop-down {{
        border-left: 1px solid {disabled_drop_down_border_left_color};
        background: {resolved_disabled_drop_down_bg};
    }}
    QComboBox:disabled::down-arrow {{
        border-top: 6px solid {tokens.border_subtle};
    }}
    QComboBox QAbstractItemView {{
        background: {tokens.menu_bg};
        color: {tokens.text_primary};
        border: 1px solid {tokens.input_border};
        selection-background-color: {tokens.menu_selected_bg};
        selection-color: {tokens.text_primary};
        outline: 0;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 28px;
        padding: 4px 10px;
        background: transparent;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {tokens.menu_hover_bg};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {tokens.menu_selected_bg};
    }}
    """
```

- [ ] **Step 2: Run the focused theme tests to verify they pass**

Run: `uv run pytest tests/test_theme.py -k "fill_first_default_state or accepts_surface_overrides or build_combobox_qss_uses_brand_tokens" -q`
Expected: PASS with the new fill-first default state and overrideable combobox surfaces.

- [ ] **Step 3: Commit the minimal implementation**

```bash
git add src/atv_player/ui/theme.py tests/test_theme.py
git commit -m "feat: soften default combobox theme states"
```

### Task 3: Add failing player combobox styling tests

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Update the player combobox theme test to assert dark player surfaces**

```python
def test_player_window_uses_smaller_player_combos_and_disabled_state_styles(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    window.subtitle_combo.setEnabled(False)
    window._apply_theme()

    manager = player_window_module.current_theme_manager()
    theme = player_window_module.current_resolved_theme()
    player_tokens = manager.player_tokens_for(theme)

    assert "min-height: 30px" in window.speed_combo.styleSheet()
    assert "QComboBox {\n        min-height: 30px;\n        padding: 0 40px 0 12px;\n        border: 1px solid transparent;" in window.speed_combo.styleSheet()
    assert f"background: {player_tokens.player_button_bg};" in window.speed_combo.styleSheet()
    assert "#ffffff" not in window.speed_combo.styleSheet()
    assert f"background: {player_tokens.player_controls_bg};" in window.subtitle_combo.styleSheet()
    assert "QComboBox:disabled" in window.subtitle_combo.styleSheet()
    assert "QComboBox:disabled::drop-down" in window.subtitle_combo.styleSheet()
```

- [ ] **Step 2: Run the focused player test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py -k "smaller_player_combos_and_disabled_state_styles" -q`
Expected: FAIL because `_apply_theme()` still builds player comboboxes from light application input tokens, so the stylesheet still contains `background: #ffffff;`.

- [ ] **Step 3: Commit the failing player test**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover player combobox low-contrast surfaces"
```

### Task 4: Apply the darker player-specific combobox variant

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Update `_apply_theme()` to pass explicit player-surface overrides**

```python
    def _apply_theme(self) -> None:
        manager = current_theme_manager()
        theme = current_resolved_theme()
        tokens = manager.tokens_for(theme)
        player_tokens = manager.player_tokens_for(theme)
        ...
        combo_qss = build_combobox_qss(
            tokens,
            border_radius=12,
            min_height=30,
            field_bg=player_tokens.player_button_bg,
            drop_down_bg=player_tokens.player_button_bg,
            text_color=player_tokens.player_text_on_dark,
            disabled_field_bg=player_tokens.player_controls_bg,
            disabled_drop_down_bg=player_tokens.player_controls_bg,
            disabled_text_color=tokens.text_secondary,
            border_color="transparent",
            hover_border_color=player_tokens.player_button_border,
            focus_border_color=tokens.accent,
            disabled_border_color="transparent",
            drop_down_border_left_color="transparent",
            disabled_drop_down_border_left_color="transparent",
        )
        for combo in self._themed_comboboxes():
            combo.setStyleSheet(combo_qss)
        ...
```

- [ ] **Step 2: Run the focused player and theme tests to verify they pass**

Run: `uv run pytest tests/test_theme.py tests/test_player_window_ui.py -k "combobox or smaller_player_combos_and_disabled_state_styles" -q`
Expected: PASS with global fill-first comboboxes and player-specific dark low-contrast combobox surfaces.

- [ ] **Step 3: Commit the player combobox implementation**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: blend player comboboxes into playback controls"
```

### Task 5: Run final verification and review the diff

**Files:**
- Test: `tests/test_theme.py`
- Test: `tests/test_player_window_ui.py`
- Review: `src/atv_player/ui/theme.py`
- Review: `src/atv_player/ui/player_window.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_theme.py tests/test_player_window_ui.py -k "combobox or smaller_player_combos_and_disabled_state_styles" -q`
Expected: PASS with updated theme helper coverage and player combobox styling coverage.

- [ ] **Step 2: Run a broader player/theme sanity pass**

Run: `uv run pytest tests/test_theme.py tests/test_player_window_ui.py -q`
Expected: PASS with no regressions in adjacent player theme and slider tests.

- [ ] **Step 3: Review the diff footprint**

Run: `git diff --stat HEAD~4..HEAD`
Expected: Only `src/atv_player/ui/theme.py`, `src/atv_player/ui/player_window.py`, `tests/test_theme.py`, and `tests/test_player_window_ui.py` change for implementation, plus this plan document if kept in the same branch.

- [ ] **Step 4: Commit the verification-ready state**

```bash
git add src/atv_player/ui/theme.py src/atv_player/ui/player_window.py tests/test_theme.py tests/test_player_window_ui.py docs/superpowers/plans/2026-05-18-combobox-visual-softening.md
git commit -m "feat: soften combobox visuals"
```
