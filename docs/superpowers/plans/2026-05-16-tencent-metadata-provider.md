# Tencent Metadata Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tencent metadata scrape provider that only keeps `dataType=2` video results, omits rating, and gives full exact title matches a `+0.2` score bonus.

**Architecture:** Follow the existing iQiyi metadata provider shape: a provider returns `MetadataMatch` search results and builds `MetadataRecord` details from cached raw payloads. Wire the new provider into app/provider labels and extend shared match scoring for Tencent exact matches without changing the overall hydrator sort pipeline.

**Tech Stack:** Python, `httpx`, pytest, existing metadata hydrator/scrape UI infrastructure

---

### Task 1: Add Tencent provider and scoring tests

**Files:**
- Create: `tests/test_metadata_tencent_provider.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_metadata_scrape_service.py` or add scoring coverage in the Tencent provider test file

- [ ] Step 1: Write failing tests for Tencent search parsing, detail mapping, and exact-match score bonus.
- [ ] Step 2: Run the targeted tests and verify they fail because the provider and Tencent scoring path do not exist yet.
- [ ] Step 3: Implement the minimal provider/search scoring changes to satisfy those tests.
- [ ] Step 4: Re-run the targeted tests and verify they pass.

### Task 2: Wire Tencent into metadata provider registration and labels

**Files:**
- Create: `src/atv_player/metadata/providers/tencent.py`
- Modify: `src/atv_player/metadata/providers/__init__.py`
- Modify: `src/atv_player/metadata/matching.py`
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/metadata/scrape.py`

- [ ] Step 1: Write failing tests that expect Tencent to appear in the metadata provider list and scrape labels.
- [ ] Step 2: Run those targeted tests and verify they fail for the missing Tencent integration.
- [ ] Step 3: Implement the minimal registration/label changes.
- [ ] Step 4: Re-run the targeted tests and verify they pass.

### Task 3: Verification

**Files:**
- Verify: `tests/test_metadata_tencent_provider.py`
- Verify: `tests/test_app.py`
- Verify: `tests/test_metadata_scrape_service.py`

- [ ] Step 1: Run all targeted Tencent metadata tests together.
- [ ] Step 2: Fix any regressions discovered by the combined run.
- [ ] Step 3: Re-run until the targeted suite is green.
