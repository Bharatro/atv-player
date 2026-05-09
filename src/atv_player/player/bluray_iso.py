from __future__ import annotations

from collections import OrderedDict
import io
import re
from threading import Lock
from types import SimpleNamespace
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:
    import pycdlib


_BLURAY_INDEX_PATH = "/BDMV/INDEX.BDMV"
_BLURAY_STREAM_RE = re.compile(r"^/BDMV/STREAM/[^/]+\.M2TS$")
_BLURAY_PLAYLIST_RE = re.compile(r"^/BDMV/PLAYLIST/[^/]+\.MPLS$")
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+)$", re.IGNORECASE)
_RANGE_UNSUPPORTED_MESSAGE = "远程 ISO 服务不支持按范围读取"
_MISSING_PVD_MESSAGE = "Valid ISO9660 filesystems must have at least one PVD"
_UDF_FILE_SET_TAG_MESSAGE = "UDF File Set Tag identifier not 256"


@dataclass(frozen=True, slots=True)
class BluRayIsoStream:
    path: str
    size: int


@dataclass(frozen=True, slots=True)
class IsoPlaybackSegment:
    stream_path: str
    stream_size: int
    duration_seconds: float
    source: object | None = None


@dataclass(frozen=True, slots=True)
class IsoPlaybackPlan:
    stream: BluRayIsoStream
    source: object | None = None
    playlist_segments: tuple[IsoPlaybackSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class _MplsPlayItem:
    clip_id: str
    stream_path: str
    in_time: int
    out_time: int
    duration: int


@dataclass(frozen=True, slots=True)
class _ParsedMplsPlaylist:
    path: str
    play_items: tuple[_MplsPlayItem, ...]
    duration: int


@dataclass(frozen=True, slots=True)
class _ClpiEntryPoint:
    time_45k: int
    byte_offset: int


@dataclass(frozen=True, slots=True)
class _ParsedClpi:
    clip_id: str
    entry_points: tuple[_ClpiEntryPoint, ...]


@dataclass(frozen=True, slots=True)
class _UdfMetadataPartitionMap:
    part_num: int
    metadata_file_location: int


@dataclass(frozen=True, slots=True)
class _UdfPartitionExtent:
    logical_start_block: int
    block_count: int
    physical_start_block: int


@dataclass(frozen=True, slots=True)
class _UdfPartitionResolver:
    part_ref_num: int
    physical_partition_start: int
    extents: tuple[_UdfPartitionExtent, ...]


@dataclass(frozen=True, slots=True)
class _UdfEntryRef:
    record: Any
    part_ref_num: int


@dataclass(frozen=True, slots=True)
class _CachedIsoSegment:
    logical_offset: int
    length: int
    physical_start: int


@dataclass(frozen=True, slots=True)
class _CachedIsoStreamSource:
    size: int
    segments: tuple[_CachedIsoSegment, ...]


@dataclass(slots=True)
class _RemoteRangeWindowCache:
    window_size: int
    startup_window_size: int
    startup_request_threshold: int
    max_windows: int
    windows: OrderedDict[int, bytes] = field(default_factory=OrderedDict)
    lock: Lock = field(default_factory=Lock)


@dataclass(frozen=True, slots=True)
class _RemoteUdfIso:
    reader: RemoteRangeReader
    logical_block_size: int
    main_descs: Any
    file_set: Any
    partition_resolvers: tuple[_UdfPartitionResolver | None, ...]


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


def _load_pycdlib_udf() -> Any:
    from pycdlib import udf

    return udf


def _safe_close_iso(iso: Any) -> None:
    try:
        iso.close()
    except Exception:
        pass


def _physical_block_count(reader: RemoteRangeReader, logical_block_size: int) -> int:
    total_size = reader._ensure_size()
    return max(1, (total_size + logical_block_size - 1) // logical_block_size)


def _ceil_blocks(length: int, logical_block_size: int) -> int:
    return max(1, (length + logical_block_size - 1) // logical_block_size)


def _read_reader_bytes(reader: RemoteRangeReader, start: int, length: int) -> bytes:
    reader.seek(start)
    payload = reader.read(length)
    return bytes(payload or b"")


def _fetch_remote_range_bytes(
    url: str,
    headers: dict[str, str],
    start: int,
    end: int,
    *,
    get: Callable[..., httpx.Response],
) -> bytes:
    request_headers = dict(headers)
    request_headers["Range"] = f"bytes={start}-{end}"
    response = get(
        url,
        headers=request_headers,
        timeout=15.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    if int(getattr(response, "status_code", 200) or 200) != 206:
        raise ValueError(_RANGE_UNSUPPORTED_MESSAGE)
    payload = bytes(getattr(response, "content", b"") or b"")
    content_range = response.headers.get("Content-Range", "").strip()
    if content_range:
        match = _CONTENT_RANGE_RE.match(content_range)
        if match is None:
            raise ValueError("远程 ISO 返回了无法识别的 Content-Range")
        actual_start = int(match.group(1))
        if actual_start != start:
            raise ValueError("远程 ISO 返回了不匹配的范围数据")
    return payload


def create_iso_stream_range_cache(
    *,
    window_size: int = 32 * 1024 * 1024,
    startup_window_size: int = 1024 * 1024,
    startup_request_threshold: int = 512 * 1024,
    max_windows: int = 3,
) -> object:
    normalized_window_size = max(1, int(window_size))
    return _RemoteRangeWindowCache(
        window_size=normalized_window_size,
        startup_window_size=max(1, min(normalized_window_size, int(startup_window_size))),
        startup_request_threshold=max(1, int(startup_request_threshold)),
        max_windows=max(1, int(max_windows)),
    )


def create_iso_parse_range_cache() -> object:
    return create_iso_stream_range_cache(
        window_size=512 * 1024,
        startup_window_size=512 * 1024,
        startup_request_threshold=512 * 1024,
        max_windows=16,
    )


def _read_remote_range_with_cache(
    url: str,
    headers: dict[str, str],
    cache: _RemoteRangeWindowCache,
    start: int,
    length: int,
    *,
    max_end: int | None = None,
    get: Callable[..., httpx.Response],
) -> bytes:
    if length <= 0:
        return b""
    chunks: list[bytes] = []
    cursor = start
    remaining = length
    while remaining > 0:
        window_start = 0
        payload: bytes | None = None
        sequential_fetch_start: int | None = None
        with cache.lock:
            for cached_window_start, cached_payload in reversed(cache.windows.items()):
                cached_window_end = cached_window_start + len(cached_payload)
                if cached_window_start <= cursor < cached_window_end:
                    window_start = cached_window_start
                    payload = cached_payload
                    cache.windows.move_to_end(cached_window_start)
                    break
                if cached_window_end == cursor:
                    sequential_fetch_start = cursor
        if payload is None:
            with cache.lock:
                has_cached_windows = bool(cache.windows)
            if not has_cached_windows and length <= cache.startup_request_threshold:
                window_start = cursor
                fetch_window_size = cache.startup_window_size
            elif sequential_fetch_start is not None:
                window_start = sequential_fetch_start
                fetch_window_size = cache.window_size
            else:
                fetch_window_size = cache.window_size
                window_start = (cursor // fetch_window_size) * fetch_window_size
            payload = _fetch_remote_range_bytes(
                url,
                headers,
                window_start,
                min(window_start + fetch_window_size - 1, max_end)
                if max_end is not None
                else window_start + fetch_window_size - 1,
                get=get,
            )
            with cache.lock:
                existing_payload = cache.windows.get(window_start)
                if existing_payload is None or len(existing_payload) < len(payload):
                    cache.windows[window_start] = payload
                    cache.windows.move_to_end(window_start)
                    while len(cache.windows) > cache.max_windows:
                        cache.windows.popitem(last=False)
                else:
                    payload = existing_payload
                    cache.windows.move_to_end(window_start)
        local_start = cursor - window_start
        available = min(max(0, len(payload) - local_start), remaining)
        if available <= 0:
            raise ValueError("远程 ISO 返回的数据长度不足")
        chunks.append(payload[local_start : local_start + available])
        cursor += available
        remaining -= available
    return b"".join(chunks)


def _read_reader_blocks(reader: RemoteRangeReader, extent: int, logical_block_size: int, block_count: int = 1) -> bytes:
    return _read_reader_bytes(reader, extent * logical_block_size, logical_block_size * block_count)


def _resolve_physical_partition_start(main_descs: Any, part_num: int) -> int:
    partitions = list(getattr(main_descs, "partitions", []) or [])
    for partition in partitions:
        if int(getattr(partition, "part_num", -1)) == part_num:
            return int(getattr(partition, "part_start_location"))
    raise ValueError("UDF 分区引用无效")


def _parse_udf_metadata_partition_map(part_ident: bytes) -> _UdfMetadataPartitionMap:
    if len(part_ident) != 62:
        raise ValueError("UDF Metadata Partition Map 长度无效")
    entity_id = _load_pycdlib_udf().UDFEntityID()
    entity_id.parse(part_ident[2:34])
    if entity_id.identifier[:23] != b"*UDF Metadata Partition":
        raise ValueError("不支持的 UDF Type 2 Partition Map")
    vol_seq_num = int.from_bytes(part_ident[34:36], "little")
    if vol_seq_num <= 0:
        raise ValueError("UDF Metadata Partition Map 卷序号无效")
    return _UdfMetadataPartitionMap(
        part_num=int.from_bytes(part_ident[36:38], "little"),
        metadata_file_location=int.from_bytes(part_ident[38:42], "little"),
    )


def _parse_udf_file_set_from_logical_volume(iso: Any) -> None:
    main_descs = getattr(iso, "udf_main_descs", None)
    logical_volumes = list(getattr(main_descs, "logical_volumes", []) or [])
    if not logical_volumes:
        raise ValueError("UDF 逻辑卷信息缺失")
    logical_volume = logical_volumes[0]
    file_set_pointer = getattr(logical_volume, "logical_volume_contents_use", None)
    if file_set_pointer is None:
        raise ValueError("UDF File Set 指针缺失")
    logical_block_size = int(getattr(iso, "logical_block_size", 2048) or 2048)
    part_ref_num = int(getattr(file_set_pointer, "part_ref_num", 0) or 0)
    partition_resolvers = _build_udf_partition_resolvers(iso._cdfp, main_descs, logical_block_size)
    if part_ref_num < 0 or part_ref_num >= len(partition_resolvers):
        raise ValueError("UDF 分区引用无效")
    if partition_resolvers[part_ref_num] is None:
        raise ValueError("UDF 分区引用无效")
    current_extent = _map_udf_partition_block_direct(
        partition_resolvers[part_ref_num],
        int(getattr(file_set_pointer, "log_block_num", 0) or 0),
    )
    file_set_and_term_data = _read_reader_blocks(iso._cdfp, current_extent, logical_block_size, 2)
    udf = _load_pycdlib_udf()
    iso.udf_file_set, iso.udf_file_set_terminator = udf.parse_file_set(
        file_set_and_term_data,
        current_extent,
        logical_block_size,
    )


def _has_udf_metadata_partition(main_descs: Any) -> bool:
    logical_volumes = list(getattr(main_descs, "logical_volumes", []) or [])
    if not logical_volumes:
        return False
    partition_maps = list(getattr(logical_volumes[0], "partition_maps", []) or [])
    return any(type(partition_map).__name__ == "UDFType2PartitionMap" for partition_map in partition_maps)


def _build_udf_partition_resolvers(reader: RemoteRangeReader, main_descs: Any, logical_block_size: int) -> tuple[_UdfPartitionResolver | None, ...]:
    logical_volumes = list(getattr(main_descs, "logical_volumes", []) or [])
    if not logical_volumes:
        raise ValueError("UDF 逻辑卷信息缺失")
    logical_volume = logical_volumes[0]
    partition_maps = list(getattr(logical_volume, "partition_maps", []) or [])
    if not partition_maps:
        partitions = list(getattr(main_descs, "partitions", []) or [])
        fallback_block_count = _physical_block_count(reader, logical_block_size)
        return tuple(
            _UdfPartitionResolver(
                part_ref_num=index,
                physical_partition_start=int(getattr(partition, "part_start_location", 0)),
                extents=(
                    _UdfPartitionExtent(
                        logical_start_block=0,
                        block_count=max(1, int(getattr(partition, "part_length", 0) or 0) or fallback_block_count),
                        physical_start_block=int(getattr(partition, "part_start_location", 0)),
                    ),
                ),
            )
            for index, partition in enumerate(partitions)
        )
    resolvers_by_ref: dict[int, _UdfPartitionResolver | None] = {index: None for index in range(len(partition_maps))}
    for part_ref_num, partition_map in enumerate(partition_maps):
        part_num = getattr(partition_map, "part_num", None)
        if part_num is None:
            continue
        try:
            physical_start = _resolve_physical_partition_start(main_descs, int(part_num))
        except ValueError:
            continue
        part_length = 0
        for partition in list(getattr(main_descs, "partitions", []) or []):
            if int(getattr(partition, "part_num", -1)) == int(part_num):
                part_length = int(getattr(partition, "part_length", 0))
                break
        if part_length <= 0:
            part_length = _physical_block_count(reader, logical_block_size)
        resolvers_by_ref[part_ref_num] = _UdfPartitionResolver(
            part_ref_num=part_ref_num,
            physical_partition_start=physical_start,
            extents=(
                _UdfPartitionExtent(
                    logical_start_block=0,
                    block_count=max(1, part_length),
                    physical_start_block=physical_start,
                ),
            ),
        )
    udf = _load_pycdlib_udf()
    for part_ref_num, partition_map in enumerate(partition_maps):
        if resolvers_by_ref.get(part_ref_num) is not None:
            continue
        if type(partition_map).__name__ != "UDFType2PartitionMap":
            continue
        metadata_map = _parse_udf_metadata_partition_map(bytes(getattr(partition_map, "part_ident", b"")))
        physical_start = _resolve_physical_partition_start(main_descs, metadata_map.part_num)
        metadata_entry_data = _read_reader_blocks(
            reader,
            physical_start + metadata_map.metadata_file_location,
            logical_block_size,
        )
        metadata_entry = udf.parse_file_entry(
            metadata_entry_data,
            physical_start + metadata_map.metadata_file_location,
            metadata_map.metadata_file_location,
            None,
        )
        if metadata_entry is None:
            raise ValueError("UDF Metadata Partition File Entry 缺失")
        extents: list[_UdfPartitionExtent] = []
        logical_start_block = 0
        for desc in list(getattr(metadata_entry, "alloc_descs", []) or []):
            if isinstance(desc, udf.UDFShortAD):
                physical_block = physical_start + int(getattr(desc, "log_block_num", 0))
            elif isinstance(desc, udf.UDFLongAD):
                base_resolver = resolvers_by_ref.get(int(getattr(desc, "part_ref_num", -1)))
                if base_resolver is None:
                    raise ValueError("UDF Metadata Partition 基础分区引用无效")
                physical_block = _map_udf_partition_block_direct(base_resolver, int(getattr(desc, "log_block_num", 0)))
            else:
                raise ValueError("不支持的 UDF Metadata Allocation Descriptor")
            block_count = _ceil_blocks(int(getattr(desc, "extent_length", 0)), logical_block_size)
            extents.append(
                _UdfPartitionExtent(
                    logical_start_block=logical_start_block,
                    block_count=block_count,
                    physical_start_block=physical_block,
                )
            )
            logical_start_block += block_count
        if not extents:
            raise ValueError("UDF Metadata Partition 数据区缺失")
        resolvers_by_ref[part_ref_num] = _UdfPartitionResolver(
            part_ref_num=part_ref_num,
            physical_partition_start=physical_start,
            extents=tuple(extents),
        )
    return tuple(resolvers_by_ref[index] for index in range(len(partition_maps)))


def _build_remote_udf_iso(reader: RemoteRangeReader, iso: Any) -> _RemoteUdfIso:
    logical_block_size = int(getattr(iso, "logical_block_size", 2048) or 2048)
    main_descs = getattr(iso, "udf_main_descs", None)
    if main_descs is None:
        raise ValueError("UDF 描述符缺失")
    partition_resolvers = _build_udf_partition_resolvers(reader, main_descs, logical_block_size)
    file_set = getattr(iso, "udf_file_set", None)
    if file_set is None:
        raise ValueError("UDF File Set 缺失")
    return _RemoteUdfIso(
        reader=reader,
        logical_block_size=logical_block_size,
        main_descs=main_descs,
        file_set=file_set,
        partition_resolvers=partition_resolvers,
    )


def _map_udf_partition_block_direct(resolver: _UdfPartitionResolver, logical_block_num: int) -> int:
    for extent in resolver.extents:
        end_block = extent.logical_start_block + extent.block_count
        if extent.logical_start_block <= logical_block_num < end_block:
            return extent.physical_start_block + (logical_block_num - extent.logical_start_block)
    raise ValueError("UDF 分区引用无效")


def _map_udf_partition_block(remote_iso: _RemoteUdfIso, part_ref_num: int, logical_block_num: int) -> tuple[int, int]:
    if part_ref_num < 0 or part_ref_num >= len(remote_iso.partition_resolvers):
        raise ValueError("UDF 分区引用无效")
    resolver = remote_iso.partition_resolvers[part_ref_num]
    if resolver is None:
        raise ValueError("UDF 分区引用无效")
    return _map_udf_partition_block_direct(resolver, logical_block_num), resolver.physical_partition_start


def _parse_udf_entry_from_long_ad(remote_iso: _RemoteUdfIso, allocation: Any, parent: Any | None) -> _UdfEntryRef:
    udf = _load_pycdlib_udf()
    abs_extent, _part_start = _map_udf_partition_block(
        remote_iso,
        int(getattr(allocation, "part_ref_num", 0)),
        int(getattr(allocation, "log_block_num", 0)),
    )
    extent_length = int(getattr(allocation, "extent_length", remote_iso.logical_block_size) or remote_iso.logical_block_size)
    entry_data = _read_reader_blocks(
        remote_iso.reader,
        abs_extent,
        remote_iso.logical_block_size,
        _ceil_blocks(extent_length, remote_iso.logical_block_size),
    )
    record = udf.parse_file_entry(
        entry_data,
        abs_extent,
        int(getattr(allocation, "log_block_num", 0)),
        parent,
    )
    if record is None:
        raise ValueError("UDF File Entry 缺失")
    return _UdfEntryRef(record=record, part_ref_num=int(getattr(allocation, "part_ref_num", 0)))


def _decode_udf_name(file_ident: Any) -> str:
    data = bytes(getattr(file_ident, "fi", b""))
    encoding = getattr(file_ident, "encoding", "latin-1")
    if not data:
        return ""
    return data.decode("utf-16_be" if encoding != "latin-1" else "latin-1")


def _iter_udf_dir_entries(remote_iso: _RemoteUdfIso, entry_ref: _UdfEntryRef) -> list[Any]:
    udf = _load_pycdlib_udf()
    file_idents: list[Any] = []
    for desc in list(getattr(entry_ref.record, "alloc_descs", []) or []):
        if isinstance(desc, udf.UDFShortAD):
            abs_extent, part_start = _map_udf_partition_block(
                remote_iso,
                entry_ref.part_ref_num,
                int(getattr(desc, "log_block_num", 0)),
            )
        elif isinstance(desc, udf.UDFLongAD):
            abs_extent, part_start = _map_udf_partition_block(
                remote_iso,
                int(getattr(desc, "part_ref_num", 0)),
                int(getattr(desc, "log_block_num", 0)),
            )
        else:
            raise ValueError("不支持的 UDF 目录分配描述符")
        extent_length = int(getattr(desc, "extent_length", 0))
        data = _read_reader_blocks(
            remote_iso.reader,
            abs_extent,
            remote_iso.logical_block_size,
            _ceil_blocks(extent_length, remote_iso.logical_block_size),
        )[:extent_length]
        offset = 0
        while offset < len(data):
            current_extent = (abs_extent * remote_iso.logical_block_size + offset) // remote_iso.logical_block_size
            file_ident, bytes_forward = udf.parse_file_ident(data[offset:], current_extent, part_start, entry_ref.record)
            offset += bytes_forward
            file_idents.append(file_ident)
    return file_idents


def _remote_udf_root_entry(remote_iso: _RemoteUdfIso) -> _UdfEntryRef:
    return _parse_udf_entry_from_long_ad(remote_iso, remote_iso.file_set.root_dir_icb, None)


def _find_remote_udf_entry(remote_iso: _RemoteUdfIso, normalized_path: str) -> _UdfEntryRef:
    if normalized_path == "/":
        return _remote_udf_root_entry(remote_iso)
    components = [component for component in normalized_path.split("/") if component]
    current = _remote_udf_root_entry(remote_iso)
    for component in components:
        matched_file_ident = None
        for file_ident in _iter_udf_dir_entries(remote_iso, current):
            if file_ident.is_parent():
                continue
            if _decode_udf_name(file_ident).upper() == component:
                matched_file_ident = file_ident
                break
        if matched_file_ident is None:
            raise ValueError("UDF 路径不存在")
        current = _parse_udf_entry_from_long_ad(remote_iso, matched_file_ident.icb, current.record)
    return current


def _walk_remote_udf_paths(remote_iso: _RemoteUdfIso) -> list[str]:
    paths: list[str] = []
    stack: list[tuple[str, _UdfEntryRef]] = [("/", _remote_udf_root_entry(remote_iso))]
    while stack:
        current_path, current_entry = stack.pop()
        paths.append(_normalize_iso_path(current_path))
        if not current_entry.record.is_dir():
            continue
        for file_ident in _iter_udf_dir_entries(remote_iso, current_entry):
            if file_ident.is_parent():
                continue
            name = _decode_udf_name(file_ident)
            if not name:
                continue
            child_path = _normalize_iso_path(f"{current_path}/{name}")
            paths.append(child_path)
            if file_ident.is_dir():
                child_entry = _parse_udf_entry_from_long_ad(remote_iso, file_ident.icb, current_entry.record)
                stack.append((child_path, child_entry))
    return sorted(set(paths))


def _stat_remote_udf_streams(remote_iso: _RemoteUdfIso) -> list[BluRayIsoStream]:
    stream_dir = _find_remote_udf_entry(remote_iso, "/BDMV/STREAM")
    streams: list[BluRayIsoStream] = []
    for file_ident in _iter_udf_dir_entries(remote_iso, stream_dir):
        if file_ident.is_parent() or file_ident.is_dir():
            continue
        name = _decode_udf_name(file_ident)
        normalized_path = _normalize_iso_path(f"/BDMV/STREAM/{name}")
        if not _BLURAY_STREAM_RE.match(normalized_path):
            continue
        entry_ref = _parse_udf_entry_from_long_ad(remote_iso, file_ident.icb, stream_dir.record)
        streams.append(BluRayIsoStream(path=normalized_path, size=_stream_size_from_record(entry_ref.record)))
    return streams


def _build_cached_iso_stream_source(remote_iso: _RemoteUdfIso, entry_ref: _UdfEntryRef) -> _CachedIsoStreamSource:
    udf = _load_pycdlib_udf()
    segments: list[_CachedIsoSegment] = []
    logical_offset = 0
    for desc in list(getattr(entry_ref.record, "alloc_descs", []) or []):
        extent_length = int(getattr(desc, "extent_length", 0))
        if extent_length <= 0:
            continue
        if isinstance(desc, udf.UDFShortAD):
            abs_extent, _part_start = _map_udf_partition_block(
                remote_iso,
                entry_ref.part_ref_num,
                int(getattr(desc, "log_block_num", 0)),
            )
        elif isinstance(desc, udf.UDFLongAD):
            abs_extent, _part_start = _map_udf_partition_block(
                remote_iso,
                int(getattr(desc, "part_ref_num", 0)),
                int(getattr(desc, "log_block_num", 0)),
            )
        else:
            raise ValueError("不支持的 UDF 文件分配描述符")
        segments.append(
            _CachedIsoSegment(
                logical_offset=logical_offset,
                length=extent_length,
                physical_start=abs_extent * remote_iso.logical_block_size,
            )
        )
        logical_offset += extent_length
    if not segments:
        raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
    return _CachedIsoStreamSource(size=_stream_size_from_record(entry_ref.record), segments=tuple(segments))


def _read_remote_udf_file_range(
    remote_iso: _RemoteUdfIso,
    entry_ref: _UdfEntryRef,
    start: int,
    inclusive_end: int,
) -> bytes:
    udf = _load_pycdlib_udf()
    chunks: list[bytes] = []
    offset = 0
    for desc in list(getattr(entry_ref.record, "alloc_descs", []) or []):
        extent_length = int(getattr(desc, "extent_length", 0))
        if extent_length <= 0:
            continue
        extent_end = offset + extent_length - 1
        if start > extent_end:
            offset += extent_length
            continue
        if inclusive_end < offset:
            break
        local_start = max(0, start - offset)
        local_end = min(extent_length - 1, inclusive_end - offset)
        if isinstance(desc, udf.UDFShortAD):
            abs_extent, _part_start = _map_udf_partition_block(
                remote_iso,
                entry_ref.part_ref_num,
                int(getattr(desc, "log_block_num", 0)),
            )
        elif isinstance(desc, udf.UDFLongAD):
            abs_extent, _part_start = _map_udf_partition_block(
                remote_iso,
                int(getattr(desc, "part_ref_num", 0)),
                int(getattr(desc, "log_block_num", 0)),
            )
        else:
            raise ValueError("不支持的 UDF 文件分配描述符")
        absolute_start = abs_extent * remote_iso.logical_block_size + local_start
        chunks.append(_read_reader_bytes(remote_iso.reader, absolute_start, local_end - local_start + 1))
        if offset + local_end >= inclusive_end:
            break
        offset += extent_length
    return b"".join(chunks)


def _read_cached_iso_stream_source_range(
    reader: RemoteRangeReader,
    source: _CachedIsoStreamSource,
    start: int,
    inclusive_end: int,
) -> bytes:
    chunks: list[bytes] = []
    for segment in source.segments:
        segment_end = segment.logical_offset + segment.length - 1
        if start > segment_end:
            continue
        if inclusive_end < segment.logical_offset:
            break
        local_start = max(0, start - segment.logical_offset)
        local_end = min(segment.length - 1, inclusive_end - segment.logical_offset)
        chunks.append(
            _read_reader_bytes(
                reader,
                segment.physical_start + local_start,
                local_end - local_start + 1,
            )
        )
        if segment.logical_offset + local_end >= inclusive_end:
            break
    return b"".join(chunks)


def _parse_udf_descriptors_with_fallback(iso: Any, invalid_iso: type[BaseException] | None) -> None:
    try:
        iso._parse_udf_descriptors()
    except Exception as exc:
        if invalid_iso is None or not isinstance(exc, invalid_iso):
            raise
        if _UDF_FILE_SET_TAG_MESSAGE not in str(exc):
            raise
        _parse_udf_file_set_from_logical_volume(iso)


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
            _parse_udf_descriptors_with_fallback(iso, invalid_iso)
            if _has_udf_metadata_partition(getattr(iso, "udf_main_descs", None)):
                remote_udf = _build_remote_udf_iso(reader, iso)
                _safe_close_iso(iso)
                return remote_udf
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
        range_cache: object | None = None,
    ) -> None:
        super().__init__()
        self._url = url
        self._headers = dict(headers)
        self._get = get
        self._position = 0
        self._size: int | None = None
        self._range_cache = (
            range_cache
            if isinstance(range_cache, _RemoteRangeWindowCache)
            else create_iso_parse_range_cache()
        )

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
        length = min(len(view), size - self._position)
        if self._range_cache is not None:
            payload = _read_remote_range_with_cache(
                self._url,
                self._headers,
                self._range_cache,
                self._position,
                length,
                max_end=size - 1,
                get=self._get,
            )
        else:
            end = self._position + length - 1
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
    if isinstance(iso, _RemoteUdfIso):
        return _walk_remote_udf_paths(iso)
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


def _read_u16be(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("MPLS 数据不完整")
    return int.from_bytes(data[offset : offset + 2], "big")


def _read_u32be(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("MPLS 数据不完整")
    return int.from_bytes(data[offset : offset + 4], "big")


def _parse_mpls_playlist(path: str, data: bytes) -> _ParsedMplsPlaylist:
    if len(data) < 20 or data[:4] != b"MPLS":
        raise ValueError("无效的 Blu-ray playlist")
    playlist_start = _read_u32be(data, 8)
    playlist_length = _read_u32be(data, playlist_start)
    playlist_end = min(len(data), playlist_start + 4 + playlist_length)
    header_offset = playlist_start + 4
    play_item_count = _read_u16be(data, header_offset + 2)
    play_item_offset = header_offset + 6
    play_items: list[_MplsPlayItem] = []
    total_duration = 0
    for _ in range(play_item_count):
        item_length = _read_u16be(data, play_item_offset)
        item_start = play_item_offset + 2
        item_end = item_start + item_length
        if item_end > playlist_end or item_end > len(data):
            raise ValueError("MPLS play item 超出边界")
        if item_length < 20:
            raise ValueError("MPLS play item 长度无效")
        clip_name = data[item_start : item_start + 5].decode("ascii", errors="ignore").strip().upper()
        clip_codec = data[item_start + 5 : item_start + 9].decode("ascii", errors="ignore").strip().upper()
        in_time = _read_u32be(data, item_start + 12)
        out_time = _read_u32be(data, item_start + 16)
        duration = max(0, out_time - in_time)
        if clip_name and clip_codec == "M2TS":
            play_items.append(
                _MplsPlayItem(
                    clip_id=clip_name,
                    stream_path=f"/BDMV/STREAM/{clip_name}.M2TS",
                    in_time=in_time,
                    out_time=out_time,
                    duration=duration,
                )
            )
            total_duration += duration
        play_item_offset = item_end
    if not play_items:
        raise ValueError("Blu-ray playlist 中没有可播放的片段")
    return _ParsedMplsPlaylist(
        path=_normalize_iso_path(path),
        play_items=tuple(play_items),
        duration=total_duration,
    )


def _parse_clpi_entry_points(clip_id: str, data: bytes) -> _ParsedClpi:
    if len(data) < 26 or data[:4] != b"HDMV":
        raise ValueError("无效的 Blu-ray clip info")
    cpi_start = _read_u32be(data, 16)
    entry_count = _read_u16be(data, cpi_start)
    cursor = cpi_start + 2
    entry_points: list[_ClpiEntryPoint] = []
    for _ in range(entry_count):
        entry_points.append(
            _ClpiEntryPoint(
                time_45k=_read_u32be(data, cursor),
                byte_offset=_read_u32be(data, cursor + 4),
            )
        )
        cursor += 8
    if not entry_points:
        raise ValueError("Blu-ray clip info 中没有可用入口点")
    return _ParsedClpi(
        clip_id=clip_id,
        entry_points=tuple(sorted(entry_points, key=lambda item: item.time_45k)),
    )


def _read_remote_udf_file(remote_iso: _RemoteUdfIso, entry_ref: _UdfEntryRef) -> bytes:
    total_size = _stream_size_from_record(entry_ref.record)
    if total_size <= 0:
        return b""
    return _read_remote_udf_file_range(remote_iso, entry_ref, 0, total_size - 1)


def _read_remote_udf_clipinfo(remote_iso: _RemoteUdfIso, clip_id: str) -> _ParsedClpi:
    clipinfo_path = f"/BDMV/CLIPINF/{clip_id}.CLPI"
    entry_ref = _find_remote_udf_entry(remote_iso, clipinfo_path)
    return _parse_clpi_entry_points(clip_id, _read_remote_udf_file(remote_iso, entry_ref))


def _iter_remote_udf_playlists(remote_iso: _RemoteUdfIso) -> list[tuple[str, bytes]]:
    playlist_dir = _find_remote_udf_entry(remote_iso, "/BDMV/PLAYLIST")
    playlists: list[tuple[str, bytes]] = []
    for file_ident in _iter_udf_dir_entries(remote_iso, playlist_dir):
        if file_ident.is_parent() or file_ident.is_dir():
            continue
        name = _decode_udf_name(file_ident)
        normalized_path = _normalize_iso_path(f"/BDMV/PLAYLIST/{name}")
        if not _BLURAY_PLAYLIST_RE.match(normalized_path):
            continue
        entry_ref = _parse_udf_entry_from_long_ad(remote_iso, file_ident.icb, playlist_dir.record)
        playlists.append((normalized_path, _read_remote_udf_file(remote_iso, entry_ref)))
    return sorted(playlists, key=lambda item: item[0])


def _compose_cached_iso_stream_sources(
    sources: list[_CachedIsoStreamSource],
) -> _CachedIsoStreamSource:
    segments: list[_CachedIsoSegment] = []
    logical_offset = 0
    for source in sources:
        for segment in source.segments:
            segments.append(
                _CachedIsoSegment(
                    logical_offset=logical_offset + segment.logical_offset,
                    length=segment.length,
                    physical_start=segment.physical_start,
                )
            )
        logical_offset += source.size
    if logical_offset <= 0 or not segments:
        raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
    return _CachedIsoStreamSource(size=logical_offset, segments=tuple(segments))


def _compute_trimmed_clip_range(
    parsed_clpi: _ParsedClpi,
    in_time: int,
    out_time: int,
    stream_size: int,
) -> tuple[int, int]:
    if stream_size <= 0:
        raise ValueError("Blu-ray clip 大小无效")
    start_point = next(
        (entry for entry in reversed(parsed_clpi.entry_points) if entry.time_45k <= in_time),
        None,
    )
    end_point = next(
        (entry for entry in parsed_clpi.entry_points if entry.time_45k > out_time),
        None,
    )
    start = ((0 if start_point is None else start_point.byte_offset) // 192) * 192
    end_exclusive = stream_size if end_point is None else ((end_point.byte_offset + 191) // 192) * 192
    end_exclusive = min(stream_size, end_exclusive)
    if end_exclusive <= start:
        raise ValueError("Blu-ray clip 裁剪区间无效")
    return start, end_exclusive


def _slice_cached_iso_stream_source(
    source: _CachedIsoStreamSource,
    start: int,
    length: int,
) -> _CachedIsoStreamSource:
    if start < 0 or length <= 0 or start + length > source.size:
        raise ValueError("Blu-ray clip 裁剪区间超出边界")
    end_exclusive = start + length
    segments: list[_CachedIsoSegment] = []
    logical_offset = 0
    for segment in source.segments:
        segment_start = segment.logical_offset
        segment_end = segment.logical_offset + segment.length
        if segment_end <= start:
            continue
        if segment_start >= end_exclusive:
            break
        local_start = max(start, segment_start)
        local_end = min(end_exclusive, segment_end)
        slice_length = local_end - local_start
        segments.append(
            _CachedIsoSegment(
                logical_offset=logical_offset,
                length=slice_length,
                physical_start=segment.physical_start + (local_start - segment_start),
            )
        )
        logical_offset += slice_length
    if logical_offset != length or not segments:
        raise ValueError("Blu-ray clip 裁剪区间无法映射到底层分段")
    return _CachedIsoStreamSource(size=length, segments=tuple(segments))


def _build_trimmed_playlist_clip_source(
    remote_iso: _RemoteUdfIso,
    play_item: _MplsPlayItem,
) -> _CachedIsoStreamSource:
    clip_entry_ref = _find_remote_udf_entry(remote_iso, play_item.stream_path)
    clip_source = _build_cached_iso_stream_source(remote_iso, clip_entry_ref)
    parsed_clpi = _read_remote_udf_clipinfo(remote_iso, play_item.clip_id)
    start, end_exclusive = _compute_trimmed_clip_range(
        parsed_clpi,
        play_item.in_time,
        play_item.out_time,
        clip_source.size,
    )
    return _slice_cached_iso_stream_source(clip_source, start, end_exclusive - start)


def _prepare_remote_udf_playlist_playback(remote_iso: _RemoteUdfIso) -> IsoPlaybackPlan | None:
    playlist_candidates: list[_ParsedMplsPlaylist] = []
    try:
        playlists = _iter_remote_udf_playlists(remote_iso)
    except ValueError:
        return None
    for playlist_path, playlist_data in playlists:
        try:
            parsed = _parse_mpls_playlist(playlist_path, playlist_data)
        except ValueError:
            continue
        playlist_candidates.append(parsed)
    for parsed in sorted(
        playlist_candidates,
        key=lambda item: (item.duration, item.path),
        reverse=True,
    ):
        try:
            child_sources = [
                _build_trimmed_playlist_clip_source(remote_iso, play_item)
                for play_item in parsed.play_items
            ]
        except ValueError:
            continue
        selected_source = _compose_cached_iso_stream_sources(child_sources)
        selected_path = parsed.play_items[0].stream_path
        playlist_segments = (
            tuple(
                IsoPlaybackSegment(
                    stream_path=play_item.stream_path,
                    stream_size=child_source.size,
                    duration_seconds=(play_item.duration / 45000.0) if play_item.duration > 0 else 0.0,
                    source=child_source,
                )
                for play_item, child_source in zip(parsed.play_items, child_sources, strict=True)
            )
            if len(parsed.play_items) > 1
            else ()
        )
        return IsoPlaybackPlan(
            stream=BluRayIsoStream(path=selected_path, size=selected_source.size),
            source=selected_source,
            playlist_segments=playlist_segments,
        )
    return None


def prepare_iso_playback(
    url: str,
    headers: dict[str, str],
    *,
    get: Callable[..., httpx.Response] = httpx.get,
) -> IsoPlaybackPlan:
    reader = RemoteRangeReader(url, headers, get=get)
    iso = _open_pycdlib_iso(reader)
    try:
        if isinstance(iso, _RemoteUdfIso):
            playlist_plan = _prepare_remote_udf_playlist_playback(iso)
            if playlist_plan is not None:
                return playlist_plan
            streams = _stat_remote_udf_streams(iso)
            selected_stream = pick_main_feature_stream(streams)
            entry_ref = _find_remote_udf_entry(iso, selected_stream.path)
            return IsoPlaybackPlan(
                stream=selected_stream,
                source=_build_cached_iso_stream_source(iso, entry_ref),
            )
        streams: list[BluRayIsoStream] = []
        for path in _walk_iso_paths(iso):
            if not _BLURAY_STREAM_RE.match(path):
                continue
            record = iso.get_record(udf_path=path)
            streams.append(BluRayIsoStream(path=path, size=_stream_size_from_record(record)))
        return IsoPlaybackPlan(stream=pick_main_feature_stream(streams))
    finally:
        _safe_close_iso(iso)


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
        if isinstance(iso, _RemoteUdfIso):
            return _stat_remote_udf_streams(iso)
        streams: list[BluRayIsoStream] = []
        for path in _walk_iso_paths(iso):
            if not _BLURAY_STREAM_RE.match(path):
                continue
            record = iso.get_record(udf_path=path)
            streams.append(BluRayIsoStream(path=path, size=_stream_size_from_record(record)))
        return streams
    finally:
        _safe_close_iso(iso)


def read_iso_stream_range_from_source(
    url: str,
    headers: dict[str, str],
    source: object,
    start: int,
    end: int | None,
    *,
    range_cache: object | None = None,
    get: Callable[..., httpx.Response] = httpx.get,
) -> tuple[bytes, int]:
    if not isinstance(source, _CachedIsoStreamSource):
        raise ValueError("unsupported iso stream source")
    total_size = int(source.size)
    if total_size <= 0:
        raise ValueError("Blu-ray ISO 中没有可播放的 m2ts 文件")
    if start < 0:
        raise ValueError("invalid range start")
    if start >= total_size:
        return b"", total_size
    inclusive_end = total_size - 1 if end is None else min(end, total_size - 1)
    if inclusive_end < start:
        return b"", total_size
    payload_parts: list[bytes] = []
    shared_cache = range_cache if isinstance(range_cache, _RemoteRangeWindowCache) else None
    for segment in source.segments:
        segment_end = segment.logical_offset + segment.length - 1
        if start > segment_end:
            continue
        if inclusive_end < segment.logical_offset:
            break
        local_start = max(0, start - segment.logical_offset)
        local_end = min(segment.length - 1, inclusive_end - segment.logical_offset)
        absolute_start = segment.physical_start + local_start
        absolute_length = local_end - local_start + 1
        if shared_cache is not None:
            payload_parts.append(
                _read_remote_range_with_cache(
                    url,
                    headers,
                    shared_cache,
                    absolute_start,
                    absolute_length,
                    max_end=segment.physical_start + segment.length - 1,
                    get=get,
                )
            )
        else:
            payload_parts.append(
                _fetch_remote_range_bytes(
                    url,
                    headers,
                    absolute_start,
                    absolute_start + absolute_length - 1,
                    get=get,
                )
            )
        if segment.logical_offset + local_end >= inclusive_end:
            break
    payload = b"".join(payload_parts)
    return payload, total_size


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
        if isinstance(iso, _RemoteUdfIso):
            entry_ref = _find_remote_udf_entry(iso, normalized_path)
            record = entry_ref.record
        else:
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
        if isinstance(iso, _RemoteUdfIso):
            payload = _read_remote_udf_file_range(iso, entry_ref, start, inclusive_end)
        else:
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
        prepare_playback: Callable[[str, dict[str, str]], IsoPlaybackPlan] = prepare_iso_playback,
    ) -> None:
        self._list_entries = list_entries
        self._stat_streams = stat_streams
        self._prepare_playback = prepare_playback
        self._prepare_playback_cache: dict[tuple[str, tuple[tuple[str, str], ...]], IsoPlaybackPlan] = {}
        self._prepare_playback_lock = Lock()

    def _prepare_playback_cache_key(self, url: str, headers: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return url, tuple(sorted((str(key), str(value)) for key, value in headers.items()))

    def prepare_playback(self, url: str, headers: dict[str, str]) -> IsoPlaybackPlan:
        cache_key = self._prepare_playback_cache_key(url, headers)
        with self._prepare_playback_lock:
            cached = self._prepare_playback_cache.get(cache_key)
        if cached is not None:
            return cached
        plan = self._prepare_playback(url, headers)
        with self._prepare_playback_lock:
            cached = self._prepare_playback_cache.get(cache_key)
            if cached is not None:
                return cached
            self._prepare_playback_cache[cache_key] = plan
        return plan

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
