from __future__ import annotations

from dataclasses import replace
import httpx
import logging
import re

from atv_player.danmaku.errors import DanmakuEmptyResultError, ProviderNotSupportedError
from atv_player.danmaku.models import DanmakuSearchItem, DanmakuSourceGroup, DanmakuSourceOption, DanmakuSourceSearchResult
from atv_player.danmaku.providers import (
    BilibiliDanmakuProvider,
    IqiyiDanmakuProvider,
    MgtvDanmakuProvider,
    SohuDanmakuProvider,
    TencentDanmakuProvider,
    YoukuDanmakuProvider,
)
from atv_player.danmaku.providers._concurrency import iter_bounded_settled
from atv_player.danmaku.providers.base import DanmakuProvider
from atv_player.danmaku.utils import (
    build_xml,
    episode_title_matches,
    extract_episode_number,
    extract_variety_issue_key,
    has_explicit_episode_marker,
    is_likely_variety_title,
    match_provider,
    normalize_name,
    should_filter_name,
    similarity_score,
    strip_episode_suffix,
    strip_variety_issue_suffix,
)


logger = logging.getLogger(__name__)

_PREFERRED_MOVIE_VARIANT_TOKENS = (
    "原声版",
    "普通话版",
    "普通话",
    "国语版",
    "国语",
    "粤语版",
    "粤语",
    "臻彩",
)

_FULL_MOVIE_TOKENS = (
    "全片",
    "正片",
    "完整版",
    "完结",
)

_SUPPLEMENTAL_MOVIE_TOKENS = (
    "独家采访",
    "采访",
    "剧情速看",
    "速看",
    "深度剖析",
    "剖析",
    "揭秘",
    "解读",
    "解析",
    "预告",
    "花絮",
    "特辑",
    "片段",
    "幕后",
    "专访",
    "首映礼",
)

_MIN_DANMAKU_CANDIDATE_DURATION_SECONDS = 300
_MAX_MEDIA_DURATION_GAP_SECONDS = 300
_LONG_FORM_DURATION_SECONDS = 3000
_SHORT_FORM_DURATION_RATIO = 0.55
_SHORT_FORM_MIN_DURATION_SECONDS = 1200

_PROVIDER_LABELS = {
    "tencent": "腾讯",
    "youku": "优酷",
    "bilibili": "B站",
    "iqiyi": "爱奇艺",
    "mgtv": "芒果",
    "sohu": "搜狐",
}


def _compact_title(text: str) -> str:
    return re.sub(r"[\W_《》【】()（）]+", "", normalize_name(text).casefold())


def build_danmaku_series_key(name: str) -> str:
    normalized = normalize_name(strip_episode_suffix(name))
    return _compact_title(normalized)


def _movie_candidate_priority(query_name: str, candidate_name: str) -> tuple[int, int, int]:
    query_base = strip_episode_suffix(normalize_name(query_name))
    candidate_base = strip_episode_suffix(normalize_name(candidate_name))
    candidate_text = normalize_name(candidate_name)
    candidate_compact = _compact_title(candidate_text)
    full_movie = int(any(token in candidate_compact for token in _FULL_MOVIE_TOKENS))
    exact_title = int(_compact_title(candidate_base) == _compact_title(query_base))
    preferred_variant = int(
        full_movie or any(token in candidate_text for token in _PREFERRED_MOVIE_VARIANT_TOKENS)
    )
    supplemental = int(any(token in candidate_text for token in _SUPPLEMENTAL_MOVIE_TOKENS))
    return exact_title, preferred_variant, supplemental


def _is_clean_title_only_movie_candidate(query_name: str, candidate_name: str) -> bool:
    query_compact = _compact_title(strip_episode_suffix(normalize_name(query_name)))
    candidate_compact = _compact_title(normalize_name(candidate_name))
    if not query_compact or query_compact not in candidate_compact:
        return False
    remainder = candidate_compact.replace(query_compact, "", 1)
    remainder = re.sub(r"(?:19|20)\d{2}", "", remainder)
    for token in (
        *_PREFERRED_MOVIE_VARIANT_TOKENS,
        *_FULL_MOVIE_TOKENS,
        "电影",
        "影片",
        "版",
        "高清",
        "超清",
        "蓝光",
        "4k",
        "hd",
    ):
        remainder = remainder.replace(_compact_title(token), "")
    return not remainder


def _filter_title_only_movie_noise(
    query_name: str,
    items: list[DanmakuSearchItem],
) -> list[DanmakuSearchItem]:
    strong_candidates = [
        item
        for item in items
        if extract_episode_number(item.name) is None
        and _is_clean_title_only_movie_candidate(query_name, item.name)
    ]
    if not strong_candidates:
        return items
    filtered = [
        item
        for item in items
        if extract_episode_number(item.name) is not None
        or _is_clean_title_only_movie_candidate(query_name, item.name)
    ]
    return filtered or items


def _filter_short_duration_candidates_for_implicit_request(
    items: list[DanmakuSearchItem],
) -> list[DanmakuSearchItem]:
    no_episode_durations = [
        item.duration_seconds for item in items if extract_episode_number(item.name) is None and item.duration_seconds > 0
    ]
    if not no_episode_durations:
        return items
    max_duration = max(no_episode_durations)
    if max_duration < _LONG_FORM_DURATION_SECONDS:
        return items
    min_duration = max(_SHORT_FORM_MIN_DURATION_SECONDS, int(max_duration * _SHORT_FORM_DURATION_RATIO))
    filtered = [
        item
        for item in items
        if item.duration_seconds <= 0 or item.duration_seconds >= min_duration
    ]
    return filtered or items


def _filter_too_short_duration_candidates(items: list[DanmakuSearchItem]) -> list[DanmakuSearchItem]:
    return [
        item
        for item in items
        if item.duration_seconds <= 0 or item.duration_seconds >= _MIN_DANMAKU_CANDIDATE_DURATION_SECONDS
    ]


def _filter_search_items_by_media_duration_gap(
    items: list[DanmakuSearchItem],
    media_duration_seconds: int,
    query_name: str = "",
) -> list[DanmakuSearchItem]:
    if media_duration_seconds <= 0:
        return items
    filtered = [
        item
        for item in items
        if item.duration_seconds <= 0
        or abs(item.duration_seconds - media_duration_seconds) <= _MAX_MEDIA_DURATION_GAP_SECONDS
    ]
    normalized_query = normalize_name(query_name)
    requested_episode = extract_episode_number(normalized_query) if normalized_query else None
    explicit_episode_request = has_explicit_episode_marker(normalized_query) if normalized_query else False
    if not explicit_episode_request or requested_episode is None:
        return filtered
    preserved_exact_matches = [
        item
        for item in items
        if extract_episode_number(item.name) == requested_episode
        and episode_title_matches(normalized_query, item.name)
    ]
    if not preserved_exact_matches:
        return filtered
    if any(
        extract_episode_number(item.name) == requested_episode
        and episode_title_matches(normalized_query, item.name)
        for item in filtered
    ):
        return filtered
    preserved_urls = {item.url for item in filtered}
    merged = list(filtered)
    for item in preserved_exact_matches:
        if item.url in preserved_urls:
            continue
        merged.append(item)
        preserved_urls.add(item.url)
    return merged


def _filter_source_options_by_media_duration_gap(
    options: list[DanmakuSourceOption],
    media_duration_seconds: int,
    query_name: str = "",
) -> list[DanmakuSourceOption]:
    if media_duration_seconds <= 0:
        return options
    filtered = [
        option
        for option in options
        if option.duration_seconds <= 0
        or abs(option.duration_seconds - media_duration_seconds) <= _MAX_MEDIA_DURATION_GAP_SECONDS
    ]
    normalized_query = normalize_name(query_name)
    requested_episode = extract_episode_number(normalized_query) if normalized_query else None
    explicit_episode_request = has_explicit_episode_marker(normalized_query) if normalized_query else False
    if not explicit_episode_request or requested_episode is None:
        return filtered
    preserved_exact_matches = [
        option
        for option in options
        if extract_episode_number(option.name) == requested_episode
        and episode_title_matches(normalized_query, option.name)
    ]
    if not preserved_exact_matches:
        return filtered
    if any(
        extract_episode_number(option.name) == requested_episode
        and episode_title_matches(normalized_query, option.name)
        for option in filtered
    ):
        return filtered
    preserved_urls = {option.url for option in filtered}
    merged = list(filtered)
    for option in preserved_exact_matches:
        if option.url in preserved_urls:
            continue
        merged.append(option)
        preserved_urls.add(option.url)
    return merged


def _is_likely_variety_search(query_name: str, items: list[DanmakuSearchItem]) -> bool:
    return is_likely_variety_title(query_name) or any(is_likely_variety_title(item.name) for item in items)


def _variety_issue_key_for_item(item: DanmakuSearchItem) -> str | None:
    metadata_year = item.resolve_context.get("variety_year")
    if metadata_year not in ("", None, 0):
        return str(metadata_year)
    return extract_variety_issue_key(item.name)


def _variety_issue_key_for_option(option: DanmakuSourceOption) -> str | None:
    metadata_year = option.resolve_context.get("variety_year")
    if metadata_year not in ("", None, 0):
        return str(metadata_year)
    return extract_variety_issue_key(option.name)


def _source_option_query_match_priority(query_name: str, option: DanmakuSourceOption) -> tuple[int, int]:
    normalized_query = normalize_name(query_name)
    if not normalized_query:
        return 0, 0
    variety_issue_key = extract_variety_issue_key(normalized_query)
    variety_issue_match = int(
        variety_issue_key is not None and _variety_issue_key_for_option(option) == variety_issue_key
    )
    requested_episode = extract_episode_number(normalized_query)
    exact_episode_match = int(
        requested_episode is not None
        and extract_episode_number(option.name) == requested_episode
        and episode_title_matches(normalized_query, option.name)
    )
    return variety_issue_match, exact_episode_match


class DanmakuService:
    def __init__(self, providers: dict[str, DanmakuProvider], provider_order: list[str]) -> None:
        self._providers = dict(providers)
        self._provider_order = list(provider_order)
        self._provider_rank = {key: index for index, key in enumerate(self._provider_order)}

    def _preferred_provider_key(self, reg_src: str) -> str | None:
        matched = match_provider(reg_src)
        if matched and matched in self._providers:
            return matched
        return None

    def _ordered_provider_keys(self, reg_src: str) -> list[str]:
        matched = self._preferred_provider_key(reg_src)
        if matched is not None:
            return [matched]
        return [key for key in self._provider_order if key in self._providers]

    @property
    def provider_order(self) -> list[str]:
        return list(self._provider_order)

    def search_danmu_sources(
        self,
        name: str,
        reg_src: str = "",
        preferred_provider: str = "",
        preferred_page_url: str = "",
        media_duration_seconds: int = 0,
        provider_filter: str = "",
    ) -> DanmakuSourceSearchResult:
        flat_results = self.search_danmu(name, reg_src, provider_filter=provider_filter)
        flat_results = _filter_search_items_by_media_duration_gap(flat_results, media_duration_seconds, name)
        requested_episode = extract_episode_number(normalize_name(name))
        grouped: dict[str, list[DanmakuSourceOption]] = {}
        for item in flat_results:
            grouped.setdefault(item.provider, []).append(
                DanmakuSourceOption(
                    provider=item.provider,
                    name=item.name,
                    url=item.url,
                    ratio=item.ratio,
                    simi=item.simi,
                    duration_seconds=item.duration_seconds,
                    episode_match=extract_episode_number(item.name) == requested_episode if requested_episode is not None else False,
                    preferred_by_history=item.url == preferred_page_url,
                    resolve_context=dict(item.resolve_context),
                )
            )
        groups = [
            DanmakuSourceGroup(
                provider=provider,
                provider_label=_PROVIDER_LABELS.get(provider, provider),
                options=options,
                preferred_by_history=provider == preferred_provider,
            )
            for provider, options in grouped.items()
        ]
        return self.rerank_danmaku_source_search_result(
            DanmakuSourceSearchResult(groups=groups),
            query_name=name,
            reg_src=reg_src,
            preferred_provider=preferred_provider,
            preferred_page_url=preferred_page_url,
            media_duration_seconds=media_duration_seconds,
        )

    def rerank_danmaku_source_search_result(
        self,
        result: DanmakuSourceSearchResult,
        *,
        query_name: str = "",
        reg_src: str = "",
        preferred_provider: str = "",
        preferred_page_url: str = "",
        media_duration_seconds: int = 0,
    ) -> DanmakuSourceSearchResult:
        normalized_query = normalize_name(query_name)
        requested_episode = extract_episode_number(normalized_query) if normalized_query else None
        explicit_episode_request = has_explicit_episode_marker(normalized_query) if normalized_query else False
        ranked_rows: list[tuple[DanmakuSourceGroup, DanmakuSourceOption, int]] = []
        stable_index = 0
        for group in result.groups:
            options = _filter_source_options_by_media_duration_gap(group.options, media_duration_seconds, query_name)
            if explicit_episode_request and requested_episode is not None:
                has_matching_episode = any(
                    extract_episode_number(option.name) == requested_episode
                    and episode_title_matches(normalized_query, option.name)
                    for option in options
                )
                if has_matching_episode:
                    options = [
                        option
                        for option in options
                        if extract_episode_number(option.name) is not None
                        or episode_title_matches(normalized_query, option.name)
                    ]
            for option in options:
                ranked_rows.append((group, option, stable_index))
                stable_index += 1
        if media_duration_seconds > 0:
            ranked_rows.sort(
                key=lambda row: self._danmaku_source_option_sort_key(
                    row[1],
                    query_name=query_name,
                    preferred_provider=preferred_provider,
                    preferred_page_url=preferred_page_url,
                    reg_src=reg_src,
                    media_duration_seconds=media_duration_seconds,
                    stable_index=row[2],
                )
            )
        return self._group_ranked_source_rows(
            ranked_rows,
            query_name=query_name,
            preferred_provider=preferred_provider,
            preferred_page_url=preferred_page_url,
            reg_src=reg_src,
        )

    def search_danmu(self, name: str, reg_src: str = "", provider_filter: str = "") -> list[DanmakuSearchItem]:
        normalized = normalize_name(name)
        search_keyword = strip_episode_suffix(strip_variety_issue_suffix(normalized)) or normalized
        requested_episode = extract_episode_number(normalized)
        explicit_episode_request = has_explicit_episode_marker(normalized)
        variety_issue_key = extract_variety_issue_key(normalized)
        primary_query = search_keyword
        preferred_key = self._preferred_provider_key(reg_src)
        if provider_filter:
            provider_keys = [provider_filter] if provider_filter in self._providers else []
            preferred_key = provider_filter if provider_filter in self._providers else None
        else:
            provider_keys = [preferred_key] if preferred_key is not None else self._ordered_provider_keys(reg_src)
        results = self._collect_search_results(provider_keys, primary_query, normalized)
        results = _filter_too_short_duration_candidates(results)
        if _is_likely_variety_search(normalized, results):
            if variety_issue_key is not None and preferred_key is not None and not provider_filter:
                has_variety_match = any(_variety_issue_key_for_item(item) == variety_issue_key for item in results)
                if not has_variety_match:
                    fallback_keys = [
                        key for key in self._provider_order if key in self._providers and key != preferred_key
                    ]
                    if fallback_keys:
                        results.extend(self._collect_search_results(fallback_keys, primary_query, normalized))
                        results = _filter_too_short_duration_candidates(results)
            return sorted(
                results,
                key=lambda item: (
                    -int(variety_issue_key is not None and _variety_issue_key_for_item(item) == variety_issue_key),
                    -int(_compact_title(strip_variety_issue_suffix(item.name)) == _compact_title(primary_query)),
                    -item.ratio,
                    -item.simi,
                    self._provider_rank.get(item.provider, len(self._provider_order)),
                ),
            )
        if requested_episode is not None:
            matching = [
                item
                for item in results
                if extract_episode_number(item.name) == requested_episode
                and episode_title_matches(normalized, item.name)
            ]
            if not matching and preferred_key is not None and not provider_filter:
                fallback_keys = [
                    key for key in self._provider_order if key in self._providers and key != preferred_key
                ]
                if fallback_keys:
                    results.extend(self._collect_search_results(fallback_keys, primary_query, normalized))
                    results = _filter_too_short_duration_candidates(results)
                    matching = [
                        item
                        for item in results
                        if extract_episode_number(item.name) == requested_episode
                        and episode_title_matches(normalized, item.name)
                    ]
            no_episode = [
                item
                for item in results
                if extract_episode_number(item.name) is None
                and (
                    not explicit_episode_request
                    or episode_title_matches(normalized, item.name)
                )
            ]
            if matching:
                results = [*matching, *no_episode]
            elif not explicit_episode_request and no_episode:
                results = no_episode
            else:
                results = []
        if requested_episode is not None and not explicit_episode_request:
            results = _filter_short_duration_candidates_for_implicit_request(results)
        if requested_episode is None:
            results = _filter_title_only_movie_noise(primary_query, results)

        def sort_key(item: DanmakuSearchItem) -> tuple[int, int, int, int, int, float, float, int]:
            item_episode = extract_episode_number(item.name)
            no_episode_priority = 0
            episode_priority = 0
            movie_exact_priority = 0
            movie_variant_priority = 0
            supplemental_penalty = 0
            duration_priority = item.duration_seconds
            explicit_episode_priority = 0
            if requested_episode is not None:
                if explicit_episode_request:
                    episode_priority = int(item_episode == requested_episode)
                    explicit_episode_priority = episode_priority
                else:
                    no_episode_priority = int(item_episode is None)
                    episode_priority = int(item_episode == requested_episode)
                    movie_exact_priority, movie_variant_priority, supplemental_penalty = _movie_candidate_priority(
                        primary_query, item.name
                    )
            elif item_episode is None:
                movie_exact_priority, movie_variant_priority, supplemental_penalty = _movie_candidate_priority(
                    primary_query, item.name
                )
            return (
                -no_episode_priority,
                -movie_exact_priority,
                -movie_variant_priority,
                supplemental_penalty,
                -explicit_episode_priority,
                -duration_priority,
                -episode_priority,
                -item.ratio,
                -item.simi,
                self._provider_rank.get(item.provider, len(self._provider_order)),
            )

        return sorted(
            results,
            key=sort_key,
        )

    def _collect_search_results(
        self, provider_keys: list[str], query_name: str, original_name: str | None = None
    ) -> list[DanmakuSearchItem]:
        results: list[DanmakuSearchItem] = []
        for batch in iter_bounded_settled(
            provider_keys,
            lambda key: (key, self._providers[key].search(query_name, original_name=original_name)),
        ):
            for settled in batch:
                if settled.error is not None:
                    logger.warning(
                        "Danmaku provider search failed provider_batch name=%s error=%s",
                        query_name,
                        settled.error,
                    )
                    continue
                key, provider_items = settled.value
                for item in provider_items:
                    if should_filter_name(query_name, item.name):
                        continue
                    ratio = item.ratio or similarity_score(query_name, item.name)
                    simi = item.simi or ratio
                    results.append(replace(item, ratio=ratio, simi=simi))
        return results

    def _danmaku_source_option_sort_key(
        self,
        option: DanmakuSourceOption,
        *,
        query_name: str,
        preferred_provider: str,
        preferred_page_url: str,
        reg_src: str,
        media_duration_seconds: int,
        stable_index: int,
    ) -> tuple[int, ...]:
        variety_issue_match, exact_episode_match = _source_option_query_match_priority(query_name, option)
        preferred_page = int(bool(preferred_page_url) and option.url == preferred_page_url)
        preferred_provider_match = int(bool(preferred_provider) and option.provider == preferred_provider)
        reg_src_provider_match = int(option.provider == self._preferred_provider_key(reg_src))
        duration_known = int(option.duration_seconds > 0 and media_duration_seconds > 0)
        duration_gap = abs(option.duration_seconds - media_duration_seconds) if duration_known else 10**9
        return (
            -variety_issue_match,
            -exact_episode_match,
            -preferred_page,
            -preferred_provider_match,
            -reg_src_provider_match,
            -int(option.episode_match),
            -duration_known,
            duration_gap,
            stable_index,
        )

    def _group_ranked_source_rows(
        self,
        ranked_rows: list[tuple[DanmakuSourceGroup, DanmakuSourceOption, int]],
        query_name: str,
        preferred_provider: str,
        preferred_page_url: str,
        reg_src: str,
    ) -> DanmakuSourceSearchResult:
        grouped_options: dict[str, list[DanmakuSourceOption]] = {}
        grouped_option_indexes: dict[str, dict[str, int]] = {}
        group_meta: dict[str, DanmakuSourceGroup] = {}
        ordered_providers: list[str] = []
        for source_group, option, _ in ranked_rows:
            provider = source_group.provider
            if provider not in grouped_options:
                grouped_options[provider] = []
                grouped_option_indexes[provider] = {}
                group_meta[provider] = source_group
                ordered_providers.append(provider)
            option_key = self._dedupe_source_option_key(option)
            existing_index = grouped_option_indexes[provider].get(option_key)
            if existing_index is None:
                grouped_option_indexes[provider][option_key] = len(grouped_options[provider])
                grouped_options[provider].append(option)
            else:
                grouped_options[provider][existing_index] = self._merge_source_options(
                    grouped_options[provider][existing_index],
                    option,
                )
        groups = [
            DanmakuSourceGroup(
                provider=provider,
                provider_label=group_meta[provider].provider_label,
                options=grouped_options[provider],
                preferred_by_history=group_meta[provider].preferred_by_history,
            )
            for provider in ordered_providers
        ]
        default_option = self._pick_default_source_option(
            groups,
            query_name=query_name,
            preferred_provider=preferred_provider,
            preferred_page_url=preferred_page_url,
            reg_src=reg_src,
        )
        return DanmakuSourceSearchResult(
            groups=groups,
            default_option_url=default_option.url if default_option is not None else "",
            default_provider=default_option.provider if default_option is not None else "",
        )

    def _pick_default_source_option(
        self,
        groups: list[DanmakuSourceGroup],
        *,
        query_name: str,
        preferred_provider: str,
        preferred_page_url: str,
        reg_src: str,
    ) -> DanmakuSourceOption | None:
        preferred_option = None
        best_query_match = (0, 0)
        best_query_option = None
        if query_name:
            for group in groups:
                for option in group.options:
                    match_priority = _source_option_query_match_priority(query_name, option)
                    if match_priority > best_query_match:
                        best_query_match = match_priority
                        best_query_option = option
                    if preferred_page_url and option.url == preferred_page_url:
                        preferred_option = option
            if preferred_option is not None and _source_option_query_match_priority(query_name, preferred_option) >= best_query_match:
                return preferred_option
            if best_query_option is not None and best_query_match > (0, 0):
                return best_query_option
        elif preferred_page_url:
            for group in groups:
                for option in group.options:
                    if option.url == preferred_page_url:
                        return option
        if preferred_provider:
            for group in groups:
                if group.provider == preferred_provider and group.options:
                    return group.options[0]
        matched_provider = self._preferred_provider_key(reg_src)
        if matched_provider:
            for group in groups:
                if group.provider == matched_provider and group.options:
                    return group.options[0]
        for group in groups:
            if group.options:
                return group.options[0]
        return None

    def _dedupe_source_option_key(self, option: DanmakuSourceOption) -> str:
        url = option.url.strip()
        if url:
            return url
        return f"name:{option.name.strip()}"

    def _merge_source_options(
        self,
        existing: DanmakuSourceOption,
        incoming: DanmakuSourceOption,
    ) -> DanmakuSourceOption:
        merged_context = dict(existing.resolve_context)
        for key, value in incoming.resolve_context.items():
            if value in ("", None, 0):
                continue
            merged_context[key] = value
        return replace(
            existing,
            name=existing.name or incoming.name,
            ratio=max(existing.ratio, incoming.ratio),
            simi=max(existing.simi, incoming.simi),
            duration_seconds=existing.duration_seconds or incoming.duration_seconds,
            episode_match=existing.episode_match or incoming.episode_match,
            preferred_by_history=existing.preferred_by_history or incoming.preferred_by_history,
            resolve_ready=existing.resolve_ready or incoming.resolve_ready,
            resolve_context=merged_context,
        )

    def resolve_danmu(self, page_url: str, option: DanmakuSourceOption | None = None) -> str:
        for key in self._provider_order:
            provider = self._providers.get(key)
            if provider is None or not provider.supports(page_url):
                continue
            if option is not None and option.url == page_url:
                prime_resolve_context = getattr(provider, "prime_resolve_context", None)
                if callable(prime_resolve_context):
                    prime_resolve_context(page_url, option.resolve_context)
            records = provider.resolve(page_url)
            if not records:
                raise DanmakuEmptyResultError(f"未找到弹幕: {page_url}")
            return build_xml(records)
        raise ProviderNotSupportedError(f"不支持的弹幕来源: {page_url}")


def create_default_danmaku_service(get=httpx.get, post=httpx.post) -> DanmakuService:
    providers = {
        "tencent": TencentDanmakuProvider(get=get, post=post),
        "youku": YoukuDanmakuProvider(get=get, post=post),
        "bilibili": BilibiliDanmakuProvider(get=get),
        "iqiyi": IqiyiDanmakuProvider(get=get),
        "mgtv": MgtvDanmakuProvider(get=get),
        "sohu": SohuDanmakuProvider(get=get),
    }
    return DanmakuService(providers, provider_order=["tencent", "youku", "bilibili", "iqiyi", "mgtv", "sohu"])
