# Blu-ray ISO Playback Design

## Goal

Support online Blu-ray ISO playback in the desktop player without requiring `mpv` to parse the ISO image directly.

The first version only targets remote Blu-ray ISO files such as:

- `http://.../movie.iso`

The player should resolve the ISO into a normal HTTP-playable media stream before handing it to `mpv`.

## Scope

In scope for this change:

- detect remote `.iso` playback targets
- inspect the ISO as a Blu-ray image
- expose the selected internal `m2ts` file through the existing local HTTP proxy pattern
- play the selected stream through the current `PlayerWindow -> MpvWidget` flow
- show explicit user-facing logs when ISO parsing fails or the ISO is not a supported Blu-ray layout

Out of scope for this first version:

- DVD ISO support
- optical disc menus
- full Blu-ray playlist navigation
- seamless branching support
- manual track selection inside the ISO

## Current Problem

The current player pipeline eventually passes the resolved playback URL directly to `mpv`.

That works for:

- normal media URLs such as `mp4`, `mkv`, `m3u8`
- DASH data URIs
- some proxied or disguised transport stream URLs

It does not work for Blu-ray ISO files. A remote `.iso` URL is currently treated as a normal media URL and loaded directly by `mpv`. `mpv` then reports `没有可播放的音视频流 (-16)` because it does not automatically inspect the ISO and select a playable title stream from `BDMV/STREAM`.

## Recommended Approach

Add an ISO resolution layer before playback:

1. detect that the playback source is a remote `.iso`
2. parse the ISO structure through a dedicated service
3. verify the image is a Blu-ray layout with `BDMV/STREAM`
4. pick a default main feature stream
5. expose that internal file through the local proxy as a normal HTTP media URL
6. keep `mpv` unchanged and let it play the proxied `m2ts`

This keeps optical-media complexity out of the player widget and matches the existing architecture, where the player already relies on a local proxy for HLS, DASH, and disguised media.

## Architecture

### ISO Service

Add a small service dedicated to remote ISO playback preparation.

Responsibilities:

- decide whether a URL should be treated as a remote ISO
- open the ISO through random-access HTTP reads
- inspect the filesystem entries
- identify whether the image is a supported Blu-ray layout
- list candidate `BDMV/STREAM/*.m2ts` files
- choose the default target stream
- return metadata needed by the local proxy

Non-responsibilities:

- UI logging
- `mpv` interaction
- playback history
- DVD parsing

### HTTP Range Reader

The ISO parser must not download the full image to local disk before playback.

Instead, it should use on-demand HTTP `Range` requests against the original ISO URL. This fits large images such as `43.79 GB` and aligns with the existing proxy strategy for remote media.

The reader should:

- fetch byte ranges lazily
- reuse current request headers
- raise clear errors for missing range support or remote fetch failures

### Local Proxy Extension

Extend the existing `LocalHlsProxyServer` with an ISO-backed raw-media endpoint.

The proxy should:

- register an ISO playback session
- map a virtual path such as `/iso/<token>/BDMV/STREAM/00080.m2ts`
- serve the selected embedded file with HTTP range support
- stream bytes from the remote ISO through the ISO range reader instead of buffering the whole file

This keeps the final playback target as a normal HTTP media resource from the player’s perspective.

## Blu-ray Detection and Selection

The first version should only accept Blu-ray ISOs that contain:

- `BDMV/index.bdmv`
- `BDMV/STREAM/*.m2ts`

If that structure is absent, the service should fail with a targeted message rather than falling through to direct `mpv` playback.

### Default Stream Selection

For the first version, select the main feature using a simple deterministic rule:

1. prefer the largest `BDMV/STREAM/*.m2ts`
2. if sizes tie, prefer the lexicographically later full path only to keep selection stable

This does not fully model Blu-ray playlists, but it is a good first pass and will handle many disc images where the main movie is the dominant stream file.

Known limitation:

- some discs split the main feature across multiple `m2ts` segments or use playlist-based branching, so largest-single-file selection may pick only part of the movie or a wrong title

That limitation is acceptable for the first version and should be called out clearly in code comments and logs.

## Playback Flow

When `PlayerWindow` is about to prepare playback for a URL:

1. existing preflight decides whether the source needs special preparation
2. if the URL is a remote `.iso`, the ISO service resolves it to a proxied internal `m2ts` URL
3. the current `PlayItem.url` is replaced with that proxied URL
4. the current playback flow continues unchanged

The player should still behave like normal playback after resolution:

- same `mpv` loading path
- same history reporting
- same progress handling
- same pause, seek, and audio/subtitle track flow as far as the selected `m2ts` supports them

## Error Handling

Failure modes should be explicit in the log panel.

Expected messages:

- remote source is not a supported Blu-ray ISO
- Blu-ray ISO contains no playable `m2ts` streams
- remote ISO server does not support required range reads
- ISO parsing failed due to malformed image data
- proxy stream failed while reading from remote ISO

Do not fall back to direct `.iso` playback after ISO parsing fails. That would only reintroduce the current opaque `mpv` error.

## Testing

Add focused unit coverage for:

- remote ISO URL detection
- Blu-ray layout detection from parsed ISO directory entries
- default stream selection choosing the largest `m2ts`
- proxy URL generation for ISO sessions
- range-serving behavior for embedded ISO files
- playback-preparation integration rewriting a `.iso` source into a proxied `m2ts` URL
- user-facing failure logging for unsupported or malformed ISO inputs

Use small fakes for:

- HTTP range reads
- ISO directory contents
- proxy session registration

Do not depend on a real multi-gigabyte ISO fixture in tests.

## Implementation Notes

The change should stay isolated to the playback-preparation and proxy layers:

- a new ISO parsing module/service
- `M3U8AdFilter` or a sibling preparation path expanded to recognize remote `.iso`
- local proxy support for ISO-backed virtual files
- player-window tests covering the new preparation path

`MpvWidget` should not gain ISO-specific behavior.

## Risks

- largest-file heuristics will miss some multi-segment Blu-ray titles
- remote storage backends may behave poorly on many range requests
- some servers may not return stable `Range` responses for huge files

Mitigations:

- keep the first version Blu-ray-only
- keep the selection rule simple and explicit
- surface actionable log messages
- preserve the option for a future second phase that parses Blu-ray playlists (`.mpls`)
