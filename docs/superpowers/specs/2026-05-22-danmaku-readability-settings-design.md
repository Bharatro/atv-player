# Danmaku Readability Settings Design

## Summary

Improve danmaku readability by adding two focused rendering controls: `opacity` and `outline strength`.

This change is intentionally narrow. It extends the existing danmaku settings and ASS rendering pipeline so users can make danmaku less visually intrusive while still keeping text readable across bright and dark scenes. The first version does not add decorative customization such as random colors or font-family selection.

## Goals

- Add a danmaku opacity setting that reduces how much danmaku blocks the video.
- Add a danmaku outline-strength setting that improves legibility without requiring larger text.
- Reuse the current danmaku ASS rendering path, settings dialog, config persistence, and render-cache partitioning.
- Keep the feature compatible with both uniform-color and source-color modes.

## Non-Goals

- Add random per-line danmaku colors.
- Add font-family selection or custom font file loading.
- Change danmaku provider parsing, XML cache contents, or search/source-selection behavior.
- Redesign the danmaku settings dialog beyond the minimum controls required for these two options.

## Scope

Primary implementation should live in:

- `src/atv_player/danmaku/subtitle.py`
- `src/atv_player/danmaku/cache.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/storage.py`
- `src/atv_player/models.py`

Primary verification should live in:

- `tests/test_danmaku_subtitle.py`
- `tests/test_player_window_ui.py`
- `tests/test_storage.py`

## Current State

The player already exposes danmaku settings for line count, render mode, position preset, color mode, uniform color, font size, and scroll speed.

The renderer generates ASS output with a single hard-coded style line:

- outline is fixed at `1`
- shadow is fixed at `0`
- text alpha is always fully opaque
- outline alpha is fixed by the style definition

That means users can currently change size and color, but cannot tune the two controls most directly tied to readability against the underlying video.

## Design

Add two new persisted preferences:

- `preferred_danmaku_opacity`: integer percentage in the range `30` to `100`, default `85`
- `preferred_danmaku_outline_strength`: enum with values `soft` and `strong`, default `strong`

Rationale:

- opacity is best expressed as a percentage because it is easy to understand and maps cleanly to ASS alpha conversion
- outline strength should start as a small preset enum instead of a free-form numeric slider to keep the UI compact and avoid exposing ASS-specific terminology

## Rendering Behavior

### Opacity

Opacity applies to the visible danmaku text regardless of whether the final text color comes from uniform color or source color.

- `100` means fully opaque text
- lower values increase transparency
- opacity affects the intro danmaku event and all rendered danmaku events consistently

Implementation detail:

- convert the configured percentage into ASS alpha
- apply that alpha to the style primary/secondary colors and any inline `\1c` overrides that represent danmaku text color
- keep the conversion centralized inside `src/atv_player/danmaku/subtitle.py`

### Outline Strength

Outline strength adjusts the readability treatment around the text:

- `soft`: keep the current overall feel, equivalent to the existing thin outline
- `strong`: increase outline width and add a small shadow so text remains readable when opacity is reduced

Implementation detail:

- keep outline and shadow controlled from the ASS style header, not per-event
- do not introduce outline color selection in this change; continue using black outline/back colors

## UI Behavior

Extend the existing danmaku settings dialog with:

- an `opacity` control, shown as a percentage spin box or slider-backed spin box
- an `outline strength` combo box with `柔和` and `清晰` options

UI rules:

- both controls live alongside the current color and font-size settings
- changing either control immediately updates persisted config and triggers danmaku reload using the existing settings-refresh behavior
- restore-defaults resets opacity to `85` and outline strength to `strong`

## Persistence and Cache

Both settings must be added to app config storage and normalized on load/save.

Rendered ASS cache keys must include:

- opacity
- outline strength

This preserves the existing contract that ASS cache entries are partitioned by render-affecting settings.

The new settings must not affect:

- danmaku XML cache keys
- provider payload caching
- danmaku search cache

## Rejected Alternatives

### Random color mode

Rejected because it conflicts with the stated goal of readability-first tuning. Random colors increase visual noise and make opacity/outline tuning less predictable.

### Font-family selection

Rejected for the first version because the user benefit is lower than opacity/outline, while implementation and support costs are higher due to cross-platform font availability and fallback differences.

### Numeric outline-width slider

Rejected for the first version because it exposes a low-level ASS detail and expands the settings surface faster than the user value justifies.

## Testing

Add targeted tests that verify:

- ASS output changes when opacity changes and the generated style or inline color data carries the expected alpha
- `soft` and `strong` outline presets generate different outline/shadow style values
- rendered cache keys differ when opacity or outline strength differs
- storage normalizes invalid opacity and outline-strength values back to defaults
- the player settings dialog reads, writes, and resets the new controls correctly

Existing danmaku rendering behavior should continue to pass for:

- uniform-color mode
- source-color mode
- static rendering
- scrolling or mixed rendering
