# Universal Media Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable detail page for `环球片单`, `大家在看`, and related recommendation cards.

**Architecture:** Add a focused `MediaDetailController` that resolves TMDB-backed identities into a display model, plus a `MediaDetailPage` that renders that model and emits actions. `MainWindow` owns the hidden page, wires list/recommendation clicks into it, and handles search/follow/refresh actions.

**Tech Stack:** Python, PySide6, existing TMDB client, existing `FollowingController.add_candidate`, pytest/pytest-qt.

---

### Task 1: Detail Controller Model

**Files:**
- Create: `src/atv_player/controllers/media_detail_controller.py`
- Test: `tests/test_media_detail_controller.py`

- [ ] **Step 1: Write failing tests for TMDB detail mapping**

Create tests that instantiate a fake TMDB client with `get_tv_detail_with_season`, `get_tv_season_detail`, and `get_recommendations`, then assert the controller maps title, episodes, cast, crew, and related recommendations.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_media_detail_controller.py -v`

Expected: import failure because `MediaDetailController` does not exist.

- [ ] **Step 3: Implement dataclasses and controller**

Create dataclasses for `MediaDetailIdentity`, `MediaDetailEpisode`, `MediaDetailPerson`, `MediaDetailRecommendation`, and `MediaDetailView`. Implement `load_from_vod`, `load_from_heat`, `load_from_identity`, `refresh`, `candidate_for_following`, and `search_title`.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_media_detail_controller.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add universal media detail controller`

### Task 2: Detail Page UI

**Files:**
- Create: `src/atv_player/ui/media_detail_page.py`
- Test: `tests/test_media_detail_page_ui.py`

- [ ] **Step 1: Write failing UI tests**

Test that `MediaDetailPage.load_view` renders metadata, actions, episodes, cast/crew, and related cards. Test that action buttons emit `search_play_requested`, `add_following_requested`, `refresh_metadata_requested`, and related cards emit `related_open_requested`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_media_detail_page_ui.py -v`

Expected: import failure because the page does not exist.

- [ ] **Step 3: Implement the page**

Use PySide6 widgets and existing theme conventions. Keep it independent from `FollowingDetailPage` models, but mirror its structure: top metadata, action row, episode section, people section, recommendations section.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_media_detail_page_ui.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add universal media detail page`

### Task 3: Main Window Wiring

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing main window tests**

Add tests proving `环球片单` card clicks open `media_detail_page`, `大家在看` clicks open the same page, search play starts global search, add following calls the following controller with a TMDB candidate, refresh reloads current detail, and related clicks recurse.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest tests/test_main_window_ui.py -k "media_detail or heat_recommendations" -v`

Expected: failures because `MainWindow` does not yet expose or wire `media_detail_page`.

- [ ] **Step 3: Wire the page**

Import and instantiate `MediaDetailController` and `MediaDetailPage`, add the page to the hidden stack, connect `global_catalog_page.item_open_requested`, heat recommendation clicks, and page action signals. Pass a controller from `app.py` using the configured TMDB key.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "media_detail or heat_recommendations" -v`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: wire universal media detail entries`

### Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run full focused suite**

Run: `uv run pytest tests/test_media_detail_controller.py tests/test_media_detail_page_ui.py tests/test_main_window_ui.py tests/test_global_catalog_controller.py -v`

Expected: all tests pass.

- [ ] **Step 2: Check worktree**

Run: `git status --short`

Expected: only intentional changes or the known unrelated `main_window.py` user change if still present.
