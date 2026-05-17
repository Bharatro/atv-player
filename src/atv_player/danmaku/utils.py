from __future__ import annotations

import re
from difflib import SequenceMatcher
from html import escape
from typing import Sequence
from urllib.parse import urlparse

from atv_player.danmaku.models import DanmakuRecord
from atv_player.models import PlayItem

_NOISE_PATTERNS = (
    r"【[^】]*】",
    r"\[[^\]]*\]",
    r"\([^)]*(高清|超清|蓝光|qq\.com|youku\.com)[^)]*\)",
)

_CN_NUM = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_EPISODE_PATTERNS = (
    r"第\s*([0-9零一二两三四五六七八九十百]+)\s*[集话期部回]",
    r"\s+0*([0-9]+)\s*[集话期]",
    r"(?<!\d)0*([0-9]+)\s*[集话期]",
    r"\s+0*([0-9]{1,4})\s*$",
    r"\bS\d+\s*E0*([0-9]+)\b",
    r"\bEP\s*0*([0-9]+)\b",
    r"\bE\s*0*([0-9]+)\b",
    r"^\s*0*(\d{1,3})\s*[-_. ]\s*(?:4k|2160p|1080p|720p|480p|360p)\b",
    r"(?:-|—|–)\s*0*([0-9]{1,4})\s*(?:[（(][^()（）]*[)）])?\s*$",
    r"^\s*0*([0-9]{1,4})(?=\s*[丨｜|])",
    r"^\s*0*([0-9]{1,4})\b",
    r"^\s*(\d+)\s*(?:[（(][^()（）]*[)）])?\s*$",
)

_EXPLICIT_EPISODE_PATTERNS = (
    r"第\s*([0-9零一二两三四五六七八九十百]+)\s*[集话期部回]",
    r"(?<!\d)0*([0-9]+)\s*[集话期]",
    r"\bS\d+\s*E0*([0-9]+)\b",
    r"\bEP\s*0*([0-9]+)\b",
    r"\bE\s*0*([0-9]+)\b",
)

_TECHNICAL_FILENAME_MARKERS = (
    "2160p",
    "1080p",
    "720p",
    "web-dl",
    "webrip",
    "bluray",
    "bdrip",
    "hdrip",
    "hdtv",
    "itunes",
    "amzn",
    "nf",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "hdr",
    "dv",
    "ddp",
    "aac",
    "atmos",
)

_QUALITY_ONLY_FILENAME_TOKENS = {
    "4k",
    "2160p",
    "1080p",
    "720p",
    "480p",
    "hdr",
    "dv",
    "hevc",
    "x264",
    "x265",
    "h264",
    "h265",
    "av1",
    "aac",
    "ddp",
    "atmos",
    "webdl",
    "webrip",
    "bluray",
    "bdrip",
    "itunes",
    "amzn",
    "nf",
    "国语",
    "粤语",
    "普通话",
    "原声",
    "超清",
    "高清",
    "蓝光",
    "正片",
    "完整版",
    "全片",
}

_VARIETY_HINT_TOKENS = (
    "纯享",
    "加更",
    "舞台",
    "未播",
    "会员版",
    "训练室",
    "reaction",
    "直拍",
)


def normalize_name(name: str) -> str:
    value = str(name).strip()
    for pattern in _NOISE_PATTERNS:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _cn_to_int(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    units = {"十": 10, "百": 100}
    for char in text:
        if char in _CN_NUM:
            current = _CN_NUM[char]
            continue
        unit = units.get(char)
        if unit is None:
            return None
        total += (current or 1) * unit
        current = 0
    return total + current


def extract_episode_number(name: str) -> int | None:
    value = normalize_name(name)
    for pattern in _EPISODE_PATTERNS:
        match = re.search(pattern, value, re.IGNORECASE)
        if match is None:
            continue
        if _looks_like_episode_range_part(value, match):
            continue
        if _looks_like_date_fragment_part(value, match):
            continue
        raw = match.group(1)
        episode = int(raw) if raw.isdigit() else _cn_to_int(raw)
        if episode is not None and 1 <= episode <= 10000:
            return episode
    return None


def _looks_like_episode_range_part(value: str, match: re.Match[str]) -> bool:
    prefix = value[: match.start()]
    suffix = value[match.end() :]
    return bool(
        re.search(r"\d{1,4}\s*-\s*$", prefix)
        or re.match(r"^\s*-\s*\d{1,4}", suffix)
    )


def _looks_like_date_fragment_part(value: str, match: re.Match[str]) -> bool:
    prefix = value[: match.start()]
    raw = match.group(1)
    if not raw.isdigit():
        return False
    fragment = int(raw)
    return bool(
        fragment <= 12
        and re.search(r"(?:19|20)\d{2}\s*$", prefix)
        or fragment <= 31
        and re.search(r"(?:19|20)\d{2}[-./]\d{1,2}\s*$", prefix)
    )


def has_explicit_episode_marker(name: str) -> bool:
    value = normalize_name(name)
    return any(re.search(pattern, value, re.IGNORECASE) is not None for pattern in _EXPLICIT_EPISODE_PATTERNS)


def _looks_like_technical_media_filename(name: str) -> bool:
    value = normalize_name(name).casefold()
    has_file_extension = re.search(r"\.(mkv|mp4|avi|mov|m4v|ts|flv)\b", value) is not None
    has_year_prefix = re.match(r"^\s*(?:19|20)\d{2}(?:[.\s_-]|$)", value) is not None
    has_marker = any(re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", value) is not None for marker in _TECHNICAL_FILENAME_MARKERS)
    return has_marker and (has_file_extension or has_year_prefix)


def _looks_like_quality_only_media_filename(name: str) -> bool:
    value = normalize_name(name)
    if re.search(r"\.(mkv|mp4|avi|mov|m4v|ts|flv)\b", value, re.IGNORECASE) is None:
        return False
    basename = re.sub(r"\([^)]*\)\s*$", "", value).strip()
    basename = re.sub(r"\.(mkv|mp4|avi|mov|m4v|ts|flv)\b.*$", "", basename, flags=re.IGNORECASE).strip()
    if not basename:
        return False
    tokens = [
        token.casefold()
        for token in re.split(r"[.\s_\-]+", basename)
        if token.strip()
    ]
    if not tokens:
        return False
    return all(token in _QUALITY_ONLY_FILENAME_TOKENS for token in tokens)


def _path_basename(value: str) -> str:
    text = str(value or "").strip().rstrip("/\\")
    if not text:
        return ""
    return re.split(r"[\\/]", text)[-1]


def _episode_number_from_candidate(name: str) -> int | None:
    technical_filename = _looks_like_technical_media_filename(name)
    direct = extract_episode_number(name)
    if direct is not None and (not technical_filename or has_explicit_episode_marker(name)):
        return direct
    return None


def _play_item_episode_number(item: PlayItem) -> int | None:
    candidates: list[str] = []
    for value in (item.original_title, item.title, _path_basename(item.path)):
        candidate = str(value or "").strip()
        if not candidate or candidate in candidates:
            continue
        candidates.append(candidate)
    for candidate in candidates:
        if (episode_number := _episode_number_from_candidate(candidate)) is not None:
            return episode_number
    return None


def _play_item_has_technical_filename(item: PlayItem) -> bool:
    seen: list[str] = []
    for value in (item.original_title, item.title, _path_basename(item.path)):
        candidate = str(value or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.append(candidate)
        if _looks_like_technical_media_filename(candidate):
            return True
    return False


def infer_playlist_episode_number(current_item: PlayItem, playlist: Sequence[PlayItem] | None = None) -> int | None:
    current_title = current_item.title or ""
    direct = _play_item_episode_number(current_item)
    if direct is not None:
        return direct
    if _play_item_has_technical_filename(current_item):
        return None
    if _looks_like_quality_only_media_filename(current_title) and (
        (playlist is None and current_item.index <= 0)
        or (playlist is not None and len(playlist) <= 1)
    ):
        return None
    current_index = current_item.index
    if not playlist:
        return current_index + 1 if current_index >= 0 else None
    if 0 <= current_index < len(playlist):
        indexed = _play_item_episode_number(playlist[current_index])
        if indexed is not None:
            return indexed
    aligned = [
        (item.index, episode)
        for item in playlist
        if (episode := _play_item_episode_number(item)) is not None
    ]
    if aligned:
        seq_like = sum(1 for index, episode in aligned if episode == index + 1)
        if seq_like >= max(1, len(aligned) // 2):
            return current_index + 1 if current_index >= 0 else None
    return current_index + 1 if current_index >= 0 else None


def strip_episode_suffix(name: str) -> str:
    value = normalize_name(name)
    patterns = (
        r"\s+第\s*\d+\s*[集话期]\s*$",
        r"\s+\d+\s*[集话期]\s*$",
        r"\s+0*\d{1,4}\s*$",
        r"\s+S\d+\s*E\d+\s*$",
        r"\s+EP?\s*\d+\s*$",
        r"\s+E\s*\d+\s*$",
    )
    for pattern in patterns:
        stripped = re.sub(pattern, "", value, flags=re.IGNORECASE)
        if stripped != value:
            return stripped.strip()
    return value


def _extract_variety_date_key(name: str) -> str | None:
    value = normalize_name(name)
    match = re.search(
        r"(?<!\d)((?:19|20)\d{2})[\s._/-]?(0[1-9]|1[0-2])[\s._/-]?(0[1-9]|[12]\d|3[01])(?:\s*期)?(?!\d)",
        value,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return "".join(match.groups())


def _extract_variety_issue_number(name: str) -> int | None:
    value = normalize_name(name)
    patterns = (
        r"第\s*([0-9零一二两三四五六七八九十百]+)\s*期",
        r"(?<!\d)0*([0-9]{1,4})\s*期",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match is None:
            continue
        raw = match.group(1)
        issue = int(raw) if raw.isdigit() else _cn_to_int(raw)
        if issue is not None and 1 <= issue <= 10000:
            return issue
    return None


def extract_variety_issue_key(name: str) -> str | None:
    date_key = _extract_variety_date_key(name)
    if date_key is not None:
        return date_key
    issue_number = _extract_variety_issue_number(name)
    if issue_number is not None:
        return str(issue_number)
    return None


def is_likely_variety_title(name: str) -> bool:
    value = normalize_name(name)
    if re.search(r"第\s*[0-9零一二两三四五六七八九十百]+\s*期", value, re.IGNORECASE) is not None:
        return True
    if re.search(r"(?<!\d)0*[0-9]{1,4}\s*期", value, re.IGNORECASE) is not None:
        return True
    if _extract_variety_date_key(value) is not None:
        return True
    lowered = value.casefold()
    return any(token in lowered for token in _VARIETY_HINT_TOKENS)


def strip_variety_issue_suffix(name: str) -> str:
    value = normalize_name(name)
    split_patterns = (
        r"^(?P<title>.+?)\s+(?:(?:19|20)\d{2}[\s._/-]?(?:0[1-9]|1[0-2])[\s._/-]?(?:0[1-9]|[12]\d|3[01])(?:\s*期)?)(?:\s+.*)?$",
        r"^(?P<title>.*?\D)\s*第\s*[0-9零一二两三四五六七八九十百]+\s*期(?:[上下中终完]?)?(?:[：: ].*)?$",
        r"^(?P<title>.*?\D)\s*0*[0-9]{1,4}\s*期(?:[上下中终完]?)?(?:[：: ].*)?$",
    )
    for pattern in split_patterns:
        match = re.match(pattern, value, re.IGNORECASE)
        if match is None:
            continue
        title = match.group("title").strip()
        if title:
            return title
    patterns = (
        r"[\s._/-]+第\s*[0-9零一二两三四五六七八九十百]+\s*期\s*$",
        r"[\s._/-]+0*[0-9]{1,4}\s*期\s*$",
        r"[\s._/-]+(?:19|20)\d{2}[\s._/-]?(?:0[1-9]|1[0-2])[\s._/-]?(?:0[1-9]|[12]\d|3[01])(?:\s*期)?\s*$",
    )
    for pattern in patterns:
        stripped = re.sub(pattern, "", value, flags=re.IGNORECASE)
        if stripped != value:
            return stripped.strip()
    return value


def match_provider(reg_src: str) -> str | None:
    host = (urlparse(reg_src).hostname or reg_src or "").lower()
    if "qq.com" in host:
        return "tencent"
    if "youku.com" in host:
        return "youku"
    if "bilibili.com" in host or "b23.tv" in host:
        return "bilibili"
    if "iqiyi.com" in host:
        return "iqiyi"
    if "mgtv.com" in host:
        return "mgtv"
    return None


def _simplify_name(name: str) -> str:
    value = normalize_name(name).casefold()
    value = re.sub(
        r"第\s*([0-9零一二两三四五六七八九十百]+)\s*季",
        lambda match: f"第{_cn_to_int(match.group(1)) if not match.group(1).isdigit() else int(match.group(1))}季",
        value,
    )
    value = re.sub(r"第\s*\d+\s*[集话期]", "", value)
    value = re.sub(r"(?<!\d)\d+\s*[集话期]", "", value)
    value = re.sub(r"\s+0*\d{1,4}\s*$", "", value)
    value = re.sub(r"\bs\d+\s*e\d+\b", "", value)
    value = re.sub(r"\bep?\s*\d+\b", "", value)
    value = re.sub(r"\be\s*\d+\b", "", value)
    value = re.sub(r"[\W_]+", "", value)
    return value


def _extract_title_sequel_number(name: str) -> int | None:
    value = _simplify_name(strip_episode_suffix(name))
    matches = re.findall(r"(?<=[^\W\d_])(\d{1,2})(?=[^\W\d_]|$)", value, re.UNICODE)
    if not matches:
        return None
    sequel = int(matches[-1])
    return sequel if 1 <= sequel <= 20 else None


def _has_sequel_number_mismatch(left: str, right: str) -> bool:
    left_seq = _extract_title_sequel_number(left)
    right_seq = _extract_title_sequel_number(right)
    if left_seq is None and right_seq is None:
        return False
    return left_seq != right_seq


def similarity_score(left: str, right: str) -> float:
    return SequenceMatcher(None, _simplify_name(left), _simplify_name(right)).ratio()


def episode_title_matches(target: str, candidate: str) -> bool:
    if _has_sequel_number_mismatch(target, candidate):
        return False
    target_base = _simplify_name(strip_episode_suffix(target))
    candidate_base = _simplify_name(strip_episode_suffix(candidate))
    if not target_base or not candidate_base:
        return True
    return candidate_base == target_base or candidate_base.startswith(target_base)


def should_filter_name(target: str, candidate: str) -> bool:
    if _has_sequel_number_mismatch(target, candidate):
        return True
    left = _simplify_name(target)
    right = _simplify_name(candidate)
    if not left or not right:
        return False
    if left in right or right in left:
        return False
    return similarity_score(left, right) < 0.55


def build_xml(records: Sequence[DanmakuRecord]) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?><i>']
    for record in records:
        parts.append(
            f'<d p="{record.time_offset},{record.pos},25,{record.color}">{escape(record.content, quote=False)}</d>'
        )
    parts.append("</i>")
    return "".join(parts)
