# X11 Player Pseudo-Maximize Topmost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make playback topmost reliable with a maximized appearance on Cinnamon/X11 by keeping the player in normal WM state and filling the available work area.

**Architecture:** `PlayerWindow` owns X11-only pseudo-maximized state, geometry conversion, persistence, and fullscreen integration. Shared title-bar code asks the window for effective maximized state and routes drag maximize/restore through overridable window methods, while other windows retain native Qt behavior.

**Tech Stack:** Python 3, PySide6/Qt, pytest-qt, X11 EWMH.

---

### Task 1: Player pseudo-maximized state

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [x] Add failing tests proving that X11 maximize uses `availableGeometry()`, stays out of `WindowMaximized`, restores the captured geometry, and leaves non-X11 behavior native.
- [x] Run the focused tests and confirm they fail because `PlayerWindow` still inherits the native maximize toggle.
- [x] Add `_pseudo_maximized`, saved normal geometry/state, X11 platform detection, enter/leave helpers, and a `PlayerWindow._toggle_maximized()` override.
- [x] Make chrome styling and resize eligibility use effective maximized state.
- [x] Run the focused tests and confirm they pass.

### Task 2: Convert legacy true-maximized windows before ABOVE

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/player_window.py`

- [x] Replace obsolete remap expectations with a failing test proving a visible true-maximized X11 player is normalized to its `normalGeometry()`, expanded to the work area, then receives native topmost.
- [x] Run the test and confirm the old hide/`showMaximized()` remap is observed.
- [x] Replace `_remap_maximized_xcb_window_for_always_on_top()` with true-to-pseudo conversion and rollback on an initial native topmost failure.
- [x] Retain show/state-change ABOVE reapplication for lifecycle changes without geometry remapping.
- [x] Run all topmost and pseudo-maximize focused tests.

### Task 3: Title-bar drag, fullscreen, and persistence

**Files:**
- Modify: `tests/test_window_chrome.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `src/atv_player/ui/window_chrome.py`
- Modify: `src/atv_player/ui/player_window.py`

- [x] Add failing tests for title-bar routed maximize/restore, fullscreen round-trip, and prefixed pseudo-maximized geometry persistence.
- [x] Run the tests and confirm the missing routing/persistence behavior fails.
- [x] Add effective-maximized title-bar hooks and route top-edge drag through the maximize request.
- [x] Add versioned geometry encoding/decoding and restore pseudo-maximize on first show.
- [x] Preserve pseudo-maximized state across fullscreen and ensure pause/resume changes only native topmost.
- [x] Run the focused test set.

### Task 4: Regression verification

**Files:**
- Verify: `src/atv_player/ui/player_window.py`
- Verify: `src/atv_player/ui/window_chrome.py`
- Verify: `tests/test_player_window_ui.py`
- Verify: `tests/test_window_chrome.py`

- [x] Run `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "always_on_top or topmost or pseudo_maximize or fullscreen_restores_maximized" -q`.
- [x] Run `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_window_chrome.py -q`.
- [x] Run Python compilation for both modified source files.
- [x] Inspect `git diff --check` and the final diff for unrelated changes.
