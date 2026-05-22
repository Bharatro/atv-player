# yt-dlp Multi-Audio Design

Date: 2026-05-22

## Summary

Add explicit multi-audio support for `yt-dlp` playback sources so the player can:

- show multiple available audio tracks in the existing `音轨` selector
- default to the original English track when available
- switch `yt-dlp` audio tracks by re-resolving and reloading playback rather than relying on `mpv` embedded audio-track switching

This design is scoped to `yt-dlp`-resolved playback items such as YouTube URLs. Existing non-`yt-dlp` audio-track behavior remains unchanged.

## Problem

Current `yt-dlp` playback flow only carries one resolved audio output:

- `url`
- `audio_url`
- `ytdl_format`

It does not preserve the set of available audio-track alternatives. As a result:

- the player cannot render multiple `yt-dlp` audio choices in the `音轨` menu
- the current default audio choice depends on the resolved stream pair rather than an explicit user-facing audio policy
- switching audio after playback starts is only possible when `mpv` exposes embedded alternate audio tracks, which does not cover the current `yt-dlp` flow reliably

## Goals

- Preserve explicit `yt-dlp` audio-track candidates in the resolved playback model.
- Expose those candidates in the existing `音轨` combo box and context menu.
- Default to the original English audio track when available.
- Allow switching `yt-dlp` audio tracks by reloading the current item with the selected audio candidate.
- Keep existing non-`yt-dlp` audio-track logic intact.

## Non-Goals

- Adding a separate new UI control just for `yt-dlp` audio.
- Reworking `mpv` native audio-track switching for local files or non-`yt-dlp` streams.
- Supporting arbitrary site-specific audio policies outside the current `yt-dlp` resolution layer.
- Persisting a global cross-video language preference beyond the existing per-session/per-window audio preference behavior.

## Data Model

Add a dedicated model for `yt-dlp` audio candidates.

Example fields:

- `id`: stable selection key
- `label`: user-facing name
- `lang`: normalized language code
- `format_id`: source `yt-dlp` format identifier when available
- `is_original`: whether the candidate is the original-language track
- `is_default`: whether `yt-dlp` marks it as default
- `ytdl_format`: selector string or equivalent replay token needed to resolve this track

Extend:

- `YtdlpResolveResult` to carry `audio_tracks: list[...]`
- `PlayItem` to carry `audio_tracks: list[...]`
- `PlayItem` to carry `selected_audio_track_id: str`

The existing `audio_url` remains for the resolved active track so playback startup stays compatible with the current load path.

## yt-dlp Parsing

Audio candidates are derived during `yt-dlp` resolve, alongside quality extraction.

For YouTube-like sources:

- inspect `formats` and `requested_formats`
- group audio-capable candidates by stable audio identity
- derive readable labels from language, original/default markers, codec, and channel metadata where available
- generate a replay token that can be used to resolve the same video with a different audio track later

The parser should prefer explicit source metadata in this order:

- original-language markers such as `original`, `orig`, or extractor-provided equivalents
- language code and title
- default flags
- codec/channel detail as disambiguation only

If the extractor does not provide enough information to construct multiple reliable candidates, the result should fall back to the current single-audio behavior.

## Default Selection Policy

For `yt-dlp` multi-audio sources, default selection should be:

1. English original track
2. English non-original track
3. Extractor-default track
4. current resolved fallback

“Original” means extractor metadata or normalized labels indicate the source/original track. This rule is intentionally English-first because the reported use case is lecture/tutorial content where dubbed or translated tracks are currently preferred incorrectly.

If no candidate matches the preferred ordering, keep the resolver’s existing selected track.

## UI Behavior

Reuse the existing `音轨` controls:

- bottom combo box
- right-click `音轨` submenu

When the current `PlayItem` includes explicit `yt-dlp` audio candidates:

- populate the audio selector from `PlayItem.audio_tracks`
- mark the current selected candidate based on `selected_audio_track_id`
- prefer these candidates over `mpv` `track-list` entries for the current item

When the current `PlayItem` does not include explicit `yt-dlp` audio candidates:

- preserve current behavior using `mpv` embedded audio tracks

This keeps UI changes minimal and avoids splitting the audio experience into separate source-specific controls.

## Runtime Switching

For `yt-dlp` audio candidates, selecting a track should not call `mpv` `aid` switching directly.

Instead:

1. capture current playback position and paused state
2. update `PlayItem.selected_audio_track_id`
3. re-resolve or rebuild the current playback URL using the selected `yt-dlp` audio candidate
4. restart the current item from the saved position
5. refresh the `音轨` selector using the newly resolved state

This mirrors the project’s current quality-switch pattern and avoids depending on `mpv` to expose alternative audio tracks for streams that were pre-resolved by `yt-dlp`.

## Interaction With Quality Switching

Quality and audio selection both affect `yt-dlp` resolution, so they must compose cleanly.

Rules:

- quality switch must preserve the selected audio-track ID when still available
- audio switch must preserve the selected quality ID when still available
- if the selected combination becomes unavailable, resolve should fall back deterministically and update both selected IDs

The resolver is the single source of truth for the final stream pair.

## Failure Handling

If multi-audio metadata cannot be extracted:

- keep playback working
- keep `音轨` in current fallback mode

If switching to a selected `yt-dlp` audio track fails:

- keep the currently playing stream unchanged when possible
- restore the previous selected audio-track ID in state
- log a concise failure message that identifies the attempted audio label

If cached or older `PlayItem` instances do not contain the new fields:

- treat them as single-audio items
- avoid migration requirements

## Testing

Add focused tests for:

### yt-dlp service

- extracting multiple audio candidates from representative `yt-dlp` payloads
- preferring English original over translated/dubbed/default alternatives
- preserving selected audio candidate across quality-based resolve
- falling back cleanly when no multi-audio metadata exists

### player window

- rendering `yt-dlp` audio candidates in the `音轨` combo/menu
- selecting a `yt-dlp` audio candidate triggers current-item reload rather than direct `mpv aid` switch
- preserving playback position and pause state during audio reload
- preserving selected quality when switching audio
- preserving selected audio when switching quality
- leaving non-`yt-dlp` audio-track behavior unchanged

## Implementation Notes

The least risky integration point is to treat `yt-dlp` multi-audio as a playback-source choice owned by `PlayItem`, not as a direct `mpv` track feature.

That means:

- parsing belongs in `yt_dlp_service.py`
- persistence of the active choice belongs in `PlayItem`
- UI wiring belongs in `player_window.py`
- `mpv_widget.py` should remain responsible only for actual embedded audio tracks exposed by `mpv`

This preserves clean ownership boundaries and keeps source-specific logic out of the `mpv` wrapper.
