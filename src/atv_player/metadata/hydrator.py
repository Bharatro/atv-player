from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import logging

from atv_player.metadata.base import MetadataProvider
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.matching import is_confident_match, score_match
from atv_player.metadata.merge import fill_missing_metadata_record, merge_metadata_record, override_visual_metadata_record
from atv_player.metadata.models import MetadataContext, MetadataMatch, MetadataRecord
from atv_player.models import VodItem

logger = logging.getLogger(__name__)

_SEARCH_CACHE_TTL_SECONDS = 7 * 24 * 3600
_EMPTY_SEARCH_CACHE_TTL_SECONDS = 3600
_DETAIL_CACHE_TTL_SECONDS = 7 * 24 * 3600
_LOCAL_DOUBAN_PRIME_SOURCE_KINDS = {"telegram", "emby", "jellyfin"}
_LOCAL_DOUBAN_PROVIDER_NAMES = {"local_douban", "remote_douban"}
_ANIME_MARKERS = ("动漫", "动画", "番剧", "anime", "acg", "国创", "声优")
_LIVE_ACTION_MARKERS = ("电视剧", "剧集", "连续剧", "真人", "古装", "短剧")
_MOVIE_MARKERS = ("电影", "影片", "movie")


def _iter_category_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return _iter_category_values(value.get("value"))
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_iter_category_values(item))
        return values
    text = str(value or "").strip()
    return [text] if text else []


def _classify_media_kind(*values: object) -> str:
    tokens = " ".join(
        token.strip().lower()
        for value in values
        for token in _iter_category_values(value)
        if token and token.strip()
    )
    if not tokens:
        return ""
    if any(marker in tokens for marker in _ANIME_MARKERS):
        return "anime"
    if any(marker in tokens for marker in _MOVIE_MARKERS):
        return "movie"
    if any(marker in tokens for marker in _LIVE_ACTION_MARKERS):
        return "live_action"
    return ""


def _match_media_kind(match: MetadataMatch) -> str:
    if match.provider == "bangumi":
        return "anime"
    if match.provider == "tmdb":
        provider_id = str(match.provider_id or "").strip()
        if provider_id.startswith("movie:"):
            return "movie"
    raw = dict(match.raw or {})
    return _classify_media_kind(
        raw.get("typeName"),
        raw.get("channel"),
        raw.get("genres"),
        raw.get("categories"),
        raw.get("baseTags"),
        raw.get("category"),
        match.title,
    )


def _record_media_kind(record: MetadataRecord) -> str:
    if record.provider == "bangumi":
        return "anime"
    if record.provider == "tmdb":
        provider_id = str(record.provider_id or "").strip()
        if provider_id.startswith("movie:"):
            return "movie"
    return _classify_media_kind(
        record.genres,
        record.title,
        record.original_title,
        record.country,
        record.detail_fields,
    )


def _vod_media_kind(vod: VodItem) -> str:
    return _classify_media_kind(vod.type_name, vod.category_name)


def _media_kinds_compatible(current_kind: str, candidate_kind: str) -> bool:
    if not current_kind or not candidate_kind:
        return True
    return current_kind == candidate_kind


def _record_has_enrichment_data(record: MetadataRecord) -> bool:
    return any(
        (
            str(record.poster or "").strip(),
            str(record.backdrop or "").strip(),
            str(record.overview or "").strip(),
            str(record.rating or "").strip(),
            list(record.actors or []),
            list(record.directors or []),
            list(record.genres or []),
            str(record.country or "").strip(),
            str(record.language or "").strip(),
            list(record.aliases or []),
            str(record.imdb_id or "").strip(),
            str(record.tmdb_id or "").strip(),
            int(record.douban_id or 0),
            list(record.detail_fields or []),
        )
    )


def _iqiyi_match_raw_has_detail(match: MetadataMatch) -> bool:
    raw = dict(match.raw or {})
    return any(
        (
            str(raw.get("promptDesc") or "").strip(),
            str(raw.get("introduction") or "").strip(),
            str(raw.get("channel") or "").strip(),
            list(raw.get("metaTags") or []),
            list(raw.get("baseTags") or []),
            raw.get("category"),
            raw.get("region"),
            raw.get("language"),
            raw.get("directors"),
            raw.get("actors"),
        )
    )


def _should_refresh_cached_detail(provider_name: str, cached: MetadataRecord, match: MetadataMatch) -> bool:
    if provider_name != "iqiyi":
        return False
    if _record_has_enrichment_data(cached):
        return False
    return _iqiyi_match_raw_has_detail(match)


class MetadataHydrator:
    def __init__(
        self,
        cache: MetadataCache,
        providers: list[MetadataProvider],
        binding_repository=None,
    ) -> None:
        self._cache = cache
        self._providers = providers
        self._providers_by_name = {provider.name: provider for provider in providers}
        self._binding_repository = binding_repository

    def _load_bound_record(self, query):
        if self._binding_repository is None:
            return None
        binding = self._binding_repository.load(query.title, query.year)
        if binding is None:
            return None
        provider = self._providers_by_name.get(binding.provider)
        if provider is None:
            self._binding_repository.delete(query.title, query.year)
            return None
        cached = self._cache.load_detail(
            binding.provider,
            binding.provider_id,
            ttl_seconds=_DETAIL_CACHE_TTL_SECONDS,
        )
        if cached is not None:
            return cached
        try:
            record = provider.get_detail(
                MetadataMatch(
                    provider=binding.provider,
                    provider_id=binding.provider_id,
                    title=binding.matched_title or query.title,
                    year=binding.matched_year or query.year,
                )
            )
        except Exception:
            self._binding_repository.delete(query.title, query.year)
            return None
        self._cache.save_detail(binding.provider, binding.provider_id, record)
        return record

    def _load_provider_matches(self, provider: MetadataProvider, query) -> list[MetadataMatch]:
        search_cache_key = getattr(provider, "search_cache_key", None)
        cache_title = query.title
        cache_year = query.year
        if callable(search_cache_key):
            provider_cache_key = search_cache_key(query)
            if provider_cache_key is not None:
                cache_title, cache_year = provider_cache_key
        matches = self._cache.load_search(
            provider.name,
            cache_title,
            cache_year,
            ttl_seconds=_SEARCH_CACHE_TTL_SECONDS,
            empty_ttl_seconds=_EMPTY_SEARCH_CACHE_TTL_SECONDS,
        )
        if matches is None:
            try:
                matches = provider.search(query)
            except Exception as exc:
                logger.warning("Metadata provider search failed provider=%s", provider.name, exc_info=exc)
                return []
            self._cache.save_search(provider.name, cache_title, cache_year, matches)
        return [replace(match, score=max(float(match.score or 0.0), score_match(query, match))) for match in matches]

    def _load_detail_record(self, provider: MetadataProvider, match: MetadataMatch):
        cached = self._cache.load_detail(
            provider.name,
            str(match.provider_id),
            ttl_seconds=_DETAIL_CACHE_TTL_SECONDS,
        )
        if cached is not None and not _should_refresh_cached_detail(provider.name, cached, match):
            return cached
        try:
            record = provider.get_detail(match)
        except Exception as exc:
            logger.warning("Metadata provider detail failed provider=%s", provider.name, exc_info=exc)
            return None
        self._cache.save_detail(provider.name, str(match.provider_id), record)
        return record

    def _prime_local_douban_query(self, context: MetadataContext, vod: VodItem, query, eligible_providers: list[MetadataProvider]):
        if context.source_kind not in _LOCAL_DOUBAN_PRIME_SOURCE_KINDS:
            return query
        local_provider = next((provider for provider in eligible_providers if provider.name in _LOCAL_DOUBAN_PROVIDER_NAMES), None)
        if local_provider is None:
            return query
        matches = self._load_provider_matches(local_provider, query)
        if not matches:
            return query
        best_match = max(matches, key=lambda item: item.score)
        if not is_confident_match(best_match.score):
            return query
        record = self._load_detail_record(local_provider, best_match)
        if record is None:
            return query
        merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
        return replace(
            query,
            title=str(vod.vod_name or "").strip() or query.title,
            year=str(vod.vod_year or "").strip() or query.year,
            type_name=str(vod.type_name or "").strip() or query.type_name,
            category_name=str(vod.category_name or "").strip() or query.category_name,
        )

    def hydrate(self, context: MetadataContext) -> VodItem:
        vod = replace(context.vod)
        query = context.to_query()
        bound_record = self._load_bound_record(query)
        if bound_record is not None:
            merge_metadata_record(vod, bound_record, provider_priority=[item.name for item in self._providers])
            return vod
        eligible_providers = [provider for provider in self._providers if provider.can_enrich(context)]
        if not eligible_providers:
            return vod
        query = self._prime_local_douban_query(context, vod, query, eligible_providers)

        with ThreadPoolExecutor(max_workers=max(1, len(eligible_providers))) as executor:
            futures = [executor.submit(self._load_provider_matches, provider, query) for provider in eligible_providers]

        ranked_candidates: list[tuple[int, MetadataProvider, MetadataMatch]] = []
        for order, (provider, future) in enumerate(zip(eligible_providers, futures)):
            matches = future.result()
            if not matches:
                continue
            best_match = max(matches, key=lambda item: item.score)
            if not is_confident_match(best_match.score):
                continue
            ranked_candidates.append((order, provider, best_match))

        primary_applied = False
        primary_kind = ""
        for order, provider, match in sorted(ranked_candidates, key=lambda item: (-item[2].score, item[0])):
            del order
            current_kind = primary_kind or _vod_media_kind(vod)
            if primary_applied and not _media_kinds_compatible(current_kind, _match_media_kind(match)):
                logger.info(
                    "Skip incompatible metadata candidate provider=%s title=%s current_kind=%s candidate_kind=%s",
                    provider.name,
                    match.title,
                    current_kind,
                    _match_media_kind(match),
                )
                continue
            record = self._load_detail_record(provider, match)
            if record is None:
                continue
            if not primary_applied:
                merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
                primary_applied = True
                primary_kind = _record_media_kind(record) or _match_media_kind(match) or _vod_media_kind(vod)
                continue
            current_kind = primary_kind or _vod_media_kind(vod)
            if not _media_kinds_compatible(current_kind, _record_media_kind(record)):
                logger.info(
                    "Skip incompatible metadata record provider=%s title=%s current_kind=%s candidate_kind=%s",
                    provider.name,
                    record.title,
                    current_kind,
                    _record_media_kind(record),
                )
                continue
            fill_missing_metadata_record(vod, record)
            override_visual_metadata_record(vod, record)
        return vod
