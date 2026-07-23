from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key

from atv_player.models import PlayItem

ORIGINAL = "index"
NAME_ASC = "name,asc"
NAME_DESC = "name,desc"
SIZE_ASC = "size,asc"
SIZE_DESC = "size,desc"
RATING_ASC = "rating,asc"
RATING_DESC = "rating,desc"
TIME_ASC = "time,asc"
TIME_DESC = "time,desc"


@dataclass(frozen=True, slots=True)
class PlaylistSortOption:
    value: str
    label: str


_OPTIONS = (
    PlaylistSortOption(ORIGINAL, "原始顺序"),
    PlaylistSortOption(NAME_ASC, "名称升序"),
    PlaylistSortOption(NAME_DESC, "名称降序"),
    PlaylistSortOption(SIZE_ASC, "大小升序"),
    PlaylistSortOption(SIZE_DESC, "大小降序"),
    PlaylistSortOption(RATING_ASC, "评分升序"),
    PlaylistSortOption(RATING_DESC, "评分降序"),
    PlaylistSortOption(TIME_ASC, "时间升序"),
    PlaylistSortOption(TIME_DESC, "时间降序"),
)


def parse_size_bytes(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value)) if math.isfinite(float(value)) else 0
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)\b",
        str(value or ""),
        re.IGNORECASE,
    )
    if match is None:
        return 0
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return max(0, int(float(match.group(1)) * units[match.group(2).upper()]))


def _natural_key(value: str):
    cleaned = str(value or "").strip().casefold()
    if not cleaned:
        return None
    return tuple(
        (0, int(token)) if token.isdigit() else (1, token)
        for token in re.split(r"(\d+)", cleaned)
        if token
    )


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _time_value(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = 0.0
    if math.isfinite(number) and number > 0:
        return number / 1000 if number >= 1_000_000_000_000 else number
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _sort_value(item: PlayItem, field: str):
    if field == "name":
        return _natural_key(item.original_title)
    if field == "size":
        return _positive_number(item.size)
    if field == "rating":
        return _positive_number(item.rating)
    if field == "time":
        return _time_value(item.time)
    return None


def _mode_field(mode: str) -> str:
    return mode.split(",", 1)[0] if "," in mode else ""


def find_playlist_item_index(
    playlist: list[PlayItem],
    current: PlayItem | None,
    fallback: int,
) -> int:
    if not playlist:
        return 0
    safe_fallback = max(0, min(fallback, len(playlist) - 1))
    if current is None:
        return safe_fallback
    for index, candidate in enumerate(playlist):
        if candidate is current:
            return index
    for field in ("vod_id", "url", "path"):
        value = str(getattr(current, field, "") or "").strip()
        if not value:
            continue
        for index, candidate in enumerate(playlist):
            if str(getattr(candidate, field, "") or "").strip() == value:
                return index
    return safe_fallback


class PlaylistSortState:
    def __init__(self) -> None:
        self.mode = ORIGINAL
        self._original_orders: dict[
            int,
            tuple[list[PlayItem], tuple[PlayItem, ...]],
        ] = {}

    def reset(self, playlists: list[list[PlayItem]] | None = None) -> None:
        self.mode = ORIGINAL
        self._original_orders.clear()
        for playlist in playlists or []:
            self.remember(playlist)

    def remember(self, playlist: list[PlayItem]) -> None:
        self._original_orders.setdefault(id(playlist), (playlist, tuple(playlist)))

    def inherit_original_order(
        self,
        previous: list[PlayItem],
        updated: list[PlayItem],
    ) -> None:
        self.remember(previous)
        previous_order = self._original_orders[id(previous)][1]
        updated_by_id = {id(item): item for item in updated}
        inherited = [
            updated_by_id[id(item)]
            for item in previous_order
            if id(item) in updated_by_id
        ]
        inherited_ids = {id(item) for item in inherited}
        inherited.extend(item for item in updated if id(item) not in inherited_ids)
        self._original_orders[id(updated)] = (updated, tuple(inherited))

    def options_for(
        self,
        playlist: list[PlayItem],
    ) -> tuple[PlaylistSortOption, ...]:
        fields = {
            field
            for field in ("name", "size", "rating", "time")
            if any(_sort_value(item, field) is not None for item in playlist)
        }
        return tuple(
            option
            for option in _OPTIONS
            if option.value == ORIGINAL or _mode_field(option.value) in fields
        )

    def apply(self, playlist: list[PlayItem], mode: str | None = None) -> str:
        self.remember(playlist)
        requested = self.mode if mode is None else mode
        supported = {option.value for option in self.options_for(playlist)}
        self.mode = requested if requested in supported else ORIGINAL
        original = self._original_orders[id(playlist)][1]
        current_by_id = {id(item): item for item in playlist}
        ordered = [
            current_by_id[id(item)]
            for item in original
            if id(item) in current_by_id
        ]
        ordered_ids = {id(item) for item in ordered}
        ordered.extend(item for item in playlist if id(item) not in ordered_ids)
        playlist[:] = ordered
        if self.mode == ORIGINAL:
            return self.mode

        field, direction = self.mode.split(",", 1)
        descending = direction == "desc"
        original_rank = {id(item): index for index, item in enumerate(playlist)}

        def compare(left: PlayItem, right: PlayItem) -> int:
            left_value = _sort_value(left, field)
            right_value = _sort_value(right, field)
            if left_value is None or right_value is None:
                if left_value is None and right_value is None:
                    return original_rank[id(left)] - original_rank[id(right)]
                return 1 if left_value is None else -1
            if left_value != right_value:
                result = -1 if left_value < right_value else 1
                return -result if descending else result
            return original_rank[id(left)] - original_rank[id(right)]

        playlist.sort(key=cmp_to_key(compare))
        return self.mode
