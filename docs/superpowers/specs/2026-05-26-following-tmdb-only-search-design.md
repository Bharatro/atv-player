# Following TMDB-Only Search Design

## Goal

Refine the `添加追更` dialog so manual title search uses TMDB only, while presenting richer TMDB results as poster cards instead of plain text rows.

The approved direction is:

- keyword search is TMDB-only
- pasted TMDB URLs still resolve directly
- pasted Bangumi / 豆瓣 URLs keep their current direct-recognition behavior
- the source-group column is removed
- results render as poster cards with metadata on the right
- TV results appear before movie results
- overview text is clamped to 3 lines

## Scope

This change covers:

- `FollowingController.search_media()` provider selection for manual keyword search
- TMDB result hydration needed for richer card display
- `FollowingSearchDialog` layout changes from grouped text rows to a single result list
- custom result card rendering for poster, rating, title, year, media type, and overview
- sorting TMDB search results so TV entries come before movie entries
- targeted controller and dialog test updates

This change does not cover:

- changing how records are stored after the user adds a result
- changing update-check logic, detail-page layout, or follow-state persistence
- changing metadata search behavior in the player scrape dialog
- replacing non-TMDB URL recognition with TMDB-only URL handling
- redesigning the dialog into a full browse page or poster wall

## Current Problems

The current add-following search flow is still optimized for multi-provider grouped text output:

- title search fans out to all available metadata providers
- the left provider-group list is unnecessary when the desired result source is fixed
- each result is rendered as a short text row, so poster, rating, and overview are not visible
- users cannot quickly distinguish TV from movie results before adding
- movie and TV matches share the same ordering even though the desired priority is TV first

## User Experience

### Search Input

- Users can still type a title or paste a supported metadata URL.
- Keyword searches should only query TMDB.
- URL input should continue to use the existing direct-candidate parsing path.

### Search Results

- The dialog should show a single result column without a provider-group sidebar.
- Each result should render as a compact horizontal card:
  - poster on the left
  - title and supporting metadata on the right
  - overview below the metadata block
- The card should display:
  - poster
  - rating
  - title
  - year
  - media type label: `电视` or `电影`
  - overview
- Overview text should be visually limited to 3 lines with truncation.
- Missing fields should degrade gracefully:
  - no poster: show a stable visual placeholder
  - no rating: omit the rating badge rather than showing fake values
  - no overview: show a short fallback such as `暂无简介`

### Ordering

- TV results must appear before movie results.
- Within each media type bucket, keep TMDB's returned order.
- No extra local scoring or fuzzy re-ranking is added in this change.

## Data and Search Design

### Keyword Search Routing

- `FollowingController.search_media()` should detect URL candidates first, as it does now.
- If the input is not a recognized URL candidate, the controller should issue a TMDB-only metadata search.
- Preferred call path:
  - `metadata_search_service.search_following(query, provider_filter="tmdb")`
- Fallback path if the service does not expose `search_following`:
  - `metadata_search_service.search(query, provider_filter="tmdb")`

This keeps the TMDB-only restriction local to add-following search instead of changing shared metadata search defaults.

### URL Handling

- TMDB URLs should continue to hydrate into a filled candidate result.
- Bangumi and 豆瓣 URLs should continue to resolve through the existing `following_candidate_from_url()` path.
- “TMDB-only search” applies to manual keyword search only, not to pasted URL recognition.

### Result Hydration

- TMDB keyword results should be hydrated enough to support the card layout.
- The dialog needs reliable access to:
  - `poster`
  - `rating`
  - `overview`
  - canonical TMDB media identity
- Hydration can continue to reuse the controller-side candidate enrichment pattern already used for URL candidates.
- Media type should be inferred from the TMDB `provider_id` prefix:
  - `tv:` => `电视`
  - `movie:` => `电影`

## UI Architecture

`FollowingSearchDialog` should remain a dialog with the same async search/add behavior, but the result presentation changes:

- remove `group_list`
- keep one selectable result list
- replace plain `QListWidgetItem` text rendering with per-item widgets

Recommended widget structure:

- `QListWidget` remains the container for low-risk selection and double-click behavior
- each result row uses a custom widget attached with `setItemWidget(...)`
- the item widget owns:
  - poster thumbnail
  - title row
  - metadata row
  - overview label

This keeps the implementation close to the existing dialog while avoiding a larger model/delegate rewrite.

## Visual Layout

Each result card should read as a compact media summary, not a generic settings row.

### Card Structure

- poster thumbnail with fixed size and rounded corners
- top row for title and optional rating badge
- second row for year and media type
- third block for overview preview

### Layout Behavior

- the row height should be stable enough that results scan cleanly
- title should take priority over metadata when width is constrained
- overview should wrap and clamp to 3 lines
- selection and hover states should remain obvious at the full-card level

### Styling Direction

- preserve the dialog's current theme tokens
- avoid introducing a brand-new visual system just for this dialog
- use the existing warm/light application styling vocabulary

## Error Handling

- If TMDB search fails, the dialog should still show a standard search failure message.
- If TMDB returns partial results, cards should render with whatever fields are available.
- If hydration fails for a keyword result, the base TMDB search candidate should still remain selectable.
- Removing the provider sidebar should not affect add, double-click, keyboard selection, or close behavior.

## Testing

Add or update targeted tests to cover:

- keyword search only calls TMDB
- TV results are ordered before movie results
- TMDB URL results still hydrate and display rich card information
- Bangumi / 豆瓣 URL recognition is not broken by the TMDB-only keyword restriction
- the dialog no longer renders the provider-group sidebar
- cards show the required text fields and remain selectable/addable
- current-episode manual input still passes through unchanged

## Implementation Notes

Recommended implementation sequence:

1. Add controller coverage for TMDB-only keyword search and TV-first ordering.
2. Add dialog coverage for the single-column card layout and retained add behavior.
3. Introduce the custom result-card widget and remove the provider-group column.
4. Reuse existing poster loading/theme helpers where practical instead of creating dialog-specific infrastructure.
5. Run focused following-controller and following-search-dialog regressions after the UI change.
