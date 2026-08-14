"""字幕匹配打分。

不要直接取搜索结果的第一条：字幕站的相关度排序很粗糙，同名不同季、不同发布
版本混在一起。这里按多个维度打分，权重集中定义在 ``MatchWeights``，便于调整，
不散落在各处。

分数换算成百分比时，分母只统计"本次查询实际能判定的维度"——比如查询里没有年份
就不把年份权重计入满分，否则电影/剧集的百分比不可比。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from atv_player.danmaku.utils import normalize_name, similarity_score
from atv_player.subtitles.languages import language_rank
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem
from atv_player.subtitles.release_parser import equivalent_tokens

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
# language_rank 的最大值（other），用于把语言排名换算成得分
_MAX_LANGUAGE_RANK = language_rank("other")


@dataclass(frozen=True, slots=True)
class MatchWeights:
    media_id: int = 50
    title: int = 30
    year: int = 10
    season: int = 30
    episode: int = 30
    language: int = 30
    release_group: int = 20
    resolution: int = 10
    source: int = 20
    codec: int = 10
    hearing_impaired: int = 5
    forced: int = 5


DEFAULT_MATCH_WEIGHTS = MatchWeights()


def _compact(text: str) -> str:
    return _NON_WORD.sub("", normalize_name(text or "")).casefold()


def _haystack(item: SubtitleSearchItem) -> str:
    return " ".join(
        part for part in (item.name, item.release_name, item.release_site) if part
    ).casefold()


def _token_present(haystack: str, token: str) -> bool:
    if not token:
        return False
    normalized = token.casefold()
    if normalized in haystack:
        return True
    # H.265 / H265 / h 265 视为同一个词
    return normalized.replace(".", "").replace("-", "") in haystack.replace(
        ".", ""
    ).replace("-", "")


def score_subtitle(
    item: SubtitleSearchItem,
    query: SubtitleQuery,
    *,
    weights: MatchWeights = DEFAULT_MATCH_WEIGHTS,
) -> tuple[int, int]:
    """返回 ``(得分, 匹配百分比)``。"""
    haystack = _haystack(item)
    score = 0.0
    max_score = 0.0

    if query.has_media_id:
        max_score += weights.media_id
        media_ids = [value for value in (query.imdb_id, query.tmdb_id) if value]
        if any(_token_present(haystack, value) for value in media_ids):
            score += weights.media_id

    if query.title:
        max_score += weights.title
        query_title = _compact(query.title)
        item_title = _compact(item.name)
        if query_title and query_title == item_title:
            score += weights.title
        elif query_title and query_title in item_title:
            score += weights.title * 0.8
        else:
            similarity = similarity_score(
                normalize_name(query.title), normalize_name(item.name)
            )
            score += weights.title * max(0.0, min(1.0, similarity))

    if query.year:
        max_score += weights.year
        if str(query.year) in haystack:
            score += weights.year

    if query.season is not None:
        max_score += weights.season
        if item.season == query.season:
            score += weights.season
        elif item.season is None and _token_present(haystack, f"s{query.season:02d}"):
            score += weights.season

    if query.episode is not None:
        max_score += weights.episode
        if item.episode == query.episode:
            score += weights.episode
        elif item.episode is None and _token_present(haystack, f"e{query.episode:02d}"):
            score += weights.episode

    # 语言总是参与打分：越靠前的语言（简英双语最高）得分越高
    max_score += weights.language
    rank = language_rank(item.language)
    score += weights.language * max(
        0.0, (_MAX_LANGUAGE_RANK - rank) / _MAX_LANGUAGE_RANK
    )

    for token, weight in (
        (query.release_group, weights.release_group),
        (query.resolution, weights.resolution),
        (query.source, weights.source),
        (query.codec, weights.codec),
    ):
        if token:
            max_score += weight
            candidates = equivalent_tokens(token) or (token,)
            if any(_token_present(haystack, alias) for alias in candidates):
                score += weight

    # 听障/强制字幕只作为小幅加分，不计入满分，避免稀释百分比
    if item.hearing_impaired:
        score += weights.hearing_impaired
    if item.forced:
        score += weights.forced

    total = int(round(score))
    percent = int(round(100 * score / max_score)) if max_score > 0 else 0
    return total, max(0, min(100, percent))


def apply_scores(
    items: list[SubtitleSearchItem],
    query: SubtitleQuery,
    *,
    weights: MatchWeights = DEFAULT_MATCH_WEIGHTS,
) -> list[SubtitleSearchItem]:
    """给每条候选打分并按分数从高到低排序。"""
    from dataclasses import replace

    scored = []
    for item in items:
        score, percent = score_subtitle(item, query, weights=weights)
        scored.append(replace(item, score=score, match_percent=percent))
    scored.sort(
        key=lambda row: (
            -row.score,
            language_rank(row.language),
            -row.download_count,
            -row.vote_score,
        )
    )
    return scored
