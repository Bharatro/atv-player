from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


@dataclass(slots=True)
class ProviderSearchResult:
    provider: object
    matches: list[MetadataMatch]
    error: Exception | None = None


async def _search_one(
    provider: object,
    query: MetadataQuery,
    semaphore: asyncio.Semaphore,
) -> ProviderSearchResult:
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


def _run_async_entrypoint(async_fn, /, *args, **kwargs):
    async def runner():
        return await async_fn(*args, **kwargs)

    return asyncio.run(runner())


def _run_provider_search(provider: object, query: MetadataQuery) -> ProviderSearchResult:
    async_search = getattr(provider, "async_search", None)
    try:
        if callable(async_search):
            matches = _run_async_entrypoint(async_search, query)
        else:
            matches = provider.search(query)
        return ProviderSearchResult(provider=provider, matches=list(matches or []))
    except Exception as exc:
        return ProviderSearchResult(provider=provider, matches=[], error=exc)


def run_provider_searches(
    providers: list[object],
    query: MetadataQuery,
    *,
    max_concurrency: int | None = None,
) -> list[ProviderSearchResult]:
    concurrency = max(1, max_concurrency or len(providers))
    if concurrency == 1 or len(providers) <= 1:
        return [_run_provider_search(provider, query) for provider in providers]
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_run_provider_search, provider, query) for provider in providers]
        return [future.result() for future in futures]


def run_provider_detail(provider: object, match: MetadataMatch) -> MetadataRecord:
    async_get_detail = getattr(provider, "async_get_detail", None)
    if callable(async_get_detail):
        return _run_async_entrypoint(async_get_detail, match)
    return provider.get_detail(match)
