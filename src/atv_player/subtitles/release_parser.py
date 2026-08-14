"""发布文件名解析。

字幕站对 ``The.Last.of.Us.S02E06.2160p.WEB-DL.H.265-GROUP.mkv`` 这类整串文件名
命中率很差，必须先拆成片名/季集/画质等结构化字段再去搜。

解析结果同时用于匹配打分（见 matcher.py）：候选字幕的发布名里若也含有相同的
画质/片源/编码/压制组，说明和当前视频是同一个发布版本，时间轴更可能对得上。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VIDEO_SUFFIXES = (
    ".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv", ".flv",
    ".rmvb", ".iso", ".m4v", ".webm",
)

_RESOLUTIONS = {
    "2160p": "2160p", "4k": "2160p", "uhd": "2160p",
    "1080p": "1080p", "1080i": "1080p", "fhd": "1080p",
    "720p": "720p", "hd": "720p",
    "480p": "480p", "576p": "576p",
}

_SOURCES = {
    "web-dl": "WEB-DL", "webdl": "WEB-DL", "webrip": "WEBRip", "web": "WEB-DL",
    "bluray": "BluRay", "blu-ray": "BluRay", "bdrip": "BDRip", "brrip": "BDRip",
    "remux": "REMUX", "hdtv": "HDTV", "dvdrip": "DVDRip", "dvd": "DVDRip",
    "hdrip": "HDRip", "uhdtv": "HDTV",
}

_CODECS = {
    "x264": "H.264", "h264": "H.264", "h-264": "H.264", "avc": "H.264",
    "x265": "H.265", "h265": "H.265", "h-265": "H.265", "hevc": "H.265",
    "av1": "AV1", "vp9": "VP9", "xvid": "Xvid", "divx": "DivX",
}

_SEASON_EPISODE = re.compile(r"\bs(\d{1,2})[\s._-]?e(\d{1,3})\b", re.IGNORECASE)
_SEASON_ONLY = re.compile(r"\bs(?:eason)?[\s._-]?(\d{1,2})\b", re.IGNORECASE)
_EPISODE_ONLY = re.compile(r"\be(?:p|pisode)?[\s._-]?(\d{1,3})\b", re.IGNORECASE)
_CN_SEASON = re.compile(r"第\s*(\d{1,2})\s*季")
_CN_EPISODE = re.compile(r"第\s*(\d{1,3})\s*[集话話期]")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_RELEASE_GROUP = re.compile(r"-([A-Za-z0-9_@]+)$")
_SEPARATORS = re.compile(r"[._]+")
_MULTI_SPACE = re.compile(r"\s{2,}")

# 出现这些词说明片名已经结束，后面都是技术参数
_TITLE_STOP_TOKENS = frozenset(
    {
        *_RESOLUTIONS,
        *_SOURCES,
        *_CODECS,
        "ddp5", "ddp", "dts", "aac", "ac3", "truehd", "atmos", "flac", "opus",
        "dv", "hdr", "hdr10", "sdr", "10bit", "8bit", "repack", "proper",
        "extended", "uncut", "limited", "internal", "complete", "multi",
    }
)


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    title: str = ""
    season: int | None = None
    episode: int | None = None
    year: int = 0
    resolution: str = ""
    source: str = ""
    codec: str = ""
    release_group: str = ""
    raw: str = ""


def _strip_container_suffix(name: str) -> str:
    lowered = name.casefold()
    for suffix in _VIDEO_SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _clean_title(text: str) -> str:
    text = _SEPARATORS.sub(" ", text)
    text = text.replace("-", " ").strip(" -[](){}")
    return _MULTI_SPACE.sub(" ", text).strip()


def parse_release_name(name: str) -> ReleaseInfo:
    """把视频文件名拆成结构化字段。

    尽量宽容：解析不出来的字段留空，调用方按"有就用、没有就降级"处理。
    """
    raw = str(name or "").strip()
    if not raw:
        return ReleaseInfo()
    stem = _strip_container_suffix(raw)
    # 压制组在末尾的 -GROUP，要在替换分隔符之前取
    release_group = ""
    group_match = _RELEASE_GROUP.search(stem)
    if group_match is not None and not group_match.group(1).isdigit():
        release_group = group_match.group(1)

    season: int | None = None
    episode: int | None = None
    matched = _SEASON_EPISODE.search(stem)
    if matched is not None:
        season = int(matched.group(1))
        episode = int(matched.group(2))
    else:
        cn_season = _CN_SEASON.search(stem)
        if cn_season is not None:
            season = int(cn_season.group(1))
        cn_episode = _CN_EPISODE.search(stem)
        if cn_episode is not None:
            episode = int(cn_episode.group(1))
        if episode is None:
            bare = _EPISODE_ONLY.search(stem)
            if bare is not None:
                episode = int(bare.group(1))
        if season is None:
            season_only = _SEASON_ONLY.search(stem)
            if season_only is not None:
                season = int(season_only.group(1))

    normalized = _SEPARATORS.sub(" ", stem)
    tokens = [token for token in re.split(r"[\s]+", normalized) if token]
    lowered_tokens = [token.casefold().strip("-[](){}") for token in tokens]

    resolution = ""
    source = ""
    codec = ""
    for token in lowered_tokens:
        if not resolution and token in _RESOLUTIONS:
            resolution = _RESOLUTIONS[token]
        if not source and token in _SOURCES:
            source = _SOURCES[token]
        if not codec and token in _CODECS:
            codec = _CODECS[token]
    if not source:
        joined = normalized.casefold()
        for key, value in _SOURCES.items():
            if key in joined:
                source = value
                break
    if not codec:
        # "H.265" 会被分隔符规则拆成 "H 265"
        compact = normalized.casefold().replace(" ", "")
        for key, value in _CODECS.items():
            if key in compact:
                codec = value
                break

    year = 0
    title_tokens: list[str] = []
    for index, token in enumerate(tokens):
        lowered = lowered_tokens[index]
        if _SEASON_EPISODE.fullmatch(lowered) or _SEASON_EPISODE.match(lowered):
            break
        if lowered in _TITLE_STOP_TOKENS:
            break
        year_match = _YEAR.fullmatch(lowered)
        if year_match is not None:
            year = int(year_match.group(1))
            break
        if _CN_SEASON.search(token) or _CN_EPISODE.search(token):
            break
        title_tokens.append(token)
    if not year:
        year_match = _YEAR.search(normalized)
        if year_match is not None:
            year = int(year_match.group(1))

    title = _clean_title(" ".join(title_tokens))
    if not title:
        title = _clean_title(normalized)
    return ReleaseInfo(
        title=title,
        season=season,
        episode=episode,
        year=year,
        resolution=resolution,
        source=source,
        codec=codec,
        release_group=release_group,
        raw=raw,
    )


def equivalent_tokens(canonical: str) -> tuple[str, ...]:
    """返回某个规范值的所有等价写法（含自身）。

    发布名里 ``x265`` / ``HEVC`` / ``H.265`` 指的是同一种编码，匹配打分时必须
    一视同仁，否则同一个发布版本会因为写法不同而被判成不匹配。
    """
    target = str(canonical or "").strip().casefold()
    if not target:
        return ()
    found = {target}
    for mapping in (_RESOLUTIONS, _SOURCES, _CODECS):
        for alias, value in mapping.items():
            if value.casefold() == target:
                found.add(alias)
    return tuple(sorted(found))
