from __future__ import annotations

from dataclasses import replace

from atv_player.metadata.base import MetadataProvider
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.merge import merge_metadata_record
from atv_player.metadata.models import MetadataContext
from atv_player.models import VodItem


class MetadataHydrator:
    def __init__(self, cache: MetadataCache, providers: list[MetadataProvider]) -> None:
        self._cache = cache
        self._providers = providers

    def hydrate(self, context: MetadataContext) -> VodItem:
        vod = replace(context.vod)
        for provider in self._providers:
            if not provider.can_enrich(context):
                continue
            matches = provider.search(context.to_query())
            if not matches:
                continue
            cached = self._cache.load_detail(provider.name, str(matches[0].provider_id), ttl_seconds=7 * 24 * 3600)
            if cached is not None:
                merge_metadata_record(vod, cached, provider_priority=[item.name for item in self._providers])
                continue
            record = provider.get_detail(matches[0])
            self._cache.save_detail(provider.name, str(matches[0].provider_id), record)
            merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
        return vod
