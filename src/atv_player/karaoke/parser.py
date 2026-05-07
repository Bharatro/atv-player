from __future__ import annotations

import re
from html import unescape

from atv_player.karaoke.models import KaraokeDocument, KaraokeLine, KaraokeWord

_QQ_LINE_RE = re.compile(r"^\[(?P<start>\d+),(?P<duration>\d+)\](?P<body>.+)$")
_QQ_WORD_RE = re.compile(r"(?P<text>[^()]+)\((?P<start>\d+),(?P<duration>\d+)\)")
_QQ_OFFSET_RE = re.compile(r"^\[offset:(?P<offset>-?\d+)\]$")
_KG_LINE_RE = re.compile(r"^\[(?P<start>\d+),(?P<duration>\d+)\](?P<body>.+)$")
_KG_WORD_RE = re.compile(r"<(?P<offset>\d+),(?P<duration>\d+),(?P<flag>\d+)>(?P<text>[^<]*)")


def parse_raw_karaoke(format_name: str, text: str, translation: str = "") -> KaraokeDocument:
    normalized = str(format_name or "").strip().lower()
    if normalized == "qqmusic-qrc":
        return parse_qqmusic_qrc(text, translation=translation)
    if normalized == "kugou-krc":
        return parse_kugou_krc(text, translation=translation)
    return KaraokeDocument(source_format=normalized)


def parse_qqmusic_qrc(text: str, translation: str = "") -> KaraokeDocument:
    content = unescape(str(text or ""))
    offset_ms = 0
    lines: list[KaraokeLine] = []
    for raw_line in _extract_qrc_lyric_lines(content):
        offset_match = _QQ_OFFSET_RE.match(raw_line)
        if offset_match is not None:
            offset_ms = int(offset_match.group("offset"))
            continue
        match = _QQ_LINE_RE.match(raw_line)
        if match is None:
            continue
        line_start = int(match.group("start")) + offset_ms
        line_duration = int(match.group("duration"))
        words: list[KaraokeWord] = []
        for word_match in _QQ_WORD_RE.finditer(match.group("body")):
            token_text = word_match.group("text")
            if not token_text:
                continue
            word_start = int(word_match.group("start")) + offset_ms
            word_end = word_start + int(word_match.group("duration"))
            words.append(KaraokeWord(text=token_text, start_ms=word_start, end_ms=word_end))
        line_text = "".join(word.text for word in words)
        if line_text:
            lines.append(
                KaraokeLine(
                    start_ms=line_start,
                    end_ms=line_start + line_duration,
                    text=line_text,
                    words=words,
                )
            )
    return KaraokeDocument(source_format="qqmusic-qrc", offset_ms=offset_ms, lines=lines)


def parse_kugou_krc(text: str, translation: str = "") -> KaraokeDocument:
    lines: list[KaraokeLine] = []
    for raw_line in str(text or "").splitlines():
        match = _KG_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        line_start = int(match.group("start"))
        line_duration = int(match.group("duration"))
        words: list[KaraokeWord] = []
        for word_match in _KG_WORD_RE.finditer(match.group("body")):
            token_text = word_match.group("text")
            if token_text == "":
                continue
            word_start = line_start + int(word_match.group("offset"))
            word_end = word_start + int(word_match.group("duration"))
            words.append(KaraokeWord(text=token_text, start_ms=word_start, end_ms=word_end))
        line_text = "".join(word.text for word in words)
        if line_text:
            lines.append(
                KaraokeLine(
                    start_ms=line_start,
                    end_ms=line_start + line_duration,
                    text=line_text,
                    words=words,
                )
            )
    return KaraokeDocument(source_format="kugou-krc", lines=lines)


def _extract_qrc_lyric_lines(content: str) -> list[str]:
    match = re.search(r'LyricContent="(?P<body>.*)"\s*/>', content, re.S)
    if match is None:
        return []
    lyric_body = match.group("body").replace("\\n", "\n")
    return [line.strip() for line in lyric_body.splitlines() if line.strip()]
