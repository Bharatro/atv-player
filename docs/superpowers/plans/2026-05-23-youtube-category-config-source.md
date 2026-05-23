# YouTube Category Config Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single selectable YouTube category source that supports built-in defaults, remote JSONC, and local JSONC while normalizing YouTube ids to bare video ids, `channel@...`, and `playlist@...`.

**Architecture:** Add a Qt-free parser/source loader layer for TVBox-style YouTube category configs, persist source settings in `AppConfig`, and inject the loader into `YouTubeController`. Keep `PosterGridPage` unchanged by continuing to return `DoubanCategory` with `CategoryFilter` groups. Update the Advanced Settings YouTube tab using existing form styles and helpers.

**Tech Stack:** Python 3.12, PySide6, SQLite settings repository, httpx-backed `ApiClient.get_text`, pytest, pytest-qt.

---

## File Structure

- Create `src/atv_player/controllers/youtube_category_config.py`: JSONC stripping, TVBox `class`/`filters` parsing, `LIST:` expansion, source loading/cache fallback, query planning helpers.
- Modify `src/atv_player/models.py`: add YouTube category source fields to `AppConfig`.
- Modify `src/atv_player/storage.py`: add columns, normalization, load/save support for the new config fields.
- Modify `src/atv_player/controllers/youtube_controller.py`: consume parsed category config, use query plans, normalize ids, emit new id format.
- Modify `src/atv_player/app.py`: pass `ApiClient.get_text` or an equivalent fetcher into the YouTube config source loader.
- Modify `src/atv_player/ui/advanced_settings_dialog.py`: add source controls in the existing YouTube tab using current styles.
- Modify `src/atv_player/ui/main_window.py`: keep the existing accepted-settings category reload path; add no new visual entry point.
- Modify `src/atv_player/controllers/player_controller.py`, `src/atv_player/yt_dlp_service.py`, and `src/atv_player/ui/player_window.py` only where direct YouTube id recognition needs bare video-id compatibility.
- Add/modify tests in `tests/test_youtube_category_config.py`, `tests/test_youtube_controller.py`, `tests/test_storage.py`, `tests/test_main_window_ui.py`, `tests/test_app.py`, and `tests/test_yt_dlp_service.py`.

---

### Task 1: JSONC Parser and TVBox Mapping

**Files:**
- Create: `src/atv_player/controllers/youtube_category_config.py`
- Test: `tests/test_youtube_category_config.py`

- [ ] **Step 1: Write failing parser tests**

Add `tests/test_youtube_category_config.py`:

```python
from atv_player.controllers.youtube_category_config import (
    YouTubeCategoryConfig,
    parse_youtube_category_config,
)


def test_parse_youtube_category_config_accepts_jsonc_comments_and_maps_filters() -> None:
    payload = """
    {
      // category comment
      "class": [
        {"type_id": "電影", "type_name": "電影"},
        {"type_id": "LIST:HDR,Girls HDR,Landscape HDR", "type_name": "HDR"}
      ],
      "filters": {
        "電影": [
          {
            "key": "time",
            "name": "時間",
            "value": [
              {"n": "全部", "v": ""},
              {"n": "2024", "v": "2024"}
            ]
          }
        ],
        "LIST:HDR,Girls HDR,Landscape HDR": [
          {
            "key": "tid",
            "name": "風景",
            "value": [
              {"n": "自然", "v": "hdr 大自然"}
            ]
          }
        ]
      }
    }
    """

    config = parse_youtube_category_config(payload)

    assert isinstance(config, YouTubeCategoryConfig)
    assert [category.type_id for category in config.categories] == [
        "電影",
        "LIST:HDR,Girls HDR,Landscape HDR",
    ]
    assert config.categories[0].filters[0].key == "time"
    assert config.categories[0].filters[0].options[0].value == ""
    assert config.categories[1].filters[0].key == "list_keyword"
    assert [option.value for option in config.categories[1].filters[0].options] == [
        "HDR",
        "Girls HDR",
        "Landscape HDR",
    ]
    assert config.categories[1].filters[1].key == "tid"


def test_parse_youtube_category_config_skips_malformed_entries() -> None:
    payload = """
    {
      "class": [
        {"type_id": "", "type_name": "空"},
        {"type_id": "ok", "type_name": "有效"}
      ],
      "filters": {
        "ok": [
          {"key": "", "name": "broken", "value": [{"n": "A", "v": "a"}]},
          {"key": "tid", "name": "类型", "value": [{"n": "", "v": "bad"}, {"n": "B", "v": "b"}]}
        ]
      }
    }
    """

    config = parse_youtube_category_config(payload)

    assert [category.type_id for category in config.categories] == ["ok"]
    assert len(config.categories[0].filters) == 1
    assert config.categories[0].filters[0].options[0].name == "B"
```

- [ ] **Step 2: Run parser tests and verify failure**

Run: `uv run pytest tests/test_youtube_category_config.py -q`

Expected: FAIL with `ModuleNotFoundError` for `atv_player.controllers.youtube_category_config`.

- [ ] **Step 3: Implement parser and models**

Create `src/atv_player/controllers/youtube_category_config.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field

from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory

LIST_KEYWORD_FILTER_KEY = "list_keyword"


@dataclass(slots=True)
class YouTubeCategoryConfig:
    categories: list[DoubanCategory] = field(default_factory=list)
    raw_text: str = ""


def strip_jsonc_comments(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _text(value: object) -> str:
    return str(value or "").strip()


def _map_filter_option(payload: object) -> CategoryFilterOption | None:
    if not isinstance(payload, dict):
        return None
    name = _text(payload.get("n"))
    if not name:
        return None
    return CategoryFilterOption(name=name, value=_text(payload.get("v")))


def _map_filter_group(payload: object) -> CategoryFilter | None:
    if not isinstance(payload, dict):
        return None
    key = _text(payload.get("key"))
    name = _text(payload.get("name"))
    if not key or not name:
        return None
    options = [
        option
        for option in (_map_filter_option(item) for item in payload.get("value") or [])
        if option is not None
    ]
    if not options:
        return None
    return CategoryFilter(key=key, name=name, options=options)


def _list_keyword_filter(category_id: str) -> CategoryFilter | None:
    if not category_id.startswith("LIST:"):
        return None
    values = [part.strip() for part in category_id.removeprefix("LIST:").split(",") if part.strip()]
    if not values:
        return None
    return CategoryFilter(
        key=LIST_KEYWORD_FILTER_KEY,
        name="关键词",
        options=[CategoryFilterOption(name=value, value=value) for value in values],
    )


def parse_youtube_category_config(text: str) -> YouTubeCategoryConfig:
    payload = json.loads(strip_jsonc_comments(text))
    if not isinstance(payload, dict):
        return YouTubeCategoryConfig(raw_text=text)
    raw_filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    categories: list[DoubanCategory] = []
    for item in payload.get("class") or []:
        if not isinstance(item, dict):
            continue
        category_id = _text(item.get("type_id"))
        category_name = _text(item.get("type_name"))
        if not category_id or not category_name:
            continue
        filters: list[CategoryFilter] = []
        list_filter = _list_keyword_filter(category_id)
        if list_filter is not None:
            filters.append(list_filter)
        filters.extend(
            group
            for group in (_map_filter_group(group_payload) for group_payload in raw_filters.get(category_id) or [])
            if group is not None
        )
        categories.append(DoubanCategory(type_id=category_id, type_name=category_name, filters=filters))
    return YouTubeCategoryConfig(categories=categories, raw_text=text)
```

- [ ] **Step 4: Run parser tests and verify pass**

Run: `uv run pytest tests/test_youtube_category_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit parser**

Run:

```bash
git add src/atv_player/controllers/youtube_category_config.py tests/test_youtube_category_config.py
git commit -m "feat: parse youtube category config"
```

Expected: commit succeeds.

---

### Task 2: Persist YouTube Category Source Settings

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Append to `tests/test_storage.py`:

```python
def test_settings_repository_persists_youtube_category_source(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.youtube_category_source_type = "remote"
    config.youtube_category_source_value = "http://example.test/youtube.json"
    config.youtube_category_cache_json = '{"class":[]}'
    config.youtube_category_cache_refreshed_at = 1779500000
    config.youtube_category_cache_error = ""

    repo.save_config(config)
    loaded = SettingsRepository(tmp_path / "app.db").load_config()

    assert loaded.youtube_category_source_type == "remote"
    assert loaded.youtube_category_source_value == "http://example.test/youtube.json"
    assert loaded.youtube_category_cache_json == '{"class":[]}'
    assert loaded.youtube_category_cache_refreshed_at == 1779500000
    assert loaded.youtube_category_cache_error == ""


def test_settings_repository_normalizes_invalid_youtube_category_source(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.youtube_category_source_type = "unknown"
    config.youtube_category_source_value = "  http://example.test/youtube.json  "
    config.youtube_category_cache_refreshed_at = -5

    repo.save_config(config)
    loaded = repo.load_config()

    assert loaded.youtube_category_source_type == "builtin"
    assert loaded.youtube_category_source_value == "http://example.test/youtube.json"
    assert loaded.youtube_category_cache_refreshed_at == 0
```

- [ ] **Step 2: Run storage tests and verify failure**

Run: `uv run pytest tests/test_storage.py -k "youtube_category_source" -q`

Expected: FAIL with `AttributeError` for missing `AppConfig` fields.

- [ ] **Step 3: Add AppConfig fields and normalization helpers**

In `src/atv_player/models.py`, add to `AppConfig` after `youtube_region`:

```python
    youtube_category_source_type: str = "builtin"
    youtube_category_source_value: str = ""
    youtube_category_cache_json: str = ""
    youtube_category_cache_refreshed_at: int = 0
    youtube_category_cache_error: str = ""
```

In `src/atv_player/storage.py`, add near other YouTube constants:

```python
_VALID_YOUTUBE_CATEGORY_SOURCE_TYPES = {"builtin", "remote", "local"}
```

Add helpers:

```python
def _normalize_youtube_category_source_type(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_YOUTUBE_CATEGORY_SOURCE_TYPES else "builtin"


def _normalize_youtube_category_source_value(value: object) -> str:
    return str(value or "").strip()


def _normalize_youtube_category_cache_refreshed_at(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized)
```

- [ ] **Step 4: Add SQLite columns and load/save wiring**

In `SettingsRepository._init_db`, add columns to `CREATE TABLE` after `youtube_region`:

```sql
                    youtube_category_source_type TEXT NOT NULL DEFAULT 'builtin',
                    youtube_category_source_value TEXT NOT NULL DEFAULT '',
                    youtube_category_cache_json TEXT NOT NULL DEFAULT '',
                    youtube_category_cache_refreshed_at INTEGER NOT NULL DEFAULT 0,
                    youtube_category_cache_error TEXT NOT NULL DEFAULT '',
```

Add `ALTER TABLE` blocks after the `youtube_region` block:

```python
            if "youtube_category_source_type" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN youtube_category_source_type TEXT NOT NULL DEFAULT 'builtin'"
                )
            if "youtube_category_source_value" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN youtube_category_source_value TEXT NOT NULL DEFAULT ''"
                )
            if "youtube_category_cache_json" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN youtube_category_cache_json TEXT NOT NULL DEFAULT ''"
                )
            if "youtube_category_cache_refreshed_at" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN youtube_category_cache_refreshed_at INTEGER NOT NULL DEFAULT 0"
                )
            if "youtube_category_cache_error" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN youtube_category_cache_error TEXT NOT NULL DEFAULT ''"
                )
```

Update the initial `INSERT`, `SELECT`, row unpacking, `AppConfig(...)`, `UPDATE`, and save parameter list with the five fields in the same order immediately after `youtube_region`.

Use these expressions in `load_config()`:

```python
            youtube_category_source_type=_normalize_youtube_category_source_type(youtube_category_source_type),
            youtube_category_source_value=_normalize_youtube_category_source_value(youtube_category_source_value),
            youtube_category_cache_json=str(youtube_category_cache_json or ""),
            youtube_category_cache_refreshed_at=_normalize_youtube_category_cache_refreshed_at(
                youtube_category_cache_refreshed_at
            ),
            youtube_category_cache_error=str(youtube_category_cache_error or "").strip(),
```

Use these expressions in `save_config()`:

```python
                    _normalize_youtube_category_source_type(config.youtube_category_source_type),
                    _normalize_youtube_category_source_value(config.youtube_category_source_value),
                    str(config.youtube_category_cache_json or ""),
                    _normalize_youtube_category_cache_refreshed_at(config.youtube_category_cache_refreshed_at),
                    str(config.youtube_category_cache_error or "").strip(),
```

- [ ] **Step 5: Run storage tests and verify pass**

Run: `uv run pytest tests/test_storage.py -k "youtube_category_source" -q`

Expected: PASS.

- [ ] **Step 6: Commit storage**

Run:

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist youtube category source settings"
```

Expected: commit succeeds.

---

### Task 3: Source Loader With Cache Fallback

**Files:**
- Modify: `src/atv_player/controllers/youtube_category_config.py`
- Test: `tests/test_youtube_category_config.py`

- [ ] **Step 1: Write failing source loader tests**

Append to `tests/test_youtube_category_config.py`:

```python
from atv_player.models import AppConfig


def test_load_youtube_category_config_fetches_remote_and_updates_cache() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
    )
    saved = []

    result = load_youtube_category_config(
        config,
        text_loader=lambda url: '{"class":[{"type_id":"電影","type_name":"電影"}],"filters":{}}',
        save_config=lambda: saved.append(config.youtube_category_cache_json),
        now=lambda: 123,
    )

    assert [category.type_name for category in result.categories] == ["電影"]
    assert config.youtube_category_cache_json.startswith('{"class"')
    assert config.youtube_category_cache_refreshed_at == 123
    assert config.youtube_category_cache_error == ""
    assert saved == [config.youtube_category_cache_json]


def test_load_youtube_category_config_uses_cache_when_remote_fails() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
        youtube_category_cache_json='{"class":[{"type_id":"缓存","type_name":"缓存"}],"filters":{}}',
    )

    result = load_youtube_category_config(
        config,
        text_loader=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")),
        save_config=lambda: None,
    )

    assert [category.type_name for category in result.categories] == ["缓存"]
    assert config.youtube_category_cache_error == "offline"


def test_load_youtube_category_config_falls_back_to_builtin_without_cache() -> None:
    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
    )

    result = load_youtube_category_config(
        config,
        text_loader=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")),
        save_config=lambda: None,
        builtin_categories=[DoubanCategory(type_id="cat", type_name="内置")],
    )

    assert [category.type_name for category in result.categories] == ["内置"]
```

Update imports:

```python
from atv_player.controllers.youtube_category_config import (
    YouTubeCategoryConfig,
    load_youtube_category_config,
    parse_youtube_category_config,
)
from atv_player.models import AppConfig, DoubanCategory
```

- [ ] **Step 2: Run source loader tests and verify failure**

Run: `uv run pytest tests/test_youtube_category_config.py -q`

Expected: FAIL with `ImportError` for `load_youtube_category_config`.

- [ ] **Step 3: Implement source loader**

Add to `src/atv_player/controllers/youtube_category_config.py`:

```python
from collections.abc import Callable
from pathlib import Path
import time

from atv_player.models import AppConfig


TextLoader = Callable[[str], str]
SaveConfig = Callable[[], None]
Now = Callable[[], int]


def _builtin_config(categories: list[DoubanCategory] | None) -> YouTubeCategoryConfig:
    return YouTubeCategoryConfig(categories=[DoubanCategory(c.type_id, c.type_name, list(c.filters)) for c in categories or []])


def _load_source_text(config: AppConfig, text_loader: TextLoader | None) -> str:
    source_type = str(config.youtube_category_source_type or "builtin").strip()
    source_value = str(config.youtube_category_source_value or "").strip()
    if source_type == "remote":
        if not source_value:
            raise ValueError("YouTube 远程分类配置 URL 为空")
        if text_loader is None:
            raise ValueError("缺少 YouTube 远程分类配置加载器")
        return text_loader(source_value)
    if source_type == "local":
        if not source_value:
            raise ValueError("YouTube 本地分类配置路径为空")
        return Path(source_value).read_text(encoding="utf-8")
    raise ValueError(f"不支持的 YouTube 分类配置源: {source_type}")


def load_youtube_category_config(
    config: AppConfig,
    *,
    text_loader: TextLoader | None = None,
    save_config: SaveConfig | None = None,
    now: Now | None = None,
    builtin_categories: list[DoubanCategory] | None = None,
) -> YouTubeCategoryConfig:
    source_type = str(config.youtube_category_source_type or "builtin").strip()
    if source_type == "builtin":
        return _builtin_config(builtin_categories)
    try:
        text = _load_source_text(config, text_loader)
        parsed = parse_youtube_category_config(text)
        if not parsed.categories:
            raise ValueError("YouTube 分类配置没有可用分类")
        config.youtube_category_cache_json = text
        config.youtube_category_cache_refreshed_at = int((now or time.time)())
        config.youtube_category_cache_error = ""
        if save_config is not None:
            save_config()
        return parsed
    except Exception as exc:
        config.youtube_category_cache_error = str(exc)
        if save_config is not None:
            save_config()
        cached_text = str(config.youtube_category_cache_json or "")
        if cached_text:
            try:
                cached = parse_youtube_category_config(cached_text)
                if cached.categories:
                    return cached
            except Exception:
                pass
        return _builtin_config(builtin_categories)
```

- [ ] **Step 4: Run source loader tests and verify pass**

Run: `uv run pytest tests/test_youtube_category_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit source loader**

Run:

```bash
git add src/atv_player/controllers/youtube_category_config.py tests/test_youtube_category_config.py
git commit -m "feat: load youtube category config sources"
```

Expected: commit succeeds.

---

### Task 4: Controller Categories, Query Planning, and New ID Format

**Files:**
- Modify: `src/atv_player/controllers/youtube_category_config.py`
- Modify: `src/atv_player/controllers/youtube_controller.py`
- Test: `tests/test_youtube_controller.py`

- [ ] **Step 1: Write failing controller tests**

Append to `tests/test_youtube_controller.py`:

```python
from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory


def test_youtube_controller_uses_configured_categories_and_tid_replaces_query() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
        category_config_loader=lambda: [
            DoubanCategory(
                type_id="電影",
                type_name="電影",
                filters=[
                    CategoryFilter(
                        key="tid",
                        name="类型",
                        options=[CategoryFilterOption(name="Netflix", value="netflix Full movie 电影")],
                    )
                ],
            )
        ],
    )

    categories = controller.load_categories()
    controller.load_items("電影", 1, filters={"tid": "netflix Full movie 电影"})

    assert [category.type_name for category in categories] == ["電影"]
    assert service.flat_calls == [("ytsearchall:netflix Full movie 电影", 1, 30)]


def test_youtube_controller_list_keyword_and_time_build_query() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(
        AppConfig(),
        yt_dlp_service=service,
        category_config_loader=lambda: [
            DoubanCategory(
                type_id="LIST:HDR,Girls HDR",
                type_name="HDR",
                filters=[
                    CategoryFilter(
                        key="list_keyword",
                        name="关键词",
                        options=[
                            CategoryFilterOption(name="HDR", value="HDR"),
                            CategoryFilterOption(name="Girls HDR", value="Girls HDR"),
                        ],
                    )
                ],
            )
        ],
    )

    controller.load_items("LIST:HDR,Girls HDR", 1, filters={"list_keyword": "Girls HDR", "time": "2024"})

    assert service.flat_calls == [("ytsearchall:Girls HDR 2024", 1, 30)]


def test_youtube_controller_emits_new_id_formats() -> None:
    service = FakeYtdlpService()
    controller = YouTubeController(AppConfig(), yt_dlp_service=service)

    items, _total = controller.load_items("cat_recommend", 1)

    assert items[0].vod_id == "abc123"


def test_youtube_controller_accepts_new_and_legacy_request_ids() -> None:
    service = ChannelYtdlpService()
    controller = YouTubeController(AppConfig(), yt_dlp_service=service)

    video_request = controller.build_request("yt:video:island12345")
    channel_request = controller.build_request("channel@UCX6OQ3DkcsbYNE6H8uQQuVA")

    assert video_request.vod.vod_id == "island12345"
    assert channel_request.vod.vod_id == "channel@UCX6OQ3DkcsbYNE6H8uQQuVA"
```

- [ ] **Step 2: Run controller tests and verify failure**

Run: `uv run pytest tests/test_youtube_controller.py -k "configured_categories or list_keyword or emits_new_id_formats or accepts_new" -q`

Expected: FAIL because `YouTubeController` does not accept `category_config_loader` and still emits `yt:*` ids.

- [ ] **Step 3: Add query-plan helpers**

In `src/atv_player/controllers/youtube_category_config.py`, add:

```python
@dataclass(slots=True)
class YouTubeQueryPlan:
    kind: str
    value: str
    unsupported_filters: dict[str, str] = field(default_factory=dict)


def normalize_youtube_vod_id(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("yt:video:"):
        return text.split(":", 2)[2]
    if text.startswith("yt:channel:"):
        return f"channel@{text.split(':', 2)[2]}"
    if text.startswith("yt:playlist:"):
        return f"playlist@{text.split(':', 2)[2]}"
    return text


def plan_youtube_query(category_id: str, filters: dict[str, str] | None = None) -> YouTubeQueryPlan:
    active = {str(key): str(value).strip() for key, value in (filters or {}).items() if str(value).strip()}
    base = normalize_youtube_vod_id(category_id)
    if base.startswith("LIST:"):
        keywords = [part.strip() for part in base.removeprefix("LIST:").split(",") if part.strip()]
        base = active.pop(LIST_KEYWORD_FILTER_KEY, keywords[0] if keywords else "")
    tid = active.pop("tid", "")
    if tid:
        base = normalize_youtube_vod_id(tid)
    unsupported = {
        key: active.pop(key)
        for key in list(active)
        if key in {"sort", "type", "format"}
    }
    suffixes = [active.pop("time", "")]
    suffixes.extend(active.values())
    query = " ".join(part for part in [base, *suffixes] if part).strip()
    if query.startswith("playlist@"):
        return YouTubeQueryPlan("playlist", query.removeprefix("playlist@"), unsupported)
    if query.startswith("channel@"):
        return YouTubeQueryPlan("channel", query.removeprefix("channel@"), unsupported)
    if query.startswith("@"):
        return YouTubeQueryPlan("channel", query, unsupported)
    return YouTubeQueryPlan("search", query, unsupported)
```

- [ ] **Step 4: Update controller to use loader, plans, and new ids**

In `src/atv_player/controllers/youtube_controller.py`:

Add imports:

```python
from atv_player.controllers.youtube_category_config import normalize_youtube_vod_id, plan_youtube_query
```

Extend `__init__` signature:

```python
        category_config_loader: Callable[[], list[DoubanCategory]] | None = None,
```

Store:

```python
        self._category_config_loader = category_config_loader
```

Add a module-level helper so app wiring can pass built-in categories to the source loader:

```python
def default_youtube_categories() -> list[DoubanCategory]:
    return [
        DoubanCategory(
            type_id=str(item["id"]),
            type_name=str(item["name"]),
            filters=_filters_for_category_id(str(item["id"])),
        )
        for item in sorted(_DEFAULT_CATEGORIES, key=lambda item: int(item["order"]))
    ]
```

Move the existing `_filters_for_category()` logic to a module-level helper so both `default_youtube_categories()` and `YouTubeController._filters_for_category()` can use it:

```python
def _filters_for_category_id(category_id: str) -> list[CategoryFilter]:
    options = [
        CategoryFilterOption(name=str(item["name"]), value=str(item["id"]))
        for item in sorted(_DEFAULT_FILTERS, key=lambda item: int(item["order"]))
        if item["categoryId"] == category_id
    ]
    return [CategoryFilter(key="filter", name="筛选", options=options)] if options else []
```

Change `load_categories()`:

```python
        if self._category_config_loader is not None:
            categories = [replace(category) for category in self._category_config_loader()]
        else:
            categories = default_youtube_categories()
```

Update `_map_entry()` ids:

```python
                vod_id=f"channel@{channel_id}",
```

```python
                vod_id=f"playlist@{playlist_id}",
```

```python
                vod_id=video_id,
```

Update `_map_entries()` prefix checks to `channel@` and bare video id checks through a helper:

```python
            if channels_only and not item.vod_id.startswith("channel@"):
                continue
            if videos_only and item.vod_id.startswith(("channel@", "playlist@")):
                continue
```

Update `_channel_ref_from_vod_id()` and thumbnail enrichment to use `channel@`.

Change category loading after login categories:

```python
        plan = plan_youtube_query(category_id, filters or {})
        if plan.unsupported_filters:
            logger.debug("YouTube unsupported search filters ignored: %s", plan.unsupported_filters)
        if not plan.value:
            return [], 0
        if plan.kind == "channel":
            request = self._build_channel_request(plan.value, f"channel@{plan.value}")
            items = [
                VodItem(vod_id=item.vod_id, vod_name=item.title, vod_pic=item.video_cover_override, vod_tag="file")
                for item in request.playlist
            ]
            return items, len(items)
        if plan.kind == "playlist":
            request = self._build_playlist_request(plan.value, f"playlist@{plan.value}")
            items = [
                VodItem(vod_id=item.vod_id, vod_name=item.title, vod_pic=item.video_cover_override, vod_tag="file")
                for item in request.playlist
            ]
            return items, len(items)
        query = plan.value
        entries = self._flat_entries(f"ytsearchall:{query}", page_number)
```

Update request builders:

```python
        vod_id = video_id
```

for video `VodItem` and `PlayItem`; use `playlist@{playlist_id}` and `channel@{channel_ref}` for playlist/channel `VodItem` and source ids.

Update `build_request()`:

```python
        normalized = normalize_youtube_vod_id(str(vod_id or "").strip())
        if normalized.startswith("UC"):
            normalized = f"channel@{normalized}"
        if normalized.startswith("playlist@"):
            return self._build_playlist_request(normalized.removeprefix("playlist@"), normalized)
        if normalized.startswith("channel@"):
            return self._build_channel_request(normalized.removeprefix("channel@"), normalized)
        if normalized.startswith("@"):
            return self._build_channel_request(normalized, f"channel@{normalized}")
        if normalized:
            return self._build_video_request(normalized, normalized)
        raise ValueError(f"没有可播放的项目: {vod_id}")
```

Update `_playback_url()`:

```python
        normalized = normalize_youtube_vod_id(value)
        if normalized.startswith(("http://", "https://")):
            return normalized
        if normalized.startswith(("channel@", "playlist@")):
            return normalized
        return _youtube_video_url(normalized)
```

- [ ] **Step 5: Run targeted controller tests and update existing expectations**

Run: `uv run pytest tests/test_youtube_controller.py -q`

Expected first run after implementation may fail existing tests expecting `yt:*`. Update those expectations to the new format:

- `yt:video:abc123` -> `abc123`
- `yt:channel:UC...` -> `channel@UC...`
- `yt:playlist:PL...` -> `playlist@PL...`
- `yt:channel:https://www.youtube.com/@channel-a` -> `channel@https://www.youtube.com/@channel-a`

Then rerun the command.

Expected: PASS.

- [ ] **Step 6: Commit controller behavior**

Run:

```bash
git add src/atv_player/controllers/youtube_category_config.py src/atv_player/controllers/youtube_controller.py tests/test_youtube_controller.py
git commit -m "feat: apply youtube category query plans"
```

Expected: commit succeeds.

---

### Task 5: Wire Source Loader Into the App

**Files:**
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing app wiring test**

Add or update a focused test in `tests/test_app.py` near the YouTube controller construction tests:

```python
def test_application_passes_youtube_category_loader_from_config(monkeypatch, tmp_path) -> None:
    captured = {}

    class FakeYouTubeController:
        def __init__(self, config, *, yt_dlp_service, category_config_loader=None, **kwargs):
            captured["config"] = config
            captured["loader"] = category_config_loader

    class AvailableYtdlp:
        def is_available(self):
            return True

    monkeypatch.setattr(app_module, "YouTubeController", FakeYouTubeController)
    repo = app_module.SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.youtube_category_source_type = "remote"
    config.youtube_category_source_value = "http://example.test/youtube.json"
    repo.save_config(config)

    app = app_module.Application(
        settings_repository=repo,
        yt_dlp_service=AvailableYtdlp(),
    )
    app._api_client = type("Api", (), {"get_text": lambda self, url: '{"class":[]}'})()
    app._create_main_window(config)

    assert callable(captured["loader"])
```

Adjust construction to match the existing `Application` test helpers if `Application(...)` requires additional dependencies.

- [ ] **Step 2: Run app wiring test and verify failure**

Run: `uv run pytest tests/test_app.py -k "youtube_category_loader" -q`

Expected: FAIL because `category_config_loader` is not passed.

- [ ] **Step 3: Pass category loader when constructing `YouTubeController`**

In `src/atv_player/app.py`, import:

```python
from atv_player.controllers.youtube_category_config import load_youtube_category_config
from atv_player.controllers.youtube_controller import YouTubeController, default_youtube_categories
```

Near YouTube controller construction, create:

```python
            def youtube_category_config_loader(config=config):
                loaded = load_youtube_category_config(
                    config,
                    text_loader=self._api_client.get_text if self._api_client is not None else None,
                    save_config=lambda: self._settings_repository.save_config(config),
                    builtin_categories=default_youtube_categories(),
                )
                return loaded.categories
```

Pass:

```python
                category_config_loader=youtube_category_config_loader,
```

Keep built-in categories inside `YouTubeController` when loader returns empty or when source type is built-in. If implementation needs built-in categories in the loader, expose a `default_youtube_categories()` helper from `youtube_controller.py` and pass it as `builtin_categories=default_youtube_categories()`.

- [ ] **Step 4: Run app wiring test and verify pass**

Run: `uv run pytest tests/test_app.py -k "youtube_category_loader" -q`

Expected: PASS.

- [ ] **Step 5: Commit app wiring**

Run:

```bash
git add src/atv_player/app.py tests/test_app.py
git commit -m "feat: wire youtube category source loader"
```

Expected: commit succeeds.

---

### Task 6: Advanced Settings UI

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing UI tests**

Append near existing Advanced Settings YouTube tests in `tests/test_main_window_ui.py`:

```python
def test_advanced_settings_dialog_shows_youtube_category_source_controls(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(
        youtube_category_source_type="remote",
        youtube_category_source_value="http://example.test/youtube.json",
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.youtube_category_source_combo.currentData() == "remote"
    assert dialog.youtube_category_source_edit.text() == "http://example.test/youtube.json"
    assert dialog.youtube_category_source_edit.isEnabled() is True
    assert dialog.youtube_category_local_path_edit.isEnabled() is False


def test_advanced_settings_dialog_saves_youtube_category_source(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.youtube_category_source_combo.setCurrentIndex(
        dialog.youtube_category_source_combo.findData("local")
    )
    dialog.youtube_category_local_path_edit.setText("/tmp/youtube.json")
    dialog._save()

    assert saved == [config]
    assert config.youtube_category_source_type == "local"
    assert config.youtube_category_source_value == "/tmp/youtube.json"
```

- [ ] **Step 2: Run UI tests and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "youtube_category_source" -q`

Expected: FAIL because the controls do not exist.

- [ ] **Step 3: Add controls while preserving existing style**

In `src/atv_player/ui/advanced_settings_dialog.py`:

Add imports:

```python
from PySide6.QtWidgets import QFileDialog
```

Create controls after existing YouTube region controls:

```python
        self.youtube_category_group = QGroupBox("分类配置")
        self.youtube_category_source_combo = FlatComboBox()
        self.youtube_category_source_combo.addItem("内置", "builtin")
        self.youtube_category_source_combo.addItem("远程 URL", "remote")
        self.youtube_category_source_combo.addItem("本地 JSON", "local")
        self.youtube_category_source_edit = QLineEdit()
        self.youtube_category_source_edit.setPlaceholderText("例如 http://192.168.50.60:4567/zx/json/youtube.json")
        self.youtube_category_local_path_edit = QLineEdit()
        self.youtube_category_local_path_edit.setPlaceholderText("选择本地 youtube.json 或 JSONC 文件")
        self.youtube_category_browse_button = QPushButton("选择")
        self.youtube_category_status_label = QLabel("")
        self.youtube_category_status_label.setWordWrap(True)
        self.youtube_category_test_button = QPushButton("测试加载")
        self.youtube_category_refresh_button = QPushButton("刷新缓存")
```

Initialize:

```python
        self.youtube_category_source_combo.setCurrentIndex(
            max(0, self.youtube_category_source_combo.findData(config.youtube_category_source_type))
        )
        if config.youtube_category_source_type == "local":
            self.youtube_category_local_path_edit.setText(config.youtube_category_source_value)
        else:
            self.youtube_category_source_edit.setText(config.youtube_category_source_value)
        self._sync_youtube_category_source_inputs()
```

Add layout below `self.youtube_group`:

```python
        youtube_category_layout = QFormLayout()
        youtube_category_layout.addRow("配置源", self.youtube_category_source_combo)
        youtube_category_layout.addRow("远程地址", self.youtube_category_source_edit)
        local_row = QHBoxLayout()
        local_row.addWidget(self.youtube_category_local_path_edit, 1)
        local_row.addWidget(self.youtube_category_browse_button)
        youtube_category_layout.addRow("本地文件", local_row)
        action_row = QHBoxLayout()
        action_row.addWidget(self.youtube_category_test_button)
        action_row.addWidget(self.youtube_category_refresh_button)
        action_row.addStretch(1)
        youtube_category_layout.addRow("操作", action_row)
        youtube_category_layout.addRow("状态", self.youtube_category_status_label)
        self.youtube_category_group.setLayout(youtube_category_layout)
        youtube_tab_layout.addWidget(self.youtube_category_group)
```

Add styling participation:

```python
            self.youtube_category_source_combo,
```

to the combo loop, and:

```python
            self.youtube_category_source_edit,
            self.youtube_category_local_path_edit,
```

to the line-edit loop.

Add methods:

```python
    def _sync_youtube_category_source_inputs(self) -> None:
        source_type = str(self.youtube_category_source_combo.currentData() or "builtin")
        self.youtube_category_source_edit.setEnabled(source_type == "remote")
        self.youtube_category_local_path_edit.setEnabled(source_type == "local")
        self.youtube_category_browse_button.setEnabled(source_type == "local")

    def _browse_youtube_category_file(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择 YouTube 分类配置",
            self.youtube_category_local_path_edit.text().strip(),
            "JSON files (*.json *.jsonc);;All files (*)",
        )
        if path:
            self.youtube_category_local_path_edit.setText(path)

    def _validated_youtube_category_values(self) -> tuple[str, str] | None:
        source_type = str(self.youtube_category_source_combo.currentData() or "builtin")
        if source_type not in {"builtin", "remote", "local"}:
            QMessageBox.warning(self, "YouTube 分类配置无效", "配置源无效")
            return None
        if source_type == "remote":
            value = self.youtube_category_source_edit.text().strip()
            if not value.startswith(("http://", "https://")):
                QMessageBox.warning(self, "YouTube 分类配置无效", "远程地址必须以 http:// 或 https:// 开头")
                return None
            return source_type, value
        if source_type == "local":
            value = self.youtube_category_local_path_edit.text().strip()
            if not value:
                QMessageBox.warning(self, "YouTube 分类配置无效", "请选择本地 JSON 文件")
                return None
            return source_type, value
        return source_type, ""
```

Connect:

```python
        self.youtube_category_source_combo.currentIndexChanged.connect(self._sync_youtube_category_source_inputs)
        self.youtube_category_browse_button.clicked.connect(self._browse_youtube_category_file)
```

In `_save()`, call validation and assign:

```python
        youtube_category_values = self._validated_youtube_category_values()
        if youtube_category_values is None:
            return
```

and:

```python
        self._config.youtube_category_source_type, self._config.youtube_category_source_value = youtube_category_values
```

Implement `测试加载` and `刷新缓存` in a later task if source loader injection is not yet available in the dialog. For this task, create disabled-safe handlers that set status text to `保存后刷新缓存可用` and wire full behavior in Task 7.

- [ ] **Step 4: Run UI tests and verify pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "youtube_category_source or youtube_settings" -q`

Expected: PASS.

- [ ] **Step 5: Commit UI controls**

Run:

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add youtube category source settings"
```

Expected: commit succeeds.

---

### Task 7: Test Load and Refresh Cache Actions

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing action tests**

Add tests:

```python
def test_advanced_settings_dialog_test_load_reports_counts(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(youtube_category_source_type="remote", youtube_category_source_value="http://example.test/youtube.json")
    dialog = AdvancedSettingsDialog(
        config,
        save_config=lambda: None,
        youtube_category_text_loader=lambda _url: '{"class":[{"type_id":"電影","type_name":"電影"}],"filters":{}}',
    )
    qtbot.addWidget(dialog)

    dialog._test_youtube_category_source()

    assert "1 个分类" in dialog.youtube_category_status_label.text()


def test_advanced_settings_dialog_refresh_cache_updates_config(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved = []
    config = AppConfig(youtube_category_source_type="remote", youtube_category_source_value="http://example.test/youtube.json")
    dialog = AdvancedSettingsDialog(
        config,
        save_config=lambda: saved.append(config.youtube_category_cache_json),
        youtube_category_text_loader=lambda _url: '{"class":[{"type_id":"電影","type_name":"電影"}],"filters":{}}',
    )
    qtbot.addWidget(dialog)

    dialog._refresh_youtube_category_cache()

    assert config.youtube_category_cache_json.startswith('{"class"')
    assert saved == [config.youtube_category_cache_json]
```

- [ ] **Step 2: Run action tests and verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "test_load_reports_counts or refresh_cache_updates" -q`

Expected: FAIL because the dialog does not accept `youtube_category_text_loader`.

- [ ] **Step 3: Inject loader and implement actions**

Update `AdvancedSettingsDialog.__init__` signature:

```python
        youtube_category_text_loader: Callable[[str], str] | None = None,
```

Store:

```python
        self._youtube_category_text_loader = youtube_category_text_loader
```

Import:

```python
from atv_player.controllers.youtube_category_config import load_youtube_category_config, parse_youtube_category_config
```

Add helper:

```python
    def _draft_youtube_category_config(self) -> AppConfig | None:
        values = self._validated_youtube_category_values()
        if values is None:
            return None
        source_type, source_value = values
        draft = AppConfig(
            youtube_category_source_type=source_type,
            youtube_category_source_value=source_value,
            youtube_category_cache_json=self._config.youtube_category_cache_json,
            youtube_category_cache_refreshed_at=self._config.youtube_category_cache_refreshed_at,
            youtube_category_cache_error=self._config.youtube_category_cache_error,
        )
        return draft

    def _set_youtube_category_status(self, category_count: int, filter_count: int) -> None:
        self.youtube_category_status_label.setText(f"加载成功：{category_count} 个分类，{filter_count} 组筛选")
```

Add actions:

```python
    def _test_youtube_category_source(self) -> None:
        draft = self._draft_youtube_category_config()
        if draft is None:
            return
        try:
            if draft.youtube_category_source_type == "builtin":
                self.youtube_category_status_label.setText("内置分类将在保存后使用")
                return
            text = (
                self._youtube_category_text_loader(draft.youtube_category_source_value)
                if draft.youtube_category_source_type == "remote" and self._youtube_category_text_loader is not None
                else Path(draft.youtube_category_source_value).read_text(encoding="utf-8")
            )
            parsed = parse_youtube_category_config(text)
            filter_count = sum(len(category.filters) for category in parsed.categories)
            self._set_youtube_category_status(len(parsed.categories), filter_count)
        except Exception as exc:
            self.youtube_category_status_label.setText(f"加载失败：{exc}")

    def _refresh_youtube_category_cache(self) -> None:
        draft = self._draft_youtube_category_config()
        if draft is None:
            return
        self._config.youtube_category_source_type = draft.youtube_category_source_type
        self._config.youtube_category_source_value = draft.youtube_category_source_value
        loaded = load_youtube_category_config(
            self._config,
            text_loader=self._youtube_category_text_loader,
            save_config=self._save_config,
        )
        filter_count = sum(len(category.filters) for category in loaded.categories)
        self._set_youtube_category_status(len(loaded.categories), filter_count)
```

Connect buttons:

```python
        self.youtube_category_test_button.clicked.connect(self._test_youtube_category_source)
        self.youtube_category_refresh_button.clicked.connect(self._refresh_youtube_category_cache)
```

Pass loader from `MainWindow._open_advanced_settings()`:

```python
            youtube_category_text_loader=getattr(self.api_client, "get_text", None),
```

Use `self._api_client.get_text` because `MainWindow` stores the API client on `_api_client`.

- [ ] **Step 4: Run action tests and verify pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "youtube_category_source or test_load_reports_counts or refresh_cache_updates" -q`

Expected: PASS.

- [ ] **Step 5: Commit actions**

Run:

```bash
git add src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: refresh youtube category config cache"
```

Expected: commit succeeds.

---

### Task 8: Bare Video ID Compatibility Outside YouTubeController

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/yt_dlp_service.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_yt_dlp_service.py`
- Test: `tests/test_player_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing compatibility tests**

Add focused tests:

```python
def test_ytdlp_service_can_resolve_bare_youtube_video_id() -> None:
    service = YtdlpPlaybackService()

    assert service.can_resolve("abc123xyz89") is True
```

In player controller tests, add:

```python
def test_player_controller_treats_bare_youtube_id_as_ytdlp_source() -> None:
    controller = PlayerController(FakeApiClient(), ytdlp_service=FakeYtdlpService())

    assert controller.can_resolve_direct_url("abc123xyz89") is True
```

Use the existing fake classes and method names from `tests/test_player_controller.py`; if the public method differs, test the existing direct URL dispatch helper that currently handles `yt:video:`.

- [ ] **Step 2: Run compatibility tests and verify failure**

Run:

```bash
uv run pytest tests/test_yt_dlp_service.py -k "bare_youtube_video_id" -q
uv run pytest tests/test_player_controller.py -k "bare_youtube_id" -q
```

Expected: FAIL because bare ids are not recognized.

- [ ] **Step 3: Add a shared video-id recognizer**

In `src/atv_player/yt_dlp_service.py`, add near URL normalization helpers:

```python
def looks_like_youtube_video_id(value: str) -> bool:
    text = str(value or "").strip()
    if text.startswith(("http://", "https://", "yt:")):
        return False
    return len(text) == 11 and all(char.isalnum() or char in {"_", "-"} for char in text)
```

Use it in canonical URL normalization:

```python
    if looks_like_youtube_video_id(candidate):
        return f"https://www.youtube.com/watch?v={candidate}"
```

Update `can_resolve()` URL checks to include `looks_like_youtube_video_id(value)`.

In `player_controller.py` and `player_window.py`, import or duplicate through `yt_dlp_service.looks_like_youtube_video_id` and extend the existing `yt:video:` checks.

- [ ] **Step 4: Run compatibility tests and update old expectations only when necessary**

Run:

```bash
uv run pytest tests/test_yt_dlp_service.py -k "youtube_id or canonical_youtube" -q
uv run pytest tests/test_player_controller.py -k "youtube" -q
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "youtube" -q
```

Expected: PASS.

- [ ] **Step 5: Commit compatibility**

Run:

```bash
git add src/atv_player/controllers/player_controller.py src/atv_player/yt_dlp_service.py src/atv_player/ui/player_window.py tests/test_yt_dlp_service.py tests/test_player_controller.py tests/test_player_window_ui.py
git commit -m "feat: accept bare youtube video ids"
```

Expected: commit succeeds.

---

### Task 9: Final Verification and Documentation

**Files:**
- Modify: `docs/help.md`
- Modify: `docs/TODO.md`
- Test: existing targeted suite

- [ ] **Step 1: Update user-facing docs**

In `docs/help.md`, update the YouTube settings section to mention:

```markdown
- **分类配置源**：可选择内置分类、远程 JSON/JSONC URL 或本地 JSON/JSONC 文件。远程/本地配置支持 TVBox 风格的 `class` 和 `filters`，加载失败时会优先使用上次成功缓存。
```

In `docs/TODO.md`, mark the YouTube custom category/filter item complete or add:

```markdown
- [x] YouTube 自定义分类与筛选条件，支持内置 / 远程 URL / 本地 JSON 配置源
```

- [ ] **Step 2: Run focused verification suite**

Run:

```bash
uv run pytest tests/test_youtube_category_config.py tests/test_youtube_controller.py tests/test_storage.py -q
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "youtube_category_source or youtube_settings or advanced_settings" -q
uv run pytest tests/test_yt_dlp_service.py -k "youtube" -q
uv run pytest tests/test_app.py -k "youtube" -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run lint/compile check**

Run:

```bash
uv run python -m py_compile src/atv_player/controllers/youtube_category_config.py src/atv_player/controllers/youtube_controller.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py
```

Expected: command exits with code 0.

- [ ] **Step 4: Commit docs and final fixes**

Run:

```bash
git add docs/help.md docs/TODO.md
git commit -m "docs: describe youtube category sources"
```

Expected: commit succeeds if docs changed. If only test expectation fixes remain from earlier tasks, include those files in the relevant feature commit instead of creating a docs-only empty commit.

- [ ] **Step 5: Final status check**

Run: `git status --short`

Expected: only pre-existing unrelated user changes remain, or no changes remain.

---

## Self-Review

- Spec coverage: the plan covers JSONC parsing, `class`/`filters`, `LIST:` expansion, single source storage, remote/local cache fallback, Advanced Settings UI with existing style, query planning, new id format, legacy id compatibility, and tests.
- Placeholder scan: no `TBD`, `TODO`, or "implement later" placeholders remain in task steps.
- Type consistency: the parser returns `YouTubeCategoryConfig`; controller receives `category_config_loader: Callable[[], list[DoubanCategory]]`; source loading works from `AppConfig`; UI saves the same five `AppConfig` fields defined in storage.
