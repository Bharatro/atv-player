# Bilibili Anime Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make anime-only Bilibili metadata enhancement fetch real bangumi season details and prefer Bilibili episode titles over TMDB only when the title can be confirmed as a valid Bilibili bangumi season.

**Architecture:** Keep the existing provider/hydrator/scrape architecture, but strengthen `BilibiliMetadataProvider` so it can normalize anime-only season details into reusable raw episode data. Then gate episode-title rewrite decisions on that normalized Bilibili data so anime playlists use Bilibili titles only when the candidate is confirmed and complete; otherwise they fall back cleanly to TMDB.

**Tech Stack:** Python 3.12+, `httpx`, pytest, existing metadata provider/cache infrastructure

---

## File Map

**Modify:**

- `src/atv_player/metadata/providers/bilibili.py`
  - Add anime-only enrich gating.
  - Parse/store `season_id`.
  - Fetch and normalize Bilibili bangumi season detail and section payloads.
  - Reuse normalized episodes in `get_detail()`.
- `src/atv_player/metadata/episode_title_resolver.py`
  - Add Bilibili anime-candidate validation helpers.
  - Switch Bilibili title mapping to normalized `raw["episodes"]` first, with `raw["eps"]` fallback.
- `src/atv_player/metadata/scrape.py`
  - Add Bilibili candidate hydration similar to existing TMDB/Bangumi hydration.
  - Gate Bilibili auto-priority on validated anime candidates, otherwise fall back to TMDB.
- `tests/test_metadata_bilibili_provider.py`
  - Cover season detail fetching, normalized episode storage, and anime-only `can_enrich()`.
- `tests/test_metadata_episode_title_resolver.py`
  - Cover special-episode filtering and confirmed-Bilibili-candidate gating.
- `tests/test_metadata_scrape_service.py`
  - Cover auto-search preferring Bilibili when confirmed and falling back to TMDB when not confirmed.

**Do not modify unless debugging proves necessary:**

- `src/atv_player/app.py`
  - Provider order already places `bilibili` ahead of `tmdb`; the missing behavior is data quality and candidate gating, not assembly order.

## Task 1: Bilibili Provider Season Detail Hydration

**Files:**
- Modify: `tests/test_metadata_bilibili_provider.py`
- Modify: `src/atv_player/metadata/providers/bilibili.py`
- Test: `tests/test_metadata_bilibili_provider.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_metadata_bilibili_provider.py`:

```python
def test_bilibili_metadata_provider_can_enrich_only_anime_context() -> None:
    provider = BilibiliMetadataProvider(get=lambda url, **kwargs: JsonResponse({"code": 0, "result": {}}))

    anime = MetadataQuery(title="牧神记", category_name="动漫")
    movie = MetadataQuery(title="长安的荔枝", category_name="电影")

    class Ctx:
        def __init__(self, query):
            self._query = query

        def to_query(self):
            return self._query

    assert provider.can_enrich(Ctx(anime)) is True
    assert provider.can_enrich(Ctx(movie)) is False


def test_bilibili_metadata_provider_get_detail_fetches_season_detail_and_normalizes_main_episodes() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if "pgc/view/web/season" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "season_id": 148433,
                        "title": "凸变英雄X",
                        "evaluate": "这是番剧详情简介",
                        "cover": "https://i0.hdslb.com/bfs/bangumi/image/season.png",
                        "areas": [{"name": "中国大陆"}],
                        "styles": [{"name": "热血"}, {"name": "战斗"}],
                        "stat": {"followers": 12345},
                        "up_info": {},
                        "publish": {"is_finish": 0},
                        "new_ep": {"desc": "更新至第28话"},
                        "actors": "声优A\n声优B",
                        "staff": "导演A\n编剧B",
                        "episodes": [
                            {"title": "1", "long_title": "启程", "badge": "", "ep_id": 1},
                            {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                        ],
                    },
                }
            )
        if "pgc/web/season/section" in url:
            return JsonResponse(
                {
                    "code": 0,
                    "result": {
                        "main_section": {
                            "episodes": [
                                {"title": "1", "long_title": "启程", "badge": "", "ep_id": 1},
                                {"title": "28", "long_title": "答案", "badge": "", "ep_id": 28},
                            ]
                        },
                        "section": [
                            {
                                "title": "SP",
                                "episodes": [
                                    {"title": "SP", "long_title": "特别篇", "badge": "SP", "ep_id": 999}
                                ],
                            }
                        ],
                    },
                }
            )
        raise AssertionError(url)

    provider = BilibiliMetadataProvider(get=fake_get)
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss148433",
        title="凸变英雄X",
        year="2025",
        raw={"title": "凸变英雄X", "season_id": 148433, "season_type_name": "国创"},
    )

    record = provider.get_detail(match)

    assert any("pgc/view/web/season" in url for url in calls)
    assert any("pgc/web/season/section" in url for url in calls)
    assert record.title == "凸变英雄X"
    assert record.poster == "https://i0.hdslb.com/bfs/bangumi/image/season.png"
    assert record.country == "中国大陆"
    assert record.genres == ["热血", "战斗"]
    assert record.overview == "这是番剧详情简介"
    assert {"label": "更新状态", "value": "更新至第28话"} in record.detail_fields
    assert match.raw["episodes"] == [
        {"episode_number": 1, "title": "1", "long_title": "启程", "badge": "", "episode_type": "main", "sort": 1},
        {"episode_number": 28, "title": "28", "long_title": "答案", "badge": "", "episode_type": "main", "sort": 28},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_metadata_bilibili_provider.py -v
```

Expected:

- `test_bilibili_metadata_provider_can_enrich_only_anime_context` fails because `can_enrich()` currently always returns `True`
- `test_bilibili_metadata_provider_get_detail_fetches_season_detail_and_normalizes_main_episodes` fails because `get_detail()` does not call Bilibili season detail endpoints or store normalized `raw["episodes"]`

- [ ] **Step 3: Write minimal implementation**

Update `src/atv_player/metadata/providers/bilibili.py` with focused helpers like:

```python
def can_enrich(self, context) -> bool:
    query = context.to_query()
    values = " ".join(
        value.strip().lower()
        for value in (str(query.category_name or ""), str(query.type_name or ""))
        if value and value.strip()
    )
    return any(token in values for token in ("动漫", "动画", "番剧", "国创", "anime"))


def _season_id_from_payload(self, payload: dict[str, object]) -> str:
    for key in ("season_id", "pgc_season_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    provider_id = str(payload.get("provider_id") or "").strip()
    match = re.search(r"/ss(\d+)", provider_id)
    return match.group(1) if match else ""


def _season_detail_payload(self, season_id: str) -> dict[str, object]:
    payload = self._request_json("https://api.bilibili.com/pgc/view/web/season", params={"season_id": season_id})
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili season detail failed: {payload.get('code')}")
    return dict(payload.get("result") or {})


def _season_section_payload(self, season_id: str) -> dict[str, object]:
    payload = self._request_json("https://api.bilibili.com/pgc/web/season/section", params={"season_id": season_id})
    if payload.get("code") != 0:
        return {}
    return dict(payload.get("result") or {})


def _normalize_bilibili_episodes(self, detail: dict[str, object], sections: dict[str, object]) -> list[dict[str, object]]:
    rows = list(((sections.get("main_section") or {}).get("episodes") or []) or (detail.get("episodes") or []))
    normalized: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            episode_number = int(str(row.get("title") or "").strip())
        except (TypeError, ValueError):
            continue
        long_title = str(row.get("long_title") or row.get("share_copy") or row.get("show_title") or "").strip()
        normalized.append(
            {
                "episode_number": episode_number,
                "title": str(row.get("title") or "").strip(),
                "long_title": long_title,
                "badge": str(row.get("badge") or "").strip(),
                "episode_type": "main",
                "sort": episode_number,
            }
        )
    return normalized


def get_detail(self, match: MetadataMatch) -> MetadataRecord:
    payload = dict(match.raw)
    if not payload:
        payload = self._search_detail_payload(match)
    season_id = self._season_id_from_payload(payload)
    if season_id:
        detail = self._season_detail_payload(season_id)
        sections = self._season_section_payload(season_id)
        payload.update(self._merge_season_payload(payload, detail))
        normalized_episodes = self._normalize_bilibili_episodes(detail, sections)
        if normalized_episodes:
            payload["episodes"] = normalized_episodes
            match.raw["episodes"] = normalized_episodes
```

Also map `poster`, `country`, `genres`, `overview`, `cv`, `staff`, and `index_show` from season detail payloads before building the `MetadataRecord`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_metadata_bilibili_provider.py -v
```

Expected:

- All tests in `tests/test_metadata_bilibili_provider.py` pass
- The new detail test proves `raw["episodes"]` is normalized and excludes section-only special entries

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_bilibili_provider.py src/atv_player/metadata/providers/bilibili.py
git commit -m "feat: hydrate bilibili anime season metadata"
```

## Task 2: Episode Title Resolver Bilibili Validation

**Files:**
- Modify: `tests/test_metadata_episode_title_resolver.py`
- Modify: `src/atv_player/metadata/episode_title_resolver.py`
- Test: `tests/test_metadata_episode_title_resolver.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_metadata_episode_title_resolver.py`:

```python
def test_build_provider_episode_playlist_prefers_normalized_bilibili_episodes_over_eps() -> None:
    vod = VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫")
    playlist = [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")]
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss148433",
        title="凸变英雄X",
        year="2025",
        raw={
            "season_id": 148433,
            "season_type_name": "国创",
            "episodes": [
                {"episode_number": 28, "long_title": "答案", "episode_type": "main", "sort": 28}
            ],
            "eps": [{"title": "28", "long_title": ""}],
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert updated[0].episode_display_title == "第28集 答案"


def test_build_provider_episode_playlist_skips_bilibili_candidate_without_confirmed_anime_season() -> None:
    vod = VodItem(vod_id="v1", vod_name="示例动画", vod_year="2025", category_name="动漫")
    playlist = [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss999",
        title="示例动画",
        year="2025",
        raw={"season_type_name": "国创", "eps": [{"title": "1", "long_title": "搜索摘要标题"}]},
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_metadata_episode_title_resolver.py -v
```

Expected:

- The first test fails because the resolver currently ignores normalized `raw["episodes"]` for Bilibili
- The second test fails because any `bilibili` candidate with `eps` currently rewrites titles even without confirmed season-detail backing

- [ ] **Step 3: Write minimal implementation**

Update `src/atv_player/metadata/episode_title_resolver.py` with helper logic like:

```python
def _is_confirmed_bilibili_anime_candidate(raw: dict[str, object]) -> bool:
    if not str(raw.get("season_id") or "").strip():
        return False
    episodes = raw.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        return False
    return True


def _candidate_supports_episode_title_rewrite(...):
    ...
    if provider == "bilibili" and not _is_confirmed_bilibili_anime_candidate(raw):
        return False
    return not _raw_indicates_movie_category(raw)


def _titles_by_index_for_bilibili(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    normalized = raw.get("episodes")
    if isinstance(normalized, list):
        for episode in normalized:
            if not isinstance(episode, dict):
                continue
            try:
                episode_number = int(episode.get("episode_number") or episode.get("sort") or 0)
            except (TypeError, ValueError):
                continue
            if str(episode.get("episode_type") or "main").strip() != "main":
                continue
            episode_title = str(episode.get("long_title") or episode.get("title") or "").strip()
            if episode_number > 0 and episode_title:
                titles_by_episode[episode_number] = episode_title
    if not titles_by_episode:
        for episode in raw.get("eps") or []:
            ...
```

This change must preserve existing `bangumi`, `tmdb`, `tencent`, and `iqiyi` behavior.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_metadata_episode_title_resolver.py -v
```

Expected:

- All resolver tests pass
- Bilibili rewrite now requires confirmed normalized anime-season data

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_episode_title_resolver.py src/atv_player/metadata/episode_title_resolver.py
git commit -m "feat: gate bilibili episode title rewrite on season detail"
```

## Task 3: Metadata Scrape Service Bilibili Auto-Fallback

**Files:**
- Modify: `tests/test_metadata_scrape_service.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Test: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_metadata_scrape_service.py`:

```python
def test_metadata_scrape_service_auto_search_prefers_confirmed_bilibili_over_tmdb(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss148433",
                title="凸变英雄X",
                year="2025",
                raw={"season_id": 148433, "season_type_name": "国创"},
            )
        ],
    )
    bilibili._hydrate_episode_candidate = lambda candidate: replace(
        candidate,
        raw={
            **candidate.raw,
            "episodes": [{"episode_number": 28, "long_title": "答案", "episode_type": "main", "sort": 28}],
        },
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:315088:season:1", title="凸变英雄X", year="2025")],
    )
    tmdb._client = FakeTMDBClient([{"episode_number": 28, "name": ""}])
    service = MetadataScrapeService(cache=cache, providers=[bilibili, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫"),
        [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "bilibili"
    assert updated[0].episode_display_title == "第28集 答案"


def test_metadata_scrape_service_auto_search_falls_back_to_tmdb_when_bilibili_candidate_is_unconfirmed(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bilibili = FakeProvider(
        "bilibili",
        matches=[
            MetadataMatch(
                provider="bilibili",
                provider_id="https://www.bilibili.com/bangumi/play/ss148433",
                title="凸变英雄X",
                year="2025",
                raw={"season_type_name": "国创", "eps": [{"title": "28", "long_title": "摘要标题"}]},
            )
        ],
    )
    tmdb = FakeProvider(
        "tmdb",
        matches=[
            MetadataMatch(
                provider="tmdb",
                provider_id="tv:315088:season:1",
                title="凸变英雄X",
                year="2025",
                raw={"episodes": [{"episode_number": 28, "name": "TMDB回退标题"}]},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[bilibili, tmdb])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="凸变英雄X", vod_year="2025", category_name="动漫"),
        [PlayItem(title="28.mp4", original_title="28.mp4", url="http://m/28.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tmdb"
    assert updated[0].episode_display_title == "第28集 TMDB回退标题"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_metadata_scrape_service.py -v
```

Expected:

- Confirmed-Bilibili test fails because scrape service does not currently hydrate Bilibili episode candidates
- Fallback test fails because a search-summary-only Bilibili candidate currently wins before TMDB

- [ ] **Step 3: Write minimal implementation**

Update `src/atv_player/metadata/scrape.py` with a Bilibili hydration branch mirroring the existing TMDB/Bangumi helpers:

```python
def _hydrate_bilibili_episode_candidate(self, candidate: object) -> object:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    if provider != "bilibili":
        return candidate
    raw = dict(getattr(candidate, "raw", {}) or {})
    episodes = raw.get("episodes")
    if isinstance(episodes, list) and episodes and str(raw.get("season_id") or "").strip():
        return candidate
    bilibili_provider = self._providers_by_name.get("bilibili")
    hydrate = getattr(bilibili_provider, "_hydrate_episode_candidate", None)
    if not callable(hydrate):
        return candidate
    return hydrate(candidate)


def build_episode_title_playlist(...):
    ordered_candidates: list[object] = []
    if preferred_candidate is not None:
        enriched = self._hydrate_tmdb_episode_candidate(vod, preferred_candidate)
        enriched = self._hydrate_bangumi_episode_candidate(enriched)
        ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
    ...
    for provider_name in ("bangumi", "bilibili", "tmdb", "tencent", "iqiyi"):
        ...
        if matches:
            enriched = self._hydrate_tmdb_episode_candidate(vod, matches[0])
            enriched = self._hydrate_bangumi_episode_candidate(enriched)
            ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
```

In `src/atv_player/metadata/providers/bilibili.py`, expose a narrow helper that the scrape service can call:

```python
def _hydrate_episode_candidate(self, candidate):
    raw = dict(getattr(candidate, "raw", {}) or {})
    season_id = self._season_id_from_payload(raw)
    if not season_id:
        return candidate
    detail = self._season_detail_payload(season_id)
    sections = self._season_section_payload(season_id)
    normalized = self._normalize_bilibili_episodes(detail, sections)
    if not normalized:
        return candidate
    raw["season_id"] = season_id
    raw["episodes"] = normalized
    return replace(candidate, raw=raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_metadata_scrape_service.py -v
```

Expected:

- All scrape-service tests pass
- Automatic anime title rewrite now uses Bilibili only when the candidate is hydrated into a confirmed season, otherwise TMDB remains the fallback

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_scrape_service.py src/atv_player/metadata/scrape.py src/atv_player/metadata/providers/bilibili.py
git commit -m "feat: prefer confirmed bilibili anime titles in scrape flow"
```

## Final Verification

**Files:**
- Test: `tests/test_metadata_bilibili_provider.py`
- Test: `tests/test_metadata_episode_title_resolver.py`
- Test: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
uv run pytest tests/test_metadata_bilibili_provider.py tests/test_metadata_episode_title_resolver.py tests/test_metadata_scrape_service.py -v
```

Expected:

- All three files pass
- No regressions in existing Bilibili/TMDB/Bangumi episode-title tests

- [ ] **Step 2: Run one broader metadata regression command**

Run:

```bash
uv run pytest tests/test_metadata_hydrator.py tests/test_metadata_merge.py -v
```

Expected:

- Pass
- Confirms the new Bilibili detail mapping did not break provider merge behavior

- [ ] **Step 3: Commit the verification checkpoint**

```bash
git status --short
```

Expected:

- Clean working tree or only intentional follow-up changes

## Self-Review

- Spec coverage:
  - Anime-only activation: Task 1
  - Bilibili season detail fetching: Task 1
  - Confirmed Bilibili ownership gating: Task 2
  - Prefer Bilibili over TMDB only when confirmed: Task 3
  - TMDB fallback when unconfirmed: Task 3
  - Regression verification: Final Verification
- Placeholder scan: No `TBD`, `TODO`, or deferred implementation steps remain.
- Type consistency:
  - `raw["season_id"]` and `raw["episodes"]` are introduced in Task 1 and reused consistently in Tasks 2 and 3.
  - `_hydrate_episode_candidate()` is defined in Task 3 and consumed only from scrape service.
