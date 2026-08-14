"""字幕搜索编排。

职责：并发扇出到各字幕站、归一排序、把失败按站点收敛，保证单站挂掉不影响整体。
排序口径：简英双语 > 繁英/中英 > 简体 > 中文 > 繁体 > 英文（见 languages.py），
集数匹配与站点偏好作为次级排序键。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import httpx

from atv_player.danmaku.providers._concurrency import iter_bounded_settled
from atv_player.danmaku.utils import (
    extract_episode_number,
    normalize_name,
    strip_episode_suffix,
)
from atv_player.subtitles.errors import (
    SubtitleProviderError,
)
from atv_player.subtitles.matcher import apply_scores
from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleProviderGroup,
    SubtitleQuery,
    SubtitleSearchItem,
    SubtitleSearchResult,
)
from atv_player.subtitles.providers.assrt import AssrtSubtitleProvider
from atv_player.subtitles.providers.base import SubtitleProvider
from atv_player.subtitles.providers.opensubtitles import OpenSubtitlesProvider
from atv_player.subtitles.providers.subdl import SubDLSubtitleProvider
from atv_player.subtitles.providers.subhd import SubHDSubtitleProvider
from atv_player.subtitles.providers.subsource import SubsourceSubtitleProvider
from atv_player.subtitles.providers.zimuku import ZimukuSubtitleProvider
from atv_player.subtitles.release_parser import parse_release_name

logger = logging.getLogger(__name__)

# 站点默认顺序：官方 API 且稳定的排前面，抓取站次之，备用站垫后
DEFAULT_PROVIDER_ORDER = [
    "subdl",
    "subhd",
    "zimuku",
    "assrt",
    "subsource",
    "opensubtitles",
]

_SEASON_EPISODE = re.compile(r"[sS](\d{1,2})[eE](\d{1,3})")
_BARE_EPISODE = re.compile(r"(?:^|[^a-zA-Z0-9])[eE][pP]?(\d{1,3})(?:$|[^0-9])")


def episode_of(text: str) -> int | None:
    """从字幕名里取集数，兼容 SxxExx / Exx 与中文"第 x 集"。"""
    if not text:
        return None
    matched = _SEASON_EPISODE.search(text)
    if matched is not None:
        return int(matched.group(2))
    matched = _BARE_EPISODE.search(text)
    if matched is not None:
        return int(matched.group(1))
    return extract_episode_number(normalize_name(text))


def build_subtitle_query(
    *,
    title: str = "",
    file_name: str = "",
    episode: int | None = None,
    season: int | None = None,
    year: int = 0,
    imdb_id: str = "",
    tmdb_id: str = "",
) -> SubtitleQuery:
    """把播放项信息整理成一次字幕查询。

    优先级：已有的 IMDb/TMDB id > 显式传入的片名与季集 > 从文件名解析出的字段。
    文件名解析出的画质/片源/编码不参与搜索关键词，只用于匹配打分（见 matcher）。
    """
    parsed = parse_release_name(file_name) if file_name else None
    resolved_title = str(title or "").strip()
    if not resolved_title and parsed is not None:
        resolved_title = parsed.title
    # 片名里若带着"第 N 集"之类的后缀，搜索时要去掉，否则站点几乎搜不到
    search_title = (
        strip_episode_suffix(normalize_name(resolved_title)) or resolved_title
    )
    resolved_episode = episode
    if resolved_episode is None:
        if parsed is not None and parsed.episode is not None:
            resolved_episode = parsed.episode
        elif resolved_title:
            resolved_episode = extract_episode_number(normalize_name(resolved_title))
    resolved_season = season
    if resolved_season is None and parsed is not None:
        resolved_season = parsed.season
    return SubtitleQuery(
        title=search_title.strip(),
        episode=resolved_episode,
        season=resolved_season,
        year=year or (parsed.year if parsed is not None else 0),
        imdb_id=str(imdb_id or "").strip(),
        tmdb_id=str(tmdb_id or "").strip(),
        file_name=str(file_name or "").strip(),
        resolution=parsed.resolution if parsed is not None else "",
        source=parsed.source if parsed is not None else "",
        codec=parsed.codec if parsed is not None else "",
        release_group=parsed.release_group if parsed is not None else "",
    )


class SubtitleSearchService:
    def __init__(
        self,
        providers: dict[str, SubtitleProvider],
        provider_order: list[str] | None = None,
        disabled_provider_ids_loader: Callable[[], list[str]] | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self._providers = dict(providers)
        order = list(provider_order or DEFAULT_PROVIDER_ORDER)
        self._provider_order = [key for key in order if key in self._providers]
        self._provider_order.extend(
            key for key in self._providers if key not in self._provider_order
        )
        self._provider_rank = {
            key: index for index, key in enumerate(self._provider_order)
        }
        self._disabled_provider_ids_loader = disabled_provider_ids_loader
        self._max_concurrency = max(1, max_concurrency)

    def _disabled_provider_ids(self) -> set[str]:
        if self._disabled_provider_ids_loader is None:
            return set()
        try:
            return {
                str(item or "").strip()
                for item in self._disabled_provider_ids_loader()
            }
        except Exception:
            logger.exception("Failed to load disabled subtitle provider ids")
            return set()

    @property
    def provider_order(self) -> list[str]:
        disabled = self._disabled_provider_ids()
        return [key for key in self._provider_order if key not in disabled]

    def provider_label(self, provider_id: str) -> str:
        provider = self._providers.get(provider_id)
        return getattr(provider, "label", provider_id) if provider else provider_id

    def search(
        self,
        query: SubtitleQuery,
        *,
        provider_filter: str = "",
    ) -> SubtitleSearchResult:
        keys = self.provider_order
        if provider_filter:
            keys = [key for key in keys if key == provider_filter]
        pending: list[str] = []
        skipped: list[str] = []
        for key in keys:
            provider = self._providers[key]
            try:
                usable = provider.available()
            except Exception:
                logger.exception(
                    "Subtitle provider availability check failed key=%s", key
                )
                usable = False
            if usable:
                pending.append(key)
            else:
                skipped.append(key)

        collected: dict[str, list[SubtitleSearchItem]] = {}
        errors: dict[str, str] = {}
        for batch in iter_bounded_settled(
            pending,
            lambda key: self._search_one(key, query),
            max_workers=self._max_concurrency,
        ):
            for settled in batch:
                if settled.error is not None:
                    # _search_one 已经吞掉了 provider 自身的异常，走到这里说明是
                    # 调度层面的意外失败，无法归属到具体站点，只记日志
                    logger.warning("Subtitle search worker failed: %s", settled.error)
                    continue
                provider_id, items, error = settled.value
                if error is not None:
                    errors[provider_id] = str(error) or error.__class__.__name__
                    continue
                collected[provider_id] = items

        groups = self._build_groups(collected, query)
        return SubtitleSearchResult(groups=groups, errors=errors, skipped=skipped)

    def _search_one(
        self,
        provider_id: str,
        query: SubtitleQuery,
    ) -> tuple[str, list[SubtitleSearchItem], Exception | None]:
        """在 worker 内部就把异常和 provider id 绑定，避免并发返回后无法归属。"""
        try:
            items = list(self._providers[provider_id].search(query) or [])
            return provider_id, items, None
        except Exception as exc:
            logger.warning(
                "Subtitle provider search failed key=%s error=%s", provider_id, exc
            )
            return provider_id, [], exc

    def _build_groups(
        self,
        collected: dict[str, list[SubtitleSearchItem]],
        query: SubtitleQuery,
    ) -> list[SubtitleProviderGroup]:
        groups: list[SubtitleProviderGroup] = []
        for provider_id, items in collected.items():
            deduped = self._dedupe(items)
            if not deduped:
                continue
            deduped = apply_scores(deduped, query)
            provider = self._providers.get(provider_id)
            groups.append(
                SubtitleProviderGroup(
                    provider=provider_id,
                    provider_label=getattr(provider, "label", provider_id),
                    items=deduped,
                    notice=getattr(provider, "notice", ""),
                )
            )
        groups.sort(key=lambda group: self._group_sort_key(group))
        return groups

    @staticmethod
    def _dedupe(items: list[SubtitleSearchItem]) -> list[SubtitleSearchItem]:
        seen: set[tuple[str, str]] = set()
        result: list[SubtitleSearchItem] = []
        for item in items:
            key = (item.provider, item.subtitle_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _group_sort_key(self, group: SubtitleProviderGroup) -> tuple[int, int]:
        # 组内已按分数排好，用最高分代表该站，站点默认顺序仅作同分时的兜底
        best_score = max((item.score for item in group.items), default=0)
        return (
            -best_score,
            self._provider_rank.get(group.provider, len(self._provider_rank)),
        )

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        provider = self._providers.get(item.provider)
        if provider is None:
            raise SubtitleProviderError(f"未知字幕来源: {item.provider}")
        content = provider.download(item)
        if not content.text.strip():
            raise SubtitleProviderError("下载到的字幕内容为空")
        return content


def create_default_subtitle_service(
    get=httpx.get,
    post=httpx.post,
    config_loader=None,
    disabled_provider_ids_loader: Callable[[], list[str]] | None = None,
) -> SubtitleSearchService:
    def _config_value(attribute: str) -> str:
        if config_loader is None:
            return ""
        try:
            return str(getattr(config_loader(), attribute, "") or "").strip()
        except Exception:
            return ""

    providers: dict[str, SubtitleProvider] = {
        "subdl": SubDLSubtitleProvider(
            get=get,
            api_key_loader=lambda: _config_value("subtitle_subdl_api_key"),
        ),
        "subhd": SubHDSubtitleProvider(get=get, post=post),
        "zimuku": ZimukuSubtitleProvider(get=get),
        "assrt": AssrtSubtitleProvider(
            get=get,
            token_loader=lambda: _config_value("subtitle_assrt_token"),
        ),
        "subsource": SubsourceSubtitleProvider(
            get=get,
            api_key_loader=lambda: _config_value("subtitle_subsource_api_key"),
        ),
        "opensubtitles": OpenSubtitlesProvider(
            get=get,
            post=post,
            api_key_loader=lambda: _config_value("subtitle_opensubtitles_api_key"),
        ),
    }
    return SubtitleSearchService(
        providers,
        provider_order=list(DEFAULT_PROVIDER_ORDER),
        disabled_provider_ids_loader=disabled_provider_ids_loader,
    )
