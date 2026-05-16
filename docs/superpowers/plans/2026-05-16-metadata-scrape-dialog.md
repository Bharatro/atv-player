# Metadata Scrape Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a player-side `刮削` dialog that searches metadata providers in parallel, lets the user manually choose one result to apply, and persists that choice as a reusable `标题 + 年份` binding.

**Architecture:** Keep the existing `MetadataHydrator` and provider chain as the single metadata backbone. Add three thin pieces around it: a SQLite-backed `MetadataBindingRepository`, a reusable `MetadataScrapeService` for parallel search and manual apply, and a `PlayerWindow` dialog that mirrors the current `弹幕源` interaction pattern without auto-applying any result.

**Tech Stack:** Python 3.14, dataclasses, SQLite, PySide6, pytest

---

## File Map

**Create:**
- `src/atv_player/metadata/bindings.py`
- `src/atv_player/metadata/scrape.py`
- `tests/test_metadata_bindings.py`
- `tests/test_metadata_scrape_service.py`

**Modify:**
- `src/atv_player/metadata/__init__.py`
- `src/atv_player/metadata/hydrator.py`
- `src/atv_player/models.py`
- `src/atv_player/controllers/player_controller.py`
- `src/atv_player/app.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/player_window.py`
- `tests/test_metadata_hydrator.py`
- `tests/test_player_window_ui.py`

**Existing references to inspect while implementing:**
- `src/atv_player/metadata/cache.py`
- `src/atv_player/metadata/models.py`
- `src/atv_player/metadata/merge.py`
- `src/atv_player/ui/player_window.py`
- `tests/test_metadata_cache.py`
- `tests/test_player_window_ui.py`

### Task 1: Add the metadata binding repository

**Files:**
- Create: `src/atv_player/metadata/bindings.py`
- Modify: `src/atv_player/metadata/__init__.py`
- Create: `tests/test_metadata_bindings.py`
- Test: `tests/test_metadata_bindings.py`

- [ ] **Step 1: Write the failing binding repository tests**

```python
from pathlib import Path

from atv_player.metadata.bindings import MetadataBindingRepository


def test_metadata_binding_repository_round_trips_normalized_title_and_year(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")

    repo.save(
        "  星际 穿越  ",
        "2014-11-07",
        provider="tmdb",
        provider_id="movie:157336",
        matched_title="Interstellar",
        matched_year="2014",
    )

    binding = repo.load("星际穿越", "2014")

    assert binding is not None
    assert binding.provider == "tmdb"
    assert binding.provider_id == "movie:157336"
    assert binding.matched_title == "Interstellar"
    assert binding.normalized_title == "星际穿越"
    assert binding.normalized_year == "2014"


def test_metadata_binding_repository_overwrites_existing_binding(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")

    repo.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    repo.save("深空彼岸", "2026", provider="local_douban", provider_id="35746415")

    binding = repo.load("深空彼岸", "2026")

    assert binding is not None
    assert binding.provider == "local_douban"
    assert binding.provider_id == "35746415"


def test_metadata_binding_repository_deletes_binding(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")
    repo.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")

    repo.delete("深空彼岸", "2026")

    assert repo.load("深空彼岸", "2026") is None
```

- [ ] **Step 2: Run the binding repository tests and verify they fail**

Run: `uv run pytest tests/test_metadata_bindings.py -q`

Expected: FAIL with `ModuleNotFoundError` because `src/atv_player/metadata/bindings.py` does not exist yet.

- [ ] **Step 3: Create the binding repository and export it**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import time

from atv_player.sqlite_utils import managed_connection


def normalize_metadata_binding_title(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    return compact.casefold()


def normalize_metadata_binding_year(value: object) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{4})", text)
    return match.group(1) if match else ""


def metadata_binding_query_key(title: object, year: object) -> str:
    return f"{normalize_metadata_binding_title(title)}\x1f{normalize_metadata_binding_year(year)}"


@dataclass(slots=True)
class MetadataBinding:
    normalized_title: str
    normalized_year: str
    provider: str
    provider_id: str
    matched_title: str = ""
    matched_year: str = ""
    updated_at: int = 0


class MetadataBindingRepository:
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
                CREATE TABLE IF NOT EXISTS metadata_bindings (
                    query_key TEXT PRIMARY KEY,
                    normalized_title TEXT NOT NULL,
                    normalized_year TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    matched_title TEXT NOT NULL DEFAULT '',
                    matched_year TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def load(self, title: object, year: object) -> MetadataBinding | None:
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT normalized_title, normalized_year, provider, provider_id, matched_title, matched_year, updated_at
                FROM metadata_bindings
                WHERE query_key = ?
                """,
                (query_key,),
            ).fetchone()
        if row is None:
            return None
        return MetadataBinding(*row)

    def save(
        self,
        title: object,
        year: object,
        *,
        provider: str,
        provider_id: str,
        matched_title: str = "",
        matched_year: str = "",
    ) -> None:
        normalized_title = normalize_metadata_binding_title(title)
        normalized_year = normalize_metadata_binding_year(year)
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO metadata_bindings (
                    query_key, normalized_title, normalized_year, provider, provider_id, matched_title, matched_year, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    provider = excluded.provider,
                    provider_id = excluded.provider_id,
                    matched_title = excluded.matched_title,
                    matched_year = excluded.matched_year,
                    updated_at = excluded.updated_at
                """,
                (
                    query_key,
                    normalized_title,
                    normalized_year,
                    str(provider or "").strip(),
                    str(provider_id or "").strip(),
                    str(matched_title or "").strip(),
                    str(matched_year or "").strip(),
                    int(time()),
                ),
            )

    def delete(self, title: object, year: object) -> None:
        query_key = metadata_binding_query_key(title, year)
        with self._connect() as conn:
            conn.execute("DELETE FROM metadata_bindings WHERE query_key = ?", (query_key,))
```

Also update `src/atv_player/metadata/__init__.py`:

```python
from atv_player.metadata.bindings import MetadataBinding, MetadataBindingRepository
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.hydrator import MetadataHydrator
from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery, MetadataRecord

__all__ = [
    "MetadataBinding",
    "MetadataBindingRepository",
    "MetadataCache",
    "MetadataContext",
    "MetadataHydrator",
    "MetadataMatch",
    "MetadataQuery",
    "MetadataRecord",
]
```

- [ ] **Step 4: Run the binding repository tests and verify they pass**

Run: `uv run pytest tests/test_metadata_bindings.py -q`

Expected: PASS with 3 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/bindings.py src/atv_player/metadata/__init__.py tests/test_metadata_bindings.py
git commit -m "feat: add metadata binding repository"
```

### Task 2: Add the metadata scrape service

**Files:**
- Create: `src/atv_player/metadata/scrape.py`
- Modify: `src/atv_player/metadata/__init__.py`
- Create: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write the failing scrape service tests**

```python
from dataclasses import replace
from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeService
from atv_player.models import VodItem


class FakeProvider:
    def __init__(self, name: str, *, matches=None, record=None, search_error: Exception | None = None) -> None:
        self.name = name
        self.matches = list(matches or [])
        self.record = record
        self.search_error = search_error
        self.search_calls: list[MetadataQuery] = []
        self.detail_calls: list[MetadataMatch] = []

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls.append(candidate)
        if self.search_error is not None:
            raise self.search_error
        return list(self.matches)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls.append(match)
        assert self.record is not None
        return self.record


def test_metadata_scrape_service_groups_parallel_results_by_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="movie:1", title="深空彼岸", year="2026")],
    )
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸", year="2026")],
    )
    service = MetadataScrapeService(cache=cache, providers=[tmdb, douban])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="")

    assert [group.provider for group in groups] == ["tmdb", "local_douban"]
    assert groups[0].items[0].provider_id == "movie:1"
    assert groups[1].items[0].provider_id == "35746415"


def test_metadata_scrape_service_keeps_failed_provider_group_for_all_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    broken = FakeProvider("tmdb", search_error=RuntimeError("tmdb timeout"))
    douban = FakeProvider(
        "local_douban",
        matches=[MetadataMatch(provider="local_douban", provider_id="35746415", title="深空彼岸")],
    )
    service = MetadataScrapeService(cache=cache, providers=[broken, douban])

    groups = service.search(MetadataQuery(title="深空彼岸"), provider_filter="")

    assert groups[0].provider == "tmdb"
    assert groups[0].error_text == "tmdb timeout"
    assert groups[0].items == []
    assert groups[1].provider == "local_douban"
    assert groups[1].items[0].provider_id == "35746415"


def test_metadata_scrape_service_apply_uses_cached_detail_before_fetching_provider(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "tmdb",
        "movie:1",
        MetadataRecord(provider="tmdb", provider_id="movie:1", poster="https://img.example/poster.jpg"),
    )
    provider = FakeProvider(
        "tmdb",
        record=MetadataRecord(provider="tmdb", provider_id="movie:1", poster="https://img.example/new.jpg"),
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])
    candidate = MetadataScrapeCandidate(
        provider="tmdb",
        provider_label="TMDB",
        provider_id="movie:1",
        title="深空彼岸",
        year="2026",
    )

    updated = service.apply(VodItem(vod_id="v1", vod_name="深空彼岸"), candidate)

    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert provider.detail_calls == []
```

- [ ] **Step 2: Run the scrape service tests and verify they fail**

Run: `uv run pytest tests/test_metadata_scrape_service.py -q`

Expected: FAIL with `ModuleNotFoundError` because `src/atv_player/metadata/scrape.py` does not exist yet.

- [ ] **Step 3: Create the scrape service and export it**

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.merge import merge_metadata_record
from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.models import VodItem

_PROVIDER_LABELS = {
    "local_douban": "本地豆瓣",
    "remote_douban": "alist-tvbox豆瓣",
    "douban": "豆瓣",
    "tmdb": "TMDB",
    "plugin": "插件",
}


@dataclass(slots=True)
class MetadataScrapeCandidate:
    provider: str
    provider_label: str
    provider_id: str
    title: str
    year: str = ""
    subtitle: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MetadataScrapeGroup:
    provider: str
    provider_label: str
    items: list[MetadataScrapeCandidate] = field(default_factory=list)
    error_text: str = ""


class MetadataScrapeService:
    def __init__(self, cache: MetadataCache, providers: list[object]) -> None:
        self._cache = cache
        self._providers = list(providers)
        self._providers_by_name = {provider.name: provider for provider in self._providers}

    def _provider_label(self, provider_name: str) -> str:
        return _PROVIDER_LABELS.get(provider_name, provider_name)

    def _candidate_from_match(self, match: MetadataMatch) -> MetadataScrapeCandidate:
        return MetadataScrapeCandidate(
            provider=match.provider,
            provider_label=self._provider_label(match.provider),
            provider_id=str(match.provider_id),
            title=match.title,
            year=match.year,
            subtitle=str(match.raw.get("subtitle") or ""),
            raw=dict(match.raw),
        )

    def search(self, query: MetadataQuery, provider_filter: str = "") -> list[MetadataScrapeGroup]:
        providers = [provider for provider in self._providers if not provider_filter or provider.name == provider_filter]

        def run(provider: object) -> MetadataScrapeGroup:
            try:
                matches = provider.search(query)
            except Exception as exc:
                return MetadataScrapeGroup(
                    provider=provider.name,
                    provider_label=self._provider_label(provider.name),
                    items=[],
                    error_text=str(exc),
                )
            return MetadataScrapeGroup(
                provider=provider.name,
                provider_label=self._provider_label(provider.name),
                items=[self._candidate_from_match(match) for match in matches],
            )

        with ThreadPoolExecutor(max_workers=max(1, len(providers))) as executor:
            futures = [executor.submit(run, provider) for provider in providers]
        return [future.result() for future in futures]

    def apply(self, vod: VodItem, candidate: MetadataScrapeCandidate) -> VodItem:
        provider = self._providers_by_name[candidate.provider]
        cached = self._cache.load_detail(candidate.provider, candidate.provider_id, ttl_seconds=7 * 24 * 3600)
        if cached is None:
            match = MetadataMatch(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                year=candidate.year,
                raw=dict(candidate.raw),
            )
            cached = provider.get_detail(match)
            self._cache.save_detail(candidate.provider, candidate.provider_id, cached)
        updated = replace(vod)
        merge_metadata_record(updated, cached, provider_priority=[item.name for item in self._providers])
        return updated
```

Also update `src/atv_player/metadata/__init__.py`:

```python
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup, MetadataScrapeService

__all__ = [
    "MetadataBinding",
    "MetadataBindingRepository",
    "MetadataCache",
    "MetadataContext",
    "MetadataHydrator",
    "MetadataMatch",
    "MetadataQuery",
    "MetadataRecord",
    "MetadataScrapeCandidate",
    "MetadataScrapeGroup",
    "MetadataScrapeService",
]
```

- [ ] **Step 4: Run the scrape service tests and verify they pass**

Run: `uv run pytest tests/test_metadata_scrape_service.py -q`

Expected: PASS with 3 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/scrape.py src/atv_player/metadata/__init__.py tests/test_metadata_scrape_service.py
git commit -m "feat: add metadata scrape service"
```

### Task 3: Wire binding-aware hydration and session plumbing

**Files:**
- Modify: `src/atv_player/metadata/hydrator.py`
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_metadata_hydrator.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing hydrator binding tests**

```python
def test_metadata_hydrator_prefers_manual_binding_before_provider_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:99", title="错误结果")],
        record=MetadataRecord(provider="tmdb", provider_id="tv:42", poster="https://img.example/poster.jpg"),
    )
    douban = FakeProvider("local_douban", matches=[])
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb, douban], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"), source_kind="browse")
    )

    assert updated.vod_pic == "https://img.example/poster.jpg"
    assert tmdb.search_calls == 0


def test_metadata_hydrator_deletes_invalid_manual_binding_and_falls_back_to_search(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "app.db")
    bindings.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    tmdb = FakeProvider(
        "tmdb",
        matches=[MetadataMatch(provider="tmdb", provider_id="tv:99", title="深空彼岸")],
        record=MetadataRecord(provider="tmdb", provider_id="tv:99", poster="https://img.example/recovered.jpg"),
        detail_error=RuntimeError("detail missing"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[tmdb], binding_repository=bindings)

    updated = hydrator.hydrate(
        MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"), source_kind="browse")
    )

    assert bindings.load("深空彼岸", "2026") is None
    assert updated.vod_name == "深空彼岸"
```

- [ ] **Step 2: Run the hydrator tests and verify they fail**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "manual_binding" -q`

Expected: FAIL because `MetadataHydrator` does not accept `binding_repository` and does not consult manual bindings yet.

- [ ] **Step 3: Make hydrator, app wiring, and player session binding-aware**

Update `src/atv_player/metadata/hydrator.py`:

```python
from dataclasses import replace
import logging

from atv_player.metadata.base import MetadataProvider
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.merge import merge_metadata_record
from atv_player.metadata.models import MetadataContext, MetadataMatch


class MetadataHydrator:
    def __init__(
        self,
        cache: MetadataCache,
        providers: list[MetadataProvider],
        binding_repository=None,
    ) -> None:
        self._cache = cache
        self._providers = providers
        self._providers_by_name = {provider.name: provider for provider in providers}
        self._binding_repository = binding_repository

    def _load_bound_record(self, query):
        if self._binding_repository is None:
            return None
        binding = self._binding_repository.load(query.title, query.year)
        if binding is None:
            return None
        provider = self._providers_by_name.get(binding.provider)
        if provider is None:
            self._binding_repository.delete(query.title, query.year)
            return None
        cached = self._cache.load_detail(binding.provider, binding.provider_id, ttl_seconds=_DETAIL_CACHE_TTL_SECONDS)
        if cached is not None:
            return cached
        try:
            record = provider.get_detail(
                MetadataMatch(
                    provider=binding.provider,
                    provider_id=binding.provider_id,
                    title=binding.matched_title or query.title,
                    year=binding.matched_year or query.year,
                )
            )
        except Exception:
            self._binding_repository.delete(query.title, query.year)
            return None
        self._cache.save_detail(binding.provider, binding.provider_id, record)
        return record

    def hydrate(self, context: MetadataContext) -> VodItem:
        vod = replace(context.vod)
        query = context.to_query()
        bound_record = self._load_bound_record(query)
        bound_provider = ""
        if bound_record is not None:
            merge_metadata_record(vod, bound_record, provider_priority=[item.name for item in self._providers])
            bound_provider = bound_record.provider
        for provider in self._providers:
            if provider.name == bound_provider:
                continue
            ...
```

Update `src/atv_player/models.py`:

```python
@dataclass(slots=True)
class OpenPlayerRequest:
    ...
    metadata_hydrator: Callable[[object], VodItem | None] | None = None
    metadata_scrape_service: object | None = None
    metadata_binding_repository: object | None = None
    episode_title_enhancer: Callable[[object], list[PlayItem] | None] | None = None
    ...
```

```python
@dataclass(slots=True)
class PlayerSession:
    ...
    metadata_hydrator: Callable[[object], VodItem | None] | None = None
    metadata_scrape_service: object | None = None
    metadata_binding_repository: object | None = None
    metadata_hydrated: bool = False
    ...
```

Update `src/atv_player/controllers/player_controller.py`:

```python
@dataclass(slots=True)
class PlayerSession:
    ...
    metadata_scrape_service: object | None = None
    metadata_binding_repository: object | None = None
```

```python
def create_session(
    ...,
    metadata_hydrator: Callable[[object], VodItem | None] | None = None,
    metadata_scrape_service: object | None = None,
    metadata_binding_repository: object | None = None,
    episode_title_enhancer: Callable[[object], list[PlayItem] | None] | None = None,
    ...
) -> PlayerSession:
    ...
    session = PlayerSession(
        ...
        metadata_hydrator=metadata_hydrator,
        metadata_scrape_service=metadata_scrape_service,
        metadata_binding_repository=metadata_binding_repository,
        episode_title_enhancer=episode_title_enhancer,
        ...
    )
```

Update `src/atv_player/app.py` to share provider construction and create both hydrator and scrape service:

```python
from atv_player.metadata import MetadataBindingRepository, MetadataCache, MetadataContext, MetadataHydrator
from atv_player.metadata.scrape import MetadataScrapeService


class AppCoordinator(QObject):
    def __init__(self, repo: SettingsRepository) -> None:
        ...
        self._metadata_binding_repository = (
            MetadataBindingRepository(repo.database_path)
            if hasattr(repo, "database_path")
            else None
        )

    def _build_metadata_providers(self, *, api_client: ApiClient, config, source_kind: str, raw_detail=None) -> list[object]:
        local_douban_client = LocalDoubanClient(cookie=config.metadata_douban_cookie)
        providers: list[object] = []
        if source_kind == "plugin":
            plugin_payload = self._build_plugin_metadata_payload(raw_detail)
            if plugin_payload is not None:
                providers.append(CustomPluginProvider(plugin_payload))
        providers.append(LocalDoubanProvider(local_douban_client))
        if config.metadata_tmdb_api_key:
            providers.append(TMDBProvider(TMDBClient(api_key=config.metadata_tmdb_api_key)))
        providers.append(RemoteDoubanProvider(api_client))
        return providers

    def _build_metadata_hydrator_factory(self, api_client: ApiClient):
        cache = MetadataCache(app_cache_dir() / "metadata")
        ...
            providers = self._build_metadata_providers(
                api_client=api_client,
                config=config,
                source_kind=source_kind,
                raw_detail=raw_detail,
            )
            hydrator = MetadataHydrator(
                cache=cache,
                providers=providers,
                binding_repository=self._metadata_binding_repository,
            )
            ...

    def _build_metadata_scrape_service_factory(self, api_client: ApiClient):
        cache = MetadataCache(app_cache_dir() / "metadata")
        supported_sources = {"browse", "plugin", "emby", "jellyfin", "feiniu", "bilibili"}

        def factory(*, source_kind: str = "", raw_detail=None):
            if source_kind not in supported_sources:
                return None
            config = self.repo.load_config()
            if not config.metadata_enhancement_enabled:
                return None
            providers = self._build_metadata_providers(
                api_client=api_client,
                config=config,
                source_kind=source_kind,
                raw_detail=raw_detail,
            )
            return MetadataScrapeService(cache=cache, providers=providers)

        return factory
```

Update `src/atv_player/ui/main_window.py` to accept and attach the new factory:

```python
class MainWindow(...):
    def __init__(..., metadata_hydrator_factory=None, metadata_scrape_service_factory=None, metadata_binding_repository=None):
        ...
        self._metadata_hydrator_factory = metadata_hydrator_factory
        self._metadata_scrape_service_factory = metadata_scrape_service_factory
        self._metadata_binding_repository = metadata_binding_repository
```

```python
def _prepare_request_for_open(self, request: OpenPlayerRequest) -> OpenPlayerRequest:
    if request.metadata_scrape_service is None and self._metadata_scrape_service_factory is not None:
        request.metadata_scrape_service = self._metadata_scrape_service_factory(
            source_kind=request.source_kind,
            raw_detail=getattr(request, "raw_detail", None),
        )
    if request.metadata_binding_repository is None:
        request.metadata_binding_repository = self._metadata_binding_repository
    ...
```

- [ ] **Step 4: Run the hydrator binding tests and verify they pass**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "manual_binding" -q`

Expected: PASS with the new manual-binding tests green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/hydrator.py src/atv_player/models.py src/atv_player/controllers/player_controller.py src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_metadata_hydrator.py
git commit -m "feat: prefer manual metadata bindings"
```

### Task 4: Add the player scrape dialog shell

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window shell tests**

```python
def test_player_window_shows_metadata_scrape_button_with_search_icon(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)

    assert window.metadata_scrape_button.toolTip() == "刮削"
    assert window.metadata_scrape_button.isEnabled() is True


def test_player_window_metadata_scrape_dialog_prefills_title_year_and_provider(qtbot) -> None:
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=object(),
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)

    dialog = window._ensure_metadata_scrape_dialog()
    window._open_metadata_scrape_dialog()

    assert dialog.windowTitle() == "刮削"
    assert window._metadata_scrape_title_edit.text() == "深空彼岸"
    assert window._metadata_scrape_year_edit.text() == "2026"
    assert window._metadata_scrape_provider_combo.currentData() == ""
```

- [ ] **Step 2: Run the focused player-window shell tests and verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_scrape_button or metadata_scrape_dialog_prefills" -q`

Expected: FAIL because the button, dialog, and helper methods do not exist yet.

- [ ] **Step 3: Add the button, dialog state, and shell rendering**

Update the `PlayerWindow` constructor state:

```python
self._metadata_scrape_dialog: QDialog | None = None
self._metadata_scrape_title_edit: QLineEdit | None = None
self._metadata_scrape_year_edit: QLineEdit | None = None
self._metadata_scrape_provider_combo: QComboBox | None = None
self._metadata_scrape_group_list: QListWidget | None = None
self._metadata_scrape_result_list: QListWidget | None = None
self._metadata_scrape_status_label: QLabel | None = None
self._metadata_scrape_groups = []
self._metadata_scrape_default_title = ""
self._metadata_scrape_default_year = ""
```

Add the toolbar button near the danmaku controls:

```python
self.metadata_scrape_button = self._create_icon_button("search.svg", "刮削")
```

Wire it into the layout and context menu:

```python
sidebar_actions.addWidget(self.metadata_scrape_button)
self.metadata_scrape_button.clicked.connect(self._open_metadata_scrape_dialog)
```

```python
menu.addAction("刮削", self._open_metadata_scrape_dialog)
```

Add the dialog builder:

```python
def _ensure_metadata_scrape_dialog(self) -> QDialog:
    if self._metadata_scrape_dialog is not None:
        return self._metadata_scrape_dialog
    dialog = QDialog(self)
    dialog.setWindowTitle("刮削")
    dialog.resize(760, 480)
    layout = QVBoxLayout(dialog)

    search_row = QHBoxLayout()
    title_column = QVBoxLayout()
    title_column.addWidget(QLabel("标题", dialog))
    self._metadata_scrape_title_edit = QLineEdit(dialog)
    title_column.addWidget(self._metadata_scrape_title_edit)

    year_column = QVBoxLayout()
    year_column.addWidget(QLabel("年份", dialog))
    self._metadata_scrape_year_edit = QLineEdit(dialog)
    year_column.addWidget(self._metadata_scrape_year_edit)

    provider_column = QVBoxLayout()
    provider_column.addWidget(QLabel("搜索来源", dialog))
    self._metadata_scrape_provider_combo = QComboBox(dialog)
    self._metadata_scrape_provider_combo.addItem("全部", "")
    provider_column.addWidget(self._metadata_scrape_provider_combo)

    search_row.addLayout(title_column, 2)
    search_row.addLayout(year_column, 1)
    search_row.addLayout(provider_column, 1)
    layout.addLayout(search_row)

    columns = QHBoxLayout()
    self._metadata_scrape_group_list = QListWidget(dialog)
    self._metadata_scrape_result_list = QListWidget(dialog)
    columns.addWidget(self._metadata_scrape_group_list, 1)
    columns.addWidget(self._metadata_scrape_result_list, 2)
    layout.addLayout(columns)

    self._metadata_scrape_status_label = QLabel("", dialog)
    layout.addWidget(self._metadata_scrape_status_label)

    actions = QHBoxLayout()
    self._metadata_scrape_rerun_button = QPushButton("重新搜索", dialog)
    self._metadata_scrape_reset_button = QPushButton("恢复默认搜索词", dialog)
    self._metadata_scrape_apply_button = QPushButton("应用结果", dialog)
    actions.addWidget(self._metadata_scrape_rerun_button)
    actions.addWidget(self._metadata_scrape_reset_button)
    actions.addWidget(self._metadata_scrape_apply_button)
    layout.addLayout(actions)

    self._metadata_scrape_dialog = dialog
    return dialog
```

Fill defaults when opening:

```python
def _open_metadata_scrape_dialog(self) -> None:
    if self.session is None or self.session.metadata_scrape_service is None:
        return
    self._metadata_scrape_default_title = str(self.session.vod.vod_name or "").strip()
    self._metadata_scrape_default_year = str(self.session.vod.vod_year or "").strip()
    dialog = self._ensure_metadata_scrape_dialog()
    self._metadata_scrape_title_edit.setText(self._metadata_scrape_default_title)
    self._metadata_scrape_year_edit.setText(self._metadata_scrape_default_year)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
```

- [ ] **Step 4: Run the focused player-window shell tests and verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_scrape_button or metadata_scrape_dialog_prefills" -q`

Expected: PASS with the new shell tests green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add metadata scrape dialog shell"
```

### Task 5: Implement async metadata scrape search and apply flow

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing async scrape interaction tests**

```python
class FakeMetadataScrapeService:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str, str]] = []
        self.apply_calls: list[tuple[str, str]] = []
        self.groups = [
            MetadataScrapeGroup(
                provider="tmdb",
                provider_label="TMDB",
                items=[
                    MetadataScrapeCandidate(
                        provider="tmdb",
                        provider_label="TMDB",
                        provider_id="movie:1",
                        title="深空彼岸",
                        year="2026",
                    )
                ],
            ),
            MetadataScrapeGroup(provider="local_douban", provider_label="本地豆瓣", items=[]),
        ]

    def search(self, query: MetadataQuery, provider_filter: str = "") -> list[MetadataScrapeGroup]:
        self.search_calls.append((query.title, query.year, provider_filter))
        return self.groups

    def apply(self, vod: VodItem, candidate: MetadataScrapeCandidate) -> VodItem:
        self.apply_calls.append((vod.vod_name, candidate.provider_id))
        return VodItem(
            vod_id=vod.vod_id,
            vod_name=vod.vod_name,
            vod_year="2026",
            vod_pic="https://img.example/poster.jpg",
            vod_content="豆瓣简介",
            detail_fields=[PlaybackDetailField(label="TMDB ID", value="1")],
            metadata_field_sources={"poster": "tmdb", "overview": "tmdb", "detail_fields": "tmdb"},
        )


class FakeMetadataBindingRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, str, str, str, str]] = []

    def save(self, title, year, *, provider, provider_id, matched_title="", matched_year="") -> None:
        self.saved.append((title, year, provider, provider_id, matched_title, matched_year))


def test_player_window_metadata_scrape_search_selects_first_result_without_auto_apply(qtbot) -> None:
    service = FakeMetadataScrapeService()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=service,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window._open_metadata_scrape_dialog()

    window._rerun_metadata_scrape_search()

    qtbot.waitUntil(lambda: window._metadata_scrape_result_list.count() == 1, timeout=1000)
    assert window._metadata_scrape_result_list.currentRow() == 0
    assert "原始简介" in window.metadata_view.toPlainText()
    assert service.apply_calls == []


def test_player_window_metadata_scrape_apply_refreshes_metadata_and_saves_binding(qtbot) -> None:
    service = FakeMetadataScrapeService()
    bindings = FakeMetadataBindingRepository()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="深空彼岸", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=service,
        metadata_binding_repository=bindings,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window._open_metadata_scrape_dialog()
    window._rerun_metadata_scrape_search()
    qtbot.waitUntil(lambda: window._metadata_scrape_result_list.count() == 1, timeout=1000)

    window._apply_selected_metadata_scrape_result()

    qtbot.waitUntil(lambda: "豆瓣简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert service.apply_calls == [("深空彼岸", "movie:1")]
    assert bindings.saved == [("深空彼岸", "2026", "tmdb", "movie:1", "深空彼岸", "2026")]
    assert "元数据已更新" in window.log_view.toPlainText()
    assert "已绑定手动刮削结果" in window.log_view.toPlainText()
```

- [ ] **Step 2: Run the focused async scrape tests and verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_scrape_search_selects_first_result_without_auto_apply or metadata_scrape_apply_refreshes_metadata_and_saves_binding" -q`

Expected: FAIL because search/apply handlers, result rendering, and binding save behavior do not exist yet.

- [ ] **Step 3: Implement the async scrape workflow**

Add scrape task signals near the other worker signal types:

```python
class _MetadataScrapeSignals(QObject):
    search_succeeded = Signal(int, object)
    apply_succeeded = Signal(int, object, object)
    failed = Signal(int, str)
```

Initialize state in `PlayerWindow.__init__`:

```python
self._metadata_scrape_signals = _MetadataScrapeSignals()
self._metadata_scrape_signals.search_succeeded.connect(self._handle_metadata_scrape_search_succeeded)
self._metadata_scrape_signals.apply_succeeded.connect(self._handle_metadata_scrape_apply_succeeded)
self._metadata_scrape_signals.failed.connect(self._handle_metadata_scrape_failed)
self._metadata_scrape_request_id = 0
```

Render groups and results:

```python
def _populate_metadata_scrape_groups(self, groups) -> None:
    self._metadata_scrape_groups = list(groups)
    self._metadata_scrape_group_list.clear()
    for group in self._metadata_scrape_groups:
        self._metadata_scrape_group_list.addItem(f"{group.provider_label} ({len(group.items)})")
    if self._metadata_scrape_groups:
        first_non_empty = next(
            (index for index, group in enumerate(self._metadata_scrape_groups) if group.items),
            0,
        )
        self._metadata_scrape_group_list.setCurrentRow(first_non_empty)


def _populate_metadata_scrape_results(self, group_index: int) -> None:
    self._metadata_scrape_result_list.clear()
    if group_index < 0 or group_index >= len(self._metadata_scrape_groups):
        return
    group = self._metadata_scrape_groups[group_index]
    for candidate in group.items:
        label = candidate.title if not candidate.year else f"{candidate.title} ({candidate.year})"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, candidate)
        self._metadata_scrape_result_list.addItem(item)
    if self._metadata_scrape_result_list.count():
        self._metadata_scrape_result_list.setCurrentRow(0)
```

Add search and reset handlers:

```python
def _rerun_metadata_scrape_search(self) -> None:
    if self.session is None or self.session.metadata_scrape_service is None:
        return
    title = self._metadata_scrape_title_edit.text().strip()
    year = self._metadata_scrape_year_edit.text().strip()
    if not title:
        self._metadata_scrape_status_label.setText("当前条目缺少标题")
        return
    provider_filter = str(self._metadata_scrape_provider_combo.currentData() or "")
    self._metadata_scrape_status_label.setText(f"刮削搜索中（{self._metadata_provider_label(provider_filter)}）...")
    self._metadata_scrape_request_id += 1
    request_id = self._metadata_scrape_request_id
    service = self.session.metadata_scrape_service

    def run() -> None:
        try:
            groups = service.search(MetadataQuery(title=title, year=year), provider_filter=provider_filter)
        except Exception as exc:
            if self._is_window_alive():
                self._metadata_scrape_signals.failed.emit(request_id, f"刮削搜索失败: {exc}")
            return
        if self._is_window_alive():
            self._metadata_scrape_signals.search_succeeded.emit(request_id, groups)

    threading.Thread(target=run, daemon=True).start()


def _reset_metadata_scrape_search_query(self) -> None:
    self._metadata_scrape_title_edit.setText(self._metadata_scrape_default_title)
    self._metadata_scrape_year_edit.setText(self._metadata_scrape_default_year)
    self._rerun_metadata_scrape_search()
```

Add apply handler:

```python
def _selected_metadata_scrape_candidate(self):
    current_item = self._metadata_scrape_result_list.currentItem()
    if current_item is None:
        return None
    return current_item.data(Qt.ItemDataRole.UserRole)


def _apply_selected_metadata_scrape_result(self) -> None:
    if self.session is None or self.session.metadata_scrape_service is None:
        return
    candidate = self._selected_metadata_scrape_candidate()
    if candidate is None:
        return
    self._metadata_scrape_request_id += 1
    request_id = self._metadata_scrape_request_id
    service = self.session.metadata_scrape_service
    current_vod = self.session.vod

    def run() -> None:
        try:
            updated_vod = service.apply(current_vod, candidate)
        except Exception as exc:
            if self._is_window_alive():
                self._metadata_scrape_signals.failed.emit(request_id, f"刮削应用失败: {exc}")
            return
        if self._is_window_alive():
            self._metadata_scrape_signals.apply_succeeded.emit(request_id, updated_vod, candidate)

    threading.Thread(target=run, daemon=True).start()
```

Handle search/apply completion:

```python
def _handle_metadata_scrape_search_succeeded(self, request_id: int, groups) -> None:
    if request_id != self._metadata_scrape_request_id:
        return
    self._populate_metadata_scrape_groups(groups)
    self._populate_metadata_scrape_results(self._metadata_scrape_group_list.currentRow())
    self._metadata_scrape_status_label.setText("")


def _handle_metadata_scrape_apply_succeeded(self, request_id: int, updated_vod: VodItem, candidate) -> None:
    if request_id != self._metadata_scrape_request_id or self.session is None:
        return
    previous_vod = self.session.vod
    self.session.vod = updated_vod
    bindings = self.session.metadata_binding_repository
    if bindings is not None and hasattr(bindings, "save"):
        bindings.save(
            previous_vod.vod_name,
            previous_vod.vod_year,
            provider=candidate.provider,
            provider_id=candidate.provider_id,
            matched_title=candidate.title,
            matched_year=candidate.year,
        )
    metadata_log = _build_metadata_update_log(previous_vod, updated_vod)
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()
    self._refresh_window_title()
    if metadata_log:
        self._append_log(metadata_log)
    self._append_log(f"已绑定手动刮削结果: {candidate.title} ({candidate.provider_label})")
    self._metadata_scrape_status_label.setText("")


def _handle_metadata_scrape_failed(self, request_id: int, message: str) -> None:
    if request_id != self._metadata_scrape_request_id:
        return
    self._metadata_scrape_status_label.setText(message)
```

Wire the dialog buttons and group changes:

```python
self._metadata_scrape_rerun_button.clicked.connect(self._rerun_metadata_scrape_search)
self._metadata_scrape_reset_button.clicked.connect(self._reset_metadata_scrape_search_query)
self._metadata_scrape_apply_button.clicked.connect(self._apply_selected_metadata_scrape_result)
self._metadata_scrape_group_list.currentRowChanged.connect(self._populate_metadata_scrape_results)
```

- [ ] **Step 4: Run the focused async scrape tests and verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_scrape_search_selects_first_result_without_auto_apply or metadata_scrape_apply_refreshes_metadata_and_saves_binding" -q`

Expected: PASS with both focused interaction tests green.

- [ ] **Step 5: Run the broader regression slice and commit**

Run: `uv run pytest tests/test_metadata_bindings.py tests/test_metadata_scrape_service.py tests/test_metadata_hydrator.py tests/test_player_window_ui.py -k "metadata_scrape or manual_binding or metadata_hydration" -q`

Expected: PASS with the new metadata scrape and binding coverage green.

Commit:

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player metadata scrape dialog"
```

## Self-Review

### Spec coverage

- `刮削` 对话框入口、字段和按钮：Task 4 and Task 5
- `全部` 并发搜索与 provider 分组：Task 2 and Task 5
- 默认高亮首条但不自动应用：Task 5
- `标题 + 年份` 手动绑定持久化：Task 1 and Task 5
- `MetadataHydrator` 优先复用手动绑定：Task 3
- 绑定失效时删除并回退自动搜索：Task 3

无缺口。

### Placeholder scan

- 没有 `TODO`、`TBD`、`implement later`
- 每个代码步骤都给了具体代码块
- 每个测试步骤都给了实际命令和预期

### Type consistency

- `MetadataBindingRepository` API 固定为 `load/save/delete`
- `MetadataScrapeService` API 固定为 `search/apply`
- `PlayerSession` / `OpenPlayerRequest` 都使用 `metadata_scrape_service` 和 `metadata_binding_repository`
- `PlayerWindow` 统一使用 `_rerun_metadata_scrape_search` 和 `_apply_selected_metadata_scrape_result`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-metadata-scrape-dialog.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
