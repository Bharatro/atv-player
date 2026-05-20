# Player Context Menu Exit Playback Design

## Summary

Add a top-level `退出播放` action to the player window's video right-click menu.

The action returns from the playback window to the main window by reusing the existing `PlayerWindow._return_to_main()` flow. It does not quit the application.

## Goals

- Add a mouse-accessible `退出播放` action to the existing video context menu.
- Make the action behave exactly like the existing return-to-main path.
- Keep the change scoped to `PlayerWindow` and its UI tests.

## Non-Goals

- Add a new "quit application" action to the context menu.
- Introduce a separate playback-exit state machine or wrapper method.
- Change keyboard shortcuts or title-bar behavior.
- Refactor existing return-to-main or quit-application flows.

## Scope

Primary implementation lives in `src/atv_player/ui/player_window.py`.

Primary verification lives in `tests/test_player_window_ui.py`.

No controller, storage, mpv wrapper, or main-window changes are required.

## Design

### Menu Placement

Extend the existing video-surface right-click menu with one additional top-level action at the end of the current action list:

- `主字幕`
- `次字幕`
- `主字幕位置`
- `次字幕位置`
- `主字幕大小`
- `次字幕大小`
- `音轨`
- `弹幕配置`
- `刮削`
- `弹幕源`
- `弹幕设置`
- `视频信息`
- `退出播放`

`退出播放` is a plain action, not a submenu and not a checkable item.

Putting it at the end keeps the existing grouping intact and makes the escape action easy to find without changing submenu ordering.

### Action Behavior

Selecting `退出播放` calls `PlayerWindow._return_to_main()`.

That means the menu action inherits the existing behavior:

- close transient player dialogs and the current context menu
- pause the video backend
- report current progress
- stop current playback through the controller queue
- persist player geometry and paused state
- hide the player window
- emit `closed_to_main`

The action must not call `QApplication.quit()` and must not reuse `_quit_application()`.

### Error Handling

No new error handling path is needed.

The action should rely on the existing `_return_to_main()` behavior and its current exception handling around video pause and shutdown-adjacent cleanup.

### Compatibility

Existing context-menu items and ordering remain unchanged except for the appended `退出播放` action.

Existing return-to-main entry points remain unchanged:

- title-bar return button
- `Esc` when not fullscreen and no dialog is open
- dedicated return shortcut

The new menu action is only an additional control surface for the same behavior.

## Testing Strategy

Add focused tests in `tests/test_player_window_ui.py` for:

- context-menu structure including the new top-level `退出播放` action
- triggering `退出播放` from the built menu and verifying it returns to the main window instead of quitting the app
- verifying the existing return-to-main side effects still happen when invoked through the menu path

## Implementation Order

1. Add a failing player-window test for the context-menu action list including `退出播放`.
2. Run the focused test to verify the expected failure.
3. Add a failing player-window test that triggers the menu action and observes return-to-main behavior.
4. Run the focused test to verify the expected failure.
5. Implement the minimal `PlayerWindow` menu wiring by appending `退出播放` and binding it to `_return_to_main()`.
6. Re-run the focused tests and keep the rest of the existing player-window menu behavior green.
