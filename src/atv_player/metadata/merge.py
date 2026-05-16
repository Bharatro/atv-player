from __future__ import annotations

from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.providers.douban import clean_overview_text
from atv_player.models import PlaybackDetailField, VodItem


def merge_metadata_record(vod: VodItem, record: MetadataRecord, provider_priority: list[str]) -> VodItem:
    del provider_priority
    if not vod.vod_name and record.title:
        vod.vod_name = record.title
    if not vod.vod_pic and record.poster:
        vod.vod_pic = record.poster
    if not vod.vod_year and record.year:
        vod.vod_year = record.year
    if not vod.type_name and record.genres:
        vod.type_name = " / ".join(record.genres)
    if not vod.vod_area and record.country:
        vod.vod_area = record.country
    if not vod.vod_lang and record.language:
        vod.vod_lang = record.language
    if not vod.vod_director and record.directors:
        vod.vod_director = ",".join(record.directors)
    if not vod.vod_actor and record.actors:
        vod.vod_actor = ",".join(record.actors)
    cleaned_overview = clean_overview_text(record.overview)
    if cleaned_overview:
        vod.vod_content = cleaned_overview
    if record.rating:
        vod.vod_remarks = record.rating
    if not vod.dbid and record.douban_id:
        vod.dbid = record.douban_id
    if record.detail_fields:
        merged: list[PlaybackDetailField] = []
        seen_labels: set[str] = set()
        for field in vod.detail_fields:
            replacement = next((item for item in record.detail_fields if item.get("label") == field.label), None)
            if replacement is not None:
                merged.append(PlaybackDetailField(label=field.label, value=str(replacement.get("value") or "")))
                seen_labels.add(field.label)
                continue
            merged.append(field)
            seen_labels.add(field.label)
        for item in record.detail_fields:
            label = str(item.get("label") or "").strip()
            if label and label not in seen_labels:
                merged.append(PlaybackDetailField(label=label, value=str(item.get("value") or "")))
                seen_labels.add(label)
        vod.detail_fields = merged
    return vod
