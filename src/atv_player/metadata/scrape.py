from __future__ import annotations

from dataclasses import dataclass, field, replace
import logging
import re

logger = logging.getLogger(__name__)

from atv_player.episode_titles import extract_season_number
from atv_player.metadata.async_runner import run_provider_searches
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.cache_key import provider_search_cache_key
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
    resolve_episode_title_source_priority,
)
from atv_player.metadata.merge import replace_metadata_record
from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.query import normalize_metadata_query_inputs, normalize_metadata_title
from atv_player.metadata.providers.bangumi import is_bangumi_anime_query
from atv_player.models import PlayItem, VodItem

_PROVIDER_LABELS = {
    "bangumi": "Bangumi",
    "bilibili": "B站",
    "tencent": "腾讯",
    "official_douban": "豆瓣官方",
    "local_douban": "本地豆瓣",
    "douban": "豆瓣",
    "iqiyi": "爱奇艺",
    "sohu": "搜狐视频",
    "tmdb": "TMDB",
    "plugin": "插件",
}

_SEARCH_CACHE_TTL_SECONDS = 7 * 24 * 3600
_EMPTY_SEARCH_CACHE_TTL_SECONDS = 3600
_ANIME_MARKERS = ("动漫", "动画", "番剧", "anime", "acg", "国创", "声优")
_LIVE_ACTION_MARKERS = ("电视剧", "剧集", "连续剧", "真人", "古装", "短剧")
_MOVIE_MARKERS = ("电影", "影片", "movie")


def normalize_metadata_scrape_title(value: object) -> str:
    return normalize_metadata_title(value)


@dataclass(slots=True)
class MetadataScrapeCandidate:
    provider: str
    provider_label: str
    provider_id: str
    title: str
    year: str = ""
    subtitle: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MetadataScrapeGroup:
    provider: str
    provider_label: str
    items: list[MetadataScrapeCandidate] = field(default_factory=list)
    error_text: str = ""


def _parse_tmdb_provider_id(provider_id: str) -> tuple[str, int | None]:
    text = str(provider_id or "").strip()
    if not text.startswith("tv:"):
        return "", None
    segments = text.split(":")
    if len(segments) < 2:
        return "", None
    tmdb_id = segments[1].strip()
    season_number = None
    if len(segments) >= 4 and segments[2] == "season":
        try:
            season_number = int(segments[3])
        except (TypeError, ValueError):
            season_number = None
    return tmdb_id, season_number


def _parse_bangumi_provider_id(provider_id: str) -> str:
    text = str(provider_id or "").strip()
    if not text.startswith("subject:"):
        return ""
    return text.split(":", 1)[1].strip()


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


def _split_category_tokens(value: object) -> list[str]:
    tokens: list[str] = []
    for item in _iter_category_values(value):
        for part in re.split(r"[,/|、，]", str(item or "").strip()):
            normalized = part.strip()
            if normalized and not normalized.isdigit():
                tokens.append(normalized)
    return tokens


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


def _media_kind_label(kind: str) -> str:
    return {
        "anime": "动漫",
        "movie": "电影",
        "live_action": "剧集",
    }.get(kind, "")


def _query_media_kind(query: MetadataQuery) -> str:
    explicit_kind = _classify_media_kind(query.category_name)
    if explicit_kind:
        return explicit_kind
    return _classify_media_kind(query.type_name)


def _match_media_kind(match: MetadataMatch) -> str:
    if match.provider == "bangumi":
        return "anime"
    if match.provider == "tmdb" and str(match.provider_id or "").strip().startswith("movie:"):
        return "movie"
    raw = dict(match.raw or {})
    return _classify_media_kind(
        raw.get("typeName"),
        raw.get("channel"),
        raw.get("genres"),
        raw.get("categories"),
        raw.get("baseTags"),
        raw.get("category"),
    )


def _match_type_subtitle(match: MetadataMatch) -> str:
    raw = dict(match.raw or {})
    for value in (raw.get("typeName"), raw.get("channel"), raw.get("category")):
        tokens = _split_category_tokens(value)
        if tokens:
            return tokens[0]
    return _media_kind_label(_match_media_kind(match))


def _source_rank(candidate: object, source_priority: list[str]) -> int:
    provider = str(getattr(candidate, "provider", "") or "").strip()
    return source_priority.index(provider) if provider in source_priority else len(source_priority) + 100


class MetadataScrapeService:
    def __init__(self, cache: MetadataCache, providers: list[object]) -> None:
        self._cache = cache
        self._providers = list(providers)
        self._providers_by_name = {provider.name: provider for provider in self._providers}

    def _provider_label(self, provider_name: str) -> str:
        return _PROVIDER_LABELS.get(provider_name, provider_name)

    def provider_options(self, query: MetadataQuery | None = None) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        for provider in self._providers:
            if provider.name == "bangumi" and query is not None and not is_bangumi_anime_query(query):
                continue
            options.append((provider.name, self._provider_label(provider.name)))
        return options

    def _candidate_from_match(self, match: MetadataMatch) -> MetadataScrapeCandidate:
        subtitle = _match_type_subtitle(match) or str(match.raw.get("subtitle") or "").strip()
        return MetadataScrapeCandidate(
            provider=match.provider,
            provider_label=self._provider_label(match.provider),
            provider_id=str(match.provider_id),
            title=match.title,
            year=match.year,
            subtitle=subtitle,
            raw=dict(match.raw),
        )

    def _is_manual_search_match_compatible(self, query: MetadataQuery, match: MetadataMatch) -> bool:
        query_kind = _query_media_kind(query)
        match_kind = _match_media_kind(match)
        if not query_kind or not match_kind:
            return True
        return query_kind == match_kind

    @staticmethod
    def _provider_search_cache_key(provider: object, query: MetadataQuery) -> tuple[str, str]:
        return provider_search_cache_key(provider, query)

    def _hydrate_tmdb_episode_candidate(self, vod: VodItem, candidate: object) -> object:
        provider = str(getattr(candidate, "provider", "") or "").strip()
        if provider != "tmdb":
            return candidate
        raw = dict(getattr(candidate, "raw", {}) or {})
        if isinstance(raw.get("episodes"), list):
            return candidate
        tmdb_provider = self._providers_by_name.get("tmdb")
        client = getattr(tmdb_provider, "_client", None)
        if client is None or not hasattr(client, "get_tv_season_detail"):
            return candidate
        provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
        tmdb_id, season_number = _parse_tmdb_provider_id(provider_id)
        if not tmdb_id:
            return candidate
        if season_number is None:
            for value in (raw.get("season_number"), getattr(candidate, "title", ""), vod.vod_name):
                parsed = extract_season_number(value)
                if parsed is not None:
                    season_number = parsed
                    break
        if season_number is None:
            return candidate
        try:
            season_detail = client.get_tv_season_detail(tmdb_id, season_number) or {}
        except Exception:
            logger.debug(
                "Skip TMDB season detail hydration tmdb_id=%s season=%s",
                tmdb_id,
                season_number,
                exc_info=True,
                extra={"log_category": "metadata", "log_source": "app"},
            )
            return candidate
        episodes = season_detail.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            return candidate
        raw["season_number"] = season_number
        raw["episodes"] = episodes
        if isinstance(candidate, MetadataScrapeCandidate | MetadataMatch):
            return replace(candidate, raw=raw)
        return candidate

    def _hydrate_bangumi_episode_candidate(self, candidate: object) -> object:
        provider = str(getattr(candidate, "provider", "") or "").strip()
        if provider != "bangumi":
            return candidate
        raw = dict(getattr(candidate, "raw", {}) or {})
        if isinstance(raw.get("episodes"), list):
            return candidate
        bangumi_provider = self._providers_by_name.get("bangumi")
        client = getattr(bangumi_provider, "_client", None)
        if client is None or not hasattr(client, "get_episodes"):
            return candidate
        subject_id = _parse_bangumi_provider_id(str(getattr(candidate, "provider_id", "") or "").strip())
        if not subject_id:
            return candidate
        episodes = client.get_episodes(subject_id) or []
        if not isinstance(episodes, list) or not episodes:
            return candidate
        raw["episodes"] = episodes
        if isinstance(candidate, MetadataScrapeCandidate | MetadataMatch):
            return replace(candidate, raw=raw)
        return candidate

    def _hydrate_bilibili_episode_candidate(self, candidate: object) -> object:
        provider = str(getattr(candidate, "provider", "") or "").strip()
        if provider != "bilibili":
            return candidate
        raw = dict(getattr(candidate, "raw", {}) or {})
        episodes = raw.get("episodes")
        if isinstance(episodes, list) and episodes and str(raw.get("season_id") or "").strip():
            return candidate
        bilibili_provider = self._providers_by_name.get("bilibili")
        hydrate = getattr(bilibili_provider, "_hydrate_episode_candidate", None)
        if not callable(hydrate):
            return candidate
        try:
            return hydrate(candidate)
        except Exception:
            logger.debug(
                "Skip Bilibili episode candidate hydration title=%s",
                str(getattr(candidate, "title", "") or "").strip(),
                exc_info=True,
                extra={"log_category": "metadata", "log_source": "app"},
            )
            return candidate

    def search(
        self,
        query: MetadataQuery,
        provider_filter: str = "",
        *,
        cache_only: bool = False,
    ) -> list[MetadataScrapeGroup]:
        normalized_title, normalized_year = normalize_metadata_query_inputs(query.title, query.year)
        query = replace(query, title=normalized_title, year=normalized_year)
        providers = [provider for provider in self._providers if not provider_filter or provider.name == provider_filter]
        logger.info(
            "Metadata scrape search title=%s year=%s category=%s type=%s provider=%s cache_only=%s",
            query.title,
            query.year,
            query.category_name,
            query.type_name,
            provider_filter or "all",
            cache_only,
            extra={"log_category": "metadata", "log_source": "app"},
        )

        cached_matches_by_provider: dict[int, list[MetadataMatch]] = {}
        providers_needing_fetch: list[object] = []
        cache_keys_by_provider: list[tuple[str, str]] = []
        for provider in providers:
            cache_title, cache_year = self._provider_search_cache_key(provider, query)
            matches = self._cache.load_search(
                provider.name,
                cache_title,
                cache_year,
                ttl_seconds=_SEARCH_CACHE_TTL_SECONDS,
                empty_ttl_seconds=_EMPTY_SEARCH_CACHE_TTL_SECONDS,
            )
            if matches is None:
                if cache_only:
                    cached_matches_by_provider[id(provider)] = []
                    continue
                providers_needing_fetch.append(provider)
                cache_keys_by_provider.append((cache_title, cache_year))
                continue
            cached_matches_by_provider[id(provider)] = list(matches)

        fetched_results = (
            run_provider_searches(
                providers_needing_fetch,
                query,
                max_concurrency=max(1, len(providers_needing_fetch)),
            )
            if providers_needing_fetch
            else []
        )
        for provider, (cache_title, cache_year), result in zip(
            providers_needing_fetch,
            cache_keys_by_provider,
            fetched_results,
        ):
            if result.error is None:
                self._cache.save_search(provider.name, cache_title, cache_year, result.matches)

        fetch_index = 0
        groups: list[MetadataScrapeGroup] = []
        for provider in providers:
            cached_matches = cached_matches_by_provider.get(id(provider))
            if cached_matches is not None:
                matches = [match for match in cached_matches if self._is_manual_search_match_compatible(query, match)]
                groups.append(
                    MetadataScrapeGroup(
                        provider=provider.name,
                        provider_label=self._provider_label(provider.name),
                        items=[self._candidate_from_match(match) for match in matches],
                    )
                )
                continue

            result = fetched_results[fetch_index]
            fetch_index += 1
            if result.error is not None:
                groups.append(
                    MetadataScrapeGroup(
                        provider=provider.name,
                        provider_label=self._provider_label(provider.name),
                        error_text=str(result.error),
                    )
                )
                continue
            matches = [match for match in result.matches if self._is_manual_search_match_compatible(query, match)]
            groups.append(
                MetadataScrapeGroup(
                    provider=provider.name,
                    provider_label=self._provider_label(provider.name),
                    items=[self._candidate_from_match(match) for match in matches],
                )
            )
        return groups

    def build_episode_title_playlist(
        self,
        vod: VodItem,
        playlist: list[PlayItem],
        *,
        preferred_candidate: MetadataScrapeCandidate | None = None,
    ) -> list[PlayItem] | None:
        ordered_candidates: list[object] = []
        if preferred_candidate is not None:
            enriched = self._hydrate_tmdb_episode_candidate(vod, preferred_candidate)
            enriched = self._hydrate_bangumi_episode_candidate(enriched)
            ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
        query = MetadataQuery(
            title=str(vod.vod_name or "").strip(),
            year=str(vod.vod_year or "").strip(),
            category_name=str(vod.category_name or "").strip(),
        )
        for provider_name in ("bangumi", "bilibili", "tmdb", "tencent", "iqiyi"):
            if preferred_candidate is not None and provider_name == preferred_candidate.provider:
                continue
            provider = self._providers_by_name.get(provider_name)
            if provider is None:
                continue
            try:
                matches = provider.search(query)
            except Exception:
                continue
            if matches:
                enriched = self._hydrate_tmdb_episode_candidate(vod, matches[0])
                enriched = self._hydrate_bangumi_episode_candidate(enriched)
                ordered_candidates.append(self._hydrate_bilibili_episode_candidate(enriched))
        source_priority = resolve_episode_title_source_priority(
            vod,
            playlist,
            ordered_candidates,
            preferred_provider=str(getattr(preferred_candidate, "provider", "") or "").strip(),
        )
        if preferred_candidate is not None and ordered_candidates:
            ordered_candidates = [ordered_candidates[0], *sorted(ordered_candidates[1:], key=lambda candidate: _source_rank(candidate, source_priority))]
        else:
            ordered_candidates = sorted(ordered_candidates, key=lambda candidate: _source_rank(candidate, source_priority))
        for candidate in ordered_candidates:
            updated = build_provider_episode_playlist(
                vod,
                playlist,
                candidate,
                source_priority=source_priority,
            )
            if updated is not None:
                return updated
        return None

    def reset(
        self,
        query: MetadataQuery,
        *,
        bound_provider: str = "",
        bound_provider_id: str = "",
        detail_keys: list[tuple[str, str]] | None = None,
    ) -> None:
        for provider in self._providers:
            cache_title = query.title
            cache_year = query.year
            search_cache_key = getattr(provider, "search_cache_key", None)
            if callable(search_cache_key):
                provider_cache_key = search_cache_key(query)
                if provider_cache_key is not None:
                    cache_title, cache_year = provider_cache_key
            self._cache.delete_search(provider.name, cache_title, cache_year)
        if bound_provider and bound_provider_id:
            self._cache.delete_detail(bound_provider, bound_provider_id)
        for provider_name, provider_id in detail_keys or []:
            if provider_name and provider_id:
                self._cache.delete_detail(provider_name, provider_id)

    def apply(self, vod: VodItem, candidate: MetadataScrapeCandidate) -> VodItem:
        provider = self._providers_by_name[candidate.provider]
        record = self._cache.load_detail(candidate.provider, candidate.provider_id, ttl_seconds=7 * 24 * 3600)
        if record is None:
            match = MetadataMatch(
                provider=candidate.provider,
                provider_id=candidate.provider_id,
                title=candidate.title,
                year=candidate.year,
                raw=dict(candidate.raw),
            )
            record = provider.get_detail(match)
            if record is None:
                raise RuntimeError(f"{candidate.provider_label or candidate.provider} 未返回刮削详情")
            self._cache.save_detail(candidate.provider, candidate.provider_id, record)
        updated = replace(vod)
        replace_metadata_record(updated, record)
        return updated
