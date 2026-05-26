from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

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


@dataclass(slots=True)
class RecommendationSeed:
    provider_id: str
    tmdb_id: str
    media_type: str
    seed_source: str
    activity_weight: float
    activity_timestamp: int
    reason_flags: list[str] = field(default_factory=list)


class TMDBDiscoveryService:
    _TRENDING_CACHE_NAMESPACE = "tmdb_discovery_trending"
    _DISCOVER_CACHE_NAMESPACE = "tmdb_discovery_discover"
    _RECOMMEND_CACHE_NAMESPACE = "tmdb_discovery_recommend"
    _TRENDING_CACHE_TTL_SECONDS = 60 * 60 * 6
    _DISCOVER_CACHE_TTL_SECONDS = 60 * 60 * 2

    def __init__(self, *, client, cache: MetadataCache) -> None:
        self._client = client
        self._cache = cache

    def trending(self, query: DiscoveryQuery) -> DiscoveryResult:
        window, source_label = self._trending_window_and_label(query.list_key)
        cache_key = self._cache_key(
            {
                "kind": "trending",
                "list_key": query.list_key or "trending_week",
                "media_type": query.media_type or "all",
                "page": int(query.page or 1),
            }
        )
        cached = self._load_cached_result(
            self._TRENDING_CACHE_NAMESPACE,
            cache_key,
            ttl_seconds=self._TRENDING_CACHE_TTL_SECONDS,
            empty_ttl_seconds=60 * 10,
        )
        if cached is not None:
            return cached
        items = [
            self._map_item(raw, source_label=source_label)
            for raw in self._client.get_trending(
                media_type=query.media_type or "all",
                window=window,
                page=query.page,
            )
        ]
        result = DiscoveryResult(items=items, total=len(items), source_label=source_label)
        self._save_cached_result(self._TRENDING_CACHE_NAMESPACE, cache_key, result)
        return result

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        cache_key = self._cache_key(
            {
                "kind": "discover",
                "media_type": query.media_type or "tv",
                "sort_by": query.sort_by or "",
                "year": query.year or "",
                "with_genres": query.with_genres or "",
                "with_origin_country": query.with_origin_country or "",
                "page": int(query.page or 1),
            }
        )
        cached = self._load_cached_result(
            self._DISCOVER_CACHE_NAMESPACE,
            cache_key,
            ttl_seconds=self._DISCOVER_CACHE_TTL_SECONDS,
            empty_ttl_seconds=60 * 10,
        )
        if cached is not None:
            return cached
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
        result = DiscoveryResult(items=items, total=len(items), source_label="筛选结果")
        self._save_cached_result(self._DISCOVER_CACHE_NAMESPACE, cache_key, result)
        return result

    def recommend(
        self,
        *,
        seeds: list[RecommendationSeed],
        favorite_provider_ids: set[str],
        following_provider_ids: set[str],
    ) -> DiscoveryResult:
        cache_key = self._cache_key(
            {
                "kind": "recommend",
                "seeds": [
                    {
                        "provider_id": seed.provider_id,
                        "tmdb_id": seed.tmdb_id,
                        "media_type": seed.media_type,
                        "seed_source": seed.seed_source,
                        "activity_weight": seed.activity_weight,
                        "activity_timestamp": seed.activity_timestamp,
                        "reason_flags": list(seed.reason_flags),
                    }
                    for seed in list(seeds or [])
                ],
                "favorite_provider_ids": sorted(str(provider_id) for provider_id in favorite_provider_ids),
                "following_provider_ids": sorted(str(provider_id) for provider_id in following_provider_ids),
            }
        )
        cached = self._load_cached_result(self._RECOMMEND_CACHE_NAMESPACE, cache_key, ttl_seconds=0)
        if cached is not None:
            return cached
        scored: dict[str, tuple[float, dict[str, object]]] = {}
        for seed in list(seeds or []):
            rows = self._client.get_recommendations(
                media_type=seed.media_type,
                tmdb_id=seed.tmdb_id,
                page=1,
            )
            for raw in rows[:12]:
                item = self._map_item(raw, source_label="推荐")
                if item.provider_id in favorite_provider_ids or item.provider_id in following_provider_ids:
                    continue
                score = seed.activity_weight
                score += float(raw.get("vote_average") or 0) / 10.0
                score += float(raw.get("popularity") or 0) / 1000.0
                existing_score, _existing_raw = scored.get(item.provider_id, (0.0, raw))
                scored[item.provider_id] = (existing_score + score, raw)
        ordered = sorted(scored.items(), key=lambda entry: entry[1][0], reverse=True)
        items = [self._map_item(raw, source_label="推荐") for _provider_id, (_score, raw) in ordered]
        result = DiscoveryResult(items=items, total=len(items), source_label="推荐")
        self._save_cached_result(self._RECOMMEND_CACHE_NAMESPACE, cache_key, result)
        return result

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

    @staticmethod
    def _cache_key(payload: dict[str, object]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _trending_window_and_label(list_key: str) -> tuple[str, str]:
        normalized = str(list_key or "").strip() or "trending_week"
        if normalized == "trending_day":
            return "day", "今日趋势"
        return "week", "本周趋势"

    def _load_cached_result(
        self,
        namespace: str,
        cache_key: str,
        *,
        ttl_seconds: int,
        empty_ttl_seconds: int | None = None,
    ) -> DiscoveryResult | None:
        payload = self._cache.load_payload(
            namespace,
            cache_key,
            ttl_seconds,
            empty_ttl_seconds=empty_ttl_seconds,
        )
        if not isinstance(payload, dict):
            return None
        items = [
            DiscoveryItem(**item)
            for item in list(payload.get("items") or [])
            if isinstance(item, dict)
        ]
        return DiscoveryResult(
            items=items,
            total=int(payload.get("total") or len(items)),
            source_label=str(payload.get("source_label") or ""),
            fallback_reason=str(payload.get("fallback_reason") or ""),
        )

    def _save_cached_result(self, namespace: str, cache_key: str, result: DiscoveryResult) -> None:
        self._cache.save_payload(
            namespace,
            cache_key,
            {
                "items": [asdict(item) for item in list(result.items or [])],
                "total": int(result.total or len(result.items)),
                "source_label": result.source_label,
                "fallback_reason": result.fallback_reason,
            },
        )
