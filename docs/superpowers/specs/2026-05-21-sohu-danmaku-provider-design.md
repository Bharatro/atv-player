# Sohu Danmaku Provider Design

## Summary

Add Sohu as a first-class generic danmaku provider so it participates in the same desktop danmaku workflow as Tencent, Youku, Bilibili, iQIYI, and MGTV. Sohu should support grouped candidate search, manual source switching, and danmaku resolution into the existing XML pipeline. The first release should cover drama, anime, movie, and variety content.

## Goals

- Add a new `sohu` danmaku provider under the existing provider abstraction.
- Include Sohu in generic multi-provider danmaku search and ranking.
- Support candidate expansion for episodic content, movies, and variety shows.
- Resolve Sohu danmaku into `DanmakuRecord` values that the existing service can convert into XML.
- Reuse search-time metadata during resolution to avoid unnecessary repeat probing.
- Keep failures isolated so a broken Sohu response does not block the rest of danmaku search.

## Non-Goals

- Changing player UI behavior or the danmaku source dialog structure.
- Combining danmaku from multiple providers into one merged stream.
- Persisting Sohu-specific metadata outside the existing in-memory provider lifecycle.
- Reworking cross-provider ranking heuristics in `DanmakuService`.
- Adding mobile-specific behavior or non-desktop Sohu handling.

## Scope

Primary implementation should live in:

- `src/atv_player/danmaku/providers/sohu.py`
- `src/atv_player/danmaku/providers/__init__.py`
- `src/atv_player/danmaku/service.py`

Primary verification should live in:

- `tests/test_danmaku_sohu_provider.py`
- `tests/test_danmaku_service.py`

## Product Decision

Sohu should behave like the existing generic providers instead of being limited to Sohu playback pages. A user searching for danmaku on any supported playback source should be able to see Sohu candidates in the grouped result set, switch to a Sohu source manually, and download Sohu danmaku without needing any Sohu-specific UI path.

The first release should target all major content shapes that Sohu exposes through its current search and playlist APIs:

- drama
- anime
- movie
- variety

If one content shape returns incomplete metadata, the provider should degrade to a narrower candidate list or page-based fallback instead of disabling Sohu completely.

## Provider Architecture

Add a new `SohuDanmakuProvider` that fully implements the existing `DanmakuProvider` protocol:

- `search(name: str, original_name: str | None = None) -> list[DanmakuSearchItem]`
- `resolve(page_url: str) -> list[DanmakuRecord]`
- `supports(page_url: str) -> bool`

The provider should use a mixed strategy:

1. Sohu search API for album-level discovery
2. Sohu playlist API for candidate expansion and duration lookup
3. playback page parsing as a fallback for missing `aid` or `vid`

This is the best fit for the current architecture because generic danmaku search depends on providers returning clean per-video candidates during `search()`, while `resolve()` still needs a reliable fallback path when search metadata is incomplete.

## Search Flow

`search()` should follow this pipeline:

1. Normalize the incoming keyword using the same expectations as the other providers.
2. Call the Sohu search endpoint and extract album-level candidates.
3. Drop results that are obviously not main content.
4. Expand each surviving album into concrete playback candidates.
5. Return `DanmakuSearchItem` objects with populated `resolve_context`.

The initial search payload must ignore candidates that do not have a usable album identifier and title. It should also explicitly filter trailer-like results using both structured metadata and title text.

### Search Noise Filtering

Drop a search result when any of the following is true:

- missing `aid`
- missing album title
- `is_trailer == 1`
- corner mark text is `预告`
- cleaned title or metadata strongly indicates `花絮`, `片段`, `特辑`, `采访`, `速看`, `解说`, or similar supplemental content

This keeps Sohu aligned with the existing provider policy of preferring main content over clips, promo assets, and commentary videos.

### Search Result Metadata

Each album-level search result should be transformed into an internal metadata object that keeps:

- `aid`
- cleaned title
- category or type label
- year when available
- poster URL when available
- reported episode count when available

This internal metadata object is only a stepping stone to candidate expansion and does not need to become a shared dataclass.

## Candidate Expansion Rules

Search must return concrete playback candidates, not just album shells, because the player dialog and resolution pipeline expect per-video URLs.

### Drama And Anime

For drama and anime content:

- call the Sohu playlist API using `aid`
- expand each playable video into a `DanmakuSearchItem`
- use the concrete episode page URL when present
- store `aid`, `vid`, duration, and content type in `resolve_context`

If the incoming user query has an explicit episode marker, prefer exact episode matches. If no exact episode match exists, keep only a small fallback set so Sohu does not flood the grouped candidate list with unrelated episodes.

### Movie

For movie content:

- prefer a single main-content candidate
- if the playlist contains one playable item, use it directly
- if the playlist contains multiple items, prefer the longest non-noise item with the closest title match

The movie path should avoid emitting extra promo clips or fragments, even if the playlist API exposes them.

### Variety

For variety content:

- expand the playlist into per-issue candidates when possible
- keep duration in `resolve_context`
- rely on existing `DanmakuService` variety ranking for final cross-provider ordering

If the original query carries a date-like issue key or an explicit issue marker such as `第X期`, keep candidates that preserve that issue identity. If not, keep the closest title matches with reasonable durations.

### Expansion Fallback

If playlist expansion fails or yields no candidates:

- fall back to a single album-derived candidate
- keep enough metadata in `resolve_context` for `resolve()` to try page parsing later

This prevents temporary playlist API failures from turning Sohu into a total search miss.

## Resolve Context

Each returned `DanmakuSearchItem` should include a `resolve_context` payload with the metadata needed to reduce redundant probing during `resolve()`.

Recommended keys:

- `aid`
- `vid`
- `duration_seconds`
- `category_name`
- `year`
- `expanded_from_playlist`

The provider should maintain a small in-memory `page_url -> resolve_context` mapping, similar to the metadata cache pattern already used by other providers. `resolve()` should look up this cache first.

## Resolve Flow

`resolve(page_url)` should follow this order:

1. Load cached `resolve_context` for the page URL when available.
2. Read `aid`, `vid`, and duration from cached metadata if present.
3. If `vid` is missing, try to refresh from the playlist API using known `aid`.
4. If `aid` or `vid` is still missing, fetch the playback page and parse fallback identifiers from HTML.
5. Compute the segment list.
6. Download danmaku segments with bounded concurrency.
7. Parse and deduplicate comment records.
8. Return sorted `DanmakuRecord` values.

If the page still lacks usable `aid` or `vid` after all fallbacks, resolution should fail with a clear `DanmakuResolveError`.

## Identifier Extraction Fallback

Playback page parsing should support at least these fallback patterns:

- `vid="..."`
- `id="aid" value="..."`
- `playlistId="..."`

If the page contains a valid `aid` but not `vid`, the provider should attempt one more playlist lookup and choose the matching video when possible. If the playlist contains only one playable item, that single item may be treated as the match.

## Duration Strategy

When duration is already cached from search expansion, reuse it.

When duration is missing:

- fetch the playlist for the current `aid`
- read the matching video's duration if available
- otherwise use a conservative fallback upper bound for segment generation

If no exact duration is known, the provider should still stop early when several later segments return no danmaku, rather than blindly requesting the entire fallback range.

## Danmaku Segment Fetching

Sohu danmaku should be fetched in fixed 300-second segments using the current Sohu danmaku API shape. The provider should build a segment list from second `0` through the resolved duration.

Each segment request should:

- include a browser-like user agent
- include a Sohu referer
- use a reasonable timeout

The provider should fetch segments with bounded concurrency comparable to the other providers. Segment-level failures should be tolerated individually; the provider should only fail the whole resolve when all segments fail or all segments are unparseable and no danmaku records are recovered.

## Comment Mapping

Sohu comment payloads should be mapped to `DanmakuRecord` as follows:

- `time_offset`: parsed from the comment play time in seconds
- `pos`: converted from Sohu position values to the existing player modes
- `color`: decimal RGB string
- `content`: comment text

Position mapping should match the existing player conventions:

- scrolling comment -> `1`
- top comment -> `5`
- bottom comment -> `4`

Records should be deduplicated using a stable key such as `(time_offset, content)` and sorted by time before returning.

## Error Handling

Search-stage parsing failures should raise `DanmakuSearchError` with Sohu-specific messages such as:

- `搜狐弹幕搜索结果解析失败`
- `搜狐弹幕搜索请求失败: ...`

Resolve-stage failures should raise `DanmakuResolveError` with clear failure categories such as:

- missing `aid` or `vid`
- playlist parsing failure
- danmaku segment parsing failure

Single segment failures should not abort the entire resolve. Search failures should remain isolated by the existing `DanmakuService` provider fan-out so that Sohu failure only removes Sohu candidates and does not break the whole danmaku search.

## Service Integration

Register Sohu in the provider exports and the default `DanmakuService` provider list. Add a provider label entry so grouped danmaku source results display a readable Sohu name.

This should be a minimal integration change:

- import `SohuDanmakuProvider`
- add `sohu` to `__all__`
- include the provider in `create_default_danmaku_service()`
- add `sohu` to provider ordering and label maps

No UI-specific changes should be required because the player already consumes generic grouped source results.

## Testing Plan

Add provider-level coverage in `tests/test_danmaku_sohu_provider.py` for:

- filtering trailer and non-main-content search items
- drama or anime playlist expansion
- movie candidate collapse to one main item
- variety candidate selection with issue-aware matching
- cached `resolve_context` reuse during `resolve()`
- HTML fallback extraction of `aid` and `vid`
- segment comment parsing and position or color mapping
- whole-resolve failure when every segment is unusable

Add service-level coverage in `tests/test_danmaku_service.py` for:

- Sohu inclusion in the default provider set
- grouped source results that include Sohu candidates with the correct provider label

## Risks And Mitigations

- Sohu search or playlist payloads may be inconsistent across content types.
  Mitigation: isolate extraction helpers by content shape and keep page parsing fallback.

- Missing duration data can cause overfetching.
  Mitigation: reuse cached duration, bound segment concurrency, and stop early after repeated empty late segments.

- Playlist expansion may produce too many irrelevant episodic candidates.
  Mitigation: respect explicit episode matching and keep narrow fallback sets.

- Movie and supplemental clip titles can be noisy.
  Mitigation: apply title-noise filtering and prefer the longest non-noise main-content item.

## Implementation Notes

- Keep helper methods inside `sohu.py` unless shared reuse becomes obvious during implementation.
- Follow the existing provider style: plain `httpx` calls injected through the constructor for testability.
- Keep comments minimal and only where the fallback logic would otherwise be hard to read.
