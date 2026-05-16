from __future__ import annotations

import re

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


def clean_overview_text(value: str) -> str:
    cleaned = str(value or "")
    cleaned = cleaned.replace("[展开全部]", " ").replace("[收起部分]", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"(?<=[。！？])\s+", cleaned)
    deduped: list[str] = []
    for part in parts:
        normalized = part.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    collapsed = "".join(deduped)
    if not collapsed:
        return ""
    repeated = re.fullmatch(r"(.+?)\s*\1+", collapsed)
    if repeated is not None:
        return repeated.group(1).strip()
    return collapsed


def _split_people(value: object) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[,/]", str(value or ""))
        if part.strip()
    ]


class DoubanProvider:
    name = "douban"

    def __init__(self, api_client, cache: MetadataCache | None = None) -> None:
        self._api_client = api_client
        self._cache = cache

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if candidate.vod_dbid:
            return [
                MetadataMatch(
                    provider=self.name,
                    provider_id=candidate.vod_dbid,
                    title=candidate.title,
                    year=candidate.year,
                )
            ]
        if not candidate.title:
            return []
        payload = self._api_client.search_douban_metadata(candidate.title, year=candidate.year)
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
                    score=0.0,
                    raw=dict(item),
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
        )
