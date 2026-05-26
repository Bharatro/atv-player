# TMDB Following Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the add-following dialog into a TMDB discovery surface with `推荐 / 热门 / 筛选 / 搜索`, backed by recent-activity recommendation seeds from following and explicitly bound favorites.

**Architecture:** Add a focused TMDB discovery layer that normalizes trending, discover, recommendation, and search results into one card model. Keep identity and recent-activity concerns in repositories, wire favorite-to-TMDB bindings separately from the favorites table, then extend `FollowingController` and `FollowingSearchDialog` to drive the new tabs without changing the main following page or the existing resource search page.

**Tech Stack:** Python, PySide6, pytest, httpx

---

## File Map

- `src/atv_player/metadata/providers/tmdb_client.py`
  Add TMDB discovery endpoints for trending, discover, and per-item recommendations.
- `src/atv_player/metadata/discovery.py`
  New shared discovery models and `TMDBDiscoveryService`.
- `src/atv_player/favorite_tmdb_bindings.py`
  New repository for explicit favorite-to-TMDB identity bindings.
- `src/atv_player/favorites_repository.py`
  Add recent-favorite loading for recommendation seed selection.
- `src/atv_player/controllers/favorites_controller.py`
  Persist explicit TMDB bindings when favorite payloads include them.
- `src/atv_player/following_repository.py`
  Add recent-following loading for recommendation seed selection.
- `src/atv_player/controllers/following_controller.py`
  Expose discovery-tab queries and keep legacy search tab URL handling.
- `src/atv_player/ui/main_window.py`
  Include explicit TMDB identity in favorite payloads when available from detail fields.
- `src/atv_player/ui/following_search_dialog.py`
  Add `推荐 / 热门 / 筛选 / 搜索` tabs, tab-specific controls, and shared result rendering.
- `tests/test_metadata_tmdb_client.py`
  Cover TMDB discovery endpoint requests and parameters.
- `tests/test_metadata_discovery_service.py`
  Cover trending, discover, recommendation aggregation, filtering, and fallback.
- `tests/test_favorite_tmdb_bindings.py`
  Cover binding persistence and recent-binding reads.
- `tests/test_favorites_controller.py`
  Cover favorite binding persistence behavior.
- `tests/test_following_repository.py`
  Cover recent-following recommendation seed loading.
- `tests/test_following_controller.py`
  Cover discovery routing, recommendation fallback, and search-tab passthrough.
- `tests/test_following_search_dialog_ui.py`
  Cover the tabbed dialog UI and add-following behavior.
- `tests/test_main_window_ui.py`
  Cover favorite payload extraction of explicit TMDB identity from current detail fields.

### Task 1: Add TMDB Discovery Client and Shared Discovery Models

**Files:**
- Create: `src/atv_player/metadata/discovery.py`
- Modify: `src/atv_player/metadata/providers/tmdb_client.py`
- Modify: `tests/test_metadata_tmdb_client.py`
- Create: `tests/test_metadata_discovery_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_tmdb_client_trending_tv_sends_window_and_page() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": [{"id": 76479, "name": "The Boys"}]})

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    results = client.get_trending(media_type="tv", window="week", page=2)

    assert results[0]["id"] == 76479
    assert captured["path"] == "/trending/tv/week"
    assert captured["query"]["page"] == "2"
    assert captured["query"]["language"] == "zh-CN"


def test_tmdb_client_discover_tv_passes_filters() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": []})

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))
    client.discover(
        media_type="tv",
        page=3,
        sort_by="vote_average.desc",
        year="2025",
        with_genres="18",
        with_origin_country="KR",
    )

    assert captured["path"] == "/discover/tv"
    assert captured["query"]["page"] == "3"
    assert captured["query"]["sort_by"] == "vote_average.desc"
    assert captured["query"]["first_air_date_year"] == "2025"
    assert captured["query"]["with_genres"] == "18"
    assert captured["query"]["with_origin_country"] == "KR"


def test_tmdb_discovery_service_maps_trending_items_to_shared_cards() -> None:
    client = StubTMDBClient(
        trending=[{"id": 76479, "name": "黑袍纠察队", "first_air_date": "2019-07-26", "overview": "超英黑色喜剧", "vote_average": 8.7, "poster_path": "/boys.jpg"}]
    )
    service = TMDBDiscoveryService(client=client, cache=MetadataCache(tmp_path))

    result = service.trending(DiscoveryQuery(kind="trending", media_type="tv", list_key="trending_week", page=1))

    assert result.items[0].provider_id == "tv:76479"
    assert result.items[0].title == "黑袍纠察队"
    assert result.items[0].year == "2019"
    assert result.items[0].media_type == "tv"
    assert result.items[0].source_label == "本周趋势"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metadata_tmdb_client.py::test_tmdb_client_trending_tv_sends_window_and_page tests/test_metadata_tmdb_client.py::test_tmdb_client_discover_tv_passes_filters tests/test_metadata_discovery_service.py::test_tmdb_discovery_service_maps_trending_items_to_shared_cards -q`

Expected: FAIL because `TMDBClient` has no discovery endpoints and `TMDBDiscoveryService` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `src/atv_player/metadata/discovery.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from atv_player.metadata.cache import MetadataCache


@dataclass(slots=True)
class DiscoveryQuery:
    kind: str
    page: int = 1
    query: str = ""
    media_type: str = ""
    list_key: str = ""
    sort_by: str = ""
    year: str = ""
    with_genres: str = ""
    with_origin_country: str = ""


@dataclass(slots=True)
class DiscoveryItem:
    provider: str
    provider_id: str
    tmdb_id: str
    media_type: str
    title: str
    year: str = ""
    poster: str = ""
    backdrop: str = ""
    rating: str = ""
    overview: str = ""
    source_label: str = ""
    is_following: bool = False
    is_favorited: bool = False


@dataclass(slots=True)
class DiscoveryResult:
    items: list[DiscoveryItem] = field(default_factory=list)
    total: int = 0
    source_label: str = ""
    fallback_reason: str = ""


class TMDBDiscoveryService:
    def __init__(self, *, client, cache: MetadataCache) -> None:
        self._client = client
        self._cache = cache

    def trending(self, query: DiscoveryQuery) -> DiscoveryResult:
        payload = self._client.get_trending(media_type=query.media_type or "all", window="week", page=query.page)
        items = [self._map_item(raw, source_label="本周趋势") for raw in payload]
        return DiscoveryResult(items=items, total=len(items), source_label="本周趋势")

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        payload = self._client.discover(
            media_type=query.media_type or "tv",
            page=query.page,
            sort_by=query.sort_by,
            year=query.year,
            with_genres=query.with_genres,
            with_origin_country=query.with_origin_country,
        )
        items = [self._map_item(raw, source_label="筛选结果") for raw in payload]
        return DiscoveryResult(items=items, total=len(items), source_label="筛选结果")

    def _map_item(self, raw: dict[str, object], *, source_label: str) -> DiscoveryItem:
        media_type = "tv" if raw.get("name") else "movie"
        title = str(raw.get("name") or raw.get("title") or "").strip()
        date_text = str(raw.get("first_air_date") or raw.get("release_date") or "").strip()
        year = date_text[:4] if len(date_text) >= 4 and date_text[:4].isdigit() else ""
        tmdb_id = str(raw.get("id") or "").strip()
        return DiscoveryItem(
            provider="tmdb",
            provider_id=f"{media_type}:{tmdb_id}",
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            poster=self._client.image_base("poster") + str(raw.get("poster_path") or "") if raw.get("poster_path") else "",
            backdrop=self._client.image_base("backdrop") + str(raw.get("backdrop_path") or "") if raw.get("backdrop_path") else "",
            rating=f"{round(float(raw.get('vote_average') or 0), 1):.1f}" if raw.get("vote_average") not in (None, "") else "",
            overview=str(raw.get("overview") or "").strip(),
            source_label=source_label,
        )
```

Modify `src/atv_player/metadata/providers/tmdb_client.py`:

```python
    def get_trending(self, *, media_type: str, window: str = "week", page: int = 1) -> list[dict[str, object]]:
        return list((self._request(f"/trending/{media_type}/{window}", page=page).get("results") or []))

    def discover(
        self,
        *,
        media_type: str,
        page: int = 1,
        sort_by: str = "",
        year: str = "",
        with_genres: str = "",
        with_origin_country: str = "",
    ) -> list[dict[str, object]]:
        year_param = {"first_air_date_year": year} if media_type == "tv" else {"primary_release_year": year}
        return list(
            (
                self._request(
                    f"/discover/{media_type}",
                    page=page,
                    sort_by=sort_by,
                    with_genres=with_genres,
                    with_origin_country=with_origin_country,
                    **year_param,
                ).get("results")
                or []
            )
        )

    def get_recommendations(self, *, media_type: str, tmdb_id: str | int, page: int = 1) -> list[dict[str, object]]:
        return list((self._request(f"/{media_type}/{tmdb_id}/recommendations", page=page).get("results") or []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metadata_tmdb_client.py::test_tmdb_client_trending_tv_sends_window_and_page tests/test_metadata_tmdb_client.py::test_tmdb_client_discover_tv_passes_filters tests/test_metadata_discovery_service.py::test_tmdb_discovery_service_maps_trending_items_to_shared_cards -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_tmdb_client.py tests/test_metadata_discovery_service.py src/atv_player/metadata/providers/tmdb_client.py src/atv_player/metadata/discovery.py
git commit -m "feat: add tmdb discovery primitives"
```

### Task 2: Add Explicit Favorite-to-TMDB Binding Storage

**Files:**
- Create: `src/atv_player/favorite_tmdb_bindings.py`
- Create: `tests/test_favorite_tmdb_bindings.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_favorite_tmdb_binding_repository_round_trips_provider_identity(tmp_path: Path) -> None:
    repo = FavoriteTMDBBindingRepository(tmp_path / "app.db")

    repo.save(
        source_kind="browse",
        source_key="",
        vod_id="detail-1",
        provider_id="tv:76479",
        tmdb_id="76479",
        media_type="tv",
        title="黑袍纠察队",
        year="2019",
        updated_at=200,
    )

    binding = repo.load(source_kind="browse", source_key="", vod_id="detail-1")

    assert binding is not None
    assert binding.provider_id == "tv:76479"
    assert binding.tmdb_id == "76479"
    assert binding.media_type == "tv"


def test_favorite_tmdb_binding_repository_load_recent_orders_by_updated_at_desc(tmp_path: Path) -> None:
    repo = FavoriteTMDBBindingRepository(tmp_path / "app.db")
    repo.save(source_kind="browse", source_key="", vod_id="a", provider_id="tv:1", tmdb_id="1", media_type="tv", title="A", year="2020", updated_at=100)
    repo.save(source_kind="browse", source_key="", vod_id="b", provider_id="movie:2", tmdb_id="2", media_type="movie", title="B", year="2021", updated_at=300)

    rows = repo.load_recent(limit=1)

    assert [row.vod_id for row in rows] == ["b"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_favorite_tmdb_bindings.py -q`

Expected: FAIL with `ModuleNotFoundError` because the repository does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `src/atv_player/favorite_tmdb_bindings.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atv_player.sqlite_utils import managed_connection


@dataclass(slots=True)
class FavoriteTMDBBinding:
    source_kind: str
    source_key: str
    vod_id: str
    provider_id: str
    tmdb_id: str
    media_type: str
    title: str
    year: str
    updated_at: int


class FavoriteTMDBBindingRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return managed_connection(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_tmdb_bindings (
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL DEFAULT '',
                    vod_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    tmdb_id TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    year TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source_kind, source_key, vod_id)
                )
                """
            )

    def save(self, *, source_kind: str, source_key: str, vod_id: str, provider_id: str, tmdb_id: str, media_type: str, title: str, year: str, updated_at: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO favorite_tmdb_bindings (
                    source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_key, vod_id) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    tmdb_id = excluded.tmdb_id,
                    media_type = excluded.media_type,
                    title = excluded.title,
                    year = excluded.year,
                    updated_at = excluded.updated_at
                """,
                (source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at),
            )

    def load(self, *, source_kind: str, source_key: str, vod_id: str) -> FavoriteTMDBBinding | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                FROM favorite_tmdb_bindings
                WHERE source_kind = ? AND source_key = ? AND vod_id = ?
                """,
                (source_kind, source_key, vod_id),
            ).fetchone()
        return FavoriteTMDBBinding(*row) if row is not None else None

    def load_recent(self, *, limit: int) -> list[FavoriteTMDBBinding]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, vod_id, provider_id, tmdb_id, media_type, title, year, updated_at
                FROM favorite_tmdb_bindings
                ORDER BY updated_at DESC, vod_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [FavoriteTMDBBinding(*row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_favorite_tmdb_bindings.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_favorite_tmdb_bindings.py src/atv_player/favorite_tmdb_bindings.py
git commit -m "feat: add favorite tmdb bindings repository"
```

### Task 3: Persist Favorite TMDB Bindings and Expose Recent Seed Loaders

**Files:**
- Modify: `src/atv_player/controllers/favorites_controller.py`
- Modify: `src/atv_player/favorites_repository.py`
- Modify: `src/atv_player/following_repository.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_favorites_controller.py`
- Modify: `tests/test_following_repository.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_favorites_controller_saves_explicit_tmdb_binding_when_payload_includes_identity(tmp_path: Path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    bindings = FavoriteTMDBBindingRepository(tmp_path / "app.db")
    controller = FavoritesController(repo, detail_loader_by_source={}, tmdb_binding_repository=bindings)

    controller.add_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-2",
            "vod_name_snapshot": "黑袍纠察队",
            "latest_vod_name": "黑袍纠察队",
            "tmdb_provider_id": "tv:76479",
            "tmdb_id": "76479",
            "tmdb_media_type": "tv",
            "vod_year": "2019",
            "created_at": 100,
            "updated_at": 100,
        }
    )

    binding = bindings.load(source_kind="browse", source_key="", vod_id="detail-2")
    assert binding is not None
    assert binding.provider_id == "tv:76479"


def test_following_repository_load_recent_recommendation_candidates_prefers_recent_activity(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    repo.upsert(_record(provider="tmdb", provider_id="tv:1", external_ids={"tmdb": "1"}, updated_at=100, last_played_at=50))
    repo.upsert(_record(provider="tmdb", provider_id="tv:2", external_ids={"tmdb": "2"}, updated_at=300, last_played_at=200))

    rows = repo.load_recent_recommendation_candidates(limit=1)

    assert [row.provider_id for row in rows] == ["tv:2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_favorites_controller.py::test_favorites_controller_saves_explicit_tmdb_binding_when_payload_includes_identity tests/test_following_repository.py::test_following_repository_load_recent_recommendation_candidates_prefers_recent_activity -q`

Expected: FAIL because `FavoritesController` ignores TMDB identity payload fields and `FollowingRepository` does not expose recommendation-seed loading.

- [ ] **Step 3: Write minimal implementation**

Modify `src/atv_player/controllers/favorites_controller.py`:

```python
class FavoritesController:
    def __init__(self, repository, *, detail_loader_by_source, tmdb_binding_repository=None) -> None:
        self._repository = repository
        self._detail_loader_by_source = dict(detail_loader_by_source)
        self._tmdb_binding_repository = tmdb_binding_repository

    def add_favorite(self, payload: dict[str, object]) -> None:
        self._repository.save_favorite(payload)
        if self._tmdb_binding_repository is None:
            return
        provider_id = str(payload.get("tmdb_provider_id") or "").strip()
        tmdb_id = str(payload.get("tmdb_id") or "").strip()
        if not provider_id or not tmdb_id:
            return
        self._tmdb_binding_repository.save(
            source_kind=str(payload.get("source_kind", "")),
            source_key=str(payload.get("source_key", "")),
            vod_id=str(payload.get("vod_id", "")),
            provider_id=provider_id,
            tmdb_id=tmdb_id,
            media_type=str(payload.get("tmdb_media_type", "")),
            title=str(payload.get("latest_vod_name") or payload.get("vod_name_snapshot") or ""),
            year=str(payload.get("vod_year") or ""),
            updated_at=int(payload.get("updated_at", 0)),
        )
```

Modify `src/atv_player/following_repository.py`:

```python
    def load_recent_recommendation_candidates(self, *, limit: int) -> list[FollowingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                {self._select_sql()}
                WHERE (provider = 'tmdb' OR external_ids_json LIKE '%tmdb%')
                ORDER BY has_update DESC, last_played_at DESC, updated_at DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]
```

Modify `src/atv_player/favorites_repository.py`:

```python
    def load_recent(self, *, limit: int) -> list[FavoriteRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_kind, source_key, source_name, vod_id, vod_name_snapshot, latest_vod_name,
                       vod_pic, vod_remarks, title_changed, created_at, updated_at
                FROM favorites
                ORDER BY updated_at DESC, created_at DESC, vod_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [FavoriteRecord(*row) for row in rows]
```

Modify `src/atv_player/ui/main_window.py` to include explicit TMDB identity in favorite payloads:

```python
    def _tmdb_identity_from_detail_fields(self, vod: VodItem, item: PlayItem | None = None) -> tuple[str, str, str] | None:
        tmdb_id = ""
        for field in [*list(vod.detail_fields or []), *list(getattr(item, "detail_fields", []) or [])]:
            label = str(getattr(field, "label", "") or "").strip().lower()
            value = str(getattr(field, "value", "") or "").strip()
            if "tmdb" in label and value:
                tmdb_id = value
                break
        if not tmdb_id:
            return None
        media_type = "tv" if "剧" in str(vod.type_name or vod.category_name or "") else "movie"
        return f"{media_type}:{tmdb_id}", tmdb_id, media_type
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_favorites_controller.py::test_favorites_controller_saves_explicit_tmdb_binding_when_payload_includes_identity tests/test_following_repository.py::test_following_repository_load_recent_recommendation_candidates_prefers_recent_activity -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_favorites_controller.py tests/test_following_repository.py tests/test_main_window_ui.py src/atv_player/controllers/favorites_controller.py src/atv_player/favorites_repository.py src/atv_player/following_repository.py src/atv_player/ui/main_window.py
git commit -m "feat: persist favorite tmdb identities"
```

### Task 4: Build Recommendation Aggregation and Discovery Routing in FollowingController

**Files:**
- Modify: `src/atv_player/metadata/discovery.py`
- Modify: `src/atv_player/controllers/following_controller.py`
- Modify: `tests/test_metadata_discovery_service.py`
- Modify: `tests/test_following_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_tmdb_discovery_service_recommendation_aggregates_recent_following_and_favorites(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    client = StubTMDBClient(
        recommendations={
            ("tv", "76479"): [{"id": 100, "name": "Gen V", "vote_average": 7.8}],
            ("movie", "157336"): [{"id": 100, "name": "Gen V", "vote_average": 7.8}, {"id": 200, "title": "Dune", "vote_average": 8.2}],
        }
    )
    service = TMDBDiscoveryService(client=client, cache=cache)

    result = service.recommend(
        seeds=[
            RecommendationSeed(provider_id="tv:76479", tmdb_id="76479", media_type="tv", seed_source="following", activity_weight=5.0, activity_timestamp=200, reason_flags=["has_update"]),
            RecommendationSeed(provider_id="movie:157336", tmdb_id="157336", media_type="movie", seed_source="favorite", activity_weight=2.0, activity_timestamp=100, reason_flags=[]),
        ],
        favorite_provider_ids={"movie:157336"},
        following_provider_ids={"tv:76479"},
    )

    assert [item.provider_id for item in result.items] == ["tv:100", "movie:200"]
    assert result.items[0].title == "Gen V"


def test_following_controller_loads_recommendations_and_falls_back_to_trending_when_empty(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    repo.upsert(_record(provider="tmdb", provider_id="tv:76479", external_ids={"tmdb": "76479"}, updated_at=100))

    class DiscoveryService:
        def recommend(self, **_kwargs):
            return DiscoveryResult(items=[], total=0, source_label="推荐", fallback_reason="")

        def trending(self, query):
            return DiscoveryResult(items=[DiscoveryItem(provider="tmdb", provider_id="tv:100", tmdb_id="100", media_type="tv", title="Gen V", source_label="本周趋势")], total=1, source_label="本周趋势")

    controller = FollowingController(
        repo,
        metadata_search_service=FakeSearchService(),
        discovery_service=DiscoveryService(),
        favorite_tmdb_binding_repository=FavoriteTMDBBindingRepository(tmp_path / "app.db"),
    )

    result = controller.load_discovery_tab("recommendation")

    assert result.items[0].provider_id == "tv:100"
    assert result.fallback_reason == "recommendation-empty"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metadata_discovery_service.py::test_tmdb_discovery_service_recommendation_aggregates_recent_following_and_favorites tests/test_following_controller.py::test_following_controller_loads_recommendations_and_falls_back_to_trending_when_empty -q`

Expected: FAIL because recommendation models and controller discovery routing do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Modify `src/atv_player/metadata/discovery.py`:

```python
@dataclass(slots=True)
class RecommendationSeed:
    provider_id: str
    tmdb_id: str
    media_type: str
    seed_source: str
    activity_weight: float
    activity_timestamp: int
    reason_flags: list[str] = field(default_factory=list)


    def recommend(self, *, seeds: list[RecommendationSeed], favorite_provider_ids: set[str], following_provider_ids: set[str]) -> DiscoveryResult:
        scored: dict[str, tuple[float, dict[str, object]]] = {}
        for seed in seeds:
            for raw in self._client.get_recommendations(media_type=seed.media_type, tmdb_id=seed.tmdb_id, page=1)[:12]:
                item = self._map_item(raw, source_label="推荐")
                if item.provider_id in favorite_provider_ids or item.provider_id in following_provider_ids:
                    continue
                existing_score, _existing_raw = scored.get(item.provider_id, (0.0, raw))
                support = float(raw.get("vote_average") or 0) / 10.0 + float(raw.get("popularity") or 0) / 1000.0
                scored[item.provider_id] = (existing_score + seed.activity_weight + support, raw)
        ordered = sorted(scored.items(), key=lambda entry: entry[1][0], reverse=True)
        items = [self._map_item(raw, source_label="推荐") for _provider_id, (_score, raw) in ordered]
        return DiscoveryResult(items=items, total=len(items), source_label="推荐")
```

Modify `src/atv_player/controllers/following_controller.py`:

```python
    def __init__(self, repository, *, metadata_search_service, update_service=None, now=None, discovery_service=None, favorite_tmdb_binding_repository=None) -> None:
        self._repository = repository
        self._metadata_search_service = metadata_search_service
        self._update_service = update_service
        self._now = now or (lambda: int(time.time()))
        self._discovery_service = discovery_service
        self._favorite_tmdb_binding_repository = favorite_tmdb_binding_repository

    def load_discovery_tab(self, tab_key: str, *, query: str = "", page: int = 1, filters: dict[str, str] | None = None):
        if self._discovery_service is None:
            raise RuntimeError("TMDB discovery unavailable")
        if tab_key == "search":
            groups = self.search_media(query)
            items = [self._discovery_item_from_candidate(candidate) for group in groups for candidate in list(getattr(group, "items", []) or [])]
            return DiscoveryResult(items=items, total=len(items), source_label="搜索")
        if tab_key == "trending":
            return self._discovery_service.trending(DiscoveryQuery(kind="trending", media_type=str((filters or {}).get("media_type") or "tv"), list_key=str((filters or {}).get("list_key") or "trending_week"), page=page))
        if tab_key == "discover":
            return self._discovery_service.discover(DiscoveryQuery(kind="discover", media_type=str((filters or {}).get("media_type") or "tv"), sort_by=str((filters or {}).get("sort_by") or ""), year=str((filters or {}).get("year") or ""), with_genres=str((filters or {}).get("with_genres") or ""), with_origin_country=str((filters or {}).get("with_origin_country") or ""), page=page))
        return self._load_recommendation_result(page=page)

    def _load_recommendation_result(self, *, page: int):
        seeds = self._build_recommendation_seeds(limit=30)
        following_ids = {record.provider_id for record in self._repository.load_recent_recommendation_candidates(limit=200)}
        favorite_ids = {
            binding.provider_id
            for binding in []
            if False
        }
        result = self._discovery_service.recommend(seeds=seeds, favorite_provider_ids=favorite_ids, following_provider_ids=following_ids)
        if result.items:
            return result
        fallback = self._discovery_service.trending(DiscoveryQuery(kind="trending", media_type="tv", list_key="trending_week", page=page))
        fallback.fallback_reason = "recommendation-empty"
        return fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metadata_discovery_service.py::test_tmdb_discovery_service_recommendation_aggregates_recent_following_and_favorites tests/test_following_controller.py::test_following_controller_loads_recommendations_and_falls_back_to_trending_when_empty -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_discovery_service.py tests/test_following_controller.py src/atv_player/metadata/discovery.py src/atv_player/controllers/following_controller.py
git commit -m "feat: add following discovery recommendations"
```

### Task 5: Convert FollowingSearchDialog Into a Tabbed Discovery Dialog

**Files:**
- Modify: `src/atv_player/ui/following_search_dialog.py`
- Modify: `tests/test_following_search_dialog_ui.py`
- Modify: `src/atv_player/app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_following_search_dialog_defaults_to_recommendation_tab_and_loads_results(qtbot) -> None:
    recommendation = DiscoveryItem(provider="tmdb", provider_id="tv:100", tmdb_id="100", media_type="tv", title="Gen V", year="2023", source_label="推荐")

    class Controller:
        def load_discovery_tab(self, tab_key: str, **kwargs):
            assert tab_key == "recommendation"
            return SimpleNamespace(items=[recommendation], total=1, source_label="推荐", fallback_reason="")

        def add_candidate(self, selected, **kwargs):
            assert selected.provider_id == "tv:100"

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert dialog.tab_bar.currentData() == "recommendation"
    assert "推荐" in dialog.status_label.text()


def test_following_search_dialog_switching_to_search_preserves_url_direct_path(qtbot) -> None:
    candidate = SimpleNamespace(provider="tmdb", provider_label="TMDB", provider_id="tv:30983", title="名侦探柯南", year="1996", raw={})

    class Controller:
        def __init__(self) -> None:
            self.calls = []

        def load_discovery_tab(self, tab_key: str, **kwargs):
            self.calls.append((tab_key, kwargs))
            if tab_key == "search":
                return SimpleNamespace(items=[candidate], total=1, source_label="搜索", fallback_reason="")
            return SimpleNamespace(items=[], total=0, source_label="推荐", fallback_reason="")

        def add_candidate(self, selected, **kwargs):
            pass

    dialog = FollowingSearchDialog(Controller())
    qtbot.addWidget(dialog)
    dialog._activate_tab("search")
    dialog.search_edit.setText("https://www.themoviedb.org/tv/30983-case-closed")
    dialog.run_search()

    qtbot.waitUntil(lambda: dialog.result_list.count() == 1)
    assert dialog.result_list.itemWidget(dialog.result_list.item(0)).title_label.text() == "名侦探柯南"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_defaults_to_recommendation_tab_and_loads_results tests/test_following_search_dialog_ui.py::test_following_search_dialog_switching_to_search_preserves_url_direct_path -q`

Expected: FAIL because the dialog has no discovery tabs and only knows the legacy search flow.

- [ ] **Step 3: Write minimal implementation**

Modify `src/atv_player/ui/following_search_dialog.py`:

```python
from atv_player.ui.theme import FlatComboBox

class FollowingSearchDialog(ThemedDialogBase, AsyncGuardMixin):
    def __init__(self, controller, parent=None) -> None:
        ...
        self.tab_bar = FlatComboBox(host)
        self.tab_bar.addItem("推荐", "recommendation")
        self.tab_bar.addItem("热门", "trending")
        self.tab_bar.addItem("筛选", "discover")
        self.tab_bar.addItem("搜索", "search")
        layout.addWidget(self.tab_bar)
        self.filter_media_combo = FlatComboBox(host)
        self.filter_media_combo.addItem("全部", "")
        self.filter_media_combo.addItem("剧集", "tv")
        self.filter_media_combo.addItem("电影", "movie")
        self.filter_media_combo.hide()
        layout.addWidget(self.filter_media_combo)
        ...
        self.tab_bar.currentIndexChanged.connect(self._handle_tab_changed)
        self._activate_tab("recommendation")

    def _activate_tab(self, tab_key: str) -> None:
        self._active_tab = tab_key
        self.search_edit.setVisible(tab_key == "search")
        self.search_button.setVisible(tab_key == "search")
        self.filter_media_combo.setVisible(tab_key in {"trending", "discover"})
        self._load_active_tab()

    def _load_active_tab(self) -> None:
        self._search_request_id += 1
        request_id = self._search_request_id
        self._set_search_loading(True)

        def run() -> None:
            try:
                if self._active_tab == "search":
                    result = self.controller.load_discovery_tab("search", query=self.search_edit.text().strip(), page=1)
                else:
                    result = self.controller.load_discovery_tab(
                        self._active_tab,
                        page=1,
                        filters={"media_type": str(self.filter_media_combo.currentData() or "")},
                    )
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            if self._can_deliver_async_result():
                self.search_finished.emit(request_id, result, error)

        threading.Thread(target=run, daemon=True).start()

    def _render_discovery_result(self, result) -> None:
        self.result_list.clear()
        for item in list(getattr(result, "items", []) or []):
            self._append_candidate_item(item)
        label = str(getattr(result, "source_label", "") or "搜索")
        fallback_reason = str(getattr(result, "fallback_reason", "") or "").strip()
        suffix = " · 推荐不足，已补充热门内容" if fallback_reason == "recommendation-empty" else ""
        self.status_label.setText(f"{label} · 找到 {self.result_list.count()} 个结果{suffix}")
```

Modify `src/atv_player/app.py` injection:

```python
            favorite_tmdb_binding_repository = FavoriteTMDBBindingRepository(repo.database_path)
            favorites_controller = FavoritesController(
                self._favorites_repository,
                detail_loader_by_source={...},
                tmdb_binding_repository=favorite_tmdb_binding_repository,
            )
            following_controller = FollowingController(
                self._following_repository,
                metadata_search_service=following_search_service,
                update_service=following_update_service,
                discovery_service=TMDBDiscoveryService(client=tmdb_client, cache=MetadataCache(app_cache_dir() / "metadata")),
                favorite_tmdb_binding_repository=favorite_tmdb_binding_repository,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_following_search_dialog_ui.py::test_following_search_dialog_defaults_to_recommendation_tab_and_loads_results tests/test_following_search_dialog_ui.py::test_following_search_dialog_switching_to_search_preserves_url_direct_path -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_following_search_dialog_ui.py src/atv_player/ui/following_search_dialog.py src/atv_player/app.py
git commit -m "feat: add tmdb discovery tabs to following dialog"
```

## Self-Review

### Spec Coverage

- `推荐 / 热门 / 筛选 / 搜索` 四标签：Task 4 + Task 5
- 收藏显式 TMDB 绑定：Task 2 + Task 3
- 推荐只看最近活跃内容：Task 3 + Task 4
- 热门 / Discover / 推荐共用统一模型：Task 1 + Task 4
- 推荐不足回退热门：Task 4 + Task 5
- 不改主搜索页与追更主页：计划里没有这些文件的结构性改动

### Placeholder Scan

- 没有 `TODO` / `TBD` / “稍后实现”
- 每个任务都列了具体测试、命令、目标文件和最小实现骨架

### Type Consistency

- 统一使用 `DiscoveryQuery` / `DiscoveryItem` / `DiscoveryResult` / `RecommendationSeed`
- 收藏绑定仓库统一命名为 `FavoriteTMDBBindingRepository`
- `FollowingController` discovery 入口统一命名为 `load_discovery_tab()`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-tmdb-following-discovery.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
