# Player Title Bar Return And Quit Design

## Summary

The player title bar should expose two distinct actions:

- `返回主窗口`: leave the player UI and show the main window while keeping the application running
- `关闭`: quit the entire application immediately

This change should make the player's top-level window actions explicit instead of overloading the close button with "return to main" behavior.

## Goals

- Add a dedicated title-bar button for returning from the player to the main window.
- Make the title-bar close button in `PlayerWindow` quit the application.
- Reuse the existing player return flow so playback teardown, progress reporting, and restore state stay consistent.
- Keep other custom-window users unchanged unless they explicitly opt into extra title-bar actions.

## Non-Goals

- Redesigning the bottom playback controls.
- Changing the main window title bar behavior.
- Introducing confirmation dialogs for quit or return.
- Renaming existing keyboard shortcuts.
- Refactoring the whole custom window chrome system beyond the extension point needed for this button.

## User Experience

### Return To Main

When the player is open in windowed mode, the title bar shows a dedicated `返回主窗口` button in the right-side action group. Clicking it should behave the same as `Ctrl+P` and non-fullscreen `Esc`:

- pause and persist the current playback restore state
- report progress and stop current playback in the existing way
- hide the player window
- restore and focus the main window

The application remains running.

### Quit Application

When the player title-bar close button is clicked, the application should quit immediately using the same path as `Ctrl+Q`. This is a full app exit, not a player-to-main transition.

### Fullscreen Behavior

The player already hides the custom title bar in fullscreen. That behavior should remain unchanged. The new return button is only visible when the title bar itself is visible.

## Architecture

### Window Chrome Extension Point

`CustomTitleBar` currently hardcodes minimize, maximize, and close buttons. It should be extended with a small optional action slot that allows a window to insert one or more custom buttons before the standard window controls.

The extension should:

- keep the existing layout and styling model
- preserve current behavior for windows that do not use extra actions
- avoid requiring every window subclass to know title-bar layout internals

### Player Ownership

`PlayerWindow` should opt into this extension and register one custom button:

- object identity owned by `PlayerWindow`
- tooltip `返回主窗口 (Ctrl+P)`
- click handler wired to existing `_return_to_main()`

No other window should receive this button by default.

### Close Behavior Routing

The current player close behavior was recently changed so `closeEvent()` returns to the main window when there is an active session and quit is not requested. That behavior should be narrowed:

- explicit `返回主窗口` button, `Ctrl+P`, and non-fullscreen `Esc` should continue to call `_return_to_main()`
- explicit application quit paths should set the quit flag and then close the app
- title-bar close button in `PlayerWindow` should trigger the quit path instead of the return path

This keeps "return" and "quit" as separate user actions while still preserving the existing safe teardown logic behind each path.

## Layout And Visual Rules

- Place the new button in the player title bar's right-side control cluster.
- Recommended order: `返回主窗口 / 最小化 / 最大化 / 关闭`.
- Match existing title-bar button sizing and hover styling so the new control feels native to the custom chrome.
- Use concise button text rather than an icon-only affordance, because this action is semantic and should be immediately discoverable.

## Error Handling

- If the player has no active session, clicking `返回主窗口` should still be safe and should simply hide the player and signal the main window as the existing flow allows.
- If quit is requested, the return path must not override the quit state.
- No new modal prompts should be introduced.

## Testing

Add focused tests for:

- `CustomTitleBar` supporting optional extra action buttons without hiding or reordering standard window controls incorrectly
- `PlayerWindow` exposing a visible title-bar return button with tooltip `返回主窗口 (Ctrl+P)`
- clicking the new return button calling the same return-to-main flow as `Ctrl+P`
- clicking the player title-bar close button quitting the application instead of returning to the main window
- fullscreen continuing to hide the whole title bar, including the new button

Existing tests that assume the player title-bar close button returns to the main window should be updated to reflect the new quit behavior.

## Risks And Mitigations

- Risk: extending `CustomTitleBar` could accidentally change non-player windows.
  Mitigation: make extra actions opt-in and preserve the default layout when unused.

- Risk: return and quit paths may both partially run if signal wiring is unclear.
  Mitigation: wire the new return button directly to `_return_to_main()` and wire the player close button to the existing `_quit_application()` path.

- Risk: tests may keep asserting the old close-button semantics.
  Mitigation: update player-window tests so close-button expectations are explicit and separated from return-button expectations.
