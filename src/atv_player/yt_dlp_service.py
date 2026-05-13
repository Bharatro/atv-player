from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from html import escape
from time import monotonic
from typing import Callable
from urllib.parse import urlparse

from atv_player.models import (
    ExternalSubtitleOption,
    PlayItem,
    VideoQualityOption,
    VodItem,
)

logger = logging.getLogger(__name__)

_KNOWN_YTDLP_DOMAINS = frozenset({
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "www.youtube.com",
    "music.youtube.com",
    "twitter.com",
    "x.com",
    "mobile.twitter.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "vimeo.com",
    "www.vimeo.com",
    "dailymotion.com",
    "www.dailymotion.com",
    "twitch.tv",
    "www.twitch.tv",
    "facebook.com",
    "www.facebook.com",
    "bilibili.com",
    "www.bilibili.com",
    "b23.tv",
    "nicovideo.jp",
    "www.nicovideo.jp",
    "soundcloud.com",
    "streamable.com",
    "reddit.com",
    "www.reddit.com",
    "rumble.com",
    "odysee.com",
    "peertube.tv",
    "bandcamp.com",
    "pinterest.com",
    "tumblr.com",
    "weibo.com",
    "www.weibo.com",
    "m.weibo.com",
})

_LANG_CODE_NAMES: dict[str, str] = {
    "en": "英文",
    "zh-Hans": "简体中文",
    "zh-Hant": "繁体中文",
    "zh": "中文",
    "zh-CN": "中文",
    "zh-TW": "中文",
}

_DEFAULT_STARTUP_MAX_HEIGHT = 1080
_DASH_DATA_URI_PREFIX = "data:application/dash+xml;base64,"


def _has_muxed_audio(fmt: dict) -> bool:
    acodec = fmt.get("acodec", "") or ""
    return acodec != "none"


def _quality_id_for_height(height: int) -> str:
    return f"ytdlp_{height}"


def _quality_height_from_id(quality_id: str) -> int | None:
    if not quality_id.startswith("ytdlp_"):
        return None
    suffix = quality_id.removeprefix("ytdlp_")
    if not suffix.isdigit():
        return None
    height = int(suffix)
    return height if height > 0 else None


def _build_format_selector(max_height: int | None) -> str:
    if max_height and max_height > 0:
        return (
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/bestvideo+bestaudio/best"
        )
    return "bestvideo+bestaudio/best"


def _media_mime_type(fmt: dict) -> str:
    ext = str(fmt.get("ext") or "").strip().lower()
    vcodec = str(fmt.get("vcodec") or "").strip().lower()
    acodec = str(fmt.get("acodec") or "").strip().lower()
    if vcodec and vcodec != "none":
        if ext == "webm":
            return "video/webm"
        return "video/mp4"
    if acodec and acodec != "none":
        if ext == "webm":
            return "audio/webm"
        return "audio/mp4"
    return "application/octet-stream"


def _representation_id(fmt: dict, fallback: str) -> str:
    format_id = str(fmt.get("format_id") or "").strip()
    if format_id:
        return f"{fallback}_{format_id}"
    return fallback


def _build_requested_formats_dash_data_uri(info: dict) -> str:
    requested_formats = info.get("requested_formats") or []
    if not isinstance(requested_formats, list):
        return ""
    video_formats = [
        fmt for fmt in requested_formats
        if isinstance(fmt, dict) and fmt.get("url") and (fmt.get("vcodec", "") or "") != "none"
    ]
    audio_formats = [
        fmt for fmt in requested_formats
        if isinstance(fmt, dict) and fmt.get("url") and (fmt.get("acodec", "") or "") != "none"
    ]
    if not video_formats or not audio_formats:
        return ""
    video_format = video_formats[0]
    audio_format = audio_formats[0]
    video_bandwidth = int(float(video_format.get("tbr") or 0) * 1000)
    audio_bandwidth = int(float(audio_format.get("tbr") or 0) * 1000)
    video_width = int(video_format.get("width") or 0)
    video_height = int(video_format.get("height") or 0)
    audio_rate = int(audio_format.get("asr") or 0)
    video_codecs = escape(str(video_format.get("vcodec") or ""), quote=True)
    audio_codecs = escape(str(audio_format.get("acodec") or ""), quote=True)
    video_url = escape(str(video_format["url"]), quote=False)
    audio_url = escape(str(audio_format["url"]), quote=False)
    video_id = _representation_id(video_format, _quality_id_for_height(video_height or 0))
    audio_id = _representation_id(audio_format, "ytdlp_audio")
    raw_xml = f"""
<MPD>
  <Period>
    <AdaptationSet>
      <ContentComponent contentType="video"/>
      <Representation id="{video_id}" bandwidth="{video_bandwidth}" width="{video_width}" height="{video_height}" codecs="{video_codecs}" mimeType="{_media_mime_type(video_format)}">
        <BaseURL>{video_url}</BaseURL>
      </Representation>
    </AdaptationSet>
    <AdaptationSet>
      <ContentComponent contentType="audio"/>
      <Representation id="{audio_id}" bandwidth="{audio_bandwidth}" audioSamplingRate="{audio_rate}" codecs="{audio_codecs}" mimeType="{_media_mime_type(audio_format)}">
        <BaseURL>{audio_url}</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
""".strip()
    return _DASH_DATA_URI_PREFIX + base64.b64encode(raw_xml.encode("utf-8")).decode("ascii")


def _pick_direct_url(info: dict) -> str:
    requested_formats_dash = _build_requested_formats_dash_data_uri(info)
    if requested_formats_dash:
        return requested_formats_dash
    direct_url = info.get("url", "")
    if direct_url:
        return direct_url
    formats = info.get("formats") or []
    muxed_formats = [fmt for fmt in formats if fmt.get("url") and _has_muxed_audio(fmt)]
    if muxed_formats:
        muxed_formats.sort(key=lambda fmt: (fmt.get("height") or 0, fmt.get("tbr") or 0), reverse=True)
        return str(muxed_formats[0]["url"])
    for fmt in formats:
        if fmt.get("url"):
            return str(fmt["url"])
    return ""


@dataclass(frozen=True, slots=True)
class YtdlpResolveResult:
    url: str
    title: str
    thumbnail: str
    description: str
    duration_seconds: int
    headers: dict[str, str]
    subtitles: list[ExternalSubtitleOption]
    qualities: list[VideoQualityOption]
    selected_quality_id: str
    extractor: str


@dataclass(slots=True)
class _YtdlpCacheEntry:
    result: YtdlpResolveResult
    expires_at: float


class YtdlpPlaybackService:
    def __init__(
        self,
        ttl_seconds: float = 300.0,
        now: Callable[[], float] = monotonic,
    ) -> None:
        self._ytdlp_module: object | None = ...  # sentinel: not yet checked
        self._supported_domains: frozenset[str] | None = None
        self._ttl_seconds = float(ttl_seconds)
        self._now = now
        self._cache: dict[str, _YtdlpCacheEntry] = {}

    def _cache_key(self, url: str, max_height: int | None) -> str:
        key = url.strip()
        if max_height and max_height > 0:
            return f"{key}#h={max_height}"
        return f"{key}#h=any"

    def _get_cached_result(self, url: str, max_height: int | None) -> YtdlpResolveResult | None:
        key = self._cache_key(url, max_height)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._cache.pop(key, None)
            return None
        return entry.result

    def _store_cached_result(self, url: str, max_height: int | None, result: YtdlpResolveResult) -> None:
        key = self._cache_key(url, max_height)
        self._cache[key] = _YtdlpCacheEntry(
            result=result,
            expires_at=self._now() + self._ttl_seconds,
        )

    def is_available(self) -> bool:
        module = self._ytdlp_module
        if module is ...:
            try:
                import yt_dlp  # noqa: F401
            except ImportError:
                module = None
            else:
                module = yt_dlp
            self._ytdlp_module = module
        return module is not None

    def can_resolve(self, url: str) -> bool:
        if not self.is_available():
            return False
        candidate = url.strip()
        if not candidate:
            return False
        parsed = urlparse(candidate)
        hostname = (parsed.hostname or "").lower()
        if hostname in _KNOWN_YTDLP_DOMAINS:
            return True
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname in _KNOWN_YTDLP_DOMAINS

    def resolve(
        self,
        url: str,
        log: object = None,
        *,
        max_height: int | None = _DEFAULT_STARTUP_MAX_HEIGHT,
    ) -> YtdlpResolveResult:
        cached = self._get_cached_result(url, max_height)
        if cached is not None:
            if callable(log):
                log(f"yt-dlp 命中缓存 [{cached.extractor}]")
            return cached
        if not self.is_available():
            raise ValueError("yt-dlp 未安装")
        import yt_dlp

        ytdlp_opts: dict = {
            "format": _build_format_selector(max_height),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "extract_flat": False,
            "noplaylist": True,
        }

        if callable(log):
            log("yt-dlp 正在提取视频信息...")
        try:
            with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.GeoRestrictedError:
            raise ValueError("该内容受地区限制")
        except yt_dlp.utils.ExtractorError as exc:
            raise ValueError(f"无法获取视频: {exc}")
        except yt_dlp.utils.DownloadError as exc:
            raise ValueError(f"下载错误: {exc}")
        except Exception as exc:
            raise ValueError(f"yt-dlp 解析失败: {exc}")

        if info is None:
            raise ValueError("yt-dlp 未返回结果")

        direct_url = _pick_direct_url(info)
        if not direct_url:
            raise ValueError("未获取到播放地址")

        http_headers = info.get("http_headers") or {}
        headers = {
            k: v for k, v in http_headers.items()
            if isinstance(k, str) and isinstance(v, str)
        }

        qualities = _build_quality_options(info)
        subtitles = _build_subtitle_options(info)
        selected_quality_id = _resolve_selected_quality_id(info, qualities, max_height)

        if callable(log):
            ext = info.get("extractor", "")
            n_qual = len(qualities)
            n_sub = len(subtitles)
            log(f"yt-dlp 提取完成 [{ext}] 清晰度={n_qual} 字幕={n_sub}")

        result = YtdlpResolveResult(
            url=direct_url,
            title=info.get("title", ""),
            thumbnail=info.get("thumbnail", ""),
            description=info.get("description", ""),
            duration_seconds=int(info.get("duration") or 0),
            headers=headers,
            subtitles=subtitles,
            qualities=qualities,
            selected_quality_id=selected_quality_id,
            extractor=info.get("extractor", ""),
        )
        self._store_cached_result(url, max_height, result)
        return result

    def resolve_for_quality(
        self,
        url: str,
        quality_id: str,
        log: object = None,
    ) -> YtdlpResolveResult:
        max_height = _quality_height_from_id(quality_id)
        return self.resolve(url, log=log, max_height=max_height)

    def resolve_to_play_item(
        self,
        url: str,
        *,
        max_height: int | None = _DEFAULT_STARTUP_MAX_HEIGHT,
    ) -> tuple[VodItem, PlayItem]:
        result = self.resolve(url, max_height=max_height)
        title = result.title or url
        vod = VodItem(
            vod_id=url,
            vod_name=title,
            vod_pic=result.thumbnail,
            vod_content=result.description,
        )
        item = PlayItem(
            title=title,
            url=result.url,
            original_url=url,
            vod_id=url,
            headers=dict(result.headers),
            playback_qualities=list(result.qualities),
            external_subtitles=list(result.subtitles),
            media_title=title,
            duration_seconds=result.duration_seconds,
        )
        if result.selected_quality_id:
            item.selected_playback_quality_id = result.selected_quality_id
        elif item.playback_qualities and not item.selected_playback_quality_id:
            item.selected_playback_quality_id = item.playback_qualities[0].id
        return vod, item


def _build_quality_options(info: dict) -> list[VideoQualityOption]:
    formats = info.get("formats") or []
    best_by_height: dict[int, dict] = {}
    for fmt in formats:
        height = fmt.get("height")
        if not height or height < 360:
            continue
        vcodec = fmt.get("vcodec", "") or ""
        if vcodec == "none":
            continue
        previous = best_by_height.get(height)
        current_tbr = fmt.get("tbr") or 0
        previous_tbr = (previous or {}).get("tbr") or 0
        if previous is None or current_tbr > previous_tbr:
            best_by_height[height] = fmt

    options: list[VideoQualityOption] = []
    for height in sorted(best_by_height.keys(), reverse=True):
        fmt = best_by_height[height]
        tbr = fmt.get("tbr")
        label = f"{height}p"
        if tbr:
            label += f"  {tbr:.0f}kbps"
        options.append(VideoQualityOption(
            id=_quality_id_for_height(height),
            label=label,
            url="",
            width=fmt.get("width") or 0,
            height=height,
            bandwidth=int((tbr or 0) * 1000),
            codecs=fmt.get("vcodec", "") or "",
        ))

    return options


def _resolve_selected_quality_id(
    info: dict,
    qualities: list[VideoQualityOption],
    max_height: int | None,
) -> str:
    selected_height = info.get("height") or 0
    if not selected_height:
        requested_formats = info.get("requested_formats") or []
        requested_heights = [
            int(fmt.get("height") or 0)
            for fmt in requested_formats
            if isinstance(fmt, dict) and fmt.get("height")
        ]
        if requested_heights:
            selected_height = max(requested_heights)
    if selected_height:
        selected_id = _quality_id_for_height(int(selected_height))
        if any(option.id == selected_id for option in qualities):
            return selected_id
    if max_height and max_height > 0:
        for option in qualities:
            if option.height <= max_height:
                return option.id
    if qualities:
        return qualities[0].id
    return ""


_ZH_EN_LANG_PREFIXES = ("en", "zh", "zh-", "zh_Hans", "zh_Hant", "zh-CN", "zh-TW")


def _is_chinese_or_english(lang_code: str) -> bool:
    return lang_code in ("en", "zh") or lang_code.startswith(_ZH_EN_LANG_PREFIXES)


def _build_subtitle_options(info: dict) -> list[ExternalSubtitleOption]:
    result: list[ExternalSubtitleOption] = []
    seen_urls: set[str] = set()

    for source_key in ("subtitles", "automatic_captions"):
        subs_dict = info.get(source_key) or {}
        is_auto = source_key == "automatic_captions"
        for lang_code, subs in subs_dict.items():
            if not _is_chinese_or_english(lang_code):
                continue
            if not isinstance(subs, list):
                continue
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                sub_url = sub.get("url", "")
                if not sub_url or sub_url in seen_urls:
                    continue
                seen_urls.add(sub_url)
                ext = sub.get("ext", "")
                lang_name = _LANG_CODE_NAMES.get(lang_code, lang_code)
                name = lang_name
                if is_auto:
                    name += " (自动生成)"
                name += " [yt-dlp]"
                result.append(ExternalSubtitleOption(
                    name=name,
                    lang=lang_code,
                    url=sub_url,
                    format=ext,
                    source="ytdlp",
                ))

    return result
