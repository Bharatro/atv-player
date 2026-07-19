# Search Result Drive Filter Design

## Goal

Add a drive-type filter to search results for `电报影视`, `电报频道`, and `盘搜`.
The filter operates only on the results already loaded for the current page. It
must not add backend query parameters, fetch additional pages, or change the
reported page count.

## Scope

In scope:

- Show the shared drive-type options for Telegram movie search, Telegram
  channel search, and Pansou search results.
- Filter the current page in memory when the selected drive type changes.
- Restore every item on the current page when the user selects `全部`.
- Normalize missing Telegram result metadata from recognized share-link hosts.
- Support both page-local search mode and global-search results injected through
  `PosterGridPage.show_external_results()`.

Out of scope:

- Server-side filtering or API contract changes.
- Filtering across pages.
- Recalculating result totals or pagination after local filtering.
- Adding drive filters to category browsing, folder browsing, or unrelated
  search providers.

## Existing Behavior

The three result surfaces use `PosterGridPage`:

- `电报影视` and `电报频道` enable the page-local search controls.
- `盘搜` receives global-search results through `show_external_results()` and
  does not expose a page-local search box.

Pansou results already carry normalized `VodItem.share_type` and
`VodItem.type_name` values from `BrowseController.search()`. Telegram movie and
channel results use the generic Douban item mapper, which preserves backend
`type_name` and display remarks but does not populate `share_type`. A Telegram
result may therefore contain only a share link in `vod_id`.

The project already defines the canonical filter options in
`SEARCH_DRIVE_FILTER_OPTIONS` and the matching behavior in
`filter_search_results()`.

## Design

### Drive-Type Normalization

Add a shared URL-to-drive-type helper next to the existing share-type name
mapping. It parses the link hostname and returns a canonical share-type id for
recognized providers. Matching is based on the hostname, not arbitrary URL
substrings.

Telegram movie and channel result mapping will use this precedence:

1. Preserve a non-empty backend `share_type`.
2. Otherwise infer the canonical id from the result share link.
3. Preserve a non-empty backend `type_name`.
4. Otherwise derive the display name from the canonical share-type id.

Unknown or malformed links remain untyped and are visible only under `全部`.
Pansou keeps its existing metadata mapping.

### Shared Result Filter

`PosterGridPage` gains an optional drive-filter capability independent of its
category filter panel. Main-window construction enables it only for the three
requested pages.

The control uses the existing `SEARCH_DRIVE_FILTER_OPTIONS` labels and values.
It is visible when the page is showing either:

- page-local search results, or
- externally injected global-search results.

It is hidden during category and folder browsing. The page keeps two lists for
the current page: the unfiltered loaded results and the rendered filtered
results. Selecting a filter recomputes the rendered list with
`filter_search_results()` and redraws the cards without calling a controller.

The click and context-menu handlers remain bound to the filtered `VodItem`
objects, so opening a visible result behaves exactly as before.

### State Transitions

- Starting a new search resets the filter to `全部` before results arrive.
- Loading another result page applies the currently selected filter to that new
  page.
- Clearing page-local search resets the filter to `全部` and restores category
  browsing.
- Clearing external results resets the filter to `全部` before restoring the
  prior page state.
- Refreshing a search reloads the current page and reapplies the selected
  filter after the response arrives.

Pagination continues to use the backend-provided total or page count. A page
may legitimately display no cards after filtering while the next-page button
remains available.

### Status Text

When filtering removes every loaded item, show a concise empty state indicating
that the current page has no results for the selected drive type. Do not report
the filtered count as the global search total.

## Error Handling

Drive-type inference is best effort. Empty identifiers, malformed URLs, and
unknown hosts return no type without raising. Existing request error and
authorization handling is unchanged because filter changes make no requests.

## Testing

Add focused coverage for:

- recognized share-link hosts mapping to canonical drive ids and names;
- Telegram movie and channel search mapping preserving backend metadata and
  filling missing metadata from `vod_id`;
- `PosterGridPage` filtering only the current loaded page;
- selecting `全部` restoring the complete current page;
- a newly loaded page reusing the active filter without an extra request;
- the filter appearing for page-local and external search results but not for
  category or folder browsing;
- main-window wiring enabling the capability only for `电报影视`, `电报频道`,
  and `盘搜`;
- existing pagination totals and item-opening behavior remaining unchanged.

