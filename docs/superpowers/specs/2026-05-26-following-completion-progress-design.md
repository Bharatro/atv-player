# 我的追更完结判定与自动进度更新 Design

## Summary

Refine `我的追更` in two places:

1. add a single, explicit completion-state rule for followed series
2. automatically advance the followed episode when the user has meaningfully started the currently playing episode

The completion rule is intentionally optimistic rather than conservative. If metadata does not show a clear future episode signal, the series is treated as `已完结`. Future signals include both normal episodes and specials such as `番外 / SP / OAD / 特别篇`.

The progress rule is intentionally stricter than the current playback bridge. A followed item should advance only after the current playback reaches 20% of that episode, and the episode number should come from the episode title when possible instead of assuming `playlist index + 1`.

## Goals

- Give `我的追更` one stable completion-status rule shared by update logic and UI.
- Treat possible future specials as enough reason to keep a series `未完结`.
- Treat missing future metadata as `已完结`, matching the user-approved optimistic rule.
- Advance following progress automatically during playback once the current episode reaches 20%.
- Prefer title-derived episode numbers over playlist position when they disagree.
- Allow specials to advance progress instead of being excluded from mainline tracking.
- Keep the logic centralized in the following domain rather than spreading it across UI widgets.

## Non-Goals

- Do not build a separate “unknown” completion state.
- Do not add a second persistence system for playback checkpoints.
- Do not block playback or metadata refresh when episode parsing is weak.
- Do not redesign the following page or detail page UI in this iteration.
- Do not attempt provider-specific heuristics beyond existing metadata fields and current episode-title parsing helpers.

## User-Approved Rules

- Completion state has only two outcomes for this feature: `已完结` and `未完结`.
- If metadata does not clearly indicate future content, treat the title as `已完结`.
- If future content exists, including specials or extras, treat the title as `未完结`.
- Playback should advance following progress only after the current item reaches 20% watched.
- Episode-number resolution should prefer title parsing over playlist index.
- Specials may advance following progress; they are not filtered out of progress updates.

## Current Problems

The current following implementation already tracks:

- `latest_episode`
- `total_episodes`
- typed `next_episode`
- playback progress callbacks from the player

But two pieces are still implicit.

First, there is no canonical completion-state resolver. The code can determine “latest aired episode” and “next scheduled episode”, but there is no single rule that says whether a followed title should be considered complete.

Second, the player-to-following bridge currently advances progress using `max(record.current_episode, current_index + 1)`. That is safe for simple playlists, but it is wrong for sources whose visible item order differs from the real episode number encoded in the title.

## Recommended Approach

Add two small, explicit rule layers inside the following domain:

1. a completion-state resolver for followed titles
2. a playback-progress resolver for current player items

The completion-state resolver should be pure and deterministic. It should consume existing following snapshot/record fields and return a symbolic state plus an internal reason that tests can assert against. UI layers should render the returned state instead of re-deriving it.

The playback-progress resolver should take the current `PlayItem`, the playlist, and the playback progress, then decide:

- the best episode number to use
- the best season number fallback
- whether the 20% watched threshold has been reached
- whether the resolved progress should be allowed to advance the stored following record

This keeps both decisions centralized and testable without introducing unnecessary new storage.

## Completion-State Design

### Symbolic State

Add a small symbolic state in the following domain, for example:

- `completed`
- `ongoing`

The UI can map these to `已完结` and `未完结`.

### Resolver Inputs

The resolver should work from existing fields only:

- `FollowingRecord.latest_episode`
- `FollowingDetailSnapshot.episodes`
- `FollowingDetailSnapshot.next_episode`
- episode `air_date`
- episode `is_special`
- current Beijing date

No new network request is required.

### Resolver Rules

Evaluate in this order:

1. If `snapshot.next_episode` exists and has a positive episode number, return `ongoing`.
2. Else, if any episode in `snapshot.episodes` has a future `air_date`, return `ongoing`.
3. Else, return `completed`.

Important consequences:

- A future special counts as future content and keeps the title `未完结`.
- If metadata has no future signal at all, the title becomes `已完结` even though a provider may later add a special or extra.
- This is intentionally not a conservative rule.

### Where It Runs

The resolver should live in the following domain, ideally near other progress/status helpers in `src/atv_player/following_models.py`.

`FollowingUpdateService` should call it after metadata refresh so the same rule drives:

- following page badges/text
- detail-page status display if needed later
- any future reminder or filter logic

## Playback Progress Update Design

### Resolver Inputs

The playback resolver should use:

- current `PlayItem`
- full playlist
- `position_seconds`
- `duration_seconds`
- existing episode-title inference helpers already used by the player/following code

### Episode Resolution Order

Resolve the target episode in this order:

1. parse a real episode number from the current item title
2. if parsing fails, fall back to playlist-position-based numbering

This preserves the user-approved rule that visible episode metadata beats raw list order.

### Threshold Rule

Only advance following progress once:

- `duration_seconds > 0`
- `position_seconds / duration_seconds >= 0.2`

If the threshold is not met, the player may continue reporting ordinary playback state elsewhere, but following progress must not advance.

### Advancement Rule

Once the threshold is met, the resolved season/episode can update the following record only if it moves progress forward. The bridge must not overwrite a higher stored episode with an older one.

This means:

- replaying an earlier episode does not roll back `current_episode`
- reopening the same episode does not create unnecessary writes
- specials can still advance progress if they resolve to a higher episode number

## Architecture And Code Boundaries

### `src/atv_player/following_models.py`

Add:

- a completion-status enum/symbol set
- a pure completion-state resolver
- a small playback-threshold / progress-resolution helper, or a compact adjacent helper if the file would otherwise become noisy

This is the preferred location because it already owns following-domain comparison helpers such as season-aware progress resolution.

### `src/atv_player/following_update_service.py`

After metadata refresh:

- reuse the completion-state resolver
- keep all future-episode logic in one place instead of reconstructing it in UI

The service remains responsible for metadata-derived state, not rendering.

### `src/atv_player/ui/main_window.py`

Adjust `_report_player_item_following_progress()` so it no longer assumes `current_index + 1` is the best answer. It should:

- locate the followed record as today
- ask the shared resolver for the target episode/season and threshold result
- call `FollowingController.record_playback_progress()` only when the threshold is satisfied and the resolved progress is valid

### `src/atv_player/controllers/following_controller.py`

Keep `record_playback_progress()` as the single write entry point for following progress updates.

If necessary, add a defensive “forward-only” check here or in the repository layer so stale playback reports cannot move progress backward.

### `src/atv_player/following_repository.py`

No new table is required for this feature by default.

If completion state needs to be shown frequently, it can remain derived at the controller/view-model layer unless later performance evidence justifies persistence.

## Error Handling

- If title parsing fails, fall back to playlist index.
- If `duration_seconds <= 0`, treat the threshold as not met and skip following advancement.
- If a record cannot be matched from the current player item, do nothing.
- If metadata contains malformed future-episode dates, ignore those rows and continue resolving from valid rows.
- If no snapshot exists yet, completion state should fall back to `已完结` under the approved optimistic rule unless a `next_episode` signal is present.

## Testing

Add focused tests for:

- `next_episode` present => `未完结`
- no `next_episode` and no future episode rows => `已完结`
- future-dated special episode => `未完结`
- playback below 20% => no following progress update
- playback at or above 20% => following progress update occurs
- title-derived episode number overrides playlist index
- fallback to playlist index when title parsing fails
- specials can advance progress
- earlier playback reports do not roll back a higher stored episode

## Rollout Notes

This feature should be implemented as a behavior refinement of the existing following system, not as a schema-heavy redesign. The key requirement is consistency: the same completion and playback rules must be shared by update checks, controller logic, and the player bridge so that the user sees one coherent notion of “完结” and “看到第几集”.
