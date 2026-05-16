from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import logging

from atv_player.metadata.base import MetadataProvider
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.matching import is_confident_match, score_match
from atv_player.metadata.merge import fill_missing_metadata_record, merge_metadata_record
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

    def _load_provider_matches(self, provider: MetadataProvider, query) -> list[MetadataMatch]:
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
                return []
            self._cache.save_search(provider.name, cache_title, cache_year, matches)
        return [replace(match, score=max(float(match.score or 0.0), score_match(query, match))) for match in matches]

    def _load_detail_record(self, provider: MetadataProvider, match: MetadataMatch):
        cached = self._cache.load_detail(
            provider.name,
            str(match.provider_id),
            ttl_seconds=_DETAIL_CACHE_TTL_SECONDS,
        )
        if cached is not None:
            return cached
        try:
            record = provider.get_detail(match)
        except Exception as exc:
            logger.warning("Metadata provider detail failed provider=%s", provider.name, exc_info=exc)
            return None
        self._cache.save_detail(provider.name, str(match.provider_id), record)
        return record

    def hydrate(self, context: MetadataContext) -> VodItem:
        vod = replace(context.vod)
        query = context.to_query()
        bound_record = self._load_bound_record(query)
        if bound_record is not None:
            merge_metadata_record(vod, bound_record, provider_priority=[item.name for item in self._providers])
            return vod
        eligible_providers = [provider for provider in self._providers if provider.can_enrich(context)]
        if not eligible_providers:
            return vod

        with ThreadPoolExecutor(max_workers=max(1, len(eligible_providers))) as executor:
            futures = [executor.submit(self._load_provider_matches, provider, query) for provider in eligible_providers]

        ranked_candidates: list[tuple[int, MetadataProvider, MetadataMatch]] = []
        for order, (provider, future) in enumerate(zip(eligible_providers, futures)):
            matches = future.result()
            if not matches:
                continue
            best_match = max(matches, key=lambda item: item.score)
            if not is_confident_match(best_match.score):
                continue
            ranked_candidates.append((order, provider, best_match))

        primary_applied = False
        for order, provider, match in sorted(ranked_candidates, key=lambda item: (-item[2].score, item[0])):
            del order
            record = self._load_detail_record(provider, match)
            if record is None:
                continue
            if not primary_applied:
                merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
                primary_applied = True
                continue
            fill_missing_metadata_record(vod, record)
        return vod
