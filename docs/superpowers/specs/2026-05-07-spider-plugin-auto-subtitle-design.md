# Spider Plugin Auto Subtitle Fallback Design

## Summary

Adjust spider-plugin subtitle behavior so a plugin-provided external subtitle is auto-enabled only when the current media item has no embedded subtitle tracks.

The change is intentionally scoped to spider-plugin external subtitles in the player window. It must preserve the current manual subtitle controls, avoid affecting Bilibili external subtitles, and keep user-driven subtitle choices authoritative.

## Goals

- Auto-enable a spider-plugin external subtitle when the current item exposes one and mpv reports no embedded subtitle tracks.
- Keep the existing primary subtitle selector and external subtitle loading path.
- Preserve `auto` semantics for embedded subtitles whenever embedded tracks exist.
- Avoid overriding explicit user subtitle choices after playback starts.

## Non-Goals

- Auto-enable Bilibili or other non-plugin external subtitles.
- Add plugin subtitles to the secondary subtitle slot.
- Persist plugin subtitle auto-selection as a new global preference.
- Redesign subtitle UI, labels, or context menu structure.

## Scope

Primary implementation should live in:

- `src/atv_player/ui/player_window.py`

Primary verification should live in:

- `tests/test_player_window_ui.py`

No spider controller changes are required for this behavior as long as plugin subtitles are already mapped into `PlayItem.external_subtitles`.

## Trigger Rules

Auto-enable should only happen when all of the following are true:

- the current `PlayItem` exposes at least one external subtitle with `source="spider"`
- the current embedded subtitle track list is empty
- the current primary subtitle preference is still `auto`
- there is not already an active primary external subtitle track for the current item

If any condition is false, the player should keep existing behavior.

## Selection Semantics

The auto-selection should reuse the current primary external subtitle loading path rather than creating a new loading mechanism.

When triggered, the player should:

1. choose the first available spider external subtitle for the current item
2. load it through the existing external subtitle loader
3. bind the resulting track to the primary subtitle slot
4. remember that the active subtitle choice is an external subtitle for the current item

This auto-selection should not be modeled as a user manual choice. The user should still be able to switch to:

- `自动选择`
- `关闭字幕`
- an embedded subtitle track
- the same spider subtitle again manually

Once the user explicitly changes subtitle state away from the auto-triggered result, the auto-fallback logic must not immediately reapply and fight the user.

## Embedded Subtitle Priority

Embedded subtitle tracks remain higher priority than spider external subtitles.

Behavior rules:

- if embedded subtitle tracks are present when subtitle state refreshes, `auto` should continue to target embedded subtitle behavior only
- if no embedded subtitle tracks are present, spider subtitle fallback may activate
- if embedded subtitle tracks appear later for the same item after spider fallback already activated, the player should not forcibly replace the already active plugin subtitle during that session refresh cycle

This keeps playback stable and avoids surprising mid-playback switches.

## Error Handling

Plugin subtitle auto-load failures must not interrupt playback.

If loading the spider subtitle fails:

- keep playback running
- append a concise log message
- leave the primary subtitle preference in a safe state
- avoid retry loops on the same immediate refresh cycle

The player should degrade back to “no active subtitle” rather than repeatedly trying and failing on every refresh signal.

## Testing Strategy

Add focused player-window tests for:

- auto-loading a spider subtitle when there are no embedded subtitle tracks
- not auto-loading when embedded subtitle tracks exist
- not auto-loading non-spider external subtitles under the same conditions
- preserving a user manual subtitle-off or manual-track choice without auto-reapplying plugin subtitles
- keeping existing manual plugin subtitle selection behavior intact

## Implementation Order

1. Add failing player-window tests for spider subtitle auto-fallback.
2. Implement helper logic to detect auto-fallback eligibility from current subtitle state.
3. Reuse the primary external subtitle loading path to auto-apply the first spider subtitle.
4. Add safeguards so manual user choices are not overridden by subsequent refreshes.
5. Run focused subtitle regressions and full touched-module verification.
