from __future__ import annotations

from difflib import SequenceMatcher
import re

from atv_player.episode_titles import extract_season_number
from atv_player.metadata.models import MetadataMatch, MetadataQuery

_MIN_CONFIDENT_MATCH_SCORE = 0.45


def normalize_match_title(value: object) -> str:
    return re.sub(r"[\s\-_:.：,，/\\|·•'\"`()（）《》【】\[\]]+", "", str(value or "").strip().lower())


def strip_match_season_suffix(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = re.sub(
        r"(?:\s*[-:：]\s*)?(?:第\s*[0-9零一二两三四五六七八九十百千]+\s*季|season\s*\d+|s\d+)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or text


def match_season_number(match: MetadataMatch) -> int | None:
    raw_season = match.raw.get("season_number")
    if isinstance(raw_season, int) and raw_season > 0:
        return raw_season
    provider_id = str(match.provider_id or "").strip()
    provider_id_match = re.search(r":season:(\d+)$", provider_id)
    if provider_id_match is not None:
        try:
            season_number = int(provider_id_match.group(1))
        except (TypeError, ValueError):
            season_number = 0
        if season_number > 0:
            return season_number
    return extract_season_number(match.title)


def is_confident_match(score: float) -> bool:
    return score >= _MIN_CONFIDENT_MATCH_SCORE


def score_match(query: MetadataQuery, match: MetadataMatch) -> float:
    explicit_score = float(match.score or 0.0)
    title_score = _title_similarity_score(query.title, match.title)
    score = max(explicit_score, title_score)

    query_season = extract_season_number(query.title)
    match_season = match_season_number(match)
    if query_season is not None:
        if match_season == query_season:
            score += 0.2
        elif match_season is not None:
            score -= 0.25

    query_year = str(query.year or "").strip()
    match_year = str(match.year or "").strip()
    if query_year and match_year:
        if query_year == match_year:
            score += 0.05
        else:
            score -= 0.08

    if match.provider == "iqiyi" and _is_full_exact_match(query.title, match.title):
        score += 0.15
    return score


def _title_similarity_score(query_title: str, match_title: str) -> float:
    normalized_query = normalize_match_title(query_title)
    normalized_match = normalize_match_title(match_title)
    if not normalized_query or not normalized_match:
        return 0.0
    if normalized_query == normalized_match:
        return 1.0

    query_base = normalize_match_title(strip_match_season_suffix(query_title))
    match_base = normalize_match_title(strip_match_season_suffix(match_title))
    if query_base and query_base == match_base:
        return 0.78
    if query_base and match_base and (query_base in match_base or match_base in query_base):
        return 0.65
    return SequenceMatcher(a=query_base or normalized_query, b=match_base or normalized_match).ratio() * 0.6


def _is_full_exact_match(query_title: str, match_title: str) -> bool:
    return normalize_match_title(query_title) == normalize_match_title(match_title)
