# Metadata Source Site Penalty Design

## Goal

Adjust metadata scraping so Tencent and iQiyi search results that come from non-native sites are less likely to win the automatic match, and stop showing source-site rows in the detail fields UI.

## Scope

- Tencent metadata search: lower the score of results whose matched site is not `腾讯视频`.
- iQiyi metadata search: lower the score of results whose `siteName` is not `爱奇艺`.
- Tencent and iQiyi metadata detail records: do not emit a `来源站点` detail field.

## Non-Goals

- Hiding or deleting third-party results from manual scrape selection.
- Changing the global title-similarity algorithm for all providers.
- Adding any new persisted metadata fields.

## Design

### Search scoring

Keep the existing `score_match(...)` title and year logic as the base score. Apply the native-site penalty inside the provider search normalization path so only Tencent and iQiyi metadata providers are affected.

For iQiyi:

- read `siteName` from the search payload
- if it is non-empty and not equal to `爱奇艺`, subtract a fixed penalty from the final candidate score

For Tencent:

- read the matched source site from the normalized payload
- if it is non-empty and not equal to `腾讯视频`, subtract a fixed penalty from the final candidate score

This keeps third-party results available, but makes a true native-site hit outrank an otherwise similar third-party hit.

### Detail fields

`IqiyiMetadataProvider.get_detail(...)` and `TencentMetadataProvider.get_detail(...)` should stop appending `{"label": "来源站点", ...}` into `MetadataRecord.detail_fields`.

The rest of each provider's detail extraction remains unchanged.

## Data Flow

1. Provider `search(...)` builds `MetadataMatch` items from remote payloads.
2. Provider-specific native-site checks adjust each match score before sorting.
3. `MetadataHydrator` still picks the highest confident match and requests detail as before.
4. Provider `get_detail(...)` returns `MetadataRecord` without `来源站点`.
5. Existing metadata merge and player detail rendering naturally stop showing that row because no provider emits it anymore.

## Risks

- Penalty too small: third-party results may still win exact-title ties.
- Penalty too large: a valid third-party fallback may drop below the confident-match threshold.

The implementation should therefore use focused tests that compare native and third-party candidates with otherwise similar titles, instead of changing the global threshold.

## Testing

- Add iQiyi provider tests showing native `爱奇艺` results outrank non-native `siteName` results with similar titles.
- Add Tencent provider tests showing native `腾讯视频` results outrank non-native `showName` results with similar titles.
- Add detail tests for both providers asserting `来源站点` is absent from returned `detail_fields`.
