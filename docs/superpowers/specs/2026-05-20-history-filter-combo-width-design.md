# History Filter Combo Width Design

## Summary

Fix the two filter comboboxes at the top of the playback-history page so their selected text remains fully readable instead of being compressed and truncated.

## Goals

- Keep the playback-history filter row visually unchanged except for improved combobox readability.
- Ensure the source filter and time filter can display their common labels without clipping in the default window size.
- Reuse the same combobox sizing strategy already used in other readable, compact controls.

## Non-Goals

- Do not redesign the playback-history page layout.
- Do not change filter behavior, labels, or available options.
- Do not restyle unrelated comboboxes elsewhere in the app.

## Scope

- `src/atv_player/ui/history_page.py`
- `tests/test_browse_page_ui.py`

## Decision

Use content-length-aware combobox sizing for the two history-page filter comboboxes.

Compared with fixed pixel widths, this is less brittle across fonts, DPI scaling, and future label changes. Compared with a larger layout redesign, it is the smallest change that directly addresses the bug.

## Design

### 1. Source Filter

Apply `AdjustToMinimumContentsLengthWithIcon` to `source_combo` and give it a minimum content length large enough for the current longest source labels.

### 2. Time Filter

Apply the same size-adjust policy to `time_combo` and give it a minimum content length that keeps labels like `最近30天` fully visible.

### 3. Layout Boundary

Keep the existing horizontal filter row. The fix should rely on the comboboxes reserving enough inline space for their own text rather than changing row structure.

## Testing

Add a focused UI test that asserts:

- both comboboxes use `AdjustToMinimumContentsLengthWithIcon`
- `source_combo` has a stable minimum content length for readable source labels
- `time_combo` has a stable minimum content length for readable time labels
