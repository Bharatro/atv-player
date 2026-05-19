# Observability Log Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a structured, persistent, size-rotated application log system that unifies backend logs and player runtime logs, adds a user-controlled logging toggle, and exposes a filterable/exportable/clearable log console inside Advanced Settings.

**Architecture:** Keep storage and rotation logic in a dedicated non-Qt `AppLogService`, attach a `logging.Handler` bridge for backend loggers, and inject the same service into `MainWindow`, `AdvancedSettingsDialog`, and `PlayerWindow`. Persist the `logging_enabled` switch in `AppConfig`/`SettingsRepository`, short-circuit log writes when disabled, and render the global log console through a dedicated `LogConsoleWidget` hosted in a new `日志` tab.

**Tech Stack:** Python 3, stdlib `logging`, `json`, `gzip`, `pathlib`, PySide6 widgets, pytest, pytest-qt, sqlite

---

## File Map

- Create: `src/atv_player/log_store.py`
  Structured log record dataclasses, JSONL writer/reader, rotation/compression, filter/export/clear operations, and the backend `logging.Handler` bridge.

- Create: `src/atv_player/ui/log_console.py`
  Dedicated Qt widget for the global log console tab: toggle, filters, table, details, export, clear, refresh.

- Modify: `src/atv_player/models.py`
  Add persisted `logging_enabled` config field.

- Modify: `src/atv_player/storage.py`
  Add schema default, migration, load/save support for `logging_enabled`.

- Modify: `src/atv_player/logging_utils.py`
  Keep console bootstrap and add a reconfigurable structured handler path.

- Modify: `src/atv_player/app.py`
  Build the shared `AppLogService`, install the structured handler after config load, and pass the service into `MainWindow`.

- Modify: `src/atv_player/ui/main_window.py`
  Accept `app_log_service`, pass it into `PlayerWindow` and `AdvancedSettingsDialog`.

- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
  Add the `日志` tab, the `启用日志记录` checkbox, and host `LogConsoleWidget`.

- Modify: `src/atv_player/ui/player_window.py`
  Mirror playback log lines into `AppLogService`, add category/level/context-aware helpers, and short-circuit detailed logging when disabled.

- Modify: `src/atv_player/app.py`
  Enrich high-value backend lifecycle logs with structured categories and context.

- Modify: `src/atv_player/metadata/hydrator.py`
  Add metadata start/success/failure log boundaries.

- Modify: `src/atv_player/metadata/scrape.py`
  Add structured manual scrape search/apply boundaries.

- Modify: `src/atv_player/proxy/server.py`
  Add HLS proxy preparation/failure logs with URL summary and proxy result context.

- Modify: `src/atv_player/plugins/loader.py`
  Add plugin load/refresh boundaries and failure logging.

- Modify: `tests/test_storage.py`
  Cover config persistence/migration of `logging_enabled`.

- Create: `tests/test_log_store.py`
  Focused unit coverage for writing, rotating, compressing, reading, filtering, exporting, clearing, and disable-mode short-circuit.

- Modify: `tests/test_app.py`
  Cover structured-handler installation, config-driven enable/disable, and service injection into `MainWindow`.

- Modify: `tests/test_main_window_ui.py`
  Cover advanced-settings `日志` tab, toggle persistence, and log-console wiring.

- Modify: `tests/test_player_window_ui.py`
  Cover playback-log mirroring, disable-mode short-circuit, and category/level emission for key troubleshooting events.

---

### Task 1: Persist The Logging Toggle In AppConfig And SettingsRepository

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing persistence and migration tests**

Add these tests to `tests/test_storage.py` near the existing config round-trip and migration coverage:

```python
def test_settings_repository_round_trip_persists_logging_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(logging_enabled=False)
    repo.save_config(config)
    saved = repo.load_config()

    assert saved.logging_enabled is False
    assert saved == config


def test_settings_repository_defaults_logging_enabled_to_true(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    assert repo.load_config().logging_enabled is True


def test_settings_repository_migrates_missing_logging_enabled_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                theme_mode TEXT NOT NULL DEFAULT 'system',
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                network_proxy_mode TEXT NOT NULL DEFAULT 'direct',
                network_proxy_url TEXT NOT NULL DEFAULT '',
                network_proxy_bypass_rules TEXT NOT NULL DEFAULT '[]',
                network_proxy_rules TEXT NOT NULL DEFAULT '[]',
                youtube_cookie_browser TEXT NOT NULL DEFAULT '',
                mpv_cache_size_mb INTEGER NOT NULL DEFAULT 512,
                mpv_hwdec_mode TEXT NOT NULL DEFAULT 'auto-safe',
                mpv_network_timeout_seconds INTEGER NOT NULL DEFAULT 15,
                mpv_default_readahead_secs INTEGER NOT NULL DEFAULT 20,
                mpv_extra_options TEXT NOT NULL DEFAULT '',
                playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]',
                global_search_hot_source TEXT NOT NULL DEFAULT '360'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, theme_mode,
                metadata_enhancement_enabled, episode_title_enhancement_enabled,
                metadata_douban_cookie, metadata_tmdb_api_key, metadata_bangumi_access_token,
                network_proxy_mode, network_proxy_url, network_proxy_bypass_rules,
                network_proxy_rules, youtube_cookie_browser, mpv_cache_size_mb,
                mpv_hwdec_mode, mpv_network_timeout_seconds, mpv_default_readahead_secs,
                mpv_extra_options, playback_auto_switch_source_on_failure, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, player_log_visible, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode,
                preferred_danmaku_uniform_color, preferred_danmaku_position_preset,
                preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history, global_search_hot_source
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', 'system',
                1, 1, '', '', '', 'direct', '', '[]', '[]', '', 512,
                'auto-safe', 15, 20, '', 0, '/', 'main', 'browse', '',
                '', '', '', '', 0, 100, 0, 0, 1, '', 1, 1, 'static',
                'source', '#FFFFFF', 'top', 1.0, 32, NULL, NULL, NULL,
                NULL, 'douban', '', '', '[]', '360'
            )
            """
        )

    repo = SettingsRepository(db_path)
    assert repo.load_config().logging_enabled is True
```

- [ ] **Step 2: Run the focused storage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_storage.py -k "logging_enabled" -v
```

Expected:

- The new tests fail because `AppConfig` has no `logging_enabled` field.
- The repository schema, loader, and saver do not know about the new column.

- [ ] **Step 3: Implement the config field and repository support**

Update `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    theme_mode: str = "system"
    logging_enabled: bool = True
    metadata_enhancement_enabled: bool = True
    ...
```

Add a normalizer to `src/atv_player/storage.py`:

```python
def _normalize_logging_enabled(value: object) -> bool:
    return bool(value)
```

Add the schema default and migration:

```python
                CREATE TABLE IF NOT EXISTS app_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    base_url TEXT NOT NULL,
                    username TEXT NOT NULL,
                    token TEXT NOT NULL,
                    vod_token TEXT NOT NULL,
                    theme_mode TEXT NOT NULL DEFAULT 'system',
                    logging_enabled INTEGER NOT NULL DEFAULT 1,
                    metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                    ...
                )
```

```python
            if "logging_enabled" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN logging_enabled INTEGER NOT NULL DEFAULT 1"
                )
```

Load/save the field:

```python
            logging_enabled=_normalize_logging_enabled(logging_enabled),
```

```python
                    logging_enabled = ?,
```

```python
                    int(config.logging_enabled),
```

- [ ] **Step 4: Run the focused storage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_storage.py -k "logging_enabled" -v
```

Expected:

- All three new tests pass.
- Existing config equality semantics remain intact.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist logging toggle in app config"
```

---

### Task 2: Build The Structured Log Store Runtime

**Files:**
- Create: `src/atv_player/log_store.py`
- Create: `tests/test_log_store.py`

- [ ] **Step 1: Write the failing log-store tests**

Create `tests/test_log_store.py` with focused service coverage:

```python
from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

from atv_player.log_store import AppLogEvent, AppLogFilter, AppLogService, StructuredJsonlHandler


def test_app_log_service_writes_jsonl_record(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=10_000_000, max_archives=5)

    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:00.000",
            level="INFO",
            source="app",
            category="app",
            message="Application initialized",
            module="atv_player.app",
        )
    )

    active_path = tmp_path / "logs" / "application.jsonl"
    payload = json.loads(active_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["message"] == "Application initialized"
    assert payload["category"] == "app"


def test_app_log_service_rotates_and_compresses_after_size_limit(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=180, max_archives=5)

    for index in range(8):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:0{index}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"event-{index}-" + ("x" * 40),
                module="atv_player.app",
            )
        )

    archives = sorted((tmp_path / "logs").glob("application.*.jsonl.gz"))
    assert archives
    with gzip.open(archives[0], "rt", encoding="utf-8") as handle:
        archived_lines = [json.loads(line)["message"] for line in handle if line.strip()]
    assert archived_lines


def test_app_log_service_keeps_only_five_archives(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=160, max_archives=5)

    for index in range(40):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:{index:02d}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"rotation-{index}-" + ("y" * 40),
                module="atv_player.app",
            )
        )

    assert len(list((tmp_path / "logs").glob("application.*.jsonl.gz"))) == 5


def test_app_log_service_reads_filters_and_exports_records(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=10_000_000, max_archives=5)
    export_path = tmp_path / "filtered.log"

    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:00.000",
            level="ERROR",
            source="playback",
            category="player",
            message="播放失败: boom",
            module="atv_player.ui.player_window",
            vod_name="测试剧",
            episode_title="第1集",
        )
    )
    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:01.000",
            level="INFO",
            source="app",
            category="network",
            message="Proxy prepared",
            module="atv_player.proxy.server",
        )
    )

    records = service.load_records(limit=2000, log_filter=AppLogFilter(query="测试剧", source="playback", level="ERROR"))
    assert [record.message for record in records] == ["播放失败: boom"]

    service.export_records(records, export_path)
    exported = export_path.read_text(encoding="utf-8")
    assert "播放失败: boom" in exported
    assert "测试剧" in exported


def test_app_log_service_clear_removes_active_and_archives(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=160, max_archives=5)
    for index in range(30):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:{index:02d}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"clear-{index}-" + ("z" * 40),
                module="atv_player.app",
            )
        )

    service.clear()

    assert list((tmp_path / "logs").glob("*")) == []


def test_structured_handler_noops_when_logging_disabled(tmp_path: Path) -> None:
    enabled = {"value": False}
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: enabled["value"], max_bytes=10_000_000, max_archives=5)
    handler = StructuredJsonlHandler(service)
    logger = logging.getLogger("test_structured_handler_noops_when_logging_disabled")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("disabled")

    assert not (tmp_path / "logs" / "application.jsonl").exists()
```

- [ ] **Step 2: Run the focused log-store tests to verify they fail**

Run:

```bash
uv run pytest tests/test_log_store.py -v
```

Expected:

- The run fails because `src/atv_player/log_store.py` does not exist.

- [ ] **Step 3: Implement the log store and logging handler**

Create `src/atv_player/log_store.py` with the core dataclasses and service:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
import json
import logging
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AppLogEvent:
    timestamp: str
    level: str
    source: str
    category: str
    message: str
    module: str
    vod_id: str = ""
    vod_name: str = ""
    episode_title: str = ""
    session_id: str = ""
    url_summary: str = ""
    source_group_index: int = -1
    source_index: int = -1
    playlist_index: int = -1
    proxy_mode: str = ""
    exception: str = ""


@dataclass(frozen=True, slots=True)
class AppLogFilter:
    query: str = ""
    source: str = ""
    level: str = ""
    category: str = ""


class AppLogService:
    def __init__(
        self,
        logs_dir: Path,
        *,
        enabled_getter,
        max_bytes: int = 10 * 1024 * 1024,
        max_archives: int = 5,
    ) -> None:
        self._logs_dir = Path(logs_dir)
        self._enabled_getter = enabled_getter
        self._max_bytes = max_bytes
        self._max_archives = max_archives
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def active_path(self) -> Path:
        return self._logs_dir / "application.jsonl"

    def write_event(self, event: AppLogEvent) -> None:
        if not self._enabled_getter():
            return
        self._rotate_if_needed()
        with self.active_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def load_records(self, *, limit: int, log_filter: AppLogFilter) -> list[AppLogEvent]:
        records = [record for record in self._iter_records_newest_first() if self._matches(record, log_filter)]
        return records[:limit]

    def export_records(self, records: list[AppLogEvent], target_path: Path) -> None:
        lines = [
            f"[{record.timestamp}] {record.level} {record.source}/{record.category} {record.message}"
            + (f" vod={record.vod_name}" if record.vod_name else "")
            + (f" episode={record.episode_title}" if record.episode_title else "")
            for record in records
        ]
        target_path.write_text("\n".join(lines), encoding="utf-8")

    def clear(self) -> None:
        for path in self._logs_dir.glob("*"):
            if path.is_file():
                path.unlink()
```

Implement rotation, archive cleanup, archive reading, and the handler in the same file:

```python
    def _rotate_if_needed(self) -> None:
        if not self.active_path.exists():
            return
        if self.active_path.stat().st_size < self._max_bytes:
            return
        archive_name = f"application.{self._archive_timestamp()}.jsonl.gz"
        archive_path = self._logs_dir / archive_name
        with self.active_path.open("rb") as source:
            with gzip.open(archive_path, "wb") as target:
                target.write(source.read())
        self.active_path.unlink()
        self._trim_archives()

    def _trim_archives(self) -> None:
        archives = sorted(self._logs_dir.glob("application.*.jsonl.gz"))
        while len(archives) > self._max_archives:
            archives.pop(0).unlink()

    def _iter_records_newest_first(self) -> list[AppLogEvent]:
        paths = sorted(self._logs_dir.glob("application.*.jsonl.gz"), reverse=True)
        if self.active_path.exists():
            paths.insert(0, self.active_path)
        records: list[AppLogEvent] = []
        for path in paths:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    records.extend(self._decode_lines(handle))
            else:
                records.extend(self._decode_lines(path.read_text(encoding="utf-8").splitlines()))
        records.sort(key=lambda item: item.timestamp, reverse=True)
        return records

    def _decode_lines(self, lines) -> list[AppLogEvent]:
        decoded: list[AppLogEvent] = []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            decoded.append(AppLogEvent(**payload))
        return decoded

    def _matches(self, record: AppLogEvent, log_filter: AppLogFilter) -> bool:
        query = log_filter.query.strip().lower()
        haystacks = [record.message, record.vod_name, record.episode_title]
        if query and not any(query in value.lower() for value in haystacks if value):
            return False
        if log_filter.source and record.source != log_filter.source:
            return False
        if log_filter.level and record.level != log_filter.level:
            return False
        if log_filter.category and record.category != log_filter.category:
            return False
        return True


class StructuredJsonlHandler(logging.Handler):
    def __init__(self, service: AppLogService) -> None:
        super().__init__()
        self._service = service

    def emit(self, record: logging.LogRecord) -> None:
        event = AppLogEvent(
            timestamp=self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            level=record.levelname,
            source=str(getattr(record, "log_source", "app") or "app"),
            category=str(getattr(record, "log_category", "app") or "app"),
            message=record.getMessage(),
            module=record.name,
            vod_id=str(getattr(record, "vod_id", "") or ""),
            vod_name=str(getattr(record, "vod_name", "") or ""),
            episode_title=str(getattr(record, "episode_title", "") or ""),
            session_id=str(getattr(record, "session_id", "") or ""),
            url_summary=str(getattr(record, "url_summary", "") or ""),
            proxy_mode=str(getattr(record, "proxy_mode", "") or ""),
            exception=self.formatException(record.exc_info) if record.exc_info else "",
        )
        self._service.write_event(event)
```

- [ ] **Step 4: Run the focused log-store tests to verify they pass**

Run:

```bash
uv run pytest tests/test_log_store.py -v
```

Expected:

- All six tests pass.
- Rotation produces `.jsonl.gz` archives and caps them at five files.
- Disable mode prevents file creation.

- [ ] **Step 5: Commit the log-store slice**

```bash
git add tests/test_log_store.py src/atv_player/log_store.py
git commit -m "feat: add structured log store runtime"
```

---

### Task 3: Wire App Startup And Backend Loggers To The Structured Handler

**Files:**
- Modify: `src/atv_player/logging_utils.py`
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing startup and handler tests**

Add these tests to `tests/test_app.py`:

```python
def test_build_application_installs_app_log_service(monkeypatch, tmp_path) -> None:
    created = {}

    class FakeService:
        def __init__(self, logs_dir, *, enabled_getter, max_bytes, max_archives) -> None:
            created["logs_dir"] = logs_dir
            created["enabled"] = enabled_getter()
            created["max_bytes"] = max_bytes
            created["max_archives"] = max_archives

    monkeypatch.setattr(app_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "AppLogService", FakeService)

    app, repo = app_module.build_application()

    assert created["logs_dir"] == tmp_path / "logs"
    assert created["enabled"] is True
    assert created["max_bytes"] == 10 * 1024 * 1024
    assert created["max_archives"] == 5
    assert getattr(app, "_app_log_service", None) is not None
    assert repo.load_config().logging_enabled is True


def test_app_coordinator_reconfigures_logging_with_structured_handler(monkeypatch, tmp_path) -> None:
    app = QApplication.instance()
    assert app is not None
    repo = app_module.SettingsRepository(tmp_path / "app.db")
    repo.save_config(AppConfig(logging_enabled=False))

    configure_calls: list[tuple[str, object]] = []

    def record_configure(level: str, structured_handler=None) -> None:
        configure_calls.append((level, structured_handler))

    monkeypatch.setattr(app_module, "configure_logging", record_configure)
    setattr(app, "_app_log_service", object())

    coordinator = app_module.AppCoordinator(repo)
    coordinator.start()

    assert configure_calls[-1][0] == "INFO"
    assert configure_calls[-1][1] is not None
```

Keep `tests/test_main.py` asserting the bootstrap call still happens:

```python
assert configured_levels == ["INFO"]
```

- [ ] **Step 2: Run the focused startup tests to verify they fail**

Run:

```bash
uv run pytest tests/test_main.py tests/test_app.py -k "app_log_service or structured_handler or configures_logging_before_start" -v
```

Expected:

- `build_application()` currently does not create or attach any log service.
- `AppCoordinator.start()` currently does not reconfigure logging with a structured handler.

- [ ] **Step 3: Implement the two-phase logging bootstrap**

Update `src/atv_player/logging_utils.py`:

```python
from __future__ import annotations

import logging


def configure_logging(level: str = "INFO", structured_handler: logging.Handler | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(console)

    if structured_handler is not None:
        structured_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        root.addHandler(structured_handler)
```

Update `src/atv_player/app.py` imports and `build_application()`:

```python
from atv_player.log_store import AppLogService, StructuredJsonlHandler
from atv_player.logging_utils import configure_logging
```

```python
def build_application() -> tuple[QApplication, SettingsRepository]:
    app = QApplication([])
    ...
    data_dir = app_data_dir()
    repo = SettingsRepository(data_dir / "app.db")
    config = repo.load_config()
    app_log_service = AppLogService(
        data_dir / "logs",
        enabled_getter=lambda: repo.load_config().logging_enabled,
        max_bytes=10 * 1024 * 1024,
        max_archives=5,
    )
    setattr(app, "_app_log_service", app_log_service)
    configure_logging("INFO", StructuredJsonlHandler(app_log_service))
    install_theme(app, ThemeManager(), config.theme_mode)
    ...
    return app, repo
```

Update `AppCoordinator.start()` to keep the handler aligned with current repo state before main-window/login work:

```python
    def start(self) -> QWidget:
        config = self.repo.load_config()
        app = QApplication.instance()
        app_log_service = getattr(app, "_app_log_service", None) if app is not None else None
        if app_log_service is not None:
            configure_logging("INFO", StructuredJsonlHandler(app_log_service))
        logger.info("App start view=%s", decide_start_view(config), extra={"log_category": "app"})
        ...
```

- [ ] **Step 4: Run the focused startup tests to verify they pass**

Run:

```bash
uv run pytest tests/test_main.py tests/test_app.py -k "app_log_service or structured_handler or configures_logging_before_start" -v
```

Expected:

- `main()` still performs the initial console bootstrap.
- `build_application()` attaches an `AppLogService`.
- `AppCoordinator.start()` reconfigures root logging with the structured handler.

- [ ] **Step 5: Commit the startup-wiring slice**

```bash
git add tests/test_main.py tests/test_app.py src/atv_player/logging_utils.py src/atv_player/app.py
git commit -m "feat: wire structured logging into app startup"
```

---

### Task 4: Enrich Backend Boundary Logs With Structured Categories And Context

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/metadata/hydrator.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Modify: `src/atv_player/proxy/server.py`
- Modify: `src/atv_player/plugins/loader.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing backend log-coverage tests**

Add targeted `caplog` tests in `tests/test_app.py`:

```python
def test_start_live_background_refresh_logs_failures_with_live_category(monkeypatch, caplog) -> None:
    class FailingLiveEpgService:
        def load_config(self):
            return type("Cfg", (), {"epg_url": "https://demo", "last_refreshed_at": 0})()

        def refresh(self):
            raise RuntimeError("epg boom")

    class FakeLiveSourceManager:
        def list_sources(self):
            return []

    coordinator = app_module.AppCoordinator(FakeRepo())

    with caplog.at_level(logging.ERROR):
        coordinator._start_live_background_refresh(FakeLiveSourceManager(), FailingLiveEpgService())
        for thread in threading.enumerate():
            if thread is not threading.current_thread():
                thread.join(timeout=1)

    assert "Background refresh failed target=epg" in caplog.text


def test_metadata_hydrator_logs_failure_with_metadata_category(monkeypatch, caplog) -> None:
    hydrator = MetadataHydrator(providers=[], binding_repository=None, cache=MetadataCache())

    with caplog.at_level(logging.WARNING):
        hydrator._logger.warning("metadata failed", extra={"log_category": "metadata"})

    assert "metadata failed" in caplog.text
```

- [ ] **Step 2: Run the focused backend logging tests to verify they fail**

Run:

```bash
uv run pytest tests/test_app.py -k "live_background_refresh_logs_failures_with_live_category or metadata_hydrator_logs_failure_with_metadata_category" -v
```

Expected:

- At least one test fails because the code does not consistently attach structured categories or explicit start/result boundaries.

- [ ] **Step 3: Add explicit structured `extra` payloads at backend boundaries**

In `src/atv_player/app.py`, enrich existing log lines:

```python
logger.info(
    "Application initialized data_dir=%s",
    data_dir,
    extra={"log_category": "app", "log_source": "app"},
)
```

```python
logger.info(
    "Background refresh finished target=epg",
    extra={"log_category": "live", "log_source": "app"},
)
logger.exception(
    "Background refresh failed target=epg",
    extra={"log_category": "live", "log_source": "app"},
)
```

In `src/atv_player/metadata/hydrator.py`:

```python
logger.info(
    "Metadata hydration start vod_id=%s title=%s",
    vod.vod_id,
    vod.vod_name,
    extra={"log_category": "metadata", "log_source": "app", "vod_id": vod.vod_id, "vod_name": vod.vod_name},
)
```

```python
logger.warning(
    "Metadata hydration failed vod_id=%s error=%s",
    vod.vod_id,
    exc,
    extra={"log_category": "metadata", "log_source": "app", "vod_id": vod.vod_id, "vod_name": vod.vod_name},
)
```

In `src/atv_player/metadata/scrape.py`:

```python
logger.info(
    "Metadata scrape search title=%s provider=%s",
    query.title,
    provider_filter or "all",
    extra={"log_category": "metadata", "log_source": "app"},
)
```

In `src/atv_player/proxy/server.py`:

```python
logger.info(
    "Proxy prepare origin=%s mode=%s",
    summarized_url,
    proxy_mode,
    extra={"log_category": "network", "log_source": "app", "url_summary": summarized_url, "proxy_mode": proxy_mode},
)
```

In `src/atv_player/plugins/loader.py`:

```python
logger.info(
    "Plugin load start path=%s",
    plugin_dir,
    extra={"log_category": "plugin", "log_source": "app"},
)
logger.exception(
    "Plugin load failed path=%s",
    plugin_dir,
    extra={"log_category": "plugin", "log_source": "app"},
)
```

- [ ] **Step 4: Run the focused backend logging tests to verify they pass**

Run:

```bash
uv run pytest tests/test_app.py -k "live_background_refresh_logs_failures_with_live_category or metadata_hydrator_logs_failure_with_metadata_category" -v
```

Expected:

- The targeted logging tests pass.
- Existing `caplog`-based backend tests keep passing because message text is preserved.

- [ ] **Step 5: Commit the backend-enrichment slice**

```bash
git add tests/test_app.py src/atv_player/app.py src/atv_player/metadata/hydrator.py src/atv_player/metadata/scrape.py src/atv_player/proxy/server.py src/atv_player/plugins/loader.py
git commit -m "feat: add structured backend troubleshooting logs"
```

---

### Task 5: Mirror Playback Logs Into The Shared Log Store And Gate Them By `logging_enabled`

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing playback-mirroring tests**

Add focused tests to `tests/test_player_window_ui.py`:

```python
class RecordingLogService:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def write_event(self, event) -> None:
        self.events.append(event.__dict__.copy())


def test_player_window_mirrors_playback_logs_into_app_log_service(qtbot) -> None:
    service = RecordingLogService()
    config = AppConfig(logging_enabled=True)
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None, app_log_service=service)
    qtbot.addWidget(window)

    window._append_log("播放失败: boom", level="ERROR", category="player")

    assert "播放失败: boom" in window.log_view.toPlainText()
    assert service.events[-1]["message"] == "播放失败: boom"
    assert service.events[-1]["source"] == "playback"
    assert service.events[-1]["category"] == "player"
    assert service.events[-1]["level"] == "ERROR"


def test_player_window_skips_detailed_log_accumulation_when_logging_disabled(qtbot) -> None:
    service = RecordingLogService()
    config = AppConfig(logging_enabled=False)
    window = PlayerWindow(FakePlayerController(), config=config, save_config=lambda: None, app_log_service=service)
    qtbot.addWidget(window)

    window._append_log("播放失败: boom", level="ERROR", category="player")

    assert window.log_view.toPlainText() == ""
    assert service.events == []
```

Add a main-window wiring test to `tests/test_main_window_ui.py`:

```python
def test_main_window_passes_log_service_to_advanced_settings_dialog(qtbot, monkeypatch) -> None:
    opened: list[object] = []

    class FakeDialog:
        def __init__(self, config, save_config, parent=None, apply_theme=None, app_log_service=None) -> None:
            del config, save_config, parent, apply_theme
            opened.append(app_log_service)

        def exec(self) -> int:
            return 1

    monkeypatch.setattr(main_window_module, "AdvancedSettingsDialog", FakeDialog)
    service = object()
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
        save_config=lambda: None,
        app_log_service=service,
    )
    qtbot.addWidget(window)

    window._open_advanced_settings()

    assert opened == [service]
```

- [ ] **Step 2: Run the focused playback-wiring tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "mirrors_playback_logs_into_app_log_service or skips_detailed_log_accumulation_when_logging_disabled" -v
uv run pytest tests/test_main_window_ui.py -k "passes_log_service_to_advanced_settings_dialog" -v
```

Expected:

- `PlayerWindow` has no `app_log_service` constructor argument.
- `_append_log()` has no category/level-aware mirror path and no disable-mode short-circuit.
- `MainWindow` has no `app_log_service` wiring path for `AdvancedSettingsDialog`.

- [ ] **Step 3: Implement constructor injection and playback log mirroring**

Extend `PlayerWindow.__init__` in `src/atv_player/ui/player_window.py`:

```python
    def __init__(
        self,
        controller,
        config=None,
        save_config=None,
        m3u8_ad_filter=None,
        playback_parser_service=None,
        default_video_cover_loader=None,
        app_log_service=None,
    ) -> None:
        ...
        self._app_log_service = app_log_service
```

Update the log helper:

```python
    def _append_log(
        self,
        message: str,
        *,
        dedupe: bool = False,
        level: str = "INFO",
        category: str = "player",
    ) -> None:
        if not message:
            return
        if self.config is not None and not getattr(self.config, "logging_enabled", True):
            return
        if dedupe and self._last_log_message == message:
            return
        formatted_message = self._format_log_line(message)
        existing_text = self.log_view.toPlainText()
        if existing_text:
            self.log_view.append(formatted_message)
        else:
            self.log_view.setPlainText(formatted_message)
        self._last_log_message = message
        self._mirror_playback_log(message, level=level, category=category)
```

Add the mirror helper:

```python
    def _mirror_playback_log(self, message: str, *, level: str, category: str) -> None:
        if self._app_log_service is None:
            return
        current_item = None
        if self.session is not None and 0 <= self.current_index < len(self.session.playlist):
            current_item = self.session.playlist[self.current_index]
        self._app_log_service.write_event(
            AppLogEvent(
                timestamp=datetime.now().isoformat(timespec="milliseconds"),
                level=level,
                source="playback",
                category=category,
                message=message,
                module=__name__,
                vod_id="" if self.session is None else self.session.vod.vod_id,
                vod_name="" if self.session is None else self.session.vod.vod_name,
                episode_title="" if current_item is None else playlist_item_display_title(current_item, "episode"),
                session_id="" if self.session is None else f"{self.session.vod.vod_id}:{self.current_index}",
                source_group_index=-1 if self.session is None else self.session.source_group_index,
                source_index=-1 if self.session is None else self.session.source_index,
                playlist_index=-1 if self.session is None else self.current_index,
            )
        )
```

Wire `MainWindow` and `AppCoordinator`:

```python
class MainWindow(...):
    def __init__(..., app_log_service=None, ...) -> None:
        ...
        self._app_log_service = app_log_service
```

```python
        dialog = AdvancedSettingsDialog(
            self.config,
            self._save_config,
            self,
            apply_theme=self._apply_application_theme,
            app_log_service=self._app_log_service,
        )
```

```python
        self.main_window = MainWindow(
            ...
            app_log_service=getattr(QApplication.instance(), "_app_log_service", None),
        )
```

- [ ] **Step 4: Run the focused playback-wiring tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "mirrors_playback_logs_into_app_log_service or skips_detailed_log_accumulation_when_logging_disabled" -v
uv run pytest tests/test_main_window_ui.py -k "passes_log_service_to_advanced_settings_dialog" -v
```

Expected:

- Playback logs are mirrored into the shared service when enabled.
- Detailed playback logging is fully skipped when disabled.
- `MainWindow` passes the shared service into `AdvancedSettingsDialog`.

- [ ] **Step 5: Commit the playback-wiring slice**

```bash
git add tests/test_player_window_ui.py tests/test_main_window_ui.py src/atv_player/ui/player_window.py src/atv_player/ui/main_window.py src/atv_player/app.py
git commit -m "feat: mirror playback logs into shared log store"
```

---

### Task 6: Add The Advanced Settings `日志` Tab With Toggle, Filters, Export, Clear, And Refresh

**Files:**
- Create: `src/atv_player/ui/log_console.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing log-console UI tests**

Add these tests to `tests/test_main_window_ui.py`:

```python
def test_advanced_settings_dialog_adds_logs_tab_with_logging_toggle(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(AppConfig(logging_enabled=False), save_config=lambda: None, app_log_service=None)
    qtbot.addWidget(dialog)

    tab_labels = [dialog.settings_tabs.tabText(index) for index in range(dialog.settings_tabs.count())]
    assert "日志" in tab_labels
    assert dialog.logging_enabled_checkbox.isChecked() is False


def test_advanced_settings_dialog_saves_logging_enabled_toggle(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved: list[bool] = []
    config = AppConfig(logging_enabled=True)
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config.logging_enabled), app_log_service=None)
    qtbot.addWidget(dialog)

    dialog.logging_enabled_checkbox.setChecked(False)
    dialog.save_button.click()

    assert config.logging_enabled is False
    assert saved == [False]


def test_log_console_widget_filters_and_shows_details(qtbot) -> None:
    from atv_player.log_store import AppLogEvent
    from atv_player.ui.log_console import LogConsoleWidget

    class FakeService:
        def __init__(self) -> None:
            self.loaded_filters = []

        def load_records(self, *, limit: int, log_filter):
            self.loaded_filters.append((limit, log_filter.query, log_filter.source, log_filter.level, log_filter.category))
            return [
                AppLogEvent(
                    timestamp="2026-05-19T12:00:00.000",
                    level="ERROR",
                    source="playback",
                    category="player",
                    message="播放失败: boom",
                    module="atv_player.ui.player_window",
                    vod_name="测试剧",
                    episode_title="第1集",
                )
            ]

        def export_records(self, records, target_path):
            target_path.write_text(records[0].message, encoding="utf-8")

        def clear(self) -> None:
            return None

    config = AppConfig(logging_enabled=True)
    widget = LogConsoleWidget(config=config, save_config=lambda: None, app_log_service=FakeService())
    qtbot.addWidget(widget)

    widget.search_edit.setText("测试剧")
    widget.source_combo.setCurrentIndex(widget.source_combo.findData("playback"))
    widget.level_combo.setCurrentIndex(widget.level_combo.findData("ERROR"))
    widget.refresh_button.click()

    assert widget.log_table.rowCount() == 1
    widget.log_table.selectRow(0)
    assert "播放失败: boom" in widget.detail_view.toPlainText()
```

- [ ] **Step 2: Run the focused UI tests to verify they fail**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "logs_tab_with_logging_toggle or saves_logging_enabled_toggle or log_console_widget_filters_and_shows_details" -v
```

Expected:

- `AdvancedSettingsDialog` has no `日志` tab.
- The dialog has no `logging_enabled_checkbox`.
- `LogConsoleWidget` does not exist yet.

- [ ] **Step 3: Implement `LogConsoleWidget` and host it in `AdvancedSettingsDialog`**

Create `src/atv_player/ui/log_console.py`:

```python
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from atv_player.log_store import AppLogFilter
from atv_player.ui.theme import FlatComboBox


class LogConsoleWidget(QWidget):
    def __init__(self, *, config, save_config, app_log_service) -> None:
        super().__init__()
        self._config = config
        self._save_config = save_config
        self._app_log_service = app_log_service
        self._records = []
        self.logging_enabled_checkbox = QCheckBox("启用日志记录")
        self.logging_enabled_checkbox.setChecked(bool(getattr(config, "logging_enabled", True)))
        self.search_edit = QLineEdit()
        self.source_combo = FlatComboBox()
        self.source_combo.addItem("全部", "")
        self.source_combo.addItem("播放", "playback")
        self.source_combo.addItem("后台", "app")
        self.level_combo = FlatComboBox()
        self.level_combo.addItem("全部", "")
        self.level_combo.addItem("INFO", "INFO")
        self.level_combo.addItem("WARNING", "WARNING")
        self.level_combo.addItem("ERROR", "ERROR")
        self.category_combo = FlatComboBox()
        for value, label in [("", "全部"), ("player", "player"), ("network", "network"), ("metadata", "metadata"), ("plugin", "plugin"), ("danmaku", "danmaku"), ("live", "live"), ("app", "app")]:
            self.category_combo.addItem(label, value)
        self.refresh_button = QPushButton("刷新")
        self.export_button = QPushButton("导出日志")
        self.clear_button = QPushButton("清空日志")
        self.status_label = QLabel("")
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["时间", "级别", "来源", "分类", "消息"])
        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        ...
```

Implement the key methods:

```python
    def _save_logging_enabled(self) -> None:
        self._config.logging_enabled = self.logging_enabled_checkbox.isChecked()
        self._save_config()
        self._update_status_banner()

    def reload_records(self) -> None:
        if self._app_log_service is None:
            self._records = []
            self._render_records()
            self.status_label.setText("日志服务不可用")
            return
        self._records = self._app_log_service.load_records(
            limit=2000,
            log_filter=AppLogFilter(
                query=self.search_edit.text().strip(),
                source=str(self.source_combo.currentData() or ""),
                level=str(self.level_combo.currentData() or ""),
                category=str(self.category_combo.currentData() or ""),
            ),
        )
        self._render_records()
        self._update_status_banner()
```

```python
    def _render_records(self) -> None:
        self.log_table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            self.log_table.setItem(row, 0, QTableWidgetItem(record.timestamp))
            self.log_table.setItem(row, 1, QTableWidgetItem(record.level))
            self.log_table.setItem(row, 2, QTableWidgetItem(record.source))
            self.log_table.setItem(row, 3, QTableWidgetItem(record.category))
            self.log_table.setItem(row, 4, QTableWidgetItem(record.message))
```

```python
    def _render_selected_detail(self) -> None:
        row = self.log_table.currentRow()
        if not (0 <= row < len(self._records)):
            self.detail_view.clear()
            return
        record = self._records[row]
        lines = [
            f"模块: {record.module}",
            f"消息: {record.message}",
            f"剧名: {record.vod_name}" if record.vod_name else "",
            f"剧集: {record.episode_title}" if record.episode_title else "",
            f"会话: {record.session_id}" if record.session_id else "",
            f"URL 摘要: {record.url_summary}" if record.url_summary else "",
            f"异常: {record.exception}" if record.exception else "",
        ]
        self.detail_view.setPlainText("\n".join(line for line in lines if line))
```

```python
    def _export_records(self) -> None:
        if self._app_log_service is None or not self._records:
            return
        filename, _selected = QFileDialog.getSaveFileName(self, "导出日志", "atv-player.log", "Log Files (*.log)")
        if not filename:
            return
        self._app_log_service.export_records(self._records, Path(filename))
        self.status_label.setText(f"已导出 {len(self._records)} 条日志")

    def _clear_logs(self) -> None:
        if self._app_log_service is None:
            return
        answer = QMessageBox.question(self, "清空日志", "确认清空所有日志和归档吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._app_log_service.clear()
        self.reload_records()
```

Host the widget in `src/atv_player/ui/advanced_settings_dialog.py`:

```python
from atv_player.ui.log_console import LogConsoleWidget
```

Extend the constructor:

```python
    def __init__(
        self,
        config: AppConfig,
        save_config: Callable[[], None],
        parent: QWidget | None = None,
        apply_theme: Callable[[], None] | None = None,
        app_log_service=None,
    ) -> None:
        ...
        self.logs_tab = QWidget()
        self.log_console = LogConsoleWidget(config=config, save_config=save_config, app_log_service=app_log_service)
        self.logging_enabled_checkbox = self.log_console.logging_enabled_checkbox
```

Add the tab:

```python
        logs_tab_layout = QVBoxLayout(self.logs_tab)
        logs_tab_layout.addWidget(self.log_console)
        self.settings_tabs.addTab(self.logs_tab, "日志")
```

Make `_save()` persist the checkbox state before calling the shared saver:

```python
        self._config.logging_enabled = self.logging_enabled_checkbox.isChecked()
```

- [ ] **Step 4: Run the focused UI tests to verify they pass**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "logs_tab_with_logging_toggle or saves_logging_enabled_toggle or log_console_widget_filters_and_shows_details" -v
```

Expected:

- The dialog now includes a `日志` tab.
- The logging toggle persists through the shared `AppConfig`.
- The console widget loads records, filters through the service interface, and shows details.

- [ ] **Step 5: Run the broader observability regression slice**

Run:

```bash
uv run pytest tests/test_storage.py -k "logging_enabled" -v
uv run pytest tests/test_log_store.py -v
uv run pytest tests/test_app.py -k "app_log_service or structured_handler" -v
uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog or logs_tab or log_console_widget" -v
uv run pytest tests/test_player_window_ui.py -k "app_log_service or logging_disabled" -v
```

Expected:

- All new observability-focused tests pass together.
- No regressions appear in existing advanced-settings or player-log behavior.

- [ ] **Step 6: Commit the log-console UI slice**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/log_console.py src/atv_player/ui/advanced_settings_dialog.py
git commit -m "feat: add advanced settings log console"
```

---

## Self-Review

- Spec coverage:
  - `logging_enabled` persistence and migration: Task 1.
  - Structured JSONL log runtime, 10 MB rotation, gzip archives, max 5 archives, export, clear: Task 2.
  - Shared handler installation and app-wide structured logging: Task 3.
  - Additional backend troubleshooting logs: Task 4.
  - Playback log mirroring and disable-mode short-circuit: Task 5.
  - Advanced Settings `日志` tab with filters, details, export, clear, refresh, and toggle: Task 6.

- Placeholder scan:
  - No `TODO`/`TBD` markers remain.
  - Every task includes explicit files, tests, commands, and code snippets.

- Type consistency:
  - `AppLogService` is the shared runtime object across `QApplication`, `MainWindow`, `AdvancedSettingsDialog`, and `PlayerWindow`.
  - `AppLogEvent` / `AppLogFilter` names are used consistently in the runtime and UI tasks.
  - `logging_enabled` is the single persisted config flag across models, repository, UI, and runtime gating.
