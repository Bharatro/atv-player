# Playback Settings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted `播放设置` tab to advanced settings, wire `YouTube Cookie` plus common mpv startup knobs into runtime behavior, and preserve the existing ISO / `yt-dlp` special profiles with clear override precedence.

**Architecture:** Extend `AppConfig` and `SettingsRepository` with six playback fields, add a third tab to `AdvancedSettingsDialog`, inject config into `MpvWidget` and `YtdlpPlaybackService`, and parse `更多 MPV 配置` as a final override layer after source-specific mpv profiles. Keep the current normal / ISO / `yt-dlp` profile split intact, but rename the user-facing prefetch control to `普通流预读时长` so its scope is explicit.

**Tech Stack:** Python 3.13, PySide6, SQLite, mpv, yt-dlp, pytest

---

## File Map

- Modify `src/atv_player/models.py`
  Add persisted playback-settings fields to `AppConfig`.
- Modify `src/atv_player/storage.py`
  Add schema migration, normalization, load/save support for the new playback fields.
- Modify `src/atv_player/ui/advanced_settings_dialog.py`
  Add the `播放设置` tab, its widgets, validation, and save wiring.
- Modify `src/atv_player/player/ytdlp_runtime.py`
  Stop implicitly defaulting to `chrome`; accept explicit cookie-browser inputs for command args and mpv `ytdl_raw_options`.
- Modify `src/atv_player/yt_dlp_service.py`
  Accept a config loader and thread the configured cookie browser into command construction.
- Modify `src/atv_player/app.py`
  Construct `YtdlpPlaybackService` with a config loader so app playback uses the saved cookie setting.
- Modify `src/atv_player/player/mpv_widget.py`
  Accept config, derive base mpv options from it, apply source-specific profiles, and merge `更多 MPV 配置` last.
- Modify `src/atv_player/ui/player_window.py`
  Pass `config` into `MpvWidget`.
- Modify `tests/test_storage.py`
  Cover round-trip and migration for the playback-settings fields.
- Modify `tests/test_main_window_ui.py`
  Cover the new `播放设置` tab, loading, saving, and validation failures.
- Modify `tests/test_ytdlp_runtime.py`
  Cover the new explicit cookie-browser helpers and the removal of the implicit `chrome` default.
- Modify `tests/test_yt_dlp_service.py`
  Cover `YtdlpPlaybackService` passing the configured cookie browser into `yt-dlp`.
- Modify `tests/test_mpv_widget.py`
  Cover config-driven `hwdec`, `demuxer_max_bytes`, `network_timeout`, default readahead, source-profile precedence, and extra-option overrides.

### Task 1: Persist Playback Settings In `AppConfig` And SQLite

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
def test_settings_repository_round_trip_persists_playback_settings(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(
        youtube_cookie_browser="edge",
        mpv_cache_size_mb=768,
        mpv_hwdec_mode="no",
        mpv_network_timeout_seconds=25,
        mpv_default_readahead_secs=45,
        mpv_extra_options="demuxer-max-back-bytes=256M\ncache-pause-wait=8",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.youtube_cookie_browser == "edge"
    assert saved.mpv_cache_size_mb == 768
    assert saved.mpv_hwdec_mode == "no"
    assert saved.mpv_network_timeout_seconds == 25
    assert saved.mpv_default_readahead_secs == 45
    assert saved.mpv_extra_options == "demuxer-max-back-bytes=256M\ncache-pause-wait=8"
    assert saved == config


def test_settings_repository_migrates_missing_playback_settings_columns(tmp_path: Path) -> None:
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

    assert config.youtube_cookie_browser == ""
    assert config.mpv_cache_size_mb == 512
    assert config.mpv_hwdec_mode == "auto-safe"
    assert config.mpv_network_timeout_seconds == 15
    assert config.mpv_default_readahead_secs == 20
    assert config.mpv_extra_options == ""
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -k playback_settings -q`

Expected: `FAIL` because `AppConfig` and `SettingsRepository` do not yet know about the six playback fields.

- [ ] **Step 3: Add the new `AppConfig` fields and storage normalization**

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
    network_proxy_bypass_rules: list[str] = field(default_factory=lambda: list(_DEFAULT_NETWORK_PROXY_BYPASS_RULES))
    youtube_cookie_browser: str = ""
    mpv_cache_size_mb: int = 512
    mpv_hwdec_mode: str = "auto-safe"
    mpv_network_timeout_seconds: int = 15
    mpv_default_readahead_secs: int = 20
    mpv_extra_options: str = ""
```

```python
# src/atv_player/storage.py
_VALID_YOUTUBE_COOKIE_BROWSERS = {"", "chrome", "edge", "firefox"}
_VALID_MPV_HWDEC_MODES = {"auto-safe", "no"}


def _normalize_youtube_cookie_browser(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_YOUTUBE_COOKIE_BROWSERS else ""


def _normalize_mpv_cache_size_mb(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 512
    return max(16, min(normalized, 4096))


def _normalize_mpv_hwdec_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_MPV_HWDEC_MODES else "auto-safe"


def _normalize_mpv_network_timeout_seconds(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 15
    return max(1, min(normalized, 300))


def _normalize_mpv_default_readahead_secs(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 20
    return max(1, min(normalized, 600))


def _normalize_mpv_extra_options(value: object) -> str:
    return str(value or "").strip()
```

```python
# src/atv_player/storage.py inside CREATE TABLE / migration / load / save
youtube_cookie_browser TEXT NOT NULL DEFAULT '',
mpv_cache_size_mb INTEGER NOT NULL DEFAULT 512,
mpv_hwdec_mode TEXT NOT NULL DEFAULT 'auto-safe',
mpv_network_timeout_seconds INTEGER NOT NULL DEFAULT 15,
mpv_default_readahead_secs INTEGER NOT NULL DEFAULT 20,
mpv_extra_options TEXT NOT NULL DEFAULT '',
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -k playback_settings -q`

Expected: `PASS` with both the round-trip and the legacy migration defaults covered.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist playback settings"
```

### Task 2: Add The `播放设置` Tab And Validation

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing dialog tests**

```python
def test_advanced_settings_dialog_adds_playback_tab_and_populates_existing_values(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig(
        youtube_cookie_browser="firefox",
        mpv_cache_size_mb=1024,
        mpv_hwdec_mode="no",
        mpv_network_timeout_seconds=20,
        mpv_default_readahead_secs=35,
        mpv_extra_options="cache-pause-wait=9\nstream-buffer-size=8M",
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.tabText(2) == "播放设置"
    assert dialog.youtube_cookie_browser_combo.currentData() == "firefox"
    assert dialog.mpv_cache_size_edit.text() == "1024"
    assert dialog.mpv_hwdec_mode_combo.currentData() == "no"
    assert dialog.mpv_network_timeout_edit.text() == "20"
    assert dialog.mpv_default_readahead_edit.text() == "35"
    assert dialog.mpv_extra_options_edit.toPlainText() == "cache-pause-wait=9\nstream-buffer-size=8M"


def test_advanced_settings_dialog_saves_trimmed_playback_settings(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    saved: list[AppConfig] = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    dialog.youtube_cookie_browser_combo.setCurrentIndex(dialog.youtube_cookie_browser_combo.findData("chrome"))
    dialog.mpv_cache_size_edit.setText(" 768 ")
    dialog.mpv_hwdec_mode_combo.setCurrentIndex(dialog.mpv_hwdec_mode_combo.findData("no"))
    dialog.mpv_network_timeout_edit.setText(" 22 ")
    dialog.mpv_default_readahead_edit.setText(" 40 ")
    dialog.mpv_extra_options_edit.setPlainText(" cache-pause-wait=8 \nstream-buffer-size=6M ")
    dialog._save()

    assert config.youtube_cookie_browser == "chrome"
    assert config.mpv_cache_size_mb == 768
    assert config.mpv_hwdec_mode == "no"
    assert config.mpv_network_timeout_seconds == 22
    assert config.mpv_default_readahead_secs == 40
    assert config.mpv_extra_options == "cache-pause-wait=8\nstream-buffer-size=6M"
    assert len(saved) == 1


def test_advanced_settings_dialog_rejects_invalid_extra_mpv_options(qtbot, monkeypatch) -> None:
    from atv_player.ui import advanced_settings_dialog as module
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    messages: list[str] = []

    def fake_warning(_parent, _title: str, text: str) -> int:
        messages.append(text)
        return 0

    monkeypatch.setattr(module.QMessageBox, "warning", fake_warning)
    dialog = AdvancedSettingsDialog(AppConfig(), save_config=lambda: None)
    qtbot.addWidget(dialog)

    dialog.mpv_extra_options_edit.setPlainText("cache-pause-wait\n=broken")
    dialog._save()

    assert messages == ["更多 MPV 配置第 1 行必须是 key=value 格式"]
```

- [ ] **Step 2: Run the dialog tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "playback_tab or extra_mpv_options or youtube_cookie_browser_combo" -q`

Expected: `FAIL` because the dialog does not yet expose playback widgets or validation.

- [ ] **Step 3: Implement the new tab and validation helpers**

```python
# src/atv_player/ui/advanced_settings_dialog.py
self.playback_tab = QWidget()
self.playback_group = QGroupBox("播放设置")
self.youtube_cookie_browser_combo = QComboBox()
self.youtube_cookie_browser_combo.addItem("不使用", "")
self.youtube_cookie_browser_combo.addItem("Chrome", "chrome")
self.youtube_cookie_browser_combo.addItem("Edge", "edge")
self.youtube_cookie_browser_combo.addItem("Firefox", "firefox")
self.mpv_cache_size_edit = QLineEdit()
self.mpv_hwdec_mode_combo = QComboBox()
self.mpv_hwdec_mode_combo.addItem("硬解", "auto-safe")
self.mpv_hwdec_mode_combo.addItem("软解", "no")
self.mpv_network_timeout_edit = QLineEdit()
self.mpv_default_readahead_edit = QLineEdit()
self.mpv_extra_options_edit = QPlainTextEdit()
self.playback_scope_label = QLabel(
    "说明：普通流预读时长只影响普通流；ISO / YouTube / DASH 仍保留内置专用参数。更多 MPV 配置会在最后应用，并可覆盖同名项。"
)
```

```python
# src/atv_player/ui/advanced_settings_dialog.py
def _validated_playback_values(self) -> tuple[str, int, str, int, int, str] | None:
    browser = str(self.youtube_cookie_browser_combo.currentData() or "")
    if browser not in {"", "chrome", "edge", "firefox"}:
        QMessageBox.warning(self, "YouTube Cookie 无效", "浏览器来源无效")
        return None

    def parse_int(text: str, *, label: str, minimum: int, maximum: int) -> int | None:
        try:
            value = int(text.strip())
        except ValueError:
            QMessageBox.warning(self, f"{label}无效", f"{label}必须是整数")
            return None
        if value < minimum or value > maximum:
            QMessageBox.warning(self, f"{label}无效", f"{label}必须在 {minimum} 到 {maximum} 之间")
            return None
        return value

    cache_size = parse_int(self.mpv_cache_size_edit.text(), label="播放缓存大小（MB）", minimum=16, maximum=4096)
    timeout = parse_int(self.mpv_network_timeout_edit.text(), label="网络超时", minimum=1, maximum=300)
    readahead = parse_int(self.mpv_default_readahead_edit.text(), label="普通流预读时长", minimum=1, maximum=600)
    if cache_size is None or timeout is None or readahead is None:
        return None

    normalized_lines: list[str] = []
    for index, raw_line in enumerate(self.mpv_extra_options_edit.toPlainText().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            QMessageBox.warning(self, "更多 MPV 配置无效", f"更多 MPV 配置第 {index} 行必须是 key=value 格式")
            return None
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            QMessageBox.warning(self, "更多 MPV 配置无效", f"更多 MPV 配置第 {index} 行的 key 不能为空")
            return None
        normalized_lines.append(f"{key}={value}")

    return (
        browser,
        cache_size,
        str(self.mpv_hwdec_mode_combo.currentData() or "auto-safe"),
        timeout,
        readahead,
        "\n".join(normalized_lines),
    )
```

- [ ] **Step 4: Run the dialog tests to verify they pass**

Run: `uv run pytest tests/test_main_window_ui.py -k "playback_tab or extra_mpv_options or youtube_cookie_browser_combo" -q`

Expected: `PASS` with the new tab loading, saving, and validation behavior covered.

- [ ] **Step 5: Commit the UI slice**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat: add playback settings tab"
```

### Task 3: Wire `YouTube Cookie` Into `yt-dlp` Runtime And Service

**Files:**
- Modify: `src/atv_player/player/ytdlp_runtime.py`
- Modify: `src/atv_player/yt_dlp_service.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_ytdlp_runtime.py`
- Test: `tests/test_yt_dlp_service.py`

- [ ] **Step 1: Write the failing `yt-dlp` runtime and service tests**

```python
def test_build_ytdlp_command_args_defaults_to_no_browser_cookies(monkeypatch) -> None:
    from atv_player.player import ytdlp_runtime

    monkeypatch.delenv("ATV_YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("ATV_YTDLP_COOKIE_FILE", raising=False)

    assert ytdlp_runtime.build_ytdlp_command_args(cookie_browser="") == []


def test_resolve_mpv_ytdl_raw_options_uses_explicit_browser_value() -> None:
    from atv_player.player import ytdlp_runtime

    assert ytdlp_runtime.resolve_mpv_ytdl_raw_options(cookie_browser="edge") == (
        "cookies-from-browser=edge,remote-components=ejs:github"
    )


def test_extract_info_via_command_prefers_configured_cookie_browser(monkeypatch) -> None:
    from atv_player.yt_dlp_service import YtdlpPlaybackService

    run_calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        run_calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(_sample_info()), stderr="")

    monkeypatch.setattr("atv_player.yt_dlp_service.subprocess.run", fake_run)
    service = YtdlpPlaybackService(config_loader=lambda: AppConfig(youtube_cookie_browser="firefox"))

    service._extract_info_via_command("https://www.youtube.com/watch?v=test123", 1080)

    command = run_calls[0]
    assert command[command.index("--cookies-from-browser") + 1] == "firefox"
```

- [ ] **Step 2: Run the focused `yt-dlp` tests to verify they fail**

Run: `uv run pytest tests/test_ytdlp_runtime.py tests/test_yt_dlp_service.py -k "cookie_browser or browser_cookies" -q`

Expected: `FAIL` because the runtime still implicitly defaults to `chrome` and the service has no config loader.

- [ ] **Step 3: Implement explicit cookie-browser plumbing**

```python
# src/atv_player/player/ytdlp_runtime.py
def _resolved_cookie_browser(cookie_browser: str = "") -> str:
    explicit = str(cookie_browser or "").strip().lower()
    if explicit in {"chrome", "edge", "firefox"}:
        return explicit
    raw_value = _normalized_env("ATV_YTDLP_COOKIES_FROM_BROWSER")
    if raw_value.lower() in {"0", "false", "no", "none", "off"}:
        return ""
    if raw_value:
        return raw_value
    if _resolved_cookie_file():
        return ""
    return ""


def build_ytdlp_command_args(
    proxy_args: list[str] | None = None,
    *,
    cookie_browser: str = "",
) -> list[str]:
    args: list[str] = []
    if proxy_args:
        args.extend(proxy_args)
    browser = _resolved_cookie_browser(cookie_browser)
    ...


def resolve_mpv_ytdl_raw_options(*, cookie_browser: str = "") -> str:
    options: list[str] = []
    browser = _resolved_cookie_browser(cookie_browser)
    ...
```

```python
# src/atv_player/yt_dlp_service.py
class YtdlpPlaybackService:
    def __init__(
        self,
        ttl_seconds: float = 300.0,
        now: Callable[[], float] = monotonic,
        proxy_decider: ProxyDecider | None = None,
        config_loader: Callable[[], AppConfig] | None = None,
    ) -> None:
        ...
        self._config_loader = config_loader

    def _configured_cookie_browser(self) -> str:
        if self._config_loader is None:
            return ""
        config = self._config_loader()
        return str(getattr(config, "youtube_cookie_browser", "") or "").strip().lower()
```

```python
# src/atv_player/yt_dlp_service.py inside _extract_info_via_command()
*build_ytdlp_command_args(
    build_ytdlp_proxy_args(self._proxy_decider, url),
    cookie_browser=self._configured_cookie_browser(),
),
```

```python
# src/atv_player/app.py
self._yt_dlp_service = YtdlpPlaybackService(
    proxy_decider=self._build_proxy_decider(),
    config_loader=self.repo.load_config,
)
```

- [ ] **Step 4: Run the focused `yt-dlp` tests to verify they pass**

Run: `uv run pytest tests/test_ytdlp_runtime.py tests/test_yt_dlp_service.py -k "cookie_browser or browser_cookies" -q`

Expected: `PASS`, proving the implicit `chrome` default is gone and configured browsers still pass through correctly.

- [ ] **Step 5: Commit the `yt-dlp` slice**

```bash
git add src/atv_player/player/ytdlp_runtime.py src/atv_player/yt_dlp_service.py src/atv_player/app.py tests/test_ytdlp_runtime.py tests/test_yt_dlp_service.py
git commit -m "feat: add configurable yt-dlp cookie browser"
```

### Task 4: Wire Playback Settings Into `MpvWidget` With Profile Precedence

**Files:**
- Modify: `src/atv_player/player/mpv_widget.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_mpv_widget.py`

- [ ] **Step 1: Write the failing mpv-widget tests**

```python
def test_mpv_widget_uses_configured_base_playback_settings(qtbot, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMPV:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    widget = MpvWidget(
        parent=None,
        config=AppConfig(
            youtube_cookie_browser="edge",
            mpv_cache_size_mb=768,
            mpv_hwdec_mode="no",
            mpv_network_timeout_seconds=22,
            mpv_default_readahead_secs=45,
        ),
    )
    qtbot.addWidget(widget)
    monkeypatch.setitem(sys.modules, "mpv", types.SimpleNamespace(MPV=FakeMPV))

    widget._create_player()

    assert captured["hwdec"] == "no"
    assert captured["demuxer_max_bytes"] == "768M"
    assert captured["network_timeout"] == 22
    assert captured["ytdl_raw_options"] == "cookies-from-browser=edge,remote-components=ejs:github"


def test_mpv_widget_keeps_special_readahead_profiles_for_ytdlp_sources(qtbot) -> None:
    widget = MpvWidget(config=AppConfig(mpv_default_readahead_secs=33))
    qtbot.addWidget(widget)
    player = FakeAlivePlayer()
    widget._player = player

    profile_name = widget._apply_stream_profile(
        player,
        "https://www.youtube.com/watch?v=test123",
        ytdl_format="bestvideo+bestaudio/best",
    )

    assert profile_name == "hybrid-ytdl"
    assert player.options["demuxer-readahead-secs"] == 120


def test_mpv_widget_extra_options_override_profile_values(qtbot) -> None:
    widget = MpvWidget(config=AppConfig(mpv_extra_options="demuxer-readahead-secs=9\ncache-pause-wait=1"))
    qtbot.addWidget(widget)
    player = FakeAlivePlayer()
    widget._player = player

    widget._apply_stream_profile(player, "https://www.youtube.com/watch?v=test123", ytdl_format="best")
    widget._apply_extra_mpv_options(player)

    assert player.options["demuxer-readahead-secs"] == "9"
    assert player.options["cache-pause-wait"] == "1"
```

- [ ] **Step 2: Run the mpv-widget tests to verify they fail**

Run: `uv run pytest tests/test_mpv_widget.py -k "base_playback_settings or special_readahead_profiles or extra_options_override" -q`

Expected: `FAIL` because `MpvWidget` does not yet accept config or apply any saved playback settings.

- [ ] **Step 3: Inject config into `MpvWidget` and apply the precedence rules**

```python
# src/atv_player/player/mpv_widget.py
class MpvWidget(QWidget):
    def __init__(self, parent=None, config: AppConfig | None = None) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        ...

    def _base_player_options(self) -> dict[str, object]:
        return {
            "wid": str(int(self.winId())),
            "hwdec": str(getattr(self._config, "mpv_hwdec_mode", "auto-safe") or "auto-safe"),
            "force_window": "yes",
            "audio_spdif": "no",
            "ad": "ffmpeg",
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "cache": True,
            "cache_pause_initial": True,
            "cache_pause_wait": 3,
            "demuxer_max_bytes": f"{int(getattr(self._config, 'mpv_cache_size_mb', 512) or 512)}M",
            "demuxer_max_back_bytes": "128M",
            "demuxer_readahead_secs": int(getattr(self._config, "mpv_default_readahead_secs", 20) or 20),
            "stream_buffer_size": "4M",
            "network_timeout": int(getattr(self._config, "mpv_network_timeout_seconds", 15) or 15),
        }
```

```python
# src/atv_player/player/mpv_widget.py
def _apply_extra_mpv_options(self, player: Any) -> None:
    raw = str(getattr(self._config, "mpv_extra_options", "") or "").strip()
    if not raw:
        return
    for line in raw.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        key, value = normalized.split("=", 1)
        self._set_player_property(key.strip(), value.strip())
```

```python
# src/atv_player/player/mpv_widget.py
def _create_player(self):
    import mpv

    common = self._base_player_options()
    ytdlp_path = resolve_mpv_ytdlp_path()
    if ytdlp_path:
        common["script_opts"] = f"ytdl_hook-ytdl_path={ytdlp_path}"
    ytdl_raw_options = resolve_mpv_ytdl_raw_options(
        cookie_browser=str(getattr(self._config, "youtube_cookie_browser", "") or "")
    )
    if ytdl_raw_options:
        common["ytdl_raw_options"] = ytdl_raw_options
```

```python
# src/atv_player/player/mpv_widget.py inside load()
profile_name = self._apply_stream_profile(...)
self._apply_extra_mpv_options(player)
```

```python
# src/atv_player/ui/player_window.py
self.video_widget = MpvWidget(self, config=self.config)
```

- [ ] **Step 4: Run the mpv-widget tests to verify they pass**

Run: `uv run pytest tests/test_mpv_widget.py -k "base_playback_settings or special_readahead_profiles or extra_options_override" -q`

Expected: `PASS`, proving the saved base values apply, the existing ISO / `yt-dlp` readahead profiles still win by default, and `更多 MPV 配置` can override them last.

- [ ] **Step 5: Run the nearby regression coverage**

Run: `uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog" -q`

Expected: `PASS`, confirming the dialog and widget wiring still coexist with the current advanced-settings flow.

- [ ] **Step 6: Commit the mpv slice**

```bash
git add src/atv_player/player/mpv_widget.py src/atv_player/ui/player_window.py tests/test_mpv_widget.py tests/test_main_window_ui.py
git commit -m "feat: add configurable playback settings"
```

## Self-Review

- Spec coverage:
  - `播放设置` tab and six fields: Task 2
  - Persistence and migration: Task 1
  - `YouTube Cookie` runtime wiring: Task 3
  - mpv base values, source-profile precedence, and final extra-option override: Task 4
- Placeholder scan:
  - No `TODO` / `TBD` / “similar to Task N” references remain.
- Type consistency:
  - `youtube_cookie_browser`, `mpv_cache_size_mb`, `mpv_hwdec_mode`, `mpv_network_timeout_seconds`, `mpv_default_readahead_secs`, and `mpv_extra_options` are used consistently across persistence, UI, and runtime tasks.
