from __future__ import annotations

from dataclasses import dataclass, field

from atv_player.metadata.cache import MetadataCache


@dataclass(slots=True)
class DiscoveryQuery:
    kind: str
    page: int = 1
    query: str = ""
    media_type: str = ""
    list_key: str = ""
    sort_by: str = ""
    year: str = ""
    with_genres: str = ""
    with_origin_country: str = ""


@dataclass(slots=True)
class DiscoveryItem:
    provider: str
    provider_id: str
    tmdb_id: str
    media_type: str
    title: str
    year: str = ""
    poster: str = ""
    backdrop: str = ""
    rating: str = ""
    overview: str = ""
    source_label: str = ""
    is_following: bool = False
    is_favorited: bool = False


@dataclass(slots=True)
class DiscoveryResult:
    items: list[DiscoveryItem] = field(default_factory=list)
    total: int = 0
    source_label: str = ""
    fallback_reason: str = ""


class TMDBDiscoveryService:
    def __init__(self, *, client, cache: MetadataCache) -> None:
        self._client = client
        self._cache = cache

    def trending(self, query: DiscoveryQuery) -> DiscoveryResult:
        items = [
            self._map_item(raw, source_label="本周趋势")
            for raw in self._client.get_trending(
                media_type=query.media_type or "all",
                window="week",
                page=query.page,
            )
        ]
        return DiscoveryResult(items=items, total=len(items), source_label="本周趋势")

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        items = [
            self._map_item(raw, source_label="筛选结果")
            for raw in self._client.discover(
                media_type=query.media_type or "tv",
                page=query.page,
                sort_by=query.sort_by,
                year=query.year,
                with_genres=query.with_genres,
                with_origin_country=query.with_origin_country,
            )
        ]
        return DiscoveryResult(items=items, total=len(items), source_label="筛选结果")

    def _map_item(self, raw: dict[str, object], *, source_label: str) -> DiscoveryItem:
        media_type = "tv" if raw.get("name") else "movie"
        title = str(raw.get("name") or raw.get("title") or "").strip()
        date_text = str(raw.get("first_air_date") or raw.get("release_date") or "").strip()
        year = date_text[:4] if len(date_text) >= 4 and date_text[:4].isdigit() else ""
        tmdb_id = str(raw.get("id") or "").strip()
        poster_path = str(raw.get("poster_path") or "").strip()
        backdrop_path = str(raw.get("backdrop_path") or "").strip()
        rating = ""
        if raw.get("vote_average") not in (None, ""):
            rating = f"{round(float(raw.get('vote_average') or 0), 1):.1f}"
        return DiscoveryItem(
            provider="tmdb",
            provider_id=f"{media_type}:{tmdb_id}",
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            poster=f"{self._client.image_base('poster')}{poster_path}" if poster_path else "",
            backdrop=f"{self._client.image_base('backdrop')}{backdrop_path}" if backdrop_path else "",
            rating=rating,
            overview=str(raw.get("overview") or "").strip(),
            source_label=source_label,
        )
