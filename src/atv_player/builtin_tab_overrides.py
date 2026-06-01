from __future__ import annotations

import json

from atv_player.models import BuiltinTabOverrides


def parse_builtin_tab_overrides_json(payload: str) -> BuiltinTabOverrides:
    try:
        parsed = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return BuiltinTabOverrides()
    if not isinstance(parsed, dict):
        return BuiltinTabOverrides()
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
    return BuiltinTabOverrides(order=order, hidden=hidden, renames=renames)


def dumps_builtin_tab_overrides_json(overrides: BuiltinTabOverrides) -> str:
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
