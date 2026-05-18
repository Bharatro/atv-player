# Combobox Visual Softening Design

## Summary

Reduce the visual dominance of `QComboBox` across the app, with special handling for the player control bar.

The concrete user-facing problems are:

- global dropdowns look like they have a visible top border
- the player control bar dropdowns attract too much attention
- disabled player dropdowns feel like active controls instead of passive labels

This design removes the default "outlined input" look from comboboxes and replaces it with a fill-based shape system. The player window then builds on the same structure with a darker, lower-contrast variant that blends into the playback controls.

## Goals

- Make global comboboxes stop reading as if they have a visible top border in the default state.
- Keep hover and focus feedback clear without restoring a heavy outline in the resting state.
- Make player control bar dropdowns visually subordinate to playback buttons and the timeline.
- Make disabled player dropdowns read more like labels with state, not clickable controls.
- Keep the change narrowly scoped to combobox styling and related tests.

## Non-Goals

- Do not redesign player control layout, spacing, or ordering.
- Do not change combobox text, placeholder text, or enabled/disabled logic.
- Do not restyle unrelated controls such as `QLineEdit`, `QSpinBox`, or playback buttons in this task.
- Do not add theme modes or change the current theme token architecture.

## Scope

Primary implementation:

- `src/atv_player/ui/theme.py`
- `src/atv_player/ui/player_window.py`

Primary verification:

- `tests/test_theme.py`
- `tests/test_player_window_ui.py`

## Current Problem

The current combobox styling still carries a strong input-field silhouette:

- global comboboxes rely on border treatment as part of their resting-state shape
- in practice, this makes the top edge stand out more than intended
- player controls reuse the same combobox structure, which is too bright and too blocky against the dark playback bar
- when player comboboxes are disabled, they still occupy too much visual weight for what is effectively placeholder state

In `PlayerWindow`, the issue is amplified because the playback bar is intentionally immersive and dark, while the dropdown fields remain visually closer to application form controls than transport controls.

## Approach Options

### Option A: Remove only the top border

Keep the existing outlined combobox and try to suppress just the top edge.

Pros:

- small-looking CSS change

Cons:

- fragile in Qt because single-edge border treatment and rounded corners often look uneven
- keeps the broader "outlined field" visual language that is causing the problem
- does not solve player control focus competition cleanly

### Option B: Convert comboboxes to fill-based controls

Use background fill and contrast, not a resting-state outline, to define the field shape. Reserve stronger edge treatment for hover and focus only.

Pros:

- solves the perceived top-border issue at the root
- gives a cleaner default state for both app forms and player controls
- maps well to the existing tokenized theme system

Cons:

- requires clearer separation of resting, hover, focus, and disabled states

### Option C: Fix only the player comboboxes

Leave global comboboxes alone and only darken the player controls.

Pros:

- smallest implementation scope

Cons:

- does not satisfy the explicit requirement that global dropdowns also lose the visible top-edge treatment
- leaves the app with two conflicting combobox visual languages for the same base control

## Decision

Adopt **Option B**.

The problem is not a literal one-pixel top border. It is the default-state reliance on outline-heavy field styling. A fill-based combobox shape removes that visual artifact globally, and the player can then apply a darker version of the same model without inventing a separate component concept.

## Design

### 1. Global Combobox State Model

Update `build_combobox_qss(...)` in `src/atv_player/ui/theme.py` so the default combobox state no longer depends on a visible border to define the control.

Required behavior:

- default state uses a filled surface with no visually strong border
- hover state introduces only a subtle edge or contrast lift
- focus state restores a clear, accessible emphasized boundary using the existing accent token path
- disabled state lowers contrast and keeps the field readable without looking interactive

The important constraint is that the default state must not read as "top edge plus outline." The field should feel shaped by surface fill and radius first, not by border contrast.

### 2. Arrow Area Treatment

The dropdown arrow area should remain visually integrated with the main field.

Required behavior:

- default state avoids a hard separator between field body and dropdown affordance
- hover and focus may lightly clarify the control edge, but should not reintroduce a strong vertical divider in the resting state
- arrow color should stay secondary in the default state and remain readable in disabled state

This keeps the control recognizably interactive without splitting it into two competing blocks.

### 3. Player Combobox Variant

`PlayerWindow` should continue to apply a dedicated combobox stylesheet for playback controls, but that stylesheet should become a darker, lower-contrast variant of the same fill-based structure.

Required behavior for player comboboxes:

- resting state blends into the dark control bar
- hover state gently lifts contrast without pulling focus from the transport controls
- focus state remains clear and keyboard-accessible
- enabled state still reads as interactive, but secondary to play/pause, seek, and timeline

This change affects the existing themed player combobox set:

- playlist group
- playlist source
- speed
- subtitle
- danmaku
- quality
- audio
- parse

### 4. Disabled Player Comboboxes As Labels

Disabled comboboxes in the player should visually communicate "current category / unavailable state" rather than "inactive button."

Required behavior:

- background moves closer to the playback bar surface
- text and arrow move toward secondary contrast
- block silhouette is reduced enough that the control reads closer to a label chip than a button

This is especially important for placeholder states like `字幕`, `清晰度`, `音轨`, and `解析` when no alternative selection is currently available.

### 5. API Shape

`build_combobox_qss(...)` should remain the central combobox style generator.

The implementation may evolve the helper signature so callers can express:

- whether the control is borderless or fill-based
- the field surface color
- the dropdown subcontrol surface color
- disabled surface and text treatment
- hover and focus edge treatment

The exact parameter names are an implementation detail, but the direction is to make player-specific combobox styling explicit instead of implicitly inheriting application form colors.

### 6. Boundaries

This design intentionally does not change:

- combobox sizing rules in `_configure_control_combo(...)`
- layout structure in the player bottom bar
- `QSpinBox` appearance for `片头` / `片尾`
- combobox population logic, enabled logic, or selection behavior

## Testing Strategy

### Theme Tests

Update `tests/test_theme.py` to verify:

- default combobox QSS no longer emits the old resting-state visible border treatment
- hover, focus, and disabled selectors still exist
- dropdown subcontrol rules still exist
- player-oriented or borderless/fill-based variants still emit the expected structure

The tests should verify behavior through generated QSS structure, not screenshot comparison.

### Player UI Tests

Update `tests/test_player_window_ui.py` only as needed to verify:

- player comboboxes still receive a dedicated themed stylesheet path
- the player does not fall back to the generic application combobox appearance

This task does not need a broad UI snapshot suite. Focused assertions around stylesheet application are sufficient.

## Risks And Mitigations

- Risk: removing too much default edge treatment makes comboboxes feel less clickable.
  - Mitigation: keep hover and focus states explicit, and keep arrow affordance readable.

- Risk: player and global comboboxes diverge into two unrelated style systems.
  - Mitigation: keep one central QSS builder and treat the player as a parameterized variant.

- Risk: disabled player comboboxes become too faint to interpret.
  - Mitigation: reduce block weight more than text legibility; preserve placeholder readability.

## Implementation Order

1. Refine the global combobox QSS generator to use fill-first default styling.
2. Update or add theme tests for the new default, hover, focus, and disabled structure.
3. Apply a darker player-specific variant through `PlayerWindow`.
4. Add or update focused player UI tests for the dedicated player combobox styling path.
