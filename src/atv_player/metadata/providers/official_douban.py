from __future__ import annotations

import re

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.providers.douban import _official_link_detail_fields, _split_people, clean_overview_text
from atv_player.metadata.providers.official_douban_client import DoubanBlockedError


class OfficialDoubanProvider:
    name = "official_douban"

    def __init__(self, local_client) -> None:
        self._local_client = local_client

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if candidate.vod_dbid:
            return [
                MetadataMatch(
                    provider=self.name,
                    provider_id=str(candidate.vod_dbid),
                    title=candidate.title,
                    year=candidate.year,
                )
            ]
        if not candidate.title:
            return []
        try:
            items = self._local_client.search(candidate.title, year=candidate.year)
        except DoubanBlockedError:
            return []
        matches: list[MetadataMatch] = []
        for item in items:
            provider_id = str(item.get("id") or "").strip()
            if not provider_id:
                continue
            matches.append(
                MetadataMatch(
                    provider=self.name,
                    provider_id=provider_id,
                    title=str(item.get("title") or item.get("name") or "").strip(),
                    year=str(item.get("year") or "").strip(),
                )
            )
        return matches

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        try:
            payload = self._local_client.get_detail(match.provider_id)
        except DoubanBlockedError:
            payload = None
        if payload is None:
            raise RuntimeError("local douban detail missing")
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or match.provider_id),
            title=str(payload.get("name") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("cover") or "").strip(),
            overview=clean_overview_text(str(payload.get("description") or "")),
            rating=str(payload.get("dbScore") or "").strip(),
            actors=_split_people(payload.get("actors")),
            directors=_split_people(payload.get("directors") or payload.get("director")),
            genres=[
                part.strip()
                for part in re.split(r"[,/]", str(payload.get("genre") or ""))
                if part.strip()
            ],
            country=str(payload.get("country") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            douban_id=int(payload.get("id") or 0),
            detail_fields=_official_link_detail_fields(payload),
        )
