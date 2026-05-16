from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from atv_player.models import PlayItem, VodItem


@dataclass(slots=True)
class MetadataQuery:
    title: str
    year: str = ""
    source_kind: str = ""
    source_key: str = ""
    vod_id: str = ""
    vod_dbid: int = 0
    type_name: str = ""
    category_name: str = ""


@dataclass(slots=True)
class MetadataContext:
    vod: "VodItem"
    source_kind: str
    source_key: str = ""
    current_item: "PlayItem | None" = None
    raw_detail: "Mapping[str, object] | None" = None

    def to_query(self) -> MetadataQuery:
        return MetadataQuery(
            title=(self.vod.vod_name or "").strip(),
            year=(self.vod.vod_year or "").strip(),
            source_kind=self.source_kind,
            source_key=self.source_key,
            vod_id=(self.vod.vod_id or "").strip(),
            vod_dbid=int(self.vod.dbid or 0),
            type_name=(self.vod.type_name or "").strip(),
            category_name=(self.vod.category_name or "").strip(),
        )


@dataclass(slots=True)
class MetadataMatch:
    provider: str
    provider_id: str
    title: str
    year: str = ""
    score: float = 0.0
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MetadataRecord:
    provider: str
    provider_id: str
    title: str = ""
    original_title: str = ""
    year: str = ""
    poster: str = ""
    backdrop: str = ""
    overview: str = ""
    rating: str = ""
    actors: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    country: str = ""
    language: str = ""
    aliases: list[str] = field(default_factory=list)
    season: str = ""
    episode: str = ""
    imdb_id: str = ""
    tmdb_id: str = ""
    douban_id: int = 0
    detail_fields: list[dict[str, object]] = field(default_factory=list)
