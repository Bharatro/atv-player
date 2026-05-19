from __future__ import annotations

from atv_player.metadata.models import MetadataQuery


def provider_search_cache_key(provider: object, query: MetadataQuery) -> tuple[str, str]:
    cache_title = query.title
    cache_year = query.year
    search_cache_key = getattr(provider, "search_cache_key", None)
    if callable(search_cache_key):
        provider_cache_key = search_cache_key(query)
        if provider_cache_key is not None:
            cache_title, cache_year = provider_cache_key
    return cache_title, cache_year
