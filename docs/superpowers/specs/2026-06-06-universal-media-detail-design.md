# Universal Media Detail Design

## Goal

Add a reusable media detail page for recommendation/list cards that are not yet tracked. `环球片单` cards and `大家在看` cards should open this page instead of only starting a text search.

## Scope

The page is a hidden navigation-stack destination and must use the same shared detail layout component as the existing追更详情 view. It is not backed by a `FollowingRecord`, but layout, section order, spacing, object names, and styling are shared with追更详情. The only intended differences are the available buttons and the business functions those buttons call.

## Identity And Data

TMDB is the canonical identity for the first version. `环球片单` already emits `VodItem.vod_id` values like `tmdb:tv:1399` and `tmdb:movie:550`; these load details directly. `大家在看` recommendations load from `external_ids["tmdb"]`, `media_key` values like `tmdb:tv:1399` or `tmdb:1399`, and the recommendation title as a fallback.

The controller fetches TMDB details, season details for TV, cast/crew from credits or aggregate credits, and TMDB recommendations. If a direct id is unavailable, it searches TMDB by title/year/media type and opens the first match. If no match is found, the UI keeps the user on the current screen and shows an error.

## Page Behavior

The shared detail scaffold renders:

- Top metadata: title, year/date, genre labels, rating, overview, and the same right-side poster carousel panel used by追更详情.
- Actions: `搜索播放` starts global search for the title; `加入追更` calls the following controller with a TMDB metadata candidate; `更新元数据` reloads the detail from TMDB.
- Episode section: the same `FollowingEpisodeBrowser` component used by追更详情. TV seasons and episodes come from TMDB season details. Movies hide this section.
- Cast/crew: the same person-card component used by追更详情, populated from TMDB cast/crew.
- Related recommendations: the same related-card component used by追更详情, clickable to recursively open the same universal detail page.

## Main Window Integration

`MainWindow` owns one `MediaDetailPage` and one `MediaDetailController`. The page is added to the navigation stack but not to visible built-in tab definitions. `环球片单` uses `PosterGridPage.item_open_requested`; `大家在看` dialog clicks use the same `open_media_detail_*` path. Related cards emit a media identity back to `MainWindow`.

`FollowingDetailPage` and `MediaDetailPage` both use `MediaDetailScaffold`. This keeps the two pages visually identical and prevents drift. Each page supplies its own action row:追更详情 keeps its full action set, while the universal detail page supplies only `返回`, `搜索播放`, `加入追更`, and `更新元数据`.

## Error Handling

Loading failures render a concise status on the page or show the existing main-window error message when no identity can be resolved. `加入追更` uses direct TMDB candidate data when available; if the following controller cannot accept it, the action falls back to global search so the user can choose a playable result.

## Testing

Focused UI tests cover:

- A `环球片单` TMDB card opens the universal detail page.
- A `大家在看` item opens the same page.
- The page renders with the shared detail scaffold, shared episode browser, shared cast cards, and shared related recommendation cards.
- Existing追更详情 layout tests continue to pass while asserting the same scaffold is in use.
- Actions emit search, add-following, and refresh requests.
- Related recommendation clicks recursively request the same detail destination.
