# IQIYI Episode Title Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `iqiyi` outrank `tmdb` for episode-title rewriting only when the series can be confidently identified as an IQIYI series, and apply that behavior consistently in both the manual scrape flow and the automatic episode-title enhancer.

**Architecture:** Keep the confidence gate and dynamic source-priority calculation in `src/atv_player/metadata/episode_title_resolver.py`, because that module already owns episode-title rewrite eligibility and provider-to-playlist mapping. `src/atv_player/metadata/scrape.py` and `src/atv_player/app.py` should delegate to those helpers instead of duplicating IQIYI detection logic. Tests land in resolver, scrape-service, and app-coordinator suites so the shared rule is locked from all entry points.

**Tech Stack:** Python, pytest, dataclasses, existing metadata providers and caches

---

### Task 1: Lock the IQIYI confidence gate and dynamic source priority in the resolver

**Files:**
- Modify: `tests/test_metadata_episode_title_resolver.py`
- Modify: `src/atv_player/metadata/episode_title_resolver.py`
- Modify: `src/atv_player/metadata/__init__.py`
- Test: `tests/test_metadata_episode_title_resolver.py`

- [ ] **Step 1: Write the failing resolver tests**

Append these tests to `tests/test_metadata_episode_title_resolver.py` after the existing provider-playlist mapping coverage:

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
    is_high_confidence_iqiyi_episode_candidate,
    resolve_episode_title_source_priority,
)


def test_iqiyi_confidence_succeeds_for_bound_iqiyi_candidate() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    candidate = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:bound",
        title="临江仙",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(
        vod,
        playlist,
        candidate,
        preferred_provider="iqiyi",
    ) is True


def test_iqiyi_confidence_succeeds_for_matching_title_year_and_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙 第一季", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="S01E01.mkv", original_title="S01E01.mkv", url="http://m/1.mp4")]
    candidate = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:match",
        title="临江仙 第一季",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, candidate) is True


def test_iqiyi_confidence_rejects_conflicting_year_or_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙 第一季", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="S01E01.mkv", original_title="S01E01.mkv", url="http://m/1.mp4")]
    wrong_year = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:wrong-year",
        title="临江仙 第一季",
        year="2024",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )
    wrong_season = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:wrong-season",
        title="临江仙 第二季",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )

    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, wrong_year) is False
    assert is_high_confidence_iqiyi_episode_candidate(vod, playlist, wrong_season) is False


def test_resolve_episode_title_source_priority_moves_iqiyi_ahead_of_tmdb_only_for_high_confidence_match() -> None:
    vod = VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    iqiyi = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="临江仙",
        year="2025",
        raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
    )
    tmdb = MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")

    assert resolve_episode_title_source_priority(vod, playlist, [iqiyi, tmdb]) == [
        "plugin",
        "bangumi",
        "bilibili",
        "iqiyi",
        "tmdb",
        "tencent",
    ]
    assert resolve_episode_title_source_priority(vod, playlist, [tmdb]) == METADATA_EPISODE_TITLE_SOURCE_PRIORITY
```

- [ ] **Step 2: Run the focused resolver tests to verify they fail**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py -k "iqiyi_confidence or resolve_episode_title_source_priority" -q`

Expected: FAIL with import errors or `AttributeError` because the new helper functions do not exist yet.

- [ ] **Step 3: Write the minimal resolver implementation**

In `src/atv_player/metadata/episode_title_resolver.py`, add shared helpers above `build_provider_episode_playlist(...)`:

```python
from atv_player.metadata.query import normalize_metadata_title

_IQIYI_PRIORITIZED_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "bangumi", "bilibili", "iqiyi", "tmdb", "tencent"]


def is_high_confidence_iqiyi_episode_candidate(
    vod: VodItem,
    playlist: list[PlayItem],
    candidate,
    *,
    preferred_provider: str = "",
) -> bool:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    if provider != "iqiyi":
        return False
    if str(preferred_provider or "").strip() == "iqiyi":
        return build_provider_episode_playlist(
            vod,
            playlist,
            candidate,
            source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
        ) is not None
    if not _iqiyi_titles_match_vod(vod, candidate):
        return False
    return build_provider_episode_playlist(
        vod,
        playlist,
        candidate,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    ) is not None


def resolve_episode_title_source_priority(
    vod: VodItem,
    playlist: list[PlayItem],
    candidates: list[object],
    *,
    preferred_provider: str = "",
) -> list[str]:
    for candidate in candidates:
        if is_high_confidence_iqiyi_episode_candidate(
            vod,
            playlist,
            candidate,
            preferred_provider=preferred_provider,
        ):
            return list(_IQIYI_PRIORITIZED_EPISODE_TITLE_SOURCE_PRIORITY)
    return list(METADATA_EPISODE_TITLE_SOURCE_PRIORITY)


def _iqiyi_titles_match_vod(vod: VodItem, candidate) -> bool:
    vod_title = normalize_metadata_title(str(vod.vod_name or "").strip())
    candidate_title = normalize_metadata_title(str(getattr(candidate, "title", "") or "").strip())
    if not vod_title or not candidate_title or vod_title != candidate_title:
        return False
    vod_year = str(vod.vod_year or "").strip()
    candidate_year = str(getattr(candidate, "year", "") or "").strip()
    if vod_year and candidate_year and vod_year != candidate_year:
        return False
    vod_season = _guess_default_season(vod)
    candidate_season = extract_season_number(getattr(candidate, "title", ""))
    if candidate_season is not None and candidate_season != vod_season:
        return False
    return True
```

Update `src/atv_player/metadata/__init__.py` by extending the existing import list and `__all__`, not by replacing the whole file. Add these names to the existing import block:

```python
from atv_player.metadata.episode_title_resolver import (
    is_high_confidence_iqiyi_episode_candidate,
    resolve_episode_title_source_priority,
)
```

Then append these names to the existing `__all__` list:

```python
__all__ += [
    "is_high_confidence_iqiyi_episode_candidate",
    "resolve_episode_title_source_priority",
]
```

- [ ] **Step 4: Run the focused resolver tests to verify they pass**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py -k "iqiyi_confidence or resolve_episode_title_source_priority" -q`

Expected: PASS

- [ ] **Step 5: Run the full resolver regression suite**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py -q`

Expected: PASS, including the existing Tencent, TMDB, Bangumi, and Bilibili mapping cases.

- [ ] **Step 6: Commit the resolver change**

```bash
git add tests/test_metadata_episode_title_resolver.py src/atv_player/metadata/episode_title_resolver.py src/atv_player/metadata/__init__.py
git commit -m "feat: add iqiyi episode title confidence gate"
```

### Task 2: Apply the dynamic priority in manual scrape playlist building

**Files:**
- Modify: `tests/test_metadata_scrape_service.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Test: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write the failing scrape-service tests**

Add these tests near the existing `build_episode_title_playlist(...)` coverage in `tests/test_metadata_scrape_service.py`:

```python
def test_metadata_scrape_service_prefers_high_confidence_iqiyi_over_tmdb(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="临江仙",
                year="2025",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "iqiyi"
    assert updated[0].episode_display_title == "第1集 缘起"


def test_metadata_scrape_service_keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    iqiyi = FakeProvider(
        "iqiyi",
        matches=[
            MetadataMatch(
                provider="iqiyi",
                provider_id="iqiyi:1",
                title="临江仙 特别篇",
                year="2025",
                raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:42:season:1", title="临江仙", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 1, "name": "TMDB标题"}])
    service = MetadataScrapeService(cache=cache, providers=[iqiyi, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第1集 TMDB标题"
```

- [ ] **Step 2: Run the focused scrape-service tests to verify they fail**

Run: `uv run pytest tests/test_metadata_scrape_service.py -k "high_confidence_iqiyi_over_tmdb or keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low" -q`

Expected: FAIL because `build_episode_title_playlist(...)` still iterates candidates in the old fixed order and returns the TMDB result first.

- [ ] **Step 3: Write the minimal scrape-service implementation**

In `src/atv_player/metadata/scrape.py`, import the new helper and reorder the candidate evaluation using the resolved priority:

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
    resolve_episode_title_source_priority,
)


def _order_episode_title_candidates(
    vod: VodItem,
    playlist: list[PlayItem],
    candidates: list[object],
    *,
    preferred_provider: str = "",
) -> list[object]:
    priority = resolve_episode_title_source_priority(
        vod,
        playlist,
        candidates,
        preferred_provider=preferred_provider,
    )
    return sorted(
        candidates,
        key=lambda candidate: (
            priority.index(str(getattr(candidate, "provider", "") or "").strip())
            if str(getattr(candidate, "provider", "") or "").strip() in priority
            else len(priority) + 100
        ),
    )


def build_episode_title_playlist(
    self,
    vod: VodItem,
    playlist: list[PlayItem],
    *,
    preferred_candidate: MetadataScrapeCandidate | None = None,
) -> list[PlayItem] | None:
    ordered_candidates: list[object] = []
    if preferred_candidate is not None:
        enriched = self._hydrate_tmdb_episode_candidate(vod, preferred_candidate)
        enriched = self._hydrate_bangumi_episode_candidate(enriched)
        ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
    query = MetadataQuery(
        title=str(vod.vod_name or "").strip(),
        year=str(vod.vod_year or "").strip(),
        category_name=str(vod.category_name or "").strip(),
    )
    for provider_name in ("bangumi", "bilibili", "tmdb", "tencent", "iqiyi"):
        if preferred_candidate is not None and provider_name == preferred_candidate.provider:
            continue
        provider = self._providers_by_name.get(provider_name)
        if provider is None:
            continue
        try:
            matches = provider.search(query)
        except Exception:
            continue
        if matches:
            enriched = self._hydrate_tmdb_episode_candidate(vod, matches[0])
            enriched = self._hydrate_bangumi_episode_candidate(enriched)
            ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
    source_priority = resolve_episode_title_source_priority(
        vod,
        playlist,
        ordered_candidates,
        preferred_provider=preferred_candidate.provider if preferred_candidate is not None else "",
    )
    ordered_candidates = _order_episode_title_candidates(
        vod,
        playlist,
        ordered_candidates,
        preferred_provider=preferred_candidate.provider if preferred_candidate is not None else "",
    )
    for candidate in ordered_candidates:
        updated = build_provider_episode_playlist(
            vod,
            playlist,
            candidate,
            source_priority=source_priority,
        )
        if updated is not None:
            return updated
    return None
```

Compute the dynamic `source_priority` once per call, store it in a local, and reuse it both for sorting and for `build_provider_episode_playlist(...)`. Do not change provider search order in `search(...)`; only change episode-title playlist building.

- [ ] **Step 4: Run the focused scrape-service tests to verify they pass**

Run: `uv run pytest tests/test_metadata_scrape_service.py -k "high_confidence_iqiyi_over_tmdb or keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low" -q`

Expected: PASS

- [ ] **Step 5: Run the broader scrape-service regression slice**

Run: `uv run pytest tests/test_metadata_scrape_service.py -k "build_episode_title_playlist or auto_search_prefers_tmdb_over_tencent_and_iqiyi or auto_search_prefers_bilibili_over_tmdb_tencent_and_iqiyi or auto_search_prefers_bangumi_over_bilibili_tmdb_tencent_and_iqiyi" -q`

Expected: PASS, including the existing Bangumi/Bilibili precedence behavior.

- [ ] **Step 6: Commit the scrape-service change**

```bash
git add tests/test_metadata_scrape_service.py src/atv_player/metadata/scrape.py
git commit -m "feat: prioritize confident iqiyi episode titles in scrape service"
```

### Task 3: Apply the dynamic priority in the automatic episode-title enhancer

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing app-level tests**

Replace the old TMDB-first expectation and add a low-confidence guard in `tests/test_app.py` near the existing episode-title enhancer tests:

```python
def test_app_coordinator_episode_title_enhancer_prefers_high_confidence_iqiyi_over_tmdb(tmp_path, monkeypatch) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(
                metadata_enhancement_enabled=True,
                metadata_tmdb_api_key="tmdb-key",
                episode_title_enhancement_enabled=True,
            )

    class FakeIqiyiProvider:
        name = "iqiyi"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [
                MetadataMatch(
                    provider="iqiyi",
                    provider_id="iqiyi:1",
                    title="临江仙",
                    year="2025",
                    raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
                )
            ]

    class EmptyTencentProvider:
        name = "tencent"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return []

    class FakeTMDBClient:
        def __init__(self, api_key: str, proxy_decider=None) -> None:
            assert api_key == "tmdb-key"
            del proxy_decider

        def search_tv(self, title: str, year: str = "") -> list[dict[str, object]]:
            return [{"id": 42, "name": title, "first_air_date": "2025-01-01"}]

        def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, object]:
            return {"episodes": [{"episode_number": 1, "name": "TMDB标题"}]}

    monkeypatch.setattr(app_module, "TencentMetadataProvider", EmptyTencentProvider)
    monkeypatch.setattr(app_module, "IqiyiMetadataProvider", FakeIqiyiProvider)
    monkeypatch.setattr(app_module, "TMDBClient", FakeTMDBClient)
    monkeypatch.setattr(app_module, "app_cache_dir", lambda: tmp_path / "app-cache")

    coordinator = AppCoordinator(FakeRepo())
    enhance = coordinator._build_episode_title_enhancer_factory(object())(
        source_kind="plugin",
        vod=VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
    )

    updated = enhance(
        SimpleNamespace(
            vod=VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
            playlist=[PlayItem(title="01.mp4", url="http://m/1.mp4", original_title="01.mp4")],
        )
    )

    assert updated is not None
    assert updated[0].episode_title_source == "iqiyi"
    assert updated[0].episode_display_title == "第1集 缘起"


def test_app_coordinator_episode_title_enhancer_keeps_tmdb_when_iqiyi_title_confidence_is_low(tmp_path, monkeypatch) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(
                metadata_enhancement_enabled=True,
                metadata_tmdb_api_key="tmdb-key",
                episode_title_enhancement_enabled=True,
            )

    class FakeIqiyiProvider:
        name = "iqiyi"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [
                MetadataMatch(
                    provider="iqiyi",
                    provider_id="iqiyi:1",
                    title="临江仙 特别篇",
                    year="2025",
                    raw={"videos": [{"itemNumber": 1, "itemTitle": "缘起"}]},
                )
            ]

    class EmptyTencentProvider:
        name = "tencent"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return []

    class FakeTMDBClient(FakeTMDBClient):
        pass

    monkeypatch.setattr(app_module, "TencentMetadataProvider", EmptyTencentProvider)
    monkeypatch.setattr(app_module, "IqiyiMetadataProvider", FakeIqiyiProvider)
    monkeypatch.setattr(app_module, "TMDBClient", FakeTMDBClient)
    monkeypatch.setattr(app_module, "app_cache_dir", lambda: tmp_path / "app-cache")

    coordinator = AppCoordinator(FakeRepo())
    enhance = coordinator._build_episode_title_enhancer_factory(object())(
        source_kind="plugin",
        vod=VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
    )

    updated = enhance(
        SimpleNamespace(
            vod=VodItem(vod_id="v1", vod_name="临江仙", vod_year="2025", category_name="电视剧"),
            playlist=[PlayItem(title="01.mp4", url="http://m/1.mp4", original_title="01.mp4")],
        )
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第1集 TMDB标题"
```

Rename the existing `test_app_coordinator_episode_title_enhancer_prefers_tmdb_over_tencent_and_iqiyi(...)` expectation to the new high-confidence IQIYI behavior, because that old contract is what this feature intentionally changes.

- [ ] **Step 2: Run the focused app tests to verify they fail**

Run: `uv run pytest tests/test_app.py -k "high_confidence_iqiyi_over_tmdb or keeps_tmdb_when_iqiyi_title_confidence_is_low" -q`

Expected: FAIL because the enhancer still applies TMDB titles first and only accepts later provider candidates when mapping count improves.

- [ ] **Step 3: Write the minimal app implementation**

In `src/atv_player/app.py`, import `resolve_episode_title_source_priority` and apply it to provider-candidate evaluation:

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
    resolve_episode_title_source_priority,
)
```

Inside `_build_episode_title_enhancer_factory(...)`:

```python
provider_candidates: list[object] = []
for candidate_vod in candidate_vods:
    provider_candidates.extend(_search_metadata_candidates(candidate_vod, source_kind))

dynamic_source_priority = resolve_episode_title_source_priority(
    effective_vod,
    playlist,
    provider_candidates,
    preferred_provider=str(getattr(bound_candidate, "provider", "") or "").strip(),
)

for candidate_vod in candidate_vods:
    for candidate in _search_metadata_candidates(candidate_vod, source_kind):
        updated_playlist = build_provider_episode_playlist(
            candidate_vod,
            playlist,
            candidate,
            source_priority=dynamic_source_priority,
        )
        if updated_playlist is None:
            continue
        updated_pairs = _season_episode_pairs(updated_playlist, default_season)
        finalized = _finalize_episode_playlist(updated_playlist, updated_pairs)
        if finalized is None:
            continue
        previous_source = str(playlist[0].episode_title_source or "").strip() if playlist else ""
        new_source = str(finalized[0].episode_title_source or "").strip() if finalized else ""
        previous_rank = dynamic_source_priority.index(previous_source) if previous_source in dynamic_source_priority else len(dynamic_source_priority) + 100
        new_rank = dynamic_source_priority.index(new_source) if new_source in dynamic_source_priority else len(dynamic_source_priority) + 100
        if (
            _count_mapped_episode_titles(finalized) > _count_mapped_episode_titles(playlist)
            or (
                _count_mapped_episode_titles(finalized) == _count_mapped_episode_titles(playlist)
                and _episode_title_snapshot(finalized) != _episode_title_snapshot(playlist)
                and new_rank < previous_rank
            )
        ):
            playlist = finalized
```

The point of this change is:

- Keep better coverage wins first
- When coverage ties, allow the higher-priority source under the dynamic order to replace the current titles
- Preserve existing Bangumi/Bilibili wins because they still rank above both IQIYI and TMDB

- [ ] **Step 4: Run the focused app tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "high_confidence_iqiyi_over_tmdb or keeps_tmdb_when_iqiyi_title_confidence_is_low" -q`

Expected: PASS

- [ ] **Step 5: Run the broader enhancer regression slice**

Run: `uv run pytest tests/test_app.py -k "episode_title_enhancer and (bilibili or bangumi or iqiyi or tmdb)" -q`

Expected: PASS, including existing Bangumi reopen/bound tests, Bilibili override tests, and TMDB fallback tests.

- [ ] **Step 6: Commit the app-level change**

```bash
git add tests/test_app.py src/atv_player/app.py
git commit -m "feat: prioritize confident iqiyi episode titles in enhancer"
```

### Task 4: Final regression and verification record

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-iqiyi-episode-title-priority.md`
- Test: `tests/test_metadata_episode_title_resolver.py`
- Test: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_app.py`

- [x] **Step 1: Run the final targeted verification suite**

Run these focused slices that cover the changed resolver, scrape-service, and enhancer paths without pulling in unrelated `tests/test_app.py` cases:

- `uv run pytest tests/test_metadata_episode_title_resolver.py -q`
- `uv run pytest tests/test_metadata_scrape_service.py -k "build_episode_title_playlist or auto_search_prefers_high_confidence_iqiyi_over_tmdb_and_tencent or auto_search_prefers_bilibili_over_tmdb_tencent_and_iqiyi or auto_search_prefers_bangumi_over_bilibili_tmdb_tencent_and_iqiyi or keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low" -q`
- `uv run pytest tests/test_app.py -k "episode_title_enhancer and (bilibili or bangumi or iqiyi or tmdb)" -q`

Expected: PASS

- [x] **Step 2: Record the verification commands in the plan**

Append this block under this task once the commands pass:

```text
Verified:
- uv run pytest tests/test_metadata_episode_title_resolver.py -q
- uv run pytest tests/test_metadata_scrape_service.py -k "build_episode_title_playlist or auto_search_prefers_high_confidence_iqiyi_over_tmdb_and_tencent or auto_search_prefers_bilibili_over_tmdb_tencent_and_iqiyi or auto_search_prefers_bangumi_over_bilibili_tmdb_tencent_and_iqiyi or keeps_tmdb_ahead_when_iqiyi_title_confidence_is_low" -q
- uv run pytest tests/test_app.py -k "episode_title_enhancer and (bilibili or bangumi or iqiyi or tmdb)" -q
```

- [ ] **Step 3: Commit the verification note**

```bash
git add docs/superpowers/plans/2026-05-20-iqiyi-episode-title-priority.md
git commit -m "docs: record iqiyi episode title priority verification"
```
