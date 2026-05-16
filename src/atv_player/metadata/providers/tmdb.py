from __future__ import annotations

import re

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


def infer_tmdb_media_type(query: MetadataQuery) -> str:
    category = str(query.category_name or "").strip().lower()
    if any(token in category for token in ("电影", "影片", "movie")):
        return "movie"
    if any(token in category for token in ("电视剧", "剧集", "动漫", "番剧", "综艺", "纪录片", "tv")):
        return "tv"
    return ""


def _normalize_title(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _strip_search_season_suffix(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = re.sub(
        r"(?:\s*[-:：]\s*)?(?:第\s*[0-9零一二两三四五六七八九十百]+\s*季|season\s*\d+|s\d+)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or text


def _extract_year(payload: dict[str, object], *, media_type: str) -> str:
    raw = str(
        payload.get("year")
        or (
            payload.get("release_date")
            if media_type == "movie"
            else payload.get("first_air_date")
        )
        or ""
    ).strip()
    return raw[:4] if len(raw) >= 4 and raw[:4].isdigit() else ""


def _should_reject_year_mismatch(media_type: str, expected_year: str, actual_year: str) -> bool:
    if media_type != "movie":
        return False
    return bool(expected_year and actual_year and actual_year != str(expected_year).strip())


def _split_names(values: list[object] | None) -> list[str]:
    return [str(value or "").strip() for value in values or [] if str(value or "").strip()]


class TMDBProvider:
    name = "tmdb"

    def __init__(self, client) -> None:
        self._client = client

    def can_enrich(self, _context) -> bool:
        return True

    def search_cache_key(self, candidate: MetadataQuery) -> tuple[str, str] | None:
        title = candidate.title
        if infer_tmdb_media_type(candidate) == "tv":
            title = _strip_search_season_suffix(title)
        return (title, candidate.year)

    def _match_from_payload(
        self,
        media_type: str,
        item: dict[str, object],
        title: str,
        year: str,
    ) -> MetadataMatch | None:
        item_title = str(item.get("title") or item.get("name") or "").strip()
        normalized_title = _normalize_title(title)
        normalized_item = _normalize_title(item_title)
        aliases = {
            _normalize_title(alias)
            for alias in item.get("aliases") or []
            if _normalize_title(alias)
        }
        if normalized_title not in {normalized_item, *aliases}:
            return None
        item_year = _extract_year(item, media_type=media_type)
        if _should_reject_year_mismatch(media_type, year, item_year):
            return None
        provider_id = str(item.get("id") or "").strip()
        if not provider_id:
            return None
        return MetadataMatch(
            provider=self.name,
            provider_id=f"{media_type}:{provider_id}",
            title=item_title,
            year=item_year,
        )

    def _search_media_type(self, media_type: str, candidate: MetadataQuery) -> list[MetadataMatch]:
        search_fn = self._client.search_movie if media_type == "movie" else self._client.search_tv
        search_title = _strip_search_season_suffix(candidate.title) if media_type == "tv" else candidate.title
        payload = search_fn(search_title, year=candidate.year)
        if not payload and search_title != candidate.title:
            payload = search_fn(candidate.title, year=candidate.year)
        matches: list[MetadataMatch] = []
        fallback_matches: list[MetadataMatch] = []
        for item in payload:
            normalized_item = dict(item)
            match = self._match_from_payload(media_type, normalized_item, search_title, candidate.year)
            if match is not None:
                matches.append(match)
                continue
            provider_id = str(normalized_item.get("id") or "").strip()
            item_title = str(
                normalized_item.get("title")
                or normalized_item.get("name")
                or normalized_item.get("original_title")
                or normalized_item.get("original_name")
                or ""
            ).strip()
            if not provider_id or not item_title:
                continue
            item_year = _extract_year(normalized_item, media_type=media_type)
            if _should_reject_year_mismatch(media_type, candidate.year, item_year):
                continue
            fallback_matches.append(
                MetadataMatch(
                    provider=self.name,
                    provider_id=f"{media_type}:{provider_id}",
                    title=item_title,
                    year=item_year,
                )
            )
        return matches or fallback_matches[:1]

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title:
            return []
        inferred = infer_tmdb_media_type(candidate)
        if inferred:
            return self._search_media_type(inferred, candidate)
        for media_type in ("movie", "tv"):
            matches = self._search_media_type(media_type, candidate)
            if matches:
                return matches
        return []

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        media_type, provider_id = str(match.provider_id).split(":", 1)
        payload = (
            self._client.get_movie_detail(provider_id)
            if media_type == "movie"
            else self._client.get_tv_detail(provider_id)
        )
        genres = [
            str(item.get("name") or "").strip()
            for item in payload.get("genres") or []
            if str(item.get("name") or "").strip()
        ]
        if media_type == "movie":
            credits = payload.get("credits") or {}
            cast = credits.get("cast") or []
            crew = credits.get("crew") or []
            alt_titles = ((payload.get("alternative_titles") or {}).get("titles") or [])
        else:
            credits = payload.get("aggregate_credits") or {}
            cast = credits.get("cast") or []
            crew = credits.get("crew") or []
            alt_titles = ((payload.get("alternative_titles") or {}).get("results") or [])
        actors = [
            str(item.get("name") or "").strip()
            for item in cast
            if str(item.get("name") or "").strip()
        ]
        directors = [
            str(item.get("name") or "").strip()
            for item in crew
            if str(item.get("job") or "").strip() == "Director" and str(item.get("name") or "").strip()
        ]
        aliases = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in alt_titles
            if str(item.get("title") or item.get("name") or "").strip()
        ]
        external_ids = payload.get("external_ids") or {}
        return MetadataRecord(
            provider=self.name,
            provider_id=match.provider_id,
            title=str(payload.get("title") or payload.get("name") or match.title or "").strip(),
            year=_extract_year(payload, media_type=media_type) or str(match.year or "").strip(),
            poster=str(payload.get("poster_url") or "").strip(),
            backdrop=str(payload.get("backdrop_url") or "").strip(),
            overview=str(payload.get("overview") or "").strip(),
            rating=str(payload.get("vote_average") or "").strip(),
            actors=_split_names(actors),
            directors=_split_names(directors),
            genres=_split_names(genres),
            aliases=_split_names(aliases),
            imdb_id=str(external_ids.get("imdb_id") or "").strip(),
            tmdb_id=str(payload.get("id") or "").strip(),
        )
