# Following Detail Merged Metadata Filter Design

## Scope

This change refines the `FollowingDetailPage` merged metadata view only.

Goals:

- Rename the merged-source button from `合并` to `媒体信息`.
- Reduce merged-view noise by showing only general media metadata.
- Eliminate duplicated update information in the merged view.

Non-goals:

- No change to provider raw views such as `TMDB`, `B站`, or `Bangumi`.
- No change to rating strip behavior.
- No change to playback platform link behavior.

## UX Behavior

The merged view becomes a curated media-information view rather than a full union of all provider fields.

Merged view keeps only these metadata labels:

- `类型`
- `年代`
- `地区`
- `语言`
- `导演`
- `演员`
- `别名`
- `豆瓣ID`
- `IMDb ID`
- `TMDB ID`

Merged view hides provider/platform operational fields, including:

- `最近更新`
- `更新时间`
- `更新状态`
- `开播`
- `播放`
- `追番`
- `点赞`
- `投币`
- `收藏`
- `回复`
- `弹幕`
- `分享`
- `播放链接`

Playback platform rows remain visible in merged view. Update timing and latest-episode information should appear there only, not in the metadata text block.

Provider raw views continue to show each provider's complete metadata fields without this merged-view filtering.

## Implementation Notes

- Keep the underlying merged snapshot data intact; apply filtering at merged-view formatting time.
- Rename only the UI label for the merged source key. The internal source key remains `merged`.
- Reuse the existing skipped-label behavior for detail formatting, but split merged-view formatting into an explicit whitelist path so future provider additions do not leak new noisy fields into merged view.

## Testing

- Add a UI regression test asserting the merged source button text is `媒体信息`.
- Add a UI regression test asserting merged overview text excludes provider operational fields like `最近更新` and `播放`.
- Keep provider raw view coverage to ensure switching to a provider view still shows provider-specific fields.
