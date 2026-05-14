# Global Search Hot Source Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hot-search source selector (`360 / 腾讯 / 爱奇艺`) above the existing category tabs, with dynamic categories per source and remembered last-selected source.

**Architecture:** Keep all popup behavior in `MainWindow` and `GlobalSearchPopup`, but replace the current single-layer category model with explicit source metadata plus per-source categories. Persist the selected source in `AppConfig`/`SettingsRepository`, and cache hot-search results by `(source, category)` so source and category switching remain independent and fast.

**Tech Stack:** Python, PySide6, httpx, pytest-qt, sqlite-backed settings persistence

---

## File Structure

- Modify: `src/atv_player/models.py`
  Purpose: Add a config field for the remembered hot-search source.
- Modify: `src/atv_player/storage.py`
  Purpose: Persist and migrate the remembered hot-search source.
- Modify: `src/atv_player/ui/main_window.py`
  Purpose: Add source metadata, source/category UI, per-source loaders, and `(source, category)` caching.
- Modify: `tests/test_storage.py`
  Purpose: Verify config round-trip and migration for the new persisted source field.
- Modify: `tests/test_main_window_ui.py`
  Purpose: Verify source tabs, dynamic categories, fallback behavior, cache behavior, and click-through search behavior.

## Task 1: Persist the Remembered Hot-Search Source

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Add the config field to `AppConfig`**

```python
@dataclass(slots=True)
class AppConfig:
    ...
    global_search_history: list[str] = field(default_factory=list)
    global_search_hot_source: str = "360"
```

- [ ] **Step 2: Extend the `app_config` schema and migration path**

```python
CREATE TABLE IF NOT EXISTS app_config (
    ...
    global_search_history TEXT NOT NULL DEFAULT '[]',
    global_search_hot_source TEXT NOT NULL DEFAULT '360'
)
```

```python
if "global_search_hot_source" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN global_search_hot_source TEXT NOT NULL DEFAULT '360'"
    )
```

- [ ] **Step 3: Load and save the new field**

```python
return AppConfig(
    ...
    global_search_history=_normalize_global_search_history(global_search_history),
    global_search_hot_source=str(global_search_hot_source or "360").strip() or "360",
)
```

```python
conn.execute(
    """
    UPDATE app_config
    SET
        ...
        global_search_history = ?,
        global_search_hot_source = ?
    WHERE id = 1
    """,
    (
        ...
        json.dumps(_normalize_global_search_history(config.global_search_history), ensure_ascii=False),
        str(config.global_search_hot_source or "360").strip() or "360",
    ),
)
```

- [ ] **Step 4: Add storage tests for round-trip and migration**

```python
def test_settings_repository_round_trip_persists_global_search_hot_source(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "settings.db")
    config = AppConfig(global_search_hot_source="iqiyi")

    repo.save_config(config)

    assert repo.load_config().global_search_hot_source == "iqiyi"
```

```python
def test_settings_repository_migrates_missing_global_search_hot_source_column(tmp_path: Path) -> None:
    ...
    assert repo.load_config().global_search_hot_source == "360"
```

- [ ] **Step 5: Run the storage tests and make them pass**

Run:

```bash
uv run pytest tests/test_storage.py -k "global_search_hot_source or global_search_history" -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit the persistence changes**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist global search hot source"
```

## Task 2: Add Source Metadata and Dynamic Source/Category UI

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Introduce explicit hot-search source metadata**

```python
_DEFAULT_GLOBAL_SEARCH_HOT_SOURCE = "360"
_DEFAULT_GLOBAL_SEARCH_HOT_CATEGORY = "dsp"

_GLOBAL_SEARCH_HOT_SOURCES = {
    "360": {
        "title": "360",
        "categories": [
            ("movie", "电视剧"),
            ("tv", "电影"),
            ("variety", "综艺"),
            ("comic", "动漫"),
            ("dsp", "综合视频"),
        ],
    },
    "tencent": {
        "title": "腾讯",
        "categories": [("hot", "热搜")],
    },
    "iqiyi": {
        "title": "爱奇艺",
        "categories": [("hot", "热搜")],
    },
}
```

- [ ] **Step 2: Extend `GlobalSearchPopup` with a source tab bar**

```python
class GlobalSearchPopup(QWidget):
    ...
    hot_source_changed = Signal(str)
```

```python
self.hot_source_tab_bar = QTabBar(self)
self.hot_source_tab_bar.setDocumentMode(True)
self.hot_source_tab_bar.setDrawBase(False)
self.hot_source_tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
self.hot_source_tab_bar.currentChanged.connect(self._handle_hot_source_tab_changed)
```

- [ ] **Step 3: Add popup APIs for source tabs and dynamic category tabs**

```python
def set_sources(self, sources: list[tuple[str, str]], current_source: str) -> None:
    ...

def set_categories(self, categories: list[tuple[str, str]], current_category: str) -> None:
    ...

def current_hot_source(self) -> str:
    ...
```

- [ ] **Step 4: Add red UI tests for source tabs and dynamic categories**

```python
def test_main_window_global_search_popup_shows_source_tabs_and_restores_saved_source(qtbot) -> None:
    window = MainWindow(..., config=AppConfig(global_search_hot_source="iqiyi"), plugin_manager=FakePluginManager())
    ...
    assert window._global_search_popup.current_hot_source() == "iqiyi"
    assert window._global_search_popup.hot_source_titles() == ["360", "腾讯", "爱奇艺"]
```

```python
def test_main_window_global_search_popup_rebuilds_categories_per_source(qtbot) -> None:
    ...
    assert window._global_search_popup.hot_tab_titles() == ["电视剧", "电影", "综艺", "动漫", "综合视频"]
    window._global_search_popup.hot_source_tab_bar.setCurrentIndex(1)
    qtbot.waitUntil(lambda: window._global_search_popup.hot_tab_titles() == ["热搜"])
```

- [ ] **Step 5: Run the popup UI tests and verify the new tests fail first, then pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup_shows_source_tabs_and_restores_saved_source or global_search_popup_rebuilds_categories_per_source" -q
```

Expected before implementation:

```text
2 failed
```

Expected after implementation:

```text
2 passed
```

- [ ] **Step 6: Commit the UI structure changes**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: add global search hot source tabs"
```

## Task 3: Refactor `MainWindow` State to Track Source and `(source, category)` Cache Keys

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Replace the current category-only state**

```python
self._global_search_hotkey_cache: dict[tuple[str, str], list[dict[str, str]]] = {}
self._global_search_hotkey_active_source = self._normalize_global_search_hot_source(
    getattr(config, "global_search_hot_source", _DEFAULT_GLOBAL_SEARCH_HOT_SOURCE)
)
self._global_search_hotkey_active_type = _DEFAULT_GLOBAL_SEARCH_HOT_CATEGORY
```

- [ ] **Step 2: Add helpers to normalize source and categories**

```python
def _normalize_global_search_hot_source(self, source: str) -> str:
    return source if source in _GLOBAL_SEARCH_HOT_SOURCES else _DEFAULT_GLOBAL_SEARCH_HOT_SOURCE

def _categories_for_hot_source(self, source: str) -> list[tuple[str, str]]:
    return list(_GLOBAL_SEARCH_HOT_SOURCES[self._normalize_global_search_hot_source(source)]["categories"])

def _fallback_hot_category(self, source: str, preferred: str) -> str:
    categories = self._categories_for_hot_source(source)
    keys = [key for key, _title in categories]
    return preferred if preferred in keys else keys[0]
```

- [ ] **Step 3: Wire source changes and category fallback behavior**

```python
def _handle_global_search_hot_source_changed(self, source: str) -> None:
    normalized = self._normalize_global_search_hot_source(source)
    self._global_search_hotkey_active_source = normalized
    self.config.global_search_hot_source = normalized
    self._save_config()
    self._global_search_hotkey_active_type = self._fallback_hot_category(
        normalized,
        self._global_search_hotkey_active_type,
    )
    self._render_global_search_popup()
```

- [ ] **Step 4: Add UI tests for fallback and remembered-source behavior**

```python
def test_main_window_global_search_popup_source_switch_falls_back_to_first_supported_category(qtbot) -> None:
    ...
    window._global_search_popup.hot_source_tab_bar.setCurrentIndex(1)
    qtbot.waitUntil(lambda: window._global_search_popup.current_hot_tab_type() == "hot")
```

```python
def test_main_window_global_search_popup_remembers_last_selected_source(qtbot) -> None:
    config = AppConfig(global_search_hot_source="360")
    ...
    window._global_search_popup.hot_source_tab_bar.setCurrentIndex(2)
    qtbot.waitUntil(lambda: config.global_search_hot_source == "iqiyi")
```

- [ ] **Step 5: Run targeted source/category state tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup_source_switch_falls_back_to_first_supported_category or global_search_popup_remembers_last_selected_source" -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit the state refactor**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "refactor: key global search hot cache by source and category"
```

## Task 4: Add Tencent and iQiyi Hot-Search Loaders and Dispatch by Source

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Add source-specific loader functions**

```python
def load_tencent_hot_searches(category: str = "hot") -> list[dict[str, str]]:
    response = httpx.post(
        _TENCENT_HOT_API,
        headers=_TENCENT_HOT_HEADERS,
        json={"pageNum": 0, "pageSize": 10, "data_version": "25081802", "client_type": 2},
        timeout=5.0,
        follow_redirects=True,
    )
    ...
```

```python
def load_iqiyi_hot_searches(category: str = "hot") -> list[dict[str, str]]:
    response = httpx.get(
        _IQIYI_HOT_API,
        timeout=5.0,
        follow_redirects=True,
    )
    ...
```

- [ ] **Step 2: Add loader dispatch based on source**

```python
def load_global_search_hotkeys(source: str, category: str) -> list[dict[str, str]]:
    if source == "360":
        return load_360_hot_searches(category)
    if source == "tencent":
        return load_tencent_hot_searches(category)
    if source == "iqiyi":
        return load_iqiyi_hot_searches(category)
    return []
```

- [ ] **Step 3: Update async request code to pass source and category together**

```python
cache_key = (source, hot_type)
...
items = self._global_search_hotkey_loader(source, hot_type)
...
self._global_search_popup_signals.hotkeys_loaded.emit(request_id, source, hot_type, list(items))
```

- [ ] **Step 4: Add tests for per-source cache behavior and item click-through**

```python
def test_main_window_global_search_popup_caches_hot_items_by_source_and_category(qtbot) -> None:
    calls: list[tuple[str, str]] = []
    ...
    assert calls == [("360", "dsp"), ("tencent", "hot")]
```

```python
def test_main_window_global_search_popup_clicking_hot_item_from_tencent_starts_search(qtbot, monkeypatch) -> None:
    ...
    assert started_keywords == ["腾讯热搜一"]
```

- [ ] **Step 5: Run focused popup tests for source-aware loading**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup_caches_hot_items_by_source_and_category or global_search_popup_clicking_hot_item_from_tencent_starts_search" -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit the source loader integration**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: add tencent and iqiyi global search hot sources"
```

## Task 5: Run Full Regression Coverage

**Files:**
- Modify: `src/atv_player/ui/main_window.py` if minimal cleanup is needed
- Modify: `tests/test_main_window_ui.py` or `tests/test_storage.py` if a brittle assertion needs adjustment

- [ ] **Step 1: Run the popup-focused suite**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_popup" -q
```

Expected:

```text
all popup tests pass
```

- [ ] **Step 2: Run global-search and storage regressions**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search" tests/test_storage.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 3: Run syntax verification for touched files**

Run:

```bash
uv run python -m py_compile src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py tests/test_storage.py
```

Expected:

```text
<no output>
```

- [ ] **Step 4: If any assertion is brittle, adjust only the helper-based checks**

```python
assert window._global_search_popup.hot_source_titles() == ["360", "腾讯", "爱奇艺"]
assert window._global_search_popup.hot_tab_titles() == ["热搜"]
```

- [ ] **Step 5: Re-run the regression command and commit the verified finish**

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search" tests/test_storage.py -q
git add src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py tests/test_storage.py
git commit -m "test: verify source-aware global search hot tabs"
```

## Self-Review

### Spec coverage

- keep 360 and add 腾讯 / 爱奇艺: covered in Tasks 2 and 4
- remember last selected source: covered in Tasks 1 and 3
- dynamic per-source categories: covered in Tasks 2 and 3
- global category fallback behavior: covered in Task 3
- per-source caching: covered in Task 4
- preserve click-through search behavior: covered in Task 4 and Task 5

### Placeholder scan

- all file paths are explicit
- all commands are concrete
- new names are defined in the same plan before later tasks use them

### Type consistency

- persisted field name: `global_search_hot_source`
- active source state: `_global_search_hotkey_active_source`
- active category state: `_global_search_hotkey_active_type`
- cache key shape: `(source, category)`
