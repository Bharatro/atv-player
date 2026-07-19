# Search Drive Filter Combo Width Design

## Goal

Ensure the search-result drive-type combo displays every option label in full.

## Design

Configure `PosterGridPage.search_drive_filter_combo` with a content-aware
minimum width. The width is calculated from the longest label in
`SEARCH_DRIVE_FILTER_OPTIONS`, plus space for the combo's left/right padding
and drop-down indicator. Use Qt's
`AdjustToMinimumContentsLengthWithIcon` size-adjust policy so the control keeps
enough inline space without expanding to fill the result area.

The change applies to the shared control used by `电报影视`, `电报频道`, and
`盘搜`. It does not change filter values, visibility rules, search behavior,
pagination, or the surrounding row structure.

## Testing

Add a focused `PosterGridPage` UI test that asserts:

- the combo uses the content-aware size-adjust policy;
- its minimum width is at least the measured longest option label plus the
  reserved padding and indicator space;
- all existing drive-filter behavior remains unchanged.

