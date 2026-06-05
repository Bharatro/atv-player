from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_VALID_MEDIA_KINDS = {"anime", "movie", "live_action", ""}


@dataclass(slots=True)
class MetadataQueryRefinementInput:
    title: str
    year: str = ""
    category_name: str = ""
    season_number: int = 0
    source_name: str = ""


@dataclass(slots=True)
class MetadataQueryRefinement:
    title: str = ""
    year: str = ""
    season_number: int = 0
    media_kind: str = ""
    alternative_titles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DanmakuQueryRefinementInput:
    title: str
    media_title: str = ""
    episode_title: str = ""
    episode_number: int = 0
    year: str = ""


@dataclass(slots=True)
class DanmakuQueryRefinement:
    queries: list[str] = field(default_factory=list)
    episode_number: int = 0
    reason: str = ""


@dataclass(slots=True)
class EpisodeTitleRewriteItem:
    index: int
    original_title: str
    display_title: str = ""


@dataclass(slots=True)
class EpisodeTitleRewriteInput:
    media_title: str
    items: list[EpisodeTitleRewriteItem] = field(default_factory=list)
    metadata_titles: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class EpisodeTitleRewrite:
    titles_by_index: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class FollowingDetailSummaryInput:
    title: str
    media_kind: str = ""
    current_episode: int = 0
    latest_episode: int = 0
    total_episodes: int = 0
    overview: str = ""
    next_episode_title: str = ""
    next_episode_air_date: str = ""
    metadata_fields: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class FollowingDetailSummary:
    summary: str = ""
    highlights: list[str] = field(default_factory=list)
    next_hint: str = ""


def _json_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {}


def _string(value: object, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _safe_title(value: object) -> str:
    text = _string(value, limit=180)
    return re.split(r"[\\/]", text)[-1]


def _string_list(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item, limit=80)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, int | float | str):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class AIEnrichmentService:
    def __init__(self, client) -> None:
        self._client = client

    def _complete(self, system: str, payload: dict[str, object]) -> dict[str, Any]:
        result = self._client.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return _json_payload(result.content)

    def refine_metadata_query(
        self,
        data: MetadataQueryRefinementInput,
    ) -> MetadataQueryRefinement:
        try:
            payload = self._complete(
                "你是影视元数据搜索 query 清洗器。只输出 JSON，不要解释。",
                {
                    "title": _safe_title(data.title),
                    "year": _string(data.year, limit=16),
                    "category_name": _string(data.category_name, limit=40),
                    "season_number": _int_value(data.season_number),
                },
            )
        except Exception:
            logger.debug("AI metadata query refinement failed", exc_info=True)
            return MetadataQueryRefinement()
        media_kind = _string(payload.get("media_kind"), limit=24)
        return MetadataQueryRefinement(
            title=_string(payload.get("title"), limit=120),
            year=_string(payload.get("year"), limit=16),
            season_number=_int_value(payload.get("season_number")),
            media_kind=media_kind if media_kind in _VALID_MEDIA_KINDS else "",
            alternative_titles=_string_list(payload.get("alternative_titles"), limit=4),
        )

    def refine_danmaku_query(
        self,
        data: DanmakuQueryRefinementInput,
    ) -> DanmakuQueryRefinement:
        try:
            payload = self._complete(
                "你是弹幕搜索 query 清洗器。只输出 JSON，不要解释。",
                {
                    "title": _safe_title(data.title),
                    "media_title": _string(data.media_title, limit=120),
                    "episode_title": _string(data.episode_title, limit=120),
                    "episode_number": _int_value(data.episode_number),
                    "year": _string(data.year, limit=16),
                },
            )
        except Exception:
            logger.debug("AI danmaku query refinement failed", exc_info=True)
            return DanmakuQueryRefinement()
        return DanmakuQueryRefinement(
            queries=_string_list(payload.get("queries"), limit=4),
            episode_number=_int_value(payload.get("episode_number")),
            reason=_string(payload.get("reason"), limit=120),
        )

    def rewrite_episode_titles(
        self,
        data: EpisodeTitleRewriteInput,
    ) -> EpisodeTitleRewrite:
        items = [
            {
                "index": item.index,
                "original_title": _safe_title(item.original_title),
                "display_title": _string(item.display_title, limit=120),
            }
            for item in data.items[:80]
        ]
        try:
            payload = self._complete(
                "你是影视分集标题改写器。只输出 JSON，不要解释。",
                {
                    "media_title": _string(data.media_title, limit=120),
                    "items": items,
                    "metadata_titles": {
                        str(index): _string(title, limit=120)
                        for index, title in data.metadata_titles.items()
                    },
                },
            )
        except Exception:
            logger.debug("AI episode title rewrite failed", exc_info=True)
            return EpisodeTitleRewrite()
        raw_map = payload.get("titles_by_index")
        titles: dict[int, str] = {}
        if isinstance(raw_map, dict):
            for key, value in raw_map.items():
                index = _int_value(key)
                title = _string(value, limit=120)
                if title:
                    titles[index] = title
        return EpisodeTitleRewrite(titles_by_index=titles)

    def summarize_following_detail(
        self,
        data: FollowingDetailSummaryInput,
    ) -> FollowingDetailSummary:
        try:
            payload = self._complete(
                "你是追更详情摘要助手。只输出 JSON，不要解释。",
                {
                    "title": _string(data.title, limit=120),
                    "media_kind": _string(data.media_kind, limit=40),
                    "current_episode": _int_value(data.current_episode),
                    "latest_episode": _int_value(data.latest_episode),
                    "total_episodes": _int_value(data.total_episodes),
                    "overview": _string(data.overview, limit=600),
                    "next_episode_title": _string(data.next_episode_title, limit=120),
                    "next_episode_air_date": _string(
                        data.next_episode_air_date,
                        limit=32,
                    ),
                    "metadata_fields": [
                        {
                            "label": _string(field.get("label"), limit=40),
                            "value": _string(field.get("value"), limit=160),
                        }
                        for field in data.metadata_fields[:12]
                    ],
                },
            )
        except Exception:
            logger.debug("AI following detail summary failed", exc_info=True)
            return FollowingDetailSummary()
        return FollowingDetailSummary(
            summary=_string(payload.get("summary"), limit=280),
            highlights=_string_list(payload.get("highlights"), limit=3),
            next_hint=_string(payload.get("next_hint"), limit=120),
        )
