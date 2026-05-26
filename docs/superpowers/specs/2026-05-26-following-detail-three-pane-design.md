# 我的追更详情页三栏分集区 Design

## Summary

Refine the following-detail episode workspace again so it uses a fixed three-pane layout:

- left: season list
- middle: season detail
- right: episode list

This change also replaces the current multi-button column switcher with a single icon button that cycles through `单列 -> 双列 -> 三列 -> 单列`. The cycle only changes the density of the right-side episode list. It does not change the page’s overall three-pane structure.

## Goals

- Change the episode workspace from the current two-part arrangement to a fixed three-pane layout.
- Keep the page-level detail structure intact: top summary area, episode area, cast/crew area.
- Move season detail out of the right-column header and into its own middle pane.
- Keep the left season list narrow and navigation-only.
- Keep the right pane focused on episode cards only.
- Replace the three explicit column buttons with one icon button that cycles through three density states.
- Persist the current episode density in the existing `following_episode_grid_columns` config field.
- Preserve episode preview behavior, season lazy-loading behavior, and watched-state behavior.

## Non-Goals

- Do not redesign the top summary/backdrop section.
- Do not redesign cast/crew information architecture in this iteration.
- Do not add popup menus, hover menus, or right-click behaviors for the density switcher.
- Do not add responsive auto-layout rules that alter the page from three panes into other structures.
- Do not add new metadata fetches when season detail fields are missing.

## User-Approved Decisions

- The episode area should be a true three-pane layout.
- Pane order is fixed: season list, season detail, episode list.
- The density switcher should be a single icon button.
- The button cycles in this order:
  - `单列`
  - `双列`
  - `三列`
  - back to `单列`
- The density switcher only affects the right-side episode list.
- The overall page remains a fixed three-pane episode workspace regardless of density.

## Current Problems

The current implementation already moved toward a richer following-detail episode workspace, but it still has two mismatches with the new requirement:

1. Season detail is still rendered as a header attached to the episode area rather than a dedicated middle pane.
2. Density switching uses multiple explicit controls instead of one cycling icon button.

That means the current episode workspace still mixes season detail and episode controls in one content column. The user now wants clearer spatial separation:

- season selection in one pane
- season context in one pane
- episode browsing in one pane

## Recommended Approach

Upgrade `FollowingEpisodeBrowser` into the full owner of the three-pane workspace.

Responsibilities:

- left pane: season selection list
- middle pane: season poster and season summary
- right pane: episode toolbar and episode card list
- right toolbar: single cycling density button
- internal state: current season summary, selected density, episode cards

`FollowingDetailPage` should stop composing season-detail header UI itself. It should treat the browser as a self-contained episode workspace and only:

- pass grouped episode/season content into it
- react to `grid_columns_changed`
- persist the selected density through config

This keeps the episode workspace cohesive and avoids pushing more layout code into the page shell.

## Layout Design

### Page-Level Structure

Keep the three main page sections:

- top metadata/backdrop section
- episode workspace section
- cast/crew section

Only the internal structure of the episode workspace changes.

### Episode Workspace

The episode workspace becomes a fixed three-pane horizontal split:

- left pane: season list
- middle pane: season detail
- right pane: episode list

Recommended intent for relative width:

- left pane: narrow
- middle pane: medium
- right pane: dominant

The right pane should remain the largest because the episode list is still the primary browsing surface.

### Left Pane: Season List

The left pane remains navigation-only:

- season title
- episode count
- selected state

It should not contain season poster or season overview text.

### Middle Pane: Season Detail

The middle pane becomes the dedicated season context panel.

It should show:

- season poster
- season title
- short metadata line such as rating / air date / episode count when available
- season overview text

This pane replaces the current right-column season header. Its purpose is to keep season context visible without pushing episode cards downward.

### Right Pane: Episode List

The right pane contains:

- top-right density switch button
- episode cards/list below

This pane must not display duplicated season poster/overview content because that now belongs in the middle pane.

## Interaction Design

### Density Switch Button

The density switcher becomes one icon button whose icon reflects the current state.

Behavior:

- current state `1` shows the single-column icon
- click -> state becomes `2`
- current state `2` shows the two-column icon
- click -> state becomes `3`
- current state `3` shows the three-column icon
- click -> state becomes `1`

This is a direct cycle, not a menu trigger.

### Episode Density Semantics

Only the right pane changes density.

- `单列`: full-width list cards, most readable
- `双列`: same fields, tighter spacing, shorter overview clamp
- `三列`: same fields, densest spacing, shortest overview clamp

The information architecture stays the same across all three states. This is not a fallback to compact mode.

### Season Selection

Season selection behavior remains:

- selecting a loaded season updates the middle-pane season detail and the right-pane episode list
- selecting an unloaded season reuses the existing lazy season-detail loading path
- once load completes, both the middle pane and the right pane refresh together

### Episode Activation

Episode activation remains unchanged:

- clicking an episode opens the existing preview dialog

## Data Sources And Fallbacks

Middle-pane season detail should resolve from the selected `FollowingSeason` first:

- title: `FollowingSeason.title`
- poster: `FollowingSeason.poster`
- overview: `FollowingSeason.overview`
- air date: `FollowingSeason.air_date`
- episode count: `FollowingSeason.episode_count`

Fallback rules:

1. If season title is empty, use the computed season display title.
2. If season poster is empty, use `FollowingRecord.poster`.
3. If season overview is empty, use `FollowingDetailSnapshot.overview`.
4. If all overview sources are empty, show `暂无本季简介`.

No new data loading behavior should be introduced just to fill missing middle-pane fields.

## Component Boundaries

### `FollowingEpisodeBrowser`

This component should own:

- pane layout
- season list
- current season summary
- density cycle state
- density button UI
- episode card rendering

Suggested outward interface:

- `set_content(...)`
- `grid_columns()`
- `set_grid_columns(...)`
- `current_season_summary()`
- `grid_columns_changed`
- `season_changed`
- `episode_activated`

### `FollowingDetailPage`

This page should own:

- outer page sections
- action row
- top summary area
- cast rail
- async data loading orchestration
- config persistence

It should no longer own a separate season header block inside the episode section.

## Configuration

Keep using:

- `AppConfig.following_episode_grid_columns`

Behavior:

- valid values remain `1`, `2`, `3`
- current value initializes the browser density
- button clicks update the browser density
- `FollowingDetailPage` persists the new value when the browser emits `grid_columns_changed`

No new config field is needed.

## Testing Strategy

Update focused coverage in:

- `tests/test_following_episode_browser.py`
- `tests/test_following_detail_page_ui.py`

Add or update tests for:

- three-pane browser layout being present
- season detail living in the middle pane instead of the right-header layout
- single density button existence
- density cycle order `1 -> 2 -> 3 -> 1`
- density icon/button state following the active value
- right-pane episode cards preserving overview text in all three density states
- season selection updating both middle-pane detail and right-pane episodes
- `FollowingDetailPage` persisting density after a cycle click
- lazy season loading still working after the layout split

Existing storage coverage for `following_episode_grid_columns` can remain as-is, with only minimal regression updates if needed.

## Risks And Mitigations

### Risk: browser component becomes too large

Moving all three panes into `FollowingEpisodeBrowser` increases its responsibility.

Mitigation:

- keep the page shell logic in `FollowingDetailPage`
- keep the browser focused only on the episode workspace
- avoid pulling unrelated top-level UI into the browser

### Risk: stale season-detail UI during async season loads

When switching to an unloaded season, the middle pane may temporarily display stale content.

Mitigation:

- update selection state immediately
- allow the page to keep existing status text for loading
- refresh the browser content only when the new season result is applied

### Risk: cycling button is less discoverable than three explicit buttons

The button trades discoverability for compactness.

Mitigation:

- keep a clear tooltip matching the current density
- use icons that visibly communicate one/two/three columns
- keep the cycle order fixed and simple

## Acceptance Criteria

The change is complete when:

- the episode section is a true three-pane layout
- left pane shows season navigation only
- middle pane shows season poster and season summary
- right pane shows episode cards only
- one icon button cycles the right-pane episode density through `1 -> 2 -> 3 -> 1`
- the button persists density through `following_episode_grid_columns`
- changing density never collapses the three-pane structure
- season selection still supports lazy loading and episode preview
