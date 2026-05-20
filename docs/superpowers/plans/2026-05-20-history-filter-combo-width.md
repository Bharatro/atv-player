# History Filter Combo Width Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the playback-history page source and time filter comboboxes readable by reserving enough width for their selected text.

**Architecture:** Make a narrowly scoped UI change inside `HistoryPage` by configuring the two filter comboboxes with the same content-length-aware sizing strategy already used by compact readable controls elsewhere in the app. Lock the behavior with a focused UI test so the bug does not regress.

**Tech Stack:** Python, PySide6, pytest

---

## File Map

- `src/atv_player/ui/history_page.py`
  Configures the playback-history source and time filter combobox sizing behavior.
- `tests/test_browse_page_ui.py`
  Verifies the history-page filter comboboxes use readable content-length-aware sizing.

### Task 1: Lock The Desired Combobox Sizing

**Files:**
- Modify: `tests/test_browse_page_ui.py`
- Test: `tests/test_browse_page_ui.py`

- [ ] **Step 1: Write the failing UI test**

Add a history-page test that asserts `source_combo` and `time_combo` use `QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon` and minimum content lengths sized for their current labels.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_browse_page_ui.py::test_history_page_filter_combos_reserve_readable_text_width -q
```

Expected: FAIL because `HistoryPage` does not yet configure these combobox sizing properties.

### Task 2: Implement The Minimal UI Fix

**Files:**
- Modify: `src/atv_player/ui/history_page.py`
- Test: `tests/test_browse_page_ui.py`

- [ ] **Step 1: Configure the two filter comboboxes**

Set both history-page filter comboboxes to `AdjustToMinimumContentsLengthWithIcon`, give the source filter a larger minimum content length than the time filter, and keep the rest of the page layout unchanged.

- [ ] **Step 2: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_browse_page_ui.py::test_history_page_filter_combos_reserve_readable_text_width -q
```

Expected: PASS.

- [ ] **Step 3: Run the broader history-page UI slice**

Run:

```bash
uv run pytest tests/test_browse_page_ui.py -k "history_page" -q
```

Expected: PASS with no regressions in playback-history page UI behavior.
