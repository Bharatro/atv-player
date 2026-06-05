from __future__ import annotations

from collections.abc import Mapping


DEFAULT_PAGE_SIZE = 30


class PageInfo(int):
    def __new__(cls, pagecount: int, total: int | None = None):
        normalized_pagecount = max(0, int(pagecount or 0))
        obj = int.__new__(cls, normalized_pagecount)
        obj.pagecount = normalized_pagecount
        obj.total = max(0, int(total if total is not None else normalized_pagecount))
        return obj


def coerce_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def page_count_from_total(total: int, page_size: int = DEFAULT_PAGE_SIZE) -> PageInfo:
    normalized_page_size = max(1, int(page_size or DEFAULT_PAGE_SIZE))
    normalized_total = max(0, int(total or 0))
    if normalized_total <= 0:
        return PageInfo(0, normalized_total)
    return PageInfo((normalized_total + normalized_page_size - 1) // normalized_page_size, normalized_total)


def page_count_from_payload(
    payload: Mapping[str, object],
    fallback_total: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PageInfo:
    page_count = coerce_nonnegative_int(payload.get("pagecount"))
    raw_total = payload.get("total")
    total = coerce_nonnegative_int(raw_total) if raw_total is not None else max(0, fallback_total)
    if page_count > 0:
        return PageInfo(page_count, total)
    return page_count_from_total(total, page_size=page_size)
