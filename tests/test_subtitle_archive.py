import gzip
import io
import zipfile

import pytest

from atv_player.subtitles.archive import (
    decode_subtitle_bytes,
    detect_archive,
    extract_subtitle,
    sniff_suffix,
)
from atv_player.subtitles.errors import (
    SubtitleArchiveError,
    SubtitleArchiveUnsupportedError,
)

SRT_TEXT = "1\n00:00:01,000 --> 00:00:02,000\n你好世界\n"


def _zip_bytes(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_detect_archive_recognizes_formats() -> None:
    assert detect_archive(_zip_bytes({"a.srt": SRT_TEXT})) == "zip"
    assert detect_archive(gzip.compress(SRT_TEXT.encode())) == "gzip"
    assert detect_archive(b"Rar!\x1a\x07\x00rest") == "rar"
    assert detect_archive(b"plain text") == ""


def test_decode_handles_utf8_gbk_and_big5() -> None:
    assert decode_subtitle_bytes("你好世界".encode()) == "你好世界"
    assert decode_subtitle_bytes("你好世界".encode("gb18030")) == "你好世界"
    assert decode_subtitle_bytes("繁體中文字幕".encode("big5")) == "繁體中文字幕"


def test_decode_empty_returns_empty_string() -> None:
    assert decode_subtitle_bytes(b"") == ""


def test_extract_plain_text_sniffs_suffix() -> None:
    content = extract_subtitle(SRT_TEXT.encode())
    assert content.suffix == ".srt"
    assert "你好世界" in content.text

    vtt = extract_subtitle(b"WEBVTT\n\n00:01.000 --> 00:02.000\nhi\n")
    assert vtt.suffix == ".vtt"

    ass = extract_subtitle(b"[Script Info]\nTitle: x\n")
    assert ass.suffix == ".ass"


def test_extract_from_zip_prefers_ass_then_simplified() -> None:
    data = _zip_bytes(
        {
            "movie.eng.srt": "english",
            "movie.chs.srt": "简体",
            "movie.chs.ass": "[Script Info]\n简体样式",
        }
    )
    content = extract_subtitle(data)
    assert content.name == "movie.chs.ass"
    assert content.suffix == ".ass"


def test_extract_from_zip_prefers_simplified_over_traditional() -> None:
    data = _zip_bytes({"movie.cht.srt": "繁體", "movie.chs.srt": "简体"})
    assert extract_subtitle(data).name == "movie.chs.srt"


def test_extract_from_zip_skips_macos_junk_entries() -> None:
    data = _zip_bytes({"__MACOSX/._movie.srt": "junk", "movie.srt": SRT_TEXT})
    assert extract_subtitle(data).name == "movie.srt"


def test_extract_from_zip_without_subtitle_member_raises() -> None:
    with pytest.raises(SubtitleArchiveError):
        extract_subtitle(_zip_bytes({"readme.txt": "nothing here"}))


def test_extract_gzip_unwraps_then_sniffs() -> None:
    content = extract_subtitle(gzip.compress(SRT_TEXT.encode()))
    assert content.suffix == ".srt"
    assert "你好世界" in content.text


def test_rar_archive_reports_unsupported() -> None:
    with pytest.raises(SubtitleArchiveUnsupportedError):
        extract_subtitle(b"Rar!\x1a\x07\x00payload")


def test_empty_payload_raises() -> None:
    with pytest.raises(SubtitleArchiveError):
        extract_subtitle(b"")


def test_sniff_suffix_defaults_to_srt() -> None:
    assert sniff_suffix("1\n00:00:01,000 --> 00:00:02,000\nhi") == ".srt"
