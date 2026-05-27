from __future__ import annotations

import re

from atv_player.metadata.matching import is_confident_match, score_match
from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataQuery, MetadataRecord

_ANIME_CATEGORY_TOKENS = ("动漫", "动画", "番剧", "acg", "anime")
_DIRECTOR_RELATION_TOKENS = ("导演", "监督", "系列构成")
_ALIAS_INFOBOX_KEYS = ("别名", "原名", "中文名")


def _normalize_title(value: object) -> str:
    return re.sub(r"[\s\-_:.：,，/\\|·•'\"`()（）《》【】\[\]]+", "", str(value or "").strip().lower())


def _strip_search_season_suffix(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = re.sub(
        r"(?:\s*[-:：]\s*)?(?:第\s*[0-9零一二两三四五六七八九十百千]+\s*季|season\s*\d+|s\d+)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or text


def _extract_year(value: object) -> str:
    match = re.search(r"(\d{4})", str(value or "").strip())
    return match.group(1) if match else ""


def _flatten_infobox_value(value: object) -> list[str]:
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_infobox_value(item))
        return flattened
    if isinstance(value, dict):
        return _flatten_infobox_value(value.get("v") or value.get("value") or value.get("name"))
    text = str(value or "").strip()
    return [text] if text else []


def _subject_aliases(payload: dict[str, object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        text = str(value or "").strip()
        normalized = _normalize_title(text)
        if not normalized or normalized in seen:
            return
        ordered.append(text)
        seen.add(normalized)

    add(payload.get("name"))
    add(payload.get("name_cn"))
    for item in payload.get("infobox") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key not in _ALIAS_INFOBOX_KEYS:
            continue
        for alias in _flatten_infobox_value(item.get("value")):
            add(alias)
    return ordered


def is_bangumi_anime_query(query: MetadataQuery) -> bool:
    values = " ".join(
        value.strip().lower()
        for value in (str(query.category_name or ""), str(query.type_name or ""))
        if value and value.strip()
    )
    return any(token in values for token in _ANIME_CATEGORY_TOKENS)


class BangumiMetadataProvider:
    name = "bangumi"

    def __init__(self, client) -> None:
        self._client = client

    def can_enrich(self, context: MetadataContext) -> bool:
        return is_bangumi_anime_query(context.to_query())

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str] | None:
        return (_strip_search_season_suffix(candidate.title), _extract_year(candidate.year))

    def _search_rows(self, title: str, year: str = "") -> list[dict[str, object]]:
        candidates = [title]
        stripped = _strip_search_season_suffix(title)
        if stripped and stripped != title:
            candidates.append(stripped)
        normalized_year = _extract_year(year)
        if normalized_year:
            candidates.extend(
                f"{candidate} {normalized_year}"
                for candidate in list(candidates)
            )
        seen: set[str] = set()
        for keyword in candidates:
            keyword = keyword.strip()
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            rows = self._client.search_subjects(keyword)
            if rows:
                return rows
        return []

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        title = str(candidate.title or "").strip()
        if not title:
            return []
        is_anime = is_bangumi_anime_query(candidate)
        matches: list[MetadataMatch] = []
        for row in self._search_rows(title, candidate.year):
            subject_type = int(row.get("type") or 0)
            if is_anime and subject_type != 2:
                continue
            match_title = str(row.get("name_cn") or row.get("name") or "").strip()
            if not match_title:
                continue
            raw = dict(row)
            raw["aliases"] = _subject_aliases(raw)
            raw["categories"] = ["动漫"] if subject_type == 2 else []
            images = row.get("images")
            if isinstance(images, dict):
                poster = str(images.get("large") or images.get("common") or images.get("grid") or "").strip()
                if poster:
                    raw["poster_url"] = poster
            match = MetadataMatch(
                provider=self.name,
                provider_id=f"subject:{row['id']}",
                title=match_title,
                year=_extract_year(row.get("date")),
                raw=raw,
            )
            match.score = score_match(candidate, match)
            if is_confident_match(match.score):
                matches.append(match)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        subject_id = str(match.provider_id).split(":", 1)[1]
        payload = self._client.get_subject(subject_id)
        persons = self._client.get_subject_persons(subject_id)
        characters = self._client.get_subject_characters(subject_id)
        aliases = _subject_aliases(payload)
        actors = self._character_actors(characters)
        directors = self._subject_staff(persons)
        genres = [str(item.get("name") or "").strip() for item in payload.get("tags") or [] if str(item.get("name") or "").strip()]
        poster = ""
        if isinstance(payload.get("images"), dict):
            images = payload["images"]
            poster = str(images.get("large") or images.get("common") or images.get("grid") or "").strip()
        detail_fields = [
            {"label": "Bangumi ID", "value": str(payload.get("id") or subject_id).strip()},
            {"label": "原题", "value": str(payload.get("name") or "").strip()},
            {"label": "别名", "value": " / ".join(aliases)},
            {"label": "话数", "value": str(payload.get("eps") or "").strip()},
        ]
        air_date = _extract_infobox_scalar(payload.get("infobox") or [], "放送开始") or str(payload.get("date") or "").strip()
        if air_date:
            detail_fields.append({"label": "放送开始", "value": air_date})
        if actors:
            detail_fields.append({"label": "声优", "value": " / ".join(actors)})
        return MetadataRecord(
            provider=self.name,
            provider_id=match.provider_id,
            title=str(payload.get("name_cn") or payload.get("name") or match.title or "").strip(),
            original_title=str(payload.get("name") or "").strip(),
            year=_extract_year(payload.get("date")) or str(match.year or "").strip(),
            poster=poster,
            overview=str(payload.get("summary") or "").strip(),
            rating=str((payload.get("rating") or {}).get("score") or "").strip(),
            actors=actors,
            directors=directors,
            genres=genres,
            aliases=aliases,
            detail_fields=[item for item in detail_fields if str(item.get("value") or "").strip()],
        )

    def _character_actors(self, characters: list[dict[str, object]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for character in characters or []:
            if not isinstance(character, dict):
                continue
            for actor in character.get("actors") or []:
                if not isinstance(actor, dict):
                    continue
                name = str(actor.get("name") or "").strip()
                if not name or name in seen:
                    continue
                ordered.append(name)
                seen.add(name)
        return ordered

    def _subject_staff(self, persons: list[dict[str, object]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for person in persons or []:
            if not isinstance(person, dict):
                continue
            relation = str(person.get("relation") or "").strip()
            if not any(token in relation for token in _DIRECTOR_RELATION_TOKENS):
                continue
            name = str(person.get("name") or "").strip()
            if not name or name in seen:
                continue
            ordered.append(name)
            seen.add(name)
        return ordered


def _extract_infobox_scalar(infobox: list[object], key_name: str) -> str:
    for item in infobox:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "").strip() != key_name:
            continue
        values = _flatten_infobox_value(item.get("value"))
        if values:
            return values[0]
    return ""
