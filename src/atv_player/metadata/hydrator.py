from __future__ import annotations

from dataclasses import replace
import logging

from atv_player.metadata.base import MetadataProvider
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.merge import merge_metadata_record
from atv_player.metadata.models import MetadataContext, MetadataMatch
from atv_player.models import VodItem

logger = logging.getLogger(__name__)

_SEARCH_CACHE_TTL_SECONDS = 7 * 24 * 3600
_EMPTY_SEARCH_CACHE_TTL_SECONDS = 3600
_DETAIL_CACHE_TTL_SECONDS = 7 * 24 * 3600


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
        cached = self._cache.load_detail(
            binding.provider,
            binding.provider_id,
            ttl_seconds=_DETAIL_CACHE_TTL_SECONDS,
        )
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
            if not provider.can_enrich(context):
                continue
            search_cache_key = getattr(provider, "search_cache_key", None)
            cache_title = query.title
            cache_year = query.year
            if callable(search_cache_key):
                provider_cache_key = search_cache_key(query)
                if provider_cache_key is not None:
                    cache_title, cache_year = provider_cache_key
            matches = self._cache.load_search(
                provider.name,
                cache_title,
                cache_year,
                ttl_seconds=_SEARCH_CACHE_TTL_SECONDS,
                empty_ttl_seconds=_EMPTY_SEARCH_CACHE_TTL_SECONDS,
            )
            if matches is None:
                try:
                    matches = provider.search(query)
                except Exception as exc:
                    logger.warning("Metadata provider search failed provider=%s", provider.name, exc_info=exc)
                    continue
                self._cache.save_search(provider.name, cache_title, cache_year, matches)
            if not matches:
                continue
            cached = self._cache.load_detail(
                provider.name,
                str(matches[0].provider_id),
                ttl_seconds=_DETAIL_CACHE_TTL_SECONDS,
            )
            if cached is not None:
                merge_metadata_record(vod, cached, provider_priority=[item.name for item in self._providers])
                continue
            try:
                record = provider.get_detail(matches[0])
            except Exception as exc:
                logger.warning("Metadata provider detail failed provider=%s", provider.name, exc_info=exc)
                continue
            self._cache.save_detail(provider.name, str(matches[0].provider_id), record)
            merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
        return vod
