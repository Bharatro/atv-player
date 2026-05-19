from __future__ import annotations

import asyncio
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
