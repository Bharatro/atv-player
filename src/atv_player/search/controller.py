from __future__ import annotations

import re

from atv_player.models import HistoryRecord, VodItem
from atv_player.search.models import SmartSearchCandidate
from atv_player.search.ranking import rank_candidates


_RATING_RE = re.compile(r"(?<!\d)([0-9](?:\.[0-9])?|10(?:\.0)?)(?!\d)")


def _rating_from_text(text: str) -> float:
    matches = [float(match.group(1)) for match in _RATING_RE.finditer(str(text or ""))]
    return max(matches) if matches else 0.0


def _vod_from_ranked(candidate: SmartSearchCandidate, reasons: list[str]) -> VodItem:
    if candidate.vod_item is not None:
        item = candidate.vod_item
    else:
        item = VodItem(
            vod_id=candidate.vod_id,
            vod_name=candidate.title,
            vod_pic=candidate.poster,
            vod_remarks=candidate.remarks,
        )
    item.type_name = "智能匹配"
    reason_text = " / ".join(reasons[:3])
    if reason_text:
        item.vod_remarks = reason_text
    return item


class SmartSearchController:
    def __init__(
        self,
        *,
        intent_parser,
        favorites_controller=None,
        following_controller=None,
        history_controller=None,
        page_size: int = 20,
    ) -> None:
        self._intent_parser = intent_parser
        self._favorites_controller = favorites_controller
        self._following_controller = following_controller
        self._history_controller = history_controller
        self._page_size = page_size

    def search_items(self, keyword: str, page: int) -> tuple[list[VodItem], int]:
        try:
            intent = self._intent_parser.parse(keyword)
        except Exception:
            return [], 0
        candidates = self._load_candidates(intent.keywords or [keyword])
        ranked = rank_candidates(candidates, intent)
        start = max(page - 1, 0) * self._page_size
        end = start + self._page_size
        items = [
            _vod_from_ranked(item.candidate, item.reasons)
            for item in ranked[start:end]
        ]
        return items, len(ranked)

    def _load_candidates(self, keywords: list[str]) -> list[SmartSearchCandidate]:
        candidates: list[SmartSearchCandidate] = []
        seen: set[tuple[str, str]] = set()
        for keyword in [item for item in keywords if str(item or "").strip()]:
            candidates.extend(self._favorite_candidates(keyword, seen))
            candidates.extend(self._following_candidates(keyword, seen))
            candidates.extend(self._history_candidates(keyword, seen))
        return candidates

    def _favorite_candidates(
        self,
        keyword: str,
        seen: set[tuple[str, str]],
    ) -> list[SmartSearchCandidate]:
        if self._favorites_controller is None or not hasattr(
            self._favorites_controller,
            "search_items",
        ):
            return []
        cards, _total = self._favorites_controller.search_items(keyword, 1)
        candidates = []
        for card in cards:
            record = getattr(card, "record", None)
            if record is None:
                continue
            key = ("favorite", record.vod_id)
            if key in seen:
                continue
            seen.add(key)
            remarks = str(record.vod_remarks or "")
            candidates.append(
                SmartSearchCandidate(
                    source_kind="favorite",
                    source_label="我的收藏",
                    vod_id=str(record.vod_id),
                    title=str(
                        card.display_title
                        or record.latest_vod_name
                        or record.vod_name_snapshot
                    ),
                    poster=str(record.vod_pic or ""),
                    remarks=remarks,
                    rating=_rating_from_text(remarks),
                )
            )
        return candidates

    def _following_candidates(
        self,
        keyword: str,
        seen: set[tuple[str, str]],
    ) -> list[SmartSearchCandidate]:
        if self._following_controller is None or not hasattr(
            self._following_controller,
            "search_items",
        ):
            return []
        cards, _total = self._following_controller.search_items(keyword, 1)
        candidates = []
        for card in cards:
            record = getattr(card, "record", None)
            if record is None:
                continue
            key = ("following", str(record.id))
            if key in seen:
                continue
            seen.add(key)
            text = " ".join(
                [
                    str(getattr(card, "subtitle", "") or ""),
                    str(getattr(card, "update_text", "") or ""),
                ]
            )
            candidates.append(
                SmartSearchCandidate(
                    source_kind="following",
                    source_label="我的追更",
                    vod_id=str(record.id),
                    title=str(record.title),
                    poster=str(record.poster or ""),
                    remarks=text,
                    overview=str(record.overview or ""),
                    rating=_rating_from_text(text),
                )
            )
        return candidates

    def _history_candidates(
        self,
        keyword: str,
        seen: set[tuple[str, str]],
    ) -> list[SmartSearchCandidate]:
        if self._history_controller is None or not hasattr(
            self._history_controller,
            "load_page",
        ):
            return []
        records, _total = self._history_controller.load_page(
            page=1,
            size=self._page_size,
            keyword=keyword,
        )
        candidates = []
        for record in records:
            if not isinstance(record, HistoryRecord):
                continue
            key = ("history", record.key)
            if key in seen:
                continue
            seen.add(key)
            remarks = str(record.vod_remarks or "")
            candidates.append(
                SmartSearchCandidate(
                    source_kind="history",
                    source_label="播放记录",
                    vod_id=str(record.key),
                    title=str(record.vod_name),
                    poster=str(record.vod_pic or ""),
                    remarks=remarks,
                    rating=_rating_from_text(remarks),
                )
            )
        return candidates
