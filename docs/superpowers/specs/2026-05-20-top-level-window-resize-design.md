# Top-Level Window Resize Design

## Summary

Restore frameless edge-resize behavior for the three top-level app windows:

- `MainWindow`
- `PlayerWindow`
- `LoginWindow`

Dialogs already resize correctly. The regression is specific to top-level windows whose content reaches the outer edge and intercepts mouse events before the resize logic can see them.

## Goals

- Make `MainWindow`, `PlayerWindow`, and `LoginWindow` resizable by dragging their outer edges and corners.
- Preserve the existing frameless custom title bar and current visual layout.
- Keep the fix centered in the shared chrome layer so all current and future top-level windows benefit.
- Add regression tests that reproduce the current failure path instead of only asserting constructor flags.

## Non-Goals

- Redesign the window chrome or switch back to native system title bars.
- Add artificial padding around top-level window content just to expose a resize hit area.
- Refactor unrelated window layout code.

## Root Cause

`_ThemedChromeMixin` currently installs its resize event filter on the window root, title bar, and content root container.

That is enough for dialogs because `ThemedDialogBase` leaves inner padding around its content, so mouse events near the outer edge still hit a watched widget.

It is not enough for `MainWindow`, `PlayerWindow`, and `LoginWindow`, because their child widgets visually extend to the edge. In real use, the mouse press lands on an unwatched descendant widget, so `_handle_resize_mouse_press()` is never called and the resize interaction never starts.

## Scope

Primary implementation:

- `src/atv_player/ui/window_chrome.py`

Primary verification:

- `tests/test_window_chrome.py`

Potential focused regression assertions for affected top-level windows:

- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_login_window_ui.py`

## Design

### Shared Chrome Fix

Keep resize behavior in `_ThemedChromeMixin`, but make event-filter coverage match the full content tree instead of only a few container widgets.

The chrome layer should:

- install the resize event filter on all existing descendants beneath the chrome root
- continue installing the filter for widgets added later
- avoid changing behavior for non-resizable windows

This keeps the resize hit-testing and geometry updates in one place and avoids window-specific workarounds.

### No Layout Padding Workaround

Do not add fake margins to top-level windows.

Padding would only expose the current incomplete event coverage instead of fixing it. It would also visibly alter the player and main-window layouts for a behavioral bug that belongs in the shared chrome implementation.

### Testing Strategy

Add a failing regression test in `tests/test_window_chrome.py` that simulates dragging a resize edge through a child widget that reaches the window boundary and verifies the window width changes.

Keep existing constructor-level assertions, but treat the child-widget drag test as the real proof because it matches the user-visible failure.

If needed, add one focused smoke test per top-level window to confirm each still reports resize support after the shared fix.

## Error Handling

No new user-facing error handling is required.

If the window is maximized or fullscreen, the existing resize guard remains authoritative and resize interaction must stay disabled.

## Implementation Order

1. Add a failing regression test covering resize drag events delivered through a child widget at the window edge.
2. Run the focused chrome test and confirm the failure reproduces.
3. Update `_ThemedChromeMixin` so resize event filtering covers descendant widgets, including widgets added after initialization.
4. Re-run the focused chrome tests, then the affected window UI tests.
5. Stop after the shared fix unless a top-level window still has an independent resize constraint.
