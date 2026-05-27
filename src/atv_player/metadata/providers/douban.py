from __future__ import annotations

import re

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord
from atv_player.metadata.providers.official_douban_client import DoubanBlockedError


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


def _split_aliases(value: object) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[/]", str(value or ""))
        if part.strip()
    ]


def _official_link_detail_fields(payload: dict[str, object]) -> list[dict[str, object]]:
    links = payload.get("official_links")
    if not isinstance(links, list) or not links:
        return []
    normalized = [dict(item) for item in links if isinstance(item, dict)]
    return [{"label": "official_links", "value": normalized}] if normalized else []


def _extra_detail_fields(payload: dict[str, object]) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for label, key in (
        ("编剧", "screenwriter"),
        ("首播", "first_air_date"),
        ("上映日期", "release_date"),
        ("集数", "episode_count"),
        ("片长", "duration"),
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            fields.append({"label": label, "value": value})
    return fields


class DoubanProvider:
    name = "douban"

    def __init__(self, api_client, cache: MetadataCache | None = None, local_client=None) -> None:
        self._api_client = api_client
        self._cache = cache
        self._local_client = local_client

    def can_enrich(self, _context) -> bool:
        return True

    def _match_from_payload(self, item: dict[str, object]) -> MetadataMatch | None:
        provider_id = str(item.get("id") or item.get("dbid") or "").strip()
        if not provider_id:
            return None
        return MetadataMatch(
            provider=self.name,
            provider_id=provider_id,
            title=str(item.get("name") or item.get("title") or "").strip(),
            year=str(item.get("year") or "").strip(),
            score=0.0,
            raw=dict(item),
        )

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
        local_items: list[dict[str, object]] = []
        if self._local_client is not None:
            try:
                local_items = self._local_client.search(candidate.title, year=candidate.year)
            except DoubanBlockedError:
                local_items = []
        if local_items:
            matches = [
                match
                for match in (self._match_from_payload(item) for item in local_items)
                if match is not None
            ]
            if matches:
                return matches
        payload = self._api_client.search_douban_metadata(candidate.title, year=candidate.year)
        items = payload.get("items") or payload.get("content") or payload.get("records") or []
        matches: list[MetadataMatch] = []
        for item in items:
            match = self._match_from_payload(item)
            if match is not None:
                matches.append(match)
        return matches

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = None
        if self._local_client is not None:
            try:
                payload = self._local_client.get_detail(match.provider_id)
            except DoubanBlockedError:
                payload = None
        if payload is None:
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
            aliases=_split_aliases(payload.get("aliases")),
            imdb_id=str(payload.get("imdb_id") or "").strip(),
            douban_id=int(payload.get("id") or payload.get("dbid") or 0),
            detail_fields=[*_official_link_detail_fields(payload), *_extra_detail_fields(payload)],
        )
