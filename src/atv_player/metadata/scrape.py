from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
import logging
import re

logger = logging.getLogger(__name__)

from atv_player.episode_titles import extract_season_number
from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
)
from atv_player.metadata.merge import replace_metadata_record
from atv_player.metadata.models import MetadataMatch, MetadataQuery
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
    "tmdb": "TMDB",
    "plugin": "插件",
}

_SEARCH_CACHE_TTL_SECONDS = 7 * 24 * 3600
_EMPTY_SEARCH_CACHE_TTL_SECONDS = 3600


def normalize_metadata_scrape_title(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"^[#＃]+\s*", "", text).strip()
    return normalized or text


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
        return MetadataScrapeCandidate(
            provider=match.provider,
            provider_label=self._provider_label(match.provider),
            provider_id=str(match.provider_id),
            title=match.title,
            year=match.year,
            subtitle=str(match.raw.get("subtitle") or ""),
            raw=dict(match.raw),
        )

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

    def search(self, query: MetadataQuery, provider_filter: str = "") -> list[MetadataScrapeGroup]:
        query = replace(query, title=normalize_metadata_scrape_title(query.title))
        providers = [provider for provider in self._providers if not provider_filter or provider.name == provider_filter]

        def run(provider: object) -> MetadataScrapeGroup:
            cache_title = query.title
            cache_year = query.year
            search_cache_key = getattr(provider, "search_cache_key", None)
            if callable(search_cache_key):
                provider_cache_key = search_cache_key(query)
                if provider_cache_key is not None:
                    cache_title, cache_year = provider_cache_key
            try:
                matches = self._cache.load_search(
                    provider.name,
                    cache_title,
                    cache_year,
                    ttl_seconds=_SEARCH_CACHE_TTL_SECONDS,
                    empty_ttl_seconds=_EMPTY_SEARCH_CACHE_TTL_SECONDS,
                )
                if matches is None:
                    matches = provider.search(query)
                    self._cache.save_search(provider.name, cache_title, cache_year, matches)
            except Exception as exc:
                return MetadataScrapeGroup(
                    provider=provider.name,
                    provider_label=self._provider_label(provider.name),
                    error_text=str(exc),
                )
            return MetadataScrapeGroup(
                provider=provider.name,
                provider_label=self._provider_label(provider.name),
                items=[self._candidate_from_match(match) for match in matches],
            )

        with ThreadPoolExecutor(max_workers=max(1, len(providers))) as executor:
            futures = [executor.submit(run, provider) for provider in providers]
        return [future.result() for future in futures]

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
            ordered_candidates.append(self._hydrate_bangumi_episode_candidate(enriched))
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
                ordered_candidates.append(self._hydrate_bangumi_episode_candidate(enriched))
        for candidate in ordered_candidates:
            updated = build_provider_episode_playlist(
                vod,
                playlist,
                candidate,
                source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
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
            self._cache.save_detail(candidate.provider, candidate.provider_id, record)
        updated = replace(vod)
        replace_metadata_record(updated, record)
        return updated
