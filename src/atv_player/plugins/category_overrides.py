from __future__ import annotations

import json

from atv_player.models import DoubanCategory, SpiderPluginCategoryOverrides, SpiderPluginRawCategory


def parse_category_overrides_json(payload: str) -> SpiderPluginCategoryOverrides:
    try:
        parsed = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return SpiderPluginCategoryOverrides()
    if not isinstance(parsed, dict):
        return SpiderPluginCategoryOverrides()
    raw_order = parsed.get("order") or []
    raw_hidden = parsed.get("hidden") or []
    raw_renames = parsed.get("renames") or {}
    order = [str(item).strip() for item in raw_order if str(item).strip()]
    hidden = [str(item).strip() for item in raw_hidden if str(item).strip()]
    renames: dict[str, str] = {}
    if isinstance(raw_renames, dict):
        for key, value in raw_renames.items():
            normalized_key = str(key).strip()
            normalized_value = str(value).strip()
            if normalized_key and normalized_value:
                renames[normalized_key] = normalized_value
    return SpiderPluginCategoryOverrides(order=order, hidden=hidden, renames=renames)


def dumps_category_overrides_json(overrides: SpiderPluginCategoryOverrides) -> str:
    payload: dict[str, object] = {}
    if overrides.order:
        payload["order"] = list(overrides.order)
    if overrides.hidden:
        payload["hidden"] = list(overrides.hidden)
    if overrides.renames:
        payload["renames"] = dict(overrides.renames)
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def apply_category_overrides(
    categories: list[SpiderPluginRawCategory],
    overrides: SpiderPluginCategoryOverrides,
) -> list[DoubanCategory]:
    by_id = {category.type_id: category for category in categories}
    hidden = set(overrides.hidden)
    visible_ids = [category.type_id for category in categories if category.type_id not in hidden]
    ordered_ids: list[str] = []
    for type_id in overrides.order:
        if type_id in visible_ids and type_id not in ordered_ids:
            ordered_ids.append(type_id)
    for type_id in visible_ids:
        if type_id not in ordered_ids:
            ordered_ids.append(type_id)
    return [
        DoubanCategory(
            type_id=type_id,
            type_name=overrides.renames.get(type_id, by_id[type_id].type_name),
            filters=list(by_id[type_id].filters),
        )
        for type_id in ordered_ids
    ]
