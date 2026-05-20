# Metadata Original Detail Match Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let metadata auto-match scoring use original-detail base fields `vod_area`, `vod_lang`, `vod_director`, and `vod_actor` as soft ranking signals without adding extra detail requests.

**Architecture:** Extend `MetadataQuery` so the existing `MetadataContext.to_query()` carries original base fields into the search phase. Keep all ranking logic centralized in `metadata.matching.score_match(...)`, where provider search `raw` payloads are normalized into comparable area/language/director/actor tokens and used for small additive bonuses that cannot override strong title/year conflicts.

**Tech Stack:** Python 3, dataclasses, pytest

---

## File Map

- Modify: `src/atv_player/metadata/models.py`
  - Add the new original-detail fields to `MetadataQuery` and populate them from `MetadataContext.to_query()`.
- Modify: `src/atv_player/metadata/matching.py`
  - Normalize query-side and match-side base fields and apply soft ranking bonuses inside `score_match(...)`.
- Modify: `tests/test_metadata_matching.py`
  - Add focused ranking regressions for area, language, director, and actor bonuses.
- Modify: `tests/test_app.py`
  - Add one query-mapping test proving `MetadataContext.to_query()` carries the new base fields.

### Task 1: Add Original Base Fields To Match Scoring

**Files:**
- Modify: `tests/test_app.py`
- Modify: `tests/test_metadata_matching.py`
- Modify: `src/atv_player/metadata/models.py`
- Modify: `src/atv_player/metadata/matching.py`

- [ ] **Step 1: Write the failing tests**

Add one `MetadataContext.to_query()` mapping test in `tests/test_app.py` near the other metadata-context/query coverage:

```python
def test_metadata_context_to_query_includes_original_base_match_fields() -> None:
    vod = VodItem(
        vod_id="vod-1",
        vod_name="深空彼岸",
        vod_year="2026",
        vod_area="中国大陆",
        vod_lang="汉语普通话",
        vod_director="周琛,赵禹晴",
        vod_actor="梁达伟,唐雅菁",
        category_name="动漫",
    )

    query = MetadataContext(vod=vod, source_kind="spider").to_query()

    assert query.vod_area == "中国大陆"
    assert query.vod_lang == "汉语普通话"
    assert query.vod_director == "周琛,赵禹晴"
    assert query.vod_actor == "梁达伟,唐雅菁"
```

Add focused scoring tests in `tests/test_metadata_matching.py`:

```python
def test_score_match_prefers_matching_area_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_area="中国大陆")

    matched_area = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"country": "中国大陆"},
    )
    mismatched_area = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"country": "日本"},
    )

    assert score_match(query, matched_area) > score_match(query, mismatched_area)


def test_score_match_prefers_matching_language_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_lang="汉语普通话")

    matched_language = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="深空彼岸",
        year="2026",
        raw={"language": {"value": "汉语普通话"}},
    )
    mismatched_language = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:2",
        title="深空彼岸",
        year="2026",
        raw={"language": {"value": "日语"}},
    )

    assert score_match(query, matched_language) > score_match(query, mismatched_language)


def test_score_match_prefers_matching_director_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_director="周琛,赵禹晴")

    matched_director = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"directors": ["周琛", "其他导演"]},
    )
    mismatched_director = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"directors": ["无关导演"]},
    )

    assert score_match(query, matched_director) > score_match(query, mismatched_director)


def test_score_match_prefers_matching_actor_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_actor="梁达伟,唐雅菁")

    matched_actor = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"actors": ["梁达伟", "其他演员"]},
    )
    mismatched_actor = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"actors": ["无关演员"]},
    )

    assert score_match(query, matched_actor) > score_match(query, mismatched_actor)
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
/home/harold/.local/bin/uv run pytest \
  tests/test_app.py::test_metadata_context_to_query_includes_original_base_match_fields \
  tests/test_metadata_matching.py -k "matching_area or matching_language or matching_director or matching_actor" -v
```

Expected:

```text
FAILED tests/test_app.py::test_metadata_context_to_query_includes_original_base_match_fields
FAILED tests/test_metadata_matching.py::test_score_match_prefers_matching_area_when_title_and_year_are_same
FAILED tests/test_metadata_matching.py::test_score_match_prefers_matching_language_when_title_and_year_are_same
FAILED tests/test_metadata_matching.py::test_score_match_prefers_matching_director_when_title_and_year_are_same
FAILED tests/test_metadata_matching.py::test_score_match_prefers_matching_actor_when_title_and_year_are_same
```

The failures should show that `MetadataQuery` does not yet expose these fields and `score_match(...)` does not use them.

- [ ] **Step 3: Write the minimal implementation**

Extend `MetadataQuery` in `src/atv_player/metadata/models.py`:

```python
@dataclass(slots=True)
class MetadataQuery:
    title: str
    year: str = ""
    source_kind: str = ""
    source_key: str = ""
    vod_id: str = ""
    vod_dbid: int = 0
    type_name: str = ""
    category_name: str = ""
    vod_area: str = ""
    vod_lang: str = ""
    vod_director: str = ""
    vod_actor: str = ""
```

Update `MetadataContext.to_query()` to pass the source `VodItem` base fields through unchanged:

```python
return MetadataQuery(
    title=title,
    year=year,
    source_kind=self.source_kind,
    source_key=self.source_key,
    vod_id=(self.vod.vod_id or "").strip(),
    vod_dbid=int(self.vod.dbid or 0),
    type_name=(self.vod.type_name or "").strip(),
    category_name=category_name,
    vod_area=(self.vod.vod_area or "").strip(),
    vod_lang=(self.vod.vod_lang or "").strip(),
    vod_director=(self.vod.vod_director or "").strip(),
    vod_actor=(self.vod.vod_actor or "").strip(),
)
```

In `src/atv_player/metadata/matching.py`, add small shared helpers for tokenization and soft bonuses:

```python
_AREA_MATCH_BONUS = 0.03
_LANGUAGE_MATCH_BONUS = 0.03
_DIRECTOR_MATCH_BONUS = 0.05
_ACTOR_MATCH_BONUS = 0.04
```

```python
def _person_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    for token in _category_tokens(value):
        normalized = normalize_match_title(token)
        if normalized:
            tokens.add(normalized)
    return tokens


def _raw_people_tokens(raw: Mapping[str, object], *keys: str) -> set[str]:
    tokens: set[str] = set()
    for key in keys:
        tokens.update(_person_tokens(raw.get(key)))
    return tokens


def _text_value_tokens(value: object) -> set[str]:
    return {normalize_match_title(token) for token in _category_tokens(value) if normalize_match_title(token)}
```

Then apply the bonuses inside `score_match(...)` after year/category scoring and before provider exact-match bonuses:

```python
    score += _category_score(query.category_name, query.type_name, match.raw)
    score += _original_detail_field_score(query, match.raw)
```

Implement `_original_detail_field_score(...)` as additive-only:

```python
def _original_detail_field_score(query: MetadataQuery, raw: Mapping[str, object]) -> float:
    score = 0.0

    query_area = _text_value_tokens(query.vod_area)
    match_area = _text_value_tokens(raw.get("country")) | _text_value_tokens(raw.get("region"))
    if query_area and match_area and query_area & match_area:
        score += _AREA_MATCH_BONUS

    query_lang = _text_value_tokens(query.vod_lang)
    match_lang = _text_value_tokens(raw.get("language"))
    if query_lang and match_lang and query_lang & match_lang:
        score += _LANGUAGE_MATCH_BONUS

    query_directors = _person_tokens(query.vod_director)
    match_directors = _raw_people_tokens(raw, "directors")
    if query_directors and match_directors and query_directors & match_directors:
        score += _DIRECTOR_MATCH_BONUS

    query_actors = _person_tokens(query.vod_actor)
    match_actors = _raw_people_tokens(raw, "actors", "cast")
    if query_actors and match_actors and query_actors & match_actors:
        score += _ACTOR_MATCH_BONUS

    return score
```

Keep the new bonuses small enough that the existing year-conflict penalty and exact-title logic still dominate bad candidates.

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:

```bash
/home/harold/.local/bin/uv run pytest \
  tests/test_app.py::test_metadata_context_to_query_includes_original_base_match_fields \
  tests/test_metadata_matching.py -k "matching_area or matching_language or matching_director or matching_actor" -v
```

Expected:

```text
PASSED tests/test_app.py::test_metadata_context_to_query_includes_original_base_match_fields
PASSED tests/test_metadata_matching.py::test_score_match_prefers_matching_area_when_title_and_year_are_same
PASSED tests/test_metadata_matching.py::test_score_match_prefers_matching_language_when_title_and_year_are_same
PASSED tests/test_metadata_matching.py::test_score_match_prefers_matching_director_when_title_and_year_are_same
PASSED tests/test_metadata_matching.py::test_score_match_prefers_matching_actor_when_title_and_year_are_same
```

- [ ] **Step 5: Run the broader matching regressions**

Run:

```bash
/home/harold/.local/bin/uv run pytest tests/test_metadata_matching.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py -v
```

Expected:

```text
PASSED tests/test_metadata_matching.py::test_score_match_boosts_synonymous_category_match
PASSED tests/test_metadata_matching.py::test_score_match_rejects_large_year_conflict_even_for_exact_title
PASSED tests/test_metadata_tencent_provider.py::test_tencent_metadata_provider_search_prefers_category_matched_result_for_same_title
PASSED tests/test_metadata_iqiyi_provider.py::test_iqiyi_metadata_provider_search_prefers_category_matched_result_for_same_title
```

No existing matching behavior should regress; the new field bonuses should only break ties among already-plausible candidates.

- [ ] **Step 6: Commit**

```bash
git add tests/test_app.py tests/test_metadata_matching.py src/atv_player/metadata/models.py src/atv_player/metadata/matching.py
git commit -m "feat: score metadata matches with original base fields"
```

## Coverage Check

- Spec section `Extend MetadataQuery` is covered by Task 1 through the `MetadataQuery` field additions and the `MetadataContext.to_query()` mapping test.
- Spec section `Populate query from original detail` is covered by the new `tests/test_app.py` mapping regression.
- Spec section `Candidate-side field extraction` is covered by Task 1 through `_text_value_tokens(...)`, `_person_tokens(...)`, and `_raw_people_tokens(...)`.
- Spec section `Scoring rules` is covered by Task 1 through the four additive field bonuses with explicitly small weights.
- Spec section `Testing` is covered by Task 1 through the focused query/scoring tests plus the broader provider regressions.

## Placeholder Scan

- No `TODO`, `TBD`, or deferred placeholders remain.
- Every code-changing step includes exact files, code, commands, and expected results.
- All symbols used later in the task are defined earlier in the task.
