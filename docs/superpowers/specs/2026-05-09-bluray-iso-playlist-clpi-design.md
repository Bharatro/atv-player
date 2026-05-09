# Blu-ray ISO Playlist and CLPI Design

## Summary

This design extends the existing remote Blu-ray ISO playback implementation beyond largest-`m2ts` selection.

The new goal is to make default-title startup match the behavior of players that treat a Blu-ray ISO as:

- a lightweight metadata parse step
- followed by playlist-driven clip selection
- followed by clip-level byte-range trimming
- followed by a single logical stream assembled from those trimmed regions

This is a second-phase design on top of [2026-05-09-bluray-iso-playback-design.md](/home/harold/workspace/atv-player/docs/superpowers/specs/2026-05-09-bluray-iso-playback-design.md:1). That first phase introduced remote ISO inspection, Range-backed reads, and proxying a selected internal stream. This phase upgrades the remote UDF path to use `BDMV/PLAYLIST/*.mpls` and `BDMV/CLIPINF/*.clpi` so multi-clip main features can start faster and more accurately.

## Goals

- Prefer Blu-ray playlists over largest-single-file heuristics when remote UDF metadata is available.
- Build one logical playback stream from all clips referenced by the selected playlist, in order.
- Trim each referenced `.m2ts` clip to the effective byte range implied by `in_time` and `out_time`.
- Parse only the metadata needed for the selected playlist, so startup stays bounded by a small number of HTTP range reads.
- Preserve the existing local proxy and cached range-read architecture.

## Non-Goals

- Implement full Blu-ray title browsing or manual title selection.
- Replicate the full upstream player scoring logic for every stream type in this change.
- Parse all `.clpi` files up front.
- Add SACD handling, DVD handling, or optical menu support.
- Change `mpv` behavior or move ISO logic into the player widget.

## Scope

Primary implementation should stay inside:

- `src/atv_player/player/bluray_iso.py`

Primary verification should stay inside:

- `tests/test_bluray_iso.py`
- `tests/test_hls_proxy_server.py`

No UI, controller, or proxy API redesign is required for this phase.

## Current Problem

The current remote UDF path already parses `MPLS`, but it still collapses a multi-clip playlist into one selected clip by picking the largest referenced `.m2ts`.

That creates two correctness problems:

- the selected stream may contain only one section of the main feature
- startup may include unwanted bytes before or after the real playback interval because no `CLPI` timing-to-byte mapping is applied

This means some Blu-ray ISOs still start slowly, pick the wrong title, or play only part of the movie even though the required metadata is available in the image.

## Recommended Approach

Keep the existing remote ISO plumbing and replace only the playlist-resolution policy for remote UDF Blu-ray images:

1. enumerate `BDMV/PLAYLIST/*.mpls`
2. parse playlists into ordered play items with `clip_id`, `stream_path`, `in_time`, `out_time`, and duration
3. try playlist candidates in descending duration order
4. for the first viable playlist, lazily read only the referenced `BDMV/CLIPINF/*.clpi`
5. extract entry-point time/byte mappings from each required `CLPI`
6. convert every play item into an effective byte range inside its physical `.m2ts`
7. slice the existing cached stream source into trimmed child sources
8. concatenate those child sources into one logical stream source
9. return that logical source through the existing proxy path

If every playlist fails at any stage, fall back to the current largest-`m2ts` rule.

## Design

### Metadata Model

Add a minimal internal model for the metadata this phase actually needs.

Suggested structures:

- `_MplsPlayItem`
  - `clip_id: str`
  - `stream_path: str`
  - `in_time: int`
  - `out_time: int`
  - `duration: int`
- `_ParsedMplsPlaylist`
  - `path: str`
  - `play_items: tuple[_MplsPlayItem, ...]`
  - `duration: int`
- `_ClpiEntryPoint`
  - `time_45k: int`
  - `byte_offset: int`
- `_ParsedClpi`
  - `clip_id: str`
  - `entry_points: tuple[_ClpiEntryPoint, ...]`

This phase should not model the full Blu-ray metadata tree. It only needs stable clip identity, timing windows, and time-to-byte mapping.

### MPLS Parsing

Upgrade playlist parsing so it preserves ordered play items rather than only returning clip paths.

Required behavior:

- verify the `MPLS` magic
- read the playlist section offset from byte `8`
- iterate play items in order
- read:
  - `clip_id` from the first 5 bytes
  - codec from the next 4 bytes
  - `in_time`
  - `out_time`
- only keep items whose codec is `M2TS`
- compute item duration as `max(0, out_time - in_time)`
- compute playlist duration as the sum of valid item durations

If a playlist produces no valid play items, reject it.

### Playlist Candidate Policy

Candidate ordering for this phase should stay simple and deterministic:

- sort by `duration` descending
- break ties by playlist path descending

This intentionally does not implement the full stream-priority scoring logic yet. The main improvement in this phase comes from playlist-based assembly and `CLPI`-based trimming, not from a more advanced default-title ranking algorithm.

### CLPI Parsing

For the selected playlist candidate, read only the `CLPI` files referenced by its play items.

Required behavior:

- verify the `HDMV` magic
- parse enough structure to extract entry points that map:
  - `time_45k`
  - physical byte offset inside the corresponding `.m2ts`

This parser should intentionally ignore metadata that is not required for start and end byte calculation.

Each parsed `CLPI` should expose entry points sorted by time ascending.

If a referenced clip has no usable entry points, treat the whole playlist as failed and try the next candidate.

### Time-to-Byte Mapping

Each play item should be converted from a time interval into a physical byte interval inside the `.m2ts`.

Required lookup behavior:

- start mapping chooses the earliest entry point whose time is at or after `in_time`; if none exists, use the last entry point
- end mapping chooses the latest entry point whose time is at or before `out_time`; if none exists, use the first entry point

The result should then be aligned to Blu-ray transport-packet boundaries:

- floor start to the previous 192-byte boundary
- move end to a 192-byte boundary that preserves the intended inclusive range

If the aligned end does not produce a positive-length interval, treat the playlist as failed.

### Cached Source Slicing

Do not create a new byte buffer for clip trimming.

Instead, add a helper that slices an existing `_CachedIsoStreamSource` into a child `_CachedIsoStreamSource` with:

- rebased logical offsets starting at zero
- physical offsets still pointing into the original remote ISO
- only the segment regions that overlap the requested clip interval

This keeps playback compatible with the existing `read_iso_stream_range_from_source()` path and preserves range-cache behavior.

### Logical Stream Assembly

After each play item has been converted into a trimmed child source:

- concatenate all child sources in play order using the existing source-composition model
- expose the total logical size as the sum of trimmed child sizes

The returned `IsoPlaybackPlan.stream.path` should remain a stable normal-looking path. The simplest choice is to keep using the first play item's `stream_path`, because the actual payload is already defined by `plan.source` and the proxy session stores that source directly.

### Failure and Fallback Rules

The remote UDF playlist path should be strict per candidate and forgiving across candidates.

For one candidate playlist, fail that playlist if:

- `MPLS` parsing fails
- any referenced `.m2ts` entry cannot be resolved
- any referenced `.clpi` entry cannot be resolved
- `CLPI` parsing yields no usable entry points
- any play item maps to an empty or invalid byte interval

If one playlist fails, continue to the next candidate.

If all playlists fail, preserve the current fallback:

- list `BDMV/STREAM/*.m2ts`
- pick the largest stream
- proxy that stream as before

## Playback Flow

The updated remote UDF flow inside `prepare_iso_playback()` should be:

1. open the remote ISO through the existing range reader
2. confirm the image is on the remote UDF path
3. enumerate playlist candidates
4. parse and rank candidate playlists
5. for each candidate:
   - resolve referenced `.m2ts` entries
   - build cached physical sources
   - resolve only the referenced `.clpi` entries
   - trim each clip source using `in_time` and `out_time`
   - compose one logical source
   - return an `IsoPlaybackPlan`
6. if no candidate succeeds, fall back to largest-`m2ts`

The proxy path, HEAD behavior, byte-range serving, and `mpv` integration remain unchanged.

## Testing

Add focused unit coverage for:

- `MPLS` parsing returning ordered play items and total duration
- minimal `CLPI` parsing returning entry-point mappings
- time-to-byte lookup around `in_time` and `out_time` edges
- 192-byte alignment behavior
- slicing a cached source into a rebased child source
- composing multiple trimmed child sources into one logical stream
- remote UDF playback selecting a playlist-backed logical source instead of the largest single clip
- resolving only the selected playlist's `.clpi` files
- retrying the next playlist when trimming or `CLPI` resolution fails
- preserving largest-`m2ts` fallback when all playlists fail

Tests should continue using compact synthetic binary fixtures rather than real ISO images.

## Risks

- a minimal `CLPI` parser may initially fail on some discs if the expected entry-point layout varies
- start and end mapping heuristics may still differ from more complete player implementations
- strict per-playlist failure handling may reject some playable discs until parser coverage improves

## Mitigations

- keep the parser intentionally narrow and well covered with binary fixtures
- preserve the current largest-`m2ts` fallback
- isolate all new behavior in `bluray_iso.py` so future scoring or parser improvements do not affect the rest of playback

