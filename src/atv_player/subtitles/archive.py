"""字幕下载内容的解包与编码处理。

字幕站返回的可能是裸字幕文本，也可能是 zip/gzip 压缩包。标准库解不开 rar/7z，
遇到这两种只能明确报错（SubDL 的 ``unpack=1`` 与 ASSRT 的 ``filelist`` 都能返回
已解包的直链，是绕开该限制的主要手段）。
"""

from __future__ import annotations

import gzip
import io
import logging
import zipfile

from atv_player.subtitles.errors import (
    SubtitleArchiveError,
    SubtitleArchiveUnsupportedError,
)
from atv_player.subtitles.languages import language_rank, normalize_language
from atv_player.subtitles.models import SubtitleContent

logger = logging.getLogger(__name__)

SUBTITLE_SUFFIXES = (".ass", ".ssa", ".srt", ".vtt", ".sub")

# 越小越优先。ass/ssa 保留样式，srt 兼容性最好，sub 多为 VobSub 二进制，垫底。
_FORMAT_RANKS = {".ass": 0, ".ssa": 1, ".srt": 2, ".vtt": 3, ".sub": 4}

_ARCHIVE_MAGIC = (
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
)

_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5", "cp950", "shift_jis")


def detect_archive(data: bytes) -> str:
    for magic, kind in _ARCHIVE_MAGIC:
        if data.startswith(magic):
            return kind
    return ""


def _cjk_score(text: str) -> int:
    """粗略衡量解码结果的合理程度。

    gb18030 几乎能"成功"解码任意字节，所以不能只看是否抛异常。这里给常见
    中日韩字符和 ASCII 加分，给私用区/替换符等乱码特征减分。
    """
    score = 0
    for char in text:
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F:
            score += 2
        elif char.isascii() and (char.isprintable() or char in "\r\n\t"):
            score += 1
        elif code == 0xFFFD or 0xE000 <= code <= 0xF8FF:
            score -= 8
        elif not char.isprintable() and char not in "\r\n\t":
            score -= 4
    return score


def decode_subtitle_bytes(data: bytes) -> str:
    """按常见字幕编码嗅探解码，挑合理度最高的结果。"""
    if not data:
        return ""
    best_text = ""
    best_score = None
    for encoding in _ENCODINGS:
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        # UTF-8 严格解码成功基本可以确定就是它，不必再比。
        if encoding in ("utf-8-sig", "utf-8"):
            return text
        score = _cjk_score(text)
        if best_score is None or score > best_score:
            best_score = score
            best_text = text
    if best_score is not None:
        return best_text
    return data.decode("utf-8", errors="replace")


def _suffix_of(name: str) -> str:
    lowered = name.casefold()
    for suffix in SUBTITLE_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return ""


def _member_sort_key(name: str) -> tuple[int, int, int]:
    suffix = _suffix_of(name)
    language = normalize_language(name)
    return (
        _FORMAT_RANKS.get(suffix, len(_FORMAT_RANKS)),
        language_rank(language),
        len(name),
    )


def _is_junk_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("__MACOSX/") or "/__MACOSX/" in normalized:
        return True
    return normalized.rsplit("/", 1)[-1].startswith("._")


def _extract_from_zip(data: bytes) -> SubtitleContent:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        candidates = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and _suffix_of(info.filename)
            and not _is_junk_member(info.filename)
        ]
        if not candidates:
            raise SubtitleArchiveError("压缩包内没有可用的字幕文件")
        candidates.sort(key=lambda info: _member_sort_key(info.filename))
        chosen = candidates[0]
        payload = archive.read(chosen)
    name = chosen.filename.replace("\\", "/").rsplit("/", 1)[-1]
    return SubtitleContent(
        text=decode_subtitle_bytes(payload),
        suffix=_suffix_of(name) or ".srt",
        name=name,
    )


def extract_subtitle(data: bytes, *, name_hint: str = "") -> SubtitleContent:
    """把下载到的字节解成字幕正文。

    ``name_hint`` 是站点给出的文件名，用于在内容本身没有格式特征时定后缀。
    """
    if not data:
        raise SubtitleArchiveError("字幕内容为空")
    kind = detect_archive(data)
    if kind == "zip":
        return _extract_from_zip(data)
    if kind == "gzip":
        try:
            payload = gzip.decompress(data)
        except OSError as exc:
            raise SubtitleArchiveError(f"gzip 解压失败: {exc}") from exc
        return extract_subtitle(payload, name_hint=name_hint)
    if kind in ("rar", "7z"):
        raise SubtitleArchiveUnsupportedError(
            f"暂不支持 {kind} 压缩包，请换一条字幕"
        )
    text = decode_subtitle_bytes(data)
    return SubtitleContent(
        text=text,
        suffix=_suffix_of(name_hint) or sniff_suffix(text),
        name=name_hint,
    )


def sniff_suffix(text: str) -> str:
    head = text.lstrip()[:400].casefold()
    if head.startswith("webvtt"):
        return ".vtt"
    if "[script info]" in head or "[v4+ styles]" in head:
        return ".ass"
    return ".srt"


def subtitle_name_sort_key(name: str) -> tuple[int, int, int]:
    """按格式与语言给字幕文件名排序（越小越优先）。

    供 provider 在站点已返回"包内文件列表"时挑最合适的一条复用
    （SubDL 的 ``unpack_files`` 与 ASSRT 的 ``filelist``）。
    """
    return _member_sort_key(name)


def suffix_of(name: str) -> str:
    return _suffix_of(name)
