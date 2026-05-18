from __future__ import annotations

import inspect
from typing import Any

from atv_player.danmaku.cache import (
    load_cached_danmaku_source_search_result,
    load_cached_danmaku_xml,
    save_cached_danmaku_source_search_result,
    save_cached_danmaku_xml,
)
from atv_player.danmaku.models import DanmakuSourceGroup, DanmakuSourceOption, DanmakuSourceSearchResult
from atv_player.danmaku.utils import has_explicit_episode_marker, infer_playlist_episode_number
from atv_player.models import PlayItem

_TITLE_ONLY_ITEM_TITLES = {
    "正片",
    "完整版",
    "全片",
    "电影",
    "播放",
}


def _compose_danmaku_search_query(title: str, episode: str) -> str:
    return " ".join(part for part in (title.strip(), episode.strip()) if part).strip()


def _looks_like_title_only_item(item: PlayItem) -> bool:
    return str(item.title or "").strip() in _TITLE_ONLY_ITEM_TITLES


def _default_episode_label(item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
    if _looks_like_title_only_item(item):
        return ""
    if not str(item.title or "").strip():
        return ""
    episode_number = infer_playlist_episode_number(item, playlist)
    if episode_number is None:
        return ""
    if str(item.title or "").strip().isdigit():
        return str(episode_number)
    return f"{episode_number}集" if has_explicit_episode_marker(item.title) or len(playlist or []) != 1 else ""


def _find_selected_option(item: PlayItem, page_url: str) -> DanmakuSourceOption | None:
    for group in item.danmaku_candidates:
        for option in group.options:
            if option.url == page_url:
                return option
    return None


class GenericDanmakuController:
    def __init__(self, danmaku_service: Any) -> None:
        self._danmaku_service = danmaku_service

    def _search_title(self, item: PlayItem) -> str:
        return item.danmaku_search_title.strip() or item.media_title.strip() or item.title.strip()

    def _search_episode(self, item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
        return item.danmaku_search_episode.strip() or _default_episode_label(item, playlist).strip()

    def _search_query(self, item: PlayItem, playlist: list[PlayItem] | None = None) -> str:
        if item.danmaku_search_query_overridden and item.danmaku_search_query.strip():
            return item.danmaku_search_query.strip()
        title = self._search_title(item)
        episode = self._search_episode(item, playlist)
        item.danmaku_search_title = title
        item.danmaku_search_episode = episode
        item.danmaku_search_query = _compose_danmaku_search_query(title, episode)
        return item.danmaku_search_query

    def _reg_src(self, item: PlayItem) -> str:
        return str(item.vod_id or item.url or "").strip()

    def _save_source_search_result(self, query_name: str, reg_src: str, result: DanmakuSourceSearchResult) -> None:
        save_cached_danmaku_source_search_result(query_name, reg_src, result)
        if reg_src:
            save_cached_danmaku_source_search_result(query_name, "", result)

    def _load_source_search_result(self, query_name: str, reg_src: str) -> DanmakuSourceSearchResult | None:
        cached = load_cached_danmaku_source_search_result(query_name, reg_src)
        if cached is not None or not reg_src:
            return cached
        return load_cached_danmaku_source_search_result(query_name, "")

    def _apply_source_search_result(self, item: PlayItem, result: DanmakuSourceSearchResult) -> None:
        item.danmaku_candidates = result.groups
        item.selected_danmaku_provider = result.default_provider
        item.selected_danmaku_url = result.default_option_url
        item.selected_danmaku_title = ""
        for group in result.groups:
            for option in group.options:
                if option.url == result.default_option_url:
                    item.selected_danmaku_title = option.name
                    break
            if item.selected_danmaku_title:
                break
        item.danmaku_error = ""

    def _rerank_source_search_result(
        self,
        result: DanmakuSourceSearchResult,
        *,
        query_name: str,
        reg_src: str,
        media_duration_seconds: int = 0,
    ) -> DanmakuSourceSearchResult:
        rerank = getattr(self._danmaku_service, "rerank_danmaku_source_search_result", None)
        if not callable(rerank):
            return result
        return rerank(
            result,
            query_name=query_name,
            reg_src=reg_src,
            media_duration_seconds=media_duration_seconds,
        )

    def _search_sources(
        self,
        query_name: str,
        reg_src: str,
        *,
        media_duration_seconds: int = 0,
        provider_filter: str = "",
    ) -> DanmakuSourceSearchResult:
        search_sources = getattr(self._danmaku_service, "search_danmu_sources", None)
        if callable(search_sources):
            kwargs = {"media_duration_seconds": media_duration_seconds}
            if "provider_filter" in inspect.signature(search_sources).parameters:
                kwargs["provider_filter"] = provider_filter
            return search_sources(query_name, reg_src, **kwargs)
        candidates = self._danmaku_service.search_danmu(query_name, reg_src, provider_filter=provider_filter)
        grouped: dict[str, list[DanmakuSourceOption]] = {}
        for item in candidates:
            grouped.setdefault(item.provider, []).append(
                DanmakuSourceOption(
                    provider=item.provider,
                    name=item.name,
                    url=item.url,
                    ratio=getattr(item, "ratio", 0.0),
                    simi=getattr(item, "simi", 0.0),
                    duration_seconds=getattr(item, "duration_seconds", 0),
                    resolve_context=dict(getattr(item, "resolve_context", {})),
                )
            )
        groups = [
            DanmakuSourceGroup(provider=provider, provider_label=provider, options=options)
            for provider, options in grouped.items()
        ]
        default_option = groups[0].options[0] if groups and groups[0].options else None
        return DanmakuSourceSearchResult(
            groups=groups,
            default_option_url="" if default_option is None else default_option.url,
            default_provider="" if default_option is None else default_option.provider,
        )

    def load_cached_danmaku_sources(
        self,
        item: PlayItem,
        playlist: list[PlayItem] | None = None,
        media_duration_seconds: int = 0,
    ) -> bool:
        query_name = self._search_query(item, playlist)
        reg_src = self._reg_src(item)
        if not query_name:
            return False
        cached = self._load_source_search_result(query_name, reg_src)
        if cached is None:
            return False
        self._apply_source_search_result(
            item,
            self._rerank_source_search_result(
                cached,
                query_name=query_name,
                reg_src=reg_src,
                media_duration_seconds=media_duration_seconds,
            ),
        )
        return True

    def refresh_danmaku_sources(
        self,
        item: PlayItem,
        query_override: str | None = None,
        search_title_override: str | None = None,
        search_episode_override: str | None = None,
        playlist: list[PlayItem] | None = None,
        force_refresh: bool = False,
        media_duration_seconds: int = 0,
        provider_filter: str = "",
    ) -> None:
        if search_title_override is not None:
            item.danmaku_search_title = search_title_override.strip()
        if search_episode_override is not None:
            item.danmaku_search_episode = search_episode_override.strip()
        if query_override is not None:
            item.danmaku_search_query = query_override.strip()
        item.danmaku_search_provider = provider_filter
        item.danmaku_search_query_overridden = (
            query_override is not None or search_title_override is not None or search_episode_override is not None
        )
        query_name = self._search_query(item, playlist)
        reg_src = self._reg_src(item)
        if not query_name:
            return
        if not force_refresh and not provider_filter and self.load_cached_danmaku_sources(
            item,
            playlist=playlist,
            media_duration_seconds=media_duration_seconds,
        ):
            return
        result = self._search_sources(
            query_name,
            reg_src,
            media_duration_seconds=media_duration_seconds,
            provider_filter=provider_filter,
        )
        if (
            not result.groups
            and item.danmaku_search_episode.strip()
            and item.danmaku_search_title.strip()
            and query_name == _compose_danmaku_search_query(item.danmaku_search_title, item.danmaku_search_episode)
        ):
            result = self._search_sources(
                item.danmaku_search_title.strip(),
                reg_src,
                media_duration_seconds=media_duration_seconds,
                provider_filter=provider_filter,
            )
            result = self._rerank_source_search_result(
                result,
                query_name=query_name,
                reg_src=reg_src,
                media_duration_seconds=media_duration_seconds,
            )
        if not provider_filter:
            self._save_source_search_result(query_name, reg_src, result)
        self._apply_source_search_result(item, result)

    def switch_danmaku_source(self, item: PlayItem, page_url: str) -> str:
        selected_option = _find_selected_option(item, page_url)
        query_name = item.danmaku_search_query.strip() or self._search_query(item)
        reg_src = self._reg_src(item)
        cached_xml = load_cached_danmaku_xml(query_name, page_url)
        if cached_xml:
            xml_text = cached_xml
        else:
            resolve = self._danmaku_service.resolve_danmu
            if selected_option is not None and "option" in inspect.signature(resolve).parameters:
                xml_text = resolve(page_url, option=selected_option)
            else:
                xml_text = resolve(page_url)
            save_cached_danmaku_xml(query_name, page_url, xml_text)
        if reg_src:
            save_cached_danmaku_xml(query_name, reg_src, xml_text)
        item.danmaku_xml = xml_text
        item.selected_danmaku_url = page_url
        if selected_option is not None:
            item.selected_danmaku_provider = selected_option.provider
            item.selected_danmaku_title = selected_option.name
        item.danmaku_error = ""
        return xml_text
