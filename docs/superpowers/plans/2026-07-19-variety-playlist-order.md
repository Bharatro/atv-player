# Variety Playlist Order Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep variety-show playlists in backend order while retaining episode title enhancement, without changing non-variety sorting.

**Architecture:** Reuse `is_likely_variety_title` for filename evidence and add a small playlist-level predicate in the app enhancer. Enhanced playlists for variety content are restored to the original identity order before being returned or cached; the title cache version is bumped to invalidate prior reordered results.

**Tech Stack:** Python 3.12, pytest, existing `PlayItem`/`VodItem` models, PySide6 application wiring.

---

### Task 1: Add the failing regression test

**Files:**
- Modify: `tests/test_app.py` near the episode title enhancer tests

- [ ] **Step 1: Add a test with date/issue filenames in backend order**

Create a fake TMDB client returning two episode titles, build a `telegram_channel` enhancer, and pass a playlist ordered as `2026-05-20 序章`, `2026-05-26 第1期`, `2026-06-02 第2期`, `2026-05-27 第1期上`. Assert the returned original titles stay in that exact order while display titles are populated.

- [ ] **Step 2: Run the test and verify it fails**

Run `uv run pytest tests/test_app.py::test_app_coordinator_episode_title_enhancer_preserves_variety_playlist_order -q`.

Expected: FAIL because the current finalizer sorts the playlist into issue-number order.

### Task 2: Implement variety detection and order restoration

**Files:**
- Modify: `src/atv_player/app.py` near `_build_episode_title_enhancer_factory`

- [ ] **Step 1: Add the minimal playlist-level variety predicate**

Treat metadata containing `综艺`, `真人秀`, `脱口秀`, or `variety` as variety. Otherwise count playlist items for which `is_likely_variety_title` is true and require at least two matches representing at least half of the playlist.

- [ ] **Step 2: Restore variety results by original identity**

Capture the original playlist before provider mapping. When finalizing a variety playlist, reorder the enhanced items using the original playlist's stable identity key, then reset indexes. Keep the existing episode-number sort path for non-variety playlists.

- [ ] **Step 3: Bump the title playlist cache version**

Change `_EPISODE_TITLE_PLAYLIST_CACHE_VERSION` from `v3` to `v4` so cached playlists created with the old reorder behavior are ignored.

- [ ] **Step 4: Run the new test and focused regressions**

Run `uv run pytest tests/test_app.py::test_app_coordinator_episode_title_enhancer_preserves_variety_playlist_order tests/test_app.py -k 'episode_title_enhancer' -q`.

Expected: the new test and all existing episode-title tests pass, including shuffled non-variety playlists that still sort.

### Task 3: Verify the focused feature surface

**Files:**
- No additional production files

- [ ] **Step 1: Run metadata and utility regressions**

Run `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_danmaku_utils.py tests/test_app.py -k 'episode_title_enhancer or variety' -q`.

- [ ] **Step 2: Check formatting and diff scope**

Run `git diff --check` and inspect `git diff --stat`; only the app implementation, its regression test, and the already committed plan/spec should be present.

- [ ] **Step 3: Commit the implementation**

Run `git add src/atv_player/app.py tests/test_app.py` followed by `git commit -m "fix: preserve variety playlist order"`.
