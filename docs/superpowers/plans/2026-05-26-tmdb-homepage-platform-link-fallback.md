# TMDB Homepage Platform Link Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TMDB detail records produce playback platform links by preferring explicit watch-provider URLs and falling back to a homepage URL only for the single matching platform.

**Architecture:** Keep the change in the TMDB provider layer by normalizing TMDB `watch/providers`, `homepage`, and `networks` into the existing `watch_providers` detail field consumed by following metadata. Existing following UI and bundle-merging code stays unchanged.

**Tech Stack:** Python, pytest

---

### Task 1: Add failing TMDB provider regression tests

**Files:**
- Modify: `tests/test_metadata_tmdb_provider.py`
- Test: `tests/test_metadata_tmdb_provider.py`

- [ ] **Step 1: Write failing tests for homepage fallback and multi-platform handling**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py -k "homepage_fallback or watch_provider_url_over_homepage or does_not_copy_homepage_to_other_networks" -q`
Expected: FAIL before implementation because TMDB provider does not yet emit normalized `watch_providers` entries.

### Task 2: Implement TMDB playback platform normalization

**Files:**
- Modify: `src/atv_player/metadata/providers/tmdb.py`
- Test: `tests/test_metadata_tmdb_provider.py`

- [ ] **Step 1: Add helper functions to map TMDB network names and homepage domains to known platform keys**
- [ ] **Step 2: Build normalized `watch_providers` detail entries from TMDB payload data**
- [ ] **Step 3: Preserve explicit TMDB watch-provider URLs over homepage fallback URLs**
- [ ] **Step 4: Append normalized `watch_providers` to TMDB detail fields in `get_detail` and `get_detail_full`**

- [ ] **Step 5: Run targeted provider tests**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py -k "homepage_fallback or watch_provider_url_over_homepage or does_not_copy_homepage_to_other_networks" -q`
Expected: PASS

### Task 3: Run focused regressions

**Files:**
- Modify: `src/atv_player/metadata/providers/tmdb.py`
- Modify: `tests/test_metadata_tmdb_provider.py`
- Test: `tests/test_following_metadata.py`
- Test: `tests/test_metadata_tmdb_provider.py`

- [ ] **Step 1: Run focused regression suite**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py tests/test_following_metadata.py -q`
Expected: PASS with zero failures
