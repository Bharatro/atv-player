# Plugin Partial Update Race Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the read-modify-write race from plugin rename, enable-toggle, and config-text updates by switching them to single-statement partial updates.

**Architecture:** Keep full-row `update_plugin()` for refresh/import flows that intentionally rewrite multiple persisted fields. Add focused repository update methods for `display_name`, `enabled`, and `config_text`, then route the three manager entrypoints through those methods so concurrent calls only touch their target column.

**Tech Stack:** Python, sqlite3, pytest

---

### Task 1: Add a regression test for non-overwriting partial updates

**Files:**
- Modify: `tests/test_storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
def test_spider_plugin_repository_partial_updates_do_not_overwrite_other_fields(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin = repo.add_plugin("local", "/plugins/demo.py", "原名称")

    repo.set_plugin_enabled(plugin.id, False)
    repo.set_plugin_config(plugin.id, "token=updated")
    repo.rename_plugin(plugin.id, "新名称")

    updated = repo.get_plugin(plugin.id)

    assert updated.display_name == "新名称"
    assert updated.enabled is False
    assert updated.config_text == "token=updated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py::test_spider_plugin_repository_partial_updates_do_not_overwrite_other_fields -q`
Expected: FAIL with `AttributeError` because the focused repository update methods do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def rename_plugin(self, plugin_id: int, display_name: str) -> None:
    ...

def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
    ...

def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_storage.py::test_spider_plugin_repository_partial_updates_do_not_overwrite_other_fields -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/atv_player/plugins/repository.py src/atv_player/plugins/__init__.py docs/superpowers/plans/2026-05-19-plugin-partial-update-race.md
git commit -m "fix: avoid spider plugin partial update races"
```

### Task 2: Route manager writes through focused repository methods

**Files:**
- Modify: `src/atv_player/plugins/__init__.py`
- Test: `tests/test_plugin_actions.py`

- [ ] **Step 1: Write the failing test**

```python
def test_plugin_actions_toggle_uses_inverse_enabled_state() -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)

    result = actions.toggle_plugin_enabled(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.toggle_calls == [(1, False)]
```
Existing UI tests already cover the manager interface shape; the regression focus remains in repository tests, so no new failing UI test is required here.

- [ ] **Step 2: Run targeted tests to verify existing behavior still holds**

Run: `uv run pytest tests/test_plugin_actions.py -q`
Expected: PASS before and after the manager wiring change.

- [ ] **Step 3: Write minimal implementation**

```python
def rename_plugin(self, plugin_id: int, display_name: str) -> None:
    self._repository.rename_plugin(plugin_id, display_name)

def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
    self._repository.set_plugin_enabled(plugin_id, enabled)

def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
    self._repository.set_plugin_config(plugin_id, config_text)
```

- [ ] **Step 4: Run tests to verify it passes**

Run: `uv run pytest tests/test_storage.py::test_spider_plugin_repository_partial_updates_do_not_overwrite_other_fields tests/test_plugin_actions.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py tests/test_plugin_actions.py src/atv_player/plugins/repository.py src/atv_player/plugins/__init__.py docs/superpowers/plans/2026-05-19-plugin-partial-update-race.md
git commit -m "fix: use partial plugin updates for manager writes"
```
