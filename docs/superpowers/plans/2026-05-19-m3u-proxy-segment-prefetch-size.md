# M3U Proxy Segment Prefetch Size Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted `m3u代理分片预取大小` playback setting that controls how many future HLS proxy segments are prefetched, with `0` disabling prefetch and `2` as the default.

**Architecture:** Extend the existing `AppConfig -> SettingsRepository -> AdvancedSettingsDialog -> AppCoordinator -> LocalHlsProxyServer -> SegmentProxy` chain instead of introducing a new settings path. Keep the prefetch thread model and cache behavior unchanged, and only replace the hard-coded "next two segments" rule with a validated integer preference.

**Tech Stack:** Python, PySide6, sqlite3, pytest

---

## File Structure

**Modify:**
- `src/atv_player/models.py`
  Add the new `AppConfig` field with its default value.
- `src/atv_player/storage.py`
  Add normalization, schema migration, load/save persistence, and default-row support.
- `src/atv_player/ui/advanced_settings_dialog.py`
  Add the playback settings input, validation, styling, load/save wiring, and error handling.
- `src/atv_player/proxy/segment.py`
  Make segment prefetch count configurable and disable prefetch when the value is `0`.
- `src/atv_player/proxy/server.py`
  Accept and forward the configured prefetch size into `SegmentProxy`.
- `src/atv_player/app.py`
  Inject the saved configuration value when constructing `LocalHlsProxyServer`.

**Test:**
- `tests/test_storage.py`
  Verify default value, persistence, migration, and normalization.
- `tests/test_main_window_ui.py`
  Verify advanced settings load/save and validation behavior.
- `tests/test_hls_proxy_segment.py`
  Verify configurable segment prefetch scheduling behavior.
- `tests/test_app.py`
  Verify `AppCoordinator` passes the saved setting into the HLS proxy.

### Task 1: Persist the New Config Field

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add these tests near the existing playback settings coverage in `tests/test_storage.py`:

```python
def test_settings_repository_defaults_m3u_proxy_segment_prefetch_size_to_two(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    assert repo.load_config().m3u_proxy_segment_prefetch_size == 2


def test_settings_repository_round_trip_persists_m3u_proxy_segment_prefetch_size(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(m3u_proxy_segment_prefetch_size=5)

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.m3u_proxy_segment_prefetch_size == 5
    assert saved == config


def test_settings_repository_migrates_missing_m3u_proxy_segment_prefetch_size_column(tmp_path: Path) -> None:
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
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO app_config (id, base_url, username, token, vod_token, last_path) VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')"
        )

    config = SettingsRepository(db_path).load_config()

    assert config.m3u_proxy_segment_prefetch_size == 2


def test_settings_repository_normalizes_invalid_m3u_proxy_segment_prefetch_size_values(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    repo.save_config(AppConfig(m3u_proxy_segment_prefetch_size=99))

    assert repo.load_config().m3u_proxy_segment_prefetch_size == 10
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_storage.py -k "m3u_proxy_segment_prefetch_size" -v
```

Expected:

```text
FAILED tests/test_storage.py::test_settings_repository_defaults_m3u_proxy_segment_prefetch_size_to_two
FAILED tests/test_storage.py::test_settings_repository_round_trip_persists_m3u_proxy_segment_prefetch_size
```

The failure should be because `AppConfig` / `SettingsRepository` do not yet expose the new field.

- [ ] **Step 3: Write the minimal model and storage implementation**

Update `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class AppConfig:
    ...
    mpv_extra_options: str = ""
    playback_auto_switch_source_on_failure: bool = False
    m3u_proxy_segment_prefetch_size: int = 2
    episode_title_enhancement_enabled: bool = True
    ...
```

Update `src/atv_player/storage.py` with a normalizer:

```python
def _normalize_m3u_proxy_segment_prefetch_size(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 2
    return max(0, min(normalized, 10))
```

Extend schema creation and migration:

```python
CREATE TABLE IF NOT EXISTS app_config (
    ...
    playback_auto_switch_source_on_failure INTEGER NOT NULL DEFAULT 0,
    m3u_proxy_segment_prefetch_size INTEGER NOT NULL DEFAULT 2,
    last_path TEXT NOT NULL,
    ...
)
```

```python
if "m3u_proxy_segment_prefetch_size" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN m3u_proxy_segment_prefetch_size INTEGER NOT NULL DEFAULT 2"
    )
```

Include the field in the default insert row, `SELECT`, `AppConfig(...)`, and `UPDATE` parameter list:

```python
m3u_proxy_segment_prefetch_size=_normalize_m3u_proxy_segment_prefetch_size(
    m3u_proxy_segment_prefetch_size
),
```

```python
_normalize_m3u_proxy_segment_prefetch_size(config.m3u_proxy_segment_prefetch_size),
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_storage.py -k "m3u_proxy_segment_prefetch_size or playback_settings or playback_auto_switch_source" -v
```

Expected:

```text
PASSED tests/test_storage.py::test_settings_repository_defaults_m3u_proxy_segment_prefetch_size_to_two
PASSED tests/test_storage.py::test_settings_repository_round_trip_persists_m3u_proxy_segment_prefetch_size
PASSED tests/test_storage.py::test_settings_repository_migrates_missing_m3u_proxy_segment_prefetch_size_column
PASSED tests/test_storage.py::test_settings_repository_normalizes_invalid_m3u_proxy_segment_prefetch_size_values
```

- [ ] **Step 5: Commit the storage changes**

```bash
git add tests/test_storage.py src/atv_player/models.py src/atv_player/storage.py
git commit -m "feat: persist m3u proxy segment prefetch size"
```

### Task 2: Add the Playback Settings UI Field and Validation

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing advanced-settings tests**

Add these tests near the existing playback settings dialog tests in `tests/test_main_window_ui.py`:

```python
def test_advanced_settings_dialog_loads_m3u_proxy_segment_prefetch_size(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(
        AppConfig(m3u_proxy_segment_prefetch_size=4),
        save_config=lambda: None,
    )
    qtbot.addWidget(dialog)

    assert dialog.m3u_proxy_segment_prefetch_size_edit.text() == "4"
    assert dialog.m3u_proxy_segment_prefetch_size_edit.placeholderText() == "0 - 10"


def test_advanced_settings_dialog_saves_m3u_proxy_segment_prefetch_size(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved: list[AppConfig] = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.m3u_proxy_segment_prefetch_size_edit.setText(" 0 ")
    dialog._save()

    assert config.m3u_proxy_segment_prefetch_size == 0
    assert len(saved) == 1


def test_advanced_settings_dialog_rejects_invalid_m3u_proxy_segment_prefetch_size(qtbot, monkeypatch) -> None:
    from atv_player.ui import advanced_settings_dialog as module
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    messages: list[str] = []

    def fake_warning(_parent, _title: str, text: str) -> int:
        messages.append(text)
        return 0

    monkeypatch.setattr(module.QMessageBox, "warning", fake_warning)
    saved: list[AppConfig] = []
    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: saved.append(dialog._config))
    qtbot.addWidget(dialog)

    dialog.m3u_proxy_segment_prefetch_size_edit.setText("11")
    dialog._save()

    assert messages == ["m3u代理分片预取大小必须在 0 到 10 之间"]
    assert saved == []
```

- [ ] **Step 2: Run the advanced-settings tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "m3u_proxy_segment_prefetch_size" -v
```

Expected:

```text
FAILED tests/test_main_window_ui.py::test_advanced_settings_dialog_loads_m3u_proxy_segment_prefetch_size
FAILED tests/test_main_window_ui.py::test_advanced_settings_dialog_saves_m3u_proxy_segment_prefetch_size
```

The failure should be because the dialog does not yet define `m3u_proxy_segment_prefetch_size_edit` or save the field.

- [ ] **Step 3: Write the minimal dialog implementation**

Add the input in `src/atv_player/ui/advanced_settings_dialog.py`:

```python
self.m3u_proxy_segment_prefetch_size_edit = QLineEdit()
self.m3u_proxy_segment_prefetch_size_edit.setPlaceholderText("0 - 10")
...
self.m3u_proxy_segment_prefetch_size_edit.setText(str(config.m3u_proxy_segment_prefetch_size))
...
playback_layout.addRow("m3u代理分片预取大小", self.m3u_proxy_segment_prefetch_size_edit)
```

Apply the existing line-edit styling:

```python
for edit in (
    self.tmdb_api_key_edit,
    self.bangumi_access_token_edit,
    self.network_proxy_url_edit,
    self.mpv_cache_size_edit,
    self.mpv_network_timeout_edit,
    self.mpv_default_readahead_edit,
    self.m3u_proxy_segment_prefetch_size_edit,
):
    edit.setStyleSheet(line_edit_qss)
    edit.setFixedHeight(42)
```

Extend `_validated_playback_values()` to parse one more integer:

```python
prefetch_size = parse_int(
    self.m3u_proxy_segment_prefetch_size_edit.text(),
    label="m3u代理分片预取大小",
    minimum=0,
    maximum=10,
)
if cache_size is None or timeout is None or readahead is None or prefetch_size is None:
    return None
```

Return and store the value:

```python
return (
    self.playback_auto_switch_source_on_failure_checkbox.isChecked(),
    browser,
    cache_size,
    str(self.mpv_hwdec_mode_combo.currentData() or "auto-safe"),
    timeout,
    readahead,
    "\n".join(normalized_lines),
    prefetch_size,
)
```

```python
(
    self._config.playback_auto_switch_source_on_failure,
    self._config.youtube_cookie_browser,
    self._config.mpv_cache_size_mb,
    self._config.mpv_hwdec_mode,
    self._config.mpv_network_timeout_seconds,
    self._config.mpv_default_readahead_secs,
    self._config.mpv_extra_options,
    self._config.m3u_proxy_segment_prefetch_size,
) = playback_values
```

- [ ] **Step 4: Run the advanced-settings tests to verify they pass**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "m3u_proxy_segment_prefetch_size or saves_trimmed_playback_settings or adds_playback_tab_and_populates_existing_values" -v
```

Expected:

```text
PASSED tests/test_main_window_ui.py::test_advanced_settings_dialog_loads_m3u_proxy_segment_prefetch_size
PASSED tests/test_main_window_ui.py::test_advanced_settings_dialog_saves_m3u_proxy_segment_prefetch_size
PASSED tests/test_main_window_ui.py::test_advanced_settings_dialog_rejects_invalid_m3u_proxy_segment_prefetch_size
```

- [ ] **Step 5: Commit the dialog changes**

```bash
git add tests/test_main_window_ui.py src/atv_player/ui/advanced_settings_dialog.py
git commit -m "feat: add m3u proxy segment prefetch setting UI"
```

### Task 3: Make Segment Prefetch Count Configurable

**Files:**
- Modify: `src/atv_player/proxy/segment.py`
- Modify: `src/atv_player/proxy/server.py`
- Test: `tests/test_hls_proxy_segment.py`

- [ ] **Step 1: Write the failing proxy tests**

Add these tests in `tests/test_hls_proxy_segment.py`:

```python
def test_segment_proxy_does_not_schedule_prefetch_when_prefetch_size_is_zero() -> None:
    scheduled: list[tuple[str, int]] = []

    registry = ProxySessionRegistry()
    token = registry.create_session("https://media.example/path/index.m3u8", {})
    registry.get(token).segments = [
        PlaylistSegment(index=0, url="https://media.example/path/0001.ts", duration=5.0),
        PlaylistSegment(index=1, url="https://media.example/path/0002.ts", duration=5.0),
    ]
    proxy = SegmentProxy(session_registry=registry, segment_prefetch_size=0)
    proxy._prefetch_segment = lambda session_token, segment_index: scheduled.append((session_token, segment_index))

    proxy.schedule_prefetch(token, 0)

    assert scheduled == []


def test_segment_proxy_schedules_configured_number_of_next_segments() -> None:
    scheduled: list[tuple[str, int]] = []

    registry = ProxySessionRegistry()
    token = registry.create_session("https://media.example/path/index.m3u8", {})
    registry.get(token).segments = [
        PlaylistSegment(index=0, url="https://media.example/path/0001.ts", duration=5.0),
        PlaylistSegment(index=1, url="https://media.example/path/0002.ts", duration=5.0),
        PlaylistSegment(index=2, url="https://media.example/path/0003.ts", duration=5.0),
        PlaylistSegment(index=3, url="https://media.example/path/0004.ts", duration=5.0),
    ]
    proxy = SegmentProxy(session_registry=registry, segment_prefetch_size=1)
    proxy._prefetch_segment = lambda session_token, segment_index: scheduled.append((session_token, segment_index))

    proxy.schedule_prefetch(token, 0)

    assert scheduled == [(token, 1)]
```

Update the existing default behavior test to keep asserting the default `2` behavior:

```python
proxy = SegmentProxy(session_registry=registry)
...
assert scheduled == [(token, 1), (token, 2)]
```

- [ ] **Step 2: Run the proxy tests to verify they fail**

Run:

```bash
uv run pytest tests/test_hls_proxy_segment.py -v
```

Expected:

```text
FAILED tests/test_hls_proxy_segment.py::test_segment_proxy_does_not_schedule_prefetch_when_prefetch_size_is_zero
FAILED tests/test_hls_proxy_segment.py::test_segment_proxy_schedules_configured_number_of_next_segments
```

The failure should be because `SegmentProxy.__init__()` does not yet accept `segment_prefetch_size`.

- [ ] **Step 3: Write the minimal proxy implementation**

Update `src/atv_player/proxy/segment.py`:

```python
class SegmentProxy:
    _IN_FLIGHT_WAIT_TIMEOUT_SECONDS = 2.0

    def __init__(
        self,
        session_registry: ProxySessionRegistry,
        get=httpx.get,
        cache: ProxyCache | None = None,
        proxy_decider: ProxyDecider | None = None,
        segment_prefetch_size: int = 2,
    ) -> None:
        self._session_registry = session_registry
        self._get = get
        self._cache = cache or ProxyCache()
        self._proxy_decider = proxy_decider
        self._segment_prefetch_size = max(0, int(segment_prefetch_size))
```

Replace the hard-coded range:

```python
def schedule_prefetch(self, token: str, current_index: int) -> None:
    session = self._session_registry.get(token)
    if session is None or self._segment_prefetch_size <= 0:
        return
    upper_bound = min(current_index + 1 + self._segment_prefetch_size, len(session.segments))
    for next_index in range(current_index + 1, upper_bound):
        cache_key = self._segment_cache_key(session.segments[next_index].url, session.headers)
        if self._cache.get_segment(cache_key) is not None:
            continue
        self._prefetch_segment(token, next_index)
```

Update `src/atv_player/proxy/server.py`:

```python
class LocalHlsProxyServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2323,
        get=httpx.get,
        stream=_default_stream,
        segment_prefetch_size: int = 2,
    ) -> None:
        ...
        self._segment_proxy = SegmentProxy(
            self._registry,
            get=get,
            segment_prefetch_size=segment_prefetch_size,
        )
```

- [ ] **Step 4: Run the proxy tests to verify they pass**

Run:

```bash
uv run pytest tests/test_hls_proxy_segment.py tests/test_hls_proxy_server.py -k "prefetch_size or schedule_prefetch or direct_media_url" -v
```

Expected:

```text
PASSED tests/test_hls_proxy_segment.py::test_segment_proxy_schedules_prefetch_for_next_segments
PASSED tests/test_hls_proxy_segment.py::test_segment_proxy_does_not_schedule_prefetch_when_prefetch_size_is_zero
PASSED tests/test_hls_proxy_segment.py::test_segment_proxy_schedules_configured_number_of_next_segments
```

- [ ] **Step 5: Commit the proxy changes**

```bash
git add tests/test_hls_proxy_segment.py src/atv_player/proxy/segment.py src/atv_player/proxy/server.py
git commit -m "feat: make hls segment prefetch size configurable"
```

### Task 4: Inject the Saved Setting from AppCoordinator

**Files:**
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing app wiring test**

Add this test in `tests/test_app.py` near other `AppCoordinator` construction tests:

```python
def test_app_coordinator_passes_saved_m3u_proxy_segment_prefetch_size_to_local_hls_proxy_server(monkeypatch) -> None:
    captured: list[int] = []

    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(m3u_proxy_segment_prefetch_size=7)

    class DummyProxyServer:
        def __init__(self, **kwargs) -> None:
            captured.append(kwargs["segment_prefetch_size"])

    class DummyFilter:
        def __init__(self, proxy_server, get) -> None:
            self.proxy_server = proxy_server
            self.get = get

    monkeypatch.setattr(app_module, "LocalHlsProxyServer", DummyProxyServer)
    monkeypatch.setattr(app_module, "M3U8AdFilter", DummyFilter)

    app_module.AppCoordinator(FakeRepo())

    assert captured == [7]
```

- [ ] **Step 2: Run the app wiring test to verify it fails**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_app.py -k "passes_saved_m3u_proxy_segment_prefetch_size" -v
```

Expected:

```text
FAILED tests/test_app.py::test_app_coordinator_passes_saved_m3u_proxy_segment_prefetch_size_to_local_hls_proxy_server
```

The failure should be because `AppCoordinator` does not yet pass `segment_prefetch_size=...`.

- [ ] **Step 3: Write the minimal app wiring implementation**

Update `src/atv_player/app.py`:

```python
class AppCoordinator(QObject):
    def __init__(self, repo: SettingsRepository) -> None:
        super().__init__()
        self.repo = repo
        ...
        proxy_config = self.repo.load_config()
        self._m3u8_ad_filter = M3U8AdFilter(
            proxy_server=LocalHlsProxyServer(
                get=self._proxy_http_get(),
                stream=self._proxy_http_stream(),
                segment_prefetch_size=proxy_config.m3u_proxy_segment_prefetch_size,
            ),
            get=self._proxy_http_get(),
        )
```

Keep the change minimal: only use the saved config value for HLS proxy construction, without adding runtime hot-reload behavior.

- [ ] **Step 4: Run the app wiring test to verify it passes**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_app.py -k "passes_saved_m3u_proxy_segment_prefetch_size or forwards_m3u8_filter_to_main_window" -v
```

Expected:

```text
PASSED tests/test_app.py::test_app_coordinator_passes_saved_m3u_proxy_segment_prefetch_size_to_local_hls_proxy_server
```

- [ ] **Step 5: Commit the app wiring change**

```bash
git add tests/test_app.py src/atv_player/app.py
git commit -m "feat: wire m3u proxy segment prefetch size into app"
```

### Task 5: Final Verification

**Files:**
- Modify: none
- Test: `tests/test_storage.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_hls_proxy_segment.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_storage.py \
  tests/test_main_window_ui.py \
  tests/test_hls_proxy_segment.py \
  tests/test_app.py \
  -k "m3u_proxy_segment_prefetch_size or playback_settings or schedule_prefetch or forwards_m3u8_filter_to_main_window" \
  -v
```

Expected:

```text
PASSED tests/test_storage.py::test_settings_repository_defaults_m3u_proxy_segment_prefetch_size_to_two
PASSED tests/test_main_window_ui.py::test_advanced_settings_dialog_loads_m3u_proxy_segment_prefetch_size
PASSED tests/test_hls_proxy_segment.py::test_segment_proxy_does_not_schedule_prefetch_when_prefetch_size_is_zero
PASSED tests/test_app.py::test_app_coordinator_passes_saved_m3u_proxy_segment_prefetch_size_to_local_hls_proxy_server
```

- [ ] **Step 2: Run a broader safety pass for touched areas**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_storage.py \
  tests/test_main_window_ui.py \
  tests/test_hls_proxy_segment.py \
  tests/test_hls_proxy_server.py \
  tests/test_app.py \
  -v
```

Expected:

```text
All selected tests PASS
```

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff --stat HEAD~4..HEAD
git diff -- src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/proxy/segment.py src/atv_player/proxy/server.py src/atv_player/app.py tests/test_storage.py tests/test_main_window_ui.py tests/test_hls_proxy_segment.py tests/test_app.py
```

Expected:

```text
Only the planned config, UI, proxy, app wiring, and test files changed.
```

- [ ] **Step 4: Commit any final cleanup if needed**

```bash
git add src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/proxy/segment.py src/atv_player/proxy/server.py src/atv_player/app.py tests/test_storage.py tests/test_main_window_ui.py tests/test_hls_proxy_segment.py tests/test_app.py
git commit -m "test: finalize m3u proxy segment prefetch size coverage"
```

Skip this commit if there is no cleanup diff after verification.
