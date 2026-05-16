# Local Douban And Advanced Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local-Douban-first metadata lookup with automatic `alist-tvbox` fallback, plus a new advanced settings dialog for Douban Cookie and TMDB API key persistence.

**Architecture:** Extend `AppConfig` and `SettingsRepository` with two metadata credential fields, surface them through a small `AdvancedSettingsDialog`, and wire a local Douban HTTP/parser client into `DoubanProvider`. `DoubanProvider` remains the metadata-facing adapter and orchestrates local-first search/detail with fallback to existing `ApiClient /api/movies` endpoints.

**Tech Stack:** Python 3.14, dataclasses, sqlite migrations, `httpx`, PySide6, pytest

---

### Task 1: Persist metadata credential settings in `AppConfig` and sqlite

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `tests/test_storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
def test_settings_repository_round_trip_persists_metadata_credentials(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(
        metadata_douban_cookie="bid=demo; ll=118282",
        metadata_tmdb_api_key="tmdb-demo-key",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.metadata_douban_cookie == "bid=demo; ll=118282"
    assert saved.metadata_tmdb_api_key == "tmdb-demo-key"


def test_settings_repository_migrates_missing_metadata_credential_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            \"\"\"
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL
            )
            \"\"\"
        )
        conn.execute(
            \"\"\"
            INSERT INTO app_config (id, base_url, username, token, vod_token, last_path)
            VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')
            \"\"\"
        )

    repo = SettingsRepository(db_path)
    config = repo.load_config()

    assert config.metadata_douban_cookie == ""
    assert config.metadata_tmdb_api_key == ""
```

- [ ] **Step 2: Run the focused storage tests and verify they fail**

Run: `uv run pytest tests/test_storage.py -k "metadata_credentials" -v`

Expected: FAIL with `TypeError` or missing-column assertions because `AppConfig` and `SettingsRepository` do not expose the new fields yet.

- [ ] **Step 3: Add the new config fields and sqlite migration**

```python
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    metadata_douban_cookie: str = ""
    metadata_tmdb_api_key: str = ""
    last_path: str = "/"
```

```python
if "metadata_douban_cookie" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN metadata_douban_cookie TEXT NOT NULL DEFAULT ''"
    )
if "metadata_tmdb_api_key" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN metadata_tmdb_api_key TEXT NOT NULL DEFAULT ''"
    )
```

```python
return AppConfig(
    base_url=str(base_url or ""),
    username=str(username or ""),
    token=str(token or ""),
    vod_token=str(vod_token or ""),
    metadata_douban_cookie=str(metadata_douban_cookie or "").strip(),
    metadata_tmdb_api_key=str(metadata_tmdb_api_key or "").strip(),
    last_path=str(last_path or "/"),
    ...
)
```

- [ ] **Step 4: Run the focused storage tests and verify they pass**

Run: `uv run pytest tests/test_storage.py -k "metadata_credentials" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist metadata credential settings"
```

### Task 2: Add the advanced settings dialog UI

**Files:**
- Create: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `tests/test_main_window_ui.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing dialog tests**

```python
def test_advanced_settings_dialog_populates_existing_config(qtbot) -> None:
    config = AppConfig(
        metadata_douban_cookie="bid=demo;",
        metadata_tmdb_api_key="tmdb-demo-key",
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.douban_cookie_edit.toPlainText() == "bid=demo;"
    assert dialog.tmdb_api_key_edit.text() == "tmdb-demo-key"


def test_advanced_settings_dialog_saves_trimmed_values(qtbot) -> None:
    saved: list[AppConfig] = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.douban_cookie_edit.setPlainText(" bid=demo; ll=118282 \n")
    dialog.tmdb_api_key_edit.setText(" tmdb-demo-key ")
    dialog._save()

    assert config.metadata_douban_cookie == "bid=demo; ll=118282"
    assert config.metadata_tmdb_api_key == "tmdb-demo-key"
    assert len(saved) == 1
```

- [ ] **Step 2: Run the focused dialog tests and verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog" -v`

Expected: FAIL with `ImportError` because the dialog module does not exist yet.

- [ ] **Step 3: Create the dialog with minimal save/cancel behavior**

```python
class AdvancedSettingsDialog(QDialog):
    def __init__(self, config: AppConfig, save_config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._save_config = save_config
        self.setWindowTitle("高级设置")
        self.resize(640, 320)

        self.douban_cookie_edit = QPlainTextEdit()
        self.douban_cookie_edit.setPlaceholderText("填写豆瓣 Cookie；留空时跳过本地豆瓣抓取")
        self.tmdb_api_key_edit = QLineEdit()
        self.tmdb_api_key_edit.setPlaceholderText("填写 TMDB API Key")
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")

        self.douban_cookie_edit.setPlainText(config.metadata_douban_cookie)
        self.tmdb_api_key_edit.setText(config.metadata_tmdb_api_key)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

    def _save(self) -> None:
        self._config.metadata_douban_cookie = self.douban_cookie_edit.toPlainText().strip()
        self._config.metadata_tmdb_api_key = self.tmdb_api_key_edit.text().strip()
        self._save_config()
        self.accept()
```

- [ ] **Step 4: Run the focused dialog tests and verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add metadata advanced settings dialog"
```

### Task 3: Add the main-window advanced settings entry point

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_app.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing main-window integration tests**

```python
def test_main_window_shows_advanced_settings_button_after_live_source_manager(qtbot) -> None:
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
    )
    qtbot.addWidget(window)

    assert window.live_source_manager_button.text() == "直播源管理"
    assert window.advanced_settings_button.text() == "高级设置"
```

```python
def test_main_window_opens_advanced_settings_dialog(qtbot, monkeypatch) -> None:
    opened: list[object] = []

    class FakeDialog:
        def __init__(self, config, save_config, parent=None) -> None:
            opened.append((config, save_config, parent))

        def exec(self) -> int:
            return 1

    monkeypatch.setattr(main_window_module, "AdvancedSettingsDialog", FakeDialog)
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
    )
    qtbot.addWidget(window)

    window._open_advanced_settings()

    assert len(opened) == 1
```

- [ ] **Step 2: Run the focused main-window tests and verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_button or opens_advanced_settings_dialog" -v`

Expected: FAIL because `MainWindow` does not expose the button or open hook yet.

- [ ] **Step 3: Wire the button and dialog opening method**

```python
from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

...
self.live_source_manager_button = QPushButton("直播源管理")
self.advanced_settings_button = QPushButton("高级设置")
self.logout_button = QPushButton("退出登录")
...
self.advanced_settings_button.clicked.connect(self._open_advanced_settings)
```

```python
def _open_advanced_settings(self) -> None:
    self._dismiss_visible_global_search_popup()
    self._close_plugin_overflow_drawer()
    self._close_help_dialog()
    dialog = AdvancedSettingsDialog(self.config, self._save_config, self)
    dialog.exec()
```

- [ ] **Step 4: Run the focused main-window tests and verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_button or opens_advanced_settings_dialog" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py tests/test_app.py
git commit -m "feat: add advanced settings entry point"
```

### Task 4: Add the local Douban client with blocked-page detection

**Files:**
- Create: `src/atv_player/metadata/providers/local_douban_client.py`
- Create: `tests/test_local_douban_client.py`
- Test: `tests/test_local_douban_client.py`

- [ ] **Step 1: Write the failing local Douban client tests**

```python
def test_local_douban_client_raises_when_html_matches_block_markers() -> None:
    html = '<html><body>有异常请求从你的 IP 发出 <a href="https://sec.douban.com/">sec</a></body></html>'
    client = LocalDoubanClient(cookie="bid=demo;", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=html)
    ))

    with pytest.raises(DoubanBlockedError):
        client.search("深空彼岸", year="2026")
```

```python
def test_local_douban_client_sends_cookie_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("Cookie", "")
        return httpx.Response(200, text="<html></html>")

    client = LocalDoubanClient(cookie="bid=demo;", transport=httpx.MockTransport(handler))

    client._get_html("https://movie.douban.com/")

    assert seen["cookie"] == "bid=demo;"
```

- [ ] **Step 2: Run the focused client tests and verify they fail**

Run: `uv run pytest tests/test_local_douban_client.py -v`

Expected: FAIL with `ModuleNotFoundError` because the local client does not exist yet.

- [ ] **Step 3: Implement the local client and blocked exception**

```python
class DoubanBlockedError(RuntimeError):
    pass


class LocalDoubanClient:
    _USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    def __init__(self, cookie: str = "", transport: httpx.BaseTransport | None = None) -> None:
        self._cookie = cookie.strip()
        self._client = httpx.Client(transport=transport, timeout=15.0, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self._USER_AGENT, "Referer": "https://movie.douban.com/"}
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    def _get_html(self, url: str, params: dict[str, object] | None = None) -> str:
        response = self._client.get(url, params=params, headers=self._headers())
        response.raise_for_status()
        html = response.text
        if "有异常请求从你的 IP 发出" in html or "https://sec.douban.com/" in html:
            raise DoubanBlockedError(f"被禁止访问: {url}")
        return html
```

- [ ] **Step 4: Run the focused client tests and verify they pass**

Run: `uv run pytest tests/test_local_douban_client.py -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/local_douban_client.py tests/test_local_douban_client.py
git commit -m "feat: add local douban metadata client"
```

### Task 5: Make `DoubanProvider` local-first with `alist-tvbox` fallback

**Files:**
- Modify: `src/atv_player/metadata/providers/douban.py`
- Modify: `tests/test_metadata_douban_provider.py`
- Test: `tests/test_metadata_douban_provider.py`

- [ ] **Step 1: Write the failing provider orchestration tests**

```python
def test_douban_provider_uses_local_search_before_backend_fallback() -> None:
    local = FakeLocalDoubanClient(search_results=[{"id": 35746415, "title": "深空彼岸", "year": "2026"}])
    api = FakeMetadataApiClient(search_payload={"items": []})
    provider = DoubanProvider(api, local_client=local)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [match.provider_id for match in matches] == ["35746415"]
    assert api.search_calls == []
```

```python
def test_douban_provider_falls_back_when_local_search_is_blocked() -> None:
    local = FakeLocalDoubanClient(search_error=DoubanBlockedError("被禁止访问"))
    api = FakeMetadataApiClient(search_payload={"items": [{"id": 35746415, "name": "深空彼岸", "year": 2026}]})
    provider = DoubanProvider(api, local_client=local)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))

    assert [match.provider_id for match in matches] == ["35746415"]
    assert api.search_calls == [("深空彼岸", "2026")]
```

```python
def test_douban_provider_falls_back_when_local_detail_is_missing() -> None:
    local = FakeLocalDoubanClient(detail_result=None)
    api = FakeMetadataApiClient(detail_payload={"id": 35746415, "name": "深空彼岸", "description": "豆瓣简介"})
    provider = DoubanProvider(api, local_client=local)

    record = provider.get_detail(MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸"))

    assert record.provider_id == "35746415"
    assert api.detail_calls == ["35746415"]
```

- [ ] **Step 2: Run the focused provider tests and verify they fail**

Run: `uv run pytest tests/test_metadata_douban_provider.py -v`

Expected: FAIL because `DoubanProvider` does not accept a local client or fallback flow yet.

- [ ] **Step 3: Refactor `DoubanProvider` to orchestrate local search/detail with fallback**

```python
class DoubanProvider:
    def __init__(self, api_client, cache: MetadataCache | None = None, local_client=None) -> None:
        self._api_client = api_client
        self._cache = cache
        self._local_client = local_client

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if candidate.vod_dbid:
            return [MetadataMatch(provider=self.name, provider_id=str(candidate.vod_dbid), title=candidate.title, year=candidate.year)]
        local_items: list[dict[str, object]] = []
        if self._local_client is not None:
            try:
                local_items = self._local_client.search(candidate.title, year=candidate.year)
            except DoubanBlockedError:
                local_items = []
        if local_items:
            return [self._match_from_local_item(item) for item in local_items]
        payload = self._api_client.search_douban_metadata(candidate.title, year=candidate.year)
        return self._matches_from_backend_payload(payload)
```

```python
    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        local_payload = None
        if self._local_client is not None:
            try:
                local_payload = self._local_client.get_detail(match.provider_id)
            except DoubanBlockedError:
                local_payload = None
        payload = local_payload or self._api_client.get_douban_metadata_detail(match.provider_id)
        return self._record_from_payload(payload, match)
```

- [ ] **Step 4: Run the focused provider tests and verify they pass**

Run: `uv run pytest tests/test_metadata_douban_provider.py -v`

Expected: PASS with all selected provider tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/douban.py tests/test_metadata_douban_provider.py
git commit -m "feat: prefer local douban metadata with fallback"
```

### Task 6: Wire advanced settings into app metadata construction and run regression coverage

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_metadata_hydrator.py`
- Test: `tests/test_app.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing app-wiring tests**

```python
def test_app_coordinator_builds_local_douban_client_from_latest_config(monkeypatch) -> None:
    class FakeRepo:
        def __init__(self) -> None:
            self.config = AppConfig(metadata_douban_cookie="bid=demo;", metadata_tmdb_api_key="tmdb-key")

        def load_config(self) -> AppConfig:
            return self.config

    coordinator = AppCoordinator(FakeRepo())
    api_client = object()

    factory = coordinator._build_metadata_hydrator_factory(api_client)
    hydrate = factory(source_kind="browse", vod=VodItem(vod_id="v1", vod_name="深空彼岸"))

    assert hydrate is not None
```

```python
def test_main_window_advanced_settings_save_updates_shared_config(qtbot, monkeypatch) -> None:
    config = AppConfig()

    class FakeDialog:
        def __init__(self, config_arg, save_config, parent=None) -> None:
            config_arg.metadata_douban_cookie = "bid=demo;"
            config_arg.metadata_tmdb_api_key = "tmdb-key"
            save_config()

        def exec(self) -> int:
            return 1

    monkeypatch.setattr(main_window_module, "AdvancedSettingsDialog", FakeDialog)
    saved: list[tuple[str, str]] = []
    window = MainWindow(..., config=config, save_config=lambda: saved.append((config.metadata_douban_cookie, config.metadata_tmdb_api_key)))
    qtbot.addWidget(window)

    window._open_advanced_settings()

    assert saved == [("bid=demo;", "tmdb-key")]
```

- [ ] **Step 2: Run the focused wiring tests and verify they fail**

Run: `uv run pytest tests/test_app.py tests/test_main_window_ui.py -k "latest_config or advanced_settings_save_updates_shared_config" -v`

Expected: FAIL because `AppCoordinator` does not yet create a local Douban client from config.

- [ ] **Step 3: Update app wiring to read fresh config when constructing providers**

```python
def _build_metadata_hydrator_factory(self, api_client: ApiClient):
    cache = MetadataCache(app_cache_dir() / "metadata")

    def factory(*, request=None, source_kind: str = "", source_key: str = "", vod=None, raw_detail=None):
        del request
        config = self.repo.load_config()
        local_douban = LocalDoubanClient(cookie=config.metadata_douban_cookie)
        providers: list[object] = []
        if source_kind == "plugin":
            plugin_payload = self._build_plugin_metadata_payload(raw_detail)
            if plugin_payload is not None:
                providers.append(CustomPluginProvider(plugin_payload))
        providers.append(DoubanProvider(api_client, cache=cache, local_client=local_douban))
        hydrator = MetadataHydrator(cache=cache, providers=providers)
        ...
```

- [ ] **Step 4: Run regression coverage for the feature slice**

Run:

```bash
uv run pytest \
  tests/test_storage.py \
  tests/test_local_douban_client.py \
  tests/test_metadata_douban_provider.py \
  tests/test_main_window_ui.py \
  tests/test_app.py \
  -k "metadata_credentials or advanced_settings or local_douban or metadata or restore_last_player" -q
```

Expected: PASS for the new storage, UI, provider, and wiring coverage without regressing existing restore/metadata flows.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/app.py tests/test_app.py tests/test_main_window_ui.py tests/test_metadata_hydrator.py
git commit -m "feat: wire local douban settings into metadata hydration"
```

## Self-Review

- Spec coverage:
  - 本地豆瓣优先 search/detail: Task 4-5
  - 风控识别与 fallback: Task 4-5
  - 高级设置按钮与对话框: Task 2-3
  - 配置持久化: Task 1
  - App wiring with fresh config reads: Task 6
  - TMDB API Key persistence only, no provider: Task 1-3 and no extra tasks beyond storage/UI
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every task has exact files, commands, and concrete code snippets
- Type consistency:
  - Config keys use `metadata_douban_cookie` and `metadata_tmdb_api_key` consistently
  - Local client type uses `DoubanBlockedError`
  - Provider constructor uses `local_client`

