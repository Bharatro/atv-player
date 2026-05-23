from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from atv_player.models import AppConfig, CategoryFilter, CategoryFilterOption, DoubanCategory

LIST_KEYWORD_FILTER_KEY = "list_keyword"


@dataclass(slots=True)
class YouTubeCategoryConfig:
    categories: list[DoubanCategory] = field(default_factory=list)
    raw_text: str = ""


@dataclass(slots=True)
class YouTubeQueryPlan:
    kind: str
    value: str
    unsupported_filters: dict[str, str] = field(default_factory=dict)


TextLoader = Callable[[str], str]
SaveConfig = Callable[[], None]
Now = Callable[[], int]


def strip_jsonc_comments(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _text(value: object) -> str:
    return str(value or "").strip()


def _map_filter_option(payload: object) -> CategoryFilterOption | None:
    if not isinstance(payload, dict):
        return None
    name = _text(payload.get("n"))
    if not name:
        return None
    return CategoryFilterOption(name=name, value=_text(payload.get("v")))


def _map_filter_group(payload: object) -> CategoryFilter | None:
    if not isinstance(payload, dict):
        return None
    key = _text(payload.get("key"))
    name = _text(payload.get("name"))
    if not key or not name:
        return None
    options = [
        option
        for option in (_map_filter_option(item) for item in payload.get("value") or [])
        if option is not None
    ]
    if not options:
        return None
    return CategoryFilter(key=key, name=name, options=options)


def _list_keyword_filter(category_id: str) -> CategoryFilter | None:
    if not category_id.startswith("LIST:"):
        return None
    values = [part.strip() for part in category_id.removeprefix("LIST:").split(",") if part.strip()]
    if not values:
        return None
    return CategoryFilter(
        key=LIST_KEYWORD_FILTER_KEY,
        name="关键词",
        options=[CategoryFilterOption(name=value, value=value) for value in values],
    )


def parse_youtube_category_config(text: str) -> YouTubeCategoryConfig:
    payload = json.loads(strip_jsonc_comments(text))
    if not isinstance(payload, dict):
        return YouTubeCategoryConfig(raw_text=text)
    raw_filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    categories: list[DoubanCategory] = []
    for item in payload.get("class") or []:
        if not isinstance(item, dict):
            continue
        category_id = _text(item.get("type_id"))
        category_name = _text(item.get("type_name"))
        if not category_id or not category_name:
            continue
        filters: list[CategoryFilter] = []
        list_filter = _list_keyword_filter(category_id)
        if list_filter is not None:
            filters.append(list_filter)
        filters.extend(
            group
            for group in (_map_filter_group(group_payload) for group_payload in raw_filters.get(category_id) or [])
            if group is not None
        )
        categories.append(DoubanCategory(type_id=category_id, type_name=category_name, filters=filters))
    return YouTubeCategoryConfig(categories=categories, raw_text=text)


def _builtin_config(categories: list[DoubanCategory] | None) -> YouTubeCategoryConfig:
    return YouTubeCategoryConfig(
        categories=[DoubanCategory(category.type_id, category.type_name, list(category.filters)) for category in categories or []]
    )


def _load_source_text(config: AppConfig, text_loader: TextLoader | None) -> str:
    source_type = str(config.youtube_category_source_type or "builtin").strip()
    source_value = str(config.youtube_category_source_value or "").strip()
    if source_type == "remote":
        if not source_value:
            raise ValueError("YouTube 远程分类配置 URL 为空")
        if text_loader is None:
            raise ValueError("缺少 YouTube 远程分类配置加载器")
        return text_loader(source_value)
    if source_type == "local":
        if not source_value:
            raise ValueError("YouTube 本地分类配置路径为空")
        return Path(source_value).read_text(encoding="utf-8")
    raise ValueError(f"不支持的 YouTube 分类配置源: {source_type}")


def load_youtube_category_config(
    config: AppConfig,
    *,
    text_loader: TextLoader | None = None,
    save_config: SaveConfig | None = None,
    now: Now | None = None,
    builtin_categories: list[DoubanCategory] | None = None,
) -> YouTubeCategoryConfig:
    source_type = str(config.youtube_category_source_type or "builtin").strip()
    if source_type == "builtin":
        return _builtin_config(builtin_categories)
    try:
        text = _load_source_text(config, text_loader)
        parsed = parse_youtube_category_config(text)
        if not parsed.categories:
            raise ValueError("YouTube 分类配置没有可用分类")
        config.youtube_category_cache_json = text
        config.youtube_category_cache_refreshed_at = int((now or time.time)())
        config.youtube_category_cache_error = ""
        if save_config is not None:
            save_config()
        return parsed
    except Exception as exc:
        config.youtube_category_cache_error = str(exc)
        if save_config is not None:
            save_config()
        cached_text = str(config.youtube_category_cache_json or "")
        if cached_text:
            try:
                cached = parse_youtube_category_config(cached_text)
                if cached.categories:
                    return cached
            except Exception:
                pass
        return _builtin_config(builtin_categories)


def normalize_youtube_vod_id(value: str) -> str:
    text = str(value or "").strip()
    return text


def plan_youtube_query(category_id: str, filters: dict[str, str] | None = None) -> YouTubeQueryPlan:
    active = {str(key): str(value).strip() for key, value in (filters or {}).items() if str(value).strip()}
    base = normalize_youtube_vod_id(category_id)
    if base.startswith("LIST:"):
        keywords = [part.strip() for part in base.removeprefix("LIST:").split(",") if part.strip()]
        base = active.pop(LIST_KEYWORD_FILTER_KEY, keywords[0] if keywords else "")
    tid = active.pop("tid", "")
    if tid:
        base = normalize_youtube_vod_id(tid)
    unsupported = {key: active.pop(key) for key in list(active) if key in {"sort", "type", "format"}}
    suffixes = [active.pop("time", "")]
    suffixes.extend(active.values())
    query = " ".join(part for part in [base, *suffixes] if part).strip()
    if query.startswith("yt:playlist:"):
        return YouTubeQueryPlan("playlist", query.removeprefix("yt:playlist:"), unsupported)
    if query.startswith("yt:channel:"):
        return YouTubeQueryPlan("channel", query.removeprefix("yt:channel:"), unsupported)
    if query.startswith("yt:video:"):
        return YouTubeQueryPlan("video", query.removeprefix("yt:video:"), unsupported)
    if query.startswith("@"):
        return YouTubeQueryPlan("channel", query, unsupported)
    return YouTubeQueryPlan("search", query, unsupported)
