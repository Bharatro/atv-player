from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


_VALID_MODES = {"title_search", "smart_discovery"}
_VALID_SORTS = {"rating", "popularity", "recent", "relevance"}


@dataclass(slots=True)
class SmartSearchIntent:
    query_text: str
    mode: str = "title_search"
    media_types: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    mood: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    year_min: int = 0
    year_max: int = 0
    rating_min: float = 0.0
    max_runtime_minutes: int = 0
    keywords: list[str] = field(default_factory=list)
    reference_titles: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    sort_preference: str = "relevance"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item or "").strip()
        for item in value
        if str(item or "").strip()
    ]


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fallback_intent(query_text: str) -> SmartSearchIntent:
    normalized = str(query_text or "").strip()
    return SmartSearchIntent(
        query_text=normalized,
        keywords=[normalized] if normalized else [],
    )


def _json_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {}


class SmartSearchIntentParser:
    def __init__(self, client) -> None:
        self._client = client

    def parse(self, query_text: str) -> SmartSearchIntent:
        normalized_query = str(query_text or "").strip()
        try:
            result = self._client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是影视搜索意图解析器。只输出 JSON，不要输出解释。"
                            "字段包含 mode, media_types, genres, mood, countries, languages, "
                            "year_min, year_max, rating_min, max_runtime_minutes, keywords, "
                            "reference_titles, negative_keywords, sort_preference。"
                        ),
                    },
                    {"role": "user", "content": normalized_query},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            payload = _json_payload(result.content)
        except Exception:
            return _fallback_intent(normalized_query)
        mode = str(payload.get("mode") or "title_search").strip()
        sort_preference = str(payload.get("sort_preference") or "relevance").strip()
        intent = SmartSearchIntent(
            query_text=normalized_query,
            mode=mode if mode in _VALID_MODES else "title_search",
            media_types=_string_list(payload.get("media_types")),
            genres=_string_list(payload.get("genres")),
            mood=_string_list(payload.get("mood")),
            countries=_string_list(payload.get("countries")),
            languages=_string_list(payload.get("languages")),
            year_min=_int_value(payload.get("year_min")),
            year_max=_int_value(payload.get("year_max")),
            rating_min=max(0.0, min(_float_value(payload.get("rating_min")), 10.0)),
            max_runtime_minutes=max(0, _int_value(payload.get("max_runtime_minutes"))),
            keywords=_string_list(payload.get("keywords")),
            reference_titles=_string_list(payload.get("reference_titles")),
            negative_keywords=_string_list(payload.get("negative_keywords")),
            sort_preference=sort_preference
            if sort_preference in _VALID_SORTS
            else "relevance",
        )
        if not intent.keywords:
            intent.keywords = [normalized_query] if normalized_query else []
        return intent
