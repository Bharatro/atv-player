# Asyncio Metadata And Danmaku Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a service-layer `asyncio` coordination path for metadata and danmaku multi-source fetching while keeping the Qt UI layer and existing public synchronous service APIs unchanged.

**Architecture:** Add a narrow async runner layer under metadata and danmaku concurrency helpers, then have existing synchronous service entry points call that layer through short-lived `asyncio.run(...)` boundaries. The first stage does not convert provider interfaces globally or migrate HTTP clients to native async implementations; it adds async orchestration plus sync-provider fallback via `asyncio.to_thread(...)`.

**Tech Stack:** Python 3.12+, asyncio, httpx, PySide6, pytest

---

## File Structure

**Create:**
- `src/atv_player/metadata/async_runner.py`
  Metadata provider orchestration helpers, sync wrapper, and dual-mode async/sync provider dispatch.
- `tests/test_metadata_async_runner.py`
  Unit tests for async metadata orchestration behavior.
- `tests/test_danmaku_provider_concurrency.py`
  Unit tests for the async-backed danmaku settled concurrency helper.

**Modify:**
- `src/atv_player/metadata/hydrator.py`
  Replace `ThreadPoolExecutor` search fan-out with the new async runner while preserving ranking, cache, and merge behavior.
- `src/atv_player/metadata/scrape.py`
  Replace `ThreadPoolExecutor` manual scrape fan-out with the new async runner while preserving cache and error isolation semantics.
- `src/atv_player/danmaku/providers/_concurrency.py`
  Replace per-batch `ThreadPoolExecutor` logic with an async-backed implementation that preserves the existing yielded settled-batch contract.
- `tests/test_metadata_hydrator.py`
  Add integration coverage proving `MetadataHydrator` works with async-capable providers and preserves failure isolation.
- `tests/test_metadata_scrape_service.py`
  Add integration coverage proving `MetadataScrapeService` works with async-capable providers and preserves per-provider error reporting.
- `tests/test_danmaku_service.py`
  Keep existing concurrency and grouping regression tests green after the async-backed helper rewrite.

**Do Not Modify In This Plan:**
- `src/atv_player/ui/*`
- `src/atv_player/metadata/providers/tmdb_client.py`
- `src/atv_player/metadata/providers/bangumi_client.py`
- `src/atv_player/metadata/providers/local_douban_client.py`
- `src/atv_player/danmaku/providers/tencent.py`
- `src/atv_player/danmaku/providers/iqiyi.py`
- `src/atv_player/danmaku/providers/bilibili.py`

Those provider-native async HTTP migrations are explicitly deferred to a follow-up plan after the stage 1 coordinator lands and is measured.

### Task 1: Add the Metadata Async Runner Foundation

**Files:**
- Create: `src/atv_player/metadata/async_runner.py`
- Create: `tests/test_metadata_async_runner.py`

- [ ] **Step 1: Write the failing metadata async-runner tests**

Create `tests/test_metadata_async_runner.py` with these tests:

```python
import asyncio

from atv_player.metadata.async_runner import run_provider_detail, run_provider_searches
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class SyncProvider:
    name = "sync"

    def __init__(self) -> None:
        self.search_calls = 0
        self.detail_calls = 0

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls += 1
        return [MetadataMatch(provider="sync", provider_id="1", title=candidate.title)]

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls += 1
        return MetadataRecord(provider="sync", provider_id=match.provider_id, title=match.title)


class AsyncProvider:
    name = "async"

    def __init__(self) -> None:
        self.search_calls = 0
        self.detail_calls = 0

    async def async_search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        self.search_calls += 1
        await asyncio.sleep(0)
        return [MetadataMatch(provider="async", provider_id="2", title=candidate.title)]

    async def async_get_detail(self, match: MetadataMatch) -> MetadataRecord:
        self.detail_calls += 1
        await asyncio.sleep(0)
        return MetadataRecord(provider="async", provider_id=match.provider_id, title=match.title)


def test_run_provider_searches_uses_async_search_when_available() -> None:
    provider = AsyncProvider()

    results = run_provider_searches([provider], MetadataQuery(title="深空彼岸", year="2026"))

    assert len(results) == 1
    assert results[0].provider is provider
    assert results[0].matches[0].provider == "async"
    assert results[0].error is None
    assert provider.search_calls == 1


def test_run_provider_searches_falls_back_to_sync_search() -> None:
    provider = SyncProvider()

    results = run_provider_searches([provider], MetadataQuery(title="成何体统", year="2026"))

    assert len(results) == 1
    assert results[0].provider is provider
    assert results[0].matches[0].provider == "sync"
    assert results[0].error is None
    assert provider.search_calls == 1


def test_run_provider_detail_uses_async_get_detail_when_available() -> None:
    provider = AsyncProvider()
    match = MetadataMatch(provider="async", provider_id="2", title="牧神记")

    record = run_provider_detail(provider, match)

    assert record.provider == "async"
    assert record.provider_id == "2"
    assert provider.detail_calls == 1


def test_run_provider_searches_collects_provider_error_without_failing_whole_batch() -> None:
    class BrokenProvider(SyncProvider):
        name = "broken"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            raise RuntimeError(f"boom:{candidate.title}")

    good = SyncProvider()
    bad = BrokenProvider()

    results = run_provider_searches([bad, good], MetadataQuery(title="剑来", year=""))

    assert results[0].provider is bad
    assert isinstance(results[0].error, RuntimeError)
    assert results[0].matches == []
    assert results[1].provider is good
    assert results[1].error is None
    assert results[1].matches[0].title == "剑来"
```

- [ ] **Step 2: Run the new metadata async-runner tests to verify they fail**

Run:

```bash
uv run pytest tests/test_metadata_async_runner.py -v
```

Expected:

```text
ERROR tests/test_metadata_async_runner.py
```

The failure should be because `atv_player.metadata.async_runner` does not exist yet.

- [ ] **Step 3: Implement the metadata async-runner module**

Create `src/atv_player/metadata/async_runner.py` with this implementation:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


class _AsyncSearchProvider(Protocol):
    async def async_search(self, candidate: MetadataQuery) -> list[MetadataMatch]: ...


class _AsyncDetailProvider(Protocol):
    async def async_get_detail(self, match: MetadataMatch) -> MetadataRecord: ...


@dataclass(slots=True)
class ProviderSearchResult:
    provider: object
    matches: list[MetadataMatch]
    error: Exception | None = None


async def _search_one(provider: object, query: MetadataQuery, semaphore: asyncio.Semaphore) -> ProviderSearchResult:
    async with semaphore:
        try:
            async_search = getattr(provider, "async_search", None)
            if callable(async_search):
                matches = await async_search(query)
            else:
                matches = await asyncio.to_thread(provider.search, query)
            return ProviderSearchResult(provider=provider, matches=list(matches or []))
        except Exception as exc:
            return ProviderSearchResult(provider=provider, matches=[], error=exc)


async def _get_detail_one(provider: object, match: MetadataMatch) -> MetadataRecord:
    async_get_detail = getattr(provider, "async_get_detail", None)
    if callable(async_get_detail):
        return await async_get_detail(match)
    return await asyncio.to_thread(provider.get_detail, match)


async def _run_provider_searches_async(
    providers: list[object],
    query: MetadataQuery,
    *,
    max_concurrency: int,
) -> list[ProviderSearchResult]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    tasks = [_search_one(provider, query, semaphore) for provider in providers]
    return list(await asyncio.gather(*tasks))


async def _run_provider_detail_async(provider: object, match: MetadataMatch) -> MetadataRecord:
    return await _get_detail_one(provider, match)


def run_provider_searches(
    providers: list[object],
    query: MetadataQuery,
    *,
    max_concurrency: int | None = None,
) -> list[ProviderSearchResult]:
    return asyncio.run(
        _run_provider_searches_async(
            providers,
            query,
            max_concurrency=max_concurrency or max(1, len(providers)),
        )
    )


def run_provider_detail(provider: object, match: MetadataMatch) -> MetadataRecord:
    return asyncio.run(_run_provider_detail_async(provider, match))
```

- [ ] **Step 4: Run the metadata async-runner tests to verify they pass**

Run:

```bash
uv run pytest tests/test_metadata_async_runner.py -v
```

Expected:

```text
PASSED tests/test_metadata_async_runner.py::test_run_provider_searches_uses_async_search_when_available
PASSED tests/test_metadata_async_runner.py::test_run_provider_searches_falls_back_to_sync_search
PASSED tests/test_metadata_async_runner.py::test_run_provider_detail_uses_async_get_detail_when_available
PASSED tests/test_metadata_async_runner.py::test_run_provider_searches_collects_provider_error_without_failing_whole_batch
```

- [ ] **Step 5: Commit the metadata async-runner foundation**

```bash
git add src/atv_player/metadata/async_runner.py tests/test_metadata_async_runner.py
git commit -m "feat: add metadata async runner"
```

### Task 2: Route Metadata Hydration And Scrape Through The Async Runner

**Files:**
- Modify: `src/atv_player/metadata/hydrator.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Modify: `tests/test_metadata_hydrator.py`
- Modify: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write the failing metadata integration tests**

Add this test to `tests/test_metadata_hydrator.py` near the existing `FakeProvider` integration tests:

```python
def test_metadata_hydrator_supports_async_provider_methods(tmp_path: Path) -> None:
    class AsyncProvider:
        name = "tmdb"

        def __init__(self) -> None:
            self.search_calls = 0
            self.detail_calls = 0

        def can_enrich(self, _context: MetadataContext) -> bool:
            return True

        async def async_search(self, candidate):
            self.search_calls += 1
            return [MetadataMatch(provider="tmdb", provider_id="movie:42", title=candidate.title)]

        async def async_get_detail(self, match):
            self.detail_calls += 1
            return MetadataRecord(provider="tmdb", provider_id=match.provider_id, title=match.title, overview="TMDB简介")

    cache = MetadataCache(tmp_path)
    provider = AsyncProvider()
    hydrator = MetadataHydrator(cache=cache, providers=[provider])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_name == "深空彼岸"
    assert updated.vod_content == "TMDB简介"
    assert provider.search_calls == 1
    assert provider.detail_calls == 1
```

Add this test to `tests/test_metadata_scrape_service.py`:

```python
def test_metadata_scrape_service_supports_async_provider_methods(tmp_path: Path) -> None:
    class AsyncProvider:
        name = "tmdb"

        def can_enrich(self, _context) -> bool:
            return True

        async def async_search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [MetadataMatch(provider="tmdb", provider_id="movie:1", title=candidate.title, year=candidate.year)]

        async def async_get_detail(self, match: MetadataMatch) -> MetadataRecord:
            return MetadataRecord(provider="tmdb", provider_id=match.provider_id, title=match.title)

    cache = MetadataCache(tmp_path)
    provider = AsyncProvider()
    service = MetadataScrapeService(cache=cache, providers=[provider])

    groups = service.search(MetadataQuery(title="深空彼岸", year="2026"), provider_filter="")

    assert [group.provider for group in groups] == ["tmdb"]
    assert groups[0].items[0].provider_id == "movie:1"
```

- [ ] **Step 2: Run the focused metadata integration tests to verify they fail**

Run:

```bash
uv run pytest tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py -k "supports_async_provider_methods" -v
```

Expected:

```text
FAILED tests/test_metadata_hydrator.py::test_metadata_hydrator_supports_async_provider_methods
FAILED tests/test_metadata_scrape_service.py::test_metadata_scrape_service_supports_async_provider_methods
```

The failures should come from the current `ThreadPoolExecutor`-based orchestration not calling `async_search` / `async_get_detail`.

- [ ] **Step 3: Replace metadata fan-out with async-runner calls**

Update `src/atv_player/metadata/hydrator.py` imports:

```python
from atv_player.metadata.async_runner import run_provider_detail, run_provider_searches
```

Replace the provider search fan-out in `MetadataHydrator.hydrate(...)`:

```python
search_results = run_provider_searches(
    eligible_providers,
    query,
    max_concurrency=max(1, len(eligible_providers)),
)

ranked_candidates: list[tuple[int, MetadataProvider, MetadataMatch]] = []
for order, result in enumerate(search_results):
    provider = eligible_providers[order]
    if result.error is not None:
        logger.warning(
            "Metadata provider search failed provider=%s",
            provider.name,
            exc_info=result.error,
            extra={"log_category": "metadata", "log_source": "app"},
        )
        continue
    matches = result.matches
    if not matches:
        continue
    best_match = max(matches, key=lambda item: item.score)
    if not is_confident_match(best_match.score):
        continue
    ranked_candidates.append((order, provider, best_match))
```

Update `_load_detail_record(...)`:

```python
try:
    record = run_provider_detail(provider, match)
except Exception as exc:
    logger.warning("Metadata provider detail failed provider=%s", provider.name, exc_info=exc)
    return None
```

Update `src/atv_player/metadata/scrape.py` imports:

```python
from atv_player.metadata.async_runner import run_provider_searches
```

Replace `MetadataScrapeService.search(...)` fan-out:

```python
search_results = run_provider_searches(
    providers,
    query,
    max_concurrency=max(1, len(providers)),
)

groups: list[MetadataScrapeGroup] = []
for provider, result in zip(providers, search_results):
    if result.error is not None:
        groups.append(
            MetadataScrapeGroup(
                provider=provider.name,
                provider_label=self._provider_label(provider.name),
                error_text=str(result.error),
            )
        )
        continue
    matches = [match for match in result.matches if self._is_manual_search_match_compatible(query, match)]
    groups.append(
        MetadataScrapeGroup(
            provider=provider.name,
            provider_label=self._provider_label(provider.name),
            items=[self._candidate_from_match(match) for match in matches],
        )
    )
return groups
```

Keep the existing cache lookup logic inside each per-provider path. Do not change ranking, merge, subtitle extraction, or cache TTL logic.

- [ ] **Step 4: Run the metadata regression tests to verify behavior is unchanged**

Run:

```bash
uv run pytest tests/test_metadata_async_runner.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py -q
```

Expected:

```text
all selected tests passed
```

At minimum, the new async-provider tests plus the existing hydrator/scrape regressions must pass.

- [ ] **Step 5: Commit the metadata integration changes**

```bash
git add src/atv_player/metadata/hydrator.py src/atv_player/metadata/scrape.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py
git commit -m "feat: route metadata fan-out through asyncio runner"
```

### Task 3: Replace Danmaku Settled Thread Pools With An Async-Backed Helper

**Files:**
- Modify: `src/atv_player/danmaku/providers/_concurrency.py`
- Create: `tests/test_danmaku_provider_concurrency.py`
- Verify: `tests/test_danmaku_service.py`

- [ ] **Step 1: Write the failing danmaku concurrency helper tests**

Create `tests/test_danmaku_provider_concurrency.py` with these tests:

```python
import threading
import time

from atv_player.danmaku.providers._concurrency import iter_bounded_settled


def test_iter_bounded_settled_preserves_batch_shape_for_sync_worker() -> None:
    rows = [1, 2, 3, 4, 5]

    batches = list(iter_bounded_settled(rows, lambda value: value * 10, max_workers=2))

    assert [[item.value for item in batch] for batch in batches] == [
        [10, 20],
        [30, 40],
        [50],
    ]


def test_iter_bounded_settled_limits_sync_worker_concurrency() -> None:
    state = {"active": 0, "max_active": 0}
    lock = threading.Lock()

    def worker(value: int) -> int:
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return value

    list(iter_bounded_settled([1, 2, 3, 4, 5], worker, max_workers=3))

    assert state["max_active"] == 3


def test_iter_bounded_settled_collects_async_worker_errors() -> None:
    async def worker(value: int) -> int:
        if value == 2:
            raise RuntimeError("boom")
        return value * 100

    batches = list(iter_bounded_settled([1, 2, 3], worker, max_workers=2))

    assert batches[0][0].value == 100
    assert isinstance(batches[0][1].error, RuntimeError)
    assert batches[1][0].value == 300
```

- [ ] **Step 2: Run the danmaku concurrency helper tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_provider_concurrency.py -v
```

Expected:

```text
FAILED tests/test_danmaku_provider_concurrency.py::test_iter_bounded_settled_collects_async_worker_errors
```

The current helper only supports `ThreadPoolExecutor` + synchronous workers.

- [ ] **Step 3: Rewrite the danmaku concurrency helper with an async internal engine**

Update `src/atv_player/danmaku/providers/_concurrency.py` to this structure:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_SEGMENT_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class SettledResult(Generic[R]):
    value: R | None = None
    error: BaseException | None = None


async def _run_worker(worker: Callable[[T], R] | Callable[[T], Awaitable[R]], row: T) -> R:
    if asyncio.iscoroutinefunction(worker):
        return await worker(row)
    return await asyncio.to_thread(worker, row)


async def _iter_bounded_settled_async(
    items: list[T],
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    *,
    max_workers: int,
) -> list[list[SettledResult[R]]]:
    semaphore = asyncio.Semaphore(max(1, max_workers))

    async def run_one(row: T) -> SettledResult[R]:
        async with semaphore:
            try:
                return SettledResult(value=await _run_worker(worker, row))
            except BaseException as exc:
                return SettledResult(error=exc)

    settled_rows = list(await asyncio.gather(*(run_one(row) for row in items)))
    batch_size = max(1, max_workers)
    return [
        settled_rows[start : start + batch_size]
        for start in range(0, len(settled_rows), batch_size)
    ]


def iter_bounded_settled(
    items: Iterable[T],
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    *,
    max_workers: int = DEFAULT_SEGMENT_CONCURRENCY,
) -> Iterator[list[SettledResult[R]]]:
    rows = list(items)
    if not rows:
        return
    for batch in asyncio.run(
        _iter_bounded_settled_async(rows, worker, max_workers=max_workers)
    ):
        yield batch
```

The public `iter_bounded_settled(...)` signature and yielded batch contract must stay unchanged for existing danmaku providers and `DanmakuService`.

- [ ] **Step 4: Run danmaku helper and service regressions**

Run:

```bash
uv run pytest tests/test_danmaku_provider_concurrency.py tests/test_danmaku_service.py -q
```

Expected:

```text
all selected tests passed
```

The existing `test_search_danmu_searches_providers_with_max_concurrency_of_four` in `tests/test_danmaku_service.py` must remain green.

- [ ] **Step 5: Commit the danmaku concurrency rewrite**

```bash
git add src/atv_player/danmaku/providers/_concurrency.py tests/test_danmaku_provider_concurrency.py tests/test_danmaku_service.py
git commit -m "feat: back danmaku concurrency with asyncio"
```

### Task 4: Run The Focused Stage 1 Regression Suite

**Files:**
- Verify only: `tests/test_metadata_async_runner.py`
- Verify only: `tests/test_metadata_hydrator.py`
- Verify only: `tests/test_metadata_scrape_service.py`
- Verify only: `tests/test_danmaku_provider_concurrency.py`
- Verify only: `tests/test_danmaku_service.py`

- [ ] **Step 1: Run the full focused stage 1 test suite**

Run:

```bash
uv run pytest \
  tests/test_metadata_async_runner.py \
  tests/test_metadata_hydrator.py \
  tests/test_metadata_scrape_service.py \
  tests/test_danmaku_provider_concurrency.py \
  tests/test_danmaku_service.py \
  -q
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 2: Run a broader smoke suite for nearby regressions**

Run:

```bash
uv run pytest tests/test_metadata_tmdb_client.py tests/test_metadata_bangumi_provider.py tests/test_metadata_douban_provider.py tests/test_danmaku_tencent_provider.py -q
```

Expected:

```text
all selected tests passed
```

## Scope Notes

- This plan intentionally stops before native async HTTP provider migration.
- `TMDBClient`, `BangumiClient`, `LocalDoubanClient`, and danmaku provider-native async HTTP conversion should be planned separately after stage 1 lands and is measured.
- The Qt UI thread model remains unchanged in this plan.
