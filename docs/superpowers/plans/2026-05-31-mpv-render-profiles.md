# MPV Render Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-facing MPV render profiles, including Vulkan, while preserving existing playback settings.

**Architecture:** Store a new `mpv_render_profile` setting in `AppConfig`/SQLite, expose it in `AdvancedSettingsDialog`, and resolve it to MPV options inside `MpvWidget`. Keep stream profiles and extra MPV options layered after the render profile.

**Tech Stack:** Python, PySide6, SQLite settings repository, python-mpv, pytest/pytest-qt.

---

### Task 1: Persist Render Profile

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] Add `mpv_render_profile: str = "auto"` to `AppConfig`.
- [ ] Add `_VALID_MPV_RENDER_PROFILES` and `_normalize_mpv_render_profile()`.
- [ ] Add `mpv_render_profile` to app_config creation, migration, insert, load, and save paths.
- [ ] Add tests for round-trip, invalid normalization, and legacy `mpv_hwdec_mode="no"` mapping to `software`.
- [ ] Run `uv run pytest tests/test_storage.py -q`.

### Task 2: Update Advanced Settings UI

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py` or existing dialog-focused tests if present

- [ ] Rename the playback form label from `解码模式` to `渲染模式`.
- [ ] Replace the combo data with `auto`, `compat`, `balanced`, `vulkan`, `quality`, `performance`, `software`.
- [ ] Save the selected value into `config.mpv_render_profile`.
- [ ] Update the help text to mention Vulkan/new drivers and compatibility fallback.
- [ ] Add a test that opening the dialog with `mpv_render_profile="vulkan"` selects Vulkan and saving `quality` persists `quality`.
- [ ] Run the focused UI test.

### Task 3: Resolve MPV Render Profiles

**Files:**
- Modify: `src/atv_player/player/mpv_widget.py`
- Test: `tests/test_mpv_widget.py`

- [ ] Add a small render-profile resolver that returns option dictionaries for explicit profiles.
- [ ] Add best-effort vendor detection using `ATV_GPU_VENDOR`, then platform hints where available.
- [ ] Apply render profile options in `_base_player_options()` after base values and before NVIDIA mismatch fallback.
- [ ] Keep Windows `auto-copy` special-casing only for legacy paths if needed.
- [ ] Add tests for `compat`, `vulkan`, `quality`, `performance`, `software`, and auto Windows Intel/NVIDIA/Linux NVIDIA cases.
- [ ] Run `uv run pytest tests/test_mpv_widget.py -q`.

### Task 4: Add MPV Creation Fallback

**Files:**
- Modify: `src/atv_player/player/mpv_widget.py`
- Test: `tests/test_mpv_widget.py`

- [ ] When MPV construction fails with a Vulkan-capable profile, retry with `balanced`, then `compat`.
- [ ] Log each failed attempt with profile key and exception.
- [ ] Keep non-Vulkan profiles on the current single-attempt behavior unless they are `auto` resolving to Vulkan.
- [ ] Add a test where fake MPV raises for `gpu-api=vulkan`, then succeeds without it.
- [ ] Add a test where all attempts fail and the original error path still raises.
- [ ] Run `uv run pytest tests/test_mpv_widget.py -q`.

### Task 5: Regression Verification

**Files:**
- No production files expected.

- [ ] Run `uv run pytest tests/test_storage.py tests/test_mpv_widget.py tests/test_main_window_ui.py -q`.
- [ ] Run `git diff --check`.
- [ ] Review `git diff` to ensure no unrelated changes were made.
