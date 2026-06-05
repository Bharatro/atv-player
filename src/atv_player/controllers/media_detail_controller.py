from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from atv_player.metadata.scrape import MetadataScrapeCandidate
from atv_player.models import VodItem


@dataclass(slots=True, frozen=True)
class MediaDetailIdentity:
    media_type: str
    tmdb_id: str
    title: str = ""


@dataclass(slots=True)
class MediaDetailEpisode:
    season_number: int
    episode_number: int
    title: str
    air_date: str = ""
    overview: str = ""
    still_url: str = ""

    @property
    def display_title(self) -> str:
        prefix = f"S{self.season_number}E{self.episode_number}" if self.season_number > 0 else f"E{self.episode_number}"
        return f"{prefix} {self.title}".strip()


@dataclass(slots=True)
class MediaDetailPerson:
    name: str
    role: str = ""
    profile_url: str = ""
    kind: str = "cast"


@dataclass(slots=True)
class MediaDetailRecommendation:
    identity: MediaDetailIdentity
    poster_url: str = ""
    year: str = ""
    rating: str = ""


@dataclass(slots=True)
class MediaDetailView:
    identity: MediaDetailIdentity
    title: str
    original_title: str = ""
    media_type: str = "tv"
    year: str = ""
    release_date: str = ""
    overview: str = ""
    poster_url: str = ""
    backdrop_url: str = ""
    rating: str = ""
    genres: list[str] = field(default_factory=list)
    seasons: list[dict[str, object]] = field(default_factory=list)
    episodes: list[MediaDetailEpisode] = field(default_factory=list)
    people: list[MediaDetailPerson] = field(default_factory=list)
    related: list[MediaDetailRecommendation] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class MediaDetailController:
    def __init__(self, *, client) -> None:
        self._client = client

    def load_from_vod(self, vod: VodItem) -> MediaDetailView:
        identity = self.identity_from_vod(vod)
        if identity is None:
            identity = self._search_identity(
                title=str(getattr(vod, "vod_name", "") or "").strip(),
                year=str(getattr(vod, "vod_year", "") or "").strip(),
                media_type=str(getattr(vod, "vod_tag", "") or "").strip(),
            )
        if identity is None:
            raise ValueError("无法识别媒体详情")
        return self.load_from_identity(identity)

    def load_from_heat(self, item: object) -> MediaDetailView:
        identity = self.identity_from_heat(item)
        if identity is None:
            identity = self._search_identity(
                title=str(getattr(item, "title", "") or "").strip(),
                year=str(getattr(item, "year", "") or "").strip(),
                media_type=str(getattr(item, "media_type", "") or "").strip(),
            )
        if identity is None:
            raise ValueError("无法识别媒体详情")
        return self.load_from_identity(identity)

    def load_from_identity(self, identity: MediaDetailIdentity) -> MediaDetailView:
        media_type = self._normalize_media_type(identity.media_type)
        tmdb_id = str(identity.tmdb_id or "").strip()
        if not tmdb_id:
            raise ValueError("缺少 TMDB ID")
        if media_type == "movie":
            raw = self._client.get_movie_detail(tmdb_id)
        else:
            raw = self._client.get_tv_detail_with_season(tmdb_id, season_number=1)
        return self._map_detail(raw, identity=MediaDetailIdentity(media_type=media_type, tmdb_id=tmdb_id, title=identity.title))

    def refresh(self, view: MediaDetailView) -> MediaDetailView:
        return self.load_from_identity(view.identity)

    def candidate_for_following(self, view: MediaDetailView) -> MetadataScrapeCandidate:
        provider_id = f"{view.media_type}:{view.identity.tmdb_id}"
        raw = {
            "tmdb_id": view.identity.tmdb_id,
            "poster_url": view.poster_url,
            "backdrop_url": view.backdrop_url,
            "rating": view.rating,
            "overview": view.overview,
            "genres": list(view.genres),
        }
        if view.media_type == "tv":
            raw["season_number"] = 1
            provider_id = f"{provider_id}:season:1"
        return MetadataScrapeCandidate(
            provider="tmdb",
            provider_label="TMDB",
            provider_id=provider_id,
            title=view.title,
            year=view.year,
            subtitle="电影" if view.media_type == "movie" else "剧集",
            raw={key: value for key, value in raw.items() if value not in ("", None, [])},
        )

    def search_title(self, view: MediaDetailView) -> str:
        return view.title

    def identity_from_vod(self, vod: VodItem) -> MediaDetailIdentity | None:
        vod_id = str(getattr(vod, "vod_id", "") or "").strip()
        match = re.match(r"^tmdb:(movie|tv):(\d+)$", vod_id)
        if match is None:
            return None
        return MediaDetailIdentity(
            media_type=match.group(1),
            tmdb_id=match.group(2),
            title=str(getattr(vod, "vod_name", "") or "").strip(),
        )

    def identity_from_heat(self, item: object) -> MediaDetailIdentity | None:
        title = str(getattr(item, "title", "") or "").strip()
        media_type = self._normalize_media_type(str(getattr(item, "media_type", "") or "").strip())
        external_ids = getattr(item, "external_ids", {}) or {}
        if isinstance(external_ids, dict):
            tmdb_value = str(external_ids.get("tmdb") or "").strip()
            identity = self._identity_from_tmdb_text(tmdb_value, title=title, media_type=media_type)
            if identity is not None:
                return identity
        media_key = str(getattr(item, "media_key", "") or "").strip()
        return self._identity_from_tmdb_text(media_key, title=title, media_type=media_type)

    def _identity_from_tmdb_text(
        self,
        value: str,
        *,
        title: str,
        media_type: str,
    ) -> MediaDetailIdentity | None:
        text = str(value or "").strip()
        if not text:
            return None
        match = re.match(r"^tmdb:(movie|tv):(\d+)$", text)
        if match is not None:
            return MediaDetailIdentity(media_type=match.group(1), tmdb_id=match.group(2), title=title)
        match = re.match(r"^(movie|tv):(\d+)(?::season:\d+)?$", text)
        if match is not None:
            return MediaDetailIdentity(media_type=match.group(1), tmdb_id=match.group(2), title=title)
        match = re.match(r"^tmdb:(\d+)$", text)
        if match is not None:
            return MediaDetailIdentity(media_type=media_type or "tv", tmdb_id=match.group(1), title=title)
        if text.isdigit():
            return MediaDetailIdentity(media_type=media_type or "tv", tmdb_id=text, title=title)
        return None

    def _search_identity(self, *, title: str, year: str = "", media_type: str = "") -> MediaDetailIdentity | None:
        if not title:
            return None
        normalized_type = self._normalize_media_type(media_type)
        searches = [normalized_type] if normalized_type in {"movie", "tv"} else ["tv", "movie"]
        for current_type in searches:
            method = self._client.search_movie if current_type == "movie" else self._client.search_tv
            for result in method(title, year=year):
                tmdb_id = str(result.get("id") or "").strip()
                if tmdb_id:
                    result_title = str(result.get("title") or result.get("name") or title).strip()
                    return MediaDetailIdentity(media_type=current_type, tmdb_id=tmdb_id, title=result_title)
        return None

    def _map_detail(self, raw: dict[str, Any], *, identity: MediaDetailIdentity) -> MediaDetailView:
        media_type = self._normalize_media_type(identity.media_type)
        title = str(raw.get("title") or raw.get("name") or identity.title).strip()
        release_date = str(raw.get("release_date") or raw.get("first_air_date") or "").strip()
        tmdb_id = str(raw.get("id") or identity.tmdb_id).strip()
        view = MediaDetailView(
            identity=MediaDetailIdentity(media_type=media_type, tmdb_id=tmdb_id, title=title),
            title=title,
            original_title=str(raw.get("original_title") or raw.get("original_name") or "").strip(),
            media_type=media_type,
            year=release_date[:4],
            release_date=release_date,
            overview=str(raw.get("overview") or "").strip(),
            poster_url=str(raw.get("poster_url") or "").strip(),
            backdrop_url=str(raw.get("backdrop_url") or "").strip(),
            rating=self._rating_text(raw.get("vote_average")),
            genres=[
                str(genre.get("name") or "").strip()
                for genre in list(raw.get("genres") or [])
                if isinstance(genre, dict) and str(genre.get("name") or "").strip()
            ],
            seasons=[dict(season) for season in list(raw.get("seasons") or []) if isinstance(season, dict)],
            raw=dict(raw),
        )
        view.episodes = self._map_episodes(raw, media_type=media_type)
        view.people = self._map_people(raw, media_type=media_type)
        view.related = self._map_related(media_type=media_type, tmdb_id=tmdb_id)
        return view

    def _map_episodes(self, raw: dict[str, Any], *, media_type: str) -> list[MediaDetailEpisode]:
        if media_type == "movie":
            return []
        season_payload = raw.get("season/1") if isinstance(raw.get("season/1"), dict) else {}
        episodes = []
        for episode in list(season_payload.get("episodes") or []):
            if not isinstance(episode, dict):
                continue
            number = self._int_value(episode.get("episode_number"))
            if number <= 0:
                continue
            episodes.append(
                MediaDetailEpisode(
                    season_number=self._int_value(episode.get("season_number")) or 1,
                    episode_number=number,
                    title=str(episode.get("name") or "").strip(),
                    air_date=str(episode.get("air_date") or "").strip(),
                    overview=str(episode.get("overview") or "").strip(),
                    still_url=str(episode.get("still_url") or "").strip(),
                )
            )
        return episodes

    def _map_people(self, raw: dict[str, Any], *, media_type: str) -> list[MediaDetailPerson]:
        credits_key = "credits" if media_type == "movie" else "aggregate_credits"
        credits = raw.get(credits_key) if isinstance(raw.get(credits_key), dict) else {}
        people: list[MediaDetailPerson] = []
        for person in list(credits.get("cast") or [])[:12]:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not name:
                continue
            role = str(person.get("character") or "").strip()
            roles = person.get("roles")
            if not role and isinstance(roles, list) and roles and isinstance(roles[0], dict):
                role = str(roles[0].get("character") or "").strip()
            people.append(
                MediaDetailPerson(
                    name=name,
                    role=role,
                    profile_url=self._profile_url(person.get("profile_path")),
                    kind="cast",
                )
            )
        for person in list(credits.get("crew") or [])[:8]:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not name:
                continue
            role = str(person.get("job") or "").strip()
            jobs = person.get("jobs")
            if not role and isinstance(jobs, list) and jobs and isinstance(jobs[0], dict):
                role = str(jobs[0].get("job") or "").strip()
            people.append(
                MediaDetailPerson(
                    name=name,
                    role=role,
                    profile_url=self._profile_url(person.get("profile_path")),
                    kind="crew",
                )
            )
        return people

    def _map_related(self, *, media_type: str, tmdb_id: str) -> list[MediaDetailRecommendation]:
        related: list[MediaDetailRecommendation] = []
        for raw in self._client.get_recommendations(media_type=media_type, tmdb_id=tmdb_id, page=1):
            if not isinstance(raw, dict):
                continue
            related_id = str(raw.get("id") or "").strip()
            title = str(raw.get("title") or raw.get("name") or "").strip()
            if not related_id or not title:
                continue
            date = str(raw.get("release_date") or raw.get("first_air_date") or "").strip()
            poster_path = str(raw.get("poster_path") or "").strip()
            related.append(
                MediaDetailRecommendation(
                    identity=MediaDetailIdentity(media_type=media_type, tmdb_id=related_id, title=title),
                    poster_url=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
                    year=date[:4],
                    rating=self._rating_text(raw.get("vote_average")),
                )
            )
        return related

    @staticmethod
    def _normalize_media_type(value: str) -> str:
        text = str(value or "").strip().lower()
        return "movie" if text in {"movie", "film"} else "tv"

    @staticmethod
    def _int_value(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _rating_text(value: object) -> str:
        if isinstance(value, (int, float)) and value:
            return f"{float(value):.1f}"
        text = str(value or "").strip()
        return text

    @staticmethod
    def _profile_url(value: object) -> str:
        path = str(value or "").strip()
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"https://image.tmdb.org/t/p/w185{path}"
