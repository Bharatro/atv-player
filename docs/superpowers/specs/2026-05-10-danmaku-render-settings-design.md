# Danmaku Render Settings Design

## Summary

Extend player danmaku rendering so users can change danmaku style at runtime through a dedicated `弹幕设置` dialog. The first version should support configurable render mode, color mode, uniform color, and position preset, and it should apply changes immediately to the currently active danmaku track without restarting playback.

The implementation is intentionally scoped to the existing player danmaku flow, current `AppConfig` persistence, and the ASS subtitle generation path. Default behavior must remain visually compatible with the current static top-aligned white danmaku rendering.

## Goals

- Add a dedicated player-side `弹幕设置` dialog separate from `弹幕源`.
- Persist danmaku style settings as global defaults in `AppConfig`.
- Keep existing danmaku enablement and line-count behavior unchanged.
- Support configurable danmaku render modes: `static`, `scroll_only`, and `mixed`.
- Support configurable danmaku color modes: `uniform` and `source`.
- Support configurable danmaku position presets: `top`, `upper`, `mid_upper`, and `bottom`.
- Apply danmaku setting changes immediately when the current item already has an active danmaku track.
- Preserve current behavior for users who never open the new dialog.

## Non-Goals

- Merge danmaku style settings into the existing `弹幕源` dialog.
- Add per-video or per-series danmaku style overrides in this change.
- Auto-enable danmaku when the user changes danmaku settings.
- Redesign the existing danmaku source search, source switching, or line-count combo behavior.
- Add advanced style controls such as font family, stroke width, opacity, or scroll speed.
- Replace ASS-based danmaku rendering with a different subtitle format.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/danmaku/cache.py`
- `src/atv_player/danmaku/subtitle.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_danmaku_subtitle.py`
- `tests/test_player_window_ui.py`
- `tests/test_build.py` only if config persistence changes affect existing config assumptions

The danmaku providers and danmaku XML format are already sufficient because source records already preserve `pos` and `color`.

## Configuration Model

The existing global danmaku fields should remain unchanged:

- `preferred_danmaku_enabled`
- `preferred_danmaku_line_count`

Add the following global danmaku rendering fields to `AppConfig`:

- `preferred_danmaku_render_mode`
- `preferred_danmaku_color_mode`
- `preferred_danmaku_uniform_color`
- `preferred_danmaku_position_preset`

Recommended persisted values:

- `preferred_danmaku_render_mode = "static"`
- `preferred_danmaku_color_mode = "uniform"`
- `preferred_danmaku_uniform_color = "#FFFFFF"`
- `preferred_danmaku_position_preset = "top"`

These defaults must preserve current behavior for upgraded users:

- danmaku remains enabled or disabled based on the existing danmaku preference
- line-count selection still drives how many simultaneous danmaku tracks may be shown
- default ASS output still appears as static white danmaku near the top of the screen

Storage requirements:

- extend the `app_config` schema with non-null text columns for the four new settings
- backfill missing columns during startup migration
- normalize invalid or blank persisted values to safe defaults during load

## Player Entry Points

Danmaku style settings should use a dedicated `弹幕设置` dialog and should not be mixed into `弹幕源`.

The player should expose the new entry point in two places:

- the video context menu, next to the existing danmaku-related actions
- the bottom player controls, adjacent to the existing danmaku controls

The existing `弹幕源` entry point and dialog should remain unchanged.

## Dialog Behavior

The new dialog should be modeless relative to the current playback session in the same way the current player dialogs are used. It should focus on immediate configuration rather than deferred form submission.

The dialog should contain:

- a `显示模式` section
- a `颜色` section
- a lightweight action row with `恢复默认` and `关闭`

The `显示模式` section should expose:

- render mode: `静态`, `仅滚动`, `混合`
- position preset: `顶部`, `顶部偏下`, `中上`, `底部`

The `颜色` section should expose:

- color mode: `统一颜色`, `保留原色`
- a uniform color picker or equivalent explicit color input for the `统一颜色` mode

Interaction rules:

- there is no `确定` or `应用` button
- every setting change saves immediately
- every setting change tries to refresh the current danmaku track immediately when one is active
- `统一颜色` controls stay visible but disabled while `保留原色` is selected
- `恢复默认` restores all four new style fields to their compatibility defaults and immediately refreshes active danmaku
- if the current item has no active danmaku, the dialog should still save global defaults and may show a light hint that changes will apply when danmaku is enabled

## Render Semantics

Danmaku rendering should continue to target ASS output, but the generation model must expand from merged static cues to per-record event rendering so that movement and per-event color can be represented correctly.

The rendering pipeline should consume:

- danmaku XML text
- line count
- render mode
- color mode
- uniform color
- position preset

### Position Semantics

The source-side `DanmakuRecord.pos` values should continue to carry danmaku intent.

The first version should treat positions as:

- `1` as scrolling danmaku
- `5` as top-fixed danmaku
- `4` as bottom-fixed danmaku
- any other or unknown value as scrolling danmaku

The user-selected position preset should define the vertical band used by the renderer:

- `top` keeps danmaku close to the top edge
- `upper` shifts the danmaku band slightly downward
- `mid_upper` uses the upper-middle region
- `bottom` moves the danmaku band near the bottom edge

This preset applies to the whole danmaku layer:

- for scrolling danmaku it defines the scrolling lanes
- for top-fixed and bottom-fixed danmaku it defines the corresponding fixed layout band used for the current display mode

### Render Modes

`static` mode:

- preserve current behavior as closely as practical
- render all danmaku as fixed-lane text without horizontal movement
- continue to respect line count as the number of simultaneous visible lanes

`scroll_only` mode:

- treat every danmaku record as horizontally moving
- do not preserve source top or bottom intent in this mode
- use ASS movement tags such as `\move(...)`

`mixed` mode:

- render `pos=1` records as moving danmaku
- render `pos=5` records as top-fixed danmaku
- render `pos=4` records as bottom-fixed danmaku
- fall back unknown positions to moving danmaku

### Color Modes

`uniform` mode:

- render all danmaku with the configured global color

`source` mode:

- render each danmaku event using `DanmakuRecord.color`
- fall back to the configured default white color when a source color is missing or invalid

Per-record rendering is required so color mode does not conflict with merged multiline cues.

## Active Danmaku Refresh

Changing danmaku style settings must not replay the current media item.

When a danmaku setting changes:

1. validate and save the config field
2. detect whether the current item has both danmaku enabled and usable `danmaku_xml`
3. if no active danmaku can be refreshed, stop after saving config
4. if active danmaku exists, unload the owned danmaku subtitle track
5. invalidate any stale temporary path reference and regenerate ASS using the updated settings
6. load the new ASS subtitle track into the same danmaku slot path used today
7. preserve the current danmaku ownership bookkeeping so subtitle cleanup remains correct

The refresh must not:

- reopen the media URL
- change danmaku source selection
- alter normal subtitle selection
- auto-enable danmaku if it is currently off

## Cache Strategy

The current danmaku ASS cache key only includes XML text and line count, which is insufficient once style settings affect output.

The ASS cache key must be expanded to include:

- cache version
- normalized line count
- normalized render mode
- normalized color mode
- normalized uniform color
- normalized position preset
- source XML text

The cache version should be bumped so previously generated ASS files cannot be reused after the renderer changes.

Changing any danmaku style setting must produce a distinct cache path even when the source XML text is unchanged.

## Error Handling

Danmaku setting failures must not interrupt playback.

Failure rules:

- invalid saved values should normalize to compatibility defaults
- invalid source colors should fall back to white
- unknown source positions should fall back to scrolling semantics
- config save failures should leave the previous in-memory config intact and surface a concise message
- active danmaku refresh failures after a successful save should log a concise message and leave playback running
- danmaku refresh failures must not clear the current danmaku source selection
- danmaku refresh failures must not corrupt non-danmaku subtitle tracks

If regeneration or mpv subtitle loading fails, the player should leave danmaku in a safe off state for the current track rather than retrying blindly inside the dialog interaction path.

## Testing Strategy

Add focused subtitle renderer tests for:

- compatibility output in `static` mode with the default configuration
- per-record uniform color rendering
- per-record source color rendering
- moving event generation in `scroll_only` mode
- mixed handling for `pos=1`, `pos=4`, and `pos=5`
- safe fallback for invalid colors and unknown positions

Add cache tests for:

- different render settings generating different cache paths
- old defaults still producing stable cache keys

Add storage and config tests for:

- schema migration for the new danmaku fields
- default config values for upgraded or fresh databases
- load-time normalization of invalid persisted values

Add player window tests for:

- exposing the new `弹幕设置` entry point in the bottom controls
- exposing the new `弹幕设置` entry point in the context menu
- opening the new dialog without affecting the existing `弹幕源` dialog
- saving each style field immediately on change
- disabling the uniform color control in `保留原色` mode
- restoring defaults through `恢复默认`
- refreshing active danmaku immediately after a setting change
- saving settings without auto-enabling danmaku when danmaku is currently off
- preserving existing danmaku combo and danmaku source behavior

## Implementation Order

1. Add failing config and storage tests for the new danmaku style fields.
2. Add failing renderer and cache tests for configurable danmaku ASS output.
3. Extend the config model, storage schema, and danmaku cache key.
4. Refactor danmaku ASS generation to accept explicit render settings and support per-record rendering.
5. Add failing player window tests for the new dialog, entry points, and immediate refresh behavior.
6. Implement the `弹幕设置` dialog and wire it to config persistence.
7. Implement active danmaku regeneration and reload on settings change.
8. Run focused danmaku, storage, and player UI regression tests.
