# Danmaku Readability Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add danmaku opacity and outline-strength settings so users can make danmaku less intrusive while keeping it readable, without adding random colors or font-family customization.

**Architecture:** Extend the existing ASS danmaku renderer with two new render parameters, thread those parameters through the danmaku cache and player-window plumbing, and persist them in `AppConfig`/SQLite alongside the current render settings. Keep the behavior inside the existing danmaku ASS pipeline so XML parsing, provider behavior, and subtitle-track ownership remain unchanged.

**Tech Stack:** Python 3.12+, PySide6, SQLite, ASS subtitles, `pytest`

---

## File Structure

**Modify:**

- `src/atv_player/danmaku/subtitle.py`
  Add normalization and ASS-format helpers for opacity and outline-strength, then apply them in the ASS style header and source-color inline overrides.
- `src/atv_player/danmaku/cache.py`
  Include the new render-affecting settings in the ASS cache version and key, and pass them through to `render_danmaku_ass(...)`.
- `src/atv_player/models.py`
  Add `AppConfig` fields for danmaku opacity and outline strength.
- `src/atv_player/storage.py`
  Add normalization helpers, schema defaults, migration columns, load/save wiring, and invalid-value fallback coverage for the new config fields.
- `src/atv_player/ui/player_window.py`
  Add settings helpers, dialog controls, config writes, reload triggers, default reset behavior, and cache-builder parameter plumbing.
- `tests/test_danmaku_subtitle.py`
  Add focused renderer coverage for opacity alpha and outline presets.
- `tests/test_danmaku_cache.py`
  Add cache-key regression coverage for opacity and outline strength.
- `tests/test_storage.py`
  Add config round-trip and migration/default normalization coverage for the new settings.
- `tests/test_player_window_ui.py`
  Add UI coverage for new controls, parameter forwarding, and restore-defaults behavior.
- `docs/help.md`
  Document the two new danmaku settings.
- `docs/TODO.md`
  Mark `弹幕透明度` complete and split `弹幕字体 / 描边` so only `描边` is marked complete.

**Do Not Modify In This Plan:**

- `src/atv_player/danmaku/providers/*`
- `src/atv_player/danmaku/direct_parse.py`
- `src/atv_player/player/mpv_widget.py`

This plan is intentionally limited to rendering, persistence, cache partitioning, and the player settings UI.

### Task 1: Extend the ASS renderer for opacity and outline strength

**Files:**
- Modify: `src/atv_player/danmaku/subtitle.py`
- Modify: `tests/test_danmaku_subtitle.py`

- [ ] **Step 1: Write the failing renderer tests**

Add these tests to `tests/test_danmaku_subtitle.py` near the existing ASS renderer coverage:

```python
def test_render_danmaku_ass_applies_text_alpha_to_uniform_and_source_color_paths() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16711680">红色</d>'
        "</i>"
    )

    uniform = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        opacity=85,
    )
    source = render_danmaku_ass(
        xml_text,
        line_count=1,
        render_mode="scroll_only",
        color_mode="source",
        uniform_color="#FFFFFF",
        opacity=85,
    )

    assert "&H26FFFFFF&" in uniform
    assert r"\1a&H26&" in source


def test_render_danmaku_ass_uses_soft_and_strong_outline_presets() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?><i>'
        '<d p="0.0,1,25,16777215">第一条</d>'
        "</i>"
    )

    soft = render_danmaku_ass(xml_text, outline_strength="soft")
    strong = render_danmaku_ass(xml_text, outline_strength="strong")

    assert "Style: Danmaku,sans-serif,32,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H64000000&,0,0,0,0,100,100,0,0,1,1,0,8,24,24,4,1" in soft
    assert "Style: Danmaku,sans-serif,32,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H64000000&,0,0,0,0,100,100,0,0,1,2,1,8,24,24,4,1" in strong
```

- [ ] **Step 2: Run the renderer tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py -k "opacity or outline_presets" -v
```

Expected:

```text
FAILED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_applies_text_alpha_to_uniform_and_source_color_paths
FAILED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_uses_soft_and_strong_outline_presets
```

The failure should be because `render_danmaku_ass(...)` does not yet accept `opacity` or `outline_strength`.

- [ ] **Step 3: Implement the renderer changes**

Update `src/atv_player/danmaku/subtitle.py` with these concrete pieces:

```python
_VALID_OUTLINE_STRENGTHS = {"soft", "strong"}
_DEFAULT_OPACITY = 85
_DEFAULT_OUTLINE_STRENGTH = "strong"


def _normalize_opacity(value: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_OPACITY
    return max(30, min(normalized, 100))


def _normalize_outline_strength(value: str) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_OUTLINE_STRENGTHS else _DEFAULT_OUTLINE_STRENGTH


def _opacity_to_ass_alpha(opacity: int) -> str:
    alpha = round((100 - _normalize_opacity(opacity)) * 255 / 100)
    return f"{alpha:02X}"


def _ass_color_with_alpha(color: str, alpha: str) -> str:
    return color.replace("&H", f"&H{alpha}", 1)


def _outline_style_values(outline_strength: str) -> tuple[int, int]:
    return (1, 0) if outline_strength == "soft" else (2, 1)
```

Then thread the values through the existing rendering path:

```python
def _build_ass_header(
    primary_color: str,
    font_size: int,
    *,
    opacity: int,
    outline_strength: str,
) -> str:
    alpha = _opacity_to_ass_alpha(opacity)
    text_color = _ass_color_with_alpha(primary_color, alpha)
    outline_width, shadow = _outline_style_values(_normalize_outline_strength(outline_strength))
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {_PLAY_RES_X}",
            f"PlayResY: {_PLAY_RES_Y}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Danmaku,sans-serif,{font_size},{text_color},{text_color},&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,{outline_width},{shadow},8,24,24,4,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
```

Update the inline color overrides so source-color lines carry both color and alpha:

```python
def _render_static_text(cue: _SubtitleCue, color_mode: str, uniform_color: str, opacity: int) -> str:
    alpha = _opacity_to_ass_alpha(opacity)
    parts: list[str] = []
    for line in cue.lines:
        text = _escape_ass_text(line.content)
        if color_mode == "source":
            text = rf"{{\1c{line.color}\1a&H{alpha}&}}{text}"
        parts.append(text)
    return r"\N".join(parts)


def _event_override(mode: str, y: int, color: str, opacity: int) -> str:
    alpha = _opacity_to_ass_alpha(opacity)
    if mode == "scroll":
        return rf"{{\an8\move({_PLAY_RES_X + 80},{y},-400,{y})\1c{color}\1a&H{alpha}&}}"
    if mode == "bottom":
        return rf"{{\an2\pos(960,{y})\1c{color}\1a&H{alpha}&}}"
    return rf"{{\an8\pos(960,{y})\1c{color}\1a&H{alpha}&}}"
```

Finally, add the new keyword parameters to `render_danmaku_ass(...)`, normalize them, and pass them into the header, intro-event, static-event, and dynamic-event helpers:

```python
def render_danmaku_ass(
    xml_text: str,
    line_count: int = 1,
    duration_seconds: float = 4.0,
    *,
    intro_episode_label: str = "",
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = _DEFAULT_UNIFORM_COLOR,
    position_preset: str = "top",
    scroll_speed: float = _DEFAULT_SCROLL_SPEED,
    font_size: int = _DEFAULT_FONT_SIZE,
    opacity: int = _DEFAULT_OPACITY,
    outline_strength: str = _DEFAULT_OUTLINE_STRENGTH,
) -> str:
    normalized_opacity = _normalize_opacity(opacity)
    normalized_outline_strength = _normalize_outline_strength(outline_strength)
    header = _build_ass_header(
        _hex_color_to_ass(normalized_uniform_color),
        normalized_font_size,
        opacity=normalized_opacity,
        outline_strength=normalized_outline_strength,
    )
```

- [ ] **Step 4: Run the renderer tests to verify they pass**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py -k "opacity or outline_presets" -v
```

Expected:

```text
PASSED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_applies_text_alpha_to_uniform_and_source_color_paths
PASSED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_uses_soft_and_strong_outline_presets
```

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_danmaku_subtitle.py src/atv_player/danmaku/subtitle.py
git commit -m "feat: add danmaku opacity and outline renderer settings"
```

### Task 2: Persist the new settings and partition the ASS cache correctly

**Files:**
- Modify: `src/atv_player/danmaku/cache.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `tests/test_danmaku_cache.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing cache and storage tests**

Add this cache regression to `tests/test_danmaku_cache.py`:

```python
def test_danmaku_ass_cache_path_changes_when_opacity_or_outline_changes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    xml_text = '<?xml version="1.0" encoding="UTF-8"?><i><d p="0.0,1,25,16777215">一条</d></i>'

    first = danmaku_cache_module.danmaku_ass_cache_path(
        xml_text,
        1,
        render_mode="static",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
        scroll_speed=1.0,
        font_size=32,
        opacity=85,
        outline_strength="strong",
    )
    second = danmaku_cache_module.danmaku_ass_cache_path(
        xml_text,
        1,
        render_mode="static",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
        scroll_speed=1.0,
        font_size=32,
        opacity=60,
        outline_strength="soft",
    )

    assert first != second
```

Add these storage regressions to `tests/test_storage.py`:

```python
def test_settings_repository_round_trip_persists_danmaku_readability_settings(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = AppConfig(
        preferred_danmaku_opacity=60,
        preferred_danmaku_outline_strength="soft",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.preferred_danmaku_opacity == 60
    assert saved.preferred_danmaku_outline_strength == "soft"


def test_settings_repository_normalizes_invalid_danmaku_readability_settings(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    repo.save_config(
        AppConfig(
            preferred_danmaku_opacity=999,
            preferred_danmaku_outline_strength="neon",
        )
    )

    saved = repo.load_config()

    assert saved.preferred_danmaku_opacity == 100
    assert saved.preferred_danmaku_outline_strength == "strong"
```

- [ ] **Step 2: Run the cache and storage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_cache.py tests/test_storage.py -k "opacity or outline_strength or readability_settings" -v
```

Expected:

```text
FAILED tests/test_danmaku_cache.py::test_danmaku_ass_cache_path_changes_when_opacity_or_outline_changes
FAILED tests/test_storage.py::test_settings_repository_round_trip_persists_danmaku_readability_settings
FAILED tests/test_storage.py::test_settings_repository_normalizes_invalid_danmaku_readability_settings
```

The failure should be because the cache helper, `AppConfig`, and `SettingsRepository` do not yet know about the new settings.

- [ ] **Step 3: Implement the cache and persistence changes**

Update `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class AppConfig:
    ...
    preferred_danmaku_scroll_speed: float = 1.0
    preferred_danmaku_font_size: int = 32
    preferred_danmaku_opacity: int = 85
    preferred_danmaku_outline_strength: str = "strong"
    main_window_geometry: bytes | None = None
```

Update `src/atv_player/storage.py` with the new validators:

```python
_VALID_DANMAKU_OUTLINE_STRENGTHS = {"soft", "strong"}


def _normalize_danmaku_opacity(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 85
    return max(30, min(normalized, 100))


def _normalize_danmaku_outline_strength(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_OUTLINE_STRENGTHS else "strong"
```

Add the two columns in all three schema paths:

```python
CREATE TABLE IF NOT EXISTS app_config (
    ...
    preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
    preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
    preferred_danmaku_opacity INTEGER NOT NULL DEFAULT 85,
    preferred_danmaku_outline_strength TEXT NOT NULL DEFAULT 'strong',
    main_window_geometry BLOB,
    ...
)
```

```python
if "preferred_danmaku_opacity" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN preferred_danmaku_opacity INTEGER NOT NULL DEFAULT 85"
    )
if "preferred_danmaku_outline_strength" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN preferred_danmaku_outline_strength TEXT NOT NULL DEFAULT 'strong'"
    )
```

Wire them through `INSERT`, `SELECT`, `load_config()`, and `save_config()`:

```python
preferred_danmaku_font_size=_normalize_danmaku_font_size(preferred_danmaku_font_size),
preferred_danmaku_opacity=_normalize_danmaku_opacity(preferred_danmaku_opacity),
preferred_danmaku_outline_strength=_normalize_danmaku_outline_strength(preferred_danmaku_outline_strength),
```

Update `src/atv_player/danmaku/cache.py` by bumping the cache version and threading the settings through both cache helpers:

```python
_DANMAKU_ASS_CACHE_VERSION = "v5"


def danmaku_ass_cache_path(
    xml_text: str,
    line_count: int,
    *,
    intro_episode_label: str = "",
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = "#FFFFFF",
    position_preset: str = "top",
    scroll_speed: float = 1.0,
    font_size: int = 32,
    opacity: int = 85,
    outline_strength: str = "strong",
) -> Path:
```

Include the new values in the digest tuple and pass them into `render_danmaku_ass(...)` and `danmaku_ass_cache_path(...)`:

```python
str(int(opacity)),
str(outline_strength),
```

- [ ] **Step 4: Run the cache and storage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_danmaku_cache.py tests/test_storage.py -k "opacity or outline_strength or readability_settings" -v
```

Expected:

```text
PASSED tests/test_danmaku_cache.py::test_danmaku_ass_cache_path_changes_when_opacity_or_outline_changes
PASSED tests/test_storage.py::test_settings_repository_round_trip_persists_danmaku_readability_settings
PASSED tests/test_storage.py::test_settings_repository_normalizes_invalid_danmaku_readability_settings
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/danmaku/cache.py src/atv_player/models.py src/atv_player/storage.py tests/test_danmaku_cache.py tests/test_storage.py
git commit -m "feat: persist danmaku readability settings"
```

### Task 3: Add the new controls to the player dialog and pass them into danmaku rendering

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window tests**

Add this parameter-forwarding regression near `test_player_window_build_danmaku_subtitle_file_passes_current_episode_label(...)`:

```python
def test_player_window_build_danmaku_subtitle_file_passes_readability_settings(qtbot, monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_load_or_create_danmaku_ass_cache(xml_text: str, line_count: int, **kwargs) -> Path | None:
        captured.update(kwargs)
        return tmp_path / "demo.ass"

    monkeypatch.setattr(player_window_module, "load_or_create_danmaku_ass_cache", fake_load_or_create_danmaku_ass_cache)

    config = AppConfig(
        preferred_danmaku_opacity=60,
        preferred_danmaku_outline_strength="soft",
    )
    window = PlayerWindow(FakePlayerController(), config=config)
    qtbot.addWidget(window)

    path = window._build_danmaku_subtitle_file(
        '<?xml version="1.0" encoding="UTF-8"?><i><d p="0.0,1,25,16777215">第一条</d></i>',
        1,
        render_mode="static",
        color_mode="uniform",
        uniform_color="#FFFFFF",
        position_preset="top",
        scroll_speed=1.0,
        font_size=32,
        opacity=60,
        outline_strength="soft",
    )

    assert path == tmp_path / "demo.ass"
    assert captured["opacity"] == 60
    assert captured["outline_strength"] == "soft"
```

Add this dialog regression near the existing danmaku-settings tests:

```python
def test_player_window_saves_and_resets_danmaku_readability_settings(qtbot) -> None:
    saved = {"called": 0}
    config = AppConfig()
    window = PlayerWindow(
        FakePlayerController(),
        config=config,
        save_config=lambda: saved.__setitem__("called", saved["called"] + 1),
    )
    qtbot.addWidget(window)

    dialog = window._ensure_danmaku_settings_dialog()
    dialog.show()
    qtbot.waitUntil(lambda: len(visible_danmaku_settings_dialogs()) == 1)

    assert isinstance(window._danmaku_opacity_spin, QSpinBox)
    assert window._danmaku_outline_strength_combo is not None

    window._danmaku_opacity_spin.setValue(60)
    window._danmaku_outline_strength_combo.setCurrentIndex(
        window._danmaku_outline_strength_combo.findData("soft")
    )

    assert config.preferred_danmaku_opacity == 60
    assert config.preferred_danmaku_outline_strength == "soft"

    window._restore_default_danmaku_render_settings()

    assert config.preferred_danmaku_opacity == 85
    assert config.preferred_danmaku_outline_strength == "strong"
    assert saved["called"] >= 3
```

- [ ] **Step 2: Run the player-window tests to verify they fail**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "readability_settings or passes_readability_settings" -v
```

Expected:

```text
FAILED tests/test_player_window_ui.py::test_player_window_build_danmaku_subtitle_file_passes_readability_settings
FAILED tests/test_player_window_ui.py::test_player_window_saves_and_resets_danmaku_readability_settings
```

The failure should be because `_build_danmaku_subtitle_file(...)` and the danmaku settings dialog do not yet accept the new parameters.

- [ ] **Step 3: Implement the player-window changes**

Add config readers and savers in `src/atv_player/ui/player_window.py`:

```python
def _preferred_danmaku_opacity(self) -> int:
    if self.config is None:
        return 85
    try:
        value = int(getattr(self.config, "preferred_danmaku_opacity", 85))
    except (TypeError, ValueError):
        return 85
    return max(30, min(value, 100))


def _preferred_danmaku_outline_strength(self) -> str:
    if self.config is None:
        return "strong"
    value = str(getattr(self.config, "preferred_danmaku_outline_strength", "strong") or "").strip()
    return value if value in {"soft", "strong"} else "strong"
```

```python
def _save_danmaku_opacity(self, value: int) -> None:
    if self.config is None:
        return
    normalized = max(30, min(int(value), 100))
    if int(getattr(self.config, "preferred_danmaku_opacity", 85)) == normalized:
        return
    self.config.preferred_danmaku_opacity = normalized
    self._save_config()
    self._refresh_danmaku_settings_dialog_controls()
    self._reload_active_danmaku_for_render_settings()


def _save_danmaku_outline_strength(self, value: str) -> None:
    if self.config is None:
        return
    normalized = value if value in {"soft", "strong"} else "strong"
    if str(getattr(self.config, "preferred_danmaku_outline_strength", "strong")) == normalized:
        return
    self.config.preferred_danmaku_outline_strength = normalized
    self._save_config()
    self._refresh_danmaku_settings_dialog_controls()
    self._reload_active_danmaku_for_render_settings()
```

Pass the values into danmaku file generation:

```python
temp_path = self._build_danmaku_subtitle_file(
    xml_text,
    line_count,
    render_mode=self._preferred_danmaku_render_mode(),
    color_mode=self._preferred_danmaku_color_mode(),
    uniform_color=self._preferred_danmaku_uniform_color(),
    position_preset=self._preferred_danmaku_position_preset(),
    scroll_speed=self._preferred_danmaku_scroll_speed(),
    font_size=self._preferred_danmaku_font_size(),
    opacity=self._preferred_danmaku_opacity(),
    outline_strength=self._preferred_danmaku_outline_strength(),
)
```

Extend `_build_danmaku_subtitle_file(...)` and `_current_danmaku_render_settings()`:

```python
def _build_danmaku_subtitle_file(
    self,
    xml_text: str,
    line_count: int,
    *,
    render_mode: str,
    color_mode: str,
    uniform_color: str,
    position_preset: str,
    scroll_speed: float,
    font_size: int,
    opacity: int,
    outline_strength: str,
) -> Path | None:
    ...
    return load_or_create_danmaku_ass_cache(
        xml_text,
        line_count,
        intro_episode_label=intro_episode_label,
        render_mode=render_mode,
        color_mode=color_mode,
        uniform_color=uniform_color,
        position_preset=position_preset,
        scroll_speed=scroll_speed,
        font_size=font_size,
        opacity=opacity,
        outline_strength=outline_strength,
    )
```

Add the dialog controls in `_ensure_danmaku_settings_dialog()`:

```python
opacity_row = QHBoxLayout()
opacity_row.addWidget(QLabel("透明度", host))
self._danmaku_opacity_spin = QSpinBox(host)
self._danmaku_opacity_spin.setRange(30, 100)
self._danmaku_opacity_spin.setSingleStep(5)
self._danmaku_opacity_spin.setSuffix("%")
opacity_row.addWidget(self._danmaku_opacity_spin, 1)
layout.addLayout(opacity_row)

outline_row = QHBoxLayout()
outline_row.addWidget(QLabel("描边强度", host))
self._danmaku_outline_strength_combo = FlatComboBox(host)
self._danmaku_outline_strength_combo.addItem("柔和", "soft")
self._danmaku_outline_strength_combo.addItem("清晰", "strong")
outline_row.addWidget(self._danmaku_outline_strength_combo, 1)
layout.addLayout(outline_row)
```

Wire them into refresh and reset:

```python
if self._danmaku_opacity_spin is not None:
    self._danmaku_opacity_spin.blockSignals(True)
    self._danmaku_opacity_spin.setValue(self._preferred_danmaku_opacity())
    self._danmaku_opacity_spin.blockSignals(False)
if self._danmaku_outline_strength_combo is not None:
    self._danmaku_outline_strength_combo.blockSignals(True)
    self._danmaku_outline_strength_combo.setCurrentIndex(
        max(0, self._danmaku_outline_strength_combo.findData(self._preferred_danmaku_outline_strength()))
    )
    self._danmaku_outline_strength_combo.blockSignals(False)
```

```python
self.config.preferred_danmaku_opacity = 85
self.config.preferred_danmaku_outline_strength = "strong"
```

- [ ] **Step 4: Run the player-window tests to verify they pass**

Run:

```bash
uv run pytest tests/test_player_window_ui.py -k "readability_settings or passes_readability_settings" -v
```

Expected:

```text
PASSED tests/test_player_window_ui.py::test_player_window_build_danmaku_subtitle_file_passes_readability_settings
PASSED tests/test_player_window_ui.py::test_player_window_saves_and_resets_danmaku_readability_settings
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add danmaku readability controls to player settings"
```

### Task 4: Update docs and run the focused verification suite

**Files:**
- Modify: `docs/help.md`
- Modify: `docs/TODO.md`
- Test: `tests/test_danmaku_subtitle.py`
- Test: `tests/test_danmaku_cache.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Update the help text and TODO list**

Update `docs/help.md` so the danmaku settings list reads:

```markdown
- 显示行数
- 显示模式：静态 / 仅滚动 / 混合
- 位置预设
- 颜色模式：统一颜色 / 保留原色
- 统一颜色
- 透明度
- 描边强度
- 文字大小
- 滚动速率
```

Update `docs/TODO.md` so the danmaku section becomes:

```markdown
- [x] 弹幕透明度
- [ ] 弹幕随机颜色
- [x] 弹幕描边强度
- [ ] 弹幕字体
```

- [ ] **Step 2: Run the focused verification suite**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_storage.py tests/test_player_window_ui.py -k "danmaku and (opacity or outline or readability or settings or cache_path_changes_when_opacity_or_outline)" -v
```

Expected:

```text
PASSED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_applies_text_alpha_to_uniform_and_source_color_paths
PASSED tests/test_danmaku_subtitle.py::test_render_danmaku_ass_uses_soft_and_strong_outline_presets
PASSED tests/test_danmaku_cache.py::test_danmaku_ass_cache_path_changes_when_opacity_or_outline_changes
PASSED tests/test_storage.py::test_settings_repository_round_trip_persists_danmaku_readability_settings
PASSED tests/test_storage.py::test_settings_repository_normalizes_invalid_danmaku_readability_settings
PASSED tests/test_player_window_ui.py::test_player_window_build_danmaku_subtitle_file_passes_readability_settings
PASSED tests/test_player_window_ui.py::test_player_window_saves_and_resets_danmaku_readability_settings
```

- [ ] **Step 3: Run the broader danmaku regression pass**

Run:

```bash
uv run pytest tests/test_danmaku_subtitle.py tests/test_danmaku_cache.py tests/test_player_window_ui.py -k "danmaku" -v
```

Expected:

```text
All selected tests pass with no regressions in existing danmaku rendering or player dialog behavior.
```

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/help.md docs/TODO.md
git commit -m "docs: document danmaku readability settings"
```

## Self-Review

### Spec coverage

- `opacity` setting: covered by Task 1 renderer behavior, Task 2 persistence/cache, Task 3 UI control, Task 4 docs.
- `outline strength` setting: covered by Task 1 renderer behavior, Task 2 persistence/cache, Task 3 UI control, Task 4 docs.
- Reuse existing ASS/cache/config/UI pipeline: covered by Tasks 1 through 3.
- Keep random colors and font-family selection out of scope: reflected in File Structure and all task scopes; no task modifies provider parsing or font-family handling.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain in the tasks.
- Every code-changing step includes concrete code to add or modify.
- Every test step names exact test files and commands.

### Type consistency

- Config field names are consistently `preferred_danmaku_opacity` and `preferred_danmaku_outline_strength`.
- Renderer keyword names are consistently `opacity` and `outline_strength`.
- UI helpers and cache helpers use the same names as the renderer and config fields.
