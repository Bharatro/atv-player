from __future__ import annotations

import re

from atv_player.following_models import FollowingRecord
from atv_player.heat.models import HeatMediaIdentity
from atv_player.metadata.models import MetadataQuery
from atv_player.metadata.providers.tmdb import infer_tmdb_media_type
from atv_player.models import FavoriteRecord, PlaybackDetailField, PlayItem, VodItem


HEAT_REQUIRED_EXTERNAL_ID_KEYS = {"tmdb", "douban", "bangumi"}


def normalize_heat_title(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[第][一二三四五六七八九十0-9]+[季部]?", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[·:：,，.。!！?？'\"“”‘’《》<>【】()[\]{}_-]", "", text)
    return text.strip()


def _field_value(fields: list[PlaybackDetailField], labels: set[str]) -> str:
    normalized_labels = {label.casefold() for label in labels}
    for field in fields:
        if str(field.label or "").strip().casefold() not in normalized_labels:
            continue
        return str(field.value or "").strip()
    return ""


def _field_action_target(fields: list[PlaybackDetailField], labels: set[str]) -> str:
    normalized_labels = {label.casefold() for label in labels}
    for field in fields:
        if str(field.label or "").strip().casefold() not in normalized_labels:
            continue
        for part in list(getattr(field, "value_parts", []) or []):
            action = getattr(part, "action", None)
            target = str(getattr(action, "target", "") or "").strip()
            if target:
                return target
    return ""


def _tmdb_media_type(vod: VodItem, explicit: str = "") -> str:
    if explicit in {"movie", "tv"}:
        return explicit
    inferred = infer_tmdb_media_type(
        MetadataQuery(
            title=str(vod.vod_name or ""),
            year=str(vod.vod_year or ""),
            type_name=str(vod.type_name or ""),
            category_name=str(vod.category_name or ""),
        )
    )
    return inferred or "movie"


def _tmdb_external_id(value: str, media_type: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if ":" in normalized:
        prefix, raw_id = normalized.split(":", 1)
        if prefix in {"movie", "tv"} and raw_id.strip():
            return f"{prefix}:{raw_id.strip()}"
    return f"{media_type}:{normalized}"


def _tmdb_identity_from_field(fields: list[PlaybackDetailField], fallback_media_type: str) -> tuple[str, str]:
    tmdb_id = _field_value(fields, {"TMDB ID", "tmdb id"})
    if not tmdb_id:
        return "", fallback_media_type
    normalized = str(tmdb_id or "").strip()
    if ":" in normalized:
        prefix, raw_id = normalized.split(":", 1)
        if prefix in {"movie", "tv"} and raw_id.strip():
            return f"{prefix}:{raw_id.strip()}", prefix
    target = _field_action_target(fields, {"TMDB ID", "tmdb id"})
    media_type = target if target in {"movie", "tv"} else fallback_media_type
    return _tmdb_external_id(normalized, media_type), media_type


def _positive_int_text(value: object) -> str:
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError):
        return ""
    return str(normalized) if normalized > 0 else ""


def heat_identity_from_vod(
    vod: VodItem,
    item: PlayItem | None = None,
) -> HeatMediaIdentity | None:
    fields = [
        *list(getattr(vod, "detail_fields", []) or []),
        *list(getattr(item, "detail_fields", []) or []),
    ]
    vod_title = str(getattr(vod, "vod_name", "") or "").strip()
    title_source = str(
        dict(getattr(vod, "metadata_field_sources", {}) or {}).get("title") or ""
    ).strip()
    if title_source == "tmdb" and vod_title:
        title = vod_title
    else:
        title = (
            str(getattr(item, "media_title", "") or "").strip()
            or vod_title
            or str(getattr(item, "title", "") or "").strip()
        )
    if not title:
        return None

    media_type = _tmdb_media_type(vod)
    external_ids: dict[str, str] = {}
    tmdb_value, media_type = _tmdb_identity_from_field(fields, media_type)
    douban_id = (
        _field_value(fields, {"豆瓣ID", "豆瓣id", "豆瓣 ID", "豆瓣 id", "dbid", "douban id"})
        or _positive_int_text(getattr(vod, "dbid", 0))
    )
    bangumi_id = _field_value(fields, {"Bangumi ID", "bangumi id"})
    if tmdb_value:
        external_ids["tmdb"] = tmdb_value
    if douban_id:
        external_ids["douban"] = douban_id
    if bangumi_id:
        external_ids["bangumi"] = bangumi_id

    if tmdb_value:
        media_key = f"tmdb:{tmdb_value}"
    elif douban_id:
        media_key = f"douban:{douban_id}"
    elif bangumi_id:
        media_key = f"bangumi:{bangumi_id}"
    else:
        normalized_title = normalize_heat_title(title)
        if not normalized_title:
            return None
        media_key = f"title:{normalized_title}"

    poster = str(getattr(vod, "vod_pic", "") or "").strip()
    if item is not None:
        poster = poster or str(getattr(item, "video_cover_override", "") or "").strip()
    return HeatMediaIdentity(
        media_key=media_key,
        title=title,
        poster=poster,
        year=str(getattr(vod, "vod_year", "") or "").strip(),
        media_type=media_type,
        external_ids=external_ids,
    )


def heat_identity_from_following(record: FollowingRecord) -> HeatMediaIdentity | None:
    title = str(getattr(record, "title", "") or "").strip()
    if not title:
        return None
    provider = str(getattr(record, "provider", "") or "").strip()
    provider_id = str(getattr(record, "provider_id", "") or "").strip()
    media_kind = str(getattr(record, "media_kind", "") or "").strip()
    media_type = "tv" if media_kind in {"tv", "剧集", "动漫", "anime"} else "movie"
    external_ids = {
        str(key): str(value)
        for key, value in dict(getattr(record, "external_ids", {}) or {}).items()
        if str(value or "").strip()
    }

    if provider == "tmdb" and provider_id:
        tmdb_value = provider_id if ":" in provider_id else f"{media_type}:{provider_id}"
        external_ids["tmdb"] = tmdb_value
        media_key = f"tmdb:{tmdb_value}"
    elif provider in {"douban", "official_douban", "local_douban"} and provider_id:
        external_ids["douban"] = provider_id
        media_key = f"douban:{provider_id}"
    elif provider == "bangumi" and provider_id:
        external_ids["bangumi"] = provider_id
        media_key = f"bangumi:{provider_id}"
    elif external_ids.get("tmdb"):
        tmdb_value = _tmdb_external_id(external_ids["tmdb"], media_type)
        external_ids["tmdb"] = tmdb_value
        media_key = f"tmdb:{tmdb_value}"
    elif external_ids.get("douban"):
        media_key = f"douban:{external_ids['douban']}"
    elif external_ids.get("bangumi"):
        media_key = f"bangumi:{external_ids['bangumi']}"
    else:
        normalized_title = normalize_heat_title(title)
        if not normalized_title:
            return None
        media_key = f"title:{normalized_title}"

    return HeatMediaIdentity(
        media_key=media_key,
        title=title,
        original_title=str(getattr(record, "original_title", "") or "").strip(),
        poster=str(getattr(record, "poster", "") or "").strip(),
        media_type=media_type,
        external_ids=external_ids,
    )


def heat_identity_from_favorite(record: FavoriteRecord) -> HeatMediaIdentity | None:
    title = str(
        getattr(record, "latest_vod_name", "")
        or getattr(record, "vod_name_snapshot", "")
        or ""
    ).strip()
    if not title:
        return None
    normalized_title = normalize_heat_title(title)
    if not normalized_title:
        return None
    return HeatMediaIdentity(
        media_key=f"title:{normalized_title}",
        title=title,
        poster=str(getattr(record, "vod_pic", "") or "").strip(),
    )


def has_required_heat_external_id(media: HeatMediaIdentity | None) -> bool:
    if media is None:
        return False
    external_ids = dict(getattr(media, "external_ids", {}) or {})
    return any(str(external_ids.get(key) or "").strip() for key in HEAT_REQUIRED_EXTERNAL_ID_KEYS)
