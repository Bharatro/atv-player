from __future__ import annotations

import html
import re
import unicodedata

from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.matching import normalize_match_title
from atv_player.metadata.providers.douban import clean_overview_text
from atv_player.models import PlaybackDetailField, PlaybackDetailFieldAction, PlaybackDetailValuePart, VodItem

_FIELD_PROVIDER_PRIORITY = {
    "overview": ["iqiyi", "official_douban", "bangumi", "local_douban", "douban", "tmdb", "plugin"],
    "rating": ["official_douban", "bangumi", "local_douban", "douban", "tmdb", "plugin", "iqiyi"],
    "poster": ["tmdb", "bangumi", "official_douban", "local_douban", "douban", "plugin", "iqiyi"],
    "year": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "actors": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "directors": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "genres": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "country": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "language": ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"],
    "douban_id": ["official_douban", "local_douban", "douban", "plugin", "iqiyi"],
}

_OVERVIEW_PROVIDER_PRIORITY = {
    "iqiyi": 0,
    "official_douban": 1,
    "bangumi": 2,
    "tmdb_season": 3,
    "douban": 4,
    "tmdb": 5,
    "local_douban": 6,
    "remote_douban": 6,
    "plugin": 7,
}

_TITLE_CORRECTION_PROVIDERS = {"local_douban", "remote_douban"}
_TITLE_NOISE_PATTERN = re.compile(
    r"(?:\bS\d+E\d+\b|第\s*\d+\s*[集话]|\b(?:WEB[-_. ]?\d+|2160p|1080p|4K|HDR|简繁字幕|外挂|内嵌|高码率)\b|@\w+@)",
    re.IGNORECASE,
)
_FOREIGN_SCRIPT_PATTERN = re.compile(r"[\u3040-\u30ff\u0400-\u04ff\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")


def _provider_rank(field_name: str, provider: str) -> int:
    order = _FIELD_PROVIDER_PRIORITY.get(field_name, [])
    return order.index(provider) if provider in order else len(order) + 100


def _overview_source_key(provider: str, provider_id: object = "") -> str:
    if provider == "tmdb" and ":season:" in str(provider_id or "").strip():
        return "tmdb_season"
    return provider


def _overview_rank(provider: str, provider_id: object = "") -> int:
    return _OVERVIEW_PROVIDER_PRIORITY.get(
        _overview_source_key(provider, provider_id),
        len(_OVERVIEW_PROVIDER_PRIORITY) + 100,
    )


def _can_override(vod: VodItem, field_name: str, provider: str) -> bool:
    current = vod.metadata_field_sources.get(field_name, "")
    if not current:
        return True
    return _provider_rank(field_name, provider) <= _provider_rank(field_name, current)


def _can_override_overview(vod: VodItem, record: MetadataRecord) -> bool:
    current = vod.metadata_field_sources.get("overview", "")
    if not current:
        return True
    return _overview_rank(record.provider, record.provider_id) <= _overview_rank(current)


def _set_field_source(vod: VodItem, field_name: str, provider: str) -> None:
    vod.metadata_field_sources[field_name] = provider


def _tmdb_media_type(record: MetadataRecord) -> str:
    if record.provider != "tmdb":
        return ""
    media_type = str(record.provider_id or "").strip().split(":", 1)[0]
    return media_type if media_type in {"movie", "tv"} else ""


def _normalize_title_for_correction(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^(?:[\[(（【][^)\]）】]{1,12}[\])）】]\s*)+", "", text)
    text = re.sub(r"[丨｜|]", "", text)
    return normalize_match_title(text)


def _title_quality_score(value: object) -> tuple[int, int]:
    text = str(value or "").strip()
    if not text:
        return (-100, 0)
    score = 0
    if _TITLE_NOISE_PATTERN.search(text):
        score -= 2
    if re.search(r"[丨｜|]", text):
        score -= 2
    if re.search(r"[【】\[\]{}<>]", text):
        score -= 1
    if re.search(r"[@_~`]", text):
        score -= 1
    if any(unicodedata.category(char).startswith("S") for char in text):
        score -= 2
    if _FOREIGN_SCRIPT_PATTERN.search(text):
        score -= 1
    return (score, -len(text))


def _is_low_quality_title(value: object) -> bool:
    return _title_quality_score(value)[0] < -1


def choose_preferred_title(current_title: object, candidate_title: object) -> str:
    current_text = str(current_title or "").strip()
    candidate_text = str(candidate_title or "").strip()
    if not current_text:
        return candidate_text
    if not candidate_text:
        return current_text
    current_score = _title_quality_score(current_text)
    candidate_score = _title_quality_score(candidate_text)
    if current_score[0] < -1 and candidate_score > current_score:
        return candidate_text
    current = _normalize_title_for_correction(current_text)
    target = _normalize_title_for_correction(candidate_text)
    if not current:
        return candidate_text
    if not target:
        return current_text
    if current != target and current not in target and target not in current:
        return current_text
    return candidate_text if candidate_score > current_score else current_text


def _build_detail_field(record: MetadataRecord, item: dict[str, object]) -> PlaybackDetailField | None:
    label = _clean_detail_text(item.get("label"))
    value = _clean_detail_text(item.get("value"))
    if not label or not value:
        return None
    if record.provider == "tmdb" and label == "TMDB ID":
        media_type = _tmdb_media_type(record)
        if media_type:
            return PlaybackDetailField(
                label=label,
                value_parts=[
                    PlaybackDetailValuePart(
                        label=value,
                        action=PlaybackDetailFieldAction(type="link", value=value, target=media_type),
                    )
                ],
            )
    return PlaybackDetailField(label=label, value=value)


def _record_detail_fields(record: MetadataRecord) -> list[dict[str, str]]:
    ordered_labels: list[str] = []
    values: dict[str, str] = {}

    def put(label: str, value: str) -> None:
        normalized_label = _clean_detail_text(label)
        normalized_value = _clean_detail_text(value)
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


def _clean_detail_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_poster_source(value: object) -> str:
    return str(value or "").strip()


def _sync_poster_candidates(vod: VodItem, *, primary: str, candidate: str = "") -> None:
    ordered: list[str] = []
    seen: set[str] = set()
    for source in (primary, *vod.poster_candidates, vod.vod_pic, candidate):
        normalized = _normalize_poster_source(source)
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    vod.vod_pic = ordered[0] if ordered else ""
    vod.poster_candidates = ordered


def merge_metadata_record(vod: VodItem, record: MetadataRecord, provider_priority: list[str]) -> VodItem:
    del provider_priority
    if record.title:
        if not vod.vod_name:
            vod.vod_name = record.title
        elif record.provider in _TITLE_CORRECTION_PROVIDERS or _is_low_quality_title(vod.vod_name):
            vod.vod_name = choose_preferred_title(vod.vod_name, record.title)
    poster = _normalize_poster_source(record.poster)
    if poster:
        if not vod.vod_pic or _can_override(vod, "poster", record.provider):
            _sync_poster_candidates(vod, primary=poster)
            _set_field_source(vod, "poster", record.provider)
        else:
            _sync_poster_candidates(vod, primary=vod.vod_pic, candidate=poster)
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
    if cleaned_overview and (not vod.vod_content or _can_override_overview(vod, record)):
        vod.vod_content = cleaned_overview
        _set_field_source(vod, "overview", _overview_source_key(record.provider, record.provider_id))
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
                replacement_field = _build_detail_field(record, replacement)
                if replacement_field is not None:
                    merged.append(replacement_field)
                seen_labels.add(field.label)
                continue
            merged.append(field)
            seen_labels.add(field.label)
        for item in detail_fields:
            label = str(item.get("label") or "").strip()
            if label and label not in seen_labels:
                appended_field = _build_detail_field(record, item)
                if appended_field is not None:
                    merged.append(appended_field)
                    seen_labels.add(label)
        vod.detail_fields = merged
        _set_field_source(vod, "detail_fields", record.provider)
    return vod


def fill_missing_metadata_record(vod: VodItem, record: MetadataRecord) -> VodItem:
    if not vod.vod_name and record.title:
        vod.vod_name = record.title
    if not vod.vod_pic and record.poster:
        _sync_poster_candidates(vod, primary=record.poster)
        _set_field_source(vod, "poster", record.provider)
    if not vod.vod_year and record.year:
        vod.vod_year = record.year
        _set_field_source(vod, "year", record.provider)
    if not vod.type_name and record.genres:
        vod.type_name = " / ".join(record.genres)
        _set_field_source(vod, "genres", record.provider)
    if not vod.vod_area and record.country:
        vod.vod_area = record.country
        _set_field_source(vod, "country", record.provider)
    if not vod.vod_lang and record.language:
        vod.vod_lang = record.language
        _set_field_source(vod, "language", record.provider)
    if not vod.vod_director and record.directors:
        vod.vod_director = ",".join(record.directors)
        _set_field_source(vod, "directors", record.provider)
    if not vod.vod_actor and record.actors:
        vod.vod_actor = ",".join(record.actors)
        _set_field_source(vod, "actors", record.provider)
    cleaned_overview = clean_overview_text(record.overview)
    if not vod.vod_content and cleaned_overview:
        vod.vod_content = cleaned_overview
        _set_field_source(vod, "overview", _overview_source_key(record.provider, record.provider_id))
    if not vod.vod_remarks and record.rating:
        vod.vod_remarks = record.rating
        _set_field_source(vod, "rating", record.provider)
    if not vod.dbid and record.douban_id:
        vod.dbid = record.douban_id
        _set_field_source(vod, "douban_id", record.provider)
    detail_fields = _record_detail_fields(record)
    if detail_fields:
        existing_labels = {field.label for field in vod.detail_fields}
        appended = False
        for item in detail_fields:
            label = str(item.get("label") or "").strip()
            if not label or label in existing_labels:
                continue
            appended_field = _build_detail_field(record, item)
            if appended_field is None:
                continue
            vod.detail_fields.append(appended_field)
            existing_labels.add(label)
            appended = True
        if appended:
            _set_field_source(vod, "detail_fields", record.provider)
    return vod


def override_visual_metadata_record(vod: VodItem, record: MetadataRecord) -> VodItem:
    if record.poster and (not vod.vod_pic or _can_override(vod, "poster", record.provider)):
        _sync_poster_candidates(vod, primary=record.poster)
        _set_field_source(vod, "poster", record.provider)
    return vod


def replace_metadata_record(vod: VodItem, record: MetadataRecord) -> VodItem:
    cleaned_overview = clean_overview_text(record.overview)
    detail_fields = _record_detail_fields(record)

    if record.title:
        vod.vod_name = record.title
    _sync_poster_candidates(vod, primary=record.poster)
    vod.vod_year = record.year
    vod.type_name = " / ".join(record.genres)
    vod.vod_area = record.country
    vod.vod_lang = record.language
    vod.vod_director = ",".join(record.directors)
    vod.vod_actor = ",".join(record.actors)
    vod.vod_content = cleaned_overview
    vod.vod_remarks = record.rating
    vod.dbid = record.douban_id
    vod.detail_fields = [field for item in detail_fields if (field := _build_detail_field(record, item)) is not None]

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
        _set_field_source(
            vod,
            field_name,
            _overview_source_key(record.provider, record.provider_id) if field_name == "overview" else record.provider,
        )
    return vod
