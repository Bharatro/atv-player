# Following Season Detail Official Layout Design

## Summary

Refit the middle season-detail pane in the following detail three-column workspace to use a layout modeled after the official season summary presentation:

- top section uses a horizontal split
- left side shows a larger season poster
- right side shows season title, episode count, and air date on separate top-aligned rows
- bottom section shows the season overview text across the full pane width
- clicking the middle-pane season poster opens a larger poster preview dialog

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
- Do not redesign the episode preview dialog beyond restoring missing runtime metadata.

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
- The poster is clickable when a season poster source exists.
- Clicking the poster opens a dedicated large-image preview dialog titled with the current season name.
- If no poster source exists, the pane keeps the current empty-state behavior and does not open a preview.

#### Season Information Block

The text block to the right of the poster uses a vertical stack with three rows:

1. Season title
2. Episode count
3. Air date

Requirements:

- Episode count and air date must not be collapsed into one combined line.
- The text stack must stay pinned to the top of the poster area rather than drifting vertically.
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
- `episode_count` -> dedicated episode-count label
- `air_date` -> dedicated air-date label
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
- Split the current combined metadata label into dedicated episode-count and air-date labels.
- Keep the right-side metadata labels top-aligned within the top row.
- Update season-detail refresh logic to populate the new labels.
- Keep current async image refresh behavior for season posters.
- Add a poster-preview dialog or equivalent dedicated large-image dialog for the middle-pane season poster click action.

Additional file:

- `src/atv_player/ui/following_detail_page.py`

Expected preview-dialog change:

- Update `FollowingEpisodePreviewDialog` metadata text to include episode runtime on the same line as air date.
- Format should be `日期 · 时长` when both values exist.
- If runtime is missing or `0`, keep the current safe fallback behavior without showing misleading empty separators.

## Styling Expectations

- Preserve the existing app visual language; do not introduce a new design system.
- Emphasize the title visually over metadata.
- Keep metadata visually quieter than the title.
- Keep spacing intentional and readable rather than dense.
- The result should feel closer to the provided official reference, but still native to the existing app UI.

## Testing

Add or update UI tests to verify:

- the season detail pane exposes separate labels for title, episode count, and air date
- the right-side information stack remains top-aligned and ordered as title -> episode count -> air date
- the season overview renders below the top-row information structure
- season selection still updates all middle-pane fields
- missing season overview still falls back correctly
- existing poster refresh behavior still works
- clicking the middle-pane poster opens a large poster preview when poster content exists
- episode preview dialog metadata shows runtime on the same line as air date when runtime is available

## Risks

- Layout tests can become overly coupled to exact widget structure if written too rigidly.
- Empty air-date or episode-count cases need safe rendering so the pane does not look broken.
- Poster enlargement must not starve the right episode pane of space in normal desktop layouts.

## Acceptance Criteria

- The middle season-detail pane uses a two-section official-style layout.
- The season poster is larger than before.
- Season title, episode count, and air date appear as separate top-aligned rows to the right of the poster.
- The overview appears below that top row and spans the pane width.
- The three-pane page structure and episode grid behavior remain unchanged.
- Clicking the middle-pane season poster opens a large-image preview dialog when a poster is available.
- Episode preview dialog shows runtime in the metadata line together with air date when runtime is present.
