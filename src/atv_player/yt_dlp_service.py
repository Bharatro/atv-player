from __future__ import annotations

import logging
from dataclasses import dataclass
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
    extractor: str


class YtdlpPlaybackService:
    def __init__(self) -> None:
        self._ytdlp_module: object | None = ...  # sentinel: not yet checked
        self._supported_domains: frozenset[str] | None = None

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

    def resolve(self, url: str, log: object = None) -> YtdlpResolveResult:
        if not self.is_available():
            raise ValueError("yt-dlp 未安装")
        import yt_dlp

        ytdlp_opts: dict = {
            "format": "bestvideo+bestaudio/best",
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

        direct_url = info.get("url", "")
        if not direct_url:
            formats = info.get("formats") or []
            for fmt in formats:
                if fmt.get("url"):
                    direct_url = fmt["url"]
                    break
        if not direct_url:
            raise ValueError("未获取到播放地址")

        http_headers = info.get("http_headers") or {}
        headers = {
            k: v for k, v in http_headers.items()
            if isinstance(k, str) and isinstance(v, str)
        }

        qualities = _build_quality_options(info)
        subtitles = _build_subtitle_options(info)

        if callable(log):
            ext = info.get("extractor", "")
            n_qual = len(qualities)
            n_sub = len(subtitles)
            log(f"yt-dlp 提取完成 [{ext}] 清晰度={n_qual} 字幕={n_sub}")

        return YtdlpResolveResult(
            url=direct_url,
            title=info.get("title", ""),
            thumbnail=info.get("thumbnail", ""),
            description=info.get("description", ""),
            duration_seconds=int(info.get("duration") or 0),
            headers=headers,
            subtitles=subtitles,
            qualities=qualities,
            extractor=info.get("extractor", ""),
        )

    def resolve_to_play_item(self, url: str) -> tuple[VodItem, PlayItem]:
        result = self.resolve(url)
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
        if item.playback_qualities and not item.selected_playback_quality_id:
            item.selected_playback_quality_id = item.playback_qualities[0].id
        return vod, item


def _build_quality_options(info: dict) -> list[VideoQualityOption]:
    formats = info.get("formats") or []
    seen: set[str] = set()
    options: list[VideoQualityOption] = []
    for fmt in formats:
        height = fmt.get("height")
        if not height or height < 360:
            continue
        fmt_url = fmt.get("url")
        if not fmt_url:
            continue
        vcodec = fmt.get("vcodec", "") or ""
        if vcodec == "none":
            continue
        format_id = fmt.get("format_id", "")
        quality_id = f"ytdlp_{format_id}"
        if quality_id in seen:
            continue
        seen.add(quality_id)

        acodec = fmt.get("acodec", "") or ""
        label = f"{height}p"
        if acodec and acodec != "none":
            label += " ✓"
        tbr = fmt.get("tbr")
        if tbr:
            label += f"  {tbr:.0f}kbps"

        options.append(VideoQualityOption(
            id=quality_id,
            label=label,
            url=fmt_url,
            width=fmt.get("width") or 0,
            height=height,
            bandwidth=int((tbr or 0) * 1000),
            codecs=vcodec,
        ))

    options.sort(key=lambda q: q.height, reverse=True)
    return options


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
