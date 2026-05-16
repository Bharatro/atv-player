# TMDB Season Overview Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make automatic metadata hydration prefer TMDB season overviews over `remote_douban`, while still allowing `local_douban` to override and keeping `remote_douban` as overview-only fallback.

**Architecture:** Keep the change local to the metadata merge layer. Introduce overview-specific provider ranking logic in `merge.py`, detect TMDB season records from `provider_id`, and lock the new behavior with hydrator-focused regression tests.

**Tech Stack:** Python, pytest, existing metadata hydration and merge helpers

---

## File Map

- Modify: `src/atv_player/metadata/merge.py`
  - Keep generic field-priority logic for non-overview fields.
  - Add overview-specific provider ranking helpers.
- Modify: `tests/test_metadata_hydrator.py`
  - Add regression coverage for TMDB season overviews vs `local_douban`, `douban`, and `remote_douban`.

### Task 1: Add a failing regression test for TMDB season overview priority

**Files:**
- Modify: `tests/test_metadata_hydrator.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing test**

```python
def test_metadata_hydrator_prefers_tmdb_season_over_remote_douban_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    remote_douban = FakeProvider(
        "remote_douban",
        matches=[MetadataMatch(provider="remote_douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="remote_douban",
            provider_id="357",
            overview="本地豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, remote_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "第五季简介"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "prefers_tmdb_season_over_remote_douban_overview" -q`

Expected: `FAIL` because `remote_douban` still overrides the TMDB season overview.

- [ ] **Step 3: Write minimal implementation**

```python
def _is_tmdb_season_record(record: MetadataRecord) -> bool:
    return record.provider == "tmdb" and ":season:" in str(record.provider_id or "")


def _overview_provider_rank(record: MetadataRecord) -> int:
    if record.provider == "local_douban":
        return 0
    if _is_tmdb_season_record(record):
        return 1
    if record.provider == "douban":
        return 2
    if record.provider == "remote_douban":
        return 3
    if record.provider == "tmdb":
        return 4
    return 5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "prefers_tmdb_season_over_remote_douban_overview" -q`

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_hydrator.py src/atv_player/metadata/merge.py
git commit -m "fix: prefer tmdb season overview over remote douban"
```

### Task 2: Preserve local Douban override and remote Douban fallback semantics

**Files:**
- Modify: `tests/test_metadata_hydrator.py`
- Modify: `src/atv_player/metadata/merge.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_metadata_hydrator_local_douban_overrides_tmdb_season_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="357",
            overview="豆瓣官方简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "豆瓣官方简介"


def test_metadata_hydrator_douban_overrides_remote_douban_but_not_tmdb_season_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:5", title="黑袍纠察队", year="2019")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="tv:42:season:5",
            overview="第五季简介",
        ),
    )
    douban = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="357", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="douban",
            provider_id="357",
            overview="豆瓣简介",
        ),
    )
    remote_douban = FakeProvider(
        "remote_douban",
        matches=[MetadataMatch(provider="remote_douban", provider_id="358", title="黑袍纠察队")],
        record=MetadataRecord(
            provider="remote_douban",
            provider_id="358",
            overview="本地豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[remote_douban, tmdb, douban])

    updated = hydrator.hydrate(
        MetadataContext(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            source_kind="browse",
        )
    )

    assert updated.vod_content == "第五季简介"
```

- [ ] **Step 2: Run tests to verify current behavior fails where expected**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "tmdb_season_overview or douban_overrides_remote_douban" -q`

Expected: at least one `FAIL` before the implementation is complete.

- [ ] **Step 3: Finish minimal implementation in `merge.py`**

```python
def _can_override_overview(vod: VodItem, record: MetadataRecord) -> bool:
    current = vod.metadata_field_sources.get("overview", "")
    if not current:
        return True
    current_record = MetadataRecord(provider=current, provider_id=vod.metadata_field_source_ids.get("overview", ""))
    return _overview_provider_rank(record) <= _overview_provider_rank(current_record)
```

Then wire `merge_metadata_record()` to use `_can_override_overview(...)` for `overview` instead of `_can_override(...)`, while continuing to use the generic path for all other fields.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "tmdb_season_overview or douban_overrides_remote_douban" -q`

Expected: all selected tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_hydrator.py src/atv_player/metadata/merge.py
git commit -m "fix: refine overview metadata priority"
```

### Task 3: Run regression verification

**Files:**
- Modify: `src/atv_player/metadata/merge.py`
- Modify: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Run the full hydrator test file**

Run: `uv run pytest tests/test_metadata_hydrator.py -q`

Expected: all tests pass

- [ ] **Step 2: Run adjacent metadata regression tests**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py tests/test_metadata_scrape_service.py tests/test_player_window_ui.py -k "metadata_scrape or metadata_hydrator" -q`

Expected: all selected tests pass

- [ ] **Step 3: Review diff for unintended scope**

Run: `git diff -- src/atv_player/metadata/merge.py tests/test_metadata_hydrator.py`

Expected: diff only changes overview priority logic and matching regression tests.

