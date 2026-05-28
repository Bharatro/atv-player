from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.search.models import RankedSmartSearchCandidate, SmartSearchCandidate


def _haystack(candidate: SmartSearchCandidate) -> str:
    return " ".join(
        [
            candidate.title,
            candidate.subtitle,
            candidate.remarks,
            candidate.overview,
            candidate.year,
            candidate.area,
            candidate.language,
            candidate.actors,
            " ".join(candidate.genres),
        ]
    ).lower()


def _contains_any(text: str, values: list[str]) -> bool:
    return any(
        str(value or "").strip().lower() in text
        for value in values
        if str(value or "").strip()
    )


def rank_candidates(
    candidates: list[SmartSearchCandidate],
    intent: SmartSearchIntent,
) -> list[RankedSmartSearchCandidate]:
    ranked: list[RankedSmartSearchCandidate] = []
    for candidate in candidates:
        text = _haystack(candidate)
        if _contains_any(text, intent.negative_keywords):
            continue
        score = 0.0
        reasons: list[str] = []
        for keyword in intent.keywords:
            normalized = str(keyword or "").strip()
            if normalized and normalized.lower() in text:
                score += 3.0
                reasons.append(f"{normalized}匹配")
        for genre in intent.genres:
            normalized = str(genre or "").strip()
            if normalized and normalized.lower() in text:
                score += 4.0
                reasons.append(f"{normalized}匹配")
        if _contains_any(text, intent.reference_titles):
            score += 5.0
            reasons.append("与参考作品相关")
        if intent.rating_min and candidate.rating >= intent.rating_min:
            score += candidate.rating
            reasons.append(f"评分 {candidate.rating:.1f}")
        elif candidate.rating:
            score += candidate.rating / 3.0
        if candidate.source_label:
            score += 1.0
            reasons.append(f"来自{candidate.source_label}")
        if intent.sort_preference == "rating" and candidate.rating:
            score += candidate.rating / 2.0
        ranked.append(
            RankedSmartSearchCandidate(
                candidate=candidate,
                score=score,
                reasons=reasons,
            )
        )
    ranked.sort(
        key=lambda item: (item.score, item.candidate.rating, item.candidate.title),
        reverse=True,
    )
    return ranked
