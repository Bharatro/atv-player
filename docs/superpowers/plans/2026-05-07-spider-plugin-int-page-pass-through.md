# Spider Plugin Int Page Pass-Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pass plugin pagination values into `categoryContent()` and `searchContent()` as integers instead of converting them to strings.

**Architecture:** Keep UI and controller public APIs unchanged at `page: int`, and remove the string conversion only at the plugin-controller boundary. Update plugin test doubles and assertions so the expected page values match the new integer contract.

**Tech Stack:** Python, pytest

---

### Task 1: Add failing regression coverage for integer page pass-through

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Change category and search assertions to expect integer page values**

```python
assert spider.category_calls == [("movie", 2, False, {"sc": "6"})]
assert spider.search_calls == [("庆余年", False, 1, "tv")]
assert spider.search_calls == [("庆余年", False, 1, "")]
```

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `pytest tests/test_spider_plugin_controller.py::test_controller_passes_selected_filters_into_category_content_extend tests/test_spider_plugin_controller.py::test_controller_passes_selected_category_into_search_content tests/test_spider_plugin_controller.py::test_controller_search_normalizes_home_category_to_empty_string -q`
Expected: FAIL because the controller still passes string page values into plugin methods

### Task 2: Remove string conversion in plugin controller

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Pass integer page into `categoryContent()`**

```python
payload = self._spider.categoryContent(category_id, page, False, dict(filters or {})) or {}
```

- [ ] **Step 2: Pass integer page into `searchContent()`**

```python
payload = self._spider.searchContent(keyword, False, page, category) or {}
```

- [ ] **Step 3: Align plugin test doubles with integer defaults**

```python
def searchContent(self, key, quick, pg=1, category=""):
    ...
```

- [ ] **Step 4: Run targeted tests to verify GREEN**

Run: `pytest tests/test_spider_plugin_controller.py::test_controller_passes_selected_filters_into_category_content_extend tests/test_spider_plugin_controller.py::test_controller_passes_selected_category_into_search_content tests/test_spider_plugin_controller.py::test_controller_search_normalizes_home_category_to_empty_string -q`
Expected: PASS

### Task 3: Run focused regression verification

**Files:**
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Run focused plugin suites**

Run: `pytest tests/test_spider_plugin_controller.py tests/test_poster_grid_page_ui.py -q`
Expected: PASS
