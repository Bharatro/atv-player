from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import time

from atv_player.danmaku.models import DanmakuSourceGroup, DanmakuSourceOption, DanmakuSourceSearchResult
from atv_player.danmaku.subtitle import _normalize_opacity, render_danmaku_ass, resolved_outline_style
from atv_player.paths import app_cache_dir

DANMAKU_CACHE_MAX_AGE_SECONDS = 3 * 24 * 60 * 60
_DANMAKU_ASS_CACHE_VERSION = "v6"
_DANMAKU_XML_CACHE_VERSION = "v1"
_DANMAKU_SOURCE_SEARCH_CACHE_VERSION = "v3"


def danmaku_cache_dir() -> Path:
    cache_dir = app_cache_dir() / "danmaku"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def danmaku_ass_cache_path(
    xml_text: str,
    line_count: int,
    *,
    intro_episode_label: str = "",
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = "#FFFFFF",
    position_preset: str = "top",
    scroll_speed: float = 1.0,
    font_size: int = 32,
    opacity: int = 85,
    outline_strength: str = "strong",
) -> Path:
    normalized_opacity = _normalize_opacity(opacity)
    outline_width, shadow = resolved_outline_style(outline_strength)
    digest = sha256(
        "\0".join(
            (
                _DANMAKU_ASS_CACHE_VERSION,
                str(max(1, min(int(line_count), 10))),
                str(intro_episode_label or "").strip(),
                render_mode,
                color_mode,
                uniform_color,
                position_preset,
                f"{float(scroll_speed):.2f}",
                str(int(font_size)),
                str(normalized_opacity),
                str(outline_width),
                str(shadow),
                xml_text,
            )
        ).encode("utf-8")
    ).hexdigest()
    return danmaku_cache_dir() / f"{digest}.ass"


def load_or_create_danmaku_ass_cache(
    xml_text: str,
    line_count: int,
    *,
    intro_episode_label: str = "",
    render_mode: str = "static",
    color_mode: str = "uniform",
    uniform_color: str = "#FFFFFF",
    position_preset: str = "top",
    scroll_speed: float = 1.0,
    font_size: int = 32,
    opacity: int = 85,
    outline_strength: str = "strong",
) -> Path | None:
    subtitle_text = render_danmaku_ass(
        xml_text,
        line_count=line_count,
        intro_episode_label=intro_episode_label,
        render_mode=render_mode,
        color_mode=color_mode,
        uniform_color=uniform_color,
        position_preset=position_preset,
        scroll_speed=scroll_speed,
        font_size=font_size,
        opacity=opacity,
        outline_strength=outline_strength,
    )
    if not subtitle_text:
        return None
    cache_path = danmaku_ass_cache_path(
        xml_text,
        line_count,
        intro_episode_label=intro_episode_label,
        render_mode=render_mode,
        color_mode=color_mode,
        uniform_color=uniform_color,
        position_preset=position_preset,
        scroll_speed=scroll_speed,
        font_size=font_size,
        opacity=opacity,
        outline_strength=outline_strength,
    )
    if not cache_path.exists():
        cache_path.write_text(subtitle_text, encoding="utf-8")
    return cache_path


def _danmaku_xml_cache_key(name: str, reg_src: str) -> str:
    return sha256("\0".join((_DANMAKU_XML_CACHE_VERSION, name.strip(), reg_src.strip())).encode("utf-8")).hexdigest()


def danmaku_xml_cache_path(name: str, reg_src: str) -> Path:
    return danmaku_cache_dir() / f"{_danmaku_xml_cache_key(name, reg_src)}.xml"


def load_cached_danmaku_xml(name: str, reg_src: str) -> str:
    cache_path = danmaku_xml_cache_path(name, reg_src)
    if not cache_path.exists():
        return ""
    try:
        return cache_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_cached_danmaku_xml(name: str, reg_src: str, xml_text: str) -> Path | None:
    normalized_xml = xml_text.strip()
    if not normalized_xml:
        return None
    cache_path = danmaku_xml_cache_path(name, reg_src)
    cache_path.write_text(normalized_xml, encoding="utf-8")
    return cache_path


def _danmaku_source_search_cache_key(name: str, reg_src: str) -> str:
    return sha256("\0".join((_DANMAKU_SOURCE_SEARCH_CACHE_VERSION, name.strip(), reg_src.strip())).encode("utf-8")).hexdigest()


def danmaku_source_search_cache_path(name: str, reg_src: str) -> Path:
    return danmaku_cache_dir() / f"{_danmaku_source_search_cache_key(name, reg_src)}.json"


def load_cached_danmaku_source_search_result(name: str, reg_src: str) -> DanmakuSourceSearchResult | None:
    cache_path = danmaku_source_search_cache_path(name, reg_src)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    groups_payload = payload.get("groups")
    if not isinstance(groups_payload, list):
        return None
    groups: list[DanmakuSourceGroup] = []
    for group_payload in groups_payload:
        if not isinstance(group_payload, dict):
            return None
        options_payload = group_payload.get("options")
        if not isinstance(options_payload, list):
            return None
        options: list[DanmakuSourceOption] = []
        for option_payload in options_payload:
            if not isinstance(option_payload, dict):
                return None
            options.append(
                DanmakuSourceOption(
                    provider=str(option_payload.get("provider") or ""),
                    name=str(option_payload.get("name") or ""),
                    url=str(option_payload.get("url") or ""),
                    ratio=float(option_payload.get("ratio") or 0.0),
                    simi=float(option_payload.get("simi") or 0.0),
                    duration_seconds=int(option_payload.get("duration_seconds") or 0),
                    episode_match=bool(option_payload.get("episode_match")),
                    preferred_by_history=bool(option_payload.get("preferred_by_history")),
                    resolve_ready=bool(option_payload.get("resolve_ready", True)),
                    resolve_context=dict(option_payload.get("resolve_context") or {})
                    if isinstance(option_payload.get("resolve_context"), dict)
                    else {},
                )
            )
        groups.append(
            DanmakuSourceGroup(
                provider=str(group_payload.get("provider") or ""),
                provider_label=str(group_payload.get("provider_label") or ""),
                options=options,
                preferred_by_history=bool(group_payload.get("preferred_by_history")),
            )
        )
    return DanmakuSourceSearchResult(
        groups=groups,
        default_option_url=str(payload.get("default_option_url") or ""),
        default_provider=str(payload.get("default_provider") or ""),
    )


def save_cached_danmaku_source_search_result(
    name: str,
    reg_src: str,
    result: DanmakuSourceSearchResult,
) -> Path | None:
    if not result.groups:
        return None
    payload = {
        "groups": [
            {
                "provider": group.provider,
                "provider_label": group.provider_label,
                "preferred_by_history": group.preferred_by_history,
                "options": [
                    {
                        "provider": option.provider,
                        "name": option.name,
                        "url": option.url,
                        "ratio": option.ratio,
                        "simi": option.simi,
                        "duration_seconds": option.duration_seconds,
                        "episode_match": option.episode_match,
                        "preferred_by_history": option.preferred_by_history,
                        "resolve_ready": option.resolve_ready,
                        "resolve_context": option.resolve_context,
                    }
                    for option in group.options
                ],
            }
            for group in result.groups
        ],
        "default_option_url": result.default_option_url,
        "default_provider": result.default_provider,
    }
    cache_path = danmaku_source_search_cache_path(name, reg_src)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return cache_path


def purge_stale_danmaku_cache(now: float | None = None) -> None:
    cutoff = (now if now is not None else time.time()) - DANMAKU_CACHE_MAX_AGE_SECONDS
    cache_dir = danmaku_cache_dir()
    for entry in cache_dir.iterdir():
        try:
            if not entry.is_file():
                continue
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue
