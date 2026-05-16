from __future__ import annotations

from typing import Protocol

from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery, MetadataRecord


class MetadataProvider(Protocol):
    name: str

    def can_enrich(self, context: MetadataContext) -> bool: ...
    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]: ...
    def get_detail(self, match: MetadataMatch) -> MetadataRecord: ...
