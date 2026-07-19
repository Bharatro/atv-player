# Search Result Drive Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add current-page drive-type filtering to search results from `电报影视`, `电报频道`, and `盘搜`.

**Architecture:** Normalize drive metadata in shared URL/type helpers and Telegram result mapping, then add an opt-in result filter to `PosterGridPage`. The page keeps backend pagination untouched while filtering only the currently loaded `VodItem` list; `MainWindow` enables the option for the three requested pages.

**Tech Stack:** Python 3.14, PySide6, pytest, pytest-qt, existing `VodItem` and `PosterGridPage` abstractions.

---

### Task 1: Add shared drive-link type normalization

**Files:**
- Modify: `src/atv_player/share_types.py`
- Modify: `src/atv_player/controllers/browse_controller.py`
- Test: `tests/test_browse_controller.py`

- [ ] **Step 1: Write failing normalization and filter tests**

Add tests that assert recognized hosts map to the existing canonical IDs and
that filtering can match a display name when only `type_name` is present:

```python
from atv_player.share_types import infer_share_type


def test_infer_share_type_uses_share_link_hostname() -> None:
    assert infer_share_type("https://pan.quark.cn/s/demo") == "5"
    assert infer_share_type("https://pan.baidu.com/s/demo") == "10"
    assert infer_share_type("https://example.test/share") == ""


def test_filter_search_results_matches_canonical_name_without_share_type() -> None:
    items = [VodItem(vod_id="1", vod_name="夸克资源", type_name="夸克")]

    assert filter_search_results(items, "5") == items
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `uv run pytest tests/test_browse_controller.py -k "infer_share_type or canonical_name_without_share_type" -v`

Expected: FAIL because `infer_share_type` is missing and the existing filter
only compares the numeric ID against `type_name`.

- [ ] **Step 3: Implement the minimal shared helper and matching rule**

In `share_types.py`, add hostname parsing with `urllib.parse.urlparse` and a
suffix-aware domain table using the existing canonical IDs:

```python
from urllib.parse import urlparse

_SHARE_TYPE_DOMAINS = {
    "10": ("baidu.com",),
    "9": ("189.cn",),
    "5": ("quark.cn",),
    "7": ("uc.cn",),
    "0": ("alipan.com", "aliyundrive.com"),
    "8": ("115.com", "115cdn.com", "anxia.com"),
    "3": ("123pan.com", "123pan.cn", "123684.com", "123865.com", "123912.com", "123592.com"),
    "2": ("xunlei.com",),
    "6": ("139.com",),
    "1": ("mypikpak.com",),
    "12": ("guangyapan.com",),
}


def infer_share_type(value: str) -> str:
    text = str(value or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return ""
    host = (urlparse(text).hostname or "").lower().rstrip(".")
    for share_type, domains in _SHARE_TYPE_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return share_type
    return ""
```

Update `filter_search_results()` to compare the selected ID, its canonical
display name from `get_share_type_name()`, and the item metadata:

```python
label = get_share_type_name(drive_type)
return [
    item for item in results
    if item.share_type == drive_type
    or (label and label in item.type_name)
]
```

- [ ] **Step 4: Run the focused tests and verify pass**

Run: `uv run pytest tests/test_browse_controller.py -k "infer_share_type or canonical_name_without_share_type or filter_search_results" -v`

Expected: PASS.

- [ ] **Step 5: Commit the shared normalization change**

```bash
git add src/atv_player/share_types.py src/atv_player/controllers/browse_controller.py tests/test_browse_controller.py
git commit -m "feat: normalize drive types for search filtering"
```

### Task 2: Normalize Telegram movie and channel search items

**Files:**
- Modify: `src/atv_player/controllers/douban_controller.py`
- Modify: `src/atv_player/controllers/telegram_search_controller.py`
- Modify: `src/atv_player/controllers/telegram_channel_controller.py`
- Test: `tests/test_telegram_search_controller.py`
- Create: `tests/test_telegram_channel_controller.py`

- [ ] **Step 1: Add failing mapping tests**

Extend the Telegram search payload test with a Quark link and assert
`share_type == "5"`. Add the same test shape for channel search. Keep a payload
that already supplies `type_name` to verify backend labels are preserved.

```python
assert items[0].share_type == "5"
```

- [ ] **Step 2: Run the controller tests and verify failure**

Run: `uv run pytest tests/test_telegram_search_controller.py tests/test_telegram_channel_controller.py -k "maps_search_payload or maps_channel_search_payload" -v`

Expected: FAIL because the generic mapper does not populate `share_type`.

- [ ] **Step 3: Add link-aware metadata mapping**

Extend `douban_controller._map_item()` to preserve payload `share_type` or
`type`, then add a small Telegram mapping helper that fills a missing value
from `vod_id` and derives `type_name` only when the backend omitted it:

```python
def _map_telegram_item(payload: dict) -> VodItem:
    item = _map_item(payload)
    item.share_type = item.share_type or infer_share_type(item.vod_id)
    item.type_name = item.type_name or get_share_type_name(item.share_type)
    return item
```

Use this helper in both `TelegramSearchController.search_items()` and
`TelegramChannelController.search_items()` and leave category mapping
unchanged except for the harmless preserved `share_type` field.

- [ ] **Step 4: Run mapping tests and the existing controller suites**

Run: `uv run pytest tests/test_telegram_search_controller.py tests/test_telegram_channel_controller.py tests/test_browse_controller.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Telegram metadata normalization**

```bash
git add src/atv_player/controllers/douban_controller.py src/atv_player/controllers/telegram_search_controller.py src/atv_player/controllers/telegram_channel_controller.py tests/test_telegram_search_controller.py tests/test_telegram_channel_controller.py
git commit -m "feat: normalize Telegram search drive metadata"
```

### Task 3: Add current-page result filtering to PosterGridPage

**Files:**
- Modify: `src/atv_player/ui/poster_grid_page.py`
- Test: `tests/test_poster_grid_page_ui.py`

- [ ] **Step 1: Add failing page tests**

Add an opt-in constructor argument `search_drive_filter_enabled=False` and
tests using `VodItem` values with `share_type` `5` and `10`. Assert the control
is hidden in category mode, appears after `show_external_results()`, filters
cards without changing the controller call count, and reapplies to a newly
loaded search page.

```python
page = PosterGridPage(
    controller,
    click_action="open",
    search_enabled=True,
    search_drive_filter_enabled=True,
)
page.show_external_results(items=items, total=61, page=1)
page.search_drive_filter_combo.setCurrentIndex(
    page.search_drive_filter_combo.findData("5")
)
assert [button.text() for button in page.card_buttons] == ["夸克资源"]
assert controller.search_calls == []
```

- [ ] **Step 2: Run the UI tests and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_poster_grid_page_ui.py -k "search_drive_filter" -v`

Expected: FAIL because the constructor option and combo do not exist.

- [ ] **Step 3: Implement the opt-in combo and state transitions**

Import `filter_search_results`, `SEARCH_DRIVE_FILTER_OPTIONS`, and
`FlatComboBox`. Add `search_drive_filter_combo`, populate it once, and connect
`currentIndexChanged` to a handler that updates `self.items` only through a
filtered render list. Keep `self._unfiltered_items` as the loaded current-page
copy. Add `_reset_search_drive_filter()`, `_apply_search_drive_filter()`, and
`_sync_search_drive_filter_visibility()`. Keep `total_items` untouched.

Place the drive filter in its own horizontal container below the existing
search controls. This is required because `_sync_search_controls_visibility()`
hides the keyword/search row for external results such as Pansou. The new
container is visible only when the opt-in flag is true and either
`_search_mode` or `_external_results_active` is true; category and folder
states hide it and render unfiltered items.

Call `_reset_search_drive_filter()` before a new page-local search and before
the first external-result page. Preserve the selection when page-local search
loads a later page or `show_external_results(..., page=N)` receives `N > 1`.
Call `_apply_search_drive_filter()` from `show_items()` after storing the new
unfiltered page. Reset the combo from `clear_search()` and
`clear_external_results()` without causing a controller request.

- [ ] **Step 4: Run the focused UI tests and verify pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_poster_grid_page_ui.py -k "search_drive_filter or external_results" -v`

Expected: PASS.

- [ ] **Step 5: Commit the reusable page behavior**

```bash
git add src/atv_player/ui/poster_grid_page.py tests/test_poster_grid_page_ui.py
git commit -m "feat: filter poster search results by drive type"
```

### Task 4: Enable the capability for the three requested sources

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add failing wiring tests**

Add `test_main_window_enables_drive_filter_for_telegram_sources_and_pansou`.
Construct `MainWindow` with `FakeTelegramController`,
`FakeTelegramChannelController`, and a minimal Pansou fake while setting
`show_telegram_channel_tab=True`. Assert the Telegram movie/channel pages opt
in and the Douban/live pages do not. Inject Pansou external results and assert
its combo becomes visible:

```python
assert window.telegram_page.search_drive_filter_combo.isHidden() is True
assert window.telegram_channel_page.search_drive_filter_combo.isHidden() is True
window.pansou_page.show_external_results(
    [VodItem(vod_id="p1", vod_name="盘搜结果", share_type="5")],
    total=1,
)
assert window.pansou_page.search_drive_filter_combo.isHidden() is False
assert window.douban_page.search_drive_filter_combo.isHidden() is True
assert window.live_page.search_drive_filter_combo.isHidden() is True
```

- [ ] **Step 2: Run the wiring tests and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_app.py tests/test_main_window_ui.py -k "search_drive_filter or pansou.*filter or telegram.*filter" -v`

Expected: FAIL because only the Telegram movie page currently has explicit
search configuration and Pansou has no filter capability.

- [ ] **Step 3: Pass the opt-in flag in `MainWindow` construction**

Set `search_drive_filter_enabled=True` on `telegram_page`, conditional
`telegram_channel_page`, and conditional `pansou_page`. Leave all other
`PosterGridPage` construction unchanged.

- [ ] **Step 4: Run the wiring and regression tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_app.py tests/test_main_window_ui.py -k "telegram or pansou or search" -v`

Expected: PASS.

- [ ] **Step 5: Commit source wiring**

```bash
git add src/atv_player/ui/main_window.py tests/test_app.py tests/test_main_window_ui.py
git commit -m "feat: enable drive filters for Telegram and Pansou"
```

### Task 5: Full verification and cleanup

**Files:**
- Test: `tests/test_browse_controller.py`
- Test: `tests/test_telegram_search_controller.py`
- Test: `tests/test_telegram_channel_controller.py`
- Test: `tests/test_poster_grid_page_ui.py`
- Test: `tests/test_app.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Run the complete focused feature suite**

Run:
`QT_QPA_PLATFORM=offscreen uv run pytest tests/test_browse_controller.py tests/test_telegram_search_controller.py tests/test_telegram_channel_controller.py tests/test_pansou_controller.py tests/test_poster_grid_page_ui.py tests/test_app.py tests/test_main_window_ui.py -q`

Expected: PASS with no failures.

- [ ] **Step 2: Run static checks on changed Python files**

Run: `uv run python -m py_compile src/atv_player/share_types.py src/atv_player/controllers/browse_controller.py src/atv_player/controllers/douban_controller.py src/atv_player/controllers/telegram_search_controller.py src/atv_player/controllers/telegram_channel_controller.py src/atv_player/ui/poster_grid_page.py src/atv_player/ui/main_window.py`

Expected: command exits successfully with no output.

- [ ] **Step 3: Review the diff and working tree**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intentional feature changes remain.
