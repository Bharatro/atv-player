from __future__ import annotations

from collections.abc import Mapping


DEFAULT_PAGE_SIZE = 30


def coerce_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def page_count_from_total(total: int, page_size: int = DEFAULT_PAGE_SIZE) -> int:
    normalized_page_size = max(1, int(page_size or DEFAULT_PAGE_SIZE))
    if total <= 0:
        return 0
    return (total + normalized_page_size - 1) // normalized_page_size


def page_count_from_payload(
    payload: Mapping[str, object],
    fallback_total: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> int:
    page_count = coerce_nonnegative_int(payload.get("pagecount"))
    if page_count > 0:
        return page_count
    raw_total = payload.get("total")
    total = coerce_nonnegative_int(raw_total) if raw_total is not None else max(0, fallback_total)
    return page_count_from_total(total, page_size=page_size)
