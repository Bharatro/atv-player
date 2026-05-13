from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
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


def _pick_requested_stream_pair(info: dict) -> tuple[str, str]:
    requested_formats = info.get("requested_formats") or []
    if not isinstance(requested_formats, list):
        return "", ""
    video_formats = [
        fmt for fmt in requested_formats
        if isinstance(fmt, dict) and fmt.get("url") and (fmt.get("vcodec", "") or "") != "none"
    ]
    audio_formats = [
        fmt for fmt in requested_formats
        if isinstance(fmt, dict) and fmt.get("url") and (fmt.get("acodec", "") or "") != "none"
    ]
    if not video_formats or not audio_formats:
        return "", ""
    return str(video_formats[0]["url"]), str(audio_formats[0]["url"])


def _video_codec_rank(vcodec: object) -> int:
    normalized = str(vcodec or "").lower()
    if normalized.startswith(("avc1", "h264")):
        return 0
    if normalized.startswith(("vp9", "vp09")):
        return 1
    if normalized.startswith(("av01", "av1")):
        return 2
    if normalized.startswith(("hev1", "hvc1", "hevc")):
        return 3
    return 4


def _audio_codec_rank(acodec: object) -> int:
    normalized = str(acodec or "").lower()
    if normalized.startswith("opus"):
        return 0
    if normalized.startswith(("mp4a", "aac")):
        return 1
    return 2


def _preferred_video_formats(info: dict, max_height: int | None) -> list[dict]:
    formats = info.get("formats") or []
    candidates = [
        fmt for fmt in formats
        if isinstance(fmt, dict)
        and fmt.get("url")
        and (fmt.get("vcodec", "") or "") != "none"
        and int(fmt.get("height") or 0) > 0
        and (max_height is None or int(fmt.get("height") or 0) <= max_height)
    ]
    if not candidates:
        return []
    best_height = max(int(fmt.get("height") or 0) for fmt in candidates)
    filtered = [fmt for fmt in candidates if int(fmt.get("height") or 0) == best_height]
    return sorted(
        filtered,
        key=lambda fmt: (
            0 if _has_muxed_audio(fmt) else 1,
            _video_codec_rank(fmt.get("vcodec")),
            -int(fmt.get("fps") or 0),
            -int(fmt.get("tbr") or 0),
        ),
    )


def _preferred_audio_formats(info: dict) -> list[dict]:
    formats = info.get("formats") or []
    candidates = [
        fmt for fmt in formats
        if isinstance(fmt, dict)
        and fmt.get("url")
        and (fmt.get("acodec", "") or "") != "none"
        and (fmt.get("vcodec", "") or "") == "none"
    ]
    return sorted(
        candidates,
        key=lambda fmt: (
            _audio_codec_rank(fmt.get("acodec")),
            -int(fmt.get("tbr") or 0),
        ),
    )


def _select_stream_pair(info: dict, max_height: int | None) -> tuple[dict | None, dict | None]:
    preferred_video_formats = _preferred_video_formats(info, max_height)
    if preferred_video_formats:
        selected_video = preferred_video_formats[0]
        if _has_muxed_audio(selected_video):
            return selected_video, None
        preferred_audio_formats = _preferred_audio_formats(info)
        if preferred_audio_formats:
            return selected_video, preferred_audio_formats[0]
    requested_video_url, requested_audio_url = _pick_requested_stream_pair(info)
    if requested_video_url:
        requested_formats = info.get("requested_formats") or []
        selected_video = next(
            (
                fmt for fmt in requested_formats
                if isinstance(fmt, dict) and fmt.get("url") == requested_video_url
            ),
            None,
        )
        selected_audio = next(
            (
                fmt for fmt in requested_formats
                if isinstance(fmt, dict) and fmt.get("url") == requested_audio_url
            ),
            None,
        )
        return selected_video, selected_audio
    return None, None


def _pick_direct_url(info: dict, max_height: int | None) -> str:
    direct_url = info.get("url", "")
    requested_formats = info.get("requested_formats") or []
    if direct_url and not requested_formats:
        return direct_url
    selected_video, _selected_audio = _select_stream_pair(info, max_height)
    if selected_video is not None and selected_video.get("url"):
        return str(selected_video["url"])
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


def _summarize_data_uri(url: str) -> str:
    if url.startswith(_DASH_DATA_URI_PREFIX):
        return f"{_DASH_DATA_URI_PREFIX}..."
    return url


def _format_mime_type(fmt: dict, *, content_type: str) -> str:
    mime_type = str(fmt.get("mime_type") or "").strip()
    if mime_type:
        return mime_type.partition(";")[0]
    ext = str(fmt.get("ext") or "").strip().lower()
    if content_type == "video":
        if ext == "webm":
            return "video/webm"
        return "video/mp4"
    if ext == "webm":
        return "audio/webm"
    return "audio/mp4"


def _format_codecs(fmt: dict, *, content_type: str) -> str:
    if content_type == "video":
        return str(fmt.get("vcodec") or "").strip()
    return str(fmt.get("acodec") or "").strip()


def _dash_representation_xml(fmt: dict, *, content_type: str) -> str:
    attrs: list[tuple[str, str]] = [
        ("id", str(fmt.get("format_id") or "").strip() or content_type),
        ("mimeType", _format_mime_type(fmt, content_type=content_type)),
    ]
    codecs = _format_codecs(fmt, content_type=content_type)
    if codecs and codecs != "none":
        attrs.append(("codecs", codecs))
    tbr = int(float(fmt.get("tbr") or 0) * 1000)
    if tbr > 0:
        attrs.append(("bandwidth", str(tbr)))
    if content_type == "video":
        width = int(fmt.get("width") or 0)
        height = int(fmt.get("height") or 0)
        if width > 0:
            attrs.append(("width", str(width)))
        if height > 0:
            attrs.append(("height", str(height)))
    attributes = " ".join(f'{key}="{value}"' for key, value in attrs)
    return (
        f"<Representation {attributes}>"
        f"<BaseURL>{str(fmt.get('url') or '')}</BaseURL>"
        "</Representation>"
    )


def _build_dash_manifest_data_uri(
    video_format: dict,
    audio_format: dict,
    *,
    duration_seconds: int,
) -> str:
    duration_attr = ""
    if duration_seconds > 0:
        duration_attr = f' mediaPresentationDuration="PT{duration_seconds}S"'
    manifest = (
        f'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static"{duration_attr}>'
        "<Period>"
        '<AdaptationSet contentType="video">'
        f"{_dash_representation_xml(video_format, content_type='video')}"
        "</AdaptationSet>"
        '<AdaptationSet contentType="audio">'
        f"{_dash_representation_xml(audio_format, content_type='audio')}"
        "</AdaptationSet>"
        "</Period>"
        "</MPD>"
    )
    encoded = base64.b64encode(manifest.encode("utf-8")).decode("ascii")
    return f"{_DASH_DATA_URI_PREFIX}{encoded}"


def _summarize_media_url(url: str) -> str:
    summarized_data_uri = _summarize_data_uri(url)
    if summarized_data_uri != url:
        return summarized_data_uri
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url
    path = parsed.path or "/"
    if len(path) > 96:
        path = f"...{path[-96:]}"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


@dataclass(frozen=True, slots=True)
class YtdlpResolveResult:
    url: str
    audio_url: str
    video_format_id: str
    audio_format_id: str
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
        logger.info("yt-dlp resolve start url=%s max_height=%s", url, max_height)
        cached = self._get_cached_result(url, max_height)
        if cached is not None:
            logger.info(
                "yt-dlp resolve cache-hit url=%s max_height=%s selected_quality=%s video=%s audio=%s",
                url,
                max_height,
                cached.selected_quality_id,
                _summarize_media_url(cached.url),
                _summarize_media_url(cached.audio_url),
            )
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
        started_at = monotonic()
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

        requested_formats = info.get("requested_formats") or []
        if requested_formats or not info.get("url"):
            selected_video, selected_audio = _select_stream_pair(info, max_height)
        else:
            selected_video, selected_audio = None, None
        direct_url = _pick_direct_url(info, max_height)
        if not direct_url:
            raise ValueError("未获取到播放地址")
        playback_url = direct_url
        requested_audio_url = ""
        if selected_audio is not None and selected_audio.get("url"):
            if selected_video is None or not selected_video.get("url"):
                raise ValueError("未获取到视频流")
            playback_url = _build_dash_manifest_data_uri(
                selected_video,
                selected_audio,
                duration_seconds=int(info.get("duration") or 0),
            )
        elif selected_video is not None and _has_muxed_audio(selected_video):
            requested_audio_url = ""

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
            url=playback_url,
            audio_url=requested_audio_url,
            video_format_id=str((selected_video or {}).get("format_id") or ""),
            audio_format_id=str((selected_audio or {}).get("format_id") or ""),
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
        requested_formats = info.get("requested_formats") or []
        requested_format_ids = [
            str(fmt.get("format_id") or "")
            for fmt in requested_formats
            if isinstance(fmt, dict) and fmt.get("format_id")
        ]
        logger.info(
            "yt-dlp resolve done url=%s max_height=%s elapsed=%.3fs selected_quality=%s height=%s format_id=%s requested_formats=%s video=%s audio=%s",
            url,
            max_height,
            monotonic() - started_at,
            selected_quality_id,
            info.get("height") or 0,
            result.video_format_id or info.get("format_id") or "",
            requested_format_ids,
            _summarize_media_url(result.url),
            _summarize_media_url(result.audio_url),
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
            audio_url=result.audio_url,
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
