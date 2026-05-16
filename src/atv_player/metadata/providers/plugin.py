from __future__ import annotations

from collections.abc import Mapping
import re

from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery, MetadataRecord


def _split_csv(value: object) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[,/]", str(value or ""))
        if part.strip()
    ]


class CustomPluginProvider:
    name = "plugin"

    def __init__(self, payload: Mapping[str, object] | None = None) -> None:
        self._payload = payload

    def can_enrich(self, _context: MetadataContext) -> bool:
        return self._payload is not None

    def search(self, _candidate: MetadataQuery) -> list[MetadataMatch]:
        if self._payload is None:
            return []
        provider_id = str(self._payload.get("id") or self._payload.get("provider_id") or "plugin").strip()
        title = str(self._payload.get("title") or "").strip()
        return [MetadataMatch(provider=self.name, provider_id=provider_id, title=title)] if provider_id else []

    def get_detail(self, _match: MetadataMatch) -> MetadataRecord:
        assert self._payload is not None
        return self.record_from_payload(self._payload)

    def record_from_payload(self, payload: Mapping[str, object]) -> MetadataRecord:
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or ""),
            title=str(payload.get("title") or ""),
            year=str(payload.get("year") or ""),
            poster=str(payload.get("poster") or payload.get("cover") or ""),
            overview=str(payload.get("overview") or ""),
            rating=str(payload.get("rating") or ""),
            actors=_split_csv(payload.get("actors")),
            directors=_split_csv(payload.get("directors") or payload.get("director")),
            genres=_split_csv(payload.get("genre") or payload.get("genres")),
            country=str(payload.get("country") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            imdb_id=str(payload.get("imdb_id") or ""),
            tmdb_id=str(payload.get("tmdb_id") or ""),
            detail_fields=list(payload.get("detail_fields") or []),
        )
