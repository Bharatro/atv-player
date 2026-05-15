# Variety Danmaku Search Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make variety-show danmaku searches drop trailing issue markers from provider queries while still preferring same-issue candidates when an issue marker exists.

**Architecture:** Keep the change inside the danmaku package. Add focused title helpers in `utils.py`, then update `DanmakuService.search_danmu()` to branch into a variety-specific query and ranking path without changing provider interfaces.

**Tech Stack:** Python 3.14, pytest, existing danmaku service/provider modules

---

## File Structure

- Modify: `src/atv_player/danmaku/utils.py`
  Responsibility: identify variety-style titles and strip trailing issue markers safely.
- Modify: `src/atv_player/danmaku/service.py`
  Responsibility: use the stripped variety query and rank candidates by issue match or title similarity.
- Modify: `tests/test_danmaku_utils.py`
  Responsibility: lock helper behavior for variety detection and suffix stripping.
- Modify: `tests/test_danmaku_service.py`
  Responsibility: lock the service contract for variety search queries and ranking.

### Task 1: Define Variety Helpers In Tests

**Files:**
- Modify: `tests/test_danmaku_utils.py`

- [ ] **Step 1: Write the failing helper tests**
- [ ] **Step 2: Run `uv run pytest tests/test_danmaku_utils.py -q` and confirm the new tests fail**

### Task 2: Define Variety Search Behavior In Tests

**Files:**
- Modify: `tests/test_danmaku_service.py`

- [ ] **Step 1: Write the failing service tests for stripped variety queries**
- [ ] **Step 2: Write the failing service tests for issue-match and similarity fallback ordering**
- [ ] **Step 3: Run `uv run pytest tests/test_danmaku_service.py -q` and confirm the new tests fail**

### Task 3: Implement Minimal Variety Logic

**Files:**
- Modify: `src/atv_player/danmaku/utils.py`
- Modify: `src/atv_player/danmaku/service.py`

- [ ] **Step 1: Add minimal variety-title helpers**
- [ ] **Step 2: Update `DanmakuService.search_danmu()` to use the variety query and ranking path**
- [ ] **Step 3: Re-run the targeted tests until green**

### Task 4: Verify Regression Slice

**Files:**
- Test: `tests/test_danmaku_utils.py`
- Test: `tests/test_danmaku_service.py`

- [ ] **Step 1: Run `uv run pytest tests/test_danmaku_utils.py tests/test_danmaku_service.py -q`**
- [ ] **Step 2: If green, run a broader slice `uv run pytest tests/test_danmaku_utils.py tests/test_danmaku_service.py tests/test_danmaku_mgtv_provider.py tests/test_spider_plugin_controller.py -q`**
