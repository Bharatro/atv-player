from __future__ import annotations

from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.providers.douban import clean_overview_text
from atv_player.models import PlaybackDetailField, VodItem

_FIELD_PROVIDER_PRIORITY = {
    "overview": ["local_douban", "remote_douban", "douban", "tmdb", "plugin"],
    "rating": ["local_douban", "remote_douban", "douban", "tmdb", "plugin"],
    "poster": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "year": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "actors": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "directors": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "genres": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "country": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "language": ["tmdb", "local_douban", "remote_douban", "douban", "plugin"],
    "douban_id": ["local_douban", "remote_douban", "douban", "plugin"],
}


def _provider_rank(field_name: str, provider: str) -> int:
    order = _FIELD_PROVIDER_PRIORITY.get(field_name, [])
    return order.index(provider) if provider in order else len(order) + 100


def _can_override(vod: VodItem, field_name: str, provider: str) -> bool:
    current = vod.metadata_field_sources.get(field_name, "")
    if not current:
        return True
    return _provider_rank(field_name, provider) <= _provider_rank(field_name, current)


def _set_field_source(vod: VodItem, field_name: str, provider: str) -> None:
    vod.metadata_field_sources[field_name] = provider


def _record_detail_fields(record: MetadataRecord) -> list[dict[str, str]]:
    ordered_labels: list[str] = []
    values: dict[str, str] = {}

    def put(label: str, value: str) -> None:
        normalized_label = str(label or "").strip()
        normalized_value = str(value or "").strip()
        if not normalized_label or not normalized_value:
            return
        if normalized_label not in values:
            ordered_labels.append(normalized_label)
        values[normalized_label] = normalized_value

    if record.aliases:
        put("别名", " / ".join(alias for alias in record.aliases if alias))
    if record.imdb_id:
        put("IMDb ID", record.imdb_id)
    if record.tmdb_id:
        put("TMDB ID", record.tmdb_id)
    for item in record.detail_fields:
        put(str(item.get("label") or ""), str(item.get("value") or ""))
    return [{"label": label, "value": values[label]} for label in ordered_labels]


def merge_metadata_record(vod: VodItem, record: MetadataRecord, provider_priority: list[str]) -> VodItem:
    del provider_priority
    if not vod.vod_name and record.title:
        vod.vod_name = record.title
    if record.poster and (not vod.vod_pic or _can_override(vod, "poster", record.provider)):
        vod.vod_pic = record.poster
        _set_field_source(vod, "poster", record.provider)
    if record.year and (not vod.vod_year or _can_override(vod, "year", record.provider)):
        vod.vod_year = record.year
        _set_field_source(vod, "year", record.provider)
    if record.genres and (not vod.type_name or _can_override(vod, "genres", record.provider)):
        vod.type_name = " / ".join(record.genres)
        _set_field_source(vod, "genres", record.provider)
    if record.country and (not vod.vod_area or _can_override(vod, "country", record.provider)):
        vod.vod_area = record.country
        _set_field_source(vod, "country", record.provider)
    if record.language and (not vod.vod_lang or _can_override(vod, "language", record.provider)):
        vod.vod_lang = record.language
        _set_field_source(vod, "language", record.provider)
    if record.directors and (not vod.vod_director or _can_override(vod, "directors", record.provider)):
        vod.vod_director = ",".join(record.directors)
        _set_field_source(vod, "directors", record.provider)
    if record.actors and (not vod.vod_actor or _can_override(vod, "actors", record.provider)):
        vod.vod_actor = ",".join(record.actors)
        _set_field_source(vod, "actors", record.provider)
    cleaned_overview = clean_overview_text(record.overview)
    if cleaned_overview and (not vod.vod_content or _can_override(vod, "overview", record.provider)):
        vod.vod_content = cleaned_overview
        _set_field_source(vod, "overview", record.provider)
    if record.rating and (not vod.vod_remarks or _can_override(vod, "rating", record.provider)):
        vod.vod_remarks = record.rating
        _set_field_source(vod, "rating", record.provider)
    if record.douban_id and (not vod.dbid or _can_override(vod, "douban_id", record.provider)):
        vod.dbid = record.douban_id
        _set_field_source(vod, "douban_id", record.provider)
    detail_fields = _record_detail_fields(record)
    if detail_fields:
        merged: list[PlaybackDetailField] = []
        seen_labels: set[str] = set()
        for field in vod.detail_fields:
            replacement = next((item for item in detail_fields if item.get("label") == field.label), None)
            if replacement is not None:
                merged.append(PlaybackDetailField(label=field.label, value=str(replacement.get("value") or "")))
                seen_labels.add(field.label)
                continue
            merged.append(field)
            seen_labels.add(field.label)
        for item in detail_fields:
            label = str(item.get("label") or "").strip()
            if label and label not in seen_labels:
                merged.append(PlaybackDetailField(label=label, value=str(item.get("value") or "")))
                seen_labels.add(label)
        vod.detail_fields = merged
        _set_field_source(vod, "detail_fields", record.provider)
    return vod


def replace_metadata_record(vod: VodItem, record: MetadataRecord) -> VodItem:
    cleaned_overview = clean_overview_text(record.overview)
    detail_fields = _record_detail_fields(record)

    if record.title:
        vod.vod_name = record.title
    vod.vod_pic = record.poster
    vod.vod_year = record.year
    vod.type_name = " / ".join(record.genres)
    vod.vod_area = record.country
    vod.vod_lang = record.language
    vod.vod_director = ",".join(record.directors)
    vod.vod_actor = ",".join(record.actors)
    vod.vod_content = cleaned_overview
    vod.vod_remarks = record.rating
    vod.dbid = record.douban_id
    vod.detail_fields = [
        PlaybackDetailField(label=str(item.get("label") or ""), value=str(item.get("value") or ""))
        for item in detail_fields
        if str(item.get("label") or "").strip() and str(item.get("value") or "").strip()
    ]

    for field_name in (
        "poster",
        "year",
        "genres",
        "country",
        "language",
        "directors",
        "actors",
        "overview",
        "rating",
        "douban_id",
        "detail_fields",
    ):
        _set_field_source(vod, field_name, record.provider)
    return vod
