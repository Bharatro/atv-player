# GitHub Plugin Repository Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the plugin manager import spider plugins from a GitHub repository URL by auto-discovering the repo default branch, loading `spiders_v2.json`, persisting plugin versions from source `//@version:` markers, skipping same-version duplicates, default-disabling `valid=false` entries, and showing visible progress during import.

**Architecture:** Keep GitHub parsing and import rules inside `SpiderPluginManager`, extend `SpiderPluginRepository` plus `SpiderPluginConfig` with a persisted `plugin_version`, and keep the dialog responsible only for prompting, showing a progress dialog, and summarizing results. The implementation stays synchronous but exposes progress through a plain Python callback so the UI can update without leaking Qt types into the manager.

**Tech Stack:** Python 3.13, PySide6, httpx, sqlite-backed plugin repository, pytest, existing spider-plugin loader/manager flow

---

## File Structure

- Modify: `src/atv_player/models.py`
  Add typed import progress/result dataclasses and extend `SpiderPluginConfig` with `plugin_version`.
- Modify: `src/atv_player/plugins/repository.py`
  Migrate `spider_plugins` with `plugin_version`, support version-aware create/update, and add lookup by `source_value`.
- Modify: `src/atv_player/plugins/__init__.py`
  Extend `SpiderPluginManager` with GitHub repository parsing, default-branch discovery, manifest import, source-version parsing, progress callbacks, and result aggregation.
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
  Add the “从 GitHub 导入” button, prompt for repo URL, show a progress dialog, dispatch import, and display the final summary.
- Modify: `tests/test_spider_plugin_manager.py`
  Add focused manager tests for GitHub manifest import, `valid=false`, version defaults, duplicate skipping, and version updates.
- Modify: `tests/test_plugin_manager_dialog.py`
  Add dialog tests for the new button, progress callback wiring, and final summary behavior.

## Task 1: Lock The Manager Import Rules With Failing Tests

**Files:**
- Modify: `tests/test_spider_plugin_manager.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Write the failing GitHub import behavior tests**

Add these imports near the top of `tests/test_spider_plugin_manager.py`:

```python
import httpx

from atv_player.models import SpiderPluginImportResult, SpiderPluginImportProgress, SpiderPluginAction, SpiderPluginConfig
```

Add these tests below `test_manager_add_remote_plugin_uses_decoded_url_filename_as_default_name`:

```python
def test_manager_import_github_repository_imports_manifest_plugins_and_disables_invalid_entries(tmp_path: Path) -> None:
    responses = {
        "https://api.github.com/repos/har01d5/tvbox": httpx.Response(
            200,
            json={"default_branch": "master"},
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/spiders_v2.json": httpx.Response(
            200,
            json=[
                {"file": "py/潮流APP.txt", "valid": True},
                {"file": "py/双星.txt", "valid": False},
                {"file": "py/无版本.txt"},
            ],
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%BD%AE%E6%B5%81APP.txt": httpx.Response(
            200,
            text="//@version:6\nprint('a')\n",
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt": httpx.Response(
            200,
            text="  //@version:2\nprint('b')\n",
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%97%A0%E7%89%88%E6%9C%AC.txt": httpx.Response(
            200,
            text="print('c')\n",
        ),
    }
    progress_events: list[tuple[str, int, int, str]] = []

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        response = responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response

    repository = SpiderPluginRepository(tmp_path / "app.db")
    manager = SpiderPluginManager(repository, FakeLoader(), get=fake_get)

    result = manager.import_github_repository(
        "https://github.com/har01d5/tvbox",
        progress_callback=lambda event: progress_events.append(
            (event.stage, event.current, event.total, event.message)
        ),
    )

    plugins = repository.list_plugins()

    assert result == SpiderPluginImportResult(imported_count=3, updated_count=0, skipped_count=0)
    assert [plugin.source_value for plugin in plugins] == [
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%BD%AE%E6%B5%81APP.txt",
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt",
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%97%A0%E7%89%88%E6%9C%AC.txt",
    ]
    assert [plugin.plugin_version for plugin in plugins] == [6, 2, 1]
    assert [plugin.enabled for plugin in plugins] == [True, False, True]
    assert progress_events == [
        ("resolve_repo", 0, 0, "正在解析仓库信息"),
        ("fetch_manifest", 0, 0, "正在读取 spiders_v2.json"),
        ("import_plugin", 1, 3, "正在导入 py/潮流APP.txt"),
        ("import_plugin", 2, 3, "正在导入 py/双星.txt"),
        ("import_plugin", 3, 3, "正在导入 py/无版本.txt"),
    ]


def test_manager_import_github_repository_skips_same_version_and_updates_existing_version(tmp_path: Path) -> None:
    responses = {
        "https://api.github.com/repos/har01d5/tvbox": httpx.Response(
            200,
            json={"default_branch": "master"},
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/spiders_v2.json": httpx.Response(
            200,
            json=[
                {"file": "py/潮流APP.txt", "valid": True},
                {"file": "py/双星.txt", "valid": True},
            ],
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%BD%AE%E6%B5%81APP.txt": httpx.Response(
            200,
            text="//@version:6\nprint('same')\n",
        ),
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt": httpx.Response(
            200,
            text="//@version:7\nprint('new')\n",
        ),
    }

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        response = responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response

    repository = SpiderPluginRepository(tmp_path / "app.db")
    repository.add_plugin(
        "remote",
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E6%BD%AE%E6%B5%81APP.txt",
        "潮流APP",
        enabled=True,
        plugin_version=6,
    )
    existing = repository.add_plugin(
        "remote",
        "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt",
        "双星",
        enabled=False,
        plugin_version=6,
    )
    repository.update_plugin(
        existing.id,
        display_name="双星自定义",
        enabled=False,
        cached_file_path=existing.cached_file_path,
        last_loaded_at=existing.last_loaded_at,
        last_error=existing.last_error,
        config_text="token=keep\n",
        plugin_version=existing.plugin_version,
    )
    manager = SpiderPluginManager(repository, FakeLoader(), get=fake_get)

    result = manager.import_github_repository("https://github.com/har01d5/tvbox")

    plugins = repository.list_plugins()
    updated = next(
        plugin
        for plugin in plugins
        if plugin.source_value == "https://raw.githubusercontent.com/har01d5/tvbox/master/py/%E5%8F%8C%E6%98%9F.txt"
    )

    assert result == SpiderPluginImportResult(imported_count=0, updated_count=1, skipped_count=1)
    assert len(plugins) == 2
    assert updated.plugin_version == 7
    assert updated.enabled is False
    assert updated.display_name == "双星自定义"
    assert updated.config_text == "token=keep\n"
```

- [ ] **Step 2: Run the targeted manager tests to verify the behavior is missing**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "import_github_repository" -v
```

Expected: FAIL because `SpiderPluginManager` does not yet accept `get=...`, `SpiderPluginImportResult` / `SpiderPluginImportProgress` do not exist yet, and `plugin_version` is not persisted.

- [ ] **Step 3: Commit the red tests**

Run:

```bash
git add tests/test_spider_plugin_manager.py
git commit -m "test: cover github plugin repository import"
```

## Task 2: Add Versioned Plugin Persistence And Import Result Models

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/plugins/repository.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Add the minimal import/result and versioned config models**

In `src/atv_player/models.py`, update `SpiderPluginConfig` and add two new dataclasses after it:

```python
@dataclass(slots=True)
class SpiderPluginConfig:
    id: int = 0
    source_type: str = ""
    source_value: str = ""
    display_name: str = ""
    enabled: bool = True
    sort_order: int = 0
    cached_file_path: str = ""
    last_loaded_at: int = 0
    last_error: str = ""
    config_text: str = ""
    plugin_version: int = 1


@dataclass(slots=True)
class SpiderPluginImportProgress:
    stage: str
    current: int = 0
    total: int = 0
    message: str = ""


@dataclass(slots=True)
class SpiderPluginImportResult:
    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
```

- [ ] **Step 2: Migrate the repository schema and read/write the new field**

Update `src/atv_player/plugins/repository.py` so `_init_db()` and CRUD include `plugin_version`:

```python
            if "plugin_version" not in plugin_columns:
                conn.execute("ALTER TABLE spider_plugins ADD COLUMN plugin_version INTEGER NOT NULL DEFAULT 1")
```

Change `add_plugin(...)` to:

```python
    def add_plugin(
        self,
        source_type: str,
        source_value: str,
        display_name: str,
        *,
        enabled: bool = True,
        plugin_version: int = 1,
    ) -> SpiderPluginConfig:
        with self._connect() as conn:
            next_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM spider_plugins"
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO spider_plugins (
                    source_type, source_value, display_name, enabled, sort_order,
                    cached_file_path, last_loaded_at, last_error, config_text, plugin_version
                )
                VALUES (?, ?, ?, ?, ?, '', 0, '', '', ?)
                """,
                (source_type, source_value, display_name, int(enabled), next_order, int(plugin_version)),
            )
        return self.get_plugin(_require_lastrowid(cursor))
```

Update `SELECT` and `UPDATE` statements to include `plugin_version`, and add:

```python
    def find_plugin_by_source_value(self, source_value: str) -> SpiderPluginConfig | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_type, source_value, display_name, enabled, sort_order,
                       cached_file_path, last_loaded_at, last_error, config_text, plugin_version
                FROM spider_plugins
                WHERE source_value = ?
                """,
                (source_value,),
            ).fetchone()
        if row is None:
            return None
        values = list(row)
        values[4] = bool(values[4])
        values[10] = int(values[10])
        return SpiderPluginConfig(*values)
```

- [ ] **Step 3: Run the targeted tests to verify the model and repository changes satisfy the type contract**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "import_github_repository" -v
```

Expected: still FAIL, but the remaining failures should now be about missing manager import behavior rather than missing `plugin_version` fields.

- [ ] **Step 4: Commit the persistence changes**

Run:

```bash
git add src/atv_player/models.py src/atv_player/plugins/repository.py tests/test_spider_plugin_manager.py
git commit -m "feat: persist spider plugin versions"
```

## Task 3: Implement GitHub Repository Import In SpiderPluginManager

**Files:**
- Modify: `src/atv_player/plugins/__init__.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Add the manager constructor dependency and helper imports**

Expand the imports at the top of `src/atv_player/plugins/__init__.py`:

```python
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

import httpx

from atv_player.models import (
    SpiderPluginAction,
    SpiderPluginActionContext,
    SpiderPluginConfig,
    SpiderPluginImportProgress,
    SpiderPluginImportResult,
)
```

Update the constructor signature:

```python
    def __init__(
        self,
        repository: SpiderPluginRepository,
        loader: SpiderPluginLoader,
        playback_history_repository=None,
        *,
        get=httpx.get,
    ) -> None:
        self._repository = repository
        self._loader = loader
        self._playback_history_repository = playback_history_repository
        self._get = get
```

- [ ] **Step 2: Add narrow parsing and progress helpers**

Insert these helpers above `SpiderPluginManager`:

```python
_PLUGIN_VERSION_PATTERN = re.compile(r"^\s*//@version:(\d+)\s*$")


def _parse_github_repo(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ValueError("请输入 GitHub 仓库地址")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("请输入 GitHub 仓库地址")
    return parts[0], parts[1]


def _parse_plugin_version(source_text: str) -> int:
    for line in source_text.splitlines()[:16]:
        matched = _PLUGIN_VERSION_PATTERN.match(line)
        if matched:
            return int(matched.group(1))
    return 1


def _raw_github_url(owner: str, repo: str, branch: str, relative_path: str) -> str:
    encoded_parts = [quote(part) for part in PurePosixPath(relative_path).parts]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{'/'.join(encoded_parts)}"
```

Add a small callback helper inside `SpiderPluginManager`:

```python
    def _emit_import_progress(
        self,
        callback: Callable[[SpiderPluginImportProgress], None] | None,
        *,
        stage: str,
        current: int = 0,
        total: int = 0,
        message: str,
    ) -> None:
        if callback is None:
            return
        callback(
            SpiderPluginImportProgress(
                stage=stage,
                current=current,
                total=total,
                message=message,
            )
        )
```

- [ ] **Step 3: Implement default-branch lookup, manifest loading, and import rules**

Add these manager methods:

```python
    def _fetch_json(self, url: str) -> object:
        response = self._get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        return response.json()

    def _fetch_text(self, url: str) -> str:
        response = self._get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def _load_github_default_branch(self, owner: str, repo: str) -> str:
        payload = self._fetch_json(f"https://api.github.com/repos/{owner}/{repo}")
        if not isinstance(payload, dict) or not str(payload.get("default_branch") or "").strip():
            raise ValueError("无法解析仓库默认分支")
        return str(payload["default_branch"]).strip()

    def import_github_repository(
        self,
        repo_url: str,
        *,
        progress_callback: Callable[[SpiderPluginImportProgress], None] | None = None,
    ) -> SpiderPluginImportResult:
        owner, repo = _parse_github_repo(repo_url)
        self._emit_import_progress(progress_callback, stage="resolve_repo", message="正在解析仓库信息")
        default_branch = self._load_github_default_branch(owner, repo)
        self._emit_import_progress(progress_callback, stage="fetch_manifest", message="正在读取 spiders_v2.json")
        manifest = self._fetch_json(_raw_github_url(owner, repo, default_branch, "spiders_v2.json"))
        if not isinstance(manifest, list):
            raise ValueError("spiders_v2.json 格式无效")

        result = SpiderPluginImportResult()
        valid_entries = [entry for entry in manifest if isinstance(entry, dict) and str(entry.get("file") or "").strip()]
        total = len(valid_entries)
        for index, entry in enumerate(valid_entries, start=1):
            file_path = str(entry.get("file") or "").strip()
            self._emit_import_progress(
                progress_callback,
                stage="import_plugin",
                current=index,
                total=total,
                message=f"正在导入 {file_path}",
            )
            if PurePosixPath(file_path).is_absolute():
                result.skipped_count += 1
                continue
            source_url = _raw_github_url(owner, repo, default_branch, file_path)
            source_text = self._fetch_text(source_url)
            plugin_version = _parse_plugin_version(source_text)
            existing = self._repository.find_plugin_by_source_value(source_url)
            if existing is None:
                plugin = self._repository.add_plugin(
                    "remote",
                    source_url,
                    _default_plugin_name("remote", source_url),
                    enabled=bool(entry.get("valid", True)),
                    plugin_version=plugin_version,
                )
                self.refresh_plugin(plugin.id)
                result.imported_count += 1
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
            )
            self.refresh_plugin(existing.id)
            result.updated_count += 1
        return result
```

- [ ] **Step 4: Run the targeted manager import tests**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -k "import_github_repository" -v
```

Expected:

```text
PASSED tests/test_spider_plugin_manager.py::test_manager_import_github_repository_imports_manifest_plugins_and_disables_invalid_entries
PASSED tests/test_spider_plugin_manager.py::test_manager_import_github_repository_skips_same_version_and_updates_existing_version
```

- [ ] **Step 5: Run the full spider plugin manager test file**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py -q
```

Expected: PASS

- [ ] **Step 6: Commit the manager implementation**

Run:

```bash
git add src/atv_player/plugins/__init__.py src/atv_player/models.py src/atv_player/plugins/repository.py tests/test_spider_plugin_manager.py
git commit -m "feat: import spider plugins from github repos"
```

## Task 4: Add The Dialog Button, Progress UI, And Summary Messaging

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Write the failing dialog tests for GitHub import and progress**

In `tests/test_plugin_manager_dialog.py`, extend `FakePluginManager.__init__` with:

```python
        self.github_import_calls: list[str] = []
        self.progress_events: list[tuple[str, int, int, str]] = []
        self.github_import_result = SpiderPluginImportResult(imported_count=2, updated_count=1, skipped_count=3)
```

Add this method to `FakePluginManager`:

```python
    def import_github_repository(self, repo_url: str, *, progress_callback=None):
        self.github_import_calls.append(repo_url)
        if progress_callback is not None:
            for event in (
                SpiderPluginImportProgress(stage="resolve_repo", message="正在解析仓库信息"),
                SpiderPluginImportProgress(stage="fetch_manifest", message="正在读取 spiders_v2.json"),
                SpiderPluginImportProgress(stage="import_plugin", current=1, total=2, message="正在导入 py/a.txt"),
                SpiderPluginImportProgress(stage="import_plugin", current=2, total=2, message="正在导入 py/b.txt"),
            ):
                self.progress_events.append((event.stage, event.current, event.total, event.message))
                progress_callback(event)
        return self.github_import_result
```

Add these imports:

```python
from atv_player.models import (
    SpiderPluginAction,
    SpiderPluginConfig,
    SpiderPluginImportProgress,
    SpiderPluginImportResult,
    SpiderPluginLogEntry,
)
```

Add this test:

```python
def test_plugin_manager_dialog_imports_github_repository_with_progress_and_summary(qtbot, monkeypatch) -> None:
    manager = FakePluginManager()
    dialog = PluginManagerDialog(manager)
    qtbot.addWidget(dialog)
    dialog.show()

    progress_updates: list[tuple[int, int, str]] = []
    summary_messages: list[str] = []

    class FakeProgressDialog:
        def __init__(self, *args, **kwargs) -> None:
            self.values: list[int] = []
            self.maximums: list[int] = []
            self.labels: list[str] = []

        def setWindowTitle(self, title: str) -> None:
            pass

        def setMinimumDuration(self, duration: int) -> None:
            pass

        def setAutoClose(self, auto_close: bool) -> None:
            pass

        def setAutoReset(self, auto_reset: bool) -> None:
            pass

        def setRange(self, minimum: int, maximum: int) -> None:
            self.maximums.append(maximum)

        def setValue(self, value: int) -> None:
            self.values.append(value)

        def setLabelText(self, text: str) -> None:
            self.labels.append(text)
            progress_updates.append((self.values[-1] if self.values else 0, self.maximums[-1] if self.maximums else 0, text))

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QProgressDialog", FakeProgressDialog)
    monkeypatch.setattr(dialog, "_prompt_github_repo_url", lambda: "https://github.com/har01d5/tvbox")
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QMessageBox.information", lambda *args: summary_messages.append(args[2]))
    monkeypatch.setattr("atv_player.ui.plugin_manager_dialog.QApplication.processEvents", lambda: None)

    dialog._import_github_repository()

    assert manager.github_import_calls == ["https://github.com/har01d5/tvbox"]
    assert progress_updates[-1] == (2, 2, "正在导入 py/b.txt")
    assert summary_messages == ["导入完成：新增 2 个，更新 1 个，跳过 3 个。"]
```

- [ ] **Step 2: Run the targeted dialog test to verify the UI entry point is missing**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_imports_github_repository_with_progress_and_summary -q
```

Expected: FAIL because the dialog does not yet have a GitHub-import button, prompt helper, progress dialog wiring, or summary message.

- [ ] **Step 3: Implement the dialog prompt, progress mapping, and result summary**

Update the imports in `src/atv_player/ui/plugin_manager_dialog.py`:

```python
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
```

Add the new button in `__init__`:

```python
        self.import_github_button = QPushButton("从 GitHub 导入")
```

Insert it into the action-button row immediately after `self.add_remote_button`.

Add these helpers:

```python
    def _prompt_github_repo_url(self) -> str:
        value, accepted = QInputDialog.getText(self, "从 GitHub 导入", "GitHub 仓库 URL")
        return value.strip() if accepted else ""

    def _update_import_progress(self, dialog: QProgressDialog, event) -> None:
        maximum = max(event.total, 0)
        dialog.setRange(0, maximum)
        dialog.setValue(event.current if maximum else 0)
        dialog.setLabelText(event.message)
        QApplication.processEvents()
```

Add the import entry point:

```python
    def _import_github_repository(self) -> None:
        repo_url = self._prompt_github_repo_url()
        if not repo_url:
            return
        progress = QProgressDialog("", "", 0, 0, self)
        progress.setWindowTitle("从 GitHub 导入")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        try:
            result = self.plugin_manager.import_github_repository(
                repo_url,
                progress_callback=lambda event: self._update_import_progress(progress, event),
            )
        except Exception as exc:
            progress.close()
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        progress.close()
        self.reload_plugins()
        QMessageBox.information(
            self,
            "导入完成",
            f"导入完成：新增 {result.imported_count} 个，更新 {result.updated_count} 个，跳过 {result.skipped_count} 个。",
        )
```

Connect the button:

```python
        self.import_github_button.clicked.connect(self._import_github_repository)
```

- [ ] **Step 4: Run the targeted dialog test and then the full dialog test file**

Run:

```bash
uv run pytest tests/test_plugin_manager_dialog.py::test_plugin_manager_dialog_imports_github_repository_with_progress_and_summary -q
uv run pytest tests/test_plugin_manager_dialog.py -q
```

Expected: PASS

- [ ] **Step 5: Commit the dialog work**

Run:

```bash
git add src/atv_player/ui/plugin_manager_dialog.py tests/test_plugin_manager_dialog.py
git commit -m "feat: add github plugin import dialog flow"
```

## Task 5: Final Verification

**Files:**
- Test: `tests/test_spider_plugin_manager.py`
- Test: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
uv run pytest tests/test_spider_plugin_manager.py tests/test_plugin_manager_dialog.py -q
```

Expected: PASS

- [ ] **Step 2: Run a lightweight broader regression pass for plugin loading**

Run:

```bash
uv run pytest tests/test_spider_plugin_loader.py -q
```

Expected: PASS

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff --stat HEAD~3..HEAD
```

Expected: only the planned model, repository, manager, dialog, and test files are changed.

## Self-Review

- Spec coverage: the plan covers default-branch discovery, `spiders_v2.json` loading, source `//@version:` parsing with default `1`, `valid=false` default-disable behavior, same-version skip, version-update retention rules, and visible progress in the dialog.
- Placeholder scan: no `TODO`, `TBD`, or vague “handle errors” placeholders remain; each code-changing step includes concrete code or command content.
- Type consistency: `SpiderPluginConfig.plugin_version`, `SpiderPluginImportProgress`, and `SpiderPluginImportResult` are defined once and reused consistently across repository, manager, dialog, and tests.
