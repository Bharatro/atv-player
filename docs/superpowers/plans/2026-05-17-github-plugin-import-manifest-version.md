# GitHub Plugin Import Manifest Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change GitHub plugin import so plugin versions come from `spiders_v2.json[].version`, and skip plugins whose imported version has not changed.

**Architecture:** Keep the behavior change isolated to `SpiderPluginManager.import_github_repository(...)`. Reuse existing repository persistence and UI flow; only adjust manager parsing, version comparison, and tests so GitHub import no longer reads source `//@version:` markers.

**Tech Stack:** Python 3.13, httpx, pytest, sqlite-backed plugin repository

---

## File Structure

- Modify: `src/atv_player/plugins/__init__.py`
  Replace source-version parsing in GitHub import with manifest-version parsing and invalid-version skip logic.
- Modify: `tests/test_spider_plugin_manager.py`
  Update manager tests to assert manifest-driven version persistence, unchanged-version skip, and invalid-version skip.

### Task 1: Write Failing Manager Tests

**Files:**
- Modify: `tests/test_spider_plugin_manager.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Write the failing tests**

Add or update tests so they assert:

```python
assert [plugin.plugin_version for plugin in plugins] == [8, 3, 5]
assert result == SpiderPluginImportResult(imported_count=3, updated_count=0, skipped_count=0)
```

and:

```python
assert result == SpiderPluginImportResult(imported_count=0, updated_count=1, skipped_count=1)
assert updated.plugin_version == 9
```

plus an invalid-version skip case:

```python
assert result == SpiderPluginImportResult(imported_count=0, updated_count=0, skipped_count=1)
assert repository.list_plugins() == []
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_manager.py -k "import_github_repository" -v`
Expected: FAIL because the manager still parses `//@version:` from source text.

### Task 2: Implement Manifest Version Parsing

**Files:**
- Modify: `src/atv_player/plugins/__init__.py`
- Test: `tests/test_spider_plugin_manager.py`

- [ ] **Step 1: Add minimal manifest-version parsing**

Implement a helper like:

```python
def _parse_manifest_plugin_version(entry: object) -> int | None:
    if not isinstance(entry, dict):
        return None
    try:
        value = int(entry.get("version"))
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None
```

- [ ] **Step 2: Use manifest version during import**

Update `import_github_repository(...)` so it:

```python
plugin_version = _parse_manifest_plugin_version(entry)
if plugin_version is None:
    result.skipped_count += 1
    continue
source_text = self._fetch_text(source_url)
existing = self._repository.find_plugin_by_source_value(source_url)
```

and no longer reads source `//@version:` for GitHub imports.

- [ ] **Step 3: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/test_spider_plugin_manager.py -k "import_github_repository" -v`
Expected: PASS

## Self-Review

- Spec coverage: plan covers manifest version parsing, unchanged-version skip, invalid-version skip, and version-update retention.
- Placeholder scan: no TODO/TBD placeholders remain.
- Type consistency: helper returns `int | None`, matching import-loop branching.
