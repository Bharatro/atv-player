# TMDB Rating One Decimal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize TMDB `vote_average` to a one-decimal string at write time so all downstream metadata consumers store and display a consistent TMDB rating value.

**Architecture:** Keep the rule local to `TMDBProvider` by introducing a tiny helper that converts raw TMDB score payloads into the canonical `MetadataRecord.rating` string. Cover both direct provider output and one downstream following-metadata path so the change is proven at the source and at a consumer boundary.

**Tech Stack:** Python 3.12, pytest, existing metadata provider/following metadata test suites

---

## File Map

- Modify: `src/atv_player/metadata/providers/tmdb.py`
  - Add a small TMDB-only rating formatter near existing helper functions.
  - Use it in both `TMDBProvider.get_detail()` and `TMDBProvider.get_detail_full()`.
- Modify: `tests/test_metadata_tmdb_provider.py`
  - Add provider-level regression tests for integer, multi-decimal, and invalid TMDB ratings.
- Modify: `tests/test_following_metadata.py`
  - Update one downstream assertion to prove the normalized TMDB rating propagates into following records.

## Task 1: Lock In Failing Rating Precision Tests

**Files:**
- Modify: `tests/test_metadata_tmdb_provider.py`
- Modify: `tests/test_following_metadata.py`

- [ ] **Step 1: Write the failing TMDB provider precision tests**

Add these tests near the existing `get_detail` / `get_detail_full` coverage in `tests/test_metadata_tmdb_provider.py`:

```python
def test_tmdb_provider_get_detail_formats_vote_average_to_one_decimal() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "仙逆",
        "overview": "简介",
        "first_air_date": "2023-01-01",
        "vote_average": 8,
        "genres": [{"name": "动画"}],
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:1",
            title="仙逆",
        )
    )

    assert record.rating == "8.0"


def test_tmdb_provider_get_detail_full_formats_vote_average_to_one_decimal() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 272432,
        "name": "低智商犯罪",
        "overview": "剧集简介",
        "first_air_date": "2026-05-04",
        "vote_average": 7.66,
        "genres": [{"name": "犯罪"}],
        "credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    client.tv_season_detail = {
        "season_number": 1,
        "overview": "第一季简介",
        "episodes": [],
    }
    provider = TMDBProvider(client)

    record = provider.get_detail_full(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:272432:season:1",
            title="低智商犯罪",
        )
    )

    assert record.rating == "7.7"


def test_tmdb_provider_get_detail_returns_empty_rating_for_invalid_vote_average() -> None:
    client = FakeTMDBClient()
    client.tv_detail = {
        "id": 42,
        "name": "仙逆",
        "overview": "简介",
        "first_air_date": "2023-01-01",
        "vote_average": "not-a-number",
        "genres": [{"name": "动画"}],
        "aggregate_credits": {},
        "alternative_titles": {"results": []},
        "external_ids": {},
    }
    provider = TMDBProvider(client)

    record = provider.get_detail(
        MetadataMatch(
            provider="tmdb",
            provider_id="tv:42:season:1",
            title="仙逆",
        )
    )

    assert record.rating == ""
```

Update the TMDB contribution in `tests/test_following_metadata.py` so the downstream expectation also reflects canonical formatting:

```python
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:315088:season:1",
                title="盗妖行",
                poster="tmdb-poster",
                backdrop="tmdb-backdrop",
                rating="7.66",
                tmdb_id="315088",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集", "still_url": "still"}],
                    }
                ],
            )
```

And change the assertion:

```python
    assert record.rating == "7.7"
```

- [ ] **Step 2: Run the focused tests to verify they fail for the right reason**

Run:

```bash
uv run pytest tests/test_metadata_tmdb_provider.py -k "formats_vote_average or invalid_vote_average" -v
uv run pytest tests/test_following_metadata.py -k "selected_iqiyi_candidate_enriches_with_tmdb_metadata" -v
```

Expected:

- The new TMDB provider tests fail because the current code returns `"8"` / `"7.66"` instead of one-decimal strings.
- The following metadata test fails because it still propagates the unnormalized TMDB rating.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_metadata_tmdb_provider.py tests/test_following_metadata.py
git commit -m "test: cover tmdb rating precision"
```

## Task 2: Implement TMDB-Only Rating Normalization

**Files:**
- Modify: `src/atv_player/metadata/providers/tmdb.py`
- Test: `tests/test_metadata_tmdb_provider.py`
- Test: `tests/test_following_metadata.py`

- [ ] **Step 1: Add the minimal TMDB rating formatter**

Insert this helper near the other private helpers in `src/atv_player/metadata/providers/tmdb.py`, for example after `_best_backdrop_urls(...)`:

```python
def _format_tmdb_rating(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        normalized = round(float(text), 1)
    except (TypeError, ValueError):
        return ""
    return f"{normalized:.1f}"
```

- [ ] **Step 2: Use the formatter in both detail write paths**

Replace the direct `vote_average` string conversion in `TMDBProvider.get_detail()` and `TMDBProvider.get_detail_full()`:

```python
            rating=_format_tmdb_rating(payload.get("vote_average")),
```

This should replace both existing lines that currently read:

```python
            rating=str(payload.get("vote_average") or "").strip(),
```

- [ ] **Step 3: Run focused tests to verify the implementation passes**

Run:

```bash
uv run pytest tests/test_metadata_tmdb_provider.py -k "formats_vote_average or invalid_vote_average" -v
uv run pytest tests/test_following_metadata.py -k "selected_iqiyi_candidate_enriches_with_tmdb_metadata" -v
```

Expected:

- All selected tests PASS.
- The TMDB provider now returns `"8.0"`, `"7.7"`, and `""` for the three covered cases.

- [ ] **Step 4: Run the broader regression slice**

Run:

```bash
uv run pytest tests/test_metadata_tmdb_provider.py tests/test_following_metadata.py -v
```

Expected:

- Full targeted suite PASS with no TMDB provider regressions.

- [ ] **Step 5: Commit the implementation**

```bash
git add src/atv_player/metadata/providers/tmdb.py tests/test_metadata_tmdb_provider.py tests/test_following_metadata.py
git commit -m "fix: normalize tmdb rating precision"
```

## Self-Review

- Spec coverage: The plan covers TMDB-only write-time normalization, both provider write paths, invalid input handling, and one downstream propagation check.
- Placeholder scan: No `TODO`/`TBD` placeholders remain; every code-changing step includes concrete snippets and exact commands.
- Type consistency: The plan uses the existing `MetadataRecord.rating: str` contract and only adds a local helper returning `str`.
