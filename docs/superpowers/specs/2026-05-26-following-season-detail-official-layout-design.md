# Following Season Detail Official Layout Design

## Summary

Refit the middle season-detail pane in the following detail three-column workspace to use a layout modeled after the official season summary presentation:

- top section uses a horizontal split
- left side shows a larger season poster
- right side shows season title, air date, and episode count on separate rows
- bottom section shows the season overview text across the full pane width

This replaces the current stacked poster-title-meta-overview arrangement with a clearer two-tier structure while keeping the overall three-pane page architecture unchanged.

## Goals

- Make the season poster more prominent in the middle pane.
- Match the official season-detail information hierarchy more closely.
- Keep the content focused on season identity and overview.
- Preserve the existing three-pane layout:
  - left season list
  - middle season detail
  - right episode list

## Non-Goals

- Do not add progress badges, completion chips, or other new metadata pills.
- Do not change the season list pane structure.
- Do not change the right-side episode list interaction model.
- Do not add new season fields beyond title, air date, episode count, poster, and overview.

## Layout Design

### Middle Pane Structure

The season detail pane remains a dedicated middle column inside `FollowingEpisodeBrowser`, but its internal layout changes from a single vertical stack to two sections:

1. Top row
   - horizontal layout
   - left: season poster
   - right: season information block
2. Bottom row
   - full-width season overview

### Top Row

#### Poster

- Increase poster size noticeably from the current `96x136`.
- Poster should read as the dominant visual anchor for the pane.
- Poster remains aligned to the top-left of the detail pane.
- Existing poster loading behavior stays intact.

#### Season Information Block

The text block to the right of the poster uses a vertical stack with three rows:

1. Season title
2. Air date
3. Episode count

Requirements:

- Air date and episode count must not be collapsed into one combined line.
- Title remains the strongest text style in the block.
- Air date and episode count use secondary styling.
- If air date is missing, its line remains empty-safe without collapsing the layout in a way that breaks spacing.
- If episode count is `0`, the UI should continue to avoid misleading text; existing season-count formatting rules may still suppress the count line when unavailable.

### Bottom Overview Block

- The season overview moves below the top row.
- It spans the full middle pane width.
- It keeps word wrapping.
- It continues to fall back to `暂无本季简介` when no season overview exists.

## Data Mapping

The middle pane continues to render from `EpisodeSeasonSummary`.

- `title` -> season title label
- `air_date` -> dedicated air-date label
- `episode_count` -> dedicated episode-count label
- `overview` -> overview block
- `poster` -> season poster

The previous combined meta label is replaced by separate labels for:

- air date
- episode count

## Component Changes

Primary file:

- `src/atv_player/ui/following_episode_browser.py`

Expected changes:

- Replace the current season-detail vertical layout with nested top-row and bottom-row layouts.
- Increase poster label sizing constraints.
- Split the current combined metadata label into dedicated air-date and episode-count labels.
- Update season-detail refresh logic to populate the new labels.
- Keep current async image refresh behavior for season posters.

## Styling Expectations

- Preserve the existing app visual language; do not introduce a new design system.
- Emphasize the title visually over metadata.
- Keep metadata visually quieter than the title.
- Keep spacing intentional and readable rather than dense.
- The result should feel closer to the provided official reference, but still native to the existing app UI.

## Testing

Add or update UI tests to verify:

- the season detail pane exposes separate labels for title, air date, and episode count
- the season overview renders below the top-row information structure
- season selection still updates all middle-pane fields
- missing season overview still falls back correctly
- existing poster refresh behavior still works

## Risks

- Layout tests can become overly coupled to exact widget structure if written too rigidly.
- Empty air-date or episode-count cases need safe rendering so the pane does not look broken.
- Poster enlargement must not starve the right episode pane of space in normal desktop layouts.

## Acceptance Criteria

- The middle season-detail pane uses a two-section official-style layout.
- The season poster is larger than before.
- Season title, air date, and episode count appear as separate rows to the right of the poster.
- The overview appears below that top row and spans the pane width.
- The three-pane page structure and episode grid behavior remain unchanged.
