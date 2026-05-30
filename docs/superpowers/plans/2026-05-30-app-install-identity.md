# App Install Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one immutable installation identifier in `app.db` for future analytics and telemetry.

**Architecture:** Add a focused `AppIdentity` model and an `app_identity` single-row table managed by `SettingsRepository`. Startup will call `ensure_app_identity()` once; the method returns the stored value when present and inserts a generated `UUID.hash` only when missing.

**Tech Stack:** Python standard library (`uuid`, `hashlib`, `platform`, `sys`), SQLite, pytest.

---

### Task 1: Storage Model And Persistence

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add tests that call `SettingsRepository.ensure_app_identity()` and assert the returned ID matches `UUID.hash`, is stable across calls, persists across repository instances, and preserves an existing row.

- [ ] **Step 2: Run the targeted tests to verify RED**

Run: `uv run pytest tests/test_storage.py -k "app_identity" -q`
Expected: FAIL because `SettingsRepository` has no `ensure_app_identity` method yet.

- [ ] **Step 3: Implement the model and repository method**

Add `AppIdentity` to `models.py`. In `storage.py`, create `app_identity`, generate IDs using UUID4 plus SHA-256 feature hash, and insert with `ON CONFLICT(id) DO NOTHING` so existing IDs remain unchanged.

- [ ] **Step 4: Run the targeted tests to verify GREEN**

Run: `uv run pytest tests/test_storage.py -k "app_identity" -q`
Expected: PASS.

### Task 2: Startup Initialization

**Files:**
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing startup test**

Add or extend an app startup test with a fake repository that records `ensure_app_identity()` calls. Assert `build_application()` ensures the app identity once after repository creation.

- [ ] **Step 2: Run the targeted test to verify RED**

Run the specific app test with `uv run pytest tests/test_app.py::<test_name> -q`.
Expected: FAIL because startup does not call `ensure_app_identity()` yet.

- [ ] **Step 3: Call identity initialization during startup**

In `build_application()`, call `repo.ensure_app_identity()` after `repo.load_config()` and before services that may later need telemetry context.

- [ ] **Step 4: Run targeted app test and storage tests**

Run: `uv run pytest tests/test_storage.py -k "app_identity" -q` and the targeted app test.
Expected: PASS.

### Task 3: Verification

**Files:**
- No additional production files.

- [ ] **Step 1: Run focused persistence test file**

Run: `uv run pytest tests/test_storage.py -q`
Expected: PASS.

- [ ] **Step 2: Inspect diff**

Run: `git diff -- src/atv_player/models.py src/atv_player/storage.py src/atv_player/app.py tests/test_storage.py tests/test_app.py`
Expected: Only scoped identity persistence and startup initialization changes.
