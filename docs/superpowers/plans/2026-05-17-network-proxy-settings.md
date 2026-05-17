# Network Proxy Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build advanced network proxy settings with persisted configuration, a centralized proxy decision layer, UI controls, and end-to-end wiring for app HTTP traffic plus `yt-dlp`.

**Architecture:** Add a new `network_proxy` module that owns rule parsing, URL-level proxy decisions, and thin adapters for `httpx`, `requests`, and `yt-dlp`. Persist proxy settings in `AppConfig` and `SettingsRepository`, expose them in a new `网络代理` tab inside `AdvancedSettingsDialog`, then inject the shared decider into fixed-host clients and per-request helpers.

**Tech Stack:** Python 3.13, PySide6, SQLite, `httpx>=0.28`, `requests`, `pytest`, `yt-dlp`

---

## File Map

- Modify `src/atv_player/models.py`
  Add persisted proxy fields to `AppConfig`.
- Modify `src/atv_player/storage.py`
  Add schema migration, load/save logic, and normalization helpers for proxy settings.
- Create `src/atv_player/network_proxy.py`
  Define proxy config, bypass rule parsing, decision objects, and adapters for `httpx`, `requests`, and `yt-dlp`.
- Modify `src/atv_player/ui/advanced_settings_dialog.py`
  Turn the dialog into tabbed UI and add the proxy form plus validation.
- Modify `src/atv_player/app.py`
  Build a shared proxy-decider loader and inject it into networked services.
- Modify `src/atv_player/api.py`
  Build the fixed-host API client with the right `httpx.Client` proxy settings.
- Modify `src/atv_player/metadata/providers/tmdb_client.py`
  Apply proxy-aware client construction for TMDB.
- Modify `src/atv_player/metadata/providers/bangumi_client.py`
  Apply proxy-aware client construction for Bangumi.
- Modify `src/atv_player/metadata/providers/local_douban_client.py`
  Apply proxy-aware client construction for local Douban fetches.
- Modify `src/atv_player/playback_parsers.py`
  Pass proxy-aware kwargs into parser GET/POST calls.
- Modify `src/atv_player/ui/poster_loader.py`
  Pass proxy-aware kwargs into poster downloads.
- Modify `src/atv_player/plugins/loader.py`
  Pass proxy-aware kwargs into remote plugin downloads.
- Modify `src/atv_player/danmaku/service.py`
  Thread proxy decider into default providers.
- Modify `src/atv_player/danmaku/providers/*.py`
  Pass proxy-aware kwargs into provider requests.
- Modify `src/atv_player/danmaku/direct_parse.py`
  Pass proxy-aware kwargs into direct parse requests.
- Modify `src/atv_player/proxy/segment.py`
  Pass proxy-aware kwargs into upstream segment fetches.
- Modify `src/atv_player/proxy/server.py`
  Pass proxy-aware kwargs into upstream m3u8 / asset fetches.
- Modify `src/atv_player/player/bluray_iso.py`
  Pass proxy-aware kwargs into remote ISO probing requests.
- Modify `src/atv_player/yt_dlp_service.py`
  Append `--proxy` when the target URL should use manual proxy and skip it when bypass rules say direct.
- Modify `src/atv_player/player/ytdlp_runtime.py`
  Allow runtime args builder to accept an optional proxy argument without disturbing existing cookie flags.
- Modify `tests/test_storage.py`
  Cover persistence defaults, round-trip, and migration for proxy fields.
- Create `tests/test_network_proxy.py`
  Cover rule parsing, matching, decision semantics, and adapters.
- Modify `tests/test_main_window_ui.py`
  Cover proxy tab behavior, validation, and save flow.
- Modify `tests/test_api_client.py`
  Cover fixed-host client proxy kwargs via a fake `httpx.Client` factory.
- Modify `tests/test_metadata_tmdb_client.py`
  Cover TMDB proxy-aware client construction.
- Modify `tests/test_local_douban_client.py`
  Cover local Douban proxy-aware client construction.
- Modify `tests/test_playback_parsers.py`
  Cover proxy kwargs flowing into parser GET/POST calls.
- Modify `tests/test_poster_loader.py`
  Cover proxy kwargs flowing into poster downloads.
- Modify `tests/test_spider_plugin_loader.py`
  Cover proxy kwargs flowing into remote plugin fetches.
- Modify `tests/test_hls_proxy_segment.py`
  Cover proxy kwargs flowing into upstream segment fetches.
- Modify `tests/test_yt_dlp_service.py`
  Cover generated `yt-dlp` command with and without proxy.

### Task 1: Persist Proxy Settings In `AppConfig` And SQLite

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing persistence tests**

```python
def test_settings_repository_round_trip_persists_network_proxy_fields(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(
        network_proxy_mode="socks5",
        network_proxy_url="socks5://user:pass@127.0.0.1:1080",
        network_proxy_bypass_rules=["localhost", "127.0.0.1", "10.0.0.0/8"],
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.network_proxy_mode == "socks5"
    assert saved.network_proxy_url == "socks5://user:pass@127.0.0.1:1080"
    assert saved.network_proxy_bypass_rules == ["localhost", "127.0.0.1", "10.0.0.0/8"]


def test_settings_repository_migrates_missing_network_proxy_columns(tmp_path: Path) -> None:
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

    assert config.network_proxy_mode == "direct"
    assert config.network_proxy_url == ""
    assert config.network_proxy_bypass_rules == [
        "localhost",
        "127.0.0.1",
        "::1",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        ".local",
    ]
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -k network_proxy -q`

Expected: FAIL with `TypeError` or missing-column assertions because `AppConfig` and `SettingsRepository` do not yet know about `network_proxy_*`.

- [ ] **Step 3: Add `AppConfig` fields and `SettingsRepository` schema/load/save support**

```python
# src/atv_player/models.py
@dataclass(slots=True)
class AppConfig:
    base_url: str = "http://127.0.0.1:4567"
    username: str = ""
    token: str = ""
    vod_token: str = ""
    metadata_enhancement_enabled: bool = True
    metadata_douban_cookie: str = ""
    metadata_tmdb_api_key: str = ""
    metadata_bangumi_access_token: str = ""
    network_proxy_mode: str = "direct"
    network_proxy_url: str = ""
    network_proxy_bypass_rules: list[str] = field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "::1",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            ".local",
        ]
    )
```

```python
# src/atv_player/storage.py
_VALID_NETWORK_PROXY_MODES = {"direct", "system", "http", "https", "socks5"}
_DEFAULT_NETWORK_PROXY_BYPASS_RULES = [
    "localhost",
    "127.0.0.1",
    "::1",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    ".local",
]


def _normalize_network_proxy_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_NETWORK_PROXY_MODES else "direct"


def _normalize_network_proxy_url(value: object) -> str:
    return str(value or "").strip()


def _normalize_network_proxy_bypass_rules(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        value = []
    rules: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        rules.append(text)
        seen.add(text)
    return rules or list(_DEFAULT_NETWORK_PROXY_BYPASS_RULES)
```

```python
# src/atv_player/storage.py inside CREATE TABLE and migration block
network_proxy_mode TEXT NOT NULL DEFAULT 'direct',
network_proxy_url TEXT NOT NULL DEFAULT '',
network_proxy_bypass_rules TEXT NOT NULL DEFAULT '[]'
```

```python
# src/atv_player/storage.py inside the AppConfig load/save tuples
network_proxy_mode=_normalize_network_proxy_mode(network_proxy_mode),
network_proxy_url=_normalize_network_proxy_url(network_proxy_url),
network_proxy_bypass_rules=_normalize_network_proxy_bypass_rules(network_proxy_bypass_rules),
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -k network_proxy -q`

Expected: PASS with the new proxy fields round-tripping and the migration backfilling defaults.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist network proxy settings"
```

### Task 2: Build The Central Proxy Decision Module

**Files:**
- Create: `src/atv_player/network_proxy.py`
- Test: `tests/test_network_proxy.py`

- [ ] **Step 1: Write the failing proxy-core tests**

```python
from atv_player.network_proxy import (
    ProxyConfig,
    ProxyDecider,
    build_httpx_kwargs_for_url,
    build_requests_proxies_for_url,
    build_ytdlp_proxy_args,
)


def test_proxy_decider_returns_direct_for_bypass_host() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="socks5",
            proxy_url="socks5://127.0.0.1:1080",
            bypass_rules=["localhost", ".local", "10.0.0.0/8"],
        )
    )

    decision = decider.decide("http://127.0.0.1:4567/api/capabilities")

    assert decision.kind == "direct"
    assert decision.proxy_url == ""


def test_proxy_decider_returns_manual_proxy_for_remote_url() -> None:
    decider = ProxyDecider(
        ProxyConfig(
            mode="http",
            proxy_url="http://user:pass@127.0.0.1:7890",
            bypass_rules=["localhost"],
        )
    )

    decision = decider.decide("https://api.themoviedb.org/3/search/tv")

    assert decision.kind == "manual"
    assert decision.proxy_url == "http://user:pass@127.0.0.1:7890"


def test_build_httpx_kwargs_for_url_disables_env_for_bypass() -> None:
    decider = ProxyDecider(ProxyConfig(mode="system", proxy_url="", bypass_rules=["127.0.0.1"]))

    assert build_httpx_kwargs_for_url(decider, "http://127.0.0.1:4567/api") == {"trust_env": False}


def test_build_requests_proxies_for_url_applies_manual_proxy() -> None:
    decider = ProxyDecider(ProxyConfig(mode="https", proxy_url="https://127.0.0.1:8443", bypass_rules=[]))

    assert build_requests_proxies_for_url(decider, "https://sec.example.com/check") == {
        "http": "https://127.0.0.1:8443",
        "https": "https://127.0.0.1:8443",
    }


def test_build_ytdlp_proxy_args_skips_bypass_targets() -> None:
    decider = ProxyDecider(ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=["youtu.be"]))

    assert build_ytdlp_proxy_args(decider, "https://youtu.be/test123") == []
```

- [ ] **Step 2: Run the proxy-core tests to verify they fail**

Run: `uv run pytest tests/test_network_proxy.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.network_proxy'`.

- [ ] **Step 3: Implement rule parsing, decisions, and adapters**

```python
# src/atv_player/network_proxy.py
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    mode: str = "direct"
    proxy_url: str = ""
    bypass_rules: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProxyDecision:
    kind: str
    proxy_url: str = ""


class ProxyRuleError(ValueError):
    pass


class ProxyDecider:
    def __init__(self, config: ProxyConfig) -> None:
        self._config = ProxyConfig(
            mode=config.mode,
            proxy_url=config.proxy_url,
            bypass_rules=list(config.bypass_rules),
        )

    def decide(self, target_url: str) -> ProxyDecision:
        parsed = urlparse(str(target_url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            return ProxyDecision("direct")
        host = (parsed.hostname or "").strip().lower()
        if self._matches_bypass(host):
            return ProxyDecision("direct")
        if self._config.mode == "direct":
            return ProxyDecision("direct")
        if self._config.mode == "system":
            return ProxyDecision("system")
        return ProxyDecision("manual", self._config.proxy_url)
```

```python
# src/atv_player/network_proxy.py adapters
def build_httpx_kwargs_for_url(decider: ProxyDecider | None, target_url: str) -> dict[str, object]:
    if decider is None:
        return {}
    decision = decider.decide(target_url)
    if decision.kind == "direct":
        return {"trust_env": False}
    if decision.kind == "system":
        return {"trust_env": True}
    return {"proxy": decision.proxy_url, "trust_env": False}


def build_requests_proxies_for_url(decider: ProxyDecider | None, target_url: str) -> dict[str, str]:
    if decider is None:
        return {}
    decision = decider.decide(target_url)
    if decision.kind != "manual":
        return {}
    return {"http": decision.proxy_url, "https": decision.proxy_url}


def build_ytdlp_proxy_args(decider: ProxyDecider | None, target_url: str) -> list[str]:
    if decider is None:
        return []
    decision = decider.decide(target_url)
    if decision.kind != "manual":
        return []
    return ["--proxy", decision.proxy_url]
```

- [ ] **Step 4: Run the proxy-core tests to verify they pass**

Run: `uv run pytest tests/test_network_proxy.py -q`

Expected: PASS with direct/system/manual decisions and adapter outputs behaving exactly as the tests assert.

- [ ] **Step 5: Commit the proxy-core slice**

```bash
git add src/atv_player/network_proxy.py tests/test_network_proxy.py
git commit -m "feat: add network proxy decision layer"
```

### Task 3: Add The `网络代理` Tab To Advanced Settings

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing dialog tests**

```python
def test_advanced_settings_dialog_loads_network_proxy_values() -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(
        network_proxy_mode="socks5",
        network_proxy_url="socks5://user:pass@127.0.0.1:1080",
        network_proxy_bypass_rules=["localhost", "127.0.0.1"],
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)

    assert dialog.settings_tabs.tabText(1) == "网络代理"
    assert dialog.network_proxy_mode_combo.currentData() == "socks5"
    assert dialog.network_proxy_url_edit.text() == "socks5://user:pass@127.0.0.1:1080"
    assert dialog.network_proxy_bypass_rules_edit.toPlainText() == "localhost\n127.0.0.1"


def test_advanced_settings_dialog_disables_proxy_url_for_system_mode() -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(AppConfig(network_proxy_mode="system"), save_config=lambda: None)

    assert dialog.network_proxy_url_edit.isEnabled() is False


def test_advanced_settings_dialog_rejects_invalid_proxy_url(monkeypatch) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog
    from atv_player.ui import advanced_settings_dialog as module

    messages: list[str] = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *_args: messages.append(_args[-1]))
    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: None)
    dialog.network_proxy_mode_combo.setCurrentIndex(dialog.network_proxy_mode_combo.findData("socks5"))
    dialog.network_proxy_url_edit.setText("http://127.0.0.1:7890")

    dialog._save()

    assert messages == ["SOCKS5 模式要求 socks5:// 代理地址"]
```

- [ ] **Step 2: Run the dialog tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k network_proxy -q`

Expected: FAIL with missing widget attributes because the dialog still only exposes metadata controls.

- [ ] **Step 3: Implement the tabbed dialog, proxy form, and validation**

```python
# src/atv_player/ui/advanced_settings_dialog.py
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

self.settings_tabs = QTabWidget()
self.metadata_tab = QWidget()
self.network_proxy_tab = QWidget()
self.settings_tabs.addTab(self.metadata_tab, "元数据")
self.settings_tabs.addTab(self.network_proxy_tab, "网络代理")

self.network_proxy_mode_combo = QComboBox()
self.network_proxy_mode_combo.addItem("直连", "direct")
self.network_proxy_mode_combo.addItem("系统代理", "system")
self.network_proxy_mode_combo.addItem("HTTP", "http")
self.network_proxy_mode_combo.addItem("HTTPS", "https")
self.network_proxy_mode_combo.addItem("SOCKS5", "socks5")
self.network_proxy_url_edit = QLineEdit()
self.network_proxy_bypass_rules_edit = QPlainTextEdit()
self.network_proxy_scope_label = QLabel("覆盖范围：API、元数据、解析源、弹幕、海报、插件下载、HLS 上游请求、yt-dlp")
```

```python
# src/atv_player/ui/advanced_settings_dialog.py validation helpers
def _sync_network_proxy_inputs(self) -> None:
    manual_mode = self.network_proxy_mode_combo.currentData() in {"http", "https", "socks5"}
    self.network_proxy_url_edit.setEnabled(manual_mode)


def _validated_network_proxy_values(self) -> tuple[str, str, list[str]] | None:
    mode = str(self.network_proxy_mode_combo.currentData() or "direct")
    proxy_url = self.network_proxy_url_edit.text().strip()
    bypass_rules = [line.strip() for line in self.network_proxy_bypass_rules_edit.toPlainText().splitlines() if line.strip()]
    if mode == "socks5" and proxy_url and not proxy_url.startswith("socks5://"):
        QMessageBox.warning(self, "代理地址无效", "SOCKS5 模式要求 socks5:// 代理地址")
        return None
    return mode, proxy_url, bypass_rules
```

- [ ] **Step 4: Run the dialog tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k network_proxy -q`

Expected: PASS with the new tab, enable/disable behavior, and save-time validation.

- [ ] **Step 5: Commit the dialog slice**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add proxy controls to advanced settings"
```

### Task 4: Inject Proxy Decisions Into `AppCoordinator` And `ApiClient`

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/api.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the failing fixed-host API tests**

```python
def test_api_client_builds_direct_httpx_client_for_local_base_url() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))

    client = ApiClient(
        base_url="http://127.0.0.1:4567",
        proxy_decider=ProxyDecider(ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=["127.0.0.1"])),
        client_factory=fake_client_factory,
    )

    assert captured["trust_env"] is False
    assert "proxy" not in captured
    client.close()


def test_api_client_builds_manual_proxy_httpx_client_for_remote_base_url() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))

    client = ApiClient(
        base_url="https://demo.remote.example",
        proxy_decider=ProxyDecider(ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])),
        client_factory=fake_client_factory,
    )

    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["trust_env"] is False
    client.close()
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `uv run pytest tests/test_api_client.py -k "builds_direct_httpx_client or builds_manual_proxy_httpx_client" -q`

Expected: FAIL because `ApiClient` does not accept `proxy_decider` or `client_factory`.

- [ ] **Step 3: Build proxy-aware fixed-host client construction and inject it from `AppCoordinator`**

```python
# src/atv_player/api.py
class ApiClient:
    def __init__(
        self,
        base_url: str,
        token: str = "",
        vod_token: str = "",
        transport: httpx.BaseTransport | None = None,
        proxy_decider: ProxyDecider | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        headers = {"Authorization": token} if token else {}
        self._vod_token = vod_token
        client_kwargs = {
            "base_url": base_url.rstrip("/"),
            "headers": headers,
            "transport": transport,
            "timeout": 30.0,
        }
        client_kwargs.update(build_httpx_kwargs_for_url(proxy_decider, base_url))
        self._client = client_factory(**client_kwargs)
```

```python
# src/atv_player/app.py
def _build_proxy_decider(self) -> ProxyDecider:
    config = self.repo.load_config()
    return ProxyDecider(
        ProxyConfig(
            mode=config.network_proxy_mode,
            proxy_url=config.network_proxy_url,
            bypass_rules=list(config.network_proxy_bypass_rules),
        )
    )

self._api_client = ApiClient(
    config.base_url,
    token=config.token,
    vod_token=config.vod_token,
    proxy_decider=self._build_proxy_decider(),
)
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `uv run pytest tests/test_api_client.py -k "builds_direct_httpx_client or builds_manual_proxy_httpx_client" -q`

Expected: PASS with local API hosts bypassing proxy and remote base URLs using the manual proxy settings.

- [ ] **Step 5: Commit the fixed-host API slice**

```bash
git add src/atv_player/app.py src/atv_player/api.py tests/test_api_client.py
git commit -m "feat: wire proxy settings into api client"
```

### Task 5: Apply The Same Fixed-Host Wiring To Metadata Clients

**Files:**
- Modify: `src/atv_player/metadata/providers/tmdb_client.py`
- Modify: `src/atv_player/metadata/providers/bangumi_client.py`
- Modify: `src/atv_player/metadata/providers/local_douban_client.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_metadata_tmdb_client.py`
- Test: `tests/test_local_douban_client.py`

- [ ] **Step 1: Write the failing metadata-client tests**

```python
def test_tmdb_client_builds_manual_proxy_httpx_client() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []})))

    TMDBClient(
        api_key="tmdb-key",
        proxy_decider=ProxyDecider(ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])),
        client_factory=fake_client_factory,
    )

    assert captured["proxy"] == "http://127.0.0.1:7890"


def test_local_douban_client_builds_direct_httpx_client_for_bypass() -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="[]")))

    LocalDoubanClient(
        cookie="bid=demo;",
        proxy_decider=ProxyDecider(ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=["movie.douban.com"])),
        client_factory=fake_client_factory,
    )

    assert captured["trust_env"] is False
```

- [ ] **Step 2: Run the metadata-client tests to verify they fail**

Run: `uv run pytest tests/test_metadata_tmdb_client.py tests/test_local_douban_client.py -k "proxy" -q`

Expected: FAIL because these clients currently do not accept `proxy_decider` or `client_factory`.

- [ ] **Step 3: Thread proxy-aware `httpx.Client` kwargs into metadata clients and app factories**

```python
# src/atv_player/metadata/providers/tmdb_client.py
class TMDBClient:
    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        proxy_decider: ProxyDecider | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        client_kwargs = {
            "base_url": self._BASE_URL,
            "transport": transport,
            "timeout": 20.0,
        }
        client_kwargs.update(build_httpx_kwargs_for_url(proxy_decider, self._BASE_URL))
        self._client = client_factory(**client_kwargs)
```

```python
# src/atv_player/app.py
providers.append(BangumiMetadataProvider(BangumiClient(
    access_token=config.metadata_bangumi_access_token,
    proxy_decider=self._build_proxy_decider(),
)))
if str(config.metadata_douban_cookie or "").strip():
    local_douban_client = LocalDoubanClient(
        cookie=config.metadata_douban_cookie,
        proxy_decider=self._build_proxy_decider(),
    )
if str(config.metadata_tmdb_api_key or "").strip():
    providers.append(TMDBProvider(TMDBClient(
        api_key=config.metadata_tmdb_api_key,
        proxy_decider=self._build_proxy_decider(),
    )))
```

- [ ] **Step 4: Run the metadata-client tests to verify they pass**

Run: `uv run pytest tests/test_metadata_tmdb_client.py tests/test_local_douban_client.py -k "proxy" -q`

Expected: PASS with proxy kwargs applied during client construction.

- [ ] **Step 5: Commit the metadata fixed-host slice**

```bash
git add src/atv_player/metadata/providers/tmdb_client.py src/atv_player/metadata/providers/bangumi_client.py src/atv_player/metadata/providers/local_douban_client.py src/atv_player/app.py tests/test_metadata_tmdb_client.py tests/test_local_douban_client.py
git commit -m "feat: apply proxy settings to metadata clients"
```

### Task 6: Wire Proxy-Aware Kwargs Into Per-Request HTTP Call Sites

**Files:**
- Modify: `src/atv_player/ui/poster_loader.py`
- Modify: `src/atv_player/playback_parsers.py`
- Modify: `src/atv_player/plugins/loader.py`
- Modify: `src/atv_player/danmaku/service.py`
- Modify: `src/atv_player/danmaku/direct_parse.py`
- Modify: `src/atv_player/danmaku/providers/bilibili.py`
- Modify: `src/atv_player/danmaku/providers/iqiyi.py`
- Modify: `src/atv_player/danmaku/providers/mgtv.py`
- Modify: `src/atv_player/danmaku/providers/tencent.py`
- Modify: `src/atv_player/danmaku/providers/youku.py`
- Modify: `src/atv_player/proxy/segment.py`
- Modify: `src/atv_player/proxy/server.py`
- Modify: `src/atv_player/player/bluray_iso.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_poster_loader.py`
- Test: `tests/test_playback_parsers.py`
- Test: `tests/test_spider_plugin_loader.py`
- Test: `tests/test_hls_proxy_segment.py`

- [ ] **Step 1: Write the failing per-request wiring tests**

```python
def test_load_remote_poster_image_passes_proxy_kwargs(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs)
        return httpx.Response(200, content=b"not-an-image")

    load_remote_poster_image(
        "https://img.example/poster.jpg",
        QSize(120, 180),
        get=fake_get,
        proxy_decider=ProxyDecider(ProxyConfig(mode="http", proxy_url="http://127.0.0.1:7890", bypass_rules=[])),
    )

    assert seen["proxy"] == "http://127.0.0.1:7890"


def test_spider_plugin_loader_fetch_remote_text_passes_proxy_kwargs() -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        seen.update(kwargs)
        return httpx.Response(200, text="print('ok')", request=httpx.Request("GET", url))

    loader = SpiderPluginLoader(
        Path("/tmp/plugins"),
        get=fake_get,
        proxy_decider=ProxyDecider(ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=[])),
    )

    assert loader._fetch_remote_text("https://plugins.example/demo.py") == "print('ok')"
    assert seen["proxy"] == "socks5://127.0.0.1:1080"
```

- [ ] **Step 2: Run the per-request tests to verify they fail**

Run: `uv run pytest tests/test_poster_loader.py tests/test_playback_parsers.py tests/test_spider_plugin_loader.py tests/test_hls_proxy_segment.py -k "proxy" -q`

Expected: FAIL because these helpers and services do not yet accept `proxy_decider` or merge proxy kwargs into outgoing requests.

- [ ] **Step 3: Thread `proxy_decider` through constructors/helpers and merge `build_httpx_kwargs_for_url` at call time**

```python
# src/atv_player/ui/poster_loader.py
def load_remote_poster_image(
    image_url: str,
    target_size: QSize,
    timeout: float = POSTER_REQUEST_TIMEOUT_SECONDS,
    get=httpx.get,
    proxy_decider: ProxyDecider | None = None,
) -> QImage | None:
    normalized_url = normalize_poster_url(image_url)
    if not normalized_url:
        return None
    cache_path = poster_cache_path(normalized_url)
    cached_image = _load_cached_poster_image(cache_path, target_size)
    if cached_image is not None:
        return cached_image
    response = get(
        normalized_url,
        headers=build_poster_request_headers(normalized_url),
        timeout=timeout,
        follow_redirects=True,
        **build_httpx_kwargs_for_url(proxy_decider, normalized_url),
    )
```

```python
# src/atv_player/playback_parsers.py
class BuiltInPlaybackParserService:
    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        post: Callable[..., httpx.Response] = httpx.post,
        resolve_cache: PlaybackResolveCache | None = None,
        proxy_decider: ProxyDecider | None = None,
    ) -> None:
        self._get = get
        self._post = post
        self._resolve_cache = resolve_cache or PlaybackResolveCache()
        self._proxy_decider = proxy_decider

    def _resolve_with_parser(self, parser: BuiltInPlaybackParser, flag: str, url: str) -> BuiltInPlaybackParserResult:
        response = self._get(
            parser.api,
            params={"flag": flag, "url": url},
            headers=dict(parser.headers),
            timeout=15.0,
            follow_redirects=True,
            **build_httpx_kwargs_for_url(self._proxy_decider, parser.api),
        )
```

```python
# src/atv_player/plugins/loader.py
class SpiderPluginLoader:
    def __init__(self, cache_dir: Path, get=httpx.get, keyring=None, proxy_decider: ProxyDecider | None = None) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._get = get
        self._keyring = keyring
        self._runtime = SecSpiderRuntime(keyring) if keyring is not None else None
        self._proxy_decider = proxy_decider

    def _fetch_remote_text(self, url: str) -> str:
        response = self._get(
            url,
            timeout=15.0,
            follow_redirects=True,
            **build_httpx_kwargs_for_url(self._proxy_decider, url),
        )
```

```python
# src/atv_player/app.py
self._playback_parser_service = BuiltInPlaybackParserService(proxy_decider=self._build_proxy_decider())
self._plugin_loader = SpiderPluginLoader(cache_dir, proxy_decider=self._build_proxy_decider())
self._danmaku_service = create_default_danmaku_service(proxy_decider=self._build_proxy_decider())
```

- [ ] **Step 4: Run the per-request tests to verify they pass**

Run: `uv run pytest tests/test_poster_loader.py tests/test_playback_parsers.py tests/test_spider_plugin_loader.py tests/test_hls_proxy_segment.py -k "proxy" -q`

Expected: PASS with the new proxy kwargs reaching poster downloads, parser requests, remote plugin fetches, and HLS upstream fetches.

- [ ] **Step 5: Commit the per-request slice**

```bash
git add src/atv_player/ui/poster_loader.py src/atv_player/playback_parsers.py src/atv_player/plugins/loader.py src/atv_player/danmaku/service.py src/atv_player/danmaku/direct_parse.py src/atv_player/danmaku/providers/bilibili.py src/atv_player/danmaku/providers/iqiyi.py src/atv_player/danmaku/providers/mgtv.py src/atv_player/danmaku/providers/tencent.py src/atv_player/danmaku/providers/youku.py src/atv_player/proxy/segment.py src/atv_player/proxy/server.py src/atv_player/player/bluray_iso.py src/atv_player/app.py tests/test_poster_loader.py tests/test_playback_parsers.py tests/test_spider_plugin_loader.py tests/test_hls_proxy_segment.py
git commit -m "feat: apply proxy settings to request-based network helpers"
```

### Task 7: Append Proxy Args To `yt-dlp` And Run Focused Regression

**Files:**
- Modify: `src/atv_player/player/ytdlp_runtime.py`
- Modify: `src/atv_player/yt_dlp_service.py`
- Test: `tests/test_yt_dlp_service.py`

- [ ] **Step 1: Write the failing `yt-dlp` proxy tests**

```python
def test_extract_info_via_command_includes_proxy_when_manual_proxy_is_selected(monkeypatch, service):
    run_calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        run_calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(_sample_info()), stderr="")

    monkeypatch.setattr("atv_player.yt_dlp_service.subprocess.run", fake_run)
    service._proxy_decider = ProxyDecider(
        ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=[])
    )

    service._extract_info_via_command("https://www.youtube.com/watch?v=test123", 1080)

    command = run_calls[0]
    assert "--proxy" in command
    assert command[command.index("--proxy") + 1] == "socks5://127.0.0.1:1080"


def test_extract_info_via_command_skips_proxy_for_bypass_target(monkeypatch, service):
    run_calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        run_calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(_sample_info()), stderr="")

    monkeypatch.setattr("atv_player.yt_dlp_service.subprocess.run", fake_run)
    service._proxy_decider = ProxyDecider(
        ProxyConfig(mode="socks5", proxy_url="socks5://127.0.0.1:1080", bypass_rules=["www.youtube.com"])
    )

    service._extract_info_via_command("https://www.youtube.com/watch?v=test123", 1080)

    assert "--proxy" not in run_calls[0]
```

- [ ] **Step 2: Run the `yt-dlp` tests to verify they fail**

Run: `uv run pytest tests/test_yt_dlp_service.py -k proxy -q`

Expected: FAIL because the command builder never appends proxy args.

- [ ] **Step 3: Add optional proxy arg generation to runtime and use it from the service**

```python
# src/atv_player/player/ytdlp_runtime.py
def build_ytdlp_command_args(proxy_args: list[str] | None = None) -> list[str]:
    args: list[str] = []
    if proxy_args:
        args.extend(proxy_args)
    browser = _resolved_cookie_browser()
    if browser:
        args.extend(["--cookies-from-browser", browser])
    else:
        cookie_file = _resolved_cookie_file()
        if cookie_file:
            args.extend(["--cookies", cookie_file])
    remote_components = _default_remote_components()
    if remote_components:
        args.extend(["--remote-components", remote_components])
    return args
```

```python
# src/atv_player/yt_dlp_service.py
class YtdlpPlaybackService:
    def __init__(self, proxy_decider: ProxyDecider | None = None) -> None:
        self._proxy_decider = proxy_decider
        self._ytdlp_path = resolve_system_ytdlp_path()

    def _extract_info_via_command(self, url: str, max_height: int | None) -> dict:
        command = [
            self._ytdlp_path or resolve_system_ytdlp_path(),
            *build_ytdlp_command_args(build_ytdlp_proxy_args(self._proxy_decider, url)),
            "--dump-single-json",
            "--no-warnings",
            url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "yt-dlp failed")
        return json.loads(completed.stdout)
```

- [ ] **Step 4: Run the focused regression suite**

Run: `uv run pytest tests/test_storage.py -k network_proxy -q`

Expected: PASS

Run: `uv run pytest tests/test_network_proxy.py -q`

Expected: PASS

Run: `uv run pytest tests/test_main_window_ui.py -k network_proxy -q`

Expected: PASS

Run: `uv run pytest tests/test_api_client.py tests/test_metadata_tmdb_client.py tests/test_local_douban_client.py -k proxy -q`

Expected: PASS

Run: `uv run pytest tests/test_poster_loader.py tests/test_playback_parsers.py tests/test_spider_plugin_loader.py tests/test_hls_proxy_segment.py tests/test_yt_dlp_service.py -k proxy -q`

Expected: PASS

- [ ] **Step 5: Commit the `yt-dlp` and verification slice**

```bash
git add src/atv_player/player/ytdlp_runtime.py src/atv_player/yt_dlp_service.py tests/test_yt_dlp_service.py
git commit -m "feat: route yt-dlp through proxy settings"
```

## Self-Review

### Spec coverage

- Persisted fields and migration: covered by Task 1.
- Centralized proxy model, rules, and adapters: covered by Task 2.
- Advanced settings tab and validation: covered by Task 3.
- AppCoordinator injection and fixed-host client wiring: covered by Tasks 4 and 5.
- Request-based helper wiring for posters, parsers, plugins, danmaku, HLS, and remote ISO probing: covered by Task 6.
- `yt-dlp` command-line proxy control: covered by Task 7.
- Focused regression around storage, UI, API, helper calls, and `yt-dlp`: covered by Task 7 Step 4.

### Placeholder scan

- No `TODO`, `TBD`, or “similar to previous task” shortcuts remain.
- Every code-changing step includes concrete code snippets.
- Every verification step includes a concrete command and expected result.

### Type consistency

- Persisted fields consistently use `network_proxy_mode`, `network_proxy_url`, and `network_proxy_bypass_rules`.
- Shared proxy types consistently use `ProxyConfig`, `ProxyDecider`, and `ProxyDecision`.
- All adapter helpers consistently use `build_httpx_kwargs_for_url`, `build_requests_proxies_for_url`, and `build_ytdlp_proxy_args`.
