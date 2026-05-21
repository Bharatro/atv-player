# Spider Plugin Bulk Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one unified spider-plugin bulk import entry that accepts either a GitHub repository URL or a direct `spiders_v2.json` URL.

**Architecture:** Keep GitHub repository resolution as a small front-end step in `SpiderPluginManager`, then route both GitHub and direct-manifest sources through one shared manifest-import core. Update the plugin-manager dialog to expose one generic bulk-import action while preserving current progress, cancellation, summary, and remote-plugin behavior.

**Tech Stack:** Python 3.12, PySide6, httpx, pytest, existing spider plugin manager/dialog/repository code

---

### Task 1: Generalize manager import flow to support direct manifest URLs

**Files:**
- Modify: `src/atv_player/plugins/__init__.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Write the failing manager tests for unified source parsing and direct manifest imports**

Add these tests to `tests/test_spider_plugin_manager.py` near the existing GitHub import coverage:

```python
def test_manager_import_plugins_accepts_direct_manifest_url_with_relative_files(tmp_path: Path) -> None:
    responses = {
        "https://d.har01d.cn/spiders_v2.json": httpx.Response(
            200,
            json=[
                {"file": "py/红果.txt", "valid": True, "version": 8},
                {"file": "nested/双星.txt", "valid": False, "version": 3},
            ],
        ),
        "https://d.har01d.cn/py/%E7%BA%A2%E6%9E%9C.txt": httpx.Response(200, text="//@version:1\nprint('a')\n"),
        "https://d.har01d.cn/nested/%E5%8F%8C%E6%98%9F.txt": httpx.Response(200, text="//@version:2\nprint('b')\n"),
    }
    progress_events: list[tuple[str, int, int, str]] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        response = responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response

    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader(), get=fake_get)

    result = manager.import_plugins(
        "https://d.har01d.cn/spiders_v2.json",
        progress_callback=lambda event: progress_events.append(
            (event.stage, event.current, event.total, event.message)
        ),
    )

    plugins = repository.list_plugins()

    assert result == SpiderPluginImportResult(imported_count=2, updated_count=0, skipped_count=0)
    assert [plugin.source_value for plugin in plugins] == [
        "https://d.har01d.cn/py/%E7%BA%A2%E6%9E%9C.txt",
        "https://d.har01d.cn/nested/%E5%8F%8C%E6%98%9F.txt",
    ]
    assert [plugin.enabled for plugin in plugins] == [True, False]
    assert progress_events == [
        ("fetch_manifest", 0, 0, "正在读取 spiders_v2.json"),
        ("import_plugin", 1, 2, "正在导入 py/红果.txt"),
        ("import_plugin", 2, 2, "正在导入 nested/双星.txt"),
    ]


def test_manager_import_plugins_accepts_direct_manifest_url_with_absolute_files(tmp_path: Path) -> None:
    plugin_url = "https://cdn.example.com/plugins/%E6%BD%AE%E6%B5%81APP.txt"
    responses = {
        "https://example.com/spiders_v2.json": httpx.Response(
            200,
            json=[{"file": plugin_url, "valid": True, "version": 6}],
        ),
        plugin_url: httpx.Response(200, text="//@version:1\nprint('a')\n"),
    }

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        response = responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response

    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader(), get=fake_get)

    result = manager.import_plugins("https://example.com/spiders_v2.json")

    plugins = repository.list_plugins()

    assert result == SpiderPluginImportResult(imported_count=1, updated_count=0, skipped_count=0)
    assert [plugin.source_value for plugin in plugins] == [plugin_url]


def test_manager_import_plugins_skips_relative_entries_with_parent_traversal(tmp_path: Path) -> None:
    responses = {
        "https://example.com/plugins/spiders_v2.json": httpx.Response(
            200,
            json=[{"file": "../escape.txt", "valid": True, "version": 2}],
        ),
    }

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        response = responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response

    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader(), get=fake_get)

    result = manager.import_plugins("https://example.com/plugins/spiders_v2.json")

    assert result == SpiderPluginImportResult(imported_count=0, updated_count=0, skipped_count=1)
    assert repository.list_plugins() == []


def test_manager_import_plugins_rejects_invalid_source_url(tmp_path: Path) -> None:
    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader())

    with pytest.raises(ValueError, match="请输入 GitHub 仓库地址或 spiders_v2.json URL"):
        manager.import_plugins("not-a-url")
```

Also update the existing GitHub import tests to call the new unified public entry:

```python
result = manager.import_plugins("https://github.com/har01d5/tvbox")
```

- [ ] **Step 2: Run the focused manager tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "import_plugins or import_github_repository" -v
```

Expected:

- FAIL with `AttributeError: 'SpiderPluginManager' object has no attribute 'import_plugins'`
- or FAIL because existing GitHub-specific expectations no longer match the new public entry

- [ ] **Step 3: Implement the unified source parser and shared manifest import core**

Update `src/atv_player/plugins/__init__.py` with a minimal generalization like this:

```python
from urllib.parse import quote, unquote, urljoin, urlparse


def _is_github_repo_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    return parsed.scheme == "https" and parsed.netloc == "github.com" and len(parts) >= 2


def _parse_manifest_source_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入 GitHub 仓库地址或 spiders_v2.json URL")
    return value.strip()


def _resolve_manifest_entry_source_url(manifest_url: str, file_path: str) -> str | None:
    parsed = urlparse(file_path)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return file_path
    path = PurePosixPath(file_path)
    if path.is_absolute() or ".." in path.parts:
        return None
    return urljoin(manifest_url, quote(file_path))
```

Add one shared import helper and route both sources through it:

```python
def import_plugins(
    self,
    source_url: str,
    *,
    progress_callback: Callable[[SpiderPluginImportProgress], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> SpiderPluginImportResult:
    result = SpiderPluginImportResult()
    source_url = source_url.strip()
    if _is_github_repo_url(source_url):
        owner, repo = _parse_github_repo(source_url)
        self._raise_if_import_cancelled(cancel_callback, result)
        self._emit_import_progress(progress_callback, stage="resolve_repo", message="正在解析仓库信息")
        self._raise_if_import_cancelled(cancel_callback, result)
        default_branch = self._load_github_default_branch(owner, repo)
        manifest_url = _raw_github_url(owner, repo, default_branch, "spiders_v2.json")
        return self._import_manifest(
            manifest_url,
            result,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
    manifest_url = _parse_manifest_source_url(source_url)
    return self._import_manifest(
        manifest_url,
        result,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback,
    )


def _import_manifest(
    self,
    manifest_url: str,
    result: SpiderPluginImportResult,
    *,
    progress_callback: Callable[[SpiderPluginImportProgress], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> SpiderPluginImportResult:
    self._emit_import_progress(progress_callback, stage="fetch_manifest", message="正在读取 spiders_v2.json")
    self._raise_if_import_cancelled(cancel_callback, result)
    manifest = self._fetch_json(manifest_url)
    if not isinstance(manifest, list):
        raise ValueError("spiders_v2.json 格式无效")
    valid_entries = [entry for entry in manifest if isinstance(entry, dict) and str(entry.get("file") or "").strip()]
    total = len(valid_entries)
    for index, entry in enumerate(valid_entries, start=1):
        self._raise_if_import_cancelled(cancel_callback, result)
        file_path = str(entry.get("file") or "").strip()
        self._emit_import_progress(
            progress_callback,
            stage="import_plugin",
            current=index,
            total=total,
            message=f"正在导入 {file_path}",
        )
        plugin_version = _parse_manifest_plugin_version(entry)
        if plugin_version is None:
            result.skipped_count += 1
            continue
        source_url = _resolve_manifest_entry_source_url(manifest_url, file_path)
        if source_url is None:
            result.skipped_count += 1
            continue
        try:
            self._raise_if_import_cancelled(cancel_callback, result)
            self._fetch_text(source_url)
            existing = self._repository.find_plugin_by_source_value(source_url)
            if existing is None:
                plugin = self._repository.add_plugin(
                    "remote",
                    source_url,
                    _default_plugin_name("remote", source_url),
                    enabled=bool(entry.get("valid", True)),
                    plugin_version=plugin_version,
                )
                result.imported_count += 1
                self._raise_if_import_cancelled(cancel_callback, result)
                self.refresh_plugin(plugin.id)
                continue
            if existing.plugin_version == plugin_version:
                result.skipped_count += 1
                continue
            self._repository.update_plugin(
                existing.id,
                display_name=existing.display_name,
                enabled=existing.enabled,
                cached_file_path=existing.cached_file_path,
                last_loaded_at=existing.last_loaded_at,
                last_error=existing.last_error,
                config_text=existing.config_text,
                plugin_version=plugin_version,
                category_overrides_json=existing.category_overrides_json,
            )
            result.updated_count += 1
            self._raise_if_import_cancelled(cancel_callback, result)
            self.refresh_plugin(existing.id)
        except SpiderPluginImportCancelled:
            raise
        except Exception:
            result.skipped_count += 1
    return result


def import_github_repository(
    self,
    repo_url: str,
    *,
    progress_callback: Callable[[SpiderPluginImportProgress], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> SpiderPluginImportResult:
    return self.import_plugins(
        repo_url,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback,
    )
```

- [ ] **Step 4: Run the focused manager tests to verify they pass**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "import_plugins or import_github_repository" -v
```

Expected:

- PASS for the existing GitHub import coverage
- PASS for the new direct-manifest, absolute-URL, traversal-skip, and invalid-input coverage

- [ ] **Step 5: Commit the manager import refactor**

```bash
git add src/atv_player/plugins/__init__.py tests/test_spider_plugin_manager.py
git commit -m "feat: support spider plugin bulk manifest import"
```

### Task 2: Rename the dialog entry to bulk import and wire it to the unified manager API

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Test: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Write the failing dialog tests for bulk-import labels and dispatch**

Update `tests/test_plugin_manager_dialog.py` so `FakePluginManager` exposes the new API and the dialog tests assert the renamed UI:

```python
class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SpiderPluginConfig(
                id=1,
                source_type="local",
                source_value="/plugins/a.py",
                display_name="本地A",
                enabled=True,
                sort_order=0,
                config_text="token=local",
                plugin_version=3,
            ),
            SpiderPluginConfig(
                id=2,
                source_type="remote",
                source_value="https://example.com/b.py",
                display_name="远程B",
                enabled=False,
                sort_order=1,
                last_error="下载失败",
                config_text="token=remote\ncookie=1\n",
                plugin_version=7,
            ),
        ]
        self.logs = {
            2: [SpiderPluginLogEntry(id=1, plugin_id=2, level="error", message="下载失败", created_at=1713206400)]
        }
        self.rename_calls: list[tuple[int, str]] = []
        self.config_calls: list[tuple[int, str]] = []
        self.toggle_calls: list[tuple[int, bool]] = []
        self.move_calls: list[tuple[int, int]] = []
        self.refresh_calls: list[int] = []
        self.add_local_calls: list[str] = []
        self.add_remote_calls: list[str] = []
        self.import_calls: list[str] = []
        self.delete_calls: list[int] = []
        self.action_calls: list[tuple[int, str, object]] = []
        self.progress_events: list[tuple[str, int, int, str]] = []
        self.action_query_calls: list[int] = []
        self.cancel_callback_checks = 0
        self.cancel_result = SpiderPluginImportResult(imported_count=1, updated_count=0, skipped_count=0)
        self.import_result = SpiderPluginImportResult(imported_count=2, updated_count=1, skipped_count=3)
        self.actions = {
            1: [SpiderPluginAction(id="qr_login", label="扫码登录")],
            2: [
                SpiderPluginAction(
                    id="refresh_cookie",
                    label="刷新 Cookie",
                    enabled=False,
                    tooltip="需要先扫码登录",
                )
            ],
        }

    def import_plugins(self, source_url: str, *, progress_callback=None, cancel_callback=None):
        self.import_calls.append(source_url)
        if progress_callback is not None:
            for event in (
                SpiderPluginImportProgress(stage="resolve_repo", message="正在解析仓库信息"),
                SpiderPluginImportProgress(stage="fetch_manifest", message="正在读取 spiders_v2.json"),
                SpiderPluginImportProgress(stage="import_plugin", current=1, total=2, message="正在导入 py/a.txt"),
                SpiderPluginImportProgress(stage="import_plugin", current=2, total=2, message="正在导入 py/b.txt"),
            ):
                self.progress_events.append((event.stage, event.current, event.total, event.message))
                progress_callback(event)
                if cancel_callback is not None:
                    self.cancel_callback_checks += 1
                    if cancel_callback():
                        raise SpiderPluginImportCancelled(self.cancel_result)
        return self.import_result
```

Add or update dialog assertions:

```python
def test_plugin_manager_dialog_renders_bulk_import_button(qtbot) -> None:
    dialog = PluginManagerDialog(FakePluginManager())
    qtbot.addWidget(dialog)

    assert dialog.import_github_button.text() == "批量导入"


def test_plugin_manager_dialog_imports_with_progress_and_summary(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()
    summary_messages: list[str] = []
    monkeypatch.setattr(dialog, "_prompt_import_source_url", lambda: "https://d.har01d.cn/spiders_v2.json")
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QMessageBox.information", lambda *args: summary_messages.append(args[2]))
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QApplication.processEvents", lambda *args, **kwargs: None)

    class FakeProgressDialog:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def setWindowTitle(self, title: str) -> None:
            pass

        def setMinimumDuration(self, duration: int) -> None:
            pass

        def setAutoClose(self, auto_close: bool) -> None:
            pass

        def setAutoReset(self, auto_reset: bool) -> None:
            pass

        def setCancelButton(self, button) -> None:
            pass

        def setWindowModality(self, modality) -> None:
            pass

        def setRange(self, minimum: int, maximum: int) -> None:
            pass

        def setValue(self, value: int) -> None:
            pass

        def setLabelText(self, text: str) -> None:
            pass

        def wasCanceled(self) -> bool:
            return False

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QProgressDialog", FakeProgressDialog)

    dialog._import_plugins()

    assert manager.import_calls == ["https://d.har01d.cn/spiders_v2.json"]
    assert summary_messages == ["导入完成：新增 2 个，更新 1 个，跳过 3 个。"]
```

Update the existing modal/cancel/reentry tests to call:

```python
dialog._import_plugins()
```

and to patch:

```python
monkeypatch.setattr(dialog, "_prompt_import_source_url", lambda: "https://github.com/har01d5/tvbox")
```

- [ ] **Step 2: Run the focused dialog tests to verify they fail**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_plugin_manager_dialog.py -k "import or bulk" -v
```

Expected:

- FAIL because `PluginManagerDialog` still renders `从 GitHub 导入`
- or FAIL because the dialog still calls `_prompt_github_repo_url()` / `import_github_repository()`

- [ ] **Step 3: Implement the bulk-import dialog rename and dispatch changes**

Update `src/atv_player/ui/plugin_manager_dialog.py` like this:

```python
self.import_github_button = QPushButton("批量导入")
for button in (
    self.add_local_button,
    self.add_remote_button,
    self.import_github_button,
    self.rename_button,
    self.config_button,
    self.category_button,
    self.enable_button,
    self.disable_button,
    self.up_button,
    self.down_button,
    self.reorder_button,
    self.refresh_button,
    self.logs_button,
    self.delete_button,
):
    actions.addWidget(button)
self.import_github_button.clicked.connect(self._import_plugins)
```

Rename the prompt and action methods:

```python
def _prompt_import_source_url(self) -> str:
    value, accepted = QInputDialog.getText(
        self,
        "批量导入",
        "GitHub 仓库 URL 或 spiders_v2.json URL",
    )
    return value.strip() if accepted else ""


def _import_plugins(self) -> None:
    if self._import_in_progress:
        return
    source_url = self._prompt_import_source_url()
    if not source_url:
        return
    progress = QProgressDialog("", "取消", 0, 0, self)
    progress.setWindowTitle("批量导入")
    self._import_in_progress = True
    self.import_github_button.setEnabled(False)
    try:
        result = self.plugin_manager.import_plugins(
            source_url,
            progress_callback=lambda event: self._update_import_progress(progress, event),
            cancel_callback=lambda: progress.wasCanceled(),
        )
    except SpiderPluginImportCancelled as exc:
        result = exc.result
        if result.imported_count or result.updated_count:
            self.plugin_tabs_dirty = True
        self.reload_plugins()
        QMessageBox.information(
            self,
            "导入已取消",
            f"已取消：新增 {result.imported_count} 个，更新 {result.updated_count} 个，跳过 {result.skipped_count} 个。",
        )
    except Exception as exc:
        QMessageBox.warning(self, "导入失败", str(exc))
    else:
        if result.imported_count or result.updated_count:
            self.plugin_tabs_dirty = True
        self.reload_plugins()
        QMessageBox.information(
            self,
            "导入完成",
            f"导入完成：新增 {result.imported_count} 个，更新 {result.updated_count} 个，跳过 {result.skipped_count} 个。",
        )
    finally:
        progress.close()
        self._import_in_progress = False
        self.import_github_button.setEnabled(True)
```

Keep the internal variable name `self.import_github_button` to minimize churn, but change the visible text, prompt text, progress title, and dispatch target to `import_plugins()`. Do not change cancellation or reload behavior.

- [ ] **Step 4: Run the focused dialog tests to verify they pass**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_plugin_manager_dialog.py -k "import or bulk" -v
```

Expected:

- PASS for the renamed button/prompt/title expectations
- PASS for progress updates, cancellation summary, and reentrancy protection

- [ ] **Step 5: Commit the dialog bulk-import update**

```bash
git add src/atv_player/ui/plugin_manager_dialog.py tests/test_plugin_manager_dialog.py
git commit -m "feat: rename spider plugin import entry to bulk import"
```

### Task 3: Update docs and run the final focused verification set

**Files:**
- Modify: `README.md`
- Verify: `tests/test_spider_plugin_manager.py`
- Verify: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Update the README plugin import description**

Change the plugin feature bullet in `README.md` from:

```md
- 支持 GitHub 仓库导入，显示新增/更新/跳过摘要
```

to:

```md
- 支持 GitHub 仓库和 `spiders_v2.json` 清单 URL 导入，显示新增/更新/跳过摘要
```

- [ ] **Step 2: Run the focused manager and dialog verification suites**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py -v
```

Expected:

- PASS for all manager import tests
- PASS for all plugin-manager dialog tests

- [ ] **Step 3: Inspect the changed files before the final commit**

Run:

```bash
git diff -- src/atv_player/plugins/__init__.py src/atv_player/ui/plugin_manager_dialog.py tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py README.md
```

Expected:

- one shared manager import path for GitHub and direct manifest URLs
- bulk-import wording in the dialog
- updated tests covering direct manifest imports and renamed UI text
- README mentioning both supported import source types

- [ ] **Step 4: Commit the docs and verified feature**

```bash
git add README.md
git commit -m "docs: mention spider plugin manifest import"
```
