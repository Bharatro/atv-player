# Universal Media Detail Design

## Goal

Add a reusable media detail page for recommendation/list cards that are not yet tracked. `环球片单` cards and `大家在看` cards should open this page instead of only starting a text search.

## Scope

The page is a hidden navigation-stack destination, similar to the existing追更详情 view, but it is not backed by a `FollowingRecord`. It must show media metadata, episodes where available, cast/crew, related recommendations, and exactly three primary actions: `搜索播放`, `加入追更`, and `更新元数据`.

## Identity And Data

TMDB is the canonical identity for the first version. `环球片单` already emits `VodItem.vod_id` values like `tmdb:tv:1399` and `tmdb:movie:550`; these load details directly. `大家在看` recommendations load from `external_ids["tmdb"]`, `media_key` values like `tmdb:tv:1399` or `tmdb:1399`, and the recommendation title as a fallback.

The controller fetches TMDB details, season details for TV, cast/crew from credits or aggregate credits, and TMDB recommendations. If a direct id is unavailable, it searches TMDB by title/year/media type and opens the first match. If no match is found, the UI keeps the user on the current screen and shows an error.

## Page Behavior

The page renders:

- Top metadata: title, year/date, genre labels, rating, overview, poster/backdrop.
- Actions: `搜索播放` starts global search for the title; `加入追更` calls the following controller with a TMDB metadata candidate; `更新元数据` reloads the detail from TMDB.
- Episode section: TV seasons and episodes from TMDB season details. Movies show an empty/hidden episode section.
- Cast/crew: a horizontal list of named people with roles/jobs and profile images when available.
- Related recommendations: clickable cards that recursively open the same universal detail page.

## Main Window Integration

`MainWindow` owns one `MediaDetailPage` and one `MediaDetailController`. The page is added to the navigation stack but not to visible built-in tab definitions. `环球片单` uses `PosterGridPage.item_open_requested`; `大家在看` dialog clicks use the same `open_media_detail_*` path. Related cards emit a media identity back to `MainWindow`.

## Error Handling

Loading failures render a concise status on the page or show the existing main-window error message when no identity can be resolved. `加入追更` uses direct TMDB candidate data when available; if the following controller cannot accept it, the action falls back to global search so the user can choose a playable result.

## Testing

Focused UI tests cover:

- A `环球片单` TMDB card opens the universal detail page.
- A `大家在看` item opens the same page.
- The page renders episode, cast/crew, and related recommendation sections.
- Actions emit search, add-following, and refresh requests.
- Related recommendation clicks recursively request the same detail destination.
