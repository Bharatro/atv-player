from __future__ import annotations

import re

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.providers.douban import _official_link_detail_fields, _split_people, clean_overview_text


def _normalize_search_title(title: object) -> str:
    text = str(title or "").strip()
    if not text:
        return ""
    return re.sub(
        r"(?<=\S)(第\s*[0-9零一二两三四五六七八九十百]+\s*季)\s*$",
        r" \1",
        text,
        flags=re.IGNORECASE,
    )


class LocalDoubanProvider:
    name = "local_douban"

    def __init__(self, api_client) -> None:
        self._api_client = api_client

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
        payload = self._api_client.search_douban_metadata(_normalize_search_title(candidate.title), year=candidate.year)
        items = payload.get("items") or payload.get("content") or payload.get("records") or []
        matches: list[MetadataMatch] = []
        for item in items:
            provider_id = str(item.get("id") or item.get("dbid") or "").strip()
            if not provider_id:
                continue
            matches.append(
                MetadataMatch(
                    provider=self.name,
                    provider_id=provider_id,
                    title=str(item.get("name") or item.get("title") or "").strip(),
                    year=str(item.get("year") or "").strip(),
                )
            )
        return matches

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = self._api_client.get_douban_metadata_detail(match.provider_id)
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or payload.get("dbid") or match.provider_id),
            title=str(payload.get("name") or payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("cover") or payload.get("poster") or "").strip(),
            overview=clean_overview_text(str(payload.get("description") or payload.get("intro") or "")),
            rating=str(payload.get("dbScore") or payload.get("rating") or "").strip(),
            actors=_split_people(payload.get("actors")),
            directors=_split_people(payload.get("directors") or payload.get("director")),
            genres=[
                part.strip()
                for part in re.split(r"[,/]", str(payload.get("genre") or ""))
                if part.strip()
            ],
            country=str(payload.get("country") or payload.get("region") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            douban_id=int(payload.get("id") or payload.get("dbid") or 0),
            detail_fields=_official_link_detail_fields(payload),
        )
