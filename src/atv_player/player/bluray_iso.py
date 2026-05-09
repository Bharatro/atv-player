from __future__ import annotations

import io
import re
from types import SimpleNamespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:
    import pycdlib


_BLURAY_INDEX_PATH = "/BDMV/INDEX.BDMV"
_BLURAY_STREAM_RE = re.compile(r"^/BDMV/STREAM/[^/]+\.M2TS$")
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+)$", re.IGNORECASE)
_RANGE_UNSUPPORTED_MESSAGE = "远程 ISO 服务不支持按范围读取"
_MISSING_PVD_MESSAGE = "Valid ISO9660 filesystems must have at least one PVD"


@dataclass(frozen=True, slots=True)
class BluRayIsoStream:
    path: str
    size: int


def is_remote_iso_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return (parsed.path or "").lower().endswith(".iso")


def pick_main_feature_stream(streams: list[BluRayIsoStream]) -> BluRayIsoStream:
    if not streams:
        raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
    return max(streams, key=lambda item: (item.size, item.path))


def _normalize_iso_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    cleaned = re.sub(r"/+", "/", cleaned)
    return cleaned.upper()


def _load_pycdlib() -> Any:
    import pycdlib

    return pycdlib


def _safe_close_iso(iso: Any) -> None:
    try:
        iso.close()
    except Exception:
        pass


def _physical_block_count(reader: RemoteRangeReader, logical_block_size: int) -> int:
    total_size = reader._ensure_size()
    return max(1, (total_size + logical_block_size - 1) // logical_block_size)


def _open_pycdlib_iso(reader: RemoteRangeReader) -> Any:
    pycdlib = _load_pycdlib()
    iso = pycdlib.PyCdlib()
    invalid_iso = getattr(getattr(pycdlib, "pycdlibexception", None), "PyCdlibInvalidISO", None)
    try:
        iso.open_fp(reader)
        return iso
    except ValueError:
        _safe_close_iso(iso)
        raise
    except Exception as exc:
        if invalid_iso is None or not isinstance(exc, invalid_iso):
            _safe_close_iso(iso)
            raise ValueError(f"ISO 解析失败: {exc}") from exc
        if _MISSING_PVD_MESSAGE not in str(exc) or not getattr(iso, "_has_udf", False):
            _safe_close_iso(iso)
            raise ValueError(f"ISO 解析失败: {exc}") from exc
        try:
            logical_block_size = int(getattr(iso, "logical_block_size", 2048) or 2048)
            iso.pvd = SimpleNamespace(space_size=_physical_block_count(reader, logical_block_size))
            iso._parse_udf_descriptors()
            iso._walk_udf_directories({})
            iso._initialized = True
            return iso
        except Exception as udf_exc:
            _safe_close_iso(iso)
            raise ValueError(f"ISO 解析失败: {udf_exc}") from udf_exc


def _parse_total_size_from_response(response: httpx.Response, *, expected_start: int) -> int:
    if int(response.status_code) != 206:
        raise ValueError(_RANGE_UNSUPPORTED_MESSAGE)
    content_range = response.headers.get("Content-Range", "").strip()
    if content_range:
        match = _CONTENT_RANGE_RE.match(content_range)
        if match is None:
            raise ValueError("远程 ISO 返回了无法识别的 Content-Range")
        start = int(match.group(1))
        total = int(match.group(3))
        if start != expected_start:
            raise ValueError("远程 ISO 返回了不匹配的范围数据")
        return total
    raise ValueError("远程 ISO 未返回可用的范围大小信息")


class RemoteRangeReader(io.RawIOBase):
    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        *,
        get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        super().__init__()
        self._url = url
        self._headers = dict(headers)
        self._get = get
        self._position = 0
        self._size: int | None = None

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        size = self._ensure_size()
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self._position + offset
        elif whence == io.SEEK_END:
            target = size + offset
        else:
            raise ValueError("unsupported whence")
        if target < 0:
            raise ValueError("negative seek position")
        self._position = target
        return self._position

    def readinto(self, buffer: bytearray | memoryview) -> int:
        view = memoryview(buffer)
        if not view:
            return 0
        size = self._ensure_size()
        if self._position >= size:
            return 0
        end = min(self._position + len(view), size) - 1
        headers = dict(self._headers)
        headers["Range"] = f"bytes={self._position}-{end}"
        response = self._get(
            self._url,
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        if int(response.status_code) != 206:
            raise ValueError(_RANGE_UNSUPPORTED_MESSAGE)
        payload = bytes(response.content)
        length = len(payload)
        view[:length] = payload
        self._position += length
        return length

    def _ensure_size(self) -> int:
        if self._size is not None:
            return self._size
        headers = dict(self._headers)
        headers["Range"] = "bytes=0-0"
        response = self._get(
            self._url,
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        self._size = _parse_total_size_from_response(response, expected_start=0)
        return self._size


def _walk_iso_paths(iso: Any) -> list[str]:
    paths: list[str] = []
    for current_path, directories, files in iso.walk(udf_path="/"):
        normalized_current = _normalize_iso_path(current_path)
        paths.append(normalized_current)
        for directory in directories:
            paths.append(_normalize_iso_path(f"{normalized_current}/{directory}"))
        for filename in files:
            paths.append(_normalize_iso_path(f"{normalized_current}/{filename}"))
    return sorted(set(paths))


def _stream_size_from_record(record: Any) -> int:
    for attr in ("info_len", "data_length", "file_length"):
        value = getattr(record, attr, None)
        if isinstance(value, int):
            return value
    try:
        return int(record.get_data_length())
    except Exception:
        return 0


def list_iso_entries(
    url: str,
    headers: dict[str, str],
    *,
    get: Callable[..., httpx.Response] = httpx.get,
) -> list[str]:
    reader = RemoteRangeReader(url, headers, get=get)
    iso = _open_pycdlib_iso(reader)
    try:
        return _walk_iso_paths(iso)
    finally:
        _safe_close_iso(iso)


def stat_iso_streams(
    url: str,
    headers: dict[str, str],
    *,
    get: Callable[..., httpx.Response] = httpx.get,
) -> list[BluRayIsoStream]:
    reader = RemoteRangeReader(url, headers, get=get)
    iso = _open_pycdlib_iso(reader)
    try:
        streams: list[BluRayIsoStream] = []
        for path in _walk_iso_paths(iso):
            if not _BLURAY_STREAM_RE.match(path):
                continue
            record = iso.get_record(udf_path=path)
            streams.append(BluRayIsoStream(path=path, size=_stream_size_from_record(record)))
        return streams
    finally:
        _safe_close_iso(iso)


def read_iso_stream_range(
    url: str,
    headers: dict[str, str],
    stream_path: str,
    start: int,
    end: int | None,
    *,
    get: Callable[..., httpx.Response] = httpx.get,
) -> tuple[bytes, int]:
    normalized_path = _normalize_iso_path(stream_path)
    reader = RemoteRangeReader(url, headers, get=get)
    iso = _open_pycdlib_iso(reader)
    try:
        record = iso.get_record(udf_path=normalized_path)
        total_size = _stream_size_from_record(record)
        if total_size <= 0:
            raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
        if start < 0:
            raise ValueError("invalid range start")
        if start >= total_size:
            return b"", total_size
        inclusive_end = total_size - 1 if end is None else min(end, total_size - 1)
        if inclusive_end < start:
            return b"", total_size
        length = inclusive_end - start + 1
        with iso.open_file_from_iso(udf_path=normalized_path) as iso_file:
            iso_file.seek(start)
            payload = iso_file.read(length)
        return bytes(payload), total_size
    finally:
        _safe_close_iso(iso)


class BlurayIsoInspector:
    def __init__(
        self,
        list_entries: Callable[[str, dict[str, str]], list[str]] = list_iso_entries,
        stat_streams: Callable[[str, dict[str, str]], list[BluRayIsoStream]] = stat_iso_streams,
    ) -> None:
        self._list_entries = list_entries
        self._stat_streams = stat_streams

    def inspect(self, url: str, headers: dict[str, str]) -> BluRayIsoStream:
        entries = [_normalize_iso_path(entry) for entry in self._list_entries(url, headers)]
        if _BLURAY_INDEX_PATH not in entries:
            raise ValueError("远程 ISO 不是受支持的 Blu-ray 目录结构")
        streams = self._stat_streams(url, headers)
        normalized_streams = [
            BluRayIsoStream(path=_normalize_iso_path(stream.path), size=int(stream.size))
            for stream in streams
            if _BLURAY_STREAM_RE.match(_normalize_iso_path(stream.path))
        ]
        if not normalized_streams:
            raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
        return pick_main_feature_stream(normalized_streams)
