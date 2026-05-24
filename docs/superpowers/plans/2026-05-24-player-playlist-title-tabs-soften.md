# Player Playlist Title Tabs Soften Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the visual weight of the playback window's `剧集标题` / `原始文件名` tabs by shrinking their font size and chrome without changing behavior anywhere else.

**Architecture:** Keep the shared player tabbar colors and state logic intact, but introduce a compact, player-specific tabbar QSS helper for `playlist_title_tabs`. Verify the exact compact sizing through `tests/test_theme.py`, then switch `PlayerWindow._apply_theme()` to use the compact helper so only this tab group changes.

**Tech Stack:** Python, PySide6, pytest, existing `theme.py` QSS builder helpers

---

### Task 1: Add a compact player tabbar helper and lock its QSS with tests

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `src/atv_player/ui/theme.py`

- [ ] **Step 1: Write the failing tests in `tests/test_theme.py`**

```python
def test_build_player_tabbar_qss_uses_default_player_tab_spacing() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_player_tabbar_qss(tokens)

    assert "font-size: 13px;" in qss
    assert "padding: 8px 14px;" in qss
    assert "border-radius: 12px;" in qss
    assert "margin-right: 6px;" in qss


def test_build_compact_player_tabbar_qss_uses_smaller_chrome() -> None:
    manager = ThemeManager(system_theme_getter=lambda: "light")
    tokens = manager.tokens_for("light")

    qss = theme_module.build_compact_player_tabbar_qss(tokens)

    assert f"background: {tokens.panel_alt_bg};" in qss
    assert f"color: {tokens.text_secondary};" in qss
    assert "font-size: 12px;" in qss
    assert "padding: 6px 10px;" in qss
    assert "border-radius: 10px;" in qss
    assert "margin-right: 4px;" in qss
    assert f"border-color: {tokens.accent};" in qss
```

- [ ] **Step 2: Run the tests to confirm the new compact helper is missing**

Run: `uv run pytest tests/test_theme.py -k "player_tabbar_qss" -v`

Expected: FAIL because `build_compact_player_tabbar_qss` does not exist yet, and the default player tabbar test also fails until the default helper explicitly emits `font-size`.

- [ ] **Step 3: Implement the minimal theme helper in `src/atv_player/ui/theme.py`**

```python
def build_player_tabbar_qss(
    tokens: ThemeTokens,
    *,
    font_size: int = 13,
    padding: str = "8px 14px",
    border_radius: int = 12,
    margin_right: int = 6,
) -> str:
    return f"""
    QTabBar::tab {{
        background: {tokens.panel_alt_bg};
        color: {tokens.text_secondary};
        border: 1px solid {tokens.border_subtle};
        border-radius: {border_radius}px;
        font-size: {font_size}px;
        padding: {padding};
        margin-right: {margin_right}px;
    }}
    QTabBar::tab:hover {{
        color: {tokens.text_primary};
        border-color: {tokens.input_hover_border};
    }}
    QTabBar::tab:selected {{
        background: {tokens.menu_selected_bg};
        color: {tokens.text_primary};
        border-color: {tokens.accent};
    }}
    """


def build_compact_player_tabbar_qss(tokens: ThemeTokens) -> str:
    return build_player_tabbar_qss(
        tokens,
        font_size=12,
        padding="6px 10px",
        border_radius=10,
        margin_right=4,
    )
```

- [ ] **Step 4: Run the theme tests again**

Run: `uv run pytest tests/test_theme.py -k "player_tabbar_qss" -v`

Expected: PASS with both player-tabbar tests green.

- [ ] **Step 5: Commit the helper and tests**

```bash
git add tests/test_theme.py src/atv_player/ui/theme.py
git commit -m "feat: soften player playlist title tab styles"
```

### Task 2: Apply the compact helper only to the playback window tabs and verify no behavior changed

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Write the failing usage change in `src/atv_player/ui/player_window.py`**

```python
from atv_player.ui.theme import (
    build_compact_player_tabbar_qss,
    build_player_control_button_qss,
    build_player_immersive_qss,
    build_player_list_qss,
    build_player_panel_qss,
    build_player_section_heading_qss,
    build_player_tabbar_qss,
    build_player_text_panel_qss,
)
```

```python
        self.playlist_title_tabs.setStyleSheet(build_compact_player_tabbar_qss(tokens))
```

- [ ] **Step 2: Run the targeted test suite before implementation wiring**

Run: `uv run pytest tests/test_theme.py -k "player_tabbar_qss" -v`

Expected: PASS. This step is the guard that the compact helper behavior is stable before wiring it into the window.

- [ ] **Step 3: Apply the import and helper switch in `src/atv_player/ui/player_window.py`**

```python
from atv_player.ui.theme import (
    build_compact_player_tabbar_qss,
    build_player_control_button_qss,
    build_player_immersive_qss,
    build_player_list_qss,
    build_player_panel_qss,
    build_player_section_heading_qss,
    build_player_tabbar_qss,
    build_player_text_panel_qss,
)
```

```python
        self.playlist_title_tabs.setStyleSheet(build_compact_player_tabbar_qss(tokens))
```

- [ ] **Step 4: Run verification for syntax and the targeted tests**

Run: `uv run python -m py_compile src/atv_player/ui/theme.py src/atv_player/ui/player_window.py`
Expected: no output

Run: `uv run pytest tests/test_theme.py -k "player_tabbar_qss" -v`
Expected: PASS

- [ ] **Step 5: Do manual playback-window verification**

Run the app and confirm:

```text
1. Open the playback window with a visible playlist sidebar.
2. Check that `剧集标题` and `原始文件名` tabs are visibly smaller and lower-contrast than before.
3. Hover each tab and confirm hover feedback still appears.
4. Switch between both tabs and confirm the playlist title mode still toggles correctly.
5. Scan nearby sidebar controls to confirm no other tab groups changed.
```

- [ ] **Step 6: Commit the playback-window wiring**

```bash
git add src/atv_player/ui/player_window.py
git commit -m "feat: use compact playlist title tabs in player window"
```
