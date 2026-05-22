# Detailed Diagnostics Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate `导出详细诊断` action to the `F1` help dialog that exports a structured, non-sensitive diagnostic text file while keeping the existing copy and export actions as the current short system-info-only variants.

**Architecture:** Keep data collection and text assembly in `MainWindow`, because it already owns the app config, plugin manager, and app log service. Keep `ShortcutHelpDialog` as a UI-only component that receives both the short diagnostics text and the detailed diagnostics text, then exposes a new export button that writes the detailed text to a dedicated file name.

**Tech Stack:** PySide6 widgets, existing `AppConfig` model, `AppLogService`, local plugin manager interface, pytest-qt.

---

### File Map

**Modify:**
- `src/atv_player/ui/help_dialog.py`
  Adds the `导出详细诊断` button, stores the detailed diagnostics text payload, and writes it to `atv-player-diagnostics-detailed.txt`.
- `src/atv_player/ui/main_window.py`
  Builds the detailed diagnostics text from system info, runtime environment, config summary, plugin summary, and recent logs, then passes it to the help dialog.
- `src/atv_player/paths.py`
  Adds a helper for the app data directory if the detailed diagnostics text needs to report it alongside the existing cache directory helper.
- `tests/test_app.py`
  Covers the new help-dialog button, the detailed export file contents, and the main-window payload builder behavior.

**Reference / Reuse:**
- `src/atv_player/diagnostics.py`
  Reuse `collect_system_info_entries()` output for the first diagnostics section.
- `src/atv_player/log_store.py`
  Reuse `AppLogService.load_records(...)` and `AppLogEvent` fields for the recent-log section.
- `src/atv_player/models.py`
  Reuse `AppConfig` fields for the configuration-summary section.

### Task 1: Add failing UI test for the detailed export button

**Files:**
- Modify: `tests/test_app.py`
- Reference: `src/atv_player/ui/help_dialog.py`

- [ ] **Step 1: Write the failing UI test for the new button and file output**

```python
def test_main_window_help_dialog_export_detailed_diagnostics_button_writes_file(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = MainWindow(
        douban_controller=FakeDoubanController(),
        telegram_controller=FakeTelegramController(),
        live_controller=FakeLiveController(),
        emby_controller=FakeEmbyController(),
        jellyfin_controller=FakeJellyfinController(),
        browse_controller=FakeBrowseController(),
        history_controller=FakeHistoryController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
    )
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    window.setFocus()
    window._build_main_window_help_payload = lambda: (
        [SystemInfoEntry("atv-player", "0.8.2", "https://github.com/power721/atv-player/releases/latest")],
        "atv-player: 0.8.2",
        (
            "系统信息\n"
            "atv-player: 0.8.2\n\n"
            "运行环境\n"
            "Qt 平台: xcb\n\n"
            "应用配置摘要\n"
            "主题: dark\n\n"
            "插件摘要\n"
            "已启用插件数: 1\n\n"
            "最近日志\n"
            "[2026-05-22T12:00:00.000] INFO app/app 启动完成"
        ),
    )

    export_path = tmp_path / "detailed.txt"
    monkeypatch.setattr(
        "atv_player.ui.help_dialog.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "Text Files (*.txt)"),
    )

    QTest.keyClick(window, Qt.Key.Key_F1)

    qtbot.waitUntil(lambda: len(visible_shortcut_help_dialogs()) == 1)
    dialog = visible_shortcut_help_dialogs()[0]
    export_button = dialog.findChild(QPushButton, "exportDetailedDiagnosticsButton")
    assert export_button is not None

    QTest.mouseClick(export_button, Qt.MouseButton.LeftButton)

    assert export_path.read_text(encoding="utf-8") == (
        "系统信息\n"
        "atv-player: 0.8.2\n\n"
        "运行环境\n"
        "Qt 平台: xcb\n\n"
        "应用配置摘要\n"
        "主题: dark\n\n"
        "插件摘要\n"
        "已启用插件数: 1\n\n"
        "最近日志\n"
        "[2026-05-22T12:00:00.000] INFO app/app 启动完成"
    )
```

- [ ] **Step 2: Run the new UI test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_main_window_help_dialog_export_detailed_diagnostics_button_writes_file -q`

Expected: FAIL because `ShortcutHelpDialog` does not expose an `exportDetailedDiagnosticsButton` yet, and `_build_main_window_help_payload()` does not return a third detailed-text value.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_app.py
git commit -m "test: cover detailed diagnostics export button"
```

### Task 2: Add failing unit test for detailed diagnostics payload generation

**Files:**
- Modify: `tests/test_app.py`
- Reference: `src/atv_player/ui/main_window.py`
- Reference: `src/atv_player/log_store.py`

- [ ] **Step 1: Write the failing payload-builder test**

```python
def test_main_window_help_payload_builds_detailed_diagnostics_text(qtbot, monkeypatch, tmp_path) -> None:
    class FakePluginManager:
        def list_plugins(self):
            return [
                SimpleNamespace(name="插件一", enabled=True),
                SimpleNamespace(name="插件二", enabled=False),
            ]

    class FakeLogService:
        def load_records(self, *, limit, log_filter):
            del log_filter
            assert limit == 20
            return [
                AppLogEvent(
                    timestamp="2026-05-22T12:00:00.000",
                    level="INFO",
                    source="app",
                    category="app",
                    message="启动完成",
                    module="main",
                )
            ]

    monkeypatch.setattr(
        main_window_module,
        "collect_system_info_entries",
        lambda: (
            SystemInfoEntry("atv-player", "0.8.2", "https://github.com/power721/atv-player/releases/latest"),
            SystemInfoEntry("Platform", "Linux 6.8.0 (x86_64)"),
        ),
    )
    monkeypatch.setattr(main_window_module.QGuiApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(main_window_module, "app_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(main_window_module, "app_cache_dir", lambda: tmp_path / "cache")

    config = AppConfig(theme_mode="dark", network_proxy_mode="direct", base_url="http://127.0.0.1:4567")
    window = MainWindow(
        douban_controller=FakeDoubanController(),
        telegram_controller=FakeTelegramController(),
        live_controller=FakeLiveController(),
        emby_controller=FakeEmbyController(),
        jellyfin_controller=FakeJellyfinController(),
        browse_controller=FakeBrowseController(),
        history_controller=FakeHistoryController(),
        player_controller=FakePlayerController(),
        config=config,
        plugin_manager=FakePluginManager(),
        app_log_service=FakeLogService(),
    )
    qtbot.addWidget(window)

    system_info_rows, diagnostics_text, detailed_text = window._build_main_window_help_payload()

    assert diagnostics_text == "系统信息\natv-player: 0.8.2\nPlatform: Linux 6.8.0 (x86_64)"
    assert "系统信息" in detailed_text
    assert "运行环境" in detailed_text
    assert "Qt 平台: xcb" in detailed_text
    assert "应用配置摘要" in detailed_text
    assert "主题: dark" in detailed_text
    assert "代理模式: direct" in detailed_text
    assert "后端地址: http://127.0.0.1:4567" in detailed_text
    assert "插件摘要" in detailed_text
    assert "已启用插件数: 1" in detailed_text
    assert "插件一" in detailed_text
    assert "最近日志" in detailed_text
    assert "[2026-05-22T12:00:00.000] INFO app/app 启动完成" in detailed_text
```

- [ ] **Step 2: Run the payload-builder test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_main_window_help_payload_builds_detailed_diagnostics_text -q`

Expected: FAIL because `_build_main_window_help_payload()` currently returns only two values and has no detailed-text builder.

- [ ] **Step 3: Commit the failing payload test**

```bash
git add tests/test_app.py
git commit -m "test: cover detailed diagnostics payload builder"
```

### Task 3: Add the detailed diagnostics payload builder in MainWindow

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `src/atv_player/paths.py`
- Reference: `src/atv_player/log_store.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Add focused helpers for detailed diagnostics text assembly**

```python
def _build_main_window_help_payload(self) -> tuple[list[SystemInfoEntry], str, str]:
    system_info_rows = list(collect_system_info_entries())
    short_lines = ["系统信息"]
    short_lines.extend(f"{entry.label}: {entry.value}" for entry in system_info_rows)
    return system_info_rows, "\n".join(short_lines), self._build_detailed_diagnostics_text(system_info_rows)

def _build_detailed_diagnostics_text(self, system_info_rows: list[SystemInfoEntry]) -> str:
    sections = [
        self._build_detailed_system_info_section(system_info_rows),
        self._build_detailed_runtime_section(),
        self._build_detailed_config_section(),
        self._build_detailed_plugin_section(),
        self._build_detailed_log_section(),
    ]
    return "\n\n".join(section for section in sections if section.strip())
```

- [ ] **Step 2: Implement the runtime, config, plugin, and log helpers with safe fallbacks**

```python
def _build_detailed_runtime_section(self) -> str:
    lines = ["运行环境"]
    lines.append(f"Qt 平台: {QGuiApplication.platformName() or '不可用'}")
    lines.append(f"数据目录: {app_data_dir()}")
    lines.append(f"缓存目录: {app_cache_dir()}")
    return "\n".join(lines)

def _build_detailed_config_section(self) -> str:
    lines = ["应用配置摘要"]
    lines.append(f"主题: {self.config.theme_mode}")
    lines.append(f"代理模式: {self.config.network_proxy_mode}")
    lines.append(f"后端地址: {self.config.base_url}")
    lines.append(f"最后活动窗口: {self.config.last_active_window}")
    return "\n".join(lines)

def _build_detailed_plugin_section(self) -> str:
    lines = ["插件摘要"]
    plugins = self._list_enabled_plugin_names()
    lines.append(f"已启用插件数: {len(plugins)}")
    lines.extend(plugins or ["无"])
    return "\n".join(lines)

def _build_detailed_log_section(self) -> str:
    lines = ["最近日志"]
    records = self._load_recent_app_logs(limit=20)
    lines.extend(records or ["无"])
    return "\n".join(lines)
```

- [ ] **Step 3: Run both new tests to verify they now pass**

Run: `uv run pytest tests/test_app.py::test_main_window_help_payload_builds_detailed_diagnostics_text tests/test_app.py::test_main_window_help_payload_diagnostics_text_excludes_shortcuts -q`

Expected: PASS

- [ ] **Step 4: Commit the payload builder**

```bash
git add src/atv_player/ui/main_window.py src/atv_player/paths.py tests/test_app.py
git commit -m "feat: build detailed diagnostics payload"
```

### Task 4: Add the detailed export button to the help dialog

**Files:**
- Modify: `src/atv_player/ui/help_dialog.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Extend the help dialog API to accept detailed diagnostics text**

```python
class ShortcutHelpDialog(ThemedDialogBase):
    def __init__(
        self,
        entries: Sequence[ShortcutEntry],
        parent: QWidget | None = None,
        *,
        system_info_rows: Sequence[SystemInfoEntry] | None = None,
        diagnostics_text: str = "",
        detailed_diagnostics_text: str = "",
    ) -> None:
        self._diagnostics_text = diagnostics_text
        self._detailed_diagnostics_text = detailed_diagnostics_text
```

- [ ] **Step 2: Add the new button and export handler**

```python
self.export_detailed_diagnostics_button = QPushButton("导出详细诊断", self)
self.export_detailed_diagnostics_button.setObjectName("exportDetailedDiagnosticsButton")
self.export_detailed_diagnostics_button.clicked.connect(self._export_detailed_diagnostics)
actions.addWidget(self.export_detailed_diagnostics_button)

def _export_detailed_diagnostics(self) -> None:
    path, _ = QFileDialog.getSaveFileName(
        self,
        "导出详细诊断",
        "atv-player-diagnostics-detailed.txt",
        "Text Files (*.txt);;All Files (*)",
    )
    if not path:
        return
    try:
        Path(path).write_text(self._detailed_diagnostics_text, encoding="utf-8")
    except OSError as exc:
        QMessageBox.critical(self, "错误", f"导出详细诊断失败: {exc}")
```

- [ ] **Step 3: Pass the detailed text from MainWindow into the dialog**

```python
system_info_rows, diagnostics_text, detailed_diagnostics_text = self._build_main_window_help_payload()
dialog = show_shortcut_help_dialog(
    self,
    context="main_window",
    existing_dialog=self.help_dialog,
    quit_sequence=self.quit_shortcut.key(),
    system_info_rows=system_info_rows,
    diagnostics_text=diagnostics_text,
    detailed_diagnostics_text=detailed_diagnostics_text,
)
```

- [ ] **Step 4: Run the new export-button test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_main_window_help_dialog_export_detailed_diagnostics_button_writes_file -q`

Expected: PASS

- [ ] **Step 5: Commit the dialog change**

```bash
git add src/atv_player/ui/help_dialog.py src/atv_player/ui/main_window.py tests/test_app.py
git commit -m "feat: add detailed diagnostics export button"
```

### Task 5: Add regression coverage for default file name and section structure

**Files:**
- Modify: `tests/test_app.py`
- Reference: `src/atv_player/ui/help_dialog.py`

- [ ] **Step 1: Add a test that locks the default detailed export file name**

```python
def test_main_window_help_dialog_detailed_export_uses_dedicated_default_filename(
    qtbot, monkeypatch
) -> None:
    window = MainWindow(
        douban_controller=FakeDoubanController(),
        telegram_controller=FakeTelegramController(),
        live_controller=FakeLiveController(),
        emby_controller=FakeEmbyController(),
        jellyfin_controller=FakeJellyfinController(),
        browse_controller=FakeBrowseController(),
        history_controller=FakeHistoryController(),
        player_controller=FakePlayerController(),
        config=AppConfig(),
    )
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    window.setFocus()
    window._build_main_window_help_payload = lambda: (
        [SystemInfoEntry("atv-player", "0.8.2", "https://github.com/power721/atv-player/releases/latest")],
        "atv-player: 0.8.2",
        "系统信息\natv-player: 0.8.2",
    )

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "atv_player.ui.help_dialog.QFileDialog.getSaveFileName",
        lambda parent, title, default_name, filters: calls.append((title, default_name)) or ("", filters),
    )

    QTest.keyClick(window, Qt.Key.Key_F1)
    qtbot.waitUntil(lambda: len(visible_shortcut_help_dialogs()) == 1)
    dialog = visible_shortcut_help_dialogs()[0]
    button = dialog.findChild(QPushButton, "exportDetailedDiagnosticsButton")
    assert button is not None

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    assert calls == [("导出详细诊断", "atv-player-diagnostics-detailed.txt")]
```

- [ ] **Step 2: Run the dedicated file-name regression test**

Run: `uv run pytest tests/test_app.py::test_main_window_help_dialog_detailed_export_uses_dedicated_default_filename -q`

Expected: PASS

- [ ] **Step 3: Commit the regression coverage**

```bash
git add tests/test_app.py
git commit -m "test: lock detailed diagnostics export filename"
```

### Task 6: Run focused verification and inspect diff

**Files:**
- Modify: none
- Test: `tests/test_app.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Run the focused diagnostics/help-dialog test set**

Run: `uv run pytest tests/test_diagnostics.py tests/test_app.py::test_main_window_f1_opens_shortcut_help_dialog tests/test_app.py::test_main_window_help_dialog_copy_diagnostics_button_copies_text tests/test_app.py::test_main_window_help_dialog_export_diagnostics_button_writes_file tests/test_app.py::test_main_window_help_payload_diagnostics_text_excludes_shortcuts tests/test_app.py::test_main_window_help_payload_builds_detailed_diagnostics_text tests/test_app.py::test_main_window_help_dialog_export_detailed_diagnostics_button_writes_file tests/test_app.py::test_main_window_help_dialog_detailed_export_uses_dedicated_default_filename tests/test_app.py::test_main_window_help_dialog_opens_system_info_links_except_platform tests/test_app.py::test_main_window_help_dialog_renders_system_info_links_like_player_metadata -q`

Expected: PASS

- [ ] **Step 2: Run the shared player-window external-link regression**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_renders_external_metadata_links_for_known_ids -q`

Expected: PASS

- [ ] **Step 3: Inspect the final diff**

Run: `git diff -- src/atv_player/ui/help_dialog.py src/atv_player/ui/main_window.py src/atv_player/paths.py tests/test_app.py tests/test_diagnostics.py`

Expected: only the detailed diagnostics payload builder, the new help-dialog button/export path, and the related tests appear.

