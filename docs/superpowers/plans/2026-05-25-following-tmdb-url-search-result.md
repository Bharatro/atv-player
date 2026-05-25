# Following TMDB URL Search Result Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user pastes a TMDB URL into the add-following dialog, resolve the URL to TMDB detail data and show a filled search result row instead of a blank placeholder.

**Architecture:** Keep URL parsing in `following_metadata.py`, keep orchestration in `FollowingController`, and reuse `MetadataScrapeService.detail_record()` to hydrate the candidate before the dialog renders it. The dialog stays presentation-only and keeps the existing single-line text row layout.

**Tech Stack:** Python, PySide6, pytest

---

### Task 1: Cover TMDB URL candidate hydration in the controller

**Files:**
- Modify: `tests/test_following_controller.py`
- Modify: `src/atv_player/controllers/following_controller.py`

- [ ] **Step 1: Write the failing test**

```python
def test_following_controller_hydrates_tmdb_url_candidate_for_search_results(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_hydrates_tmdb_url_candidate_for_search_results -q`
Expected: FAIL because `search_media()` currently returns an empty-title placeholder candidate for TMDB URLs.

- [ ] **Step 3: Write minimal implementation**

```python
def search_media(self, keyword: str):
    url_candidate = self.candidate_from_url(keyword)
    if url_candidate is not None:
        hydrated_candidate = self._hydrate_url_candidate(url_candidate)
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_hydrates_tmdb_url_candidate_for_search_results -q`
Expected: PASS

### Task 2: Cover rendered dialog text for hydrated TMDB URL results

**Files:**
- Modify: `tests/test_following_search_dialog_ui.py`
- Modify: `src/atv_player/ui/following_search_dialog.py`

- [ ] **Step 1: Write the failing test**

```python
def test_following_search_dialog_renders_tmdb_url_candidate_details(qtbot) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_details -q`
Expected: FAIL because the TMDB URL candidate currently lacks detail fields to render.

- [ ] **Step 3: Write minimal implementation**

```python
def _candidate_text(self, candidate) -> str:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_details -q`
Expected: PASS

### Task 3: Verify the focused regression set

**Files:**
- Test: `tests/test_following_controller.py`
- Test: `tests/test_following_search_dialog_ui.py`

- [ ] **Step 1: Run the focused regression tests**

Run: `uv run pytest tests/test_following_controller.py::test_following_controller_hydrates_tmdb_url_candidate_for_search_results tests/test_following_search_dialog_ui.py::test_following_search_dialog_renders_tmdb_url_candidate_details tests/test_following_search_dialog_ui.py::test_following_search_dialog_matches_scrape_dialog_shell_and_adds_selection tests/test_following_search_dialog_ui.py::test_following_search_dialog_passes_manual_current_episode_when_supported -q`
Expected: PASS
