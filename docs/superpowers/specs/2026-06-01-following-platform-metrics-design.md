# Following Platform Metrics Design

## Goal

Show richer official-site metadata on the following detail page for iQiyi, Tencent Video, Youku, and Bilibili. Mango TV is out of scope until a dedicated metadata provider exists.

## Scope

- Provider detail records expose site metrics through existing `detail_fields`.
- The merged following page platform row shows only one compact activity metric per platform.
- Provider-specific source views show all extracted site metrics.
- No database schema or persisted following-record structure changes.

## Field Model

Providers should use these display labels when data is available:

- `站内评分`
- `热度`
- `评论`

Bilibili does not expose a native heat value in the current provider payload. Its merged platform row uses `播放` as the main activity metric instead of inventing a `热度` value. Bilibili source views keep the existing richer fields such as `播放`, `追番`, `点赞`, `投币`, `收藏`, `回复`, `弹幕`, and `分享`.

## UI Behavior

The merged source keeps its current metadata whitelist. The playback platform row adds at most one metric after each platform:

- iQiyi/Tencent/Youku: prefer `热度`
- Bilibili: prefer `播放`
- If the metric is missing, show only the platform link/name

When the user switches to a provider source tab, the detail text includes all scalar `detail_fields`, so `站内评分`, `热度`, and `评论` appear there when supplied by the provider.

## Data Flow

Provider detail extraction remains the source of truth. `following_metadata` derives platform entries from each provider record and attaches the compact metric to the entry used by `FollowingDetailPage`.

To keep compatibility, this should either extend `FollowingPlaybackPlatformEntry` with a defaulted display field or derive the metric while rendering from already-available source snapshots. The implementation should choose the smaller local change after checking the existing tests.

## Testing

Add or update tests for:

- iQiyi provider extracts site score, heat, and comments when present.
- Tencent provider extracts site score, heat, and comments when present.
- Youku provider extracts site score, heat, and comments when present.
- Bilibili keeps existing activity fields and the merged platform row uses `播放`.
- Following detail UI shows only the compact metric in the merged platform row and full fields in provider source views.
