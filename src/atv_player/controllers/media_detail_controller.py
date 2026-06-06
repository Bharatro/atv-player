from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingRecord,
    FollowingMetadataBundle,
    FollowingSeason,
    FollowingEpisode,
)
from atv_player.following_metadata import (
    build_following_metadata_bundle,
)
from atv_player.metadata.scrape import MetadataScrapeCandidate
from atv_player.metadata.models import MetadataQuery, MetadataRecord
from atv_player.models import VodItem


@dataclass(slots=True, frozen=True)
class MediaDetailIdentity:
    media_type: str
    tmdb_id: str
    title: str = ""


@dataclass(slots=True, frozen=True)
class MediaDetailLookup:
    title: str
    year: str = ""
    media_type: str = ""
    provider: str = ""
    provider_id: str = ""
    poster_url: str = ""


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
    url: str = ""
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
    metadata_bundle: FollowingMetadataBundle | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class MediaDetailController:
    def __init__(self, *, client, metadata_search_service=None) -> None:
        self._client = client
        self._metadata_search_service = metadata_search_service

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

    def placeholder_from_vod(self, vod: VodItem) -> MediaDetailView:
        identity = self.identity_from_vod(vod) or self._placeholder_identity(
            title=str(getattr(vod, "vod_name", "") or "").strip(),
            year=str(getattr(vod, "vod_year", "") or "").strip(),
            media_type=str(getattr(vod, "vod_tag", "") or "").strip(),
        )
        return self._placeholder_view(
            identity,
            title=str(getattr(vod, "vod_name", "") or identity.title).strip(),
            year=str(getattr(vod, "vod_year", "") or "").strip(),
            poster_url=str(getattr(vod, "vod_pic", "") or "").strip(),
        )

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

    def placeholder_from_heat(self, item: object) -> MediaDetailView:
        identity = self.identity_from_heat(item) or self._placeholder_identity(
            title=str(getattr(item, "title", "") or "").strip(),
            year=str(getattr(item, "year", "") or "").strip(),
            media_type=str(getattr(item, "media_type", "") or "").strip(),
        )
        return self._placeholder_view(
            identity,
            title=str(getattr(item, "title", "") or identity.title).strip(),
            year=str(getattr(item, "year", "") or "").strip(),
            poster_url=str(getattr(item, "poster", "") or getattr(item, "poster_url", "") or "").strip(),
        )

    def load_from_lookup(self, lookup: MediaDetailLookup) -> MediaDetailView:
        identity = self._search_identity(
            title=lookup.title,
            year=lookup.year,
            media_type=lookup.media_type,
        )
        if identity is None:
            raise ValueError("无法识别媒体详情")
        return self.load_from_identity(identity)

    def placeholder_from_lookup(self, lookup: MediaDetailLookup) -> MediaDetailView:
        identity = self._placeholder_identity(
            title=lookup.title,
            year=lookup.year,
            media_type=lookup.media_type,
        )
        return self._placeholder_view(
            identity,
            title=lookup.title or identity.title,
            year=lookup.year,
            poster_url=lookup.poster_url,
        )

    def load_from_identity(self, identity: MediaDetailIdentity) -> MediaDetailView:
        media_type = self._normalize_media_type(identity.media_type)
        tmdb_id = str(identity.tmdb_id or "").strip()
        if not tmdb_id:
            raise ValueError("缺少 TMDB ID")
        if media_type == "movie":
            raw = self._client.get_movie_detail(tmdb_id)
        else:
            raw = self._client.get_tv_detail_with_season(tmdb_id, season_number=1)
        return self._map_detail(
            raw,
            identity=MediaDetailIdentity(media_type=media_type, tmdb_id=tmdb_id, title=identity.title),
            season_number=1,
        )

    def placeholder_from_identity(self, identity: MediaDetailIdentity) -> MediaDetailView:
        return self._placeholder_view(identity, title=identity.title)

    def refresh(self, view: MediaDetailView) -> MediaDetailView:
        self._reset_metadata_cache_for_view(view)
        return self.load_from_identity(view.identity)

    def load_season(self, view: MediaDetailView, *, season_number: int) -> MediaDetailView:
        if view.media_type == "movie":
            return view
        normalized_season = max(1, self._int_value(season_number))
        identity = MediaDetailIdentity(
            media_type=self._normalize_media_type(view.identity.media_type),
            tmdb_id=str(view.identity.tmdb_id or "").strip(),
            title=view.identity.title or view.title,
        )
        raw = self._client.get_tv_detail_with_season(identity.tmdb_id, season_number=normalized_season)
        return self._map_detail(raw, identity=identity, season_number=normalized_season)

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

    def _placeholder_identity(self, *, title: str, year: str = "", media_type: str = "") -> MediaDetailIdentity:
        del year
        return MediaDetailIdentity(
            media_type=self._normalize_media_type(media_type),
            tmdb_id="",
            title=title,
        )

    def _placeholder_view(
        self,
        identity: MediaDetailIdentity,
        *,
        title: str = "",
        year: str = "",
        poster_url: str = "",
    ) -> MediaDetailView:
        view = MediaDetailView(
            identity=identity,
            title=title or identity.title or "媒体详情",
            media_type=self._normalize_media_type(identity.media_type),
            year=str(year or "").strip(),
            poster_url=poster_url,
            overview="正在加载元数据...",
        )
        view.metadata_bundle = self._metadata_bundle_for_view(view)
        return view

    def _map_detail(
        self,
        raw: dict[str, Any],
        *,
        identity: MediaDetailIdentity,
        season_number: int = 1,
    ) -> MediaDetailView:
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
            poster_url=self._image_url(raw.get("poster_url") or raw.get("poster_path"), kind="poster"),
            backdrop_url=self._image_url(raw.get("backdrop_url") or raw.get("backdrop_path"), kind="backdrop"),
            rating=self._rating_text(raw.get("vote_average")),
            genres=[
                str(genre.get("name") or "").strip()
                for genre in list(raw.get("genres") or [])
                if isinstance(genre, dict) and str(genre.get("name") or "").strip()
            ],
            seasons=[self._map_season(season) for season in list(raw.get("seasons") or []) if isinstance(season, dict)],
            raw=dict(raw),
        )
        view.episodes = self._map_episodes(raw, media_type=media_type, season_number=season_number)
        view.people = self._map_people(raw, media_type=media_type)
        view.related = self._map_related(media_type=media_type, tmdb_id=tmdb_id)
        view.metadata_bundle = self._metadata_bundle_for_view(view)
        if season_number == 1:
            view = self._enrich_metadata_bundle(view)
        return view

    def _map_episodes(
        self,
        raw: dict[str, Any],
        *,
        media_type: str,
        season_number: int = 1,
    ) -> list[MediaDetailEpisode]:
        if media_type == "movie":
            return []
        season_key = f"season/{max(1, self._int_value(season_number))}"
        season_payload = raw.get(season_key) if isinstance(raw.get(season_key), dict) else {}
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
        credits = self._credits_payload(raw, media_type=media_type)
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
                    url=self._person_url(person.get("id")),
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
                    url=self._person_url(person.get("id")),
                    kind="crew",
                )
            )
        return people

    def _credits_payload(self, raw: dict[str, Any], *, media_type: str) -> dict[str, Any]:
        keys = ["credits"] if media_type == "movie" else ["aggregate_credits", "credits"]
        for key in keys:
            payload = raw.get(key)
            if isinstance(payload, dict):
                return payload
        return {}

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

    @staticmethod
    def _person_url(value: object) -> str:
        person_id = str(value or "").strip()
        if not person_id:
            return ""
        return f"https://www.themoviedb.org/person/{person_id}"

    @staticmethod
    def _image_url(value: object, *, kind: str) -> str:
        path = str(value or "").strip()
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        size = "w780" if kind == "backdrop" else "w500"
        return f"https://image.tmdb.org/t/p/{size}{path}"

    def _map_season(self, season: dict[str, object]) -> dict[str, object]:
        mapped = dict(season)
        poster = self._image_url(mapped.get("poster_url") or mapped.get("poster_path"), kind="poster")
        if poster:
            mapped["poster_url"] = poster
        return mapped

    def _metadata_bundle_for_view(self, view: MediaDetailView) -> FollowingMetadataBundle:
        tmdb_record = self._metadata_record_from_view(view)
        _bundle, _record, snapshot = build_following_metadata_bundle(
            base_record=self._following_record_from_view(view),
            base_snapshot=self._following_snapshot_from_view(view),
            tmdb_detail_record=tmdb_record,
            provider_records={},
        )
        return snapshot.metadata_bundle or _bundle

    def _enrich_metadata_bundle(self, view: MediaDetailView) -> MediaDetailView:
        service = self._metadata_search_service
        if service is None or not view.identity.tmdb_id:
            return view
        try:
            tmdb_record = self._metadata_record_from_view(view)
            provider_records = self._load_provider_records(view, tmdb_record=tmdb_record)
            if not provider_records:
                return view
            _bundle, _record, snapshot = build_following_metadata_bundle(
                base_record=self._following_record_from_view(view),
                base_snapshot=self._following_snapshot_from_view(view),
                tmdb_detail_record=tmdb_record,
                provider_records=provider_records,
            )
            view.metadata_bundle = snapshot.metadata_bundle
            if snapshot.overview:
                view.overview = snapshot.overview
        except Exception:
            return view
        return view

    def _load_provider_records(
        self,
        view: MediaDetailView,
        *,
        tmdb_record: MetadataRecord,
    ) -> dict[str, tuple[MetadataRecord, float]]:
        service = self._metadata_search_service
        if service is None:
            return {}
        records: dict[str, tuple[MetadataRecord, float]] = {}
        groups_by_provider: dict[str, list[object]] = {}
        groups = service.search_following(
            MetadataQuery(
                title=view.title,
                year=view.year,
                source_kind="tmdb",
                vod_id=f"{self._normalize_media_type(view.media_type)}:{view.identity.tmdb_id}",
                category_name="电影" if view.media_type == "movie" else "剧集",
            )
        )
        for group in groups or []:
            provider = str(getattr(group, "provider", "") or "").strip()
            if not provider or provider == "tmdb":
                continue
            items = list(getattr(group, "items", []) or [])
            if not items:
                continue
            groups_by_provider.setdefault(provider, []).extend(items)
        douban_record = self._load_douban_provider_record(service, groups_by_provider)
        if douban_record is not None:
            records["douban"] = douban_record
        for provider, items in groups_by_provider.items():
            if provider in {"official_douban", "local_douban", "douban"}:
                continue
            provider_record = self._load_first_provider_record(
                service,
                items,
                base_record=tmdb_record,
            )
            if provider_record is not None:
                records[provider] = provider_record
        return records

    def _reset_metadata_cache_for_view(self, view: MediaDetailView) -> None:
        service = self._metadata_search_service
        reset = getattr(service, "reset", None)
        if not callable(reset):
            return
        media_type = self._normalize_media_type(view.media_type)
        query = MetadataQuery(
            title=view.title,
            year=view.year,
            source_kind="tmdb",
            vod_id=f"{media_type}:{view.identity.tmdb_id}",
            category_name="电影" if media_type == "movie" else "剧集",
        )
        detail_keys = self._metadata_detail_keys_from_view(view)
        try:
            reset(
                query,
                bound_provider="tmdb",
                bound_provider_id=self._tmdb_provider_id(
                    media_type=media_type,
                    tmdb_id=str(view.identity.tmdb_id or "").strip(),
                ),
                detail_keys=detail_keys,
            )
        except Exception:
            return

    def _metadata_detail_keys_from_view(self, view: MediaDetailView) -> list[tuple[str, str]]:
        bundle = view.metadata_bundle
        if bundle is None:
            return []
        keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for source_key, snapshot in dict(bundle.source_snapshots or {}).items():
            provider = str(getattr(snapshot, "provider", "") or source_key or "").strip()
            provider_id = str(getattr(snapshot, "provider_id", "") or "").strip()
            if not provider or not provider_id:
                continue
            key = (provider, provider_id)
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def _load_douban_provider_record(
        self,
        service,
        groups_by_provider: dict[str, list[object]],
    ) -> tuple[MetadataRecord, float] | None:
        for provider in ("official_douban", "local_douban", "douban"):
            result = self._load_first_provider_record(service, groups_by_provider.get(provider, []))
            if result is None:
                continue
            record, confidence = result
            return (
                self._canonical_douban_record(record),
                confidence,
            )
        return None

    def _load_first_provider_record(
        self,
        service,
        items: list[object],
        *,
        base_record: MetadataRecord | None = None,
    ) -> tuple[MetadataRecord, float] | None:
        for candidate in items:
            try:
                record = service.detail_record_full(candidate)
            except Exception:
                continue
            if not _metadata_record_media_kind_compatible(base_record, record):
                continue
            confidence = float(getattr(candidate, "confidence", 1.0) or 1.0)
            return record, confidence
        return None

    def _canonical_douban_record(self, record: MetadataRecord) -> MetadataRecord:
        record.provider = "douban"
        return record

    def _metadata_record_from_view(self, view: MediaDetailView) -> MetadataRecord:
        raw = dict(view.raw or {})
        media_type = self._normalize_media_type(view.media_type)
        tmdb_id = str(raw.get("id") or view.identity.tmdb_id or "").strip()
        credits = self._credits_payload(raw, media_type=media_type)
        cast = [item for item in list(credits.get("cast") or []) if isinstance(item, dict)]
        crew = [item for item in list(credits.get("crew") or []) if isinstance(item, dict)]
        cast_details = [self._person_detail(item, role_key="role") for item in cast]
        cast_details = [item for item in cast_details if item.get("name")]
        crew_details = [self._person_detail(item, role_key="job") for item in crew]
        crew_details = [item for item in crew_details if item.get("name")]
        aliases = self._aliases_from_raw(raw, media_type=media_type)
        external_ids = raw.get("external_ids") if isinstance(raw.get("external_ids"), dict) else {}
        detail_fields = [
            {"label": "genres", "value": list(view.genres)},
            {"label": "seasons", "value": list(view.seasons)},
            {
                "label": "episodes",
                "value": [
                    {
                        "season_number": episode.season_number,
                        "episode_number": episode.episode_number,
                        "name": episode.title,
                        "air_date": episode.air_date,
                        "overview": episode.overview,
                        "still_url": episode.still_url,
                    }
                    for episode in view.episodes
                ],
            },
        ]
        detail_fields.extend(self._tmdb_detail_fields_from_raw(raw, media_type=media_type))
        return MetadataRecord(
            title=view.title,
            original_title=view.original_title,
            year=view.year,
            poster=view.poster_url,
            backdrop=view.backdrop_url,
            backdrops=self._backdrops_from_raw(raw, fallback=view.backdrop_url),
            rating=view.rating,
            overview=view.overview,
            provider="tmdb",
            provider_id=self._tmdb_provider_id(media_type=media_type, tmdb_id=tmdb_id),
            actors=self._split_names([item.get("name") for item in cast_details]),
            directors=self._split_names(
                [
                    item.get("name")
                    for item in crew_details
                    if str(item.get("job") or "").strip() == "Director"
                ]
            ),
            cast_details=cast_details,
            crew_details=crew_details,
            genres=list(view.genres),
            country=self._country_text(raw),
            language=self._language_text(raw),
            aliases=aliases,
            imdb_id=str(external_ids.get("imdb_id") or "").strip(),
            tmdb_id=tmdb_id,
            detail_fields=detail_fields,
        )

    def _tmdb_provider_id(self, *, media_type: str, tmdb_id: str) -> str:
        if media_type == "tv" and tmdb_id:
            return f"tv:{tmdb_id}:season:1"
        return f"{media_type}:{tmdb_id}"

    def _person_detail(self, item: dict[str, object], *, role_key: str) -> dict[str, object]:
        name = str(item.get("name") or "").strip()
        detail: dict[str, object] = {"name": name}
        role = self._person_role(item) if role_key == "role" else self._person_job(item)
        if role:
            detail[role_key] = role
        avatar = self._profile_url(item.get("profile_path"))
        if avatar:
            detail["avatar"] = avatar
        person_id = str(item.get("id") or "").strip()
        if person_id:
            detail["url"] = f"https://www.themoviedb.org/person/{person_id}"
        return detail

    def _person_role(self, item: dict[str, object]) -> str:
        roles = item.get("roles")
        if isinstance(roles, list):
            for role in roles:
                if isinstance(role, dict) and str(role.get("character") or "").strip():
                    return str(role.get("character") or "").strip()
        return str(item.get("character") or "").strip()

    def _person_job(self, item: dict[str, object]) -> str:
        jobs = item.get("jobs")
        if isinstance(jobs, list):
            for job in jobs:
                if isinstance(job, dict) and str(job.get("job") or "").strip():
                    return str(job.get("job") or "").strip()
        return str(item.get("job") or "").strip()

    def _aliases_from_raw(self, raw: dict[str, Any], *, media_type: str) -> list[str]:
        alt_payload = raw.get("alternative_titles") if isinstance(raw.get("alternative_titles"), dict) else {}
        key = "titles" if media_type == "movie" else "results"
        return self._split_names(
            [
                item.get("title") or item.get("name")
                for item in list(alt_payload.get(key) or [])
                if isinstance(item, dict)
            ]
        )

    def _tmdb_detail_fields_from_raw(self, raw: dict[str, Any], *, media_type: str) -> list[dict[str, object]]:
        fields: list[dict[str, object]] = []
        if media_type == "tv":
            for label in ("number_of_episodes", "number_of_seasons", "last_air_date"):
                value = str(raw.get(label) or "").strip()
                if value:
                    fields.append({"label": label, "value": value})
            for label in ("last_episode_to_air", "next_episode_to_air"):
                value = raw.get(label)
                if isinstance(value, dict):
                    fields.append({"label": label, "value": value})
        watch_providers = raw.get("watch_providers") or raw.get("watch/providers")
        if isinstance(watch_providers, dict):
            entries = self._watch_provider_entries(watch_providers)
            if entries:
                fields.append({"label": "watch_providers", "value": entries})
                fields.append({"label": "watch_provider_sources", "value": entries})
        return fields

    def _watch_provider_entries(self, payload: dict[str, object]) -> list[dict[str, str]]:
        results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
        country = results.get("CN") if isinstance(results, dict) else None
        if not isinstance(country, dict):
            return []
        shared_link = str(country.get("link") or country.get("url") or "").strip()
        entries = []
        for bucket in ("flatrate", "free", "ads", "buy", "rent"):
            providers = country.get(bucket)
            if not isinstance(providers, list):
                continue
            for item in providers:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("provider_name") or "").strip()
                if not label:
                    continue
                entries.append(
                    {
                        "provider": label,
                        "label": label,
                        "url": str(item.get("url") or item.get("link") or shared_link).strip(),
                    }
                )
        return entries

    def _country_text(self, raw: dict[str, Any]) -> str:
        countries = [
            str(item.get("name") or item.get("iso_3166_1") or "").strip()
            for item in list(raw.get("production_countries") or [])
            if isinstance(item, dict)
        ]
        if not countries:
            countries = [str(item or "").strip() for item in list(raw.get("origin_country") or [])]
        return " / ".join(item for item in countries if item)

    def _language_text(self, raw: dict[str, Any]) -> str:
        languages = [
            str(item.get("name") or item.get("english_name") or item.get("iso_639_1") or "").strip()
            for item in list(raw.get("spoken_languages") or [])
            if isinstance(item, dict)
        ]
        if not languages:
            languages = [str(raw.get("original_language") or "").strip()]
        return " / ".join(item for item in languages if item)

    def _backdrops_from_raw(self, raw: dict[str, Any], *, fallback: str = "") -> list[str]:
        images = raw.get("images") if isinstance(raw.get("images"), dict) else {}
        values = [
            self._image_url(item.get("file_path"), kind="backdrop")
            for item in list(images.get("backdrops") or [])
            if isinstance(item, dict)
        ]
        return self._split_names([fallback, *values])

    @staticmethod
    def _split_names(values: list[object] | None) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for value in values or []:
            name = str(value or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    def _following_record_from_view(self, view: MediaDetailView) -> FollowingRecord:
        return FollowingRecord(
            id=0,
            title=view.title,
            original_title=view.original_title,
            media_kind="movie" if view.media_type == "movie" else "live_action",
            season_number=1 if view.media_type == "tv" else 0,
            poster=view.poster_url,
            backdrop=view.backdrop_url,
            rating=view.rating,
            provider="tmdb",
            provider_id=f"{view.media_type}:{view.identity.tmdb_id}",
            external_ids={"tmdb": str(view.identity.tmdb_id)} if view.identity.tmdb_id else {},
        )

    def _following_snapshot_from_view(self, view: MediaDetailView) -> FollowingDetailSnapshot:
        return FollowingDetailSnapshot(
            overview=view.overview,
            metadata_fields=list(view.metadata_bundle.merged_snapshot.metadata_fields if view.metadata_bundle else []),
            seasons=[
                FollowingSeason(
                    season_number=self._int_value(season.get("season_number")),
                    title=str(season.get("name") or season.get("title") or "").strip(),
                    overview=str(season.get("overview") or "").strip(),
                    air_date=str(season.get("air_date") or "").strip(),
                    poster=str(season.get("poster_url") or season.get("poster_path") or "").strip(),
                    episode_count=self._int_value(season.get("episode_count")),
                    is_special=self._int_value(season.get("season_number")) <= 0,
                )
                for season in view.seasons
                if isinstance(season, dict)
            ],
            episodes=[
                FollowingEpisode(
                    season_number=episode.season_number,
                    episode_number=episode.episode_number,
                    title=episode.title,
                    overview=episode.overview,
                    air_date=episode.air_date,
                    still=episode.still_url,
                )
                for episode in view.episodes
            ],
            posters=[view.poster_url] if view.poster_url else [],
            backdrops=[view.backdrop_url] if view.backdrop_url else [],
        )


_ANIME_MEDIA_MARKERS = ("动漫", "动画", "番剧", "anime", "acg", "国创", "声优")
_LIVE_ACTION_MEDIA_MARKERS = ("电视剧", "剧集", "连续剧", "真人", "短剧")
_MOVIE_MEDIA_MARKERS = ("电影", "影片", "movie")


def _metadata_record_media_kind_compatible(
    base_record: MetadataRecord | None,
    candidate_record: MetadataRecord,
) -> bool:
    base_kind = _metadata_record_media_kind(base_record)
    candidate_kind = _metadata_record_media_kind(candidate_record)
    if not base_kind or not candidate_kind:
        return True
    return base_kind == candidate_kind


def _metadata_record_media_kind(record: MetadataRecord | None) -> str:
    if record is None:
        return ""
    provider = str(getattr(record, "provider", "") or "").strip()
    provider_id = str(getattr(record, "provider_id", "") or "").strip()
    if provider == "bangumi":
        return "anime"
    if provider == "tmdb":
        if provider_id.startswith("movie:"):
            return "movie"
        if provider_id.startswith("tv:"):
            if _metadata_values_contain_any(getattr(record, "genres", []), _ANIME_MEDIA_MARKERS):
                return "anime"
            return "live_action"
    return _classify_metadata_media_kind(
        getattr(record, "genres", []),
        getattr(record, "detail_fields", []),
        getattr(record, "title", ""),
        getattr(record, "original_title", ""),
    )


def _classify_metadata_media_kind(*values: object) -> str:
    tokens = " ".join(
        str(token or "").strip().lower()
        for value in values
        for token in _iter_metadata_kind_tokens(value)
        if str(token or "").strip()
    )
    if not tokens:
        return ""
    if any(marker in tokens for marker in _ANIME_MEDIA_MARKERS):
        return "anime"
    if any(marker in tokens for marker in _MOVIE_MEDIA_MARKERS):
        return "movie"
    if any(marker in tokens for marker in _LIVE_ACTION_MEDIA_MARKERS):
        return "live_action"
    return ""


def _metadata_values_contain_any(value: object, markers: tuple[str, ...]) -> bool:
    text = " ".join(str(item or "").strip().lower() for item in _iter_metadata_kind_tokens(value))
    return any(marker in text for marker in markers)


def _iter_metadata_kind_tokens(value: object) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for key in ("label", "value"):
            values.extend(_iter_metadata_kind_tokens(value.get(key)))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_iter_metadata_kind_tokens(item))
        return values
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,/|、，·\s]+", text) if part.strip()]
