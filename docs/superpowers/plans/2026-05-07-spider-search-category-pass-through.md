# Spider Search Category Pass-Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pass the currently selected plugin category into spider `searchContent()` as the last argument, converting synthetic `home` to an empty string.

**Architecture:** Keep the normalization rule inside `SpiderPluginController` so UI code only forwards the selected category id. Extend the shared search method signature with an optional `category_id` parameter so poster-grid search can pass context without breaking non-plugin controllers.

**Tech Stack:** Python, pytest, PySide6

---

### Task 1: Add regression coverage for category-aware plugin search

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `tests/test_poster_grid_page_ui.py`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Write the failing controller test**

```python
def test_controller_passes_selected_category_into_search_content() -> None:
    spider = SearchCategorySpider()
    controller = SpiderPluginController(spider, plugin_name="分类搜索插件", search_enabled=True)

    items, total = controller.search_items("庆余年", 1, category_id="tv")

    assert total == 1
    assert items[0].vod_name == "庆余年"
    assert spider.search_calls == [("庆余年", False, "1", "tv")]
```

- [ ] **Step 2: Write the failing UI test**

```python
def test_poster_grid_page_search_passes_selected_category_to_controller(qtbot) -> None:
    controller = SearchableDoubanController()
    page = show_loaded_page(qtbot, PosterGridPage(controller, click_action="open", search_enabled=True))

    qtbot.waitUntil(lambda: page.selected_category_id == "suggestion")
    page.category_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: page.selected_category_id == "movie")

    page.keyword_edit.setText("黑袍纠察队")
    page.search()

    qtbot.waitUntil(lambda: controller.search_calls == [("黑袍纠察队", 1, "movie")])
```

- [ ] **Step 3: Run targeted tests to verify RED**

Run: `pytest tests/test_spider_plugin_controller.py::test_controller_passes_selected_category_into_search_content tests/test_poster_grid_page_ui.py::test_poster_grid_page_search_passes_selected_category_to_controller -q`
Expected: FAIL because current search signatures and calls do not pass `category_id`

### Task 2: Implement category pass-through with home normalization

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Modify: `src/atv_player/controllers/bilibili_controller.py`
- Modify: `src/atv_player/controllers/emby_controller.py`
- Modify: `src/atv_player/controllers/feiniu_controller.py`
- Modify: `src/atv_player/controllers/jellyfin_controller.py`
- Modify: `src/atv_player/controllers/pansou_controller.py`
- Modify: `src/atv_player/controllers/telegram_search_controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Update search method signatures with optional category**

```python
def search_items(self, keyword: str, page: int, category_id: str = "") -> tuple[list[VodItem], int]:
    ...
```

- [ ] **Step 2: Pass selected category from poster-grid search**

```python
items, total = self.controller.search_items(keyword, page, category_id=self.selected_category_id)
```

- [ ] **Step 3: Normalize `home` and call spider search with category**

```python
category = "" if category_id == "home" else str(category_id or "")
payload = self._spider.searchContent(keyword, False, str(page), category) or {}
```

- [ ] **Step 4: Add home normalization coverage**

```python
def test_controller_search_normalizes_home_category_to_empty_string() -> None:
    spider = SearchCategorySpider()
    controller = SpiderPluginController(spider, plugin_name="分类搜索插件", search_enabled=True)

    controller.search_items("庆余年", 1, category_id="home")

    assert spider.search_calls == [("庆余年", False, "1", "")]
```

- [ ] **Step 5: Run targeted tests to verify GREEN**

Run: `pytest tests/test_spider_plugin_controller.py::test_controller_passes_selected_category_into_search_content tests/test_spider_plugin_controller.py::test_controller_search_normalizes_home_category_to_empty_string tests/test_poster_grid_page_ui.py::test_poster_grid_page_search_passes_selected_category_to_controller -q`
Expected: PASS

### Task 3: Run broader regression verification

**Files:**
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Run relevant focused suites**

Run: `pytest tests/test_spider_plugin_controller.py tests/test_poster_grid_page_ui.py -q`
Expected: PASS
