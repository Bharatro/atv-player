# Player Log Toggle Design

## Summary

Add a dedicated playback-log toggle button to the top of the player window sidebar so users can show or hide the `播放日志` section independently from the rest of the detail area.

The existing `详情` toggle should keep controlling the entire detail panel. The new `播放日志` toggle should only control the log title and log text area inside that panel. When logs are hidden, the poster and `影片详情` content remain visible and the metadata view should expand to use the freed vertical space.

## Goals

- Let users hide `播放日志` without hiding the rest of the detail panel.
- Keep the interaction aligned with the existing top sidebar icon-button row.
- Preserve current default behavior for first-time users by showing logs initially.
- Persist the playback-log visibility choice across player window reopen and app restart.
- Keep fullscreen and wide-mode behavior consistent with existing sidebar visibility rules.

## Non-Goals

- Redesign the whole sidebar layout.
- Add a separate floating log dialog or detachable log window.
- Introduce a second splitter inside the detail panel in this change.
- Add keyboard shortcuts for the new log toggle in the first release.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_player_window_ui.py`

## Design

### Sidebar Actions

The top sidebar action row currently exposes `播放列表` and `详情`. Add a third icon button:

- `播放日志`

Button semantics:

- `播放列表` continues to control the playlist panel.
- `详情` continues to control the entire detail panel.
- `播放日志` controls only the log section inside the detail panel.

The new button should be checkable and default to checked when no saved preference exists.

### Detail Panel Structure

The detail panel should be split into two logical sections:

1. detail content section:
   - poster
   - detail actions
   - detail fields
   - `影片详情` label
   - `metadata_view`
2. playback log section:
   - `播放日志` label
   - `log_view`

Implementation should group the log label and `log_view` inside a dedicated container widget. Hiding that container must leave the rest of the detail panel intact.

When the log section is hidden:

- `metadata_view` remains visible
- detail actions and detail fields keep their current behavior
- the remaining layout stretches naturally without leaving a blank reserved area for the log panel

### Visibility Rules

Normal windowed mode:

- if `详情` is unchecked, the entire detail panel is hidden regardless of log state
- if `详情` is checked and `播放日志` is unchecked, the detail panel stays visible but the log section is hidden
- if both are checked, the full detail panel including logs is visible

Fullscreen mode:

- existing behavior remains unchanged
- sidebar action buttons are hidden
- playlist, detail panel, and log section are all effectively hidden

Wide mode:

- existing behavior remains unchanged
- the whole sidebar stays hidden
- the saved playback-log toggle state must not be reset by entering or leaving wide mode

### Persistence

Add a new `AppConfig` boolean field:

- `player_log_visible: bool = True`

Persistence rules:

- initialize the `播放日志` toggle button from `config.player_log_visible` when config is available
- if the user changes the log toggle, save the updated value immediately
- if no config is available, keep the in-memory default of `True`

The new preference is independent from `player_main_splitter_state` and `player_wide_mode`.

### UI Text and Iconography

The new button should use an icon button consistent with the existing sidebar controls. The tooltip text should be `播放日志`.

This change does not require a text label in the button body, and it should preserve the current compact icon-only control row style.

If no dedicated log icon exists yet, the implementation may reuse an existing suitable icon asset or add a new one, but the button meaning must be clear from the tooltip.

## Testing

Add or update UI tests to cover:

- the player window shows a dedicated playback-log toggle button in the sidebar action row
- toggling `播放日志` hides only the log section and keeps the detail panel visible
- toggling `详情` still hides the entire detail panel
- fullscreen still hides sidebar actions and detail content regardless of log toggle state
- `player_log_visible` persists across window recreation

## Risks

- If the log label is left outside the dedicated log container, hiding logs will leave an orphaned `播放日志` heading.
- If the new visibility flag is coupled incorrectly to the existing detail toggle, users may lose the ability to show details without logs.
- If persistence is only applied on shutdown, the toggle can desync after crashes or forced exits.
