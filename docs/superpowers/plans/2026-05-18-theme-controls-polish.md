# Theme Controls Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish themed comboboxes, player controls, and player sliders so dropdowns match the brand system and the playback bar has stronger hierarchy, readable icons, and stronger slider feedback.

**Architecture:** Extend `theme.py` with richer control tokens plus dedicated QSS helpers for comboboxes, player buttons, and sliders. Keep application-level theme logic unchanged, and update `AdvancedSettingsDialog` / `PlayerWindow` to consume the new helpers and runtime-tinted icons through focused UI hooks.

**Tech Stack:** PySide6, Qt QSS, SVG icon assets, pytest/pytest-qt

---

### Task 1: Add failing tests for combobox and player control polish

**Files:**
- Modify: `tests/test_theme.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_combobox_qss_uses_brand_tokens() -> None:
    tokens = current_theme_manager().tokens_for("light")
    qss = build_combobox_qss(tokens)
    assert tokens.accent in qss
    assert "QComboBox::drop-down" in qss
    assert "QAbstractItemView" in qss


def test_advanced_settings_dialog_applies_branded_combobox_styles(qtbot) -> None:
    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: None)
    qtbot.addWidget(dialog)
    assert "QComboBox::drop-down" in dialog.theme_mode_combo.styleSheet()
    assert dialog.theme_mode_combo.styleSheet() == dialog.network_proxy_mode_combo.styleSheet()


def test_player_window_uses_primary_style_for_play_button_and_tinted_icons(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    assert window.play_button.property("control_role") == "primary"
    assert window.prev_button.property("control_role") == "secondary"
    assert window.play_button.icon().pixmap(24, 24).toImage() != QIcon(str(window._icons_dir / "play.svg")).pixmap(24, 24).toImage()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py tests/test_player_window_ui.py -k "combobox or tinted_icons or branded_combobox or primary_style_for_play_button" -q`
Expected: FAIL because combobox helper/style hooks and tinted icon behavior do not exist yet

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_theme.py tests/test_main_window_ui.py tests/test_player_window_ui.py
git commit -m "test: cover theme controls polish"
```

### Task 2: Implement branded combobox helper and token extensions

**Files:**
- Modify: `src/atv_player/ui/theme.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Add the new theme tokens and combobox helper**

```python
@dataclass(frozen=True, slots=True)
class ThemeTokens:
    ...
    input_hover_border: str
    input_focus_ring: str
    menu_bg: str
    menu_hover_bg: str
    menu_selected_bg: str
    player_button_bg: str
    player_button_hover_bg: str
    player_button_pressed_bg: str
    player_button_border: str
    player_button_icon: str
    player_primary_button_bg: str
    player_primary_button_hover_bg: str
    player_primary_button_pressed_bg: str
    player_primary_button_icon: str


def build_combobox_qss(tokens: ThemeTokens, *, border_radius: int = 12, min_height: int = 34) -> str:
    return f\"\"\"
    QComboBox {{
        min-height: {min_height}px;
        padding: 0 42px 0 12px;
        border: 1px solid {tokens.input_border};
        border-radius: {border_radius}px;
        background: {tokens.input_bg};
        color: {tokens.text_primary};
    }}
    ...
    \"\"\"
```

- [ ] **Step 2: Run the focused helper tests**

Run: `uv run pytest tests/test_theme.py -k "combobox" -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/atv_player/ui/theme.py tests/test_theme.py
git commit -m "feat: add branded combobox theme helpers"
```

### Task 3: Apply branded combobox styling to settings dialog and player combos

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Apply the new helper to dialog and player combobox widgets**

```python
combo_qss = build_combobox_qss(current_tokens())
for combo in (
    self.theme_mode_combo,
    self.network_proxy_mode_combo,
    self.youtube_cookie_browser_combo,
    self.mpv_hwdec_mode_combo,
):
    combo.setStyleSheet(combo_qss)
```

- [ ] **Step 2: Refresh the styles from existing `_apply_theme()` hooks**

Run: `uv run pytest tests/test_main_window_ui.py -k "branded_combobox or advanced_settings_dialog" -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py tests/test_main_window_ui.py
git commit -m "feat: style themed combobox controls"
```

### Task 4: Add runtime icon tinting and player control hierarchy

**Files:**
- Modify: `src/atv_player/ui/icon_cache.py`
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Add a tinted icon loader**

```python
def load_tinted_icon(path: str | Path, color: str) -> QIcon:
    ...
```

- [ ] **Step 2: Mark player buttons with primary/secondary roles and apply themed QSS**

```python
button.setProperty("control_role", "primary")
button.setStyleSheet(build_player_control_button_qss(player_tokens, role="primary"))
```

- [ ] **Step 3: Use tinted icons for the control buttons and keep play/mute state updates routed through the tinted loader**

Run: `uv run pytest tests/test_player_window_ui.py -k "tinted_icons or primary_style_for_play_button or icon_updates_use_cached_icon_loader" -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/atv_player/ui/icon_cache.py src/atv_player/ui/theme.py src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: polish player control visuals"
```

### Task 5: Run the final verification set

**Files:**
- Test: `tests/test_theme.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_theme.py tests/test_main_window_ui.py tests/test_player_window_ui.py -k "theme or advanced_settings_dialog or history_page_search_styles_follow_resolved_dark_theme or filter_buttons_use_light_theme_stylesheet or filter_group_labels_use_bold_blue_text or primary_style_for_play_button or tinted_icons" -q`
Expected: PASS

- [ ] **Step 2: Review git diff**

Run: `git diff --stat`
Expected: Only theme/control polish files and targeted test updates are present

- [ ] **Step 3: Commit final verification-ready state**

```bash
git add src/atv_player/ui/theme.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py src/atv_player/ui/icon_cache.py tests/test_theme.py tests/test_main_window_ui.py tests/test_player_window_ui.py docs/superpowers/plans/2026-05-18-theme-controls-polish.md
git commit -m "feat: polish themed controls and player buttons"
```

### Task 6: Add strong-feedback slider styling

**Files:**
- Modify: `src/atv_player/ui/theme.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_theme.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing slider style tests**

```python
def test_build_slider_qss_uses_brand_fill_and_hover_handle() -> None:
    tokens = ThemeManager(system_theme_getter=lambda: "dark").player_tokens_for("dark")
    qss = build_slider_qss(tokens, groove_height=8, handle_diameter=18)
    assert tokens.accent in qss
    assert "QSlider::sub-page:horizontal" in qss
    assert "QSlider::handle:horizontal:hover" in qss


def test_player_window_applies_strong_feedback_slider_styles(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    assert "QSlider::sub-page:horizontal" in window.progress.styleSheet()
    assert "height: 8px" in window.progress.styleSheet()
    assert "height: 6px" in window.volume_slider.styleSheet()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_theme.py tests/test_player_window_ui.py -k "slider_qss or strong_feedback_slider_styles" -q`
Expected: FAIL because slider helper/style hooks do not exist yet

- [ ] **Step 3: Implement slider QSS and attach it in `_apply_theme()`**

```python
self.progress.setStyleSheet(build_slider_qss(player_tokens, groove_height=8, handle_diameter=18))
self.volume_slider.setStyleSheet(build_slider_qss(player_tokens, groove_height=6, handle_diameter=14))
```

- [ ] **Step 4: Re-run focused slider tests**

Run: `uv run pytest tests/test_theme.py tests/test_player_window_ui.py -k "slider_qss or strong_feedback_slider_styles" -q`
Expected: PASS
