# 我的追更详情页布局改版 Design

## Summary

Refine the `我的追更` detail page so the episode area always presents rich episode information and supports density changes through column count instead of content modes.

This change removes the existing `简洁 / 封面 / 完整` episode display modes and replaces them with a persistent `单列 / 双列 / 三列` layout switch. It also tightens the season rail, reduces cast-card size, increases the usable height of the episode section, and adds a season header inside the episode area that shows the selected season's poster and overview.

## Goals

- Remove the `简洁 / 封面 / 完整` display-mode tabs from the following detail episode area.
- Always render episode cards in the current rich/full presentation.
- Add a right-aligned icon-button group for `单列 / 双列 / 三列`.
- Default the episode layout to `单列`.
- Persist the selected episode column count and reuse it when the user opens the page again.
- Reduce the width of the left season list.
- Reduce the visual size of cast/crew cards so the cast section occupies less height.
- Increase the vertical space available to the episode section.
- Show season-specific poster and overview in the episode area, using the selected season as the source of truth.

## Non-Goals

- Do not redesign the top-of-page metadata/backdrop section beyond keeping it compatible with the new episode area.
- Do not add responsive auto-column logic; users switch only between the explicit `1 / 2 / 3` column choices.
- Do not add new dialogs, hover previews, or “expand more” controls for season metadata in this iteration.
- Do not add new metadata-fetch behavior or extra network requests when season fields are missing.
- Do not change the episode preview dialog behavior.

## User-Approved Decisions

- Season poster and season overview belong in the episode area, above the episode list, on the right side.
- The season info layout should follow the provided reference: small season poster on the left, season title and short metadata on the right, then season intro text beneath/alongside in the same horizontal header block.
- The default layout is `单列`.
- The selected column count should be persisted and restored.

## Current Problems

The current implementation in `src/atv_player/ui/following_episode_browser.py` is optimized for a single-column `QListView` delegate with three content modes:

- `compact`
- `poster`
- `full`

That model works for changing card density inside one vertical list, but it is the wrong abstraction for the requested UI:

- the user no longer wants content modes
- the new control is about column count, not card detail level
- season poster/overview need to live inside the episode section itself
- the current top `QTabBar` is no longer the right control surface

Trying to keep the old tab-based mode system and layer column switching on top would create an awkward hybrid that is harder to reason about and maintain.

## Recommended Approach

Keep the existing season grouping, watched-state logic, thumbnail loading, and episode activation flow, but replace the right-side rendering structure with a dedicated episode-grid presentation.

Concretely:

- `FollowingDetailPage` owns the outer layout changes.
- `FollowingEpisodeBrowser` stops exposing display-mode tabs and instead manages:
  - season selection
  - the selected season’s episodes
  - selected column count
  - episode activation
- The episode content area becomes:
  - left: narrow season rail
  - right top: season header
  - right body: full episode cards laid out in `1 / 2 / 3` columns

This preserves the stable data model and selection semantics while replacing the rendering model that no longer matches the product direction.

## Layout Design

### Overall Page Balance

The detail page keeps its three high-level sections:

- top metadata/backdrop section
- episode section
- cast/crew section

The episode section becomes visually more prominent:

- increase its minimum height relative to the current implementation
- allow the page to spend more vertical space on episodes before cast/crew
- reduce the cast section footprint so episodes remain the primary focus

### Episode Section

The episode section should be split into two columns:

- left: season list
- right: season header + episode grid

The left season list should be narrower than the current `1:4` horizontal split. It is a selector, not a content surface. It should contain only season titles and counts, without season posters or season descriptions.

The right side should contain:

1. A season header row at the top
2. A column-switch control aligned to the top-right
3. A full episode grid below

### Season Header

The season header is bound to the currently selected season and should visually match the approved reference:

- left: a small season poster
- right top: season title
- right secondary line: short season metadata such as rating/year/episode count when available
- right body: season premiere/status sentence and season overview text when available

The header should stay compact enough not to crowd out the episode list, but large enough to make season context obvious when users switch seasons.

### Episode Cards

Episode cards always use the rich/full presentation:

- still image on the left in single-column mode
- title
- rating/score badge when available
- air date
- runtime when available
- watched marker
- special marker
- overview text

Changing between `单列 / 双列 / 三列` must only change layout density. It must not remove fields from the episode card.

Density behavior:

- `单列`: keep the approved reference layout, with still image on the left and full text stack on the right
- `双列`: keep the same fields, but compress spacing and clamp overview to fewer lines
- `三列`: keep the same fields, but use the tightest spacing and shortest overview clamp

The key rule is that `双列 / 三列` remain the same information design, not fallback variants of the old compact mode.

### Cast/Crew Section

The cast section remains a horizontal scrolling rail, but cards should be reduced one size tier:

- smaller avatar box
- smaller overall card height
- tighter internal padding
- enough room for avatar, name, and role/job only

The goal is to keep cast useful without competing with the episode section for height.

## Interaction Design

### Column Switcher

Replace the current `QTabBar` display-mode control with a compact icon-button group at the top-right of the episode area:

- single-column icon
- two-column icon
- three-column icon

Behavior:

- only one option can be active at a time
- active state is visually highlighted
- clicking an option immediately relayouts the episode cards
- the chosen value is saved to config

### Season Selection

Season selection behavior should remain the same at the data level:

- selecting a season updates the visible episode set
- if that season’s episode details are not loaded yet, the existing season-load path is reused
- the season header updates together with the selected season

### Episode Activation

Episode click/activation should keep the current behavior:

- opening the existing episode preview dialog

No new interaction model is needed here.

## Data Sources And Fallbacks

Season header data should resolve from the selected season first:

- poster: `FollowingSeason.poster`
- title: `FollowingSeason.title`
- overview: `FollowingSeason.overview`
- air date: `FollowingSeason.air_date`
- episode count: `FollowingSeason.episode_count`

Fallback rules:

1. If the selected season has no poster, use the record-level poster.
2. If the selected season has no overview, use the snapshot-level overview.
3. If neither exists, show compact placeholder text such as `暂无本季简介`.
4. Missing season metadata must not trigger extra background fetches on its own.

This keeps the UI deterministic and avoids turning a layout refinement into a metadata-refresh feature.

## Configuration And Migration

The current persisted setting `following_episode_display_mode` no longer matches the new UX. The config should move to an explicit column-count preference:

- add `following_episode_grid_columns`
- valid values: `1`, `2`, `3`
- default value: `1`

Compatibility strategy:

- existing installs may still have `following_episode_display_mode`
- the app can keep reading that legacy field for migration compatibility
- after the new field exists, the detail page should use `following_episode_grid_columns` as the canonical value

Normalization:

- invalid or missing values normalize to `1`

This keeps saved state simple and aligned with the new control.

## Implementation Plan Shape

Implementation should stay focused and not spread into unrelated refactors.

Expected areas:

- `src/atv_player/ui/following_detail_page.py`
- `src/atv_player/ui/following_episode_browser.py`
- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- focused tests in:
  - `tests/test_following_detail_page_ui.py`
  - `tests/test_following_episode_browser.py`
  - `tests/test_storage.py`

Recommended structural direction:

- keep the existing season grouping helpers and watched-state logic
- remove the episode mode tabs from the browser API
- replace the single-column list rendering with a grid-oriented episode surface
- keep async thumbnail loading and episode activation behavior

## Testing Strategy

Add or update focused coverage for:

- the detail page no longer rendering the `简洁 / 封面 / 完整` tab control
- the new default column count being `1`
- column-switch controls changing the rendered column count
- the selected column count being saved and restored
- invalid persisted column values normalizing to `1`
- season selection updating the season header content
- season header poster/overview fallback behavior
- the season list consuming less width than before
- the episode section minimum height increasing relative to the old layout target
- cast cards and cast rail height shrinking relative to the previous values
- episode activation still opening the existing preview dialog

The tests should focus on behavior and widget contract, not pixel-perfect styling.

## Risks And Mitigations

### Risk: too many episode widgets for long seasons

Moving away from a single `QListView` delegate to a grid of widgets may increase widget count for long-running shows.

Mitigation:

- keep the implementation scoped to the current selected season only
- avoid rendering off-season episode widgets
- preserve the current lazy season-load behavior

This may still be acceptable for current usage because only one season is visible at a time.

### Risk: config migration confusion

Older configs contain a mode string rather than a numeric column count.

Mitigation:

- define one canonical new field
- normalize missing/invalid values to `1`
- keep tests proving compatibility behavior

### Risk: season metadata is incomplete

Not all providers or stored snapshots will have season-level overview/poster fields.

Mitigation:

- use deterministic fallback to record/snapshot-level fields
- show clear placeholders instead of hiding the entire header

## Acceptance Criteria

The feature is complete when:

- the following detail page no longer shows `简洁 / 封面 / 完整`
- the episode area always uses the rich/full episode presentation
- users can switch between `单列 / 双列 / 三列` using a top-right button group
- the default layout is `单列`
- the selected layout persists across page reopen and app restart
- the season list is visibly narrower
- the episode section is taller and more prominent
- cast cards are smaller and the cast rail consumes less height
- the selected season’s poster and overview appear in the episode area header
- missing season poster/overview cleanly fall back without errors
