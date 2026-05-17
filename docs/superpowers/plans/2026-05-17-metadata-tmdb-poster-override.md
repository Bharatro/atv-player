# Metadata TMDB Poster Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let automatic metadata hydration keep existing overview/rating behavior while still allowing a later TMDB record to override an already-populated poster.

**Architecture:** Keep the change local to the metadata merge and hydrator layers. Add one shared poster-only override helper in `merge.py`, call it after `fill_missing_metadata_record()` for non-primary hydration results, and lock the behavior with focused hydrator and scrape regression tests.

**Tech Stack:** Python, pytest, existing metadata hydration/merge helpers

---

## File Map

- Modify: `src/atv_player/metadata/merge.py`
  - Keep existing full-merge and fill-missing responsibilities.
  - Add a poster-only helper that reuses the current provider priority table instead of inventing new ranking rules.
- Modify: `src/atv_player/metadata/hydrator.py`
  - Keep primary-provider merge behavior unchanged.
  - Call the new poster override helper after `fill_missing_metadata_record()` for later compatible records.
- Modify: `tests/test_metadata_hydrator.py`
  - Add focused regression coverage for “official_douban first, TMDB later” and “TMDB first, lower-priority later” poster behavior.
- Modify: `tests/test_metadata_scrape_service.py`
  - Add a regression test proving manual scrape `apply()` still replaces poster/overview/metadata fields exactly as before.

### Task 1: Lock the desired auto-hydration poster behavior with failing tests

**Files:**
- Modify: `tests/test_metadata_hydrator.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing tests**

Add these tests near the existing hydrator coverage around `test_metadata_hydrator_keeps_official_douban_overview_but_uses_tmdb_visual_fields(...)`:

```python
def test_metadata_hydrator_later_tmdb_overrides_existing_official_douban_poster(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    official_douban = FakeProvider(
        "official_douban",
        matches=[MetadataMatch(provider="official_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="official_douban",
            provider_id="35746415",
            poster="https://img.example/douban-poster.jpg",
            overview="豆瓣简介",
            rating="8.1",
        ),
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:42",
            poster="https://img.example/tmdb-hd-poster.jpg",
            overview="TMDB简介",
            rating="7.2",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[official_douban, tmdb])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-hd-poster.jpg"
    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"
    assert updated.metadata_field_sources["poster"] == "tmdb"


def test_metadata_hydrator_later_lower_priority_provider_does_not_override_tmdb_poster(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸")],
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:42",
            poster="https://img.example/tmdb-hd-poster.jpg",
            overview="TMDB简介",
        ),
    )
    local_douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(
            provider="local_douban",
            provider_id="35746415",
            poster="https://img.example/douban-small-poster.jpg",
            overview="豆瓣简介",
        ),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, local_douban])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_pic == "https://img.example/tmdb-hd-poster.jpg"
    assert updated.metadata_field_sources["poster"] == "tmdb"
```

- [ ] **Step 2: Run the focused tests to verify red**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "later_tmdb_overrides_existing_official_douban_poster or later_lower_priority_provider_does_not_override_tmdb_poster" -q`

Expected: first test `FAIL` because the later TMDB record currently only goes through `fill_missing_metadata_record()` and cannot replace an existing poster.

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/test_metadata_hydrator.py
git commit -m "test: cover tmdb poster override during hydration"
```

### Task 2: Add a poster-only override helper and wire it into hydration

**Files:**
- Modify: `src/atv_player/metadata/merge.py`
- Modify: `src/atv_player/metadata/hydrator.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the minimal merge-layer helper**

In `src/atv_player/metadata/merge.py`, add this helper after `fill_missing_metadata_record(...)`:

```python
def override_visual_metadata_record(vod: VodItem, record: MetadataRecord) -> VodItem:
    if record.poster and (not vod.vod_pic or _can_override(vod, "poster", record.provider)):
        vod.vod_pic = record.poster
        _set_field_source(vod, "poster", record.provider)
    return vod
```

Do not move overview/rating/year logic into this helper. This function is poster-only for this change.

- [ ] **Step 2: Run the focused tests to verify they still fail for the right reason**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "later_tmdb_overrides_existing_official_douban_poster or later_lower_priority_provider_does_not_override_tmdb_poster" -q`

Expected: still `FAIL`, because nothing calls the new helper yet.

- [ ] **Step 3: Wire the helper into later hydration records**

Update the imports in `src/atv_player/metadata/hydrator.py`:

```python
from atv_player.metadata.merge import (
    fill_missing_metadata_record,
    merge_metadata_record,
    override_visual_metadata_record,
)
```

Then update the non-primary branch inside `MetadataHydrator.hydrate(...)` from:

```python
            fill_missing_metadata_record(vod, record)
```

to:

```python
            fill_missing_metadata_record(vod, record)
            override_visual_metadata_record(vod, record)
```

Keep the primary branch unchanged:

```python
            if not primary_applied:
                merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
                primary_applied = True
                primary_kind = _record_media_kind(record) or _match_media_kind(match) or _vod_media_kind(vod)
                continue
```

- [ ] **Step 4: Run the focused tests to verify green**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "later_tmdb_overrides_existing_official_douban_poster or later_lower_priority_provider_does_not_override_tmdb_poster" -q`

Expected: `2 passed`

- [ ] **Step 5: Run the adjacent existing hydrator regression**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "keeps_official_douban_overview_but_uses_tmdb_visual_fields" -q`

Expected: `1 passed`, confirming overview/rating behavior stayed intact.

- [ ] **Step 6: Commit the implementation**

```bash
git add src/atv_player/metadata/merge.py src/atv_player/metadata/hydrator.py tests/test_metadata_hydrator.py
git commit -m "fix: allow tmdb poster override during hydration"
```

### Task 3: Prove manual scrape apply semantics did not change and run regressions

**Files:**
- Modify: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Add a manual-apply regression test**

Append this test near `test_metadata_scrape_service_apply_replaces_all_metadata_fields_from_selected_result(...)`:

```python
def test_metadata_scrape_service_apply_still_replaces_poster_even_after_hydration_override_change(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(
            provider="tmdb",
            provider_id="movie:1",
            title="新标题",
            poster="https://img.example/tmdb-poster.jpg",
            overview="新简介",
            rating="7.8",
        ),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.apply(
        VodItem(
            vod_id="v1",
            vod_name="旧标题",
            vod_pic="https://img.example/old-poster.jpg",
            vod_content="旧简介",
            vod_remarks="9.9",
            metadata_field_sources={
                "poster": "local_douban",
                "overview": "local_douban",
                "rating": "local_douban",
            },
        ),
        MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id="movie:1",
            title="新标题",
            year="2026",
        ),
    )

    assert updated.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert updated.vod_content == "新简介"
    assert updated.vod_remarks == "7.8"
    assert updated.metadata_field_sources["poster"] == "tmdb"
    assert updated.metadata_field_sources["overview"] == "tmdb"
    assert updated.metadata_field_sources["rating"] == "tmdb"
```

- [ ] **Step 2: Run the scrape regression test to verify green**

Run: `uv run pytest tests/test_metadata_scrape_service.py -k "apply_still_replaces_poster_even_after_hydration_override_change or apply_replaces_all_metadata_fields_from_selected_result" -q`

Expected: `2 passed`

- [ ] **Step 3: Run the full targeted regression set**

Run: `uv run pytest tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py -q`

Expected: all tests pass.

- [ ] **Step 4: Review the final diff for scope control**

Run: `git diff -- src/atv_player/metadata/merge.py src/atv_player/metadata/hydrator.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py`

Expected: diff only adds one poster override helper, one hydrator call site, and regression tests.

- [ ] **Step 5: Commit the regression lock if Task 3 introduced new test changes after Task 2**

```bash
git add tests/test_metadata_scrape_service.py tests/test_metadata_hydrator.py
git commit -m "test: lock metadata poster override regressions"
```
