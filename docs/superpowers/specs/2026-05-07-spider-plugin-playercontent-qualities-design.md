# Spider Plugin `playerContent().qualities` Playback Quality Design

## Summary

Extend spider-plugin playback so `playerContent()` may return a `qualities` list that describes multiple playable URLs for the same episode. The player should expose those options through the existing playback quality control and switch between them while preserving playback position and paused state when possible.

The change is intentionally scoped to spider-plugin playback items, the existing player quality selector, and the current lazy `playerContent()` resolution flow. Existing plugins that only return a single `url` must keep working unchanged.

## Goals

- Accept `qualities` from spider-plugin `playerContent()` payloads.
- Keep top-level `url` as the default playback URL for backward compatibility.
- Reuse the existing player quality selector UI instead of adding a new dialog or menu.
- Allow switching between spider-provided quality URLs while preserving playback position and pause state.
- Keep existing DASH quality behavior working for items that do not use spider quality options.

## Non-Goals

- Change `playerContent().url` itself to accept arrays.
- Expand one episode into multiple playlist rows just to represent quality variants.
- Support per-quality `header` or `parse` overrides in the first release.
- Support quality entries that only provide labels without a direct playable URL.
- Persist spider quality preference across episodes or app restarts in this change.

## Scope

Primary implementation should live in:

- `src/atv_player/models.py`
- `src/atv_player/plugins/controller.py`
- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_spider_plugin_controller.py`
- `tests/test_player_window_ui.py`

No new top-level UI surface is required. The existing quality combo box and context-menu quality submenu should be reused.

## Payload Contract

`playerContent()` may return:

```python
{
    "parse": 0,
    "url": "https://cdn.example/video-1080.m3u8",
    "header": {"Referer": "https://site.example"},
    "qualities": [
        {"id": "1080p", "label": "1080P", "url": "https://cdn.example/video-1080.m3u8"},
        {"id": "720p", "label": "720P", "url": "https://cdn.example/video-720.m3u8"},
    ],
}
```

Contract rules:

- top-level `url` remains required and is the default playback URL
- `qualities` is optional
- each quality entry must provide non-blank `id`, `label`, and `url`
- each quality `url` must be a directly playable media URL under the same rules already used for ordinary spider playback
- if `qualities` is missing or empty, playback behaves exactly as it does today

The first release applies the top-level `header` to all quality URLs. Per-quality headers are intentionally out of scope.

## Data Model

`PlayItem` should gain dedicated state for spider quality options instead of storing that state only in the player UI.

Add:

- `playback_qualities: list[VideoQualityOption]`
- `selected_playback_quality_id: str`

The existing `VideoQualityOption` model should be extended with:

- `url: str = ""`

That keeps one shared quality-option type for both spider URL qualities and DASH track qualities. For spider-provided qualities, `id`, `label`, and `url` are required; width, height, bandwidth, and codecs may remain unset. For DASH-derived qualities, `url` remains blank because the prepared DASH manifest URL stays on the play item instead of on each option.

`PlayItem.url` remains the currently selected concrete playback URL. `selected_playback_quality_id` tracks which spider quality is active for the current item.

## Controller Behavior

`SpiderPluginController._resolve_play_item()` should continue to resolve:

- parse requirement
- playback URL
- request headers
- external subtitles
- danmaku prefetch

In addition, after a direct playback URL is accepted, it should inspect `qualities` and populate the current `PlayItem` with normalized spider quality options.

Normalization rules:

- each playback resolution overwrites any stale `playback_qualities` and `selected_playback_quality_id`
- malformed entries are ignored rather than failing playback
- if one normalized quality URL matches top-level `url`, that entry becomes the selected quality
- otherwise, if there are normalized qualities, the first entry becomes the selected quality
- if no normalized quality survives validation, the item falls back to single-URL playback

The controller should not replace `item.url` with another quality URL during normalization. Top-level `url` remains the authoritative initial playback URL.

## Player Integration

The player already has one quality control surface. This change should keep that single control but let it represent one of two sources:

- spider URL quality options
- DASH track quality options

Priority rules:

1. If the current play item has spider `playback_qualities`, show those in the quality combo and context menu.
2. Otherwise, if the current prepared URL exposes DASH qualities, keep the existing DASH behavior.
3. If neither source provides multiple qualities, keep the quality control disabled.

This avoids mixing spider URL variants and DASH track variants in one menu at the same time.

## Quality Switching Behavior

When the user switches a spider quality option:

1. Capture the current playback position.
2. Capture whether playback is currently paused.
3. Save the previous `item.url` and previous `selected_playback_quality_id`.
4. Replace `item.url` with the selected spider quality URL.
5. Update `selected_playback_quality_id`.
6. Reuse the existing playback prepare and playback start flow.
7. Resume from the captured playback position.
8. Preserve the previous pause state.

This should match the current DASH quality switching experience as closely as practical.

## Error Handling

Spider quality failures must not interrupt the current successful playback session.

Rules:

- invalid `qualities` payload data is ignored and falls back to top-level `url`
- if a quality switch fails during prepare or load, restore the previous `item.url`
- if a quality switch fails during prepare or load, restore the previous `selected_playback_quality_id`
- append a concise player log message such as `清晰度切换失败: ...`
- keep the previous successful playback active when restoration succeeds

If a spider quality URL turns out to require parse resolution, special headers, or page-level extraction beyond the current direct-play contract, the first release should treat it as unsupported rather than guessing.

## Testing Strategy

Add controller tests for:

- mapping valid `qualities` entries into `PlayItem.playback_qualities`
- selecting the matching quality when one entry URL equals top-level `url`
- falling back to the first valid quality when no entry matches top-level `url`
- ignoring malformed quality entries without breaking top-level playback
- preserving existing behavior when `qualities` is absent

Add player window tests for:

- showing spider quality options in the existing quality combo
- showing spider quality options in the existing quality submenu
- preserving playback position and pause state when switching spider quality
- restoring previous URL and selected quality when a spider quality switch fails
- leaving DASH quality behavior unchanged for items without spider quality options
- preferring spider quality options over DASH quality options when both are theoretically available

## Implementation Order

1. Add failing spider controller tests for `qualities` normalization and selection.
2. Extend `PlayItem` with spider quality state.
3. Implement spider quality parsing in `SpiderPluginController`.
4. Add failing player window tests for spider quality UI and switching behavior.
5. Refactor the player quality refresh logic so one control can represent either spider or DASH quality sources.
6. Implement spider quality switching with playback-state preservation and rollback on failure.
7. Run focused controller and player tests, then broader player-quality regressions.
