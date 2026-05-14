# Global Search Popup Visual Refresh Design

## Goal

Refine the global-search popup UI so it feels like a search panel for a video product instead of a plain utility menu.

The approved direction is:

- content-oriented rather than system-oriented
- balanced search panel rather than discovery page
- warm cinema-like palette rather than cool neutral styling

This change is visual only. The existing behavior stays the same:

- explicit popup-button trigger
- left history / right hot-search layout
- hot-search category tabs
- history and hot items still trigger search
- outside click and button toggle still close the popup

## Scope

This change covers:

- `GlobalSearchPopup` visual styling
- spacing, typography, and alignment in both columns
- history-row visual treatment
- hot-search tab visual treatment
- hot-search item layout and hierarchy
- small UI-oriented test updates where structure assertions need to match the refined widget tree

This change does not cover:

- changing popup open/close behavior
- changing hot-search API loading or caching
- reintroducing auto-popup or auto-suggestion behavior
- changing search history persistence rules
- changing the main search bar behavior outside the popup

## Current Problems

The current popup works functionally but still looks assembled from default widgets:

- the container reads like a plain bordered panel rather than product UI
- history and hot-search sections have weak hierarchy
- row spacing and internal alignment feel dense and mechanical
- action buttons such as `清空` and `删除` visually compete with primary content
- tabs look like raw controls instead of content channel selectors
- hot-search items do not feel meaningfully different from history rows

## Visual Direction

Use a warm, editorial search-panel style:

- base surfaces: off-white and warm light beige rather than flat white on gray
- accents: muted orange / copper rather than bright blue
- borders: light and sparse, relying more on block separation and spacing
- typography: stronger section labels, softer metadata, clearer primary text hierarchy
- interaction: warmer hover states with subtle fill changes instead of generic button hover

The popup should feel closer to a compact ranking/search module from a streaming product than to a desktop settings menu.

## Layout Design

Keep the existing two-column structure, but rebalance it visually:

- left column remains the secondary area for search history
- right column becomes the visual anchor for hot-search content
- the center divider should be lighter and less dominant than the current hard split
- both columns should share the same outer padding and vertical rhythm

Recommended proportions:

- history column slightly narrower
- hot-search column slightly wider

The popup width can remain roughly where it is now, but internal spacing should create more breathing room than additional chrome.

## History Column

The history side should look quiet and utilitarian without feeling dead.

### Header

- use a compact section heading such as `搜索历史`
- reduce the visual weight of `清空`
- align heading and action on a clean baseline

### Rows

- keep fixed row height for stability
- use a full-row hover background with warm tint
- make the keyword the clear primary text
- keep `删除` as a small secondary text action with low contrast until hover

History rows should read as simple, scannable recall actions, not as independent cards.

## Hot-Search Column

The hot-search side should carry more of the product personality.

### Header and Tabs

- keep the `热搜` label but make it feel like a section title rather than default label text
- restyle tabs to look like channel selectors
- inactive tabs should be quiet
- active tab should use warm emphasis, ideally through background tint and text color rather than heavy outlines

Tabs should feel closer to media-category pills or segmented controls than native tab widgets.

### Hot Items

Hot-search items should be visually distinct from history rows:

- add ranking numbers on the left
- use larger or stronger title text than history rows
- reserve a little more vertical padding
- use warmer hover fill than history
- allow the right column to read like a small ranking list

This creates immediate visual separation between:

- “things I searched before”
- “things trending now”

## Component Architecture

Keep the current widget ownership in `GlobalSearchPopup`, but separate styling responsibilities more clearly:

- container-level surface styling
- history-section styling
- hot-section styling
- row-level styling for history and hot items
- tab styling

The implementation should prefer a small number of centralized style strings or helper methods instead of scattering many inline style fragments across row constructors.

## Interaction Design

No interaction changes are required, but the refreshed visual states should make current behavior easier to understand:

- hover state should clearly indicate the whole row is clickable
- delete/clear actions should read as secondary utilities
- selected hot tab should be unambiguous
- the popup should visually support quick scanning before clicking

## Error Handling

There are no new functional error cases. Existing fallback states should be visually cleaned up:

- empty history should render as a calm empty state rather than a leftover label
- empty hot-search results should use the same visual language

These empty states should stay compact and avoid dominating the panel.

## Testing

Add or adjust UI coverage to verify the stable structure that this visual refresh relies on:

- history rows still render with fixed height
- history and hot sections still expose their item helpers for click tests
- hot-tab titles and current-tab mapping remain unchanged from a behavioral perspective

Behavioral global-search tests should continue to pass unchanged, since this is not a logic redesign.

## Implementation Notes

Recommended implementation approach:

1. Refactor popup styling into clearer section-level helpers.
2. Restyle container, divider, headings, and action buttons.
3. Redesign history rows with stable height and softer utility actions.
4. Redesign hot tabs and hot rows with ranking-oriented layout.
5. Update targeted UI tests if the row structure changes.

The work should stay inside the popup component and nearby tests unless a tiny helper extraction materially improves maintainability.
