"""下载后的字幕落盘。

写到应用缓存目录，再把绝对路径交给播放器现有的外挂字幕通道
（``_fetch_external_subtitle_text`` 本来就支持绝对本地路径）。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from atv_player.paths import app_cache_dir
from atv_player.subtitles.models import SubtitleContent

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\s]+')
_MAX_STEM_LENGTH = 60


def subtitle_cache_dir() -> Path:
    path = app_cache_dir() / "subtitles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_stem(text: str) -> str:
    stem = _UNSAFE_CHARS.sub("_", str(text or "").strip()).strip("_")
    return stem[:_MAX_STEM_LENGTH] or "subtitle"


def save_subtitle_file(content: SubtitleContent, *, title: str = "") -> Path:
    """把字幕正文写入缓存目录，返回绝对路径。

    文件名带内容哈希，同一条字幕重复下载会命中同一个文件，不会堆积。
    """
    digest = hashlib.sha256(content.text.encode("utf-8", "replace")).hexdigest()[:12]
    stem = _safe_stem(title or content.name)
    suffix = content.suffix if content.suffix.startswith(".") else f".{content.suffix}"
    path = subtitle_cache_dir() / f"{stem}-{digest}{suffix or '.srt'}"
    if not path.exists():
        path.write_text(content.text, encoding="utf-8")
    return path
