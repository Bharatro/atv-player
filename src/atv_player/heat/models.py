from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class HeatClientContext:
    app: str = "atv-player"
    version: str = ""
    platform: str = ""

    def to_payload(self) -> dict[str, object]:
        return {"app": self.app, "version": self.version, "platform": self.platform}


@dataclass(slots=True, frozen=True)
class HeatMediaIdentity:
    media_key: str
    title: str
    original_title: str = ""
    poster: str = ""
    year: str = ""
    media_type: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"media_key": self.media_key, "title": self.title}
        for key, value in (
            ("original_title", self.original_title),
            ("poster", self.poster),
            ("year", self.year),
            ("media_type", self.media_type),
        ):
            if value:
                payload[key] = value
        external_ids = {key: value for key, value in self.external_ids.items() if value}
        if external_ids:
            payload["external_ids"] = external_ids
        return payload


@dataclass(slots=True, frozen=True)
class HeatEvent:
    event_id: str
    installation_id: str
    event_type: str
    occurred_at: int
    client: HeatClientContext
    media: HeatMediaIdentity | None = None
    context: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class HeatRecommendation:
    media_key: str
    title: str
    original_title: str = ""
    poster: str = ""
    year: str = ""
    media_type: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)
    heat_score: float = 0.0
    rank: int = 0
    watching_now: int = 0
    recent_watchers: int = 0
    recent_searches: int = 0
    recent_favorites: int = 0
    reason: str = ""


@dataclass(slots=True, frozen=True)
class HeatMediaSummary:
    media_key: str
    display_text: str = ""
    watching_now: int = 0
    recent_watchers: int = 0
    recent_searches: int = 0
    recent_favorites: int = 0
    recent_following_adds: int = 0
    heat_score: float = 0.0

    def best_display_text(self) -> str:
        if self.display_text:
            return self.display_text
        if self.watching_now > 0:
            return f"{self.watching_now} 人正在播放"
        if self.recent_watchers > 0:
            return f"{self.recent_watchers} 人近期观看"
        return ""
