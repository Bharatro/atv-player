# Danmaku Cleaning and Episode Offset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace danmaku environment-variable settings with persisted global cleaning controls and add per-series, per-episode, per-provider fixed-second offsets that can be adjusted from the player without re-downloading danmaku.

**Architecture:** Persist only bounded global cleaning settings in `AppConfig`/SQLite. Keep growing episode/provider offsets in the existing series preference JSON, shared by all controller types. Cache cleaned, unshifted XML and apply the selected offset only while rendering ASS so reloads cannot compound the shift.

**Tech Stack:** Python 3.12, dataclasses, SQLite, PySide6, pytest, pytest-qt

---

## File Map

- `src/atv_player/models.py`: add global cleaning fields, runtime item offset, and persisted series offset mapping.
- `src/atv_player/storage.py`: normalize and persist the three global cleaning fields.
- `src/atv_player/danmaku/processing.py`: implement plain-text cleaning policy and retain fixed-second offset only.
- `src/atv_player/danmaku/service.py`: load persisted cleaning settings; remove all danmaku environment-variable behavior.
- `src/atv_player/danmaku/direct_parse.py`: apply the shared cleaning policy to direct-parse records.
- `src/atv_player/danmaku/preferences.py`: derive stable episode keys and atomically persist episode/provider offsets.
- `src/atv_player/danmaku/generic.py`: expose offset load/save through the generic controller.
- `src/atv_player/plugins/controller.py`: expose offset load/save through plugin controllers and remove download-time offsets.
- `src/atv_player/plugins/__init__.py`: accept the coordinator-owned shared preference store.
- `src/atv_player/app.py`: create and inject shared config/preference dependencies.
- `src/atv_player/ui/main_window.py`: inject cleaning and preference dependencies into direct-parse controllers.
- `src/atv_player/danmaku/subtitle.py`: apply fixed-second offset to parsed records during ASS rendering.
- `src/atv_player/danmaku/cache.py`: version XML cache and include offset in ASS cache identity.
- `src/atv_player/ui/advanced_settings_dialog.py`: expose and save global cleaning controls.
- `src/atv_player/ui/player_window.py`: add the episode offset row, debounce saving, and reload the active ASS.
- `tests/test_storage.py`: config migration and round-trip coverage.
- `tests/test_danmaku_processing.py`: cleaning semantics and removal of rule/percent behavior.
- `tests/test_danmaku_service.py`: persisted settings and environment-variable removal.
- `tests/test_direct_parse_danmaku.py`: direct-parse cleaning coverage.
- `tests/test_danmaku_preferences.py`: backward compatibility, keying, atomic offset persistence.
- `tests/test_generic_danmaku_controller.py`: generic controller offset delegation.
- `tests/test_spider_plugin_controller.py`: plugin controller offset delegation and unshifted XML.
- `tests/test_danmaku_subtitle.py`: render-time fixed offsets and no compounding.
- `tests/test_danmaku_cache.py`: cache version and offset identity.
- `tests/test_main_window_ui.py`: advanced-settings controls and dependency injection.
- `tests/test_player_window_ui.py`: offset row state, debounce, source/episode switching, and rerendering.

### Task 1: Persist Global Cleaning Configuration

**Files:**
- Modify: `src/atv_player/models.py:24`
- Modify: `src/atv_player/storage.py:45-1485`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing model and repository tests**

Add tests that exercise defaults, round-trip persistence, and malformed database values:

```python
def test_app_config_defaults_disable_danmaku_cleaning() -> None:
    config = AppConfig()
    assert config.danmaku_blocked_words == []
    assert config.danmaku_duplicate_window_minutes == 0
    assert config.danmaku_convert_top_bottom_to_scroll is False


def test_settings_repository_round_trips_danmaku_cleaning(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.danmaku_blocked_words = [" 广告 ", "剧透", "广告", ""]
    config.danmaku_duplicate_window_minutes = 7
    config.danmaku_convert_top_bottom_to_scroll = True
    repo.save_config(config)

    loaded = repo.load_config()
    assert loaded.danmaku_blocked_words == ["广告", "剧透"]
    assert loaded.danmaku_duplicate_window_minutes == 7
    assert loaded.danmaku_convert_top_bottom_to_scroll is True


def test_settings_repository_normalizes_invalid_danmaku_cleaning(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    with sqlite3.connect(tmp_path / "app.db") as conn:
        conn.execute(
            "UPDATE app_config SET danmaku_blocked_words = ?, "
            "danmaku_duplicate_window_minutes = ? WHERE id = 1",
            ('["  spam  ", 3, "spam", ""]', 999),
        )
    loaded = repo.load_config()
    assert loaded.danmaku_blocked_words == ["spam"]
    assert loaded.danmaku_duplicate_window_minutes == 60
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_storage.py -k "danmaku_cleaning" -q
```

Expected: FAIL because `AppConfig` and `app_config` do not contain the new fields.

- [ ] **Step 3: Add model fields and storage normalization**

Add the fields to `AppConfig` beside `disabled_danmaku_provider_ids`. Add focused helpers in `storage.py`:

```python
def _normalize_danmaku_blocked_words(value: object) -> list[str]:
    values = value if isinstance(value, list) else []
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        word = raw.strip()
        if not word or word in seen:
            continue
        seen.add(word)
        output.append(word)
    return output


def _normalize_danmaku_duplicate_window_minutes(value: object) -> int:
    try:
        return max(0, min(int(value), 60))
    except (TypeError, ValueError):
        return 0
```

Add the three columns to initial schema, guarded `ALTER TABLE` migrations, the initial insert, `SELECT` unpacking, `AppConfig(...)`, and `UPDATE` binding. Serialize blocked words with `json.dumps(..., ensure_ascii=False)` and decode malformed JSON as an empty list.

- [ ] **Step 4: Run storage tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_storage.py -k "danmaku_cleaning or preferred_danmaku" -q
```

Expected: PASS.

- [ ] **Step 5: Re-read changed files and commit**

Run:

```bash
rg -n "danmaku_blocked_words|danmaku_duplicate_window_minutes|danmaku_convert_top_bottom_to_scroll" src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git diff --check
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat(danmaku): persist cleaning preferences"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the new commit is HEAD and lists exactly the three files above.

### Task 2: Replace Environment Variables With the Persisted Cleaning Pipeline

**Files:**
- Modify: `src/atv_player/danmaku/processing.py`
- Modify: `src/atv_player/danmaku/service.py`
- Modify: `src/atv_player/danmaku/direct_parse.py`
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_danmaku_processing.py`
- Test: `tests/test_danmaku_service.py`
- Test: `tests/test_direct_parse_danmaku.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing pure-processing and service tests**

Replace regex/rule-parser tests with persisted-policy behavior:

```python
def test_clean_records_uses_casefolded_plain_substrings() -> None:
    records = [_r(1, "SPAM link"), _r(2, "正常"), _r(3, "spam again")]
    cleaned = clean_records(
        records,
        blocked_words=["spam"],
        duplicate_window_minutes=0,
        convert_top_bottom=False,
    )
    assert [record.content for record in cleaned] == ["正常"]


def test_service_ignores_removed_danmaku_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("ATV_DANMU_BLOCKED_WORDS", "/normal/")
    monkeypatch.setenv("ATV_DANMU_GROUP_MINUTE", "5")
    monkeypatch.setenv("ATV_DANMU_CONVERT_TOP_BOTTOM", "1")
    monkeypatch.setenv("ATV_DANMU_OFFSET", "demo:99")
    service = DanmakuService(
        {"fake": FakeProvider()},
        provider_order=["fake"],
        config_loader=lambda: AppConfig(),
    )
    xml = service.resolve_danmu("https://example.test/video")
    assert "normal" in xml
    assert 'p="1' in xml
```

Add a service test with `AppConfig(danmaku_blocked_words=[...], danmaku_duplicate_window_minutes=1, danmaku_convert_top_bottom_to_scroll=True)` and assert the configured order is applied.

- [ ] **Step 2: Write a failing direct-parse cleaning test**

```python
def test_direct_parse_controller_applies_persisted_cleaning_before_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path)
    controller = DirectParseDanmakuController(
        load=lambda _url: {
            "danmuku": [[1, "top", "#ffffff", "", "广告"], [2, "bottom", "#ffffff", "", "正常"]]
        },
        config_loader=lambda: AppConfig(
            danmaku_blocked_words=["广告"],
            danmaku_convert_top_bottom_to_scroll=True,
        ),
    )
    item = PlayItem(title="第1集", url="", original_url="https://example.test/1")
    xml = controller.switch_danmaku_source(item, item.original_url)
    assert "广告" not in xml
    assert 'p="2,1,' in xml
```

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_processing.py tests/test_danmaku_service.py tests/test_direct_parse_danmaku.py -k "clean or environment or persisted" -q
```

Expected: FAIL because `clean_records` and `config_loader` do not exist and environment variables still control the service.

- [ ] **Step 4: Implement the shared cleaning policy**

In `processing.py`, replace regex matching and remove `OffsetRule`, `parse_offset_rules`, `resolve_offset_seconds`, and percent handling. Keep fixed-second `apply_time_offset` and add:

```python
def clean_records(
    records: Sequence[DanmakuRecord],
    *,
    blocked_words: Sequence[str],
    duplicate_window_minutes: int,
    convert_top_bottom: bool,
) -> list[DanmakuRecord]:
    blocked = tuple(word.strip().casefold() for word in blocked_words if word.strip())
    output = [
        record
        for record in records
        if not any(word in record.content.casefold() for word in blocked)
    ]
    output = group_by_time_window(output, duplicate_window_minutes)
    return convert_top_bottom_to_scroll(output) if convert_top_bottom else output
```

In `DanmakuService`, add `config_loader: Callable[[], AppConfig] | None`, load it inside `_process_records`, log failures, and remove `_apply_time_offset`, the `offset_context` argument, plus every `os.environ` access. Remove plugin-controller construction and forwarding of `offset_context`. Pass `config_loader=self.repo.load_config` from `AppCoordinator`.

In `DirectParseDanmakuController`, add optional `config_loader`, build `DanmakuRecord` values from payload, call `clean_records`, then call `build_xml`. In `MainWindow._build_direct_parse_danmaku_controller`, pass `config_loader=lambda: self.config`.

- [ ] **Step 5: Run cleaning and controller tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_processing.py tests/test_danmaku_service.py tests/test_direct_parse_danmaku.py tests/test_main_window_ui.py -k "danmaku and (clean or environment or direct_parse)" -q
```

Expected: PASS, with no test restoring or deleting danmaku environment variables manually.

- [ ] **Step 6: Confirm environment code is gone and commit**

Run:

```bash
rg -n "ATV_DANMU|parse_offset_rules|resolve_offset_seconds|use_percent|offset_context" src
rg -n "ATV_DANMU" tests/test_danmaku_service.py
git diff --check
git add src/atv_player/danmaku/processing.py src/atv_player/danmaku/service.py src/atv_player/danmaku/direct_parse.py src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_danmaku_processing.py tests/test_danmaku_service.py tests/test_direct_parse_danmaku.py tests/test_main_window_ui.py
git commit -m "feat(danmaku): use persisted cleaning settings"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the production search returns no matches; the test search returns only the intentional environment-variables-have-no-effect regression test; the commit is verified at HEAD.

### Task 3: Persist Episode and Provider Offsets in the Shared Series Store

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/danmaku/preferences.py`
- Modify: `src/atv_player/danmaku/generic.py`
- Modify: `src/atv_player/danmaku/direct_parse.py`
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `src/atv_player/plugins/__init__.py`
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_danmaku_preferences.py`
- Test: `tests/test_generic_danmaku_controller.py`
- Test: `tests/test_direct_parse_danmaku.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write failing preference-store tests**

```python
def test_preference_store_isolates_episode_provider_offsets(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")
    store.save_offset("jianlai", "episode:12", "tencent", -3.0)
    store.save_offset("jianlai", "episode:12", "bilibili", 1.5)
    store.save_offset("jianlai", "episode:13", "tencent", 2.0)
    assert store.load_offset("jianlai", "episode:12", "tencent") == -3.0
    assert store.load_offset("jianlai", "episode:12", "bilibili") == 1.5
    assert store.load_offset("jianlai", "episode:13", "tencent") == 2.0


def test_preference_store_zero_removes_offset_and_reads_old_json(tmp_path: Path) -> None:
    path = tmp_path / "danmaku-series.json"
    path.write_text('{"jianlai":{"provider":"tencent","page_url":"u","title":"t","updated_at":1}}', encoding="utf-8")
    store = DanmakuSeriesPreferenceStore(path)
    assert store.load_offset("jianlai", "episode:12", "tencent") == 0.0
    store.save_offset("jianlai", "episode:12", "tencent", 4.0)
    store.save_offset("jianlai", "episode:12", "tencent", 0.0)
    assert store.load_offset("jianlai", "episode:12", "tencent") == 0.0
```

Add parameterized key tests for inferred playlist episode, normalized label, stable item digest, and `single` fallback. Add a concurrent save test with two threads and assert both provider keys survive valid JSON.

- [ ] **Step 2: Write failing controller delegation tests**

For each controller type, create a store and item with `danmaku_series_key`, selected provider, and playlist context. Assert:

```python
controller.save_danmaku_offset(item, -2.5, playlist=[item])
assert controller.load_danmaku_offset(item, playlist=[item]) == -2.5
assert item.danmaku_offset_seconds == -2.5
```

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_preferences.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py -k "offset" -q
```

Expected: FAIL because the model, store APIs, episode key helper, and controller methods are absent.

- [ ] **Step 4: Implement model, keying, and atomic persistence**

Add `PlayItem.danmaku_offset_seconds` and `DanmakuSeriesPreference.episode_source_offsets`. In `preferences.py`, add:

```python
def build_danmaku_episode_key(item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
    number = infer_playlist_episode_number(item, playlist)
    if number is not None and number > 0:
        return f"episode:{number}"
    label = re.sub(r"\s+", "", item.danmaku_search_episode).casefold()
    if label:
        return f"label:{label}"
    identity = str(item.vod_id or item.original_url or item.url or "").strip()
    if identity:
        return f"item:{sha256(identity.encode('utf-8')).hexdigest()[:16]}"
    return "single"
```

Use an `RLock` around read-modify-write. Write JSON to a `NamedTemporaryFile` in `self._path.parent`, flush it, then `Path(temp_name).replace(self._path)` in `finally` cleanup. Normalize finite offsets to `-600.0..600.0`; `0.0` removes entries.

- [ ] **Step 5: Inject one shared store and expose controller methods**

Create `self._danmaku_preference_store = DanmakuSeriesPreferenceStore()` in `AppCoordinator`. Add optional `danmaku_preference_store` constructor arguments to `SpiderPluginManager`, `GenericDanmakuController`, `DirectParseDanmakuController`, and `MainWindow`; defaults preserve existing tests. Pass the coordinator instance to plugin manager, generic factory, and main window/direct controller.

Each controller implements:

```python
def load_danmaku_offset(self, item: PlayItem, playlist: list[PlayItem] | None = None) -> float:
    value = load_item_danmaku_offset(self._danmaku_preference_store, item, playlist)
    item.danmaku_offset_seconds = value
    return value

def save_danmaku_offset(self, item: PlayItem, value: float, playlist: list[PlayItem] | None = None) -> None:
    save_item_danmaku_offset(self._danmaku_preference_store, item, value, playlist)
    item.danmaku_offset_seconds = value
```

The shared helper derives/sets `item.danmaku_series_key`, episode key, and selected provider. Preserve `episode_source_offsets` whenever existing source/search preferences are rewritten.

- [ ] **Step 6: Run preference and controller tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_preferences.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py -k "preference or offset" -q
```

Expected: PASS.

- [ ] **Step 7: Re-read the JSON write path and commit**

Run:

```bash
sed -n '1,280p' src/atv_player/danmaku/preferences.py
git diff --check
git add src/atv_player/models.py src/atv_player/danmaku/preferences.py src/atv_player/danmaku/generic.py src/atv_player/danmaku/direct_parse.py src/atv_player/plugins/controller.py src/atv_player/plugins/__init__.py src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_danmaku_preferences.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py
git commit -m "feat(danmaku): persist episode source offsets"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the preference-store commit is HEAD and the disk read shows lock plus atomic replacement.

### Task 4: Apply Offsets Only During ASS Rendering and Version Caches

**Files:**
- Modify: `src/atv_player/danmaku/subtitle.py`
- Modify: `src/atv_player/danmaku/cache.py`
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_danmaku_subtitle.py`
- Test: `tests/test_danmaku_cache.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing render and cache tests**

```python
def test_render_danmaku_ass_applies_fixed_offset_without_mutating_xml() -> None:
    xml = '<i><d p="5,1,25,16777215">晚三秒</d></i>'
    shifted = render_danmaku_ass(xml, time_offset_seconds=-3.0)
    repeated = render_danmaku_ass(xml, time_offset_seconds=-3.0)
    assert "Dialogue: 0,0:00:02.00" in shifted
    assert repeated == shifted
    assert 'p="5' in xml


def test_danmaku_ass_cache_path_includes_offset(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path)
    xml = '<i><d p="5,1,25,16777215">x</d></i>'
    zero = danmaku_cache_module.danmaku_ass_cache_path(xml, 1, time_offset_seconds=0.0)
    shifted = danmaku_cache_module.danmaku_ass_cache_path(xml, 1, time_offset_seconds=-3.0)
    assert zero != shifted
```

Add a cache-version test that reconstructs the old `v1` XML digest and asserts `danmaku_xml_cache_path` uses a different path.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py -k "offset or cache_path_includes" -q
```

Expected: FAIL because render/cache APIs reject `time_offset_seconds`.

- [ ] **Step 3: Thread offset through render and cache APIs**

Import `DanmakuRecord` into `subtitle.py` and make `_parse_danmaku_xml_records` return `list[DanmakuRecord]` instead of its duplicate private record dataclass. Add `time_offset_seconds: float = 0.0` to `render_danmaku_ass`, `danmaku_ass_cache_path`, and `load_or_create_danmaku_ass_cache`. After XML parsing:

```python
records = apply_time_offset(records, time_offset_seconds)
```

Include `f"{float(time_offset_seconds):.3f}"` in the ASS digest and bump `_DANMAKU_ASS_CACHE_VERSION` from `v6` to `v7`. Bump `_DANMAKU_XML_CACHE_VERSION` from `v1` to `v2`.

In `PlayerWindow._build_danmaku_subtitle_file`, pass `current_item.danmaku_offset_seconds if current_item else 0.0` into `load_or_create_danmaku_ass_cache` for both synchronous and asynchronous render paths.

- [ ] **Step 4: Run render/cache/player tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py -k "danmaku and (offset or cache or subtitle_file)" -q
```

Expected: PASS.

- [ ] **Step 5: Commit and verify**

Run:

```bash
rg -n "time_offset_seconds|_DANMAKU_ASS_CACHE_VERSION|_DANMAKU_XML_CACHE_VERSION" src/atv_player/danmaku src/atv_player/ui/player_window.py tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py
git diff --check
git add src/atv_player/danmaku/subtitle.py src/atv_player/danmaku/cache.py src/atv_player/ui/player_window.py tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py
git commit -m "feat(danmaku): apply offsets during rendering"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the rendering commit is HEAD and both cache versions are visible in the disk read.

### Task 5: Add Global Cleaning Controls to Advanced Settings

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing UI tests**

```python
def test_advanced_settings_dialog_populates_danmaku_cleaning(qtbot) -> None:
    config = AppConfig(
        danmaku_blocked_words=["广告", "剧透"],
        danmaku_duplicate_window_minutes=5,
        danmaku_convert_top_bottom_to_scroll=True,
    )
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)
    assert dialog.danmaku_blocked_words_edit.toPlainText() == "广告\n剧透"
    assert dialog.danmaku_duplicate_window_spinbox.value() == 5
    assert dialog.danmaku_convert_top_bottom_checkbox.isChecked() is True


def test_advanced_settings_dialog_saves_normalized_danmaku_cleaning(qtbot) -> None:
    saved: list[AppConfig] = []
    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)
    dialog.danmaku_blocked_words_edit.setPlainText(" 广告 \n剧透\n广告\n")
    dialog.danmaku_duplicate_window_spinbox.setValue(3)
    dialog.danmaku_convert_top_bottom_checkbox.setChecked(True)
    dialog._save()
    assert config.danmaku_blocked_words == ["广告", "剧透"]
    assert config.danmaku_duplicate_window_minutes == 3
    assert config.danmaku_convert_top_bottom_to_scroll is True
    assert saved == [config]
```

- [ ] **Step 2: Run UI tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog and danmaku_cleaning" -q
```

Expected: FAIL because the widgets do not exist.

- [ ] **Step 3: Build and save the cleaning group**

Create `danmaku_cleaning_group`, `QPlainTextEdit`, `QSpinBox`, and `QCheckBox` in `AdvancedSettingsDialog.__init__`. Set the spin range to `0..60` and suffix to ` 分钟`. Add the group after `danmaku_source_group` in the metadata tab. Populate from config and normalize lines during `_save`:

```python
words = [line.strip() for line in self.danmaku_blocked_words_edit.toPlainText().splitlines()]
self._config.danmaku_blocked_words = list(dict.fromkeys(word for word in words if word))
self._config.danmaku_duplicate_window_minutes = self.danmaku_duplicate_window_spinbox.value()
self._config.danmaku_convert_top_bottom_to_scroll = self.danmaku_convert_top_bottom_checkbox.isChecked()
```

- [ ] **Step 4: Run advanced-settings tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k "advanced_settings_dialog" -q
```

Expected: PASS.

- [ ] **Step 5: Commit and verify**

Run:

```bash
sed -n '320,480p' src/atv_player/ui/advanced_settings_dialog.py
git diff --check
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_main_window_ui.py
git commit -m "feat(ui): add danmaku cleaning settings"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the UI commit is HEAD and contains only dialog plus UI tests.

### Task 6: Add the Episode Offset Calibration Row

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing layout and state tests**

Add focused tests using a fake controller with `load_danmaku_offset` and `save_danmaku_offset`:

```python
def test_danmaku_source_dialog_shows_saved_episode_offset(qtbot) -> None:
    controller = FakeOffsetDanmakuController(offset=-3.0)
    window, item = build_window_with_loaded_danmaku(qtbot, controller)
    window._open_danmaku_source_dialog()
    assert window._danmaku_source_offset_spin is not None
    assert window._danmaku_source_offset_spin.minimum() == -600.0
    assert window._danmaku_source_offset_spin.maximum() == 600.0
    assert window._danmaku_source_offset_spin.singleStep() == 0.5
    assert window._danmaku_source_offset_spin.value() == -3.0
    assert window._danmaku_source_offset_spin.isEnabled() is True


def test_danmaku_offset_change_debounces_save_and_rerender(qtbot, monkeypatch) -> None:
    controller = FakeOffsetDanmakuController(offset=0.0)
    window, item = build_window_with_loaded_danmaku(qtbot, controller)
    renders: list[float] = []
    monkeypatch.setattr(window, "_configure_danmaku_for_current_item", lambda: renders.append(item.danmaku_offset_seconds))
    window._open_danmaku_source_dialog()
    window._danmaku_source_offset_spin.setValue(-2.0)
    window._danmaku_source_offset_spin.setValue(-3.0)
    qtbot.waitUntil(lambda: controller.saved == [-3.0], timeout=1000)
    assert renders == [-3.0]
```

Add tests for disabled state without XML/provider, reset to zero, source switch loading its own value before rerender, episode change restoring its value, and missing controller APIs falling back to zero.

- [ ] **Step 2: Run focused player tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "danmaku_source and offset" -q
```

Expected: FAIL because the offset widgets and timer do not exist.

- [ ] **Step 3: Add widgets, timer, synchronization, and save path**

In `PlayerWindow.__init__`, add nullable widget fields and a single-shot timer:

```python
self._danmaku_source_offset_spin: QDoubleSpinBox | None = None
self._danmaku_source_offset_reset_button: QPushButton | None = None
self._danmaku_offset_save_timer = QTimer(self)
self._danmaku_offset_save_timer.setSingleShot(True)
self._danmaku_offset_save_timer.setInterval(250)
self._danmaku_offset_save_timer.timeout.connect(self._apply_pending_danmaku_offset)
```

In `_ensure_danmaku_source_dialog`, insert an unframed horizontal row after the two source lists and before status/actions. Configure range, decimals, step, and suffix; connect `valueChanged` to restart the timer and reset button to `setValue(0.0)`.

Implement `_load_current_danmaku_offset`, `_sync_danmaku_offset_controls`, and `_apply_pending_danmaku_offset`. Call synchronization when opening/refreshing the dialog, changing the current episode, and after source tasks finish. Disable the row when XML/provider is absent or a source task is active. Block spin signals while loading a stored value.

On timer fire, set the item field, invoke optional controller `save_danmaku_offset(item, value, playlist=...)`, log persistence failures, and call `_configure_danmaku_for_current_item()` without downloading XML.

- [ ] **Step 4: Run all focused danmaku player tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "danmaku_source or danmaku_subtitle_file or cached_danmaku" -q
```

Expected: PASS.

- [ ] **Step 5: Run the complete feature test set**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_storage.py tests/test_danmaku_processing.py tests/test_danmaku_service.py tests/test_direct_parse_danmaku.py tests/test_danmaku_preferences.py tests/test_generic_danmaku_controller.py tests/test_spider_plugin_controller.py tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_main_window_ui.py tests/test_player_window_ui.py -q
```

Expected: all selected tests PASS with zero failures.

- [ ] **Step 6: Commit and verify**

Run:

```bash
rg -n "danmaku_source_offset|danmaku_offset_save_timer|save_danmaku_offset" src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git diff --check
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat(ui): add episode danmaku offset control"
git log -1 --oneline
git show --stat --oneline HEAD
```

Expected: the final feature commit is HEAD and contains the player window plus its tests.

### Task 7: Full Verification and Requirement Audit

**Files:**
- Verify only; modify a file only if a failing check identifies a feature-related defect, then repeat that task's RED/GREEN cycle and commit separately.

- [ ] **Step 1: Confirm all environment-variable code is removed**

Run:

```bash
rg -n "ATV_DANMU|parse_offset_rules|resolve_offset_seconds|use_percent|offset_context" src
rg -n "ATV_DANMU" tests/test_danmaku_service.py
```

Expected: the production search has no matches; the test search contains only the intentional environment-variables-have-no-effect regression test.

- [ ] **Step 2: Run lint and type checks on changed production modules**

Run:

```bash
uv run ruff check src/atv_player/models.py src/atv_player/storage.py src/atv_player/danmaku src/atv_player/plugins/controller.py src/atv_player/plugins/__init__.py src/atv_player/app.py src/atv_player/ui/main_window.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py
npx --yes pyright src/atv_player/models.py src/atv_player/storage.py src/atv_player/danmaku src/atv_player/plugins/controller.py src/atv_player/app.py src/atv_player/ui/main_window.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/player_window.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest -q
```

Expected: the full repository suite exits 0 with no failures.

- [ ] **Step 4: Audit requirements and repository state**

Run:

```bash
git status --short --branch
git log -8 --oneline
git show --stat --oneline HEAD
```

Confirm against the design document:

- global cleaning survives a repository round trip;
- old environment variables have no effect;
- direct parse and provider records share cleaning semantics;
- XML cache stores unshifted records under version `v2`;
- offsets are isolated by series, episode, and provider;
- player adjustment rerenders cached XML without downloading;
- reset, source switch, episode switch, and legacy-controller fallback are tested;
- every feature commit is present in `git log` and its files appear in `git show --stat`.

Expected: clean worktree except for explicitly identified pre-existing user changes, and every checklist item has direct test or source evidence.
