# Spider Plugin Category Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-plugin spider category management so users can reorder, rename, hide, and restore default categories while preserving raw `type_id` behavior for requests and search.

**Architecture:** Persist category override JSON on each plugin row, parse and apply it inside `SpiderPluginController`, expose a dedicated category-management dialog for one plugin at a time, and wire that dialog into both `PluginManagerDialog` and the existing main-window plugin tab context menu flow. Keep all request paths keyed by original `type_id` and use the existing changed-plugin tab reload path after saves.

**Tech Stack:** Python 3.13, PySide6, sqlite3, pytest, pytest-qt, existing spider plugin repository/manager/controller/UI layers

---

## File Structure

- Create: `src/atv_player/plugins/category_overrides.py`
  Centralize tolerant JSON parsing, serialization, and application of category overrides.
- Create: `src/atv_player/ui/plugin_category_manager_dialog.py`
  Add the single-plugin category management dialog.
- Create: `tests/test_plugin_category_manager_dialog.py`
  Lock dialog reorder/rename/hide/reset/save behavior.
- Modify: `src/atv_player/models.py`
  Add typed plugin category override/raw-category models and extend `SpiderPluginConfig`.
- Modify: `src/atv_player/plugins/repository.py`
  Persist `category_overrides_json`, add migration, and add a focused setter.
- Modify: `src/atv_player/plugins/__init__.py`
  Pass category overrides into plugin controllers and add manager helpers for raw category loading and override saves.
- Modify: `src/atv_player/plugins/controller.py`
  Preserve raw plugin categories and apply overrides only when exposing browsing categories.
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  Add the `分类管理` button and open the dialog for a single selected plugin.
- Modify: `src/atv_player/ui/main_window.py`
  Add `分类管理` to the existing plugin context menu and route it through the existing partial plugin-tab reload flow.
- Modify: `tests/test_storage.py`
  Cover repository migration and round-trip persistence for `category_overrides_json`.
- Modify: `tests/test_spider_plugin_manager.py`
  Cover manager raw-category loading and override persistence.
- Modify: `tests/test_spider_plugin_controller.py`
  Cover rename/hide/order application and “new categories append to end”.
- Modify: `tests/test_plugin_manager_dialog.py`
  Cover button enablement and dialog integration from plugin manager.
- Modify: `tests/test_main_window_ui.py`
  Cover category management from plugin tab context actions and partial tab refresh.

### Task 1: Add Persistent Plugin Category Override Storage

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/plugins/repository.py`

- [ ] **Step 1: Write the failing repository tests**

Add these tests to `tests/test_storage.py` near the existing spider-plugin repository coverage:

```python
def test_spider_plugin_repository_round_trips_category_overrides_json(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repo.add_plugin("local", "/plugins/demo.py", "演示插件")

    repo.set_plugin_category_overrides(
        plugin.id,
        '{"order":["movie","tv"],"hidden":["adult"],"renames":{"movie":"影片"}}',
    )

    saved = repo.get_plugin(plugin.id)

    assert saved.category_overrides_json == (
        '{"order":["movie","tv"],"hidden":["adult"],"renames":{"movie":"影片"}}'
    )


def test_spider_plugin_repository_migrates_missing_category_overrides_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL,
                cached_file_path TEXT NOT NULL DEFAULT '',
                last_loaded_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                config_text TEXT NOT NULL DEFAULT '',
                plugin_version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugins (
                id, source_type, source_value, display_name, enabled, sort_order,
                cached_file_path, last_loaded_at, last_error, config_text, plugin_version
            )
            VALUES (1, 'local', '/plugins/demo.py', '演示插件', 1, 0, '', 0, '', '', 1)
            """
        )

    repo = SpiderPluginRepository(db_path)
    plugin = repo.get_plugin(1)

    assert plugin.category_overrides_json == ""
    repo.set_plugin_category_overrides(1, '{"order":["tv"]}')
    assert repo.get_plugin(1).category_overrides_json == '{"order":["tv"]}'


def test_spider_plugin_repository_partial_updates_preserve_category_overrides_json(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repo.add_plugin("local", "/plugins/demo.py", "演示插件")
    repo.set_plugin_category_overrides(plugin.id, '{"renames":{"movie":"影片"}}')

    repo.update_plugin(
        plugin.id,
        display_name="演示插件新",
        enabled=False,
        cached_file_path="",
        last_loaded_at=1713206400,
        last_error="",
        config_text="token=updated",
    )

    saved = repo.get_plugin(plugin.id)

    assert saved.display_name == "演示插件新"
    assert saved.config_text == "token=updated"
    assert saved.category_overrides_json == '{"renames":{"movie":"影片"}}'
```

- [ ] **Step 2: Run the focused storage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_storage.py::test_spider_plugin_repository_round_trips_category_overrides_json tests/test_storage.py::test_spider_plugin_repository_migrates_missing_category_overrides_column tests/test_storage.py::test_spider_plugin_repository_partial_updates_preserve_category_overrides_json -v
```

Expected: FAIL because `SpiderPluginConfig` and `SpiderPluginRepository` do not yet expose `category_overrides_json` or `set_plugin_category_overrides(...)`.

- [ ] **Step 3: Add the new config field and repository column**

Update `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class SpiderPluginConfig:
    id: int = 0
    source_type: str = ""
    source_value: str = ""
    display_name: str = ""
    enabled: bool = True
    sort_order: int = 0
    cached_file_path: str = ""
    last_loaded_at: int = 0
    last_error: str = ""
    config_text: str = ""
    plugin_version: int = 1
    category_overrides_json: str = ""
```

Update `src/atv_player/plugins/repository.py`:

```python
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spider_plugins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL,
                    cached_file_path TEXT NOT NULL DEFAULT '',
                    last_loaded_at INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    config_text TEXT NOT NULL DEFAULT '',
                    plugin_version INTEGER NOT NULL DEFAULT 1,
                    category_overrides_json TEXT NOT NULL DEFAULT ''
                )
                """
            )
            if "category_overrides_json" not in plugin_columns:
                conn.execute(
                    "ALTER TABLE spider_plugins ADD COLUMN category_overrides_json TEXT NOT NULL DEFAULT ''"
                )
```

Also update every `SELECT` and `INSERT` to include the new last column:

```python
SELECT id, source_type, source_value, display_name, enabled, sort_order,
       cached_file_path, last_loaded_at, last_error, config_text, plugin_version,
       category_overrides_json
FROM spider_plugins
```

and:

```python
INSERT INTO spider_plugins (
    source_type, source_value, display_name, enabled, sort_order,
    cached_file_path, last_loaded_at, last_error, config_text, plugin_version, category_overrides_json
)
VALUES (?, ?, ?, ?, ?, '', 0, '', '', ?, '')
```

- [ ] **Step 4: Add a focused repository setter without breaking partial updates**

Extend `src/atv_player/plugins/repository.py`:

```python
    def set_plugin_category_overrides(self, plugin_id: int, category_overrides_json: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE spider_plugins SET category_overrides_json = ? WHERE id = ?",
                (category_overrides_json, plugin_id),
            )
```

Keep `update_plugin(...)` backward-compatible by preserving the stored override string when the caller does not pass one:

```python
    def update_plugin(
        self,
        plugin_id: int,
        *,
        display_name: str,
        enabled: bool,
        cached_file_path: str,
        last_loaded_at: int,
        last_error: str,
        config_text: str,
        plugin_version: int = 1,
        category_overrides_json: str | None = None,
    ) -> None:
        if category_overrides_json is None:
            category_overrides_json = self.get_plugin(plugin_id).category_overrides_json
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE spider_plugins
                SET display_name = ?, enabled = ?, cached_file_path = ?,
                    last_loaded_at = ?, last_error = ?, config_text = ?, plugin_version = ?,
                    category_overrides_json = ?
                WHERE id = ?
                """,
                (
                    display_name,
                    int(enabled),
                    cached_file_path,
                    last_loaded_at,
                    last_error,
                    config_text,
                    int(plugin_version),
                    category_overrides_json,
                    plugin_id,
                ),
            )
```

- [ ] **Step 5: Re-run the focused storage tests**

Run:

```bash
uv run pytest tests/test_storage.py::test_spider_plugin_repository_round_trips_category_overrides_json tests/test_storage.py::test_spider_plugin_repository_migrates_missing_category_overrides_column tests/test_storage.py::test_spider_plugin_repository_partial_updates_preserve_category_overrides_json -v
```

Expected: PASS.

### Task 2: Parse And Apply Category Overrides In The Spider Plugin Controller

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/models.py`
- Create: `src/atv_player/plugins/category_overrides.py`
- Modify: `src/atv_player/plugins/controller.py`

- [ ] **Step 1: Write the failing controller tests**

Add these tests to `tests/test_spider_plugin_controller.py` after the existing filter coverage:

```python
def test_controller_applies_category_overrides_without_changing_type_ids() -> None:
    controller = SpiderPluginController(
        FilterSpider(),
        plugin_name="筛选插件",
        search_enabled=True,
        category_overrides_json='{"order":["tv","movie"],"hidden":["adult"],"renames":{"tv":"剧集","movie":"影片"}}',
    )

    categories = controller.load_categories()

    assert [(item.type_id, item.type_name) for item in categories] == [
        ("tv", "剧集"),
        ("movie", "影片"),
    ]


def test_controller_appends_new_categories_not_present_in_saved_order() -> None:
    class ExtraCategorySpider(FilterSpider):
        def homeContent(self, filter):
            payload = super().homeContent(filter)
            payload["class"].append({"type_id": "variety", "type_name": "综艺"})
            return payload

    controller = SpiderPluginController(
        ExtraCategorySpider(),
        plugin_name="筛选插件",
        search_enabled=True,
        category_overrides_json='{"order":["tv","movie"],"renames":{"tv":"剧集"}}',
    )

    categories = controller.load_categories()

    assert [item.type_id for item in categories] == ["tv", "movie", "variety"]
    assert categories[2].type_name == "综艺"


def test_controller_exposes_raw_categories_for_category_manager() -> None:
    controller = SpiderPluginController(
        FilterSpider(),
        plugin_name="筛选插件",
        search_enabled=True,
        category_overrides_json='{"renames":{"movie":"影片"}}',
    )

    raw_categories = controller.load_raw_categories()
    visible_categories = controller.load_categories()

    assert [(item.type_id, item.type_name) for item in raw_categories] == [
        ("movie", "电影"),
        ("tv", "剧集"),
        ("adult", "成人视频"),
    ]
    assert visible_categories[0].type_name == "影片"
```

Update `FilterSpider.homeContent()` in the same test file so its `class` payload includes three categories:

```python
            "class": [
                {"type_id": "movie", "type_name": "电影"},
                {"type_id": "tv", "type_name": "剧集"},
                {"type_id": "adult", "type_name": "成人视频"},
            ],
```

- [ ] **Step 2: Run the focused controller tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py::test_controller_applies_category_overrides_without_changing_type_ids tests/test_spider_plugin_controller.py::test_controller_appends_new_categories_not_present_in_saved_order tests/test_spider_plugin_controller.py::test_controller_exposes_raw_categories_for_category_manager -v
```

Expected: FAIL because `SpiderPluginController` does not accept `category_overrides_json` and does not expose `load_raw_categories()`.

- [ ] **Step 3: Add typed override models and helper functions**

Extend `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class SpiderPluginCategoryOverrides:
    order: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
    renames: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SpiderPluginRawCategory:
    type_id: str
    type_name: str
    filters: list[CategoryFilter] = field(default_factory=list)
```

Create `src/atv_player/plugins/category_overrides.py`:

```python
from __future__ import annotations

import json

from atv_player.models import DoubanCategory, SpiderPluginCategoryOverrides, SpiderPluginRawCategory


def parse_category_overrides_json(payload: str) -> SpiderPluginCategoryOverrides:
    try:
        parsed = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return SpiderPluginCategoryOverrides()
    if not isinstance(parsed, dict):
        return SpiderPluginCategoryOverrides()
    order = [str(item).strip() for item in parsed.get("order") or [] if str(item).strip()]
    hidden = [str(item).strip() for item in parsed.get("hidden") or [] if str(item).strip()]
    renames = {
        str(key).strip(): str(value).strip()
        for key, value in (parsed.get("renames") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    return SpiderPluginCategoryOverrides(order=order, hidden=hidden, renames=renames)


def dumps_category_overrides_json(overrides: SpiderPluginCategoryOverrides) -> str:
    payload: dict[str, object] = {}
    if overrides.order:
        payload["order"] = overrides.order
    if overrides.hidden:
        payload["hidden"] = overrides.hidden
    if overrides.renames:
        payload["renames"] = overrides.renames
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload else ""


def apply_category_overrides(
    categories: list[SpiderPluginRawCategory],
    overrides: SpiderPluginCategoryOverrides,
) -> list[DoubanCategory]:
    by_id = {category.type_id: category for category in categories}
    visible_ids = [category.type_id for category in categories if category.type_id not in set(overrides.hidden)]
    ordered_ids: list[str] = []
    for type_id in overrides.order:
        if type_id in visible_ids and type_id not in ordered_ids:
            ordered_ids.append(type_id)
    for type_id in visible_ids:
        if type_id not in ordered_ids:
            ordered_ids.append(type_id)
    return [
        DoubanCategory(
            type_id=type_id,
            type_name=overrides.renames.get(type_id, by_id[type_id].type_name),
            filters=list(by_id[type_id].filters),
        )
        for type_id in ordered_ids
    ]
```

- [ ] **Step 4: Preserve raw categories and apply overrides on read**

Update `src/atv_player/plugins/controller.py`:

```python
from atv_player.models import (
    CategoryFilter,
    CategoryFilterOption,
    DoubanCategory,
    ExternalSubtitleOption,
    OpenPlayerRequest,
    PlaybackDetailAction,
    PlaybackDetailField,
    PlaybackDetailFieldAction,
    PlaybackDetailValuePart,
    PlaybackLoadResult,
    PlayItem,
    SpiderPluginRawCategory,
    VodItem,
)
from atv_player.plugins.category_overrides import apply_category_overrides, parse_category_overrides_json
```

Extend `__init__`:

```python
        category_overrides_json: str = "",
    ) -> None:
        ...
        self._category_overrides_json = str(category_overrides_json or "")
        self._category_overrides = parse_category_overrides_json(self._category_overrides_json)
        self._raw_home_categories: list[SpiderPluginRawCategory] = []
        self._has_home_recommendations = False
```

Change `_ensure_home_loaded()` so it stores raw categories first:

```python
        raw_categories = [
            SpiderPluginRawCategory(
                type_id=_coerce_category_id(item.get("type_id")),
                type_name=str(item.get("type_name") or ""),
                filters=_map_category_filters(raw_filters.get(_coerce_category_id(item.get("type_id")))),
            )
            for item in payload.get("class", [])
        ]
        items = self._map_items(payload)
        self._raw_home_categories = raw_categories
        self._home_items = self._annotate_items_with_category(items) if items else []
        self._has_home_recommendations = bool(self._home_items)
        self._home_loaded = True
```

Add:

```python
    def load_raw_categories(self) -> list[DoubanCategory]:
        self._ensure_home_loaded()
        return [
            DoubanCategory(type_id=item.type_id, type_name=item.type_name, filters=list(item.filters))
            for item in self._raw_home_categories
        ]

    def load_categories(self) -> list[DoubanCategory]:
        self._ensure_home_loaded()
        categories = apply_category_overrides(self._raw_home_categories, self._category_overrides)
        if self._has_home_recommendations:
            categories = [DoubanCategory(type_id="home", type_name="推荐"), *categories]
        return categories
```

- [ ] **Step 5: Re-run the focused controller tests**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py::test_controller_applies_category_overrides_without_changing_type_ids tests/test_spider_plugin_controller.py::test_controller_appends_new_categories_not_present_in_saved_order tests/test_spider_plugin_controller.py::test_controller_exposes_raw_categories_for_category_manager -v
```

Expected: PASS.

### Task 3: Add Manager Helpers For Raw Category Loading And Override Saving

**Files:**
- Modify: `tests/test_spider_plugin_manager.py`
- Modify: `src/atv_player/plugins/__init__.py`

- [ ] **Step 1: Write the failing manager tests**

Add these tests to `tests/test_spider_plugin_manager.py`:

```python
class CategoryLoader(FakeLoader):
    def load(self, config: SpiderPluginConfig, force_refresh: bool = False) -> LoadedSpiderPlugin:
        loaded = super().load(config, force_refresh=force_refresh)
        spider = FakeSpider()
        return LoadedSpiderPlugin(
            config=loaded.config,
            spider=spider,
            plugin_name="分类插件",
            search_enabled=True,
        )


def test_manager_set_plugin_category_overrides_persists_json_and_survives_refresh(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/demo.py", "演示插件")
    manager = SpiderPluginManager(repository, FakeLoader())

    manager.set_plugin_category_overrides(plugin.id, '{"renames":{"movie":"影片"}}')
    manager.refresh_plugin(plugin.id)

    saved = repository.get_plugin(plugin.id)

    assert saved.category_overrides_json == '{"renames":{"movie":"影片"}}'


def test_manager_load_plugin_categories_returns_raw_plugin_categories(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repository.add_plugin("local", "/plugins/demo.py", "演示插件")
    repository.set_plugin_category_overrides(plugin.id, '{"renames":{"hot":"热门推荐"}}')
    manager = SpiderPluginManager(repository, CategoryLoader())

    categories = manager.load_plugin_categories(plugin.id)

    assert [(item.type_id, item.type_name) for item in categories] == [
        ("hot", "热门"),
        ("tv", "剧场"),
    ]
```

- [ ] **Step 2: Run the focused manager tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py::test_manager_set_plugin_category_overrides_persists_json_and_survives_refresh tests/test_spider_plugin_manager.py::test_manager_load_plugin_categories_returns_raw_plugin_categories -v
```

Expected: FAIL because `SpiderPluginManager` does not yet expose `set_plugin_category_overrides(...)` or `load_plugin_categories(...)`.

- [ ] **Step 3: Add manager passthrough methods and pass overrides into built plugin controllers**

Update `src/atv_player/plugins/__init__.py`:

```python
    def set_plugin_category_overrides(self, plugin_id: int, category_overrides_json: str) -> None:
        self._repository.set_plugin_category_overrides(plugin_id, category_overrides_json)

    def load_plugin_categories(self, plugin_id: int) -> list[DoubanCategory]:
        plugin, loaded = self._load_plugin(plugin_id)
        controller = SpiderPluginController(
            loaded.spider,
            plugin_name=self._plugin_title(plugin, loaded),
            search_enabled=loaded.search_enabled,
            spider_initializer=loaded.initialize_spider,
        )
        return controller.load_raw_categories()
```

Pass overrides through `_build_plugin_definition(...)`:

```python
        controller = SpiderPluginController(
            loaded.spider,
            plugin_name=title,
            search_enabled=loaded.search_enabled,
            category_overrides_json=plugin.category_overrides_json,
            drive_detail_loader=drive_detail_loader,
            offline_download_detail_loader=offline_download_detail_loader,
            ...
        )
```

- [ ] **Step 4: Ensure every repository update path preserves the override JSON**

Where `SpiderPluginManager` calls `self._repository.update_plugin(...)`, include the stored override string explicitly when the plugin object is already available:

```python
                category_overrides_json=plugin.category_overrides_json,
```

Do this in:

- `refresh_plugin(...)`
- `iter_enabled_plugins(...)` error path
- `load_plugins(...)` error path
- GitHub import version-update path

- [ ] **Step 5: Re-run the focused manager tests**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py::test_manager_set_plugin_category_overrides_persists_json_and_survives_refresh tests/test_spider_plugin_manager.py::test_manager_load_plugin_categories_returns_raw_plugin_categories -v
```

Expected: PASS.

### Task 4: Build The Plugin Category Management Dialog

**Files:**
- Create: `tests/test_plugin_category_manager_dialog.py`
- Create: `src/atv_player/ui/plugin_category_manager_dialog.py`

- [ ] **Step 1: Write the failing dialog tests**

Create `tests/test_plugin_category_manager_dialog.py`:

```python
from atv_player.models import DoubanCategory, SpiderPluginConfig
from atv_player.ui.plugin_category_manager_dialog import PluginCategoryManagerDialog


class FakePluginManager:
    def __init__(self) -> None:
        self.plugin = SpiderPluginConfig(
            id=7,
            source_type="local",
            source_value="/plugins/demo.py",
            display_name="演示插件",
            enabled=True,
            category_overrides_json='{"order":["tv","movie"],"hidden":["adult"],"renames":{"movie":"影片"}}',
        )
        self.saved_overrides: list[tuple[int, str]] = []

    def list_plugins(self):
        return [self.plugin]

    def load_plugin_categories(self, plugin_id: int):
        assert plugin_id == 7
        return [
            DoubanCategory(type_id="movie", type_name="电影"),
            DoubanCategory(type_id="tv", type_name="剧集"),
            DoubanCategory(type_id="adult", type_name="成人视频"),
        ]

    def set_plugin_category_overrides(self, plugin_id: int, category_overrides_json: str) -> None:
        self.saved_overrides.append((plugin_id, category_overrides_json))
        self.plugin.category_overrides_json = category_overrides_json


def _row_texts(dialog: PluginCategoryManagerDialog) -> list[str]:
    return [dialog.category_list.item(index).text() for index in range(dialog.category_list.count())]


def test_plugin_category_manager_dialog_uses_override_order_and_hidden_marker(qtbot) -> None:
    dialog = PluginCategoryManagerDialog(FakePluginManager(), plugin_id=7)
    qtbot.addWidget(dialog)

    assert _row_texts(dialog) == ["剧集", "影片", "成人视频（已隐藏）"]


def test_plugin_category_manager_dialog_restore_defaults_resets_draft(qtbot) -> None:
    dialog = PluginCategoryManagerDialog(FakePluginManager(), plugin_id=7)
    qtbot.addWidget(dialog)
    dialog._move_to_bottom()
    dialog._toggle_hidden()

    dialog._restore_defaults()

    assert _row_texts(dialog) == ["电影", "剧集", "成人视频"]


def test_plugin_category_manager_dialog_save_persists_compact_override_json(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginCategoryManagerDialog(manager, plugin_id=7)
    qtbot.addWidget(dialog)
    dialog.category_list.setCurrentRow(0)
    monkeypatch.setattr(dialog, "_prompt_display_name", lambda current: "长剧")
    dialog._rename_selected()
    dialog._move_to_bottom()

    dialog._save()

    assert manager.saved_overrides == [
        (7, '{"order":["movie","adult","tv"],"hidden":["adult"],"renames":{"movie":"影片","tv":"长剧"}}')
    ]
    assert dialog.result() == dialog.DialogCode.Accepted
```

- [ ] **Step 2: Run the new dialog tests to verify the dialog does not exist yet**

Run:

```bash
uv run pytest tests/test_plugin_category_manager_dialog.py -q
```

Expected: FAIL with import errors because `PluginCategoryManagerDialog` does not exist yet.

- [ ] **Step 3: Implement the category manager dialog with draft row state**

Create `src/atv_player/ui/plugin_category_manager_dialog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QInputDialog, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout

from atv_player.models import SpiderPluginCategoryOverrides
from atv_player.plugins.category_overrides import dumps_category_overrides_json, parse_category_overrides_json
from atv_player.ui.window_chrome import ThemedDialogBase


@dataclass(slots=True)
class _CategoryRow:
    type_id: str
    raw_name: str
    display_name: str
    hidden: bool = False


class PluginCategoryManagerDialog(ThemedDialogBase):
    def __init__(self, plugin_manager, plugin_id: int, parent=None) -> None:
        super().__init__(title="分类管理", parent=parent)
        self.plugin_manager = plugin_manager
        self.plugin_id = plugin_id
        self.plugin = next(item for item in self.plugin_manager.list_plugins() if int(item.id) == int(plugin_id))
        self.raw_categories = list(self.plugin_manager.load_plugin_categories(plugin_id))
        self._default_rows = self._build_default_rows()
        self._draft_rows = self._build_rows_from_overrides(parse_category_overrides_json(self.plugin.category_overrides_json))
        self.category_list = QListWidget(self)
        self.category_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.top_button = QPushButton("置顶", self)
        self.up_button = QPushButton("上移", self)
        self.down_button = QPushButton("下移", self)
        self.bottom_button = QPushButton("置底", self)
        self.rename_button = QPushButton("重命名", self)
        self.hide_button = QPushButton("隐藏/显示", self)
        self.reset_button = QPushButton("恢复默认", self)
        self.save_button = QPushButton("保存", self)
        self.cancel_button = QPushButton("取消", self)
        ...
```

Implement the core draft helpers:

```python
    def _build_default_rows(self) -> list[_CategoryRow]:
        return [
            _CategoryRow(type_id=item.type_id, raw_name=item.type_name, display_name=item.type_name, hidden=False)
            for item in self.raw_categories
        ]

    def _build_rows_from_overrides(self, overrides: SpiderPluginCategoryOverrides) -> list[_CategoryRow]:
        by_id = {row.type_id: _CategoryRow(**row.__dict__) for row in self._build_default_rows()}
        ordered_ids: list[str] = []
        for type_id in overrides.order:
            if type_id in by_id and type_id not in ordered_ids:
                ordered_ids.append(type_id)
        for row in self._build_default_rows():
            if row.type_id not in ordered_ids:
                ordered_ids.append(row.type_id)
        rows: list[_CategoryRow] = []
        for type_id in ordered_ids:
            row = by_id[type_id]
            renamed = overrides.renames.get(type_id, "")
            if renamed:
                row.display_name = renamed
            row.hidden = type_id in set(overrides.hidden)
            rows.append(row)
        return rows

    def _compose_override_json(self) -> str:
        overrides = SpiderPluginCategoryOverrides(
            order=[row.type_id for row in self._draft_rows],
            hidden=[row.type_id for row in self._draft_rows if row.hidden],
            renames={
                row.type_id: row.display_name
                for row in self._draft_rows
                if row.display_name.strip() and row.display_name.strip() != row.raw_name
            },
        )
        return dumps_category_overrides_json(overrides)
```

Render hidden rows with a marker:

```python
    def _render_rows(self) -> None:
        self.category_list.clear()
        for row in self._draft_rows:
            label = row.display_name
            if row.hidden:
                label = f"{label}（已隐藏）"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, row.type_id)
            self.category_list.addItem(item)
        if self.category_list.count():
            self.category_list.setCurrentRow(0)
```

- [ ] **Step 4: Wire save, rename, hide, move, and restore-default behavior**

Add:

```python
    def _prompt_display_name(self, current: str) -> str:
        value, accepted = QInputDialog.getText(self, "重命名分类", "显示名称", text=current)
        return value.strip() if accepted else ""

    def _rename_selected(self) -> None:
        row = self._current_row_object()
        if row is None:
            return
        value = self._prompt_display_name(row.display_name)
        if not value:
            return
        row.display_name = value
        self._render_rows()

    def _toggle_hidden(self) -> None:
        row = self._current_row_object()
        if row is None:
            return
        row.hidden = not row.hidden
        self._render_rows()

    def _restore_defaults(self) -> None:
        self._draft_rows = self._build_default_rows()
        self._render_rows()

    def _save(self) -> None:
        self.plugin_manager.set_plugin_category_overrides(self.plugin_id, self._compose_override_json())
        self.accept()
```

Use the same row-reorder pattern as `PluginReorderDialog` for `置顶/上移/下移/置底`.

- [ ] **Step 5: Re-run the dialog tests**

Run:

```bash
uv run pytest tests/test_plugin_category_manager_dialog.py -q
```

Expected: PASS.

### Task 5: Integrate Category Management Into Plugin Manager Dialog

**Files:**
- Modify: `tests/test_plugin_manager_dialog.py`
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`

- [ ] **Step 1: Write the failing plugin-manager dialog tests**

Add these tests to `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_dialog_exposes_category_management_button(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.category_button.text() == "分类管理"


def test_plugin_manager_dialog_enables_category_management_only_for_single_selection(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.plugin_table.clearSelection()
    dialog._sync_action_state()
    assert dialog.category_button.isEnabled() is False

    _select_rows(dialog, 0)
    dialog._sync_action_state()
    assert dialog.category_button.isEnabled() is True

    _select_rows(dialog, 0, 1)
    dialog._sync_action_state()
    assert dialog.category_button.isEnabled() is False


def test_plugin_manager_dialog_opens_category_manager_and_marks_tabs_dirty_on_accept(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.plugin_table.selectRow(0)
    reload_calls: list[str] = []

    class FakeCategoryDialog:
        def __init__(self, plugin_manager, plugin_id: int, parent=None) -> None:
            assert plugin_manager is manager
            assert plugin_id == 1
            assert parent is dialog

        def exec(self) -> int:
            manager.plugins[0].category_overrides_json = '{"order":["tv"]}'
            return PluginManagerDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog, "reload_plugins", lambda: reload_calls.append("reload"))
    monkeypatch.setattr(plugin_manager_dialog_module, "PluginCategoryManagerDialog", FakeCategoryDialog)

    dialog._open_category_manager_dialog()

    assert dialog.plugin_tabs_dirty is True
    assert reload_calls == ["reload"]
```

- [ ] **Step 2: Run the focused dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_exposes_category_management_button tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_enables_category_management_only_for_single_selection tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_opens_category_manager_and_marks_tabs_dirty_on_accept -v
```

Expected: FAIL because `PluginManagerDialog` does not yet expose a category-management button or open method.

- [ ] **Step 3: Add the new button and enablement logic**

Update `src/atv_player/ui/plugin_manager_dialog.py`:

```python
from atv_player.ui.plugin_category_manager_dialog import PluginCategoryManagerDialog
...
        self.category_button = QPushButton("分类管理")
...
        for button in (
            self.add_local_button,
            self.add_remote_button,
            self.import_github_button,
            self.rename_button,
            self.config_button,
            self.category_button,
            self.toggle_button,
            self.up_button,
            self.down_button,
            self.reorder_button,
            self.refresh_button,
            self.logs_button,
            self.delete_button,
        ):
            actions.addWidget(button)
...
        self.category_button.clicked.connect(self._open_category_manager_dialog)
```

In `_sync_action_state()`:

```python
            self.category_button.setEnabled(False)
```

and:

```python
        self.category_button.setEnabled(has_single_selection)
```

- [ ] **Step 4: Open the dialog and mark plugin tabs dirty after a successful save**

Add to `src/atv_player/ui/plugin_manager_dialog.py`:

```python
    def _open_category_manager_dialog(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        dialog = PluginCategoryManagerDialog(self.plugin_manager, plugin_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.plugin_tabs_dirty = True
        self.reload_plugins()
```

- [ ] **Step 5: Re-run the focused plugin-manager dialog tests**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_exposes_category_management_button tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_enables_category_management_only_for_single_selection tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_opens_category_manager_and_marks_tabs_dirty_on_accept -v
```

Expected: PASS.

### Task 6: Add Category Management To Main-Window Plugin Context Menus

**Files:**
- Modify: `tests/test_main_window_ui.py`
- Modify: `src/atv_player/ui/main_window.py`

- [ ] **Step 1: Write the failing main-window tests**

Add these tests to `tests/test_main_window_ui.py` near the existing plugin context action coverage:

```python
def test_main_window_manage_categories_context_action_reloads_only_target_plugin(qtbot, monkeypatch) -> None:
    manager = WidthAwarePluginManager()
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=manager.load_plugins(["1", "2", "3"]),
        plugin_manager=manager,
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_available_plugin_tab_width", lambda: 600)
    monkeypatch.setattr(window, "_plugin_tab_title_width", lambda title: 88)
    opened: list[int] = []
    monkeypatch.setattr(window, "_open_plugin_category_manager", lambda plugin_id: opened.append(plugin_id) or True)

    window.show()
    window._refresh_navigation_tabs()
    result = window._run_plugin_context_action("manage_categories", "2")

    assert result is True
    assert opened == [2]
    assert manager.load_plugins_calls[-1] == ["2"]


def test_main_window_plugin_context_menu_includes_category_management(qtbot, monkeypatch) -> None:
    manager = WidthAwarePluginManager()
    window = MainWindow(
        douban_controller=FakeStaticController(),
        telegram_controller=FakeStaticController(),
        live_controller=FakeStaticController(),
        emby_controller=FakeStaticController(),
        jellyfin_controller=FakeStaticController(),
        browse_controller=FakeStaticController(),
        history_controller=FakeStaticController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
        spider_plugins=manager.load_plugins(["1"]),
        plugin_manager=manager,
    )
    qtbot.addWidget(window)
    captured_actions: list[str] = []

    class FakeAction:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeMenu:
        def __init__(self, parent=None) -> None:
            del parent
            self.actions: list[FakeAction] = []

        def addAction(self, text: str):
            action = FakeAction(text)
            self.actions.append(action)
            captured_actions.append(text)
            return action

        def exec(self, global_pos):
            del global_pos
            return None

    monkeypatch.setattr(main_window_module, "QMenu", FakeMenu)

    window._open_plugin_context_menu("1", window.mapToGlobal(window.rect().center()))

    assert captured_actions == ["重新加载", "编辑名称", "编辑配置", "分类管理", "禁用"]
```

- [ ] **Step 2: Run the focused main-window tests to verify they fail**

Run:

```bash
uv run pytest tests/test_main_window_ui.py::test_main_window_manage_categories_context_action_reloads_only_target_plugin tests/test_main_window_ui.py::test_main_window_plugin_context_menu_includes_category_management -v
```

Expected: FAIL because the action map and context menu do not yet include `manage_categories`.

- [ ] **Step 3: Add the context-menu item and action dispatch**

Update `src/atv_player/ui/main_window.py`:

```python
        manage_categories_action = menu.addAction("分类管理")
        toggle_action = menu.addAction(self._plugin_toggle_action_text(plugin_id))
        chosen = menu.exec(global_pos)
        if chosen is reload_action:
            self._run_plugin_context_action("refresh", plugin_id)
        elif chosen is rename_action:
            self._run_plugin_context_action("rename", plugin_id)
        elif chosen is config_action:
            self._run_plugin_context_action("edit_config", plugin_id)
        elif chosen is manage_categories_action:
            self._run_plugin_context_action("manage_categories", plugin_id)
        elif chosen is toggle_action:
            self._run_plugin_context_action("toggle_enabled", plugin_id)
```

Extend `_run_plugin_context_action(...)`:

```python
        if action_name == "manage_categories":
            changed = self._open_plugin_category_manager(int(self._normalize_plugin_id(plugin_id)))
            if not changed:
                return False
            self._reload_changed_plugin_tabs([self._normalize_plugin_id(plugin_id)])
            self._sync_plugin_overflow_drawer(reset_search=False)
            return True
```

- [ ] **Step 4: Reuse the same dialog path from visible tabs and hidden drawer items**

Add a helper to `src/atv_player/ui/main_window.py`:

```python
    def _open_plugin_category_manager(self, plugin_id: int) -> bool:
        if self._plugin_manager is None:
            return False
        self._close_plugin_overflow_drawer()
        dialog = PluginCategoryManagerDialog(self._plugin_manager, plugin_id, self)
        return dialog.exec() == QDialog.DialogCode.Accepted
```

Import the dialog:

```python
from atv_player.ui.plugin_category_manager_dialog import PluginCategoryManagerDialog
```

This helper is shared automatically by:

- visible plugin tabs through `_handle_plugin_tab_context_menu_requested(...)`
- hidden drawer items through `self._plugin_overflow_drawer.plugin_context_requested.connect(self._open_plugin_context_menu)`

- [ ] **Step 5: Re-run the focused main-window tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py::test_main_window_manage_categories_context_action_reloads_only_target_plugin tests/test_main_window_ui.py::test_main_window_plugin_context_menu_includes_category_management -v
```

Expected: PASS.

### Task 7: Run End-To-End Verification

**Files:**
- Test: `tests/test_storage.py`
- Test: `tests/test_spider_plugin_manager.py`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_plugin_category_manager_dialog.py`
- Test: `tests/test_plugin_manager_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Run the storage and manager suite**

Run:

```bash
uv run pytest tests/test_storage.py tests/test_spider_plugin_manager.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the controller and dialog suite**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py tests/test_plugin_category_manager_dialog.py tests/test_plugin_manager_dialog.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the focused main-window UI suite**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "plugin_context or category_management" -q
```

Expected: PASS.

- [ ] **Step 4: Run a final compile smoke check**

Run:

```bash
uv run python -m py_compile src/atv_player/models.py src/atv_player/plugins/repository.py src/atv_player/plugins/__init__.py src/atv_player/plugins/controller.py src/atv_player/plugins/category_overrides.py src/atv_player/ui/plugin_category_manager_dialog.py src/atv_player/ui/plugin_manager_dialog.py src/atv_player/ui/main_window.py
```

Expected: no output.
