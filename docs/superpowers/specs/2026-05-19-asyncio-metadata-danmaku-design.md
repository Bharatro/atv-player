# asyncio Metadata And Danmaku Design

## Goal

Introduce `asyncio` where it can improve multi-source metadata and danmaku fetching without pulling the Qt UI layer or the whole codebase into an async-first architecture.

This design is intentionally limited to the service layer that coordinates multiple providers. The first stage should reduce thread-heavy coordination, improve concurrency control, and create a clean path for gradually migrating high-value providers to native async HTTP.

## Non-Goals

- Do not replace the Qt event loop with an `asyncio`-integrated main loop.
- Do not convert every provider interface to `async def` in one pass.
- Do not change plugin compatibility contracts in this stage.
- Do not optimize CPU-bound parsing, scoring, XML/HTML processing, or merge logic in this stage.

## Current Problems

The current code already performs concurrent I/O, but the concurrency model is fragmented:

- metadata aggregation uses `ThreadPoolExecutor`
- danmaku segment fetchers use thread-batched settled execution
- many provider calls still perform synchronous HTTP
- error handling and concurrency limits are repeated across layers

This works, but the model scales poorly as more providers and multi-request sources are added. The biggest issues are:

- high tail latency when several remote providers are slow
- unnecessary thread usage for I/O-bound work
- duplicated concurrency helpers
- no clean migration path from sync provider methods to async HTTP clients

## Proposed Approach

Use a staged async coordination model.

Stage 1 keeps current public synchronous entry points such as metadata hydrate/search and danmaku service flows. Inside those synchronous methods, move provider fan-out and bounded concurrent execution into short-lived `asyncio` runners.

The runner layer should:

- schedule provider work with `asyncio.gather`
- use `asyncio.Semaphore` for bounded concurrency
- prefer native async provider methods when available
- fall back to `asyncio.to_thread(...)` for existing synchronous providers
- preserve current result semantics and business rules

This creates an internal async service layer without forcing the UI layer or plugin-facing provider contracts to become async immediately.

## Architecture

### 1. Async coordination helpers

Add small internal helpers for service-layer fan-out:

- `atv_player.metadata.async_runner`
- `atv_player.danmaku.providers.async_runner`

The helpers should provide functions like:

- `run_provider_searches(...)`
- `run_provider_details(...)`
- `iter_bounded_settled_async(...)`

These helpers own concurrency orchestration only. They should not contain ranking, matching, merge, or provider-specific parsing logic.

### 2. Sync-compatible service entry points

Existing synchronous service methods stay synchronous to their callers:

- `MetadataHydrator.hydrate(...)`
- metadata scrape search/apply flows
- danmaku service/provider entry flows that currently return synchronously

Internally, these methods call the async coordination helpers through a short-lived event loop boundary. This should remain local to the service layer. The UI must not need to know whether the underlying provider fan-out is thread-based or async-based.

### 3. Dual-mode provider execution

Provider execution should use a capability check:

- if a provider exposes `async_search` / `async_get_detail`, await it directly
- otherwise, execute existing sync `search` / `get_detail` with `asyncio.to_thread(...)`

This preserves backward compatibility while allowing incremental conversion of selected providers.

### 4. Shared async HTTP for high-value providers

After the coordinator exists, migrate high-value network-bound providers first:

- metadata: `tmdb_client`, `bangumi_client`, `local_douban_client`
- danmaku: `tencent`, `iqiyi`, `bilibili`

These providers should use a shared `httpx.AsyncClient` strategy within the service lifetime that needs them, rather than creating ad hoc per-request clients. This is where most real async performance gains will come from.

## Data Flow

### Metadata hydrate

1. Build and normalize the query exactly as today.
2. Keep current cache checks and bound-record short-circuit behavior.
3. Fan out provider match loading through an async runner.
4. For each provider:
   - use cache if present
   - otherwise run `async_search` or `to_thread(search)`
5. Keep current ranking and compatibility filtering logic unchanged.
6. Load detail records through the same async-capable runner model.
7. Keep current merge order, media-kind checks, and visual override behavior unchanged.

### Metadata manual scrape search

1. Keep the current public synchronous API.
2. Fan out provider searches via `gather`.
3. Preserve per-provider error isolation and the current `MetadataScrapeGroup` contract.
4. Preserve current cache-only mode behavior.

### Danmaku multi-segment fetching

1. Replace thread-batched settled execution helper usage with an async settled helper.
2. Keep the current settled result contract:
   - success and failure are both collected
   - partial success remains valid
3. Use bounded concurrency with `Semaphore` rather than short-lived thread pools per batch.

## Error Handling

Behavior must remain stable for callers:

- one provider failing must not fail the whole metadata aggregation flow
- one danmaku segment failing must not discard successful segment results
- timeout, transport, and parse failures should continue to be logged and collapsed into the same external results the code returns today

The async layer should not reinterpret provider failures. It should only:

- gather results
- bound concurrency
- normalize async and sync execution paths into the same result shape

## Event Loop Strategy

This design intentionally avoids a long-lived global `asyncio` loop tied to Qt.

Rules:

- do not replace the application event loop
- do not rely on `qasync` in this stage
- do not keep a global service loop running in the UI thread

Instead:

- synchronous service entry points create a local async execution boundary
- async work stays inside that boundary
- UI code continues using existing worker threads and signal delivery

This minimizes risk and keeps the async change isolated to provider coordination.

## Concurrency Policy

- provider-level fan-out uses `asyncio.gather`
- concurrency must be bounded with `Semaphore`
- per-provider or per-source limits should remain configurable in code, not hard-coded across many call sites
- cache hits should bypass network concurrency and return immediately

The first stage should prefer modest defaults over aggressive fan-out. Stability is more important than chasing the highest possible parallelism.

## Migration Plan

### Stage 1

- add async coordination helpers
- route metadata hydrate/search through async fan-out
- route danmaku settled batching through async fan-out
- keep existing provider interfaces and tests largely intact

### Stage 2

- migrate selected high-value providers to native async HTTP
- reduce `to_thread(...)` usage on the hottest paths
- centralize async HTTP client lifecycle where practical

### Stage 3

- evaluate whether additional provider interfaces should formally expose async methods
- only expand further if measured gains justify the larger surface-area change

## Testing

### Unit tests

Add focused tests for the async coordination layer:

- async provider path is awaited directly
- sync provider path falls back to `asyncio.to_thread(...)`
- concurrency limit is respected
- per-provider exception isolation is preserved
- settled result collection preserves partial success behavior

### Regression tests

Existing metadata and danmaku tests must continue to pass without changing their external expectations. The purpose of the first stage is architectural and performance-oriented, not behavioral.

### Performance checks

Add at least one targeted benchmark-style test or local measurement harness for:

- multi-provider metadata search under mocked latency
- danmaku multi-segment fetch under mocked latency

The expected result is not a dramatic single-request speedup. The expected result is lower coordination overhead and better total latency under concurrent remote I/O.

## Risks

- introducing async wrappers around mostly sync providers can add complexity before full async provider migration happens
- careless event-loop usage could leak async concerns into the UI layer
- converting provider internals too broadly in stage 1 would create unnecessary churn

These risks are controlled by keeping stage 1 narrow and preserving current public synchronous service contracts.

## Recommendation

Proceed with stage 1 only:

- build async coordination helpers
- integrate them into metadata hydrate/search and danmaku settled fan-out
- keep UI and provider public contracts stable

This is the smallest change that creates real future leverage and should produce measurable improvement on multi-source I/O paths without destabilizing the desktop application architecture.
