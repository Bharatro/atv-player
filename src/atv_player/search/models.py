from __future__ import annotations

from dataclasses import dataclass, field

from atv_player.models import VodItem


@dataclass(slots=True)
class SmartSearchCandidate:
    source_kind: str
    source_label: str
    vod_id: str
    title: str
    subtitle: str = ""
    poster: str = ""
    remarks: str = ""
    overview: str = ""
    year: str = ""
    area: str = ""
    language: str = ""
    actors: str = ""
    genres: list[str] = field(default_factory=list)
    rating: float = 0.0
    vod_item: VodItem | None = None


@dataclass(slots=True)
class RankedSmartSearchCandidate:
    candidate: SmartSearchCandidate
    score: float
    reasons: list[str] = field(default_factory=list)
