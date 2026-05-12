# Player Metadata CR Links Design

## Summary

Extend player metadata string rendering so ordinary detail fields such as `vod_director`, `vod_actor`, and `vod_content` may embed clickable inline actions using a lightweight markup contract.

This enables backend-provided values such as a Bilibili UP owner name to open the built-in Bilibili tab and show that UP's video list, without introducing a field-specific frontend rule.

Example:

```text
[a=cr:{"target":"bilibili","type":"category","value":"up:378885845"}/]Harold[/a]
```

The markup is rendered inside the existing metadata text area in the player sidebar. Existing plain-text metadata must continue to work unchanged.

## Goals

- Keep metadata in the existing player detail area.
- Allow arbitrary metadata strings to contain one or more clickable segments.
- Support mixed plain text and clickable text in the same field.
- Route built-in Bilibili links through the built-in Bilibili tab and controller.
- Preserve existing spider-plugin detail-field actions and external-link behavior.
- Degrade invalid markup to plain text instead of breaking playback.

## Non-Goals

- Replace the structured `detail_fields` payload model.
- Add rich text beyond inline clickable segments.
- Support nested clickable markup.
- Add dynamic target registration in the first release.
- Extend clickable markup to poster cards, search results, or browse grids.

## Scope

Primary implementation should live in:

- `src/atv_player/ui/player_window.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/models.py`

Primary verification should live in:

- `tests/test_player_window_ui.py`
- `tests/test_main_window_ui.py`

The change is intentionally scoped to player metadata rendering and click routing.

## Markup Contract

Metadata strings may include zero or more inline clickable segments using this format:

```text
[a=cr:<json>/]label[/a]
```

Example payloads:

```text
[a=cr:{"target":"bilibili","type":"category","value":"up:378885845"}/]Harold[/a]
[a=cr:{"type":"link","value":"https://space.bilibili.com/378885845"}/]Harold homepage[/a]
[a=cr:{"type":"search","value":"Actor 1"}/]Actor 1[/a] / [a=cr:{"type":"search","value":"Actor 2"}/]Actor 2[/a]
```

Contract rules:

- `label` is the rendered clickable text.
- `<json>` must decode to an object.
- `type` and `value` are required for a clickable segment.
- `target` is optional.
- unknown or malformed markup is rendered as plain text.
- source text order is preserved.
- backend-controlled separators such as ` / ` or `、` remain plain text between clickable segments.

## Action Contract

The inline markup uses a small routing object:

- `target: str | omitted`
- `type: str`
- `value: str`

Supported first-release actions:

- `type="category"`
- `type="detail"`
- `type="search"`
- `type="link"`

Supported first-release targets:

- omitted: existing player detail-field routing behavior
- `target="bilibili"`: built-in Bilibili routing behavior

Rules:

- omitted `target` preserves current behavior and routes through the existing player detail action pipeline
- `type="link"` opens the external browser
- `target="bilibili"` must not be routed through spider-plugin `categoryContent()`
- first release only requires `target="bilibili"` with `type="category"` for UP video-list navigation

## Rendering Behavior

The existing metadata view remains the single rendering surface.

Before the metadata text is converted to HTML:

1. scan each supported metadata string for `[a=cr:...][/a]` segments
2. emit plain text fragments as escaped HTML text
3. emit matched clickable fragments as internal anchor links
4. preserve normal field formatting, line order, and separators

Field behavior:

- `vod_director` may contain one clickable segment or plain text
- `vod_actor` may contain multiple clickable segments mixed with plain separators
- `vod_content` may contain clickable segments and line breaks
- first release applies to metadata row values already assembled by `PlayerWindow._format_metadata_html()`, so the capability is generic within the existing player metadata formatter rather than limited to one named field

This keeps `vod_actor` as a normal string field rather than introducing a separate array contract.

## Internal Link Translation

Inline metadata links should be translated into the same internal anchor mechanism already used by clickable detail fields.

The player window should convert a valid inline segment into an internal `atv-player://...` URL that carries:

- `target`
- `action_type`
- `action_value`

The existing metadata anchor click handling should then decode and dispatch this normalized action object upward.

Reasoning:

- one click path keeps metadata-link handling consistent
- player rendering remains source-agnostic
- main-window routing can decide whether a click is for built-in Bilibili, a spider plugin, or an external link

## Main-Window Routing

When the player session receives an inline metadata action:

- `target="bilibili"` and `type="category"`
  - show the main window again
  - switch to the Bilibili tab
  - set the selected Bilibili category to `value`
  - load page 1 via the built-in `BilibiliController.load_items(value, 1)`
- omitted `target`
  - preserve existing detail-field action routing behavior
- `type="link"`
  - open the external browser

The critical rule is that `value="up:378885845"` for `target="bilibili"` means "open this UP owner's built-in Bilibili video list", not "call a spider plugin category route".

## Error Handling

Inline metadata markup must never block playback or metadata display.

Rules:

- invalid JSON is displayed as ordinary text
- missing `type` or `value` produces ordinary text
- unsupported `target` produces ordinary text
- malformed or unclosed tags produce ordinary text
- multiple valid segments in one field are rendered independently in source order

No extra player log entry is required for malformed inline metadata markup in the first release.

## Testing Strategy

Player metadata rendering tests should cover:

- plain text metadata remains plain text
- one valid inline segment renders as one clickable anchor
- multiple inline segments in one field render in order with separators preserved
- malformed markup degrades to plain text
- metadata line breaks continue to render correctly when clickable markup is present

Player click-dispatch tests should cover:

- clicking a metadata inline link forwards the decoded `target`, `type`, and `value`
- existing detail-field links still dispatch correctly

Main-window routing tests should cover:

- `target="bilibili"` plus `type="category"` switches to the Bilibili tab and loads page 1 for `up:378885845`
- omitted `target` continues to use existing spider-plugin detail-field routing
- `type="link"` still opens the external browser path

## Documentation Follow-Up

Document the inline metadata markup for backend providers that populate plain string metadata:

- `[a=cr:<json>/]label[/a]`
- `target="bilibili"` for built-in Bilibili routes
- `type/value` requirements
- multiple clickable segments in one string field
