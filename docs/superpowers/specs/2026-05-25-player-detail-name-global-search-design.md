# Player Detail Name Global Search Design

## Goal

In the player details panel, clicking the displayed media name should close the player window and start a global search for that same name.

## Scope

- Support only the normal playback detail layout where the metadata row label is `名称`.
- Do not support YouTube-style details (`detail_style == "youtube"`), where the row label is `标题`.
- Do not support live-style details (`detail_style == "live"`), where the row label is `标题`.
- Use the currently displayed `vod_name`, so scraped metadata names are searched when scraped metadata is active. If the original metadata toggle is active, the original displayed name is searched.

## Architecture

`PlayerWindow` already renders details as HTML in `metadata_view` and dispatches internal links from `_handle_metadata_link()`. Add a new `global_search_requested` signal and render the normal `名称` row as an internal `atv-player://global-search` link when the name is non-empty. `MainWindow` connects that signal to the existing `_handle_favorite_global_search()` helper, which already sets the global search box and starts the search.

## Behavior

When the user clicks the `名称` value in the normal player details panel:

1. `PlayerWindow` parses the internal link.
2. It emits `global_search_requested` with the displayed name.
3. `PlayerWindow` runs the existing return-to-main flow, hiding the player and stopping current playback.
4. `MainWindow` starts the existing global search flow with that keyword.

Invalid or empty keywords are ignored. External metadata links and existing detail-field links continue to use their current handlers.

## Testing

- Add a `PlayerWindow` UI test that opens a normal session, verifies the plain text still includes `名称: <name>`, and invokes the internal link handler to assert the signal emits the name.
- Assert that clicking the name also emits `closed_to_main` and hides the player window.
- Add a `PlayerWindow` UI test that YouTube/live details do not render a global-search link for their title rows.
- Add a `MainWindow` UI test that a player-window `global_search_requested` signal calls the existing global search path.
